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
                if (Shared(name.Name) && !ReplacesHostFacade(name.Name, path))
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
                    string original;
                    if (!origins.TryGetValue(name.FullName, out original)) original = Path.GetFullPath(previous.Location);
                    if (original != path)
                        throw new InvalidOperationException("Two different reference paths have the same assembly identity: " + original + " and " + path);
                    return previous;
                }
                directories.Add(Path.GetDirectoryName(path));
                var assembly = LoadFromAssemblyPath(Loadable(path));
                loaded[name.FullName] = assembly;
                origins[name.FullName] = path;
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
            // The paths references were asked for, by identity (a reference assembly loads from a copy).
            readonly System.Collections.Generic.Dictionary<string, string> origins = new System.Collections.Generic.Dictionary<string, string>();

            // A reference assembly (metadata only, as platform packs and many packages ship them) is not loaded for
            // execution by the runtime; the compiler only reads its metadata, so it loads a copy without the
            // ReferenceAssembly mark, cached by the module id. The output still names the original identity.
            static string Loadable(string path)
            {
                if (!IsReferenceAssembly(path)) return path;
                var directory = Path.Combine(Path.GetTempPath(), "nemerle-reference-copies", ModuleId(path).ToString("N"));
                var copy = Path.Combine(directory, Path.GetFileName(path));
                if (File.Exists(copy)) return copy;
                Directory.CreateDirectory(directory);
                var pending = copy + "." + Guid.NewGuid().ToString("N") + ".tmp";
                try
                {
                    // writing resolves some of its references (enum values in attributes): its folder and the host's
                    using (var resolver = new Mono.Cecil.DefaultAssemblyResolver())
                    {
                        resolver.AddSearchDirectory(Path.GetDirectoryName(path));
                        resolver.AddSearchDirectory(Path.GetDirectoryName(typeof(object).Assembly.Location));
                        using (var definition = Mono.Cecil.AssemblyDefinition.ReadAssembly(path, new Mono.Cecil.ReaderParameters { AssemblyResolver = resolver }))
                        {
                            var marks = new System.Collections.Generic.List<Mono.Cecil.CustomAttribute>();
                            foreach (var a in definition.CustomAttributes)
                                if (a.AttributeType.FullName == "System.Runtime.CompilerServices.ReferenceAssemblyAttribute") marks.Add(a);
                            foreach (var a in marks) definition.CustomAttributes.Remove(a);
                            // the other mark: processor architecture "none" (0x70); a copy is plain IL
                            var flags = (uint)definition.Name.Attributes;
                            if ((flags & 0x70) == 0x70) definition.Name.Attributes = (Mono.Cecil.AssemblyAttributes)((flags & ~0x70u) | 0x10u);
                            // attributes are constructed when the compiler reads them, and their members here are
                            // stubs (they throw): give attribute types bodies that return defaults
                            foreach (var type in definition.MainModule.GetTypes())
                                if (IsAttribute(type))
                                    foreach (var method in type.Methods)
                                        if (method.HasBody) Stub(method);
                            // a module initializer's body is a stub (it throws), and reading attributes would run it
                            foreach (var type in definition.MainModule.Types)
                                if (type.Name == "<Module>")
                                    foreach (var method in new System.Collections.Generic.List<Mono.Cecil.MethodDefinition>(type.Methods))
                                        if (method.IsConstructor && method.IsStatic) type.Methods.Remove(method);
                            definition.Write(pending);
                        }
                    }
                    try { File.Move(pending, copy); } catch (IOException) { File.Delete(pending); } // another compiler made it first
                    return copy;
                }
                catch (Exception error) when (!(error is IOException))
                {
                    if (File.Exists(pending)) File.Delete(pending);
                    throw new BadImageFormatException("the reference assembly " + path + " cannot be read for compilation: " + error.Message, error);
                }
            }
            static bool IsAttribute(Mono.Cecil.TypeDefinition type)
            {
                for (var b = type.BaseType; b != null; )
                {
                    if (b.FullName == "System.Attribute") return true;
                    Mono.Cecil.TypeDefinition next;
                    try { next = b.Resolve(); } catch (Exception) { return false; }
                    b = next == null ? null : next.BaseType;
                }
                return false;
            }
            static void Stub(Mono.Cecil.MethodDefinition method)
            {
                var body = new Mono.Cecil.Cil.MethodBody(method);
                var il = body.GetILProcessor();
                var result = method.ReturnType;
                if (result.MetadataType != Mono.Cecil.MetadataType.Void)
                {
                    if (result.IsValueType || result.IsGenericParameter)
                    {
                        var local = new Mono.Cecil.Cil.VariableDefinition(result);
                        body.Variables.Add(local); body.InitLocals = true;
                        il.Emit(Mono.Cecil.Cil.OpCodes.Ldloca, local);
                        il.Emit(Mono.Cecil.Cil.OpCodes.Initobj, result);
                        il.Emit(Mono.Cecil.Cil.OpCodes.Ldloc, local);
                    }
                    else il.Emit(Mono.Cecil.Cil.OpCodes.Ldnull);
                }
                il.Emit(Mono.Cecil.Cil.OpCodes.Ret);
                method.Body = body;
            }
            static bool IsReferenceAssembly(string path)
            {
                using (var stream = File.OpenRead(path))
                using (var pe = new System.Reflection.PortableExecutable.PEReader(stream))
                {
                    if (!pe.HasMetadata) return false;
                    var metadata = System.Reflection.Metadata.PEReaderExtensions.GetMetadataReader(pe);
                    if (((int)metadata.GetAssemblyDefinition().Flags & 0x70) == 0x70) return true;
                    foreach (var handle in metadata.GetAssemblyDefinition().GetCustomAttributes())
                    {
                        var attribute = metadata.GetCustomAttribute(handle);
                        System.Reflection.Metadata.EntityHandle type;
                        if (attribute.Constructor.Kind == System.Reflection.Metadata.HandleKind.MemberReference)
                            type = metadata.GetMemberReference((System.Reflection.Metadata.MemberReferenceHandle)attribute.Constructor).Parent;
                        else if (attribute.Constructor.Kind == System.Reflection.Metadata.HandleKind.MethodDefinition)
                            type = metadata.GetMethodDefinition((System.Reflection.Metadata.MethodDefinitionHandle)attribute.Constructor).GetDeclaringType();
                        else continue;
                        string name = null;
                        if (type.Kind == System.Reflection.Metadata.HandleKind.TypeReference)
                            name = metadata.GetString(metadata.GetTypeReference((System.Reflection.Metadata.TypeReferenceHandle)type).Name);
                        else if (type.Kind == System.Reflection.Metadata.HandleKind.TypeDefinition)
                            name = metadata.GetString(metadata.GetTypeDefinition((System.Reflection.Metadata.TypeDefinitionHandle)type).Name);
                        if (name == "ReferenceAssemblyAttribute") return true;
                    }
                    return false;
                }
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
            // The host has an assembly of this name only as a facade (it defines no types), and `path` defines them:
            // a platform's own assembly (WindowsBase of the Windows desktop pack) is meant, not the host's stand-in.
            static readonly System.Collections.Generic.Dictionary<string, bool> facades = new System.Collections.Generic.Dictionary<string, bool>();
            static bool ReplacesHostFacade(string name, string path)
            {
                var host = Path.Combine(Path.GetDirectoryName(typeof(object).Assembly.Location), name + ".dll");
                if (!File.Exists(host) || Path.GetFullPath(path) == Path.GetFullPath(host)) return false;
                return DefinesNoTypes(host) && !DefinesNoTypes(path);
            }
            static bool DefinesNoTypes(string path)
            {
                bool result;
                lock (facades)
                    if (facades.TryGetValue(path, out result)) return result;
                using (var stream = File.OpenRead(path))
                using (var pe = new System.Reflection.PortableExecutable.PEReader(stream))
                {
                    var metadata = System.Reflection.Metadata.PEReaderExtensions.GetMetadataReader(pe);
                    result = metadata.TypeDefinitions.Count <= 1; // <Module> only
                }
                lock (facades) facades[path] = result;
                return result;
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
                // a real assembly in a reference folder over the host's facade of that name (WPF's WindowsBase)
                foreach (var directory in directories)
                {
                    var candidate = Path.Combine(directory, name.Name + ".dll");
                    if (File.Exists(candidate) && ReplacesHostFacade(name.Name, candidate)) return LoadReference(candidate);
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
            Assembly loaded;
            using (var pe = new MemoryStream(image, false))
            {
                if (symbols == null) loaded = context.LoadFromStream(pe);
                else using (var pdb = new MemoryStream(symbols, false)) loaded = context.LoadFromStream(pe, pdb);
            }
            KeepSection(loaded, image);
            return loaded;
#else
            return symbols == null ? Assembly.Load(image) : Assembly.Load(image, symbols);
#endif
        }
#if MODERN_CLR
        // the continuation section of an image loaded from memory, which has no file to read it from again: Nemerle's
        // runtime reads the type records there (Nemerle.Scopes, a value of another copy of a type), kept as long as the
        // assembly is (a process-wide slot, as the scopes' storage, in types of the core library only)
        static void KeepSection(Assembly assembly, byte[] image)
        {
            byte[] section;
            try { section = ClrCompilerSection.ReadBytes(image); }
            catch (InvalidDataException) { return; }
            if (section == null) return;
            var domain = AppDomain.CurrentDomain;
            lock (domain)
            {
                var kept = domain.GetData("Nemerle.Sections") as System.Runtime.CompilerServices.ConditionalWeakTable<Assembly, byte[]>;
                if (kept == null)
                {
                    kept = new System.Runtime.CompilerServices.ConditionalWeakTable<Assembly, byte[]>();
                    domain.SetData("Nemerle.Sections", kept);
                }
                kept.AddOrUpdate(assembly, section);
            }
        }
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
                if (references.TryGetValue(name.FullName, out path)) return Loaded(name, path) ?? LoadFromAssemblyPath(path);
                throw new FileNotFoundException("No explicit script dependency for " + name.FullName);
            }
            // the host's copy of a reference, when the host has loaded the same assembly: the script then shares its
            // types (and values in a scope) with the host, as the same CLR types. The same is the same name, version
            // and key, and for one without a key the same build (its module's MVID): another build of it is the
            // script's own copy
            static Assembly Loaded(AssemblyName name, string path)
            {
                var hosts = new System.Collections.Generic.List<AssemblyLoadContext> { Default };
                var host = GetLoadContext(typeof(ClrAssemblyLoader).Assembly);
                if (host != null && host != Default && !host.IsCollectible) hosts.Add(host);
                Guid? build = null;
                foreach (var context in hosts)
                    foreach (var assembly in context.Assemblies)
                    {
                        if (assembly.IsDynamic || assembly.FullName != name.FullName) continue;
                        var key = assembly.GetName().GetPublicKeyToken();
                        if (key != null && key.Length > 0) return assembly;
                        if (build == null) build = Mvid(path);
                        if (build == assembly.ManifestModule.ModuleVersionId) return assembly;
                    }
                return null;
            }
            static Guid Mvid(string path)
            {
                using (var stream = File.OpenRead(path))
                using (var pe = new System.Reflection.PortableExecutable.PEReader(stream))
                {
                    var metadata = System.Reflection.Metadata.PEReaderExtensions.GetMetadataReader(pe);
                    return metadata.GetGuid(metadata.GetModuleDefinition().Mvid);
                }
            }
        }
#endif
    }
}
