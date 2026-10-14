using System;
using System.IO;
using System.Reflection;
#if MODERN_CLR
using System.Runtime.Loader;
#endif

namespace Nemerle.Platform
{
    public static class ClrAssemblyLoader
    {
        public static Assembly Load(string name) { return Assembly.Load(new AssemblyName(name)); }
        public static Assembly Load(AssemblyName name) { return Assembly.Load(name); }
        public static Assembly LoadFile(string path)
        {
#if MODERN_CLR
            return new ClrLibrarySession().LoadReference(path);
#else
            return Assembly.LoadFrom(path);
#endif
        }
        public static Assembly FindBySimpleName(string name)
        {
#if MODERN_CLR
            foreach (var assembly in AssemblyLoadContext.Default.Assemblies)
                if (string.Equals(assembly.GetName().Name, name, StringComparison.OrdinalIgnoreCase)) return assembly;
            try { return Load(name); }
            catch (FileNotFoundException) { return null; }
#else
            return Assembly.LoadWithPartialName(name);
#endif
        }
        public static string GetLocation(Assembly assembly) { return assembly.Location; }
        public static string GetLocation(AssemblyName name)
        {
#if MODERN_CLR
            return Load(name).Location;
#else
            return name.CodeBase == null ? Load(name).Location : new Uri(name.CodeBase).LocalPath;
#endif
        }
    }
}

namespace Nemerle.Platform
{
    // One reference-load scope per compiler manager. CoreCLR's default probing
    // can prefer a host-directory DLL over an explicitly requested path.
    public sealed class ClrLibrarySession
    {
#if MODERN_CLR
        private sealed class ReferenceContext : AssemblyLoadContext
        {
            readonly System.Collections.Generic.Dictionary<string, Assembly> loaded =
                new System.Collections.Generic.Dictionary<string, Assembly>(StringComparer.OrdinalIgnoreCase);
            readonly System.Collections.Generic.HashSet<string> directories =
                new System.Collections.Generic.HashSet<string>(StringComparer.Ordinal);
            internal void Share(Assembly assembly)
            {
                Assembly existing;
                if (loaded.TryGetValue(assembly.FullName, out existing) && !ReferenceEquals(existing, assembly))
                    throw new InvalidOperationException("Conflicting shared assembly identity: " + assembly.FullName);
                loaded[assembly.FullName] = assembly;
            }
            // Another build of a core assembly (see OtherRuntimeBuild) lives in its own context, so that code which
            // was built for the running compiler (macro libraries) never binds to it.
            sealed class TargetRuntimeContext : AssemblyLoadContext
            {
                readonly ReferenceContext owner;
                internal TargetRuntimeContext(ReferenceContext owner) : base("Nemerle target runtime") { this.owner = owner; }
                protected override Assembly Load(AssemblyName name) { return owner.Resolve(name); }
            }
            TargetRuntimeContext target;
            // Macro libraries run inside the compiler: another build of the standard macros binds to the running
            // compiler and runtime (never to a target runtime loaded for compilation).
            sealed class PluginContext : AssemblyLoadContext
            {
                readonly string directory;
                internal PluginContext(string directory) : base("Nemerle macro plugin") { this.directory = directory; }
                protected override Assembly Load(AssemblyName name)
                {
                    if (Shared(name.Name)) return Default.LoadFromAssemblyName(name);
                    var path = Path.Combine(directory, name.Name + ".dll");
                    return File.Exists(path) ? LoadFromAssemblyPath(path) : null;
                }
            }
            // A macro or parser library runs inside the compiler. It shares the compilation's copy of a dependency when
            // that is the same build, and keeps its own copy (from its directory) when the compilation references another
            // build of the same identity (bootstrapping Nitra: the previous Nitra compiler compiling the next runtime).
            sealed class LibraryPluginContext : AssemblyLoadContext
            {
                readonly ReferenceContext owner; readonly string directory;
                internal LibraryPluginContext(ReferenceContext owner, string directory) : base("Nemerle plugin library")
                { this.owner = owner; this.directory = directory; }
                protected override Assembly Load(AssemblyName name)
                {
                    if (Shared(name.Name)) return owner.Resolve(name);
                    var path = Path.Combine(directory, name.Name + ".dll");
                    if (!File.Exists(path)) return owner.Resolve(name);
                    foreach (var loaded in owner.loaded.Values)
                        if (string.Equals(loaded.GetName().Name, name.Name, StringComparison.OrdinalIgnoreCase) && loaded.Location.Length > 0
                            && ModuleId(loaded.Location) == ModuleId(path))
                            return loaded;
                    return LoadFromAssemblyPath(path);   // its own build: bound to the plugin's other dependencies
                }
            }
            internal Assembly LoadPlugin(string path)
            {
                path = Path.GetFullPath(path);
                var name = AssemblyName.GetAssemblyName(path);
                Assembly previous;
                if (Shared(name.Name) || loaded.TryGetValue(name.FullName, out previous)) return LoadReference(path);
                var directory = Path.GetDirectoryName(path);
                var conflict = false;
                foreach (var dependency in Directory.GetFiles(directory, "*.dll"))
                    foreach (var other in loaded.Values)
                        if (other.Location.Length > 0 && Path.GetFullPath(other.Location) != Path.GetFullPath(dependency)
                            && string.Equals(other.GetName().Name, Path.GetFileNameWithoutExtension(dependency), StringComparison.OrdinalIgnoreCase)
                            && ModuleId(other.Location) != ModuleId(dependency))
                            conflict = true;
                if (!conflict) return LoadReference(path);
                var plugin = new LibraryPluginContext(this, directory).LoadFromAssemblyPath(path);
                loaded[name.FullName] = plugin;
                return plugin;
            }
            internal Assembly LoadReference(string path)
            {
                path = Path.GetFullPath(path);
                var name = AssemblyName.GetAssemblyName(path);
                Assembly previous;
                if (Shared(name.Name))
                {
                    if (!OtherRuntimeBuild(name, path)) return Default.LoadFromAssemblyName(name);
                    if (loaded.TryGetValue(name.FullName, out previous)) return previous;
                    if (name.Name == "Nemerle.Macros")
                    {
                        var plugin = new PluginContext(Path.GetDirectoryName(path)).LoadFromAssemblyPath(path);
                        loaded[name.FullName] = plugin;
                        return plugin;
                    }
                    directories.Add(Path.GetDirectoryName(path));
                    if (target == null) target = new TargetRuntimeContext(this);
                    var other = target.LoadFromAssemblyPath(path);
                    loaded[name.FullName] = other;
                    return other;
                }
                if (loaded.TryGetValue(name.FullName, out previous))
                {
                    // Scripts loaded from validated PE bytes have no Location. A
                    // host-shared instance is the authority for their CLR identity.
                    if (previous.Location.Length == 0) return previous;
                    if (Path.GetFullPath(previous.Location) != path)
                        throw new InvalidOperationException("Two different reference paths have the same assembly identity: " + previous.Location + " and " + path);
                    return previous;
                }
                directories.Add(Path.GetDirectoryName(path));
                var assembly = LoadFromAssemblyPath(path);
                loaded[name.FullName] = assembly;
                return assembly;
            }
            // Bootstrapping a runtime whose types moved: a compiler running on one build of Nemerle.dll /
            // Nemerle.Compiler.dll / Nemerle.Macros.dll may compile against a different build of them (whose
            // signatures use the new runtime). The same build (same module id) stays shared with the running compiler.
            static bool OtherRuntimeBuild(AssemblyName name, string path)
            {
                if (name.Name != "Nemerle" && name.Name != "Nemerle.Compiler" && name.Name != "Nemerle.Macros") return false;
                foreach (var running in Default.Assemblies)
                    if (running.GetName().Name == name.Name && running.Location.Length > 0)
                        return ModuleId(running.Location) != ModuleId(path);
                // Not loaded by the running compiler (e.g. -no-stdmacros -macros:<path>): another build than the
                // compiler's own copy is loaded from its path.
                var own = Path.Combine(AppContext.BaseDirectory, name.Name + ".dll");
                return File.Exists(own) && ModuleId(own) != ModuleId(path);
            }
            static Guid ModuleId(string path)
            {
                using (var stream = File.OpenRead(path))
                using (var pe = new System.Reflection.PortableExecutable.PEReader(stream))
                {
                    var metadata = System.Reflection.Metadata.PEReaderExtensions.GetMetadataReader(pe);
                    return metadata.GetGuid(metadata.GetModuleDefinition().Mvid);
                }
            }
            static bool Shared(string name)
            {
                return name == "Nemerle" || name == "Nemerle.Compiler" || name == "Nemerle.Platform" ||
                    name == "Nemerle.Macros" || name == "Mono.Cecil" || name == "System.CodeDom" ||
                    name == "mscorlib" || name == "netstandard" ||
                    File.Exists(Path.Combine(Path.GetDirectoryName(typeof(object).Assembly.Location), name + ".dll"));
            }
            protected override Assembly Load(AssemblyName name) { return Resolve(name); }
            internal Assembly Resolve(AssemblyName name)
            {
                Assembly assembly;
                if (loaded.TryGetValue(name.FullName, out assembly)) return assembly;
                // A dependency on another build of a core assembly (e.g. the newer Nemerle.dll next to a newer
                // Nemerle.Compiler.dll) resolves in this context when that build sits in a reference directory.
                foreach (var directory in directories)
                {
                    var candidate = Path.Combine(directory, name.Name + ".dll");
                    if (!File.Exists(candidate)) continue;
                    var candidateName = AssemblyName.GetAssemblyName(candidate);
                    // Only for a request of that build's version: code built for the running runtime keeps it.
                    if ((name.Version == null || name.Version.Equals(candidateName.Version)) && OtherRuntimeBuild(candidateName, candidate))
                        return LoadReference(candidate);
                }
                if (Shared(name.Name)) return Default.LoadFromAssemblyName(name);
                // The build of the requested version first: a macro library built against one build of a library
                // (bootstrapping Nitra) keeps it while the compilation references another version.
                foreach (var directory in directories)
                {
                    var path = Path.Combine(directory, name.Name + ".dll");
                    if (File.Exists(path) && (name.Version == null || name.Version.Equals(AssemblyName.GetAssemblyName(path).Version)))
                        return LoadReference(path);
                }
                foreach (var directory in directories)
                {
                    var path = Path.Combine(directory, name.Name + ".dll");
                    if (File.Exists(path)) return LoadReference(path);
                }
                return null;
            }
        }
        readonly ReferenceContext context = new ReferenceContext();
#endif
        public void ShareAssembly(Assembly assembly)
        {
            if (assembly == null) throw new ArgumentNullException("assembly");
#if MODERN_CLR
            context.Share(assembly);
#endif
        }
        public Assembly LoadPlugin(string path)
        {
#if MODERN_CLR
            return context.LoadPlugin(path);
#else
            return Assembly.LoadFrom(path);
#endif
        }
        public Assembly LoadReference(string path)
        {
#if MODERN_CLR
            return context.LoadReference(path);
#else
            return Assembly.LoadFrom(path);
#endif
        }
    }
}

namespace Nemerle.Platform
{
    public static class ClrScriptSupport
    {
        public static string Digest(byte[] image)
        {
            using (var algorithm = System.Security.Cryptography.SHA256.Create())
                return BitConverter.ToString(algorithm.ComputeHash(image)).Replace("-", "");
        }
        public static string TypeName(Type type)
        {
            if (type.IsByRef || type.IsPointer || type.ContainsGenericParameters)
                throw new ArgumentException("Script contracts require closed managed types: " + type);
            if (type == typeof(void)) return "void";
            if (type.IsArray)
            {
                if (type.GetArrayRank() != 1) throw new ArgumentException("Only one-dimensional script contract arrays are supported");
                return "array[" + TypeName(type.GetElementType()) + "]";
            }
            var chain = new System.Collections.Generic.Stack<Type>();
            for (var current = type; current != null; current = current.DeclaringType) chain.Push(current);
            var arguments = type.IsGenericType ? type.GetGenericArguments() : new Type[0];
            var index = 0;
            var result = new System.Text.StringBuilder();
            while (chain.Count != 0)
            {
                var part = chain.Pop();
                if (result.Length == 0 && !string.IsNullOrEmpty(part.Namespace)) result.Append(part.Namespace).Append('.');
                else if (result.Length != 0) result.Append('.');
                var tick = part.Name.IndexOf('`');
                result.Append(tick < 0 ? part.Name : part.Name.Substring(0, tick));
                var count = tick < 0 ? 0 : int.Parse(part.Name.Substring(tick + 1), System.Globalization.CultureInfo.InvariantCulture);
                if (count != 0)
                {
                    result.Append('[');
                    for (var i = 0; i < count; i++)
                    {
                        if (i != 0) result.Append(',');
                        result.Append(TypeName(arguments[index++]));
                    }
                    result.Append(']');
                }
            }
            return result.ToString();
        }
        public static bool Identifier(string value)
        {
            if (string.IsNullOrEmpty(value)) return false;
            if (!(char.IsLetter(value[0]) || value[0] == '_')) return false;
            foreach (var c in value) if (!(char.IsLetterOrDigit(c) || c == '_')) return false;
            return true;
        }
        public static Assembly Load(byte[] image, byte[] symbols, Assembly[] shared, string[] references)
        { return Load(image, symbols, shared, references, new string[0]); }
        public static Assembly Load(byte[] image, byte[] symbols, Assembly[] shared, string[] references, string[] nativeReferences)
        {
#if MODERN_CLR
            var context = new ScriptContext(shared, references, nativeReferences);
            using (var pe = new MemoryStream(image, false))
            {
                if (symbols == null) return context.LoadFromStream(pe);
                using (var pdb = new MemoryStream(symbols, false)) return context.LoadFromStream(pe, pdb);
            }
#else
            return symbols == null ? Assembly.Load(image) : Assembly.Load(image, symbols);
#endif
        }
#if MODERN_CLR
        sealed class ScriptContext : AssemblyLoadContext
        {
            readonly System.Collections.Generic.Dictionary<string, Assembly> shared = new System.Collections.Generic.Dictionary<string, Assembly>();
            readonly System.Collections.Generic.Dictionary<string, string> references = new System.Collections.Generic.Dictionary<string, string>();
            readonly System.Collections.Generic.Dictionary<string, string> native = new System.Collections.Generic.Dictionary<string, string>(StringComparer.Ordinal);
            public ScriptContext(Assembly[] assemblies, string[] paths, string[] nativePaths)
            {
                foreach (var path in nativePaths)
                {
                    var filename = Path.GetFileName(path);
                    var stem = filename.StartsWith("lib", StringComparison.Ordinal) ? filename.Substring(3) : filename;
                    var dot = stem.IndexOf('.');
                    if (dot >= 0) stem = stem.Substring(0, dot);
                    foreach (var key in new[] { filename, stem })
                    {
                        string previous;
                        if (native.TryGetValue(key, out previous) && previous != path)
                            throw new InvalidOperationException("Conflicting native script dependency: " + key);
                        native[key] = path;
                    }
                }
                foreach (var assembly in assemblies)
                {
                    Assembly previous;
                    if (shared.TryGetValue(assembly.FullName, out previous) && !ReferenceEquals(previous, assembly))
                        throw new InvalidOperationException("Conflicting script contract identity: " + assembly.FullName);
                    shared[assembly.FullName] = assembly;
                }
                foreach (var path in paths)
                {
                    var full = Path.GetFullPath(path);
                    var name = AssemblyName.GetAssemblyName(full).FullName;
                    string previous;
                    if (references.TryGetValue(name, out previous) && previous != full)
                        throw new InvalidOperationException("Conflicting script reference identity: " + name);
                    references[name] = full;
                }
            }
            protected override IntPtr LoadUnmanagedDll(string name)
            {
                string path;
                return native.TryGetValue(name, out path) ? LoadUnmanagedDllFromPath(path) : IntPtr.Zero;
            }
            protected override Assembly Load(AssemblyName name)
            {
                Assembly assembly;
                if (shared.TryGetValue(name.FullName, out assembly)) return assembly;
                if (name.Name == "Nemerle" || name.Name == "Nemerle.Platform" ||
                    File.Exists(Path.Combine(Path.GetDirectoryName(typeof(object).Assembly.Location), name.Name + ".dll")))
                    return Default.LoadFromAssemblyName(name);
                string path;
                if (references.TryGetValue(name.FullName, out path)) return LoadFromAssemblyPath(path);
                throw new FileNotFoundException("No explicit script dependency for " + name.FullName);
            }
        }
#endif
    }
}
