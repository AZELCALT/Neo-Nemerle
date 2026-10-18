using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;

namespace Nemerle.Platform
{
    /// The .NET a compilation targets. The compiler always runs on (and types against) the host runtime; a target
    /// says what the output may name: which public assemblies hold the framework's types (its reference
    /// assemblies), whether it can be a program, and what a program needs next to it to start.
    public sealed class ClrTarget
    {
        /// `net10.0`, `net8.0`, `netstandard2.0`, `netstandard2.1`, `net48`, ...
        public string Name { get; private set; }
        /// "netcore", "netstandard" or "netframework".
        public string Family { get; private set; }
        public Version Version { get; private set; }

        ClrTarget(string name, string family, Version version) { Name = name; Family = family; Version = version; }

        /// A .NET Standard target is a contract between runtimes: it has libraries only.
        public bool Executables { get { return Family != "netstandard"; } }

        /// The framework a program names in its runtimeconfig.json; null when it needs none (.NET Framework and
        /// Mono start a program directly).
        public string RuntimeConfigFramework { get { return Family == "netcore" ? "Microsoft.NETCore.App" : null; } }

        /// The version a program names in its runtimeconfig.json.
        public string RuntimeConfigVersion { get { return Version.Major + "." + Version.Minor + ".0"; } }

        /// The target of the running runtime (the default).
        public static ClrTarget Host
        {
            get { var v = typeof(object).Assembly.GetName().Version; return new ClrTarget("net" + v.Major + ".0", "netcore", new Version(v.Major, 0)); }
        }

        /// A target by its framework name.
        public static ClrTarget Parse(string name)
        {
            if (string.IsNullOrEmpty(name)) throw new ArgumentException("no target framework name");
            string n = name.Trim().ToLowerInvariant();
            Version v;
            if (n.StartsWith("netstandard", StringComparison.Ordinal) && Version.TryParse(n.Substring(11), out v)
                && (v == new Version(2, 0) || v == new Version(2, 1)))
                return new ClrTarget(n, "netstandard", v);
            if (n.StartsWith("netcoreapp", StringComparison.Ordinal) && Version.TryParse(n.Substring(10), out v) && v.Major >= 3)
                return new ClrTarget(n, "netcore", v);
            if (n.StartsWith("net", StringComparison.Ordinal) && n.Contains(".") && Version.TryParse(n.Substring(3), out v) && v.Major >= 5)
                return new ClrTarget(n, "netcore", v);
            // .NET Framework: net462 ... net481
            int digits;
            if (n.StartsWith("net", StringComparison.Ordinal) && !n.Contains(".") && n.Length >= 5 && int.TryParse(n.Substring(3), out digits))
            {
                string d = n.Substring(3);
                var fv = new Version(d[0] - '0', d[1] - '0', d.Length > 2 ? d[2] - '0' : 0);
                if (fv >= new Version(4, 6, 2) && fv.Major == 4) return new ClrTarget(n, "netframework", fv);
            }
            throw new ArgumentException("unknown target framework `" + name + "'; the targets are net5.0 and later, netstandard2.0, netstandard2.1, and net462 to net481");
        }

        /// The target a reference assembly folder is for: System.Runtime's version for .NET, netstandard.dll's for
        /// .NET Standard (a folder with no System.Runtime of its own), mscorlib's for .NET Framework.
        public static ClrTarget FromReferences(string directory)
        {
            string root = Path.GetFullPath(directory);
            if (!Directory.Exists(root)) throw new ArgumentException("the target reference folder does not exist: " + root);
            Func<string, Version> version = file => System.Reflection.AssemblyName.GetAssemblyName(Path.Combine(root, file)).Version;
            // the assembly that defines the types (the others in the folder are facades that forward to it)
            Func<string, bool> defines = file => File.Exists(Path.Combine(root, file)) && !IsFacade(Path.Combine(root, file));
            if (defines("netstandard.dll"))
            {
                var v = version("netstandard.dll");
                return new ClrTarget("netstandard" + v.Major + "." + v.Minor, "netstandard", new Version(v.Major, v.Minor));
            }
            if (defines("mscorlib.dll"))
                return new ClrTarget("netframework", "netframework", new Version(4, 0));
            if (File.Exists(Path.Combine(root, "System.Runtime.dll")))
            {
                var v = version("System.Runtime.dll");
                return new ClrTarget("net" + v.Major + ".0", "netcore", new Version(v.Major, 0));
            }
            throw new ArgumentException("not a reference assembly folder (no System.Runtime.dll, netstandard.dll or mscorlib.dll): " + root);
        }

        // a facade only forwards types elsewhere (netstandard2.0 ships System.Runtime.dll as one)
        static bool IsFacade(string path)
        {
            using (var definition = Mono.Cecil.AssemblyDefinition.ReadAssembly(path))
                return definition.MainModule.Types.Count(t => t.IsPublic) == 0;
        }

        /// The NuGet package that holds the target's reference assemblies, and the folder inside it.
        public void ReferencePackage(out string id, out string version, out string folder)
        {
            switch (Family)
            {
                case "netstandard":
                    if (Version.Minor == 0) { id = "NETStandard.Library"; version = "2.0.3"; folder = "build/netstandard2.0/ref"; }
                    else { id = "NETStandard.Library.Ref"; version = "2.1.0"; folder = "ref/netstandard2.1"; }
                    return;
                case "netframework":
                    string short_ = Version.Major.ToString() + Version.Minor + (Version.Build > 0 ? Version.Build.ToString() : "");
                    id = "Microsoft.NETFramework.ReferenceAssemblies.net" + short_; version = "1.0.3";
                    folder = "build/.NETFramework/v" + Version.Major + "." + Version.Minor + (Version.Build > 0 ? "." + Version.Build : "");
                    return;
                default:
                    id = "Microsoft.NETCore.App.Ref"; version = Version.Major + "." + Version.Minor + ".0";
                    folder = "ref/net" + Version.Major + "." + Version.Minor;
                    return;
            }
        }

        public bool SameAs(ClrTarget other) { return other != null && Family == other.Family && Version.Major == other.Version.Major && (Family == "netcore" || Version == other.Version); }

        public override string ToString() { return Name; }
    }

    /// The output names something the target does not have: each problem, by member and by the method that uses it.
    public sealed class ClrTargetException : Exception
    {
        public IList<string> Problems { get; private set; }
        public ClrTargetException(string target, IList<string> problems)
            : base(problems.Count + " use(s) of what " + target + " does not have") { Problems = problems; }
    }
}
