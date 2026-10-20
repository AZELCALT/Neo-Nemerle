using System;
using static Nemerle.Compiler.compilation_options;
using static Nemerle.Compiler.manager_class;
using static Nemerle.Compiler.Source;
using static Nemerle.Collections;

public static class InMemoryHost
{
    public static int Main(string[] args)
    {
        var options = new CompilationOptions();
        options.CompileToMemory = true;
        options.ProgressBar = false;
        options.ColorMessages = false;
        options.OutputFileName = "InMemoryGenerated.exe";
        options.SourceRoot = System.IO.Path.GetDirectoryName(System.IO.Path.GetFullPath(args[0]));
        options.Sources = NList.FromArray<ISource>(
            new ISource[] { new FileSource(args[0], options.Warnings) });

        var compiler = new ManagerClass(options);
        compiler.InitOutput(Console.Out);
        compiler.Run();

        // hello.n is the file module hello; its top-level statements are hello.Main.
        compiler.GeneratedAssembly.GetType("hello").GetMethod("Main")
            .Invoke(null, new object[] { new string[0] });   // a program's Main takes its arguments
        return 0;
    }
}
