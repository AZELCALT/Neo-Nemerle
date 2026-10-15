using System;
using System.IO;
using System.Threading;
using Nemerle.Scripting.NuGet;
using static Nemerle.Scripting.contracts;
using static Nemerle.Scripting.dependencies;
using static Nemerle.Scripting.host;
using static Nemerle.Scripting.session;
class NuGetScriptingChecks {
 static void Check(bool value,string message) { if(!value)throw new Exception(message); }
 static void Main(string[] args) {
  var root=args[0]; var definition=new ScriptDefinition();definition.TargetReferenceDirectory=args[1];definition.Properties.Add("args",typeof(string[]));
  var resolver=new NuGetScriptResolver(Path.Combine(root,"packages"),new[]{Path.Combine(root,"feed")});resolver.Offline=true;
  var options=new ScriptHostOptions();options.Resolver=resolver;var host=new ScriptHost(options);
  var code="[assembly: DependsOn(\"Example\", \"1.0.0\")]\n[assembly: DependsOn(\"Other\", \"1.0.0\")]\nExampleApi.Value()\n";
  var compilation=host.Compile(new ScriptSource(code,Path.Combine(root,"deps.n")),definition);
  foreach(var diagnostic in compilation.Diagnostics)Console.WriteLine(diagnostic.Message);
  Check(compilation.Success,"dependency compilation");
  var inputs=new ScriptInputs();inputs.Properties.Add("args",Array.Empty<string>());
  var result=host.Evaluate(compilation.Script,inputs);if(result.Error!=null)throw result.Error;
  Check((int)result.Value==42,"transitive dependency execution");
  var artifact=Path.Combine(root,"saved.dll");host.Save(compilation.Script,artifact);
  var loaded=host.Load(artifact,definition);
  Check((int)host.Evaluate(loaded,inputs).Value==42,"bundled package artifact");
  using(var session=new ScriptSession(host,definition,inputs)) {
    Check(session.Submit(new ScriptSource(code,Path.Combine(root,"first.n"))).Success,"session dependencies");
    var later=session.Submit(new ScriptSource("ExampleApi.Value()\n",Path.Combine(root,"second.n")));
    foreach(var diagnostic in later.Compilation.Diagnostics)Console.WriteLine(diagnostic.Message);
    Check(later.Success && (int)later.Evaluation.Value==42,"package declarations persist across submissions");
  }
  var malformed=host.Compile(new ScriptSource("[assembly: DependsOn(System.String.Empty, \"1.0.0\")]\n()\n",Path.Combine(root,"bad.n")),definition);
  Check(!malformed.Success && malformed.Diagnostics[0].Line==1,"literal metadata validation");
  var native=host.Compile(new ScriptSource("[assembly: DependsOn(\"Native\", \"1.0.0\")]\nNativeFixture.Answer()\n",Path.Combine(root,"native.n")),definition);
  foreach(var diagnostic in native.Diagnostics)Console.WriteLine(diagnostic.Message);
  Check(native.Success,"native package compilation");
  var nativeResult=host.Evaluate(native.Script,inputs);if(nativeResult.Error!=null)throw nativeResult.Error;
  Check((int)nativeResult.Value==42,"native dependency and portable RID fallback");
  var macro=host.Compile(new ScriptSource("[assembly: DependsOn(\"MacroFixture\", \"1.0.0\")]\nusing macrofixture; answer\n",Path.Combine(root,"withmacro.n")),definition);
  foreach(var diagnostic in macro.Diagnostics)Console.WriteLine(diagnostic.Message);
  Check(macro.Success && (int)host.Evaluate(macro.Script,inputs).Value==42,"resolved macro syntax available before parsing");
  File.WriteAllText(Path.Combine(root,"macrochild.n"),"[assembly: DependsOn(\"MacroFixture\",\"1.0.0\")]\nusing macrofixture; Answer() : int { answer }\n");
  var macroGraph=host.Compile(new ScriptSource("[assembly: Import(\"macrochild.n\")]\nusing macrofixture; (macrochild.Answer() + answer) / 2\n",Path.Combine(root,"macroparent.n")),definition);
  foreach(var diagnostic in macroGraph.Diagnostics)Console.WriteLine(diagnostic.Message);
  Check(macroGraph.Success && (int)host.Evaluate(macroGraph.Script,inputs).Value==42,"source imports retain dependency macros before parent parsing");
  using(var fileSession=new ScriptSession(host,definition,inputs)) {
    var source=new ScriptSource("[assembly: DependsOn(\"Example.dll\")]\n[assembly: DependsOn(\"Helper.dll\")]\nExampleApi.Value()\n",Path.Combine(root,"direct.n"));
    Check(fileSession.Submit(source).Success,"relative assembly dependencies");
    var history=Path.Combine(root,"direct.history");fileSession.SaveHistory(history);
    var dependency=Path.Combine(root,"Helper.dll");var original=File.ReadAllBytes(dependency);
    using(var writer=new FileStream(dependency,FileMode.Append))writer.WriteByte(0);
    var replay=fileSession.ReplayHistory(history);
    Check(replay.Length==1 && !replay[0].Success && replay[0].Compilation.Diagnostics[0].Message.Contains("dependencies changed"),"history rejects changed assembly dependencies before evaluation");
    File.WriteAllBytes(dependency,original);
  }
  if(args.Length>2) {
    var remoteOptions=new ScriptHostOptions();remoteOptions.Resolver=new NuGetScriptResolver(Path.Combine(root,"remote-packages"),new[]{args[2]});
    var remoteHost=new ScriptHost(remoteOptions);
    var remote=remoteHost.Compile(new ScriptSource(code,Path.Combine(root,"remote.n")),definition);
    foreach(var diagnostic in remote.Diagnostics)Console.WriteLine(diagnostic.Message);
    Check(remote.Success,"explicit HTTP v3 feed resolution");
    var remoteResult=remoteHost.Evaluate(remote.Script,inputs);if(remoteResult.Error!=null)throw remoteResult.Error;
    Check((int)remoteResult.Value==42,"HTTP-downloaded transitive dependencies execute");
    Console.WriteLine("PASS: HTTP v3 index, package download, transitive resolution and execution");
  }
  Directory.Move(Path.Combine(root,"feed"),Path.Combine(root,"hidden-feed"));
  Check(host.Compile(new ScriptSource(code,Path.Combine(root,"deps.n")),definition).Success,"offline lock replay without feed");
  var helperPath=Path.Combine(root,"packages","packages","helper","1.0.0","lib","net10.0","Helper.dll");
  var helperBytes=File.ReadAllBytes(helperPath);File.WriteAllText(helperPath,"corrupt");
  Check(!host.Compile(new ScriptSource(code,Path.Combine(root,"deps.n")),definition).Success,"extracted package integrity");
  File.WriteAllBytes(helperPath,helperBytes);
  var conflict=host.Compile(new ScriptSource("[assembly: DependsOn(\"Example\", \"1.0.0\")]\n[assembly: DependsOn(\"Conflict\", \"1.0.0\")]\n()\n",Path.Combine(root,"conflict.n")),definition);
  Check(!conflict.Success,"conflicting graph rejected");
  Console.WriteLine("PASS: literal metadata, transitive diamond, lock/offline reuse, native RID fallback, macro syntax, saved dependencies and conflicts");
 }
}
