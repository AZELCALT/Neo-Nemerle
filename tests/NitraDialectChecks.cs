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
        public NitraDialectType ResolveType(string name, NitraDialectContext context) => name == "custom_int" ? new(name) : null;
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
        else if(configure) config.ConfigureDialects = registry => registry.RegisterResolver("G",name,new Resolver());
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
        Compile(root,refs,"Direct",Grammar,"space G {42}; G:.Direct::value(42)",42);
        Compile(root,refs,"Forward",Grammar,"def x=G:.Forward::value(); space G {42}; x",42);
        Compile(root,refs,"Callback",Grammar,"space G {42}; def f : int -> int = G:.Callback::abs; f(-42)",42);
        Compile(root,refs,"ClrCall",Grammar,"space G {42}; G:.ClrCall::abs(-42)",42);
        Compile(root,refs,"Alias",Grammar,"space G as Named {42}; G:.Alias.Named::value(42)",42);
        Compile(root,refs,"ScopeValue",Grammar,"scope.A.registery(\"name\",type(\"custom_int\")); scope.A.name=42; space G [A] {42}; G:.ScopeValue::shared()",42);
        Compile(root,refs,"ScopeUpdate",Grammar,"scope.A.registery(\"name\",type(\"custom_int\")); scope.A.name=7; scope.A.name=42; space G [A] {42}; scope.A.name + G:.ScopeUpdate::value(0)",42);
        Compile(root,refs,"Reference",Grammar,"space G {42}; scope.A.registery(\"f\",G:.Reference::value); scope.A.f(42)",42);
        Compile(root,refs,"FileOwned",Grammar,"space G {42}; G:.FileOwned::value(42)",42);
        Compile(root,refs,"MissingMember",Grammar,"space G {42}; G:.MissingMember::missing()",null,failure:"unreachable dialect member");
        Compile(root,refs,"MissingSpace",Grammar,"space G {42}; G:.OtherFile::value()",null,failure:"unknown dialect space");
        Compile(root,refs,"Overload",Grammar,"space G {42}; G:.Overload::value(1,2)",null,failure:"ambiguous value overload");
        Compile(root,refs,"DuplicateSpace",Grammar,"space G {42}; space G {42}",null,configure:false,failure:"duplicate dialect space");
        Compile(root,refs,"DuplicateBinding",Grammar,"scope.A.registery(\"x\",type(\"custom_int\")); scope.A.registery(\"x\",type(\"custom_int\")); space G {42}",null,failure:"duplicate scope binding");
        Compile(root,refs,"MissingBinding",Grammar,"scope.A.x=42; space G {42}",null,failure:"unknown shared scope");
        Compile(root,refs,"Unattached",Grammar,"scope.A.registery(\"name\",type(\"custom_int\")); scope.A.name=42; space G {42}; G:.Unattached::shared()",null,failure:"scope is not attached");
        Compile(root,refs,"Uninitialized",Grammar,"scope.A.registery(\"x\",type(\"custom_int\")); space G [A] {42}; scope.A.x",null,failure:"no expression value");
        Compile(root,refs,"NoResolver",Grammar,"space G {42}; G:.NoResolver::value()",null,configure:false,failure:"space has no dialect resolver");
        Compile(root,refs,"AfterFailure",Grammar,"space G {42}; G:.AfterFailure::value(42)",42);
        // A native parameterless mapping sees the same scoped services without changing Nitra notation.
        // The scope is the shared memory of the program and its spaces: the mapping reads `name` and writes `out` back.
        var contextual=Grammar.Replace("map PExpr = <[ 42 ]>;","map PExpr = { def c=NitraDialectContext.Current; def s=c.Scope(\"A\"); s.Set(\"out\",s.Get(\"name\").Value); <[ () ]> };");
        Compile(root,refs,"MappingScope",contextual,"scope.A.registery(\"name\",type(\"custom_int\")); scope.A.registery(\"out\",type(\"custom_int\")); scope.A.name=42; space G [A] {42}; scope.A.out",42,configure:false);
        var explicitContext=Grammar.Replace("map PExpr = <[ 42 ]>;","map (context : NitraDialectContext) PExpr = { def s=context.Scope(\"A\"); s.Set(\"out\",s.Get(\"name\").Value); <[ () ]> };");
        Compile(root,refs,"ExplicitContext",explicitContext,"scope.A.registery(\"name\",type(\"custom_int\")); scope.A.registery(\"out\",type(\"custom_int\")); scope.A.name=42; space G [A] {42}; scope.A.out",42,configure:false);
        var selfRegistering=Grammar.Replace("map PExpr = <[ 42 ]>;","map PExpr = { def c=NitraDialectContext.Current; when(c.Space.Resolver==null) c.RegisterResolver(NitraDialectChecks.CreateResolver()); <[ 42 ]> };");
        Compile(root,refs,"MappingResolver",selfRegistering,"def x=G:.MappingResolver::value(42); space G {42}; x",42,configure:false);
        Compile(root,refs,"TwoDialects",Grammar+Grammar.Replace("grammar G", "grammar H"),"scope.A.registery(\"name\",type(\"custom_int\")); scope.A.name=42; space G [A] {42}; space H [A] {42}; H:.TwoDialects::shared()",42,
            setup:r=>{r.RegisterResolver("G","TwoDialects",new Resolver()); r.RegisterResolver("H","TwoDialects",new Resolver());});
        Compile(root,refs,"CrossFile","scope A; "+Grammar,"scope.A.registery(\"name\",type(\"custom_int\")); scope.A.name=42; space G [A] {42}; G:.Other::shared()",42,
            setup:r=>{r.RegisterResolver("G","CrossFile",new Resolver()); r.RegisterResolver("G","Other",new Resolver());},
            extraSources:new[]{("Other","space G [A] {42}")});
        Compile(root,refs,"ScopeDeclaration","scope A; "+Grammar,"scope.A.registery(\"name\",type(\"custom_int\")); scope.A.name=42; space G [A] {42}; G:.ScopeDeclaration::shared()",42);
        Compile(root,refs,"ScopeBlock","scope A {} "+Grammar,"scope.A.registery(\"name\",type(\"custom_int\")); scope.A.name=42; space G [A] {42}; G:.ScopeBlock::shared()",42);
        Compile(root,refs,"NoScopeLeak",Grammar,"scope.A.registery(\"name\",type(\"custom_int\")); scope.A.name=42; space G [A] {42}; name",null,failure:"unbound");
        Compile(root,refs,"ClrMismatch",Grammar,"space G {42}; G:.ClrMismatch::abs(true)",null);
        Compile(root,refs,"QualifiedDialect",Grammar.Replace("grammar G", "grammar Q.G"),"space Q.G {42}; Q.G:.QualifiedDialect::value(42)",42,
            setup:r=>r.RegisterResolver("Q.G","QualifiedDialect",new Resolver()));
        Compile(root,refs,"NestedCalls",Grammar,"space G {42}; G:.NestedCalls::value(G:.NestedCalls::abs(-42))",42);
        Compile(root,refs,"ScopeExpression",Grammar,"scope.A.registery(\"name\",type(\"custom_int\")); scope.A.name=System.Math.Abs(-42); space G [A] {42}; G:.ScopeExpression::shared()",42);
        Compile(root,refs,"MissingAttachment",Grammar,"space G [Absent] {42}",null,failure:"unknown shared scope");
        Compile(root,refs,"AfterMismatch",Grammar,"space G {42}; G:.AfterMismatch::value(42)",42);
        Console.WriteLine("PASS: "+count+" dialect checks");
    }
}
