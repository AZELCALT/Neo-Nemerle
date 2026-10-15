// EXPERIMENT: reads a binary's continuation section (doc/CONTINUATION.md) and checks what it carries.
//   ContinuationChecks.dll <binary> <toolchain> [expected grammar [source file expected alternatives]]
using System;
using System.IO;
using System.Linq;
using System.Reflection;
using Store = Nemerle.Compiler.continuation.ContinuationStore;

static class ContinuationChecks
{
    static void Check(bool condition, string message) { if (!condition) throw new Exception(message); }

    static int Main(string[] args)
    {
        var image = File.ReadAllBytes(args[0]);
        var toolchain = args[1];
        var raw = Nemerle.Platform.ClrCompilerSection.ReadBytes(image);
        if (args.Length > 2 && args[2] == "--extract-image")
        {
            File.WriteAllBytes(args[3], Store.FromImage(image).GrammarImage);
            Console.WriteLine("wrote " + args[3]);
            return 0;
        }
        if (args.Length < 3)
        {
            Check(raw == null, "a compilation without -experimental-continuation must not write a .nemir section");
            Console.WriteLine("PASS: no continuation section without the flag");
            return 0;
        }
        Check(raw != null, "missing .nemir section");
        var store = Store.FromImage(image);
        if (args[2] == "--macros")
        {
            // E5: every macro defined in the binary is indexed, and its mark is the exact span of its definition
            Check(store.Macros.Count > 0, "no macros indexed");
            var text = File.ReadAllText(args[3]);
            foreach (var m in store.Macros)
            {
                Check(m.Start >= 0 && m.End <= text.Length && Store.Hash(Store.Normalize(text.Substring(m.Start, m.End - m.Start))) == m.Hash,
                    "macro mark " + m.Name + " [" + m.Start + "," + m.End + ") does not match the source text");
                Check(Assembly.LoadFrom(args[0]).GetType(m.TypeName) != null, "macro class " + m.TypeName + " not in the binary");
            }
            if (store.Types.Count > 0)
                Console.WriteLine("type subsection: " + string.Join("; ", store.Types.Select(t => t.TypeName + " {" + string.Join(", ", t.Members) + "}")));
            Console.WriteLine("PASS: macro subsection: " + string.Join(", ", store.Macros.Select(m => m.Name + " (" + m.TypeName + ") [" + m.Start + "," + m.End + ")")) + "; marks match the source");
            return 0;
        }
        Check(store.GrammarImage != null, "no grammar image");
        var grammar = store.Grammars.FirstOrDefault(g => g.Name == args[2]);
        Check(grammar != null, "grammar " + args[2] + " not recorded; have: " + string.Join(",", store.Grammars.Select(g => g.Name)));
        var kinds = grammar.Marks.GroupBy(m => m.Kind).ToDictionary(g => g.Key, g => g.Count());
        Check(grammar.Marks.All(m => m.End >= m.Start && m.Parent < grammar.Marks.IndexOf(m)), "marks must be spans in tree order");
        if (args.Length > 4)
        {
            // every mark is the exact span of its declaration in the source file
            var source = File.ReadAllText(args[3]);
            foreach (var m in grammar.Marks)
                Check(m.End <= source.Length && Store.Hash(Store.Normalize(source.Substring(m.Start, m.End - m.Start))) == m.Hash,
                    "mark " + m.Kind + " " + m.Name + " [" + m.Start + "," + m.End + ") does not match the source text");
            int rules = int.Parse(args[4]);
            Check(grammar.Marks.Count >= rules, "expected at least one mark per alternative (" + rules + "), got " + grammar.Marks.Count);
            Console.WriteLine("marks match the source; kinds: " + string.Join(", ", kinds.Select(k => k.Key + "=" + k.Value)));
        }
        // the stored image loads next to the compiler and Nitra and carries the generated recognition grammar
        var shared = new[] { "Nemerle.Compiler.dll", "Integrated.Nitra.Runtime.dll", "Integrated.DotNetLang.dll",
                             "Integrated.Nitra.Grammar.dll", "Integrated.Nitra.Compiler.dll" }
            .Select(n => Assembly.LoadFrom(Path.Combine(toolchain, n))).ToArray();
        var loaded = Store.LoadImage(store.GrammarImage, shared, shared.Select(a => a.Location).ToArray());
        var graphs = loaded.GetTypes().Count(t => t.GetMethod("GetRecognitionGrammar", BindingFlags.Public | BindingFlags.Static | BindingFlags.DeclaredOnly) != null);
        Check(graphs > 0, "stored image has no GetRecognitionGrammar");
        var roundTrip = Store.Read(store.Write());
        Check(roundTrip.Grammars.Count == store.Grammars.Count && roundTrip.GrammarImage.Length == store.GrammarImage.Length, "container round trip");
        Console.WriteLine("PASS: continuation section: " + raw.Length + " bytes (grammar image " + store.GrammarImage.Length +
            " bytes uncompressed), grammar " + grammar.Name + " with " + grammar.Marks.Count + " marks, " + graphs + " recognition graph(s) load");
        return 0;
    }
}
