using System;
using System.IO;
using System.Reflection;
using static Nemerle.Compiler.AST;
using static Nemerle.Compiler.compilation_options;
using static Nemerle.Compiler.manager_class;
using static Nemerle.Compiler.Source;
using static Nemerle.Collections;

// A probe of the existing compiler API, not the proposed public scripting API.
public static class RuntimeCompilationChecks
{
    static void Check(bool condition, string message)
    {
        if (!condition) throw new Exception(message);
    }
    static Assembly Compile(string sourcePath, string text, out int errors,
        out string diagnostics)
    {
        var previous = ManagerClass.Instance;
        int count = 0;
        var messages = new StringWriter();
        Assembly result = null;
        try
        {
            var options = new CompilationOptions();
            options.CompileToMemory = true;
            options.TargetIsLibrary = true;
            options.TargetIsSet = true;
            options.ProgressBar = false;
            options.ColorMessages = false;
            // Existing hosting mode turns compiler bailouts into exceptions.
            options.IgnoreConfusion = true;
            options.OutputFileName = "Probe_" + Guid.NewGuid().ToString("N") + ".dll";
            options.SourceRoot = Path.GetDirectoryName(sourcePath);
            options.Sources = NList.FromArray<ISource>(new ISource[] {
                new StringSource(Location.GetFileIndex(sourcePath), text)
            });
            var compiler = new ManagerClass(options);
            compiler.InitOutput(messages);
            compiler.ErrorOccured += (location, message) => {
                count++;
                Check(location.File == sourcePath && location.Line > 0,
                    "Errors must retain the supplied source identity");
            };
            try { compiler.Run(); }
            catch { if (count == 0) throw; }
            if (count == 0) result = compiler.GeneratedAssembly;
        }
        finally { ManagerClass.Instance = previous; }
        errors = count;
        diagnostics = messages.ToString();
        return result;
    }
    public static void Main(string[] args)
    {
        var source = Path.Combine(args[0], "later.n");
        int errors;
        string diagnostics;
        var original = ManagerClass.Instance;
        var first = Compile(source, "public class Later { public static Run() : int { 42 } }\n",
            out errors, out diagnostics);
        Check(errors == 0 && first != null, diagnostics);
        var method = first.GetType("later+Later").GetMethod("Run");
        Check((int)method.Invoke(null, null) == 42 && (int)method.Invoke(null, null) == 42,
            "Compiled code must support repeated invocation without recompiling");
        Check(ManagerClass.Instance == original, "Probe must restore the previous compiler context");
        var invalid = Compile(source, "public class Broken { public static Run() : int { absent_name } }\n",
            out errors, out diagnostics);
        Check(errors > 0 && invalid == null && diagnostics.Contains("absent_name"),
            "Invalid source must yield diagnostics rather than a runnable artifact");
        var afterFailure = Compile(source, "public class Later { public static Run() : int { 43 } }\n",
            out errors, out diagnostics);
        Check(errors == 0 && (int)afterFailure.GetType("later+Later").GetMethod("Run").Invoke(null, null) == 43,
            "A failed compilation must not poison the next one: " + diagnostics);
        Check((int)method.Invoke(null, null) == 42,
            "New code must coexist with the previous compiled artifact");
        var module = Compile(source,
            "mask api { Twice(x : int) : int { x * 2 } }\nRun() : int { api.Twice(21) }\n",
            out errors, out diagnostics);
        Check(errors == 0 && (int)module.GetType("later").GetMethod("Run").Invoke(null, null) == 42,
            "Source text compilation must retain file module and mask semantics: " + diagnostics);
        Check(ManagerClass.Instance == original, "Compiler context must be restored after all probes");
        Console.WriteLine("PASS: source-text compilation, structured error events, failure recovery, artifact coexistence, repeated invocation, file modules and masks");
    }
}
