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
        /// The OS a .NET target is specific to (`windows`, `android`, `ios`, `maccatalyst`, `macos`, `tvos`), or null.
        public string Platform { get; private set; }
        /// The platform's version from the name (`35.0` in `net9.0-android35.0`), or null for the default one.
        public string PlatformVersion { get; private set; }

        ClrTarget(string name, string family, Version version) { Name = name; Family = family; Version = version; }

        static readonly string[] Platforms = { "windows", "android", "ios", "maccatalyst", "macos", "tvos" };

        /// The target without its platform (`net9.0` for `net9.0-android35.0`): the base .NET's reference assemblies.
        public ClrTarget Base { get { return Platform == null ? this : new ClrTarget("net" + Version.Major + "." + Version.Minor, Family, Version); } }

        /// A .NET Standard target is a contract between runtimes: it has libraries only. So are the mobile and Apple
        /// platforms here: their apps are packaged (and compiled ahead of time) by the platform's workload, which takes
        /// these libraries; Windows programs run on the desktop runtime.
        public bool Executables { get { return Family != "netstandard" && (Platform == null || Platform == "windows"); } }

        /// The framework a program names in its runtimeconfig.json; null when it needs none (.NET Framework and
        /// Mono start a program directly). A Windows program runs on the desktop runtime (WinForms, WPF).
        public string RuntimeConfigFramework
        {
            get { return Family != "netcore" ? null : Platform == "windows" ? "Microsoft.WindowsDesktop.App" : "Microsoft.NETCore.App"; }
        }

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
            // a platform: net8.0-windows, net9.0-android35.0, net9.0-ios18.0, ...
            int dash = n.IndexOf('-');
            if (dash > 0 && n.StartsWith("net", StringComparison.Ordinal) && Version.TryParse(n.Substring(3, dash - 3), out v) && v.Major >= 5)
            {
                string rest = n.Substring(dash + 1);
                string platform = Platforms.FirstOrDefault(x => rest.StartsWith(x, StringComparison.Ordinal) && (rest.Length == x.Length || char.IsDigit(rest[x.Length])));
                if (platform == null) throw new ArgumentException("unknown platform `" + rest + "' in `" + name + "'; the platforms are " + string.Join(", ", Platforms));
                string pv = rest.Substring(platform.Length);
                Version check;
                if (pv.Length > 0 && !Version.TryParse(pv.Contains(".") ? pv : pv + ".0", out check)) throw new ArgumentException("`" + pv + "' is not a platform version in `" + name + "'");
                return new ClrTarget(n, "netcore", v) { Platform = platform, PlatformVersion = pv.Length == 0 ? null : (pv.Contains(".") ? pv : pv + ".0") };
            }
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
            throw new ArgumentException("unknown target framework `" + name + "'; the targets are netcoreapp3.x, net5.0 and later (with a platform: net8.0-windows, net9.0-android, net9.0-ios, ...), netstandard2.0, netstandard2.1, and net462 to net481");
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
                // before .NET 5, .NET Core numbered System.Runtime 4.2.x (3.0 and 3.1 alike)
                if (v.Major < 5) return new ClrTarget("netcoreapp3.x", "netcore", new Version(3, 0));
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
                    // .NET Core 3.x calls its folder netcoreappX.Y; .NET 5 and later netX.Y
                    folder = (Version.Major >= 5 ? "ref/net" : "ref/netcoreapp") + Version.Major + "." + Version.Minor;
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
