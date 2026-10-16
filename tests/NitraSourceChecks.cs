using System;
using System.IO;
using System.Linq;
using static Nemerle.Compiler.AST;
using static Nemerle.Compiler.compilation_options;
using static Nemerle.Compiler.manager_class;
using static Nemerle.Compiler.nitra_compilation;
using static Nemerle.Compiler.NitraSourceCompilation;
using static Nemerle.Compiler.Parsetree;
using static Nemerle.Compiler.Source;
using static Nemerle.Collections;
using static NativeOutputChecks;
public static class NitraSourceChecks
{
    static int checks;
    static void Check(bool value,string message) { if(!value) throw new Exception(message); checks++; }
    const string Grammar=@"grammar G {
      syntax module Test {
        using Nitra.Core;
        [StartRule] syntax Start = Expr;
        syntax Expr {
          precedence Add: | Add = Left=Expr ""+"" Right=Expr;
          precedence Multiply: | Multiply = Left=Expr ""*"" Right=Expr;
          precedence 0: | Number = Value=Digits;
          | Group = ""("" Inner=Expr "")"";
        }
        regex Digits = ['0'..'9']+;
      }
    }
";
    const string Variables=@"grammar G { syntax module Test {
      using Nitra.Core;
      [StartRule] syntax Start = Declaration* Result=Expr;
      syntax Declaration = ""var"" Name=IdentifierBody ""="" Value=Expr "";"";
      syntax Expr {
        precedence Add: | Add = Left=Expr ""+"" Right=Expr;
        precedence 0: | Number = Value=Digits;
        | Variable = Name=IdentifierBody;
      }
      regex Digits = ['0'..'9']+;
    } }
";
    static void Compile(string root,string references,string name,string code,bool success,int expected=0,Action<NitraCompilationContext> setup=null,bool variables=false,bool inspect=false)
    {
        var previous=ManagerClass.Instance;
        code=TopLevelSpaces.Lift(code);
        try
        {
            var options=new CompilationOptions {
                CompileToMemory=true,TargetIsLibrary=true,TargetIsSet=true,ProgressBar=false,
                ColorMessages=false,IgnoreConfusion=true,OutputFileName=name+".dll",TargetReferenceDirectory=references,
                SourceRoot=root,InspectNitraSyntax=inspect
            };
            int calls=0;
            options.NitraSources=new NitraSourceConfiguration((typer,owner)=> {
                calls++;
                var ctx=variables ? VariableSupport.Context(typer,owner+".Test",Location.Default) : Support.Context(typer,owner+".Test",Location.Default);
                setup?.Invoke(ctx); return ctx;
            },true);
            options.NitraSources.SpaceValueTarget=TopLevelSpaces.Target;
            string path=Path.Combine(root,name+".n");
            options.Sources=NList.FromArray<ISource>(new ISource[]{new StringSource(Location.GetFileIndex(path),code)});
            var compiler=new ManagerClass(options); var messages=new StringWriter();compiler.InitOutput(messages);
            int errors=0; compiler.ErrorOccured+=(location,message)=> {
                errors++; Check(location.File==path || inspect,"source diagnostic identity");
                if(message.Contains("absent_name")) {
                    var offset=code.IndexOf("absent_name",StringComparison.Ordinal);var before=code.Substring(0,offset);
                    Check(location.Line==1+before.Count(c=>c=='\n') && location.Column==offset-before.LastIndexOf('\n'),"ordinary diagnostics retain exact offsets after source hooks");
                }
            };
            try {compiler.Run();} catch {if(errors==0) throw;}
            Check((errors==0)==success,messages.ToString());
            if(success) {
                Check(compiler.GeneratedAssembly!=null,"generated assembly");
                TopLevelSpaces.RunFile(compiler.GeneratedAssembly,name);
                var result=(int)compiler.GeneratedAssembly.GetTypes().Single(t=>t.Name=="Example").GetMethod("Run").Invoke(null,null);
                Check(result==expected,"execution result");Check(calls>0,"source mapping context invoked");
            } else {
                bool runnable=false;
                try { var method=compiler.GeneratedAssembly?.GetTypes().FirstOrDefault(t=>t.Name=="Example")?.GetMethod("Run"); if(method!=null) {method.Invoke(null,null);runnable=true;} } catch { }
                Check(!runnable,name+": invalid source must not produce runnable output");
            }
        }
        finally {ManagerClass.Instance=previous;}
        Check(ManagerClass.Instance==previous,"manager restored");
    }
    public static void Main(string[] args)
    {
        Compile(args[0],args[1],"Arithmetic",Grammar+"public class Example { public static Run() : int { space G { 1 + 2 * (3 + 4) } } }",true,15);
        Compile(args[0],args[1],"Plain",Grammar+"public class Example { public static Run() : int { space { (1 + 2) * 3 } } }",true,9);
        Compile(args[0],args[1],"Multiline",Grammar+"public class Example { public static Run() : int { space\n G\n {\n 4 + 5\n } } }",true,9);
        Compile(args[0],args[1],"BadInput",Grammar+"public class Example { public static Run() : int { space G { 1 + } } }",false);
        Compile(args[0],args[1],"Unknown",Grammar+"public class Example { public static Run() : int { space Missing { 1 } } }",false);
        Compile(args[0],args[1],"Cycle",Grammar+"public class Example { public static Run() : int { space G { 1 } } }",false,setup:ctx=> {
            var a=new NitraSemanticProperty{Name="a",Stage=0,Evaluate=_=>1};a.Dependencies.Add("b");
            var b=new NitraSemanticProperty{Name="b",Stage=0,Evaluate=_=>2};b.Dependencies.Add("a");ctx.Properties.Add(a);ctx.Properties.Add(b);
        });
        Compile(args[0],args[1],"MissingProperty",Grammar+"public class Example { public static Run() : int { space G { 1 } } }",false,setup:ctx=> {
            var a=new NitraSemanticProperty{Name="a",Stage=0,Evaluate=_=>1};a.Dependencies.Add("missing");ctx.Properties.Add(a);
        });
        Compile(args[0],args[1],"AfterFailure",Grammar+"public class Example { public static Run() : int { space G { 6 * 7 } } }",true,42);
        Compile(args[0],args[1],"Variables",Variables+"public class Example { public static Run() : int { space G { var x = 40; var y = x + 2; y } } }",true,42,variables:true);
        Compile(args[0],args[1],"UnknownVariable",Variables+"public class Example { public static Run() : int { space G { absent + 1 } } }",false,variables:true);
        Compile(args[0],args[1],"DuplicateVariable",Variables+"public class Example { public static Run() : int { space G { var x = 1; var x = 2; x } } }",false,variables:true);
        int emitted=0,evaluated=0;
        Compile(args[0],args[1],"Ambiguous","grammar G { syntax module Test { [StartRule] syntax Start { | A = \"x\"; | B = \"x\"; } } } public class Example { public static Run() : int { space G {x} } }",false,setup:ctx=> {
            ctx.Mappings["G.Test.Start.A"]=(c,n)=> {emitted++;return null;};
            ctx.Properties.Add(new NitraSemanticProperty{Name="side-effect",Evaluate=_=> {evaluated++;return null;}});
        });
        Check(emitted==0 && evaluated==0,"unresolved structures must not run semantic or output callbacks");
        Compile(args[0],args[1],"LaterStage",Grammar+"public class Example { public static Run() : int { space G { 1 } } }",false,setup:ctx=> {
            var a=new NitraSemanticProperty{Name="a",Stage=0,Evaluate=_=> {evaluated++;return 1;}};a.Dependencies.Add("b");
            var b=new NitraSemanticProperty{Name="b",Stage=1,Evaluate=_=>2};ctx.Properties.Add(a);ctx.Properties.Add(b);
        });
        Check(evaluated==0,"invalid semantic dependencies diagnosed before evaluation");
        Compile(args[0],args[1],"SourceOffsets",Grammar+"public class Example { public static Run() : int { def a=space G { 1 + 2 }; absent_name } }",false);
        Compile(args[0],args[1],"FileModules",Grammar+"public class Example { public static Run() : int { space G { 40 + 2 } } }",true,42);
        Compile(args[0],args[1],"ModeConflict",Grammar+"public class Example { public static Run() : int { space G { 1 } } }",false,inspect:true);
        Compile(args[0],args[1],"OrdinarySpaceName",Grammar+"public class Example { public static space() : int { 1 } public static Run() : int { Example.space() + space G { 41 } } }",true,42);
        Compile(args[0],args[1],"Overflow",Grammar+"public class Example { public static Run() : int { space G { 99999999999999999999 } } }",false);
        Compile(args[0],args[1],"NoRuntimeBlock", "runtime Draft { this is not Nemerle; }"+Grammar+"public class Example { public static Run() : int { space G { 40 + 2 } } }",false);
        Compile(args[0],args[1],"InactiveGrammar",Grammar.Replace("syntax module Test", "statement Envelope form { \"begin\" ...Operand... \"end\" } semantic kind Operand = \"unused\"; syntax module Test")+"public class Example { public static Run() : int { space G { 40 + 2 } } }",true,42);
        Compile(args[0],args[1],"NoActivationLeak",Grammar+"public class Example { public static Run() : int { var x = 1; x } }",false);
        Compile(args[0],args[1],"OrdinaryPlaceholderNames",Grammar+"public class Example { public static runtime() : int { 1 } public static compile() : int { 1 } public static Run() : int { runtime() + compile() + space G { 40 } } }",true,42);
        Console.WriteLine($"PASS: {checks} grammar/space execution, locations, semantic errors and recovery checks");
    }
}
