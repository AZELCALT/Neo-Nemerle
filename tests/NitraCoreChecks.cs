using System;
using System.IO;
using System.Reflection;
using static Nitra.Declarations;
using System.Collections.Immutable;
public static class NitraCoreChecks
{
    static int checks;
    static void Check(bool ok,string message) { if(!ok) throw new Exception(message); checks++; }
    public static void Main(string[] args)
    {
        foreach(var name in new[]{"Integrated.Nitra.Runtime", "Integrated.DotNetLang", "Integrated.Nitra.Grammar", "Integrated.Nitra.Compiler", "Integrated.Nitra.Grammar.Support"}) {
            var assembly=Assembly.LoadFrom(Path.Combine(args[0],name+".dll"));
            Check(assembly.GetTypes().Length>0,"native source-built types must load: "+name);
            foreach(var dependency in assembly.GetReferencedAssemblies())
                Check(!dependency.Name.StartsWith("Boot."),"current native core must not depend on the legacy bootstrap runtime");
        }
        var table=new TableScope("native-test");
        Check(table.Bind<DeclarationSymbol>((Predicate<DeclarationSymbol>)(_=>true)).IsEmpty,"empty native table lookup");
        Check(EmptyScope.Instance.Bind<DeclarationSymbol>((Predicate<DeclarationSymbol>)(_=>true)).IsEmpty,"empty native scope lookup");
        Check(ReferenceEquals(EmptyScope.Instance.HideWith(table),table),"native scope hiding");
        Check(ReferenceEquals(EmptyScope.Instance.UnionWith(table),table),"native scope union");
        var reference=Ref<DeclarationSymbol>.CreateUnresolved("missing");
        Check(reference.IsUnresolved && reference.Name=="missing","native unresolved reference");
        var resolved=((IRef)reference).Resolve<DeclarationSymbol>((ResolutionAlgorithm<DeclarationSymbol,DeclarationSymbol>)null);
        Check(resolved.IsUnresolved && ReferenceEquals(reference.ResolvedTo,resolved),"native generic interface resolution must execute after persistence");
        var context=new DependentPropertyEvalContext();
        context.CalculatedCountInc();context.DeferredCountInc();context.NextPass();
        Check(context.CalculatedCount==1 && context.DeferredCount==1 && context.Pass==1,"native dependent-property evaluation context");
        var arguments=ImmutableArray.Create<IRef>(Ref<DeclarationSymbol>.CreateUnresolved("unresolved-type"));
        var allResolved=DotNet.AstUtils.ResolveAll<DeclarationSymbol,IRef>(arguments,out var typeArguments);
        Check(!allResolved && typeArguments.Count==1 && typeArguments[0]==null,"native generic type argument resolution preserves unresolved slots");
        int made=0;
        NitraSyntaxParseTree.Name nativeName=null;
        var file=new Nitra.Compiler.RecognizedNemerleFile(null,17,"original",provider=> {
            made++;
            nativeName=NitraSyntaxParseTree.Name.CreateRecognizedParseTree(provider,new Nitra.Runtime.NSpan(0,8),
                new Nitra.Runtime.OptionParseTree<Nitra.Runtime.NSpan>.None(Nitra.Runtime.Location.Default),new Nitra.Runtime.NSpan(0,8));
            return NitraSyntaxParseTree.Start.CreateRecognizedParseTree(provider,new Nitra.Runtime.NSpan(0,8),
                new Nitra.Runtime.ConcreteListParseTree<NitraSyntaxParseTree.NamespaceMember>(
                    Nitra.Runtime.Location.Default,Array.Empty<NitraSyntaxParseTree.NamespaceMember>()));
        },true);
        Check(made==1 && file.Length==8,"selected semantic input constructed once");
        Check(nativeName.Value()=="original" && ReferenceEquals(nativeName.File,file),"native token semantic methods read original source");
        var tree=file.GetParseTree();
        Check(ReferenceEquals(tree.File,file),"selected native tree retains semantic source identity");
        Check(ReferenceEquals(tree,file.GetParseTree()),"selected native tree is not replayed");
        file.UpdateParseTree();file.ResetCache();file.DeepResetProperties();
        Check(ReferenceEquals(tree,file.GetParseTree()) && made==1,"semantic reset cannot restart recognition");
        bool blocked=false;try {file.ReParse();} catch(InvalidOperationException) {blocked=true;}
        Check(blocked,"selected semantic input refuses upstream parsing");
        blocked=false;try {_=file.ParseResult;} catch(InvalidOperationException) {blocked=true;}
        Check(blocked,"selected semantic input does not fabricate a parser result");
        ((NitraSyntaxParseTree.Start)tree).CollectGlobalSymbols(null);
        Check(made==1,"native grammar semantic method executes on selected input");
        Console.WriteLine($"PASS: {checks} source-built native core loading, scopes, references and property-context checks (no upstream parser invoked)");
    }
}
