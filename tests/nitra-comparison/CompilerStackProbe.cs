// Diagnostic control: run the unchanged comparison worker with the existing
// command-line compiler's stack budget. This does not change the default host.
using System;
using System.Reflection;
using System.Threading;
class CompilerStackProbe {
    static int Main(string[] args) {
        int code=2;
        var thread=new Thread(()=>{
            try {
                var main=Assembly.LoadFrom(args[0]).GetType("Worker").GetMethod("Main",BindingFlags.Static|BindingFlags.NonPublic);
                code=(int)main.Invoke(null,new object[]{new[]{args[1],args[2],args[3]}});
            } catch(Exception error) {Console.Error.WriteLine(error);}
        },int.Parse(args[4]));
        thread.Name="Compiler stack diagnostic";thread.Start();thread.Join();return code;
    }
}
