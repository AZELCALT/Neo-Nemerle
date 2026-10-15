using System;
using System.Linq;
using System.Reflection;
using BindingFlags = System.Reflection.BindingFlags;
using System.Collections;
using static Nemerle.Compiler.nitra_compilation;
using static Nemerle.Compiler.NitraRecognition;
using static Nemerle.Compiler.NitraStructures;
using static Nemerle.Compiler.nitra_syntax;
using static Nemerle.Compiler.NitraTypes;
using static Nemerle.Compiler.Parsetree;
using static Nemerle.Compiler.type_info;
public static class NitraStructureChecks
{
    static int checks;
    static void Check(bool value, string message) { if(!value) throw new Exception(message); checks++; }
    static NitraPreparedGrammar Prepare(string source)
    {
        var d=NitraSyntax.Read(source,"structure.nitra",true);
        Check(d.Success,d.ToJson());
        return NitraSyntax.Prepare(NitraSyntax.BaselineDefinitions(true).Append(d),new[]{"Test"},true);
    }
    const BindingFlags Fields=BindingFlags.Instance|BindingFlags.Public|BindingFlags.NonPublic;
    static void CheckRetention(NitraPreparedGrammar grammar,string rule,string text) {
        // Selection consumes retained evidence only: the recognition result carries evidence, and
        // construction succeeds, covers the whole input and does not need the diagnostic region export.
        var selected=NitraSyntax.Structure(grammar,rule,text,null,true);
        Check(selected.Success,"retained construction succeeds: "+rule+": "+string.Join(";",selected.Diagnostics));
        Check(selected.Root!=null && selected.Root.Start==0 && selected.Root.End==text.Length,"construction covers the whole input: "+rule);
        Check(selected.Recognition.Regions.Count==0,"compact selection avoids diagnostic region export: "+rule);
        var again=NitraSyntax.Structure(grammar,rule,text,null,true);
        Check(again.Nodes.Count==selected.Nodes.Count,"repeated construction is deterministic: "+rule);
    }
    public static void Main()
    {
        const string suspended = "namespace G { statement Envelope form { \"begin\" ...Operand... \"end\" } semantic kind Operand = \"inactive\"; grammar (Other) { deferred interaction; } syntax module Test { form Envelope; [StartRule] syntax Start = form; syntax form = \"native\"; } ast Data { form : string; } }";
        var filtered=NitraSyntax.ReadSourceGrammar(suspended,"suspended.n",true);
        Check(filtered.Success,filtered.ToJson());
        Check(filtered.InactiveConstructs.Count==4,"custom forms, kinds and interactions are retained as inactive");
        Check(filtered.InactiveConstructs.All(c=>suspended.Substring(c.Start,c.End-c.Start)==c.Text),"inactive source spans remain exact");
        Check(filtered.ToJson().Contains("\"active\":false"),"inspection explicitly reports inactivity");
        Check(filtered.Source==suspended,"original grammar source retained");
        var nativeOnly=NitraSyntax.Prepare(NitraSyntax.BaselineDefinitions(true).Append(filtered),new[]{"G.Test"},true);
        Check(nativeOnly.Recognize("G.Test.Start","native").Accepted,"native module and native rule named form remain active");
        Check(!nativeOnly.Recognize("G.Test.Start","inactive").Accepted,"inactive kind does not contribute alternatives");
        Check(!NitraSyntax.Read(suspended,"strict.nitra",true).Success,"strict native reader does not implicitly enable custom notation");
        var g=Prepare(@"syntax module Test {
          using Nitra.Core;
          [StartRule] syntax Start = Expr;
          syntax Expr {
            precedence Add:
            | Add = Left=Expr ""+"" Right=Expr;
            precedence Multiply:
            | Multiply = Left=Expr ""*"" Right=Expr;
            precedence 0:
            | Number = Value=Digits;
            | Group = ""("" Inner=Expr "")"";
          }
          regex Digits = ['0'..'9']+;
          [ExplicitSpaces] syntax Items = (Value=Digits; "","" )+;
          [ExplicitSpaces] syntax Tail = (""x""; "",""; ?)+;
          [ExplicitSpaces] syntax Ambiguous { | A=""x""; | B=""x""; }
          [ExplicitSpaces] syntax Ordered = Ambiguous Ambiguous;
          [ExplicitSpaces] syntax Cycle { | Loop=Cycle; | Empty=""""; }
          [ExplicitSpaces] syntax Prefix { | A=""a""; | Empty=""""; }
          [ExplicitSpaces] syntax Partition = Left=Prefix Right=Prefix;
          [ExplicitSpaces] syntax Empty = ""x""*;
          [ExplicitSpaces] syntax Bounded = (""x""; "",""; ?){1,3};
          [ExplicitSpaces] syntax Optional = ""x""? ""y"";

          syntax Family {
            | A = ""start"" Body "";"";
            | B = ""start"" Body ""end"";
            | C = ""start"" Body ""end"" ""start"";
          }
          [ExplicitSpaces] syntax Body = ""x"";
        }");
        var structure=NitraSyntax.Structure(g,"Test.Start","1 + 2 * (3 + 4)",null,true);
        Check(structure.Success,string.Join(";",structure.Diagnostics));
        Check(structure.Nodes.Select(n=>(n.Operation,n.Start,n.End)).Distinct().Count()==structure.Nodes.Count,"shared object identity");
        var add=structure.Nodes.Single(n=>n.Kind=="variant" && n.Label=="Test.Expr.Add" && n.Start==0);
        Check(add.Captures("Left").Count==1 && add.Captures("Right").Count==1,"captures belong to own production");
        Check(add.Captures("Left")[0].Text.Trim()=="1","left capture span");
        Check(add.Captures("Right")[0].Text.Trim()=="2 * (3 + 4)","right capture span");
        foreach(var (rule,text) in new[]{("Test.Items","1,22,333"),("Test.Tail","x,x,"),("Test.Empty",""),("Test.Empty","xxx")})
        {
            var s=NitraSyntax.Structure(g,rule,text,null,true);
            Check(s.Success,rule+": "+string.Join(";",s.Diagnostics));
        }
        // Deep arithmetic uses explicit construction frames, not a raised
        // recursion ceiling. Check exact leaves and source spans as well.
        foreach (var count in new[] {128, 512, 2048}) {
            var text=string.Join("+",Enumerable.Repeat("7",count));
            var deep=NitraSyntax.Structure(g,"Test.Start",text,null,true);
            Check(deep.Success,"deep arithmetic "+count+": "+string.Join(";",deep.Diagnostics));
            Check(deep.Root.Start==0 && deep.Root.End==text.Length,"deep arithmetic full span "+count);
            Check(deep.Nodes.Count(n=>n.Kind=="variant" && n.Label=="Test.Expr.Number" && n.Text=="7")==count,"deep arithmetic exact operands "+count);
        }
        var nestedText=new string('(',1024)+"7"+new string(')',1024);
        var nested=NitraSyntax.Structure(g,"Test.Start",nestedText,null,true);
        Check(nested.Success,"deep parenthesized structure: "+string.Join(";",nested.Diagnostics));
        Check(nested.Root.End==nestedText.Length,"deep parenthesized complete span");
        var captureRoot=new NitraStructure {Kind="seq"};var cursor=captureRoot;
        for(int i=0;i<8192;i++) {var next=new NitraStructure {Kind="seq"};cursor.Children.Add(next);cursor=next;}
        var deepCapture=new NitraStructure {Kind="capture",Label="value"};cursor.Children.Add(deepCapture);
        Check(captureRoot.Captures("value").Single()==deepCapture,"capture discovery handles deep structural wrappers");
        var hidden=new NitraStructure {Kind="call"};hidden.Children.Add(new NitraStructure {Kind="capture",Label="value"});captureRoot.Children.Add(hidden);
        Check(captureRoot.Captures("value").Single()==deepCapture,"capture discovery preserves call boundaries");
        int calls=0;
        var ambiguous=NitraSyntax.Structure(g,"Test.Ambiguous","x",null,true);
        Check(!ambiguous.Success && ambiguous.Diagnostics.Any(d=>d.Contains("ambiguity")),"ambiguity is not silently selected");
        var selected=NitraSyntax.Structure(g,"Test.Ambiguous","x",c=>{ calls++; return c.Options.FindIndex(o=>o.Label.EndsWith(".B")); },true);
        Check(selected.Success && calls==1,"explicit structural resolution");
        Check(selected.Nodes.Any(n=>n.Label=="Test.Ambiguous.B") && !selected.Nodes.Any(n=>n.Label=="Test.Ambiguous.A"),"only selected alternative materialized");
        var visitOrder=new System.Collections.Generic.List<int>();
        var ordered=NitraSyntax.Structure(g,"Test.Ordered","xx",c=>{visitOrder.Add(c.Start);return 0;},true);
        Check(ordered.Success && visitOrder.SequenceEqual(new[]{0,1}),"depth-first resolver order survives suspended construction");
        var cycle=NitraSyntax.Structure(g,"Test.Cycle","",c=>0,true);
        Check(!cycle.Success && cycle.Diagnostics.Any(d=>d.Contains("cyclic structural interpretation")),"cyclic interpretation diagnosed without a depth ceiling");
        Check(NitraSyntax.Structure(g,"Test.Start","7",null,true).Success,"recovery after cyclic interpretation");
        var finiteCycle=NitraSyntax.Structure(g,"Test.Cycle","",c=>c.Options.FindIndex(o=>o.Label.EndsWith(".Empty")),true);
        Check(finiteCycle.Success,"a terminating alternative remains selectable in a recursive grammar");
        Check(!NitraSyntax.Structure(g,"Test.Partition","a",null,true).Success,"partition ambiguity retained");
        Check(NitraSyntax.Structure(g,"Test.Partition","a",c=>0,true).Success,"partition selection uses endpoint evidence");
        Check(!NitraSyntax.Structure(g,"Test.Ambiguous","x",c=>99,true).Success,"invalid resolver index diagnosed");
        Check(!NitraSyntax.Structure(g,"Test.Start","1+",null,true).Success,"rejected input has no structural object");
        Check(NitraSyntax.Structure(g,"Test.Start","5",null,true).Success,"failure recovery");
        var family=NitraSyntax.Structure(g,"Test.Family","start x end start",null,true);
        Check(family.Success,string.Join(";",family.Diagnostics));
        Check(g.Recognize("Test.Family","start x end start").Regions.Count(n=>n.Kind=="call" && n.Label=="Test.Body")==1,"shared body call across competing endings");
        Check(family.Nodes.Count(n=>n.Kind=="variant" && n.Label.StartsWith("Test.Family."))==1,"only full selected family is materialized");
        var longList=NitraSyntax.Structure(g,"Test.Items",string.Join(",",Enumerable.Repeat("1",1500)),null,true);
        Check(longList.Success,"long structural lists do not recurse on the host stack: "+string.Join(";",longList.Diagnostics));
        CheckRetention(g,"Test.Start","7+7*7+7");
        CheckRetention(g,"Test.Items","1,22,333");
        CheckRetention(g,"Test.Tail","x,x,");
        var partitions=new System.Collections.Generic.List<int[]>();
        var partition=NitraSyntax.Structure(g,"Test.Partition","a",c=>{partitions.Add(c.Options.Select(o=>o.End).ToArray());return c.Options.Count-1;},true);
        Check(partition.Success && partitions.Any(options=>options.SequenceEqual(new[]{0,1})),"early feasibility preserves every partition option in endpoint order");
        foreach(var text in new[]{"7","7+7","(7+7)*7","7+"}) {
            var priorResult=NitraSyntax.Structure(g,"Test.Start",text,null,true);
            var second=NitraSyntax.Structure(g,"Test.Start",text,null,true);
            Check(priorResult.Success==second.Success && priorResult.Nodes.Count==second.Nodes.Count,"target spans and failed inputs do not leak between invocations");
        }
        foreach(var (rule,text,expected) in new[]{("Test.Bounded","x",true),("Test.Bounded","x,x,x,",true),("Test.Bounded","",false),("Test.Bounded","x,x,x,x",false),("Test.Optional","y",true),("Test.Optional","xy",true),("Test.Optional","xxy",false)}) {
            var bounded=NitraSyntax.Structure(g,rule,text,null,true);
            Check(bounded.Success==expected,"bounded/nullable retained transitions: "+rule+" "+text);
        }
        CheckRetention(g,"Test.Bounded","x,x,x,");
        var parent=new NitraTableScope(); var child=new NitraTableScope {Parent=parent};
        var outer=new NitraSemanticSymbol{Name="x",Kind="outer"}; var inner=new NitraSemanticSymbol{Name="x",Kind="inner"};
        parent.Define(outer); Check(child.Lookup("x").Single()==outer,"enclosing scope");
        child.Define(inner); Check(child.Lookup("x").Single()==inner,"shadowing");
        var list=child.Lookup("x"); list.Clear(); Check(child.Lookup("x").Count==1,"lookup cannot mutate table");
        child.Define(inner); Check(child.Lookup("x").Count==1,"stable symbol identity");
        child.Define(new NitraSemanticSymbol{Name="x"}); Check(child.Lookup("x").Count==2,"candidate set retained");
        Check(child.Lookup("missing").Count==0,"missing lookup");
        var any=new NitraSemanticType(new object(),null);
        var number=new NitraSemanticType(new object(),null);
        var other=new NitraSemanticType(new object(),null);
        var solver=new NitraTypeSolver((a,b)=>ReferenceEquals(a,b) || ReferenceEquals(a,number) && ReferenceEquals(b,any));
        var variable=new NitraTypeVariable(any,null);
        Check(solver.TryUnify(variable,number) && ReferenceEquals(solver.Resolve(variable),variable),"speculative unification rollback");
        Check(solver.Unify(variable,number) && ReferenceEquals(solver.Resolve(variable),number),"custom subtyping and committed binding");
        var incompatible=new NitraTypeVariable(number,null);
        Check(!solver.Unify(incompatible,other) && ReferenceEquals(solver.Resolve(incompatible),incompatible),"failed bound check rollback");
        var ctor=new object(); var first=new NitraTypeVariable(null,null);
        var left=new NitraSemanticType(ctor,new NitraSemanticType[]{first,number});
        var right=new NitraSemanticType(ctor,new[]{number,other});
        Check(!solver.Unify(left,right) && ReferenceEquals(solver.Resolve(first),first),"partial structural unification rollback");
        var recursive=new NitraSemanticType(ctor,new NitraSemanticType[]{first});
        Check(!solver.Unify(first,recursive),"occurs check");
        var lower=new NitraTypeVariable(null,number);var upper=new NitraTypeVariable(any,null);
        Check(solver.Unify(lower,upper) && solver.Unify(upper,number) && ReferenceEquals(solver.Resolve(lower),number),"merged variable bounds");
        Check(solver.Require(number,any) && !solver.Require(any,number),"required upper bound");
        Check(solver.Provide(any,number) && !solver.Provide(number,any),"provided lower bound");
        var speculative=new NitraTypeVariable(null,null);
        Check(solver.TryRequire(speculative,any) && ReferenceEquals(solver.Resolve(speculative),speculative),"speculative upper constraint rollback");
        Check(solver.TryProvide(speculative,number) && ReferenceEquals(solver.Resolve(speculative),speculative),"speculative lower constraint rollback");
        var shortcut = NitraSyntax.Read("namespace G { syntax module Look { [StartRule] syntax Start = \"a\" !Child \"b\"; syntax Child = \"c\"; } }", "shortcut.nitra", true);
        var shortcutGrammar = NitraSyntax.Prepare(NitraSyntax.BaselineDefinitions(true).Concat(new[]{shortcut}),new[]{"G.Look"},true);
        var shortcutTree = NitraSyntax.Structure(shortcutGrammar,"G.Look.Start","ab",null,true);
        Check(shortcutTree.Success,"zero-width lookahead shortcuts retain settled evidence: "+string.Join(";",shortcutTree.Diagnostics));
        Console.WriteLine($"PASS: {checks} settled structure, ambiguity, capture, scope and identity checks");
    }
}
