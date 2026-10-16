using System;
using System.IO;
using System.Linq;
using static Nemerle.Compiler.AST;
using static Nemerle.Compiler.compilation_options;
using static Nemerle.Compiler.manager_class;
using static Nemerle.Compiler.NitraSourceCompilation;
using static Nemerle.Compiler.Source;
using static Nemerle.Collections;

static class NitraAutomaticSourceChecks
{
    static int count;
    static void Check(bool ok, string message) { if (!ok) throw new Exception(message); count++; }
    static void Compile(string root, string references, string name, string grammar, string body, int? expected)
    {
        var previous = ManagerClass.Instance;
        try
        {
            var options = new CompilationOptions {
                CompileToMemory = true, TargetIsLibrary = true, TargetIsSet = true,
                ProgressBar = false, ColorMessages = false, IgnoreConfusion = true,
                OutputFileName = name + ".dll", TargetReferenceDirectory = references,
                NitraSources = new NitraSourceConfiguration(true) { SpaceValueTarget = TopLevelSpaces.Target }, DisableExternalParsers = true
            };
            var code = TopLevelSpaces.Lift(grammar + "\npublic class Example { public static Run() : int { " + body + " } }");
            options.Sources = NList.FromArray<ISource>(new ISource[] {
                new StringSource(Location.GetFileIndex(Path.Combine(root, name + ".n")), code)
            });
            var compiler = new ManagerClass(options);
            var messages = new StringWriter(); compiler.InitOutput(messages);
            int errors = 0; compiler.ErrorOccured += (_, _) => errors++;
            try { compiler.Run(); } catch { if (errors == 0) throw; }
            Check((errors == 0) == expected.HasValue, name + ": " + messages);
            if (expected.HasValue)
            {
                TopLevelSpaces.RunFile(compiler.GeneratedAssembly, name);
                var method = compiler.GeneratedAssembly.GetTypes().Single(t => t.Name == "Example").GetMethod("Run");
                Check((int)method.Invoke(null, null) == expected.Value, name + ": wrong result");
            }
            Console.WriteLine("PASS: " + name);
        }
        finally { ManagerClass.Instance = previous; }
        Check(ManagerClass.Instance == previous, "manager restoration");
    }
    static void Main(string[] args)
    {
        const string direct = """
        grammar G {
          using Nemerle.Compiler.Parsetree;
          syntax module Test {
            using Nitra.Core;
            [StartRule] syntax Start = Value { map PExpr { Value } }
            syntax Value = "42" { map PExpr = <[ 42 ]>; }
          }
        }
        """;
        Compile(args[0],args[1],"Automatic",direct,"space G { 42 }",42);
        Compile(args[0],args[1],"AutomaticPlain",direct,"space { 42 }",42);
        Compile(args[0],args[1],"RejectInput",direct,"space G { other }",null);
        Compile(args[0],args[1],"AfterFailure",direct,"space G { 42 }",42);
        Compile(args[0],args[1],"OrdinaryIsolation",direct,"Value",null);
        Compile(args[0],args[1],"MissingMap",direct.Replace("map PExpr { Value }", ""),"space G { 42 }",null);
        const string fields = """
        grammar G {
          using Nemerle.Compiler.Parsetree;
          syntax module Test {
            using Nitra.Core;
            [StartRule] syntax Start = Prefix="tag"? Values=(Value; ",")+ {
              map PExpr = {
                unless(this.Prefix.HasValue && this.Values.Item1.Count == 2 && this.Values.Item2.Count == 1)
                  throw System.Exception("native optional/separated fields were lost");
                unless(this.Values.Item1[0].Pair.HasValue && !this.Values.Item1[1].Pair.HasValue)
                  throw System.Exception("native recursive tuple fields were lost");
                <[ 42 ]>
              };
            }
            syntax Value = "x" Pair=("y" "z")?;
          }
        }
        """;
        Compile(args[0],args[1],"NativeFields",fields,"space G { tag x y z, x }",42);
        const string sql = """
        grammar Sql {
          using Nemerle.Compiler.Parsetree;
          syntax module Query {
            using Nitra.Core;
            [StartRule] syntax Select = "SELECT" "42" { map PExpr = <[ 42 ]>; }
          }
        }
        """;
        Compile(args[0],args[1],"Sql",sql,"space Sql { SELECT 42 }",42);
        const string arithmetic = """
        grammar G {
          using Nemerle.Compiler.Parsetree;
          syntax module Test {
            using Nitra.Core;
            [StartRule] syntax Start = Expr { map PExpr { Expr } }
            syntax Expr {
              map PExpr;
              precedence Sum:
              | Subtract = Left=Expr "-" Right=Expr { map PExpr = <[ $(this.Left.GetAst()) - $(this.Right.GetAst()) ]>; }
              precedence Product:
              | Multiply = Left=Expr "*" Right=Expr { map PExpr = <[ $(this.Left.GetAst()) * $(this.Right.GetAst()) ]>; }
              precedence 0:
              | Number = "7" { map PExpr = <[ 7 ]>; }
            }
          }
        }
        """;
        Compile(args[0],args[1],"NativeAssociativity",arithmetic,"space G { 7 - 7 - 7 }",-7);
        Compile(args[0],args[1],"NativePrecedence",arithmetic,"space G { 7 - 7 * 7 }",-42);
        Compile(args[0],args[1],"NativeRightAssociativity",arithmetic.Replace("Left=Expr \"-\" Right=Expr {", "Left=Expr \"-\" Right=Expr right-associative {"),"space G { 7 - 7 - 7 }",7);
        Compile(args[0],args[1],"TwoDefinitions",direct+sql,"space G { 42 } + space Sql { SELECT 42 }",84);
        // runtime/compile blocks are not part of the language
        Compile(args[0],args[1],"NoRuntimeBlock","runtime Draft { not executable; }"+direct,"space G { 42 }",null);
        // grammar (A, B) handles how A and B work together; space (A, B) uses it, whatever the order
        const string handler = """
        grammar (Sql, G) {
          using Nemerle.Compiler.Parsetree;
          syntax module Bridge {
            using Nitra.Core;
            using G.Test;
            using Sql.Query;
            [StartRule] syntax Both = Select "+" Value { map PExpr = <[ $(this.Select.GetAst()) + $(this.Value.GetAst()) ]>; }
          }
        }
        """;
        Compile(args[0],args[1],"GrammarHandler",direct+sql+handler,"space (G, Sql) { SELECT 42 + 42 }",84);
        // without a handler, a mixed space starts at the first grammar in sorted order that has a start rule
        Compile(args[0],args[1],"MixWithoutHandler",direct+sql,"space (Sql, G) { 42 }",42);
        // the joint set: a handler applies, as extensions of its grammars, in every space that has all of them
        const string layered = """
        grammar G {
          using Nemerle.Compiler.Parsetree;
          syntax module Test {
            using Nitra.Core;
            [StartRule] syntax Start = Item { map PExpr { Item } }
            syntax Item { map PExpr; | One = "1" { map PExpr = <[ 1 ]>; } }
          }
        }
        grammar S {
          using Nemerle.Compiler.Parsetree;
          syntax module Words { using Nitra.Core; syntax Two = "two" { map PExpr = <[ 2 ]>; } }
        }
        grammar X {
          using Nemerle.Compiler.Parsetree;
          syntax module Other { using Nitra.Core; syntax Unused = "x" { map PExpr = <[ 0 ]>; } }
        }
        grammar (S, G) {
          using Nemerle.Compiler.Parsetree;
          syntax module Bridge {
            using Nitra.Core;
            using G.Test;
            using S.Words;
            extend syntax Item { | FromS = Two { map PExpr { Two } } }
          }
        }
        """;
        Compile(args[0],args[1],"JointHandler",layered,"space (X, S, G) { two }",2);
        Compile(args[0],args[1],"ExclusiveHandler",layered,"space (G, S) { two }",2);
        Compile(args[0],args[1],"HandlerNeedsItsGrammars",layered,"space G { two }",null);
        Compile(args[0],args[1],"InactiveGrammar",direct.Replace("syntax module Test", "statement Envelope form { \"start\" ...Operand... \"end\" } semantic kind Operand = \"unused\"; syntax module Test"),"space G { 42 }",42);
        Console.WriteLine("PASS: " + count + " automatic native source checks");
    }
}
