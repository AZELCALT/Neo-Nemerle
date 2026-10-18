using System;
using System.IO;
using System.Reflection;
using System.Reflection.Emit;
using System.Diagnostics.SymbolStore;
#if MODERN_CLR
using System.Reflection.Metadata;
using System.Reflection.Metadata.Ecma335;
using System.Reflection.PortableExecutable;
using System.Runtime.Loader;
#endif

namespace Nemerle.Platform
{
    // Owns one compilation's assembly lifecycle; language semantics stay in ncc.
    public sealed class ClrAssemblySession
    {
        public AssemblyBuilder Builder { get; private set; }
        public ModuleBuilder Module { get; private set; }
        public static bool LegacySecurityAvailable {
            get {
#if MODERN_CLR
                return false;
#else
                return true;
#endif
            }
        }
        public static void RunLegacySecurity(Action emit)
        {
#if !MODERN_CLR
            emit();
#endif
        }
        readonly bool inMemory;
        readonly bool emitDebug;
        readonly string output;
        MethodInfo entryPoint;
        bool windows;
        Assembly executable;
#if MODERN_CLR
        readonly System.Collections.Generic.List<Tuple<string, byte[]>> resources =
            new System.Collections.Generic.List<Tuple<string, byte[]>>();
        ClrNativeResources nativeResources;
        byte[] compilerSection;
        byte[] compilerSigningKey;
#endif

        /// The target framework of the output; null: the host's.
        public ClrTarget Target { get; set; }

        public ClrAssemblySession(AssemblyName name, string outputPath, bool compileToMemory, bool debug)
            : this(name, outputPath, compileToMemory, debug, null) { }

        public ClrAssemblySession(AssemblyName name, string outputPath, bool compileToMemory, bool debug, object[] permissions)
        {
            inMemory = compileToMemory;
            emitDebug = debug;
            output = Path.GetFullPath(outputPath);
#if MODERN_CLR
            if (debug && compileToMemory) throw new NotSupportedException("Portable debug symbols require persisted compilation.");
            if (permissions != null && Array.Exists(permissions, value => value != null))
                throw new NotSupportedException("Declarative security is not supported by the CoreCLR backend.");
            Builder = compileToMemory
                ? AssemblyBuilder.DefineDynamicAssembly(name, AssemblyBuilderAccess.Run)
                : new PersistedAssemblyBuilder(name, typeof(object).Assembly);
            Module = Builder.DefineDynamicModule(name.Name);
#else
            Builder = AppDomain.CurrentDomain.DefineDynamicAssembly(name,
                compileToMemory ? AssemblyBuilderAccess.Run : AssemblyBuilderAccess.Save,
                Path.GetDirectoryName(output),
                permissions == null ? null : (System.Security.PermissionSet)permissions[0],
                permissions == null ? null : (System.Security.PermissionSet)permissions[1],
                permissions == null ? null : (System.Security.PermissionSet)permissions[2]);
            Module = compileToMemory ? Builder.DefineDynamicModule(name.Name, debug)
                : Builder.DefineDynamicModule(name.Name, Path.GetFileName(output), debug);
#endif
        }

        public ISymbolWriter GetSymbolWriter()
        {
#if MODERN_CLR
            // Sequence points belong to the portable-PDB writer, not an unmanaged writer.
            return null;
#else
            return Module.GetSymWriter();
#endif
        }

        public void SetEntryPoint(MethodInfo method, bool windowsApplication)
        {
            entryPoint = method;
            windows = windowsApplication;
#if !MODERN_CLR
            Builder.SetEntryPoint(method, windows ? PEFileKinds.WindowApplication : PEFileKinds.ConsoleApplication);
#endif
        }

        public void SetCompilerSection(byte[] data, byte[] signingKey = null)
        {
#if MODERN_CLR
            if (inMemory) throw new NotSupportedException("Compiler sections require persisted compilation.");
            if (compilerSection != null) throw new InvalidOperationException("Compiler section already specified.");
            compilerSection = (byte[])data.Clone();
            compilerSigningKey = signingKey == null ? null : (byte[])signingKey.Clone();
#else
            throw new NotSupportedException("Compiler sections require CoreCLR.");
#endif
        }

        public void AddEmbeddedResource(string name, string path)
        {
#if MODERN_CLR
            if (inMemory) throw new NotSupportedException("Embedded resources require persisted compilation.");
            resources.Add(Tuple.Create(name, File.ReadAllBytes(path)));
#else
            var stream = File.OpenRead(path);
            try { Module.DefineManifestResource(name, stream, ResourceAttributes.Public); }
            catch { stream.Dispose(); throw; }
#endif
        }
        public void AddLinkedResource(string name, string path)
        {
#if MODERN_CLR
            throw new NotSupportedException("CoreCLR cannot load external linked resources; use embedded resources instead.");
#else
            Builder.AddResourceFile(name, path);
#endif
        }
        public void AddUnmanagedResource(string path)
        {
#if MODERN_CLR
            if (inMemory) throw new NotSupportedException("Native resources require persisted compilation.");
            if (nativeResources != null) throw new InvalidOperationException("Native resources already specified.");
            nativeResources = new ClrNativeResources(File.ReadAllBytes(path));
#else
            Module.DefineUnmanagedResource(path);
#endif
        }
        public void AddVersionResource()
        {
#if !MODERN_CLR
            Builder.DefineVersionInfoResource();
#endif
        }

        public void Save(PortableExecutableKinds kind, ImageFileMachine machine)
        {
            if (inMemory) throw new InvalidOperationException("Cannot save a runnable assembly session.");
#if MODERN_CLR
            var persisted = (PersistedAssemblyBuilder)Builder;
            BlobBuilder il, fields;
            MetadataBuilder symbols;
            var metadata = persisted.GenerateMetadata(out il, out fields, out symbols);
            var resourceData = new BlobBuilder();
            foreach (var resource in resources)
            {
                uint offset = (uint)resourceData.Count;
                resourceData.WriteInt32(resource.Item2.Length);
                resourceData.WriteBytes(resource.Item2);
                metadata.AddManifestResource(ManifestResourceAttributes.Public,
                    metadata.GetOrAddString(resource.Item1), default(EntityHandle), offset);
            }
            var entry = entryPoint == null ? default(MethodDefinitionHandle)
                : MetadataTokens.MethodDefinitionHandle(entryPoint.MetadataToken);
            DebugDirectoryBuilder debugDirectory = null;
            if (emitDebug)
            {
                var pdb = new PortablePdbBuilder(symbols, metadata.GetRowCounts(), entry);
                var pdbBlob = new BlobBuilder();
                var id = pdb.Serialize(pdbBlob);
                var pdbPath = Path.ChangeExtension(output, ".pdb");
                using (var stream = File.Create(pdbPath)) pdbBlob.WriteContentTo(stream);
                debugDirectory = new DebugDirectoryBuilder();
                debugDirectory.AddCodeViewEntry(Path.GetFileName(pdbPath), id, pdb.FormatVersion);
            }
            var flags = CorFlags.ILOnly;
            if ((kind & PortableExecutableKinds.Required32Bit) != 0) flags |= CorFlags.Requires32Bit;
            if (compilerSigningKey != null) flags |= CorFlags.StrongNameSigned;
            var peMachine = (Machine)(ushort)machine;
            var characteristics = Characteristics.ExecutableImage;
            if (entryPoint == null) characteristics |= Characteristics.Dll;
            var header = new PEHeaderBuilder(machine: peMachine,
                imageCharacteristics: characteristics,
                subsystem: windows ? Subsystem.WindowsGui : Subsystem.WindowsCui);
            var image = new CompilerSectionPEBuilder(header, new MetadataRootBuilder(metadata),
                il, fields, resourceData, entry, flags, debugDirectory, nativeResources, compilerSection,
                compilerSigningKey == null ? 128 : checked((int)BitConverter.ToUInt32(compilerSigningKey, 12) / 8));
            var blob = new BlobBuilder();
            image.Serialize(blob);
            if (compilerSigningKey != null) ClrCompilerSection.Sign(image, blob, compilerSigningKey);
            using (var stream = File.Create(output)) blob.WriteContentTo(stream);
            if (!emitDebug && File.Exists(Path.ChangeExtension(output, ".pdb")))
                File.Delete(Path.ChangeExtension(output, ".pdb"));
            // a program for .NET names the runtime it starts on; .NET Framework and Mono start it directly
            var target = Target ?? ClrTarget.Host;
            var config = Path.ChangeExtension(output, ".runtimeconfig.json");
            if (entryPoint != null && target.RuntimeConfigFramework != null)
                File.WriteAllText(config,
                    "{\"runtimeOptions\":{\"tfm\":\"" + target.Name + "\",\"framework\":{\"name\":\"" + target.RuntimeConfigFramework
                    + "\",\"version\":\"" + target.RuntimeConfigVersion + "\"}}}");
            else if (File.Exists(config)) File.Delete(config);
#else
            Builder.Save(Path.GetFileName(output), kind, machine);
#endif
        }

        public Assembly ExecutableAssembly
        {
            get {
                if (inMemory) return Builder;
                if (executable == null)
                {
#if MODERN_CLR
                    executable = AssemblyLoadContext.Default.LoadFromAssemblyPath(output);
#else
                    executable = Builder;
#endif
                }
                return executable;
            }
        }
    }
#if MODERN_CLR
    // Converts the standard resource-compiler .res container into a PE .rsrc
    // directory. No Windows API or SDK resource compiler is needed at emission.
    internal sealed class ClrNativeResources : ResourceSectionBuilder
    {
        sealed class Key : IComparable<Key>
        {
            public readonly string Name;
            public readonly ushort Id;
            public Key(string name, ushort id) { Name = name; Id = id; }
            public int CompareTo(Key other)
            {
                if (Name != null) return other.Name == null ? -1 : StringComparer.Ordinal.Compare(Name, other.Name);
                return other.Name != null ? 1 : Id.CompareTo(other.Id);
            }
        }
        sealed class Node
        {
            public readonly System.Collections.Generic.SortedDictionary<Key, Node> Children =
                new System.Collections.Generic.SortedDictionary<Key, Node>();
            public byte[] Data;
            public int Offset, NameOffset, PayloadOffset;
        }
        readonly Node root = new Node();
        static int Align(int value) { return checked((value + 3) & ~3); }
        static Key ReadKey(BinaryReader reader, long end)
        {
            if (reader.BaseStream.Position + 2 > end) throw new InvalidDataException("Truncated native resource identifier.");
            ushort first = reader.ReadUInt16();
            if (first == 0xffff)
            {
                if (reader.BaseStream.Position + 2 > end) throw new InvalidDataException("Truncated native resource ordinal.");
                return new Key(null, reader.ReadUInt16());
            }
            var text = new System.Text.StringBuilder();
            while (first != 0)
            {
                text.Append((char)first);
                if (reader.BaseStream.Position + 2 > end) throw new InvalidDataException("Unterminated native resource name.");
                first = reader.ReadUInt16();
            }
            return new Key(text.ToString(), 0);
        }
        static Node Child(Node parent, Key key)
        {
            Node value;
            if (!parent.Children.TryGetValue(key, out value)) parent.Children.Add(key, value = new Node());
            return value;
        }
        public ClrNativeResources(byte[] input)
        {
            using (var stream = new MemoryStream(input, false))
            using (var reader = new BinaryReader(stream))
            {
                while (stream.Position < stream.Length)
                {
                    long start = stream.Position;
                    if (stream.Length - start < 8) throw new InvalidDataException("Truncated native resource header.");
                    uint length = reader.ReadUInt32(), header = reader.ReadUInt32();
                    long end = start + header;
                    if (header < 8 || end > stream.Length || length > stream.Length - end)
                        throw new InvalidDataException("Invalid native resource size.");
                    var type = ReadKey(reader, end);
                    var name = ReadKey(reader, end);
                    stream.Position = Align(checked((int)stream.Position));
                    if (stream.Position + 16 > end) throw new InvalidDataException("Truncated native resource metadata.");
                    reader.ReadUInt32(); reader.ReadUInt16();
                    ushort language = reader.ReadUInt16();
                    reader.ReadUInt32(); reader.ReadUInt32();
                    stream.Position = end;
                    var data = reader.ReadBytes(checked((int)length));
                    // The conventional empty type=0/name=0 entry is a file header.
                    if (!(length == 0 && type.Name == null && type.Id == 0 && name.Name == null && name.Id == 0))
                    {
                        var leaf = Child(Child(Child(root, type), name), new Key(null, language));
                        if (leaf.Data != null) throw new InvalidDataException("Duplicate native resource type/name/language.");
                        leaf.Data = data;
                    }
                    long next = Align(checked((int)stream.Position));
                    if (next > stream.Length && stream.Position != stream.Length)
                        throw new InvalidDataException("Truncated native resource padding.");
                    stream.Position = Math.Min(next, stream.Length);
                }
            }
        }
        static void Layout(Node node, ref int offset)
        {
            if (node.Data != null) return;
            node.Offset = offset;
            offset = checked(offset + 16 + 8 * node.Children.Count);
            foreach (var child in node.Children.Values) Layout(child, ref offset);
        }
        static void Names(Node node, ref int offset)
        {
            foreach (var item in node.Children)
            {
                if (item.Key.Name != null)
                {
                    if (item.Key.Name.Length > ushort.MaxValue) throw new InvalidDataException("Native resource name is too long.");
                    item.Value.NameOffset = offset;
                    offset = checked(offset + 2 + 2 * item.Key.Name.Length);
                }
                Names(item.Value, ref offset);
            }
        }
        static void DataEntries(Node node, ref int offset)
        {
            if (node.Data != null) { node.Offset = offset; offset = checked(offset + 16); }
            foreach (var child in node.Children.Values) DataEntries(child, ref offset);
        }
        static void Payloads(Node node, ref int offset)
        {
            if (node.Data != null) { offset = Align(offset); node.PayloadOffset = offset; offset = checked(offset + node.Data.Length); }
            foreach (var child in node.Children.Values) Payloads(child, ref offset);
        }
        static void Write(Node node, BinaryWriter writer, int rva)
        {
            writer.BaseStream.Position = node.Offset;
            if (node.Data != null)
            {
                writer.Write(checked((uint)(rva + node.PayloadOffset))); writer.Write((uint)node.Data.Length);
                writer.Write(0u); writer.Write(0u);
                writer.BaseStream.Position = node.PayloadOffset; writer.Write(node.Data);
                return;
            }
            int named = 0;
            foreach (var key in node.Children.Keys) if (key.Name != null) named++;
            if (named > ushort.MaxValue || node.Children.Count - named > ushort.MaxValue)
                throw new InvalidDataException("Too many native resource entries.");
            writer.Write(0u); writer.Write(0u); writer.Write(0u);
            writer.Write((ushort)named); writer.Write((ushort)(node.Children.Count - named));
            foreach (var item in node.Children)
            {
                writer.Write(item.Key.Name == null ? (uint)item.Key.Id : 0x80000000u | (uint)item.Value.NameOffset);
                writer.Write((uint)item.Value.Offset | (item.Value.Data == null ? 0x80000000u : 0));
            }
            foreach (var item in node.Children)
            {
                if (item.Key.Name != null)
                {
                    writer.BaseStream.Position = item.Value.NameOffset;
                    writer.Write((ushort)item.Key.Name.Length);
                    foreach (char c in item.Key.Name) writer.Write((ushort)c);
                }
                Write(item.Value, writer, rva);
            }
        }
        protected override void Serialize(BlobBuilder builder, SectionLocation location)
        {
            int offset = 0;
            Layout(root, ref offset); Names(root, ref offset);
            offset = Align(offset); DataEntries(root, ref offset); Payloads(root, ref offset);
            var bytes = new byte[offset];
            using (var stream = new MemoryStream(bytes, true))
            using (var writer = new BinaryWriter(stream)) Write(root, writer, location.RelativeVirtualAddress);
            builder.WriteBytes(bytes);
        }
    }
#endif

}
