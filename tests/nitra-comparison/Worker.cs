using System;
using System.IO;
using System.Linq;
using System.Reflection;
using BindingFlags = System.Reflection.BindingFlags;
using SideSyntax = Nemerle.Compiler.nitra_syntax.NitraSyntax;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.Text.Json;
using System.Security.Cryptography;
using System.Text;
using Nitra;
using static Nitra.Runtime;
using static Nemerle.Compiler.compilation_options;
using static Nemerle.Compiler.manager_class;
using static Nemerle.Compiler.NitraRecognition;
using static Nemerle.Compiler.NitraStructures;
using static Nemerle.Compiler.NitraSyntaxModel;
using static Nemerle.Compiler.Source;
using static Nemerle.Compiler.type_info;
using static Nemerle.Compiler.Parsetree;

public static class ComparisonBridge
{
    public static Func<string,PExpr> Generate;
    public static PExpr Output(string engine) => Generate(engine);
}

sealed class Worker
{
    sealed class StrictRejection : OperationCanceledException {
        public readonly int Offset;
        public StrictRejection(int offset) { Offset=offset; }
    }
    sealed class Input {
        public string Module {get;set;}
        public string Rule {get;set;}
        public string Text {get;set;}
        public string References {get;set;}
        public int Warmups {get;set;} = 2;
        public int Samples {get;set;} = 5;
        public int Iterations {get;set;} = 3;
        public bool Benchmark {get;set;}
        public bool Backend {get;set;}
    }
    sealed class Outcome {
        public string Status {get;set;}
        public int End {get;set;}
        public string Tree {get;set;}
        public string Mapping {get;set;}
        [System.Text.Json.Serialization.JsonIgnore] public PExpr Output {get;set;}
        public string Error {get;set;}
        public double ParseMs {get;set;}
        public double MaterializeMs {get;set;}
        public double MappingMs {get;set;}
        public long AllocatedBytes {get;set;}
    }
    readonly Dictionary<string,Func<ISourceSnapshotProvider,NitraStructure,Func<string,ISourceSnapshotProvider,NitraStructure,object>,object>> factories = new();
    readonly Dictionary<Type,(string rule,PropertyInfo[] fields)> schemas = new();
    readonly List<NitraDocument> documents = new();
    readonly Assembly fixture;
    NitraPreparedGrammar side;
    ParseSession native;
    Input input;
    string engine;
    NitraRecognitionResult lastRecognition;
    static readonly JsonSerializerOptions JsonOptions=new(){MaxDepth=16384};
    static double Ms(long ticks) => ticks * 1000.0 / Stopwatch.Frequency;
    static string Hash(string s) => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(s)));
    Worker(string fixturePath) { fixture=Assembly.LoadFrom(fixturePath); }
    void Add(Assembly assembly) {
        foreach(var type in assembly.GetTypes()) {
            var graph=type.GetMethod("GetRecognitionGrammar",BindingFlags.Public|BindingFlags.Static|BindingFlags.DeclaredOnly);
            if(graph!=null && graph.ReturnType==typeof(NitraDocument)) documents.Add((NitraDocument)graph.Invoke(null,null));
            var identity=type.GetMethod("GetRecognitionRuleName",BindingFlags.Public|BindingFlags.Static|BindingFlags.DeclaredOnly);
            if(identity!=null) {
                var method=type.GetMethod("CreateSelected",BindingFlags.Public|BindingFlags.Static|BindingFlags.DeclaredOnly);
                factories.Add((string)identity.Invoke(null,null),(Func<ISourceSnapshotProvider,NitraStructure,Func<string,ISourceSnapshotProvider,NitraStructure,object>,object>)method.CreateDelegate(typeof(Func<ISourceSnapshotProvider,NitraStructure,Func<string,ISourceSnapshotProvider,NitraStructure,object>,object>)));
            }
        }
    }
    void Prepare() {
        if(engine=="side") {
            Add(typeof(ParseTree).Assembly); Add(typeof(NitraSyntaxParseTree.Start).Assembly);
            Add(Assembly.Load("Integrated.DotNetLang")); Add(fixture);
            side=SideSyntax.Prepare(documents,new[]{input.Module},true);
            foreach(var setting in new[]{("NITRA_FILTER_WORKERS","MaximumFilterWorkers"),("NITRA_FILTER_MINIMUM","MinimumFilterCandidates"),("NITRA_NODE_MINIMUM","MinimumNodeWork")}) {
                var value=Environment.GetEnvironmentVariable(setting.Item1);
                if(value!=null) typeof(NitraPreparedGrammar).GetField(setting.Item2,BindingFlags.Instance|BindingFlags.NonPublic)?.SetValue(side,int.Parse(value));
            }
            if(Environment.GetEnvironmentVariable("NITRA_FILTER_LEGACY")=="1") typeof(NitraPreparedGrammar).GetField("LegacyRecognition",BindingFlags.Instance|BindingFlags.NonPublic).SetValue(side,true);
        } else {
            var assemblies=new[]{typeof(ParseTree).Assembly,typeof(NitraSyntaxParseTree.Start).Assembly,Assembly.Load("Integrated.DotNetLang"),fixture};
            var descriptor=assemblies.SelectMany(GrammarDescriptor.GetDescriptors).Single(g=>g.FullName==input.Module);
            var start=(StartRuleDescriptor)descriptor.Rules.Single(r=>input.Module+"."+r.Name==input.Rule);
            native=new ParseSession(start,null,null,-1,default,true,default,r=>throw new StrictRejection(r.MaxFailPos),null,null,null);
            _=native.CompositeGrammar; // preparation, not hidden in warm parse timing
        }
    }
    object Create(string name,ISourceSnapshotProvider provider,NitraStructure selected,Dictionary<string,object> memo) {
        var node=selected; var key=name;
        if(!factories.ContainsKey(key)) {
            while(!(node.Kind=="variant" && factories.ContainsKey(node.Label))) {
                if(node.Children.Count!=1) throw new InvalidOperationException("missing factory for "+name);
                node=node.Children[0];
            }
            key=node.Label;
        }
        var sequence=Nitra.Runtime.SelectedFields.Unwrap(node,"seq"); var identity=key+":"+sequence.Id;
        if(memo.TryGetValue(identity,out var cached)) return cached;
        var tree=factories[key](provider,sequence,(n,p,s)=>Create(n,p,s,memo));memo.Add(identity,tree);return tree;
    }
    (string,PropertyInfo[]) Schema(Type type) {
        if(schemas.TryGetValue(type,out var result)) return result;
        for(var current=type;current!=null;current=current.BaseType) {
            var rule=current.GetMethod("GetRecognitionRuleName",BindingFlags.Public|BindingFlags.Static|BindingFlags.DeclaredOnly);
            if(rule!=null) {
                var props=current.GetProperties(BindingFlags.Public|BindingFlags.Instance|BindingFlags.DeclaredOnly)
                    .Where(p=>p.GetIndexParameters().Length==0 && p.Name!="Span" && typeof(IParseTree).IsAssignableFrom(p.PropertyType))
                    .OrderBy(p=>p.Name,StringComparer.Ordinal).ToArray();
                return schemas[type]=((string)rule.Invoke(null,null),props);
            }
        }
        return schemas[type]=(null,Array.Empty<PropertyInfo>());
    }
    // Force native typed fields with an explicit traversal stack. This verifier
    // must not reject valid deep inputs because of its own recursion ceiling.
    object Snapshot(object value,string text,ref bool ambiguous) {
        var pending=new Stack<Action>();
        var active=new HashSet<object>(System.Collections.Generic.ReferenceEqualityComparer.Instance);
        bool sawAmbiguous=false; object root=null;
        void Inspect(object current,Action<object> receive) {
            if(current is NSpan span) {receive(new object[]{"span",span.StartPos,span.EndPos,text.Substring(span.StartPos,span.Length)});return;}
            if(!active.Add(current)) throw new InvalidOperationException("cyclic parse-tree snapshot");
            pending.Push(()=>active.Remove(current));
            if(current is IAmbiguousParseTree many) {
                sawAmbiguous=true;
                var alternatives=many.Ambiguities.ToArray();var snapshots=new object[alternatives.Length];
                pending.Push(()=>receive(new object[]{"ambiguous",snapshots.Select(x=>JsonSerializer.Serialize(x,JsonOptions)).OrderBy(x=>x,StringComparer.Ordinal).ToArray()}));
                for(int i=alternatives.Length-1;i>=0;i--) {int index=i;pending.Push(()=>Inspect(alternatives[index],x=>snapshots[index]=x));}
                return;
            }
            if(current is not ParseTree tree) throw new InvalidOperationException("unexpected field "+current.GetType());
            var (rule,fields)=Schema(tree.GetType());var items=new List<object>();
            receive(new object[]{tree.Span.StartPos,tree.Span.EndPos,items});
            void Fields(PropertyInfo[] properties,bool named) {
                for(int i=0;i<properties.Length;i++) items.Add(null);
                int offset=items.Count-properties.Length;
                for(int i=properties.Length-1;i>=0;i--) {
                    int index=i;var field=properties[index];
                    pending.Push(()=>Inspect(field.GetValue(tree),x=>items[offset+index]=named?new object[]{field.Name,x}:x));
                }
            }
            if(rule!=null) {items.Add(rule);Fields(fields,true);}
            else if(tree is IEnumerable list) {
                items.Add("list");var values=list.Cast<object>().ToArray();
                for(int i=0;i<values.Length;i++) items.Add(null);
                for(int i=values.Length-1;i>=0;i--) {int index=i;pending.Push(()=>Inspect(values[index],x=>items[index+1]=x));}
            } else {
                var hasValue=tree.GetType().GetProperty("HasValue");
                if(hasValue!=null) {
                    bool has=(bool)hasValue.GetValue(tree);items.Add("option");items.Add(has);
                    if(has) {items.Add(null);pending.Push(()=>Inspect(tree.GetType().GetProperty("Value").GetValue(tree),x=>items[2]=x));}
                } else {
                    var tuple=tree.GetType().GetProperties().Where(p=>p.Name.StartsWith("Item",StringComparison.Ordinal)&&p.GetIndexParameters().Length==0&&typeof(IParseTree).IsAssignableFrom(p.PropertyType)).OrderBy(p=>p.Name,StringComparer.Ordinal).ToArray();
                    if(tuple.Length==0) throw new InvalidOperationException("unknown tree schema "+tree.GetType());
                    items.Add("tuple");Fields(tuple,false);
                }
            }
        }
        pending.Push(()=>Inspect(value,x=>root=x));
        while(pending.Count>0) pending.Pop()();
        ambiguous=sawAmbiguous;return root;
    }
    Outcome Run() {
        long allocated=GC.GetAllocatedBytesForCurrentThread();long begin=Stopwatch.GetTimestamp();
        var result=new Outcome();object tree=null;NitraStructureResult structure=null;
        try {
            var source=new SourceSnapshot(input.Text);
            if(engine=="side") {
                structure=SideSyntax.Structure(side,input.Rule,input.Text,null,true);
                lastRecognition=structure.Recognition;
                result.End=structure.Recognition.Furthest;
                if(!structure.Success) {
                    result.Status=structure.Recognition.Accepted && structure.Recognition.Complete && structure.Diagnostics.Any(s=>s.Contains("ambiguity")) ? "ambiguous" : "rejected";
                    result.Error=string.Join("; ",structure.Diagnostics);return result;
                }
                tree=Create(input.Rule,source.File,structure.Root,new Dictionary<string,object>());
                result.End=structure.Root.End;
            } else {
                var parsed=native.Parse(source);
                result.End=parsed.ParseEnd;
                if(parsed.MainParserFail || !parsed.IsSuccess || parsed.ParseEnd!=input.Text.Length) {result.Status="rejected";return result;}
                tree=parsed.CreateParseTree();
            }
            long afterParse=Stopwatch.GetTimestamp();result.ParseMs=Ms(afterParse-begin);
            bool ambiguous=false;var snapshot=Snapshot(tree,input.Text,ref ambiguous);
            result.Tree=JsonSerializer.Serialize(snapshot,JsonOptions);
            long afterTree=Stopwatch.GetTimestamp();result.MaterializeMs=Ms(afterTree-afterParse);
            result.Status=ambiguous ? "ambiguous" : "accepted";
            var map=tree.GetType().GetMethod("GetAst",BindingFlags.Public|BindingFlags.Instance,null,Type.EmptyTypes,null);
            if(map!=null && map.ReturnType==typeof(PExpr) && !ambiguous) {result.Output=(PExpr)map.Invoke(tree,null);result.Mapping=result.Output.ToString();}
            result.MappingMs=Ms(Stopwatch.GetTimestamp()-afterTree);
        } catch(StrictRejection rejected) { result.Status="rejected";result.End=rejected.Offset; }
          catch(Exception error) {while(error is TargetInvocationException && error.InnerException!=null) error=error.InnerException;result.Status="error";result.Error=error.ToString();}
        finally {result.AllocatedBytes=GC.GetAllocatedBytesForCurrentThread()-allocated;if(result.ParseMs==0) result.ParseMs=Ms(Stopwatch.GetTimestamp()-begin);}
        return result;
    }
    int ExecuteOutput() {
        var previous=ManagerClass.Instance;
        try {
            ComparisonBridge.Generate=engineName=>{
                if(engineName!=engine) throw new InvalidOperationException("backend engine mismatch");
                var result=Run();if(result.Status!="accepted" || result.Output==null) throw new InvalidOperationException("backend mapping failed: "+result.Error);
                return result.Output;
            };
            var options=new CompilationOptions {CompileToMemory=true,TargetIsLibrary=true,TargetIsSet=true,ProgressBar=false,ColorMessages=false,IgnoreConfusion=true,DisableExternalParsers=true,TargetReferenceDirectory=input.References,OutputFileName="Backend_"+Guid.NewGuid().ToString("N")+".dll"};
            options.SharedAssemblies=AppDomain.CurrentDomain.GetAssemblies();
            options.MacrosToLoad=Nemerle.Collections.NList.FromArray(new[]{fixture.Location});
            options.ReferencedLibraries=Nemerle.Collections.NList.FromArray(new[]{fixture.Location,typeof(ComparisonBridge).Assembly.Location,typeof(PExpr).Assembly.Location,typeof(ParseTree).Assembly.Location});
            var code="using Comparison; public Run() : int { Replay(\""+engine+"\") }"; // the file module Backend
            options.Sources=Nemerle.Collections.NList.FromArray<ISource>(new ISource[]{new StringSource(Nemerle.Compiler.AST.Location.GetFileIndex("Backend.n"),code)});
            var compiler=new ManagerClass(options);var messages=new StringWriter();compiler.InitOutput(messages);int errors=0;compiler.ErrorOccured+=(_,_)=>errors++;
            try {compiler.Run();} catch(Exception error) {throw new Exception("direct AST backend failed: "+messages,error);}
            if(errors!=0 || compiler.GeneratedAssembly==null) throw new Exception("direct AST backend failed: "+messages);
            return (int)compiler.GeneratedAssembly.GetType("Backend").GetMethod("Run").Invoke(null,null);
        } finally {ComparisonBridge.Generate=null;ManagerClass.Instance=previous;}
    }
    static void InitializeCompiler(string references) {
        var options=new CompilationOptions {CompileToMemory=true,TargetIsLibrary=true,TargetIsSet=true,ProgressBar=false,ColorMessages=false,IgnoreConfusion=true,DisableExternalParsers=true,TargetReferenceDirectory=references,OutputFileName="ComparisonContext.dll"};
        options.Sources=Nemerle.Collections.NList.FromArray<ISource>(Array.Empty<ISource>());
        var manager=new ManagerClass(options);var messages=new StringWriter();manager.InitOutput(messages);int errors=0;manager.ErrorOccured+=(_,_)=>errors++;manager.ParseGrammarSources();
        if(errors!=0) throw new Exception(messages.ToString());ManagerClass.Instance=manager;
    }
    static int Main(string[] args) {
        try {
            var worker=new Worker(args[0]){engine=args[1],input=JsonSerializer.Deserialize<Input>(File.ReadAllText(args[2]))};
            var contextClock=Stopwatch.StartNew();InitializeCompiler(worker.input.References);contextClock.Stop();
            var before=GC.GetAllocatedBytesForCurrentThread();var clock=Stopwatch.StartNew();worker.Prepare();clock.Stop();
            var setupMs=clock.Elapsed.TotalMilliseconds;var setupBytes=GC.GetAllocatedBytesForCurrentThread()-before;
            var cold=worker.Run();
            var counters=new Dictionary<string,long>();
            if(worker.lastRecognition!=null) foreach(var name in typeof(NitraRecognitionResult).GetFields(BindingFlags.Instance|BindingFlags.Public|BindingFlags.NonPublic).Where(f=>f.FieldType==typeof(int)).Select(f=>f.Name)) {
                var field=typeof(NitraRecognitionResult).GetField(name,BindingFlags.Instance|BindingFlags.Public|BindingFlags.NonPublic);if(field!=null)counters[name]=Convert.ToInt64(field.GetValue(worker.lastRecognition));
            }
            var samples=new List<object>();object recovery=null;bool recoveryPassed=true;
            if(cold.Status=="accepted") {
                var original=worker.input.Text;Outcome invalid;
                try {worker.input.Text=original+"\0";invalid=worker.Run();} finally {worker.input.Text=original;}
                var again=worker.Run();recoveryPassed=invalid.Status=="rejected" && again.Status==cold.Status && again.Tree==cold.Tree && again.Mapping==cold.Mapping;
                recovery=new{passed=recoveryPassed,rejected_status=invalid.Status,after_status=again.Status};
            }
            if(worker.input.Benchmark && cold.Status!="error") {
                for(int i=0;i<worker.input.Warmups;i++) worker.Run();
                for(int sample=0;sample<worker.input.Samples;sample++) {
                    double parse=0,materialize=0,mapping=0;long bytes=0;
                    for(int i=0;i<worker.input.Iterations;i++) {
                        var r=worker.Run();
                        if(r.Status!=cold.Status || r.Tree!=cold.Tree || r.Mapping!=cold.Mapping) throw new Exception("nondeterministic result between repetitions");
                        parse+=r.ParseMs;materialize+=r.MaterializeMs;mapping+=r.MappingMs;bytes+=r.AllocatedBytes;
                    }
                    double n=worker.input.Iterations;samples.Add(new{parse_ms=parse/n,materialize_snapshot_ms=materialize/n,mapping_ms=mapping/n,total_ms=(parse+materialize+mapping)/n,allocated_bytes=bytes/n});
                }
            }
            int? backendValue=null;string backendError=null;double backendMs=0;
            if(worker.input.Backend && cold.Output!=null && cold.Status=="accepted") {
                // Keep parse/map evidence if an uncatchable backend stack
                // overflow terminates this process. The final result supersedes
                // this checkpoint when execution completes normally.
                Console.WriteLine(JsonSerializer.Serialize(new{worker_phase="before_backend",engine=worker.engine,status=cold.Status,end=cold.End,tree=cold.Tree,tree_sha256=Hash(cold.Tree),mapping=cold.Mapping,error=cold.Error,recognition_counters=counters,cold,samples,backend_value=(int?)null,backend_error="backend execution did not finish",recovery_control=recovery,recovery_passed=recoveryPassed}));
                Console.Out.Flush();
                var backendClock=Stopwatch.StartNew();
                try {backendValue=worker.ExecuteOutput();} catch(Exception error) {backendError=error.ToString();}
                backendMs=backendClock.Elapsed.TotalMilliseconds;
            }
            var process=Process.GetCurrentProcess();process.Refresh();
            Console.WriteLine(JsonSerializer.Serialize(new{engine=worker.engine,status=cold.Status,end=cold.End,tree=cold.Tree,tree_sha256=cold.Tree==null?null:Hash(cold.Tree),mapping=cold.Mapping,error=cold.Error,recognition_counters=counters,compiler_context_ms=contextClock.Elapsed.TotalMilliseconds,setup_ms=setupMs,setup_allocated_bytes=setupBytes,cold,samples,backend_value=backendValue,backend_error=backendError,backend_ms=backendMs,recovery_control=recovery,recovery_passed=recoveryPassed,peak_working_set_bytes=process.PeakWorkingSet64,gc_heap_bytes=GC.GetTotalMemory(false),runtime=System.Runtime.InteropServices.RuntimeInformation.FrameworkDescription,architecture=System.Runtime.InteropServices.RuntimeInformation.ProcessArchitecture.ToString()}));
            return cold.Status=="error" || !recoveryPassed || backendError!=null?2:0;
        } catch(Exception error) {Console.WriteLine(JsonSerializer.Serialize(new{status="worker_error",error=error.ToString()}));return 2;}
    }
}
