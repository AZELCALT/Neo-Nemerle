using System;
using System.IO;
using System.Linq;
using static Nemerle.Compiler.AST;
using static Nemerle.Compiler.compilation_options;
using static Nemerle.Compiler.main_parser;
using static Nemerle.Compiler.manager_class;
using static Nemerle.Compiler.NitraDialectServices;
using static Nemerle.Compiler.NitraSourceCompilation;
using static Nemerle.Compiler.Source;
using static Nemerle.Compiler.Parsetree;
using static Nemerle.Collections;

public static class NitraDialectChecks
{
    static int count;
    static void Check(bool ok, string message) { if (!ok) throw new Exception(message); count++; }
    public sealed class Resolver : INitraDialectResolver
    {
        public NitraDialectType ResolveType(string name, NitraDialectContext context) => name == "custom_int" ? new(name, "int") : null;
        public NitraDialectResolution Resolve(NitraDialectRequest request)
        {
            if (request.Name != "value" && request.Name != "abs" && request.Name != "shared") return null;
            if (request.Name == "value" && request.IsCall && request.Arguments.Length > 1)
                throw new ArgumentException("ambiguous value overload");
            var answer = new NitraDialectResolution();
            answer.Signatures.Add(new(request.Name,new("custom_int"),Array.Empty<NitraDialectType>()));
            if (request.Name == "value") answer.Signatures.Add(new(request.Name,new("custom_int"),new[]{new NitraDialectType("custom_int")}));
            answer.Lower = r => {
                Check(NitraDialectContext.Current == r.Context, "resolver context active during lowering");
                if (r.Name == "shared") {
                    var binding = r.Context.Scope("A").Get("name");
                    Check(r.Context.ResolveType(binding.Type.Name).Name == "custom_int", "custom type resolution");
                    return (PExpr)binding.Value;
                }
                if (r.Name == "abs") {
                    var fn = MainParser.ParseExpr(r.Context.Typer.Env,"System.Math.Abs",r.Context.Location,false);
                    return r.IsCall ? new PExpr.Call(fn,NList.FromArray(r.Arguments)) : fn;
                }
                return r.Arguments.Length == 1 ? r.Arguments[0] : MainParser.ParseExpr(r.Context.Typer.Env,"42",r.Context.Location,false);
            };
            return answer;
        }
    }
    public static INitraDialectResolver CreateResolver() => new Resolver();
    const string Grammar = """
    grammar G {
      using Nemerle.Compiler.NitraDialectServices;
      using Nemerle.Compiler.Parsetree;
      syntax module Test {
        using Nitra.Core;
        [StartRule] syntax Start = "42" { map PExpr = <[ 42 ]>; }
      }
    }
    """;
    static void Compile(string root, string references, string name, string grammar, string body, int? expected,
                        bool configure = true, string failure = null, Action<NitraDialectRegistry> setup = null, (string name,string code)[] extraSources = null)
    {
        var previous = ManagerClass.Instance;
        var config = new NitraSourceConfiguration(true);
        if(setup!=null) config.ConfigureDialects=setup;
        else if(configure) config.ConfigureDialects = registry => registry.RegisterResolver(name+".G",new Resolver());
        try {
            var options = new CompilationOptions {
                CompileToMemory=true,TargetIsLibrary=true,TargetIsSet=true,ProgressBar=false,ColorMessages=false,IgnoreConfusion=true,
                OutputFileName=name+".dll",TargetReferenceDirectory=references,NitraSources=config,DisableExternalParsers=true,
                SourceRoot=root,
                ReferencedLibraries=NList.FromArray(new[]{typeof(NitraDialectChecks).Assembly.Location})
            };
            // the body is the file's top-level code (a space is top level); a final expression is the result
            int last=body.LastIndexOf(';'); string tail=body.Substring(last+1).Trim();
            string top=tail.StartsWith("space") || tail.Length==0 ? body : body.Substring(0,last+1)+" Example.Result = "+tail+";";
            var code=grammar+"\npublic class Example { public static mutable Result : int; public static Run() : int { Result } }\n"+top;
            var sources=new System.Collections.Generic.List<ISource>{new StringSource(Location.GetFileIndex(Path.Combine(root,name+".n")),code)};
            if(extraSources!=null) foreach(var source in extraSources) sources.Add(new StringSource(Location.GetFileIndex(Path.Combine(root,source.name+".n")),source.code));
            options.Sources=NList.FromArray(sources.ToArray());
            var compiler=new ManagerClass(options); var messages=new StringWriter(); compiler.InitOutput(messages);
            int errors=0; compiler.ErrorOccured += (_,_)=>errors++;
            try { compiler.Run(); } catch(Exception e) { if(errors==0) { errors++; messages.WriteLine(e); } }
            Check((errors==0)==expected.HasValue,name+": "+messages);
            if(failure!=null) Check(messages.ToString().Contains(failure),name+": missing diagnostic "+failure+": "+messages);
            if(expected.HasValue) {
                TopLevelSpaces.RunFile(compiler.GeneratedAssembly,name);
                var method=compiler.GeneratedAssembly.GetTypes().Single(t=>t.Name=="Example").GetMethod("Run");
                Check((int)method.Invoke(null,null)==expected.Value,name+": wrong result");
            }
            if(name=="Reference" && expected.HasValue) Check(((NitraDialectResolution)config.Dialects.Scope("A").Get("f").Metadata).Signatures.Count==2,"reference signatures inferred");
            if(configure && expected.HasValue) Check(config.Dialects.Trace.Any(t=>t.StartsWith("resolve ")),"trace missing");
            Console.WriteLine("PASS: "+name);
        } finally { ManagerClass.Instance=previous; }
        Check(ManagerClass.Instance==previous,"manager restored");
        bool inactive=false; try { _=NitraDialectContext.Current; } catch(InvalidOperationException) { inactive=true; }
        Check(inactive,"mapping context restored");
    }
    static void Main(string[] args)
    {
        var root=args[0]; var refs=args[1];
        Compile(root,refs,"Direct",Grammar,"space G {42}; dial:.Direct.G::value(42)",42);
        Compile(root,refs,"Forward",Grammar,"def x=dial:.Forward.G::value(); space G {42}; x",42);
        Compile(root,refs,"Callback",Grammar,"space G {42}; def f : int -> int = dial:.Callback.G::abs; f(-42)",42);
        Compile(root,refs,"ClrCall",Grammar,"space G {42}; dial:.ClrCall.G::abs(-42)",42);
        Compile(root,refs,"Alias",Grammar,"space G as Named {42}; dial:.Alias.Named::value(42)",42);
        Compile(root,refs,"ScopeValue",Grammar,"scope.A.registery(\"name\",type(\"custom_int\")); scope.A.name=42; space G [A] {42}; dial:.ScopeValue.G::shared()",42);
        Compile(root,refs,"ScopeUpdate",Grammar,"scope.A.registery(\"name\",type(\"custom_int\")); scope.A.name=7; scope.A.name=42; space G [A] {42}; scope.A.name + dial:.ScopeUpdate.G::value(0)",42);
        Compile(root,refs,"Reference",Grammar,"space G {42}; scope.A.registery(\"f\",dial:.Reference.G::value); scope.A.f(42)",42);
        Compile(root,refs,"FileOwned",Grammar,"space G {42}; dial:.FileOwned.G::value(42)",42);
        Compile(root,refs,"MissingMember",Grammar,"space G {42}; dial:.MissingMember.G::missing()",null,failure:"unreachable dialect member");
        Compile(root,refs,"MissingSpace",Grammar,"space G {42}; dial:.OtherFile.G::value()",null,failure:"unknown space");
        Compile(root,refs,"Overload",Grammar,"space G {42}; dial:.Overload.G::value(1,2)",null,failure:"ambiguous value overload");
        Compile(root,refs,"DuplicateSpace",Grammar,"space G {42}; space G {42}",null,configure:false,failure:"duplicate space");
        Compile(root,refs,"DuplicateBinding",Grammar,"scope.A.registery(\"x\",type(\"custom_int\")); scope.A.registery(\"x\",type(\"custom_int\")); space G {42}",null,failure:"duplicate scope binding");
        Compile(root,refs,"MissingBinding",Grammar,"scope.A.x=42; space G {42}",null,failure:"unknown shared scope");
        Compile(root,refs,"Unattached",Grammar,"scope.A.registery(\"name\",type(\"custom_int\")); scope.A.name=42; space G {42}; dial:.Unattached.G::shared()",null,failure:"scope is not attached");
        // a slot starts with its type's default; its type comes from the grammar (the resolver maps custom_int to int)
        Compile(root,refs,"DefaultSlot",Grammar,"scope.A.registery(\"x\",type(\"custom_int\")); space G [A] {42}; scope.A.x",0,configure:false,
            setup:r=>r.RegisterResolver("DefaultSlot.G",new Resolver()));
        Compile(root,refs,"NoResolver",Grammar,"space G {42}; dial:.NoResolver.G::value()",null,configure:false,failure:"space has no dialect resolver");
        // a file has one space per grammar; a mixing space (A, B) is a space of its own whatever the order, reached
        // as dial:.file.(A, B)::member through any of its grammars
        const string Extra = "grammar H { using Nemerle.Compiler.Parsetree; syntax module Extra { using Nitra.Core; syntax Word = \"x\"; } }\n";
        Compile(root,refs,"MixSpace",Grammar+Extra,"space G {42}; space (H, G) {42}; dial:.MixSpace.G::value(40) + dial:.MixSpace.(G, H)::value(1) + dial:.MixSpace.(H,G)::value(1)",42,
            setup:r=>{r.RegisterResolver("MixSpace.G",new Resolver()); r.RegisterResolver("MixSpace.(H, G)",new Resolver());});
        Compile(root,refs,"DuplicateMix",Grammar+Extra,"space (G, H) {42}; space (H, G) {42}",null,configure:false,failure:"duplicate space");
        Compile(root,refs,"OneSpacePerGrammar",Grammar,"space G as S {42}; space G as T {42}",null,configure:false,failure:"duplicate space");
        Compile(root,refs,"PlainSpace",Grammar,"space {42}; space G {42}; dial:.PlainSpace::value(40) + dial:.PlainSpace.G::value(2)",42,
            setup:r=>{r.RegisterResolver("PlainSpace",new Resolver()); r.RegisterResolver("PlainSpace.G",new Resolver());});
        Compile(root,refs,"GrammarFirstForm",Grammar,"space G {42}; G:.GrammarFirstForm::value(42)",null);
        Compile(root,refs,"AfterFailure",Grammar,"space G {42}; dial:.AfterFailure.G::value(42)",42);
        // A native parameterless mapping sees the same scoped services without changing Nitra notation.
        // The scope is the storage the program and its spaces share: the space's code reads `name` and writes `out`.
        var contextual=Grammar.Replace("map PExpr = <[ 42 ]>;","map PExpr = { def c=NitraDialectContext.Current; def s=c.Scope(\"A\"); s.Write(\"out\",s.Read(\"name\")) };");
        Compile(root,refs,"MappingScope",contextual,"scope.A.registery(\"name\",type(\"int\")); scope.A.registery(\"out\",type(\"int\")); scope.A.name=42; space G [A] {42}; scope.A.out",42,configure:false);
        var explicitContext=Grammar.Replace("map PExpr = <[ 42 ]>;","map (context : NitraDialectContext) PExpr = { def s=context.Scope(\"A\"); s.Write(\"out\",s.Read(\"name\")) };");
        Compile(root,refs,"ExplicitContext",explicitContext,"scope.A.registery(\"name\",type(\"int\")); scope.A.registery(\"out\",type(\"int\")); scope.A.name=42; space G [A] {42}; scope.A.out",42,configure:false);
        // anything fits a slot; the code using it is type-checked: a slot of an unknown type reads as object
        Compile(root,refs,"AnySlot",Grammar,"scope.A.registery(\"thing\",type(\"whatever\")); scope.A.thing=\"text\"; space G [A] {42}; (scope.A.thing :> string).Length + 38",42,configure:false);
        Compile(root,refs,"ReadAnywhere",Grammar,"scope.A.registery(\"n\",type(\"int\")); scope.A.n=40; space G [A] {42}; Reader.Helper.Get()",42,configure:false,
            extraSources:new[]{("Reader","public static class Helper { public static Get() : int { scope.A.n + 2 } }")});
        var selfRegistering=Grammar.Replace("map PExpr = <[ 42 ]>;","map PExpr = { def c=NitraDialectContext.Current; when(c.Space.Resolver==null) c.RegisterResolver(NitraDialectChecks.CreateResolver()); <[ 42 ]> };");
        Compile(root,refs,"MappingResolver",selfRegistering,"def x=dial:.MappingResolver.G::value(42); space G {42}; x",42,configure:false);
        Compile(root,refs,"TwoDialects",Grammar+Grammar.Replace("grammar G", "grammar H"),"scope.A.registery(\"name\",type(\"custom_int\")); scope.A.name=42; space G [A] {42}; space H [A] {42}; dial:.TwoDialects.H::shared()",42,
            setup:r=>{r.RegisterResolver("TwoDialects.G",new Resolver()); r.RegisterResolver("TwoDialects.H",new Resolver());});
        Compile(root,refs,"CrossFile","scope A; "+Grammar,"scope.A.registery(\"name\",type(\"custom_int\")); scope.A.name=42; space G [A] {42}; dial:.Other.G::shared()",42,
            setup:r=>{r.RegisterResolver("CrossFile.G",new Resolver()); r.RegisterResolver("Other.G",new Resolver());},
            extraSources:new[]{("Other","space G [A] {42}")});
        Compile(root,refs,"ScopeDeclaration","scope A; "+Grammar,"scope.A.registery(\"name\",type(\"custom_int\")); scope.A.name=42; space G [A] {42}; dial:.ScopeDeclaration.G::shared()",42);
        Compile(root,refs,"ScopeBlock","scope A {} "+Grammar,"scope.A.registery(\"name\",type(\"custom_int\")); scope.A.name=42; space G [A] {42}; dial:.ScopeBlock.G::shared()",42);
        Compile(root,refs,"NoScopeLeak",Grammar,"scope.A.registery(\"name\",type(\"custom_int\")); scope.A.name=42; space G [A] {42}; name",null,failure:"unbound");
        Compile(root,refs,"ClrMismatch",Grammar,"space G {42}; dial:.ClrMismatch.G::abs(true)",null);
        Compile(root,refs,"QualifiedDialect",Grammar.Replace("grammar G", "grammar Q.G"),"space Q.G {42}; dial:.QualifiedDialect.Q.G::value(42)",42,
            setup:r=>r.RegisterResolver("QualifiedDialect.Q.G",new Resolver()));
        Compile(root,refs,"NestedCalls",Grammar,"space G {42}; dial:.NestedCalls.G::value(dial:.NestedCalls.G::abs(-42))",42);
        Compile(root,refs,"ScopeExpression",Grammar,"scope.A.registery(\"name\",type(\"custom_int\")); scope.A.name=System.Math.Abs(-42); space G [A] {42}; dial:.ScopeExpression.G::shared()",42);
        Compile(root,refs,"MissingAttachment",Grammar,"space G [Absent] {42}",null,failure:"unknown shared scope");
        Compile(root,refs,"AfterMismatch",Grammar,"space G {42}; dial:.AfterMismatch.G::value(42)",42);
        Console.WriteLine("PASS: "+count+" dialect checks");
    }
}
