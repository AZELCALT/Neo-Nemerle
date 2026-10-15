using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using static Nemerle.Compiler.NitraRecognition;
using static Nemerle.Compiler.nitra_syntax;
public static class NitraSyntaxChecks
{
    static int checks;
    static void Check(bool ok, string name) { if (!ok) throw new Exception(name); ++checks; }
    static NitraPreparedGrammar Prepare(string text, string module="Test")
    {
        var doc=NitraSyntax.Read(text,"checks.nitra",true);
        Check(doc.Success && doc.SurfaceValidated, "native declaration validation: "+doc.ToJson());
        return NitraSyntax.Prepare(NitraSyntax.BaselineDefinitions(true).Append(doc),new[]{module},true);
    }
    static void Match(NitraPreparedGrammar g,string rule,string input,bool expected=true)
    {
        var r=g.Recognize(rule,input);
        Check(r.Complete && r.Accepted==expected,rule+" input="+input+" expected="+expected+" diagnostics="+string.Join(";",r.Diagnostics));
        Check(r.Regions.Select(n=>(n.Operation,n.Start)).Distinct().Count()==r.Regions.Count,"unique shared operation/position regions");
        using var json=JsonDocument.Parse(r.ToJson());
        Check(json.RootElement.GetProperty("accepted").GetBoolean()==r.Accepted,"recognition JSON");
    }
    public static int Main(string[] args)
    {
        NitraSyntax.ReadDefinitions("",""); ++checks; // no opt-in: Nitra syntax is part of the language
        var grammar=Prepare(@"syntax module Test {
          using Nitra.Core;
          keyword regex IdentifierBody rule S;
          [StartRule] syntax Start = ""begin"" Expr ""end"";
          syntax Expr {
            precedence Add:
            | Add = Expr ""+"" Expr;
            precedence Multiply:
            | Multiply = Expr ""*"" Expr;
            precedence 0:
            | Number = Digits;
            | Group = ""("" Expr "")"";
          }
          regex Digits = ['0'..'9']+;
          syntax Tight = Expr ^ + Multiply;
          [ExplicitSpaces] syntax Exact = ""a"" ""b"";
          syntax Loose = ""a"" ""b"";
          [ExplicitSpaces] syntax List = (""a""; "",""; ?){1,3};
          [ExplicitSpaces] syntax EmptyList = (""a""; "","" )*;
          regex Bound = ['a'..'z']{2,4};
          regex Sub = (""a"" | ""ab"") - ""a"";
          alias Nested = Recursive;
          syntax Recursive {
            precedence Negate:
            | Negate = ""-"" Nested;
            precedence 0:
            | Atom = ""x"";
            | Group = ""("" Nested "")"";
          }
          regex Prefixes = ""a"" | ""ab"";
          regex RegexSequence = Prefixes ""b"";
          regex RegexEpsilon = (""a""?)*;
          regex RegexSubtractCall = Prefixes - ""a"";
          regex RegexRepeat = ""a""* ""a"";
          alias SpacedAlias = ""a"" ""b"";
          syntax AliasUse = SpacedAlias;
          [ExplicitSpaces] syntax AliasExact = SpacedAlias;
          regex Words = ""if"" | ""while"";
          syntax WordThenNumber = Words Digits;
          syntax Captured = Value=Digits;
          [ExplicitSpaces] syntax RawOptional = ""a""? ""a"";
          [ExplicitSpaces] syntax Predicate = &""a"" !""b"" ""a"";
          regex Lower = [Ll]+;
          regex NotDigit = [^Nd];
          [ExplicitSpaces] syntax Scalar = Any;
        }");
        Check(grammar.Recognize("Test.Captured","123").Regions.Any(x=>x.Kind=="capture" && x.Label=="Value" && x.Start==0 && x.Ends.Contains(3)),"syntax capture span retained");
        Check(grammar.StartRules.Contains("Test.Start"),"StartRule metadata");
        Match(grammar,"Test.Start","  begin 1+2*3 end ");
        Match(grammar,"Test.Start","beginning 1 end",false);
        Match(grammar,"Test.Start","begin (1+2)*3 end");
        Match(grammar,"Test.Start","begin 1+ end",false);
        Match(grammar,"Test.Tight","1"); Match(grammar,"Test.Tight","1*2",false);
        Match(grammar,"Test.Exact","ab"); Match(grammar,"Test.Exact","a b",false);
        Match(grammar,"Test.Loose","a b");
        foreach(var s in new[]{"a","a,b","a,a,a,","a,"}) Match(grammar,"Test.List",s,s!="a,b");
        Match(grammar,"Test.List","a,a,a,a",false);
        Match(grammar,"Test.EmptyList",""); Match(grammar,"Test.EmptyList","a,a");
        Match(grammar,"Test.Bound","abcd"); Match(grammar,"Test.Bound","a",false); Match(grammar,"Test.Bound","abcde",false);
        Match(grammar,"Test.Sub","ab"); Match(grammar,"Test.Sub","a",false);
        Match(grammar,"Test.Recursive","-(x)"); Match(grammar,"Test.Recursive","--x");
        Match(grammar,"Test.RegexSequence","ab"); Match(grammar,"Test.RegexSequence","abb");
        Match(grammar,"Test.RegexEpsilon",""); Match(grammar,"Test.RegexEpsilon","aaa");
        Match(grammar,"Test.RegexSubtractCall","ab"); Match(grammar,"Test.RegexSubtractCall","a",false);
        Match(grammar,"Test.RegexRepeat","a"); Match(grammar,"Test.RegexRepeat","aaa");
        Match(grammar,"Test.AliasUse","a b"); Match(grammar,"Test.AliasExact","a b",false);
        Match(grammar,"Test.WordThenNumber","if 1"); Match(grammar,"Test.WordThenNumber","if1",false);
        Match(grammar,"Test.RawOptional","aa"); Match(grammar,"Test.RawOptional","a",false);
        Match(grammar,"Test.Predicate","a"); Match(grammar,"Test.Predicate","b",false);
        Match(grammar,"Test.Lower","λé"); Match(grammar,"Test.Lower","A",false);
        Match(grammar,"Test.NotDigit","x"); Match(grammar,"Test.NotDigit","1",false);
        Match(grammar,"Test.Scalar","😀"); Match(grammar,"Test.Scalar","\uD800",false);
        var ext=Prepare(@"namespace Example {
          syntax module Base { token Item { | A = ""a""; } }
          syntax module More { using B = Base; extend token B.Item { | B = ""b""; } [StartRule] syntax Start = B.Item; }
        }","Example.More");
        Match(ext,"Example.More.Start","a"); Match(ext,"Example.More.Start","b");
        var unicodeGrammar=Prepare("syntax module Café { using Nitra.Core; [StartRule] syntax a\u0301 = \"x\"; }","Café");
        Match(unicodeGrammar,"Café.a\u0301","x");
        var sql=Prepare(@"syntax module Sql {
          using Nitra.Core;
          keyword regex IdentifierBody rule S;
          [StartRule] syntax Query = ""SELECT"" (Identifier; "","" )+ ""FROM"" Identifier (""WHERE"" Identifier ""="" Value)? "";"";
          token Identifier = IdentifierBody;
          regex Digits = ['0'..'9']+;
          token Value { | Number = Digits; | Quoted = ""'"" (!""'"" Any)* ""'""; }
        }", "Sql");
        Match(sql,"Sql.Query","SELECT a,b FROM table WHERE a = 'hello';");
        Match(sql,"Sql.Query","SELECT FROM;",false);
        var dyn=Prepare(@"syntax module Test { [DynamicSyntaxExtender] syntax Start = ""x""; }");
        var deferred=dyn.Recognize("Test.Start","x");
        Check(!deferred.Complete && deferred.Diagnostics.Any(x=>x.Contains("dynamic grammar")),"dynamic execution explicitly deferred");
        foreach(var s in new[]{"syntax module X { syntax A = ; }","syntax module X { syntax A = (\"x\"; }","syntax module X { unknown garbage; }","}","syntax module X { regex A = '\\uQQQQ'; }", "syntax module X { regex A = 'a'{999999999999}; }"})
            Check(!NitraSyntax.Read(s,"bad.nitra",true).Success,"invalid declaration rejected: "+s);
        var retained=NitraSyntax.Read("syntax module X { syntax A = \"x\" { Value() : int = 42; } }","retained.nitra",true);
        Check(retained.Success && retained.Declarations[0].Children.Any(d=>d.Children.Any(c=>c.Text.Contains("42"))),"semantic body retained at its declaration");
        var reused=grammar.Recognize("Test.Start","begin 1+2 end");
        Check(reused.Accepted,"prepared grammar reusable");
        if(args.Length>0)
        {
            foreach(var (file,module,rule,input) in new[]{("arithmetic.nitra","Arithmetic","Arithmetic.Start","expression.txt"),("sql.nitra","Sql","Sql.Query","query.sql")})
            {
                var sample=Prepare(File.ReadAllText(Path.Combine(args[0],file)),module);
                Match(sample,rule,File.ReadAllText(Path.Combine(args[0],input)));
            }
        }
        Console.WriteLine($"PASS: {checks} Nitra declaration/recognition checks");
        return 0;
    }
}
