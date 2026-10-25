using System;
using System.IO;
using System.Linq;
using static Nemerle.Compiler.manager_class;
using static Nemerle.Scripting.contracts;
using static Nemerle.Scripting.host;
using static Nemerle.Scripting.session;
using static Nemerle.Scripting.cache;
using static Nemerle.Scripting.dependencies;
using static Nemerle.Scripting.definitions;
using static Nemerle.Scripting.facilities;
public sealed class Counter { public int Value; public int Add(int n) { return Value+=n; } }
public class ScriptBase { public int Seed; public ScriptBase(int seed) {Seed=seed;} public int BaseValue() {return Seed;} }
public sealed class Outer { public int Number=10; public int Choose(string x) {return 10;} public int Same(int x) {return 10+x;} }
public sealed class Inner { public int Number=20; public int Choose(int x) {return 20+x;} public int Same(int x) {return 20+x;} }
public sealed class ImportRefiner : IScriptConfigurationRefiner {
 public int Calls; public string Version => "1";
 public ScriptDefinition BeforeParsing(ScriptSource source, ScriptDefinition definition) { Calls++; return definition; }
 public ScriptDefinition OnDependencies(ScriptCollectedData data, ScriptDefinition definition) { Calls++;definition.Imports.Add("System");return definition; }
}
public interface IScriptAnswer { int Answer(); }
public class GenericOuter<T> { public class Nested<U> { public T First; public U Second; } }
public sealed class StageRefiner : IScriptCompilationRefiner {
 public int Annotations, Compiling; public string Version=>"1"; public string[] AnnotationNames=>new[]{"HostFlag"};
 public ScriptDefinition OnAnnotations(ScriptCollectedData data,ScriptDefinition d) {Annotations++;d.Properties.Add("number",typeof(int));return d;}
 public ScriptDefinition BeforeCompiling(ScriptCollectedData data,ScriptDefinition d) {Compiling++;return d;}
}
public sealed class EvaluationRefiner : IScriptEvaluationRefiner {
 public int Calls; public string Version=>"1";
 public ScriptInputs BeforeEvaluate(ScriptEvaluationContext context) {Calls++;context.Inputs.Properties["number"]=42;return context.Inputs;}
}
public sealed class ExecutionWrapper : IScriptExecutionWrapper {
 public int Calls; public bool Repeat; public string Version=>"1";
 public EvaluationResult Execute(ScriptEvaluationContext context,Func<EvaluationResult> run) {Calls++;var result=run();if(Repeat)run();return result;}
}
public sealed class ChildInputs : IScriptImportedInputProvider {
 public bool Invalid; public ScriptInputs GetInputs(CompiledScript child,ScriptEvaluationContext parent,ScriptInputs inherited) {if(Invalid)inherited.Properties["counter"]="wrong";return inherited;}
}
public static class ScriptingChecks {
 static ScriptHost host=new ScriptHost(); static string root;
 static void Check(bool condition,string message) {if(!condition) throw new Exception(message);}
 static CompiledScript Compile(string code, ScriptDefinition d=null) {
  var r=host.Compile(new ScriptSource(code,Path.Combine(root,"x.n")), d??new ScriptDefinition());
  foreach(var diagnostic in r.Diagnostics) Console.WriteLine(diagnostic.File+":"+diagnostic.Line+": "+diagnostic.Message);
  Check(r.Success,"compile failed: "+code); return r.Script;
 }
 static EvaluationResult Eval(string code) {
  var r=host.Evaluate(Compile(code),new ScriptInputs()); if(r.Error!=null)throw r.Error; return r;
 }
 public static void Main(string[] args) {
  root=args[0]; var previous=ManagerClass.Instance;
  var d=new ScriptDefinition(); d.Properties.Add("counter",typeof(Counter));
  var script=Compile("mask math { Double(n : int) : int { counter.Add(n * 2) } }\nx.math.Double(21)\n",d);
  var inputs=new ScriptInputs();var counter=new Counter();inputs.Properties.Add("counter",counter);
  var r=host.Evaluate(script,inputs); if(r.Error!=null) throw r.Error;
  Check((int)r.Value==42 && counter.Value==42,"input identity");
  var twice=(Func<int,int>)r.GetFunction("x.math.Double",typeof(Func<int,int>));
  Check(twice(2)==46,"bound masked function");
  var artifact=Path.Combine(root,"saved.dll");host.Save(script,artifact);
  var loaded=host.Load(artifact,d); Check((int)host.Evaluate(loaded,inputs).Value==88,"saved artifact context");
  Check(twice(1)==90,"old delegate coexists");
  var legacy=Compile("42 : int\n");var legacyPath=Path.Combine(root,"legacy.dll");File.WriteAllBytes(legacyPath,legacy.Image);
  using(var writer=new BinaryWriter(File.Create(legacyPath+".script"))) {
    writer.Write("Nemerle.Script");writer.Write(1);
    writer.Write(Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(legacy.Image)));
    writer.Write(legacy.ScriptType.FullName);writer.Write(legacy.EvaluationMethod);
    writer.Write(0);writer.Write(0);writer.Write(typeof(object).AssemblyQualifiedName);writer.Write(0);writer.Write(0);
  }
  Check((int)host.Evaluate(host.Load(legacyPath,new ScriptDefinition()),new ScriptInputs()).Value==42,"version-one descriptor compatibility");
  var legacyTwo=Path.Combine(root,"legacytwo.dll");File.WriteAllBytes(legacyTwo,legacy.Image);
  using(var writer=new BinaryWriter(File.Create(legacyTwo+".script"))) {
    writer.Write("Nemerle.Script");writer.Write(2);
    writer.Write(Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(legacy.Image)));writer.Write("");
    writer.Write(legacy.ScriptType.FullName);writer.Write(legacy.EvaluationMethod);
    writer.Write(0);writer.Write(0);writer.Write(typeof(object).AssemblyQualifiedName);writer.Write(0);writer.Write(0);
    for(int i=0;i<7;i++)writer.Write(0);
  }
  Check((int)host.Evaluate(host.Load(legacyTwo,new ScriptDefinition()),new ScriptInputs()).Value==42,"version-two descriptor compatibility");
  var state=Compile("mutable value : int = 0;\nInc() : int { value = value + 1; value }\nmask math { Double() : int { value = value * 2; value } }\nvalue = 3; value\n");
  var a=host.Evaluate(state,new ScriptInputs());var b=host.Evaluate(state,new ScriptInputs());
  if(a.Error!=null) throw a.Error;
  Check((int)a.Value==3 && (int)b.Value==3,"fresh state");
  var inc=(Func<int>)a.GetFunction("x.Inc",typeof(Func<int>));
  var dbl=(Func<int>)a.GetFunction("x.math.Double",typeof(Func<int>));
  Check(inc()==4 && dbl()==8 && ((Func<int>)b.GetFunction("x.Inc",typeof(Func<int>)))()==4,"one context per evaluation, shared by masks");
  Check((int)Eval("mask math { Double(n : int) : int { n * 2 } F(Double : int) : int { Double + 1 } }\nx.math.F(4)\n").Value==5,"local shadowing");
  Check((int)Eval("A() : int { 7 }\nx.A()\n").Value==7,"file-qualified root function");
  Check(Eval("null : string\n").Kind==ScriptResultKind.Value && Eval("null : string\n").Value==null,"null value");
  Check(Eval("null\n").Kind==ScriptResultKind.Value && Eval("null\n").Value==null,"bare null value");
  Check(Eval("()\n").Kind==ScriptResultKind.Void,"void result");
  var error=host.Evaluate(Compile("throw System.InvalidOperationException(\"user failure\")\n"),new ScriptInputs());
  Check(error.Kind==ScriptResultKind.Error && error.Error is InvalidOperationException,"user exception");
  var bad=host.Compile(new ScriptSource("mask hidden { private F() : int { 1 } }\nx.hidden.F()\n",Path.Combine(root,"x.n")),new ScriptDefinition());
  Check(!bad.Success && bad.Diagnostics.Length>0 && bad.Diagnostics[0].Line>0,"mask privacy diagnostics");
  Check((int)Eval("42 : int\n").Value==42,"recovery after failure");
  var bd=new ScriptDefinition();bd.BaseType=typeof(ScriptBase);bd.BaseArgumentTypes.Add(typeof(int));
  var bs=Compile("BaseValue() + 2\n",bd);var bi=new ScriptInputs();bi.BaseArguments.Add(40);
  Check((int)host.Evaluate(bs,bi).Value==42,"base constructor and inherited member");
  var rd=new ScriptDefinition();rd.ReceiverTypes.Add(typeof(Outer));rd.ReceiverTypes.Add(typeof(Inner));
  var rs=Compile("Choose(2) + Choose(\"outer\") + Same(1)\n",rd);
  var ri=new ScriptInputs();ri.Receivers.Add(new Outer());ri.Receivers.Add(new Inner());
  var re=host.Evaluate(rs,ri);if(re.Error!=null)throw re.Error;
  Check((int)re.Value==53,"receiver scope order and applicability");
  var imports=new ScriptDefinition();imports.Imports.Add("System");
  Check((int)host.Evaluate(Compile("Math.Abs(-42 : int)\n",imports),new ScriptInputs()).Value==42,"default imports");
  Check((int)Eval("class Box { public Value : int; public this(n : int) { Value = n; } }\ndef b = Box(7); b.Value\n").Value==7,"nested types");
  Check((int)Eval("mask math { class Box { public Value : int; public this(n : int) { Value = n; } } }\ndef b = x.math.Box(7); b.Value\n").Value==7,"masked types");
  var closure=Eval("mutable value : int = 3;\n(n : int) => { value = value + n; value }\n");
  Check((int)closure.Value.GetType().GetMethod("apply",new[]{typeof(int)}).Invoke(closure.Value,new object[]{4})==7,"closure retains state");
  var debug=new ScriptDefinition();debug.Debug=true;
  var debugScript=Compile("Fail() : int { throw System.InvalidOperationException(\"debug failure\") }\nFail()\n",debug);
  var debugResult=host.Evaluate(debugScript,new ScriptInputs());
  Check(debugScript.Symbols!=null && debugResult.Error.StackTrace.Contains("x.n:line 1"),"portable PDB original source location");
  host.Save(debugScript,Path.Combine(root,"debug.dll"));
  var loadedDebug=host.Evaluate(host.Load(Path.Combine(root,"debug.dll"),debug),new ScriptInputs());
  Check(loadedDebug.Error.StackTrace.Contains("x.n:line 1"),"loaded PDB source location");
  var order=Compile("counter.Add(1);\nvalue : int = counter.Value;\ncounter.Add(1);\nvalue + counter.Value\n",d);
  host.Save(order,Path.Combine(root,"order.dll"));
  var oi=new ScriptInputs();oi.Properties.Add("counter",new Counter());
  var orderResult=host.Evaluate(order,oi);if(orderResult.Error!=null){Console.WriteLine(orderResult.Error);throw orderResult.Error;}
  Check((int)orderResult.Value==3,"initializer/statement source order after input binding");
  Check((int)Eval("mask math { Helper() : int { 3 } mutable value : int = Helper(); Read() : int { value } }\nx.math.Read()\n").Value==3,"masked initializer scope");
  Check((int)Eval("mask math { mutable value : int = 3; Value : int { get { value } set { this.value = value; } } }\nx.math.Value = 7; x.math.Value\n").Value==7,"masked property accessors");
  var auto=Compile("Value : int { get; set; default counter.Add(1); }\ncounter.Add(1); Value + counter.Value\n",d);
  var ai=new ScriptInputs();ai.Properties.Add("counter",new Counter());
  var ar=host.Evaluate(auto,ai);if(ar.Error!=null)throw ar.Error;
  Check((int)ar.Value==3,"automatic property initializer order");
  Check((int)Eval("[Record] class Box { public value : int; }\ndef b = Box(7); b.value\n").Value==7,"existing declaration macro");
  var rp=host.Evaluate(Compile("(Number : int)\n",rd),ri);if(rp.Error!=null)throw rp.Error;
  Check((int)rp.Value==20,"implicit receiver property precedence");
  Check((int)Eval("mask math { class Box { public Value : int; public this(n : int) { Value = n; } } Make() : Box { Box(7) } }\nx.math.Make().Value\n").Value==7,"masked type in function signature");
  Check((int)Eval("def n = 41 : int; Read() : int { n + 1 } Read()\n").Value==42,"top-level def belongs to script instance");
  using (var session = new ScriptSession(host,new ScriptDefinition(),new ScriptInputs())) {
    SubmissionResult Submit(string code) {
      var result=session.Submit(new ScriptSource(code,Path.Combine(root,"repl.n")));
      foreach(var diagnostic in result.Compilation.Diagnostics) Console.WriteLine(diagnostic.Message);
      Check(result.Success,"submission failed: "+code);
      if(result.Evaluation.Error!=null)throw result.Evaluation.Error;
      return result;
    }
    var first=Submit("mutable count : int = 1; Inc() : int { count = count + 1; count } (count : int)\n");
    var earlier=(Func<int>)first.Evaluation.GetFunction("repl.Inc",typeof(Func<int>));
    Check((int)Submit("(Inc() : int)\n").Evaluation.Value==2,"previous instance invocation");
    Check((int)Submit("count = count + 10; (repl.Inc() : int)\n").Evaluation.Value==13,"previous state mutation");
    Submit("def count = 100 : int; count\n");
    Check((int)Submit("(count : int)\n").Evaluation.Value==100 && earlier()==14,"shadowing keeps earlier bindings");
    Submit("using System; class Box { public Value : int; public this(n : int) { Value=n; } } ()\n");
    Check((int)Submit("def b = Box(Math.Abs(-7 : int)); b.Value\n").Evaluation.Value==7,"previous types and imports");
    var historyPath=Path.Combine(root,"repl.history"); session.SaveHistory(historyPath);
    var restored=session.ReadHistory(historyPath);
    Check(restored.Length==session.History.Length,"stored source history");
    var incompatibleDefinition=new ScriptDefinition();incompatibleDefinition.Version="changed";
    using(var incompatible=new ScriptSession(host,incompatibleDefinition,new ScriptInputs())) {
      Check(incompatible.ReadHistory(historyPath).Length==restored.Length,"history source remains readable after configuration change");
      try { incompatible.ReplayHistory(historyPath);throw new Exception("incompatible replay accepted"); }
      catch(InvalidDataException) { }
    }
    var replayed=session.Replay(restored);
    Check(replayed.Length==restored.Length && Array.TrueForAll(replayed,x=>x.Success),"explicit history replay");
    var rejected=session.Submit(new ScriptSource("not_defined\n",Path.Combine(root,"repl.n")));
    Check(!rejected.Compilation.Success && session.History.Length==7,"failed compilation is uncommitted");
    Check((int)Submit("(count : int)\n").Evaluation.Value==100,"session recovery");
    session.Reset();
    Check(session.History.Length==0,"reset history");
    Submit("mutable state : int = 0; ()\n");
    var failed=session.Submit(new ScriptSource("state = 7; throw System.InvalidOperationException(\"failure\")\n",Path.Combine(root,"repl.n")));
    Check(failed.Compilation.Success && !failed.Success && failed.Evaluation.Error is InvalidOperationException && session.History.Length==1,"failed evaluation is uncommitted");
    Check((int)Submit("(state : int)\n").Evaluation.Value==7,"failed evaluation retains prior side effects");
    Submit("using M = System.Math; class Box { public Value : int; public this(n : int) { Value=n; } } null : string\n");
    Check((int)Submit("def box = repl.Box(M.Abs(-42 : int)); box.Value\n").Evaluation.Value==42,"qualified earlier types and aliases");
    Check((bool)Submit("res2 == null\n").Evaluation.Value,"typed null result retained");
    var asynchronous=session.SubmitAsync(new ScriptSource("42 : int\n",Path.Combine(root,"repl.n")),System.Threading.CancellationToken.None).GetAwaiter().GetResult();
    Check(asynchronous.Success && (int)asynchronous.Evaluation.Value==42,"asynchronous submission");
  }
  Check((int)Eval("def (a,b) = (20 : int,22 : int); Sum() : int { a+b } Sum()\n").Value==42,"tuple bindings belong to instance");
  Check((int)Eval("def n = 40 : int; def add = (x : int) => n + x; add(2)\n").Value==42,"inferred closure binding and capture");
  Check((int)Eval("def (Some(n)) = Some(42 : int); Read() : int { n } Read()\n").Value==42,"variant pattern binding belongs to instance");
  Check((int)Eval("def add = { def n = 40 : int; (x : int) => n + x }; add(2)\n").Value==42,"nested lexical capture in inferred binding");
  var registry=new ScriptDefinitionRegistry(new ScriptDefinition());registry.Register(".script.n",new ScriptDefinition());
  var selectedOptions=new ScriptHostOptions();selectedOptions.DefinitionSelector=registry;
  Check(new ScriptHost(selectedOptions).Compile(new ScriptSource("41 + 1 : int\n",Path.Combine(root,"selected.script.n"))).Success,"custom definition extension");
  var refiner=new ImportRefiner();var refiningOptions=new ScriptHostOptions();refiningOptions.Refiners.Add(refiner);
  var unmodified=new ScriptDefinition();var refined=new ScriptHost(refiningOptions).Compile(new ScriptSource("Math.Abs(-42 : int)\n",Path.Combine(root,"refined.n")),unmodified);
  Check(refined.Success && refiner.Calls==2 && unmodified.Imports.Count==0,"refinement stages and definition snapshots");
  var cacheDirectory=Path.Combine(root,"code-cache");
  var options=new ScriptHostOptions(); options.Cache=new FileScriptArtifactCache(cacheDirectory,16*1024*1024);
  var cachedHost=new ScriptHost(options);
  var cacheSource=new ScriptSource("def n = 40 : int; n + 2\n",Path.Combine(root,"cached.n"));
  var ca=cachedHost.Compile(cacheSource,new ScriptDefinition()); var cb=cachedHost.Compile(cacheSource,new ScriptDefinition());
  Check(ca.Success && cb.Success && ca.Script.Assembly.FullName==cb.Script.Assembly.FullName,"compiled artifact cache hit");
  Check((int)cachedHost.Evaluate(cb.Script,new ScriptInputs()).Value==42,"cached execution");
  var fingerprintFile=Path.Combine(root,"fingerprint-reference.bin");
  File.WriteAllText(fingerprintFile,"AAAA");
  var fingerprintTime=File.GetLastWriteTimeUtc(fingerprintFile);
  var fingerprintDefinition=new ScriptDefinition();
  fingerprintDefinition.References.Add(fingerprintFile);
  fingerprintDefinition.RuntimeReferences.Add(fingerprintFile);
  var originalFingerprint=ScriptFingerprint.Create(cacheSource,fingerprintDefinition,"1");
  Check(originalFingerprint==ScriptFingerprint.Create(cacheSource,fingerprintDefinition,"1"),"unchanged repeated references retain fingerprint");
  File.WriteAllText(fingerprintFile,"BBBB");File.SetLastWriteTimeUtc(fingerprintFile,fingerprintTime);
  Check(originalFingerprint!=ScriptFingerprint.Create(cacheSource,fingerprintDefinition,"1"),"fingerprints recheck contents despite unchanged size and timestamp");
  var missingReference=new ScriptDefinition();missingReference.References.Add(Path.Combine(root,"missing-reference.dll"));
  var missingResult=cachedHost.Compile(cacheSource,missingReference);
  Check(!missingResult.Success && missingResult.Diagnostics.Any(x=>x.IsError),"missing cache inputs produce compilation diagnostics");
  var cachePath=Path.Combine(cacheDirectory,ScriptFingerprint.Create(cacheSource,new ScriptDefinition(),"1"),"script.dll");
  File.WriteAllText(cachePath,"corrupt");
  Check(cachedHost.Compile(cacheSource,new ScriptDefinition()).Success,"corrupt cache recovery");
  var changed=cachedHost.Compile(new ScriptSource("43 : int\n",cacheSource.Path),new ScriptDefinition());
  Check(changed.Success && changed.Script.Assembly.FullName!=cb.Script.Assembly.FullName && (int)cachedHost.Evaluate(changed.Script,new ScriptInputs()).Value==43,"changed source invalidates cache");
  var inputSource=new ScriptSource("counter.Add(2)\n",Path.Combine(root,"cachedinput.n"));
  var inputFirst=cachedHost.Compile(inputSource,d);var inputSecond=cachedHost.Compile(inputSource,d);
  var inputValues=new ScriptInputs();var supplied=new Counter{Value=40};inputValues.Properties.Add("counter",supplied);
  Check(inputFirst.Success && inputSecond.Success && inputFirst.Script.Assembly.FullName==inputSecond.Script.Assembly.FullName,"typed input compilation cached");
  Check((int)cachedHost.Evaluate(inputSecond.Script,inputValues).Value==42 && supplied.Value==42,"cached artifact retains host identity");
  supplied.Value=50;
  Check((int)cachedHost.Evaluate(inputSecond.Script,inputValues).Value==52,"cache excludes live input values");
  var dependencyFailure=host.Compile(new ScriptSource("[assembly: DependsOn(\"Example\", \"1.0.0\")]\n42 : int\n",Path.Combine(root,"dep.n")),new ScriptDefinition());
  Check(!dependencyFailure.Success && dependencyFailure.Diagnostics[0].Message.Contains("resolver"),"dependency attribute collected before compiler");
  var cancelled=new System.Threading.CancellationToken(true);
  try { host.CompileAsync(cacheSource,new ScriptDefinition(),cancelled).GetAwaiter().GetResult(); throw new Exception("cancellation ignored"); }
  catch(OperationCanceledException) { }
  Facilities();
  Check(ManagerClass.Instance==previous,"compiler context restoration");
  var asyncBinding=Eval("using System.Threading.Tasks;\n"
    + "async def Value() : Task[int] { await Task.Yield(); 5 }\n"
    + "def answer = Value().Result;\nawait Task.Yield();\nanswer\n");
  Check(asyncBinding.Kind==ScriptResultKind.Value && (int)asyncBinding.Value==5,
    "an inferred binding may call a local async function in a waiting script");
  var localStreams=Eval("using System;\nusing System.Collections.Generic;\nusing System.Threading.Tasks;\n"
    + "async def S(k : int) : IAsyncEnumerable[int] { yield k; await Task.Yield(); yield k * 2 }\n"
    + "async def T() : Task[int] { await Task.Yield(); 5 }\n"
    + "def start = T().Result;\nmutable total = start;\nawait foreach (item in S(10)) total += item;\ntotal\n");
  Check(localStreams.Kind==ScriptResultKind.Value && (int)localStreams.Value==35,
    "async initializer inference with a local async stream uses the root solver");
  var badWaitingInitializer=host.Compile(new ScriptSource("using System.Threading.Tasks;\n"
    + "await Task.Yield();\ndef bad = \"text\" * 2;\nbad\n",Path.Combine(root,"bad_waiting.n")));
  var initializerErrors=badWaitingInitializer.Diagnostics.Where(x=>x.IsError).ToArray();
  Check(!badWaitingInitializer.Success && initializerErrors.Length==2
    && initializerErrors.All(x=>x.Line==3)
    && initializerErrors.Select(x=>x.Message).Distinct().Count()==2,
    "waiting initializer inference reports operator diagnostics once at the original source line");
  Console.WriteLine("PASS: scripting inputs, identity, exports, masks, inferred bindings/closures, session chaining/shadowing/failures, typed results, source history/replay, refiners, async cancellation, cache integrity and saved artifacts");
 }
 static void Facilities() {
  File.WriteAllText(Path.Combine(root,"math.n"), "mutable count : int = 0; count = count + 1; mask nested { public class Pair { public N : int; public this(n : int) { N = n; } } Double(n : int) : int { n * 2 } } mask functions { Answer() : int { 42 } } Read() : int { count }\n");
  var imported=Compile("[assembly: Import(\"math.n\")]\nmath.nested.Double(21)\n");
  var result=host.Evaluate(imported,new ScriptInputs()); if(result.Error!=null)throw result.Error;
  Check((int)result.Value==42,"qualified imported mask");
  Check((int)host.Evaluate(Compile("[assembly: Import(\"math.n\")]\nusing math.nested; Double(21)\n"),new ScriptInputs()).Value==42,"explicit imported mask opening");
  Check((int)host.Evaluate(Compile("[assembly: Import(\"math.n\")]\nusing M = math.nested; M.Double(21)\n"),new ScriptInputs()).Value==42,"imported mask alias");
  Check((int)host.Evaluate(Compile("[assembly: Import(\"math.n\")]\nusing M = math.nested; def p : M.Pair = M.Pair(42); p.N\n"),new ScriptInputs()).Value==42,"imported masked type alias");
  Check(!host.Compile(new ScriptSource("[assembly: Import(\"math.n\")]\nDouble(21)\n",Path.Combine(root,"x.n"))).Success,"source imports do not implicitly open masks");
  File.WriteAllText(Path.Combine(root,"other.n"),"Read() : int { 42 }\n");
  Check(!host.Compile(new ScriptSource("[assembly: Import(\"math.n\",\"other.n\")]\nusing math; using other; Read()\n",Path.Combine(root,"ambiguous.n"))).Success,"ambiguous opened script members rejected");
  Check((int)host.Evaluate(Compile("[assembly: Import(\"math.n\",\"other.n\")]\nusing math; using other; Read() : int { 42 }\nRead()\n"),new ScriptInputs()).Value==42,"local declaration wins over opened imports");
  File.WriteAllText(Path.Combine(root,"left.n"),"[assembly: Import(\"math.n\")]\nRead() : int { math.Read() }\n");
  File.WriteAllText(Path.Combine(root,"right.n"),"[assembly: Import(\"math.n\")]\nRead() : int { math.Read() }\n");
  var diamond=Compile("[assembly: Import(\"left.n\", \"right.n\")]\nleft.Read() + right.Read()\n");
  Check(Object.ReferenceEquals(diamond.ImportedScripts[0].Script.ImportedScripts[0].Script,diamond.ImportedScripts[1].Script.ImportedScripts[0].Script),"diamond compilation deduplicated");
  Check((int)host.Evaluate(diamond,new ScriptInputs()).Value==2,"diamond evaluation");
  var bundle=Path.Combine(root,"graph.dll");host.Save(diamond,bundle);
  var relocated=Path.Combine(root,"relocated");Directory.CreateDirectory(relocated);
  File.Copy(bundle,Path.Combine(relocated,"graph.dll"));File.Copy(bundle+".script",Path.Combine(relocated,"graph.dll.script"));
  CopyTree(bundle+".dependencies",Path.Combine(relocated,"graph.dll.dependencies"));
  var loaded=host.Load(Path.Combine(relocated,"graph.dll"),new ScriptDefinition());
  var evaluated=host.Evaluate(loaded,new ScriptInputs());if(evaluated.Error!=null)throw evaluated.Error;
  Check((int)evaluated.Value==2,"relocated graph artifact");
  var childDescriptor=Directory.GetFiles(Path.Combine(relocated,"graph.dll.dependencies"),"*.script",SearchOption.AllDirectories)[0];
  var descriptorBytes=File.ReadAllBytes(childDescriptor);File.AppendAllText(childDescriptor,"tampered");
  try{host.Load(Path.Combine(relocated,"graph.dll"),new ScriptDefinition());throw new Exception("changed child descriptor accepted");}catch(InvalidDataException){}
  File.WriteAllBytes(childDescriptor,descriptorBytes);
  Check(!host.Compile(new ScriptSource("[assembly: Import(\"math.n\", \"math.n\")]\n42\n",Path.Combine(root,"duplicate.n"))).Success,"duplicate imports rejected");
  File.WriteAllText(Path.Combine(root,"cycle.n"),"[assembly: Import(\"cycle.n\")]\n42\n");
  Check(!host.Compile(new ScriptSource(File.ReadAllText(Path.Combine(root,"cycle.n")),Path.Combine(root,"cycle.n"))).Success,"cycle rejected");
  var patternRegistry=new ScriptDefinitionRegistry(new ScriptDefinition());
  patternRegistry.Register(".n",new ScriptDefinition{Id="general",DisplayName="General"});
  patternRegistry.Register(".n",new ScriptDefinition{Id="special",FilePathPattern="special[.]n$",DisplayName="Special"});
  Check(patternRegistry.Select(new ScriptSource("",Path.Combine(root,"special.n"))).Id=="special" && patternRegistry.Select(new ScriptSource("",Path.Combine(root,"normal.n"))).Id=="general","path-pattern selection with compatible extensions");
  File.WriteAllText(Path.Combine(root,"System.n"),"Double(n : int) : int { n * 2 }\n");
  Check((int)host.Evaluate(Compile("[assembly: Import(\"System.n\")]\nSystem.Double(21) + System.Math.Abs(0 : int)\n"),new ScriptInputs()).Value==42,"qualified CLR fallback beside source owner");
  File.WriteAllText(Path.Combine(root,"System.n"),"Double(n : int) : int { n * 2 } public class Math { public static Abs(n : int) : int { n + 1 } }\n");
  Check((int)host.Evaluate(Compile("[assembly: Import(\"System.n\")]\nSystem.Double(21) + System.Math.Abs(0 : int)\n"),new ScriptInputs()).Value==43,"source nested type overloads precede colliding CLR type");
  var selected=new ScriptDefinition();selected.Properties.Add("seed",typeof(int));
  var registry=new ScriptDefinitionRegistry(new ScriptDefinition());registry.Register(".special.n",selected);
  var selecting=new ScriptHost(new ScriptHostOptions{DefinitionSelector=registry});
  File.WriteAllText(Path.Combine(root,"child.special.n"),"Answer() : int { seed + 2 }\n");
  var selectedParent=selecting.Compile(new ScriptSource("[assembly: Import(\"child.special.n\")]\nchild.Answer()\n",Path.Combine(root,"parent.n")),selected);
  var selectedInputs=new ScriptInputs();selectedInputs.Properties.Add("seed",40);
  Check(selectedParent.Success && (int)selecting.Evaluate(selectedParent.Script,selectedInputs).Value==42,"selected child definition and matching inherited input");
  File.WriteAllText(Path.Combine(root,"privatechild.n"),"mask hidden { private Secret() : int { 42 } }\n");
  Check(!host.Compile(new ScriptSource("[assembly: Import(\"privatechild.n\")]\nprivatechild.hidden.Secret()\n",Path.Combine(root,"privateparent.n"))).Success,"imported private member inaccessible");
  var named=new ScriptDefinition{ResultField="answer",ResultType=typeof(int)};
  var namedResult=host.Evaluate(Compile("42 : int\n",named),new ScriptInputs());
  Check((int)namedResult.Instance.GetType().GetField("answer").GetValue(namedResult.Instance)==42,"named typed result field");
  var disabled=new ScriptDefinition{CaptureResult=false};
  Check(host.Evaluate(Compile("42 : int\n",disabled),new ScriptInputs()).Kind==ScriptResultKind.Void,"disabled result capture");
  var location=new ScriptDefinition{FileLocationProperty="file"};
  Check((string)host.Evaluate(Compile("file\n",location),new ScriptInputs()).Value==Path.Combine(root,"x.n"),"source file binding");
  var fragment=new ScriptDefinition();fragment.SourceFragments.Add(new ScriptSourceFragment(12,9));
  Check((int)host.Evaluate(Compile("not valid !\n42 : int\n",fragment),new ScriptInputs()).Value==42,"source fragments");
  Check((int)Eval("def functions = array[(n : int) => n + 2]; functions[0](40)\n").Value==42,"indexed function call remains an expression");
  var generic=host.Evaluate(Compile("Identity[T](value : T) : T { value }\n()\n"),new ScriptInputs());
  Check(((Func<int,int>)generic.GetFunction("x.Identity",typeof(Func<int,int>),new[]{typeof(int)}))(42)==42,"explicit generic function binding");
  Check((int)host.Evaluate(Compile("[assembly: CompilerOptions(\"-define:SELECTED\")]\n#if SELECTED\n42 : int\n#else\n1 : int\n#endif\n"),new ScriptInputs()).Value==42,"literal semantic compiler option");
  var options=host.Compile(new ScriptSource("[assembly: CompilerOptions(\"-out:bad.dll\")]\n42\n",Path.Combine(root,"options.n")));
  Check(!options.Success && options.Diagnostics[0].Message.Contains("controlled"),"host controlled options rejected");
  DeepFacilities();
  Console.WriteLine("PASS: source imports, explicit using/aliases, graph composition/relocation, result contracts, fragments and generic function binding");
 }

 static void DeepFacilities() {
  var source=new ScriptSource("F() : int {\n",Path.Combine(root,"syntax.n"));
  Check(host.ClassifyInput(source,new ScriptDefinition())==ScriptInputCompleteness.Incomplete,"unfinished brace classification");
  Check(host.ClassifyInput(new ScriptSource("40 +\n",source.Path),new ScriptDefinition())==ScriptInputCompleteness.Incomplete,"unfinished expression classification");
  Check(host.ClassifyInput(new ScriptSource("40 + 2\n",source.Path),new ScriptDefinition())==ScriptInputCompleteness.Complete,"complete classification");
  Check(host.ClassifyInput(new ScriptSource("}\n",source.Path),new ScriptDefinition())==ScriptInputCompleteness.Invalid,"invalid bracket classification");
  Check(host.ClassifyInput(new ScriptSource("F(1 +)\n",source.Path),new ScriptDefinition())==ScriptInputCompleteness.Invalid,"closed malformed expression classification");
  Check(host.ClassifyInput(new ScriptSource("/* unfinished\n",source.Path),new ScriptDefinition())==ScriptInputCompleteness.Incomplete,"unfinished comment classification");
  Check(host.ClassifyInput(new ScriptSource("@\"unfinished\n",source.Path),new ScriptDefinition())==ScriptInputCompleteness.Incomplete,"unfinished multiline string classification");
  var stages=new StageRefiner();var evaluation=new EvaluationRefiner();var wrapper=new ExecutionWrapper();
  var options=new ScriptHostOptions{ExecutionWrapper=wrapper};options.CompilationRefiners.Add(stages);options.EvaluationRefiners.Add(evaluation);
  var stagedHost=new ScriptHost(options);
  var staged=stagedHost.Compile(new ScriptSource("[assembly: HostFlag(\"test\")]\nnumber\n",Path.Combine(root,"staged.n")));
  Check(staged.Success && stages.Annotations==1 && stages.Compiling==1,"annotation and before compiling stages");
  var stagedInputs=new ScriptInputs();
  Check((int)stagedHost.Evaluate(staged.Script,stagedInputs).Value==42 && evaluation.Calls==1 && wrapper.Calls==1 && stagedInputs.Properties.Count==0,"evaluation hook, wrapper, input snapshot");
  wrapper.Repeat=true;try{stagedHost.Evaluate(staged.Script,stagedInputs);throw new Exception("wrapper repeated execution");}catch(InvalidOperationException){}
  var implemented=new ScriptDefinition();implemented.Interfaces.Add(typeof(IScriptAnswer));
  Check(((IScriptAnswer)host.Evaluate(Compile("Answer() : int { 42 }\n()\n",implemented),new ScriptInputs()).Instance).Answer()==42,"configured CLR interface");
  var nested=new ScriptDefinition();nested.Properties.Add("nested",typeof(GenericOuter<int>.Nested<string>));
  var nestedInputs=new ScriptInputs();nestedInputs.Properties.Add("nested",new GenericOuter<int>.Nested<string>{First=42,Second="ok"});
  Check((int)host.Evaluate(Compile("nested.First\n",nested),nestedInputs).Value==42,"closed nested generic contract");
  var prelude=new ScriptDefinition{Debug=true};prelude.Preludes.Add(new ScriptSource("def seed = 40 : int;\n",Path.Combine(root,"host-prelude.n")));
  var withPrelude=Compile("seed + 2\n",prelude);
  Check((int)host.Evaluate(withPrelude,new ScriptInputs()).Value==42 && withPrelude.Symbols!=null,"separately located prelude AST and PDB");
  File.WriteAllText(Path.Combine(root,"shared.n"),"counter.Add(1); mutable value : int = 0; Next() : int { value = value + 1; value }\n");
  File.WriteAllText(Path.Combine(root,"branchone.n"),"[assembly: Import(\"shared.n\")]\nNext() : int { shared.Next() }\n");
  File.WriteAllText(Path.Combine(root,"branchtwo.n"),"[assembly: Import(\"shared.n\")]\nNext() : int { shared.Next() }\n");
  var definition=new ScriptDefinition();definition.Properties.Add("counter",typeof(Counter));
  var counter=new Counter();var values=new ScriptInputs();values.Properties.Add("counter",counter);
  var diamond=Compile("[assembly: Import(\"branchone.n\",\"branchtwo.n\")]\nbranchone.Next() + branchtwo.Next()\n",definition);
  Check((int)host.Evaluate(diamond,values).Value==3 && counter.Value==1,"one imported initialization per evaluation graph");
  Check((int)host.Evaluate(diamond,values).Value==3 && counter.Value==2,"independent evaluation creates fresh graph");
  var independent=definition.Snapshot();independent.ShareImportedInstances=false;
  Check((int)host.Evaluate(Compile("[assembly: Import(\"branchone.n\",\"branchtwo.n\")]\nbranchone.Next() + branchtwo.Next()\n",independent),values).Value==2 && counter.Value==4,"explicit separate branch instances");
  var provider=new ChildInputs{Invalid=true};var invalidHost=new ScriptHost(new ScriptHostOptions{ImportedInputProvider=provider});
  try{invalidHost.Evaluate(diamond,values);throw new Exception("invalid child input accepted");}catch(ArgumentException){}
  Check(counter.Value==4,"child schema validation before graph initialization");
  using(var session=new ScriptSession(host,definition,values)) {
    var first=session.Submit(new ScriptSource("[assembly: Import(\"shared.n\")]\nshared.Next()\n",Path.Combine(root,"first.n")));
    var second=session.Submit(new ScriptSource("shared.Next()\n",Path.Combine(root,"second.n")));
    Check(first.Success && second.Success && (int)first.Evaluation.Value==1 && (int)second.Evaluation.Value==2 && counter.Value==5,"session retains imported instances");
    var importedHistory=Path.Combine(root,"import.history");session.SaveHistory(importedHistory);
    File.AppendAllText(Path.Combine(root,"shared.n"),"\n// changed\n");
    var replacement=session.Submit(new ScriptSource("[assembly: Import(\"shared.n\")]\nshared.Next()\n",Path.Combine(root,"third.n")));
    Check(!replacement.Success && replacement.Compilation.Diagnostics[0].Message.Contains("changed"),"session imported replacement rejected");
    Check(session.ReadHistory(importedHistory).Length==2 && counter.Value==5,"imported history read does not execute changed source");
    var replay=session.ReplayHistory(importedHistory);
    Check(replay.Length==1 && !replay[0].Success && replay[0].Compilation.Diagnostics[0].Message.Contains("dependencies changed") && counter.Value==5,"imported history rejects changed graph before execution");
  }
  using(var aliasSession=new ScriptSession(host,new ScriptDefinition(),new ScriptInputs())) {
    var first=aliasSession.Submit(new ScriptSource("[assembly: Import(\"math.n\")]\nusing M = math.functions; M.Answer()\n",Path.Combine(root,"aliasfirst.n")));
    var second=aliasSession.Submit(new ScriptSource("M.Answer()\n",Path.Combine(root,"aliassecond.n")));
    foreach(var diagnostic in first.Compilation.Diagnostics)Console.WriteLine(diagnostic.Message);
    foreach(var diagnostic in second.Compilation.Diagnostics)Console.WriteLine(diagnostic.Message);
    Check(first.Success && second.Success && (int)second.Evaluation.Value==42,"imported mask aliases persist across submissions");
  }
  using(var generics=new ScriptSession(host,new ScriptDefinition(),new ScriptInputs())) {
    var declarations=generics.Submit(new ScriptSource("type Box[T] = System.Collections.Generic.List[T];\nIdentity[T](n : T) : T { n }\nPick(n : int) : int { n } Pick(n : string) : string { n }\n()\n",Path.Combine(root,"genericfirst.n")));
    foreach(var diagnostic in declarations.Compilation.Diagnostics)Console.WriteLine(diagnostic.Message);
    Check(declarations.Success,"generic aliases and overloads declared in REPL");
    var reuse=generics.Submit(new ScriptSource("def items : Box[int] = Box(); items.Add(42); Identity(items[0]) + Pick(0)\n",Path.Combine(root,"genericsecond.n")));
    foreach(var diagnostic in reuse.Compilation.Diagnostics)Console.WriteLine(diagnostic.Message);
    Check(reuse.Success && (int)reuse.Evaluation.Value==42,"generic aliases and overloads persist across submissions");
  }
  var cacheOptions=new ScriptHostOptions{Cache=new FileScriptArtifactCache(Path.Combine(root,"graph-cache"),64*1024*1024)};
  var caching=new ScriptHost(cacheOptions);var graphSource=new ScriptSource("[assembly: Import(\"math.n\")]\nmath.nested.Double(21)\n",Path.Combine(root,"graphcache.n"));
  var firstGraph=caching.Compile(graphSource);var secondGraph=caching.Compile(graphSource);
  Check(firstGraph.Success && secondGraph.Success && firstGraph.Script.Assembly.FullName==secondGraph.Script.Assembly.FullName,"graph artifact cache hit");
  var savedCacheHit=Path.Combine(root,"cachedgraph.dll");caching.Save(secondGraph.Script,savedCacheHit);
  Check((int)caching.Evaluate(caching.Load(savedCacheHit,new ScriptDefinition()),new ScriptInputs()).Value==42,"cache-hit graph can be saved without temporary compile paths");
  File.AppendAllText(Path.Combine(root,"math.n"),"\n// cache invalidation\n");
  var changedGraph=caching.Compile(graphSource);
  Check(changedGraph.Success && changedGraph.Script.Assembly.FullName!=secondGraph.Script.Assembly.FullName,"graph cache includes imported source");
  Console.WriteLine("PASS: structured input completeness, compilation/evaluation stages, wrappers, CLR interfaces, nested generic types, preludes, graph input validation/sharing, session imports and graph cache invalidation");
 }
 static void CopyTree(string source,string destination) {
  Directory.CreateDirectory(destination);foreach(var file in Directory.GetFiles(source))File.Copy(file,Path.Combine(destination,Path.GetFileName(file)));
  foreach(var directory in Directory.GetDirectories(source))CopyTree(directory,Path.Combine(destination,Path.GetFileName(directory)));
 }

}
