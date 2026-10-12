using System;
using System.IO;
using System.Reflection;
using System.Reflection.Emit;
using System.ComponentModel;
using Nemerle.Platform;
#if MODERN_CLR
using System.Reflection.Metadata;
using System.Reflection.PortableExecutable;
using System.Linq;
#endif

[TypeConverter(typeof(ResourcePayloadConverter))]
public class ResourcePayload { public byte[] Bytes; }
public class ResourcePayloadConverter : TypeConverter
{
    public override bool CanConvertFrom(ITypeDescriptorContext context, Type type)
    { return type == typeof(byte[]) || base.CanConvertFrom(context, type); }
    public override object ConvertFrom(ITypeDescriptorContext context, System.Globalization.CultureInfo culture, object value)
    { return value is byte[] ? new ResourcePayload { Bytes = (byte[])value } : base.ConvertFrom(context, culture, value); }
}

class AssemblySessionChecks
{
    static void Check(bool condition, string message)
    {
        if (!condition) throw new Exception(message);
    }
    static MethodBuilder Emit(ModuleBuilder module)
    {
        var type = module.DefineType("Program", TypeAttributes.Public);
        var method = type.DefineMethod("Main", MethodAttributes.Public | MethodAttributes.Static,
            typeof(int), Type.EmptyTypes);
        var il = method.GetILGenerator(); il.Emit(OpCodes.Ldc_I4, 42); il.Emit(OpCodes.Ret);
        type.CreateType();
        return method;
    }
#if MODERN_CLR
    static void NativeEntry(BinaryWriter writer, object type, object name, ushort language, byte[] data)
    {
        long start = writer.BaseStream.Position;
        writer.Write((uint)data.Length); writer.Write(0u);
        foreach (var key in new[] { type, name })
        {
            if (key is string) { foreach (char c in (string)key) writer.Write((ushort)c); writer.Write((ushort)0); }
            else { writer.Write((ushort)0xffff); writer.Write(Convert.ToUInt16(key)); }
        }
        while (writer.BaseStream.Position % 4 != 0) writer.Write((byte)0);
        writer.Write(0u); writer.Write((ushort)0); writer.Write(language); writer.Write(0u); writer.Write(0u);
        long end = writer.BaseStream.Position;
        writer.BaseStream.Position = start + 4; writer.Write((uint)(end - start)); writer.BaseStream.Position = end;
        writer.Write(data); while (writer.BaseStream.Position % 4 != 0) writer.Write((byte)0);
    }
    static int NativeChild(byte[] section, int offset, object key)
    {
        int count = BitConverter.ToUInt16(section, offset + 12) + BitConverter.ToUInt16(section, offset + 14);
        for (int i = 0; i < count; i++)
        {
            uint name = BitConverter.ToUInt32(section, offset + 16 + i * 8);
            bool matches;
            if ((name & 0x80000000u) != 0)
            {
                int start = (int)(name & 0x7fffffffu);
                string text = System.Text.Encoding.Unicode.GetString(section, start + 2, BitConverter.ToUInt16(section, start) * 2);
                matches = key is string && text == (string)key;
            }
            else matches = !(key is string) && name == Convert.ToUInt32(key);
            if (matches) return (int)(BitConverter.ToUInt32(section, offset + 20 + i * 8) & 0x7fffffffu);
        }
        throw new Exception("Missing native resource key: " + key);
    }
#endif
    static void Main(string[] args)
    {
        var path = Path.Combine(args[0], "SessionOutput.exe");
        var resourcePath = Path.Combine(args[0], "session-resource.bin");
        File.WriteAllBytes(resourcePath, new byte[] { 3, 7, 11 });
        var persisted = new ClrAssemblySession(new AssemblyName("SessionOutput"), path, false, false);
        persisted.SetEntryPoint(Emit(persisted.Module), false);
        persisted.AddEmbeddedResource("sample", resourcePath);
        persisted.Save(PortableExecutableKinds.ILOnly, ImageFileMachine.I386);
        var loaded = Assembly.Load(File.ReadAllBytes(path));
        Check(loaded.EntryPoint != null && (int)loaded.EntryPoint.Invoke(null, null) == 42,
            "Saved entry point must execute");
        using (var resource = loaded.GetManifestResourceStream("sample"))
            Check(resource != null && resource.ReadByte() == 3 && resource.ReadByte() == 7 && resource.ReadByte() == 11,
                "Embedded resource contents must survive");
        var live = new ClrAssemblySession(new AssemblyName("LiveSession"), path, true, false);
        Emit(live.Module);
        Check((int)live.ExecutableAssembly.GetType("Program").GetMethod("Main").Invoke(null, null) == 42,
            "Runnable session must execute immediately");
        bool refused = false;
        try { live.Save(PortableExecutableKinds.ILOnly, ImageFileMachine.I386); }
        catch (InvalidOperationException) { refused = true; }
        Check(refused, "Runnable session cannot masquerade as a persisted session");
        var signedName = new AssemblyName("SignedSession");
        var signer = new ClrEmission { PersistedOutput = true };
        signer.ConfigureSigning(signedName, args[1]);
        var signedPath = Path.Combine(args[0], "SignedSession.dll");
        var signed = new ClrAssemblySession(signedName, signedPath, false, false);
        Emit(signed.Module);
        signed.Save(PortableExecutableKinds.ILOnly, ImageFileMachine.I386);
        signer.CompleteAssembly(signedPath, signedName);
        Check(AssemblyName.GetAssemblyName(signedPath).GetPublicKey().Length > 0,
            "Signing must preserve the public key");
        using (var reader = new ClrResXReader(new StringReader("<root><data name='text'><value>hello</value></data><data name='count' type='System.Int32'><value>7</value></data><data name='bytes' type='System.Byte[]'><value>AwcL</value></data></root>")))
        {
            var values = new System.Collections.Hashtable();
            foreach (System.Collections.DictionaryEntry item in reader) values.Add(item.Key, item.Value);
            Check((string)values["text"] == "hello" && (int)values["count"] == 7 && ((byte[])values["bytes"])[2] == 11,
                "Portable resource values must keep their types and contents");
        }
        using (var reader = new ClrResXReader(new StringReader("<root><data name='guid' type='System.Guid'><value>00112233-4455-6677-8899-aabbccddeeff</value></data><data name='span' type='System.TimeSpan'><value>01:02:03</value></data><data name='nil' type='System.Resources.ResXNullRef, System.Windows.Forms'><value /></data></root>")))
        {
            var values = new System.Collections.Hashtable();
            foreach (System.Collections.DictionaryEntry item in reader) values.Add(item.Key, item.Value);
            Check((Guid)values["guid"] == new Guid("00112233-4455-6677-8899-aabbccddeeff") && (TimeSpan)values["span"] == new TimeSpan(1, 2, 3) && values.ContainsKey("nil") && values["nil"] == null,
                "Portable resources must support invariant converters and explicit nulls");
        }
        var encodedPath = Path.Combine(args[0], "encoded.txt");
        File.WriteAllText(encodedPath, "café", System.Text.Encoding.Unicode);
        using (var reader = new ClrResXReader(new StringReader("<root><data name='file' type='System.Resources.ResXFileRef, System.Windows.Forms'><value>encoded.txt;System.String;utf-16</value></data></root>"), args[0]))
        {
            foreach (System.Collections.DictionaryEntry item in reader) Check((string)item.Value == "café", "File resources must resolve against base directory with declared encoding");
        }
        using (var reader = new ClrResXReader(new StringReader("<root><data name='converted' type='" + typeof(ResourcePayload).AssemblyQualifiedName + "' mimetype='application/x-microsoft.net.object.bytearray.base64'><value>AwcL</value></data></root>")))
        {
            foreach (System.Collections.DictionaryEntry item in reader) Check(((ResourcePayload)item.Value).Bytes[2] == 11,
                "Byte-array MIME resources must use the supplied type converter");
        }
        bool unsupported = false;
        try { new ClrResXReader(new StringReader("<root><data name='binary' mimetype='application/x-microsoft.net.object.binary.base64'><value>AA==</value></data></root>")); }
        catch (NotSupportedException) { unsupported = true; }
        Check(unsupported, "Unsupported binary object resources must produce a diagnostic");
#if MODERN_CLR
        var factoryName = new AssemblyName("GenericConstructorOutput");
        var factoryPath = Path.Combine(args[0], factoryName.Name + ".dll");
        var factorySession = new ClrAssemblySession(factoryName, factoryPath, false, false);
        var factoryEmission = new ClrEmission { PersistedOutput = true };
        var factoryOwner = factorySession.Module.DefineType("Factory`1", TypeAttributes.Public);
        var factoryParameter = factoryOwner.DefineGenericParameters("T")[0];
        var pairDefinition = typeof(System.Collections.Generic.KeyValuePair<,>);
        var pairConstructor = pairDefinition.GetConstructors()[0];
        var pairType = pairDefinition.MakeGenericType(factoryParameter.MakeArrayType(), typeof(bool));
        var factoryCall = factoryEmission.GetConstructorFactory(factorySession.Module, pairType, pairConstructor);
        Check(factoryCall != null, "Generic array constructor needs a persisted factory");
        var factoryRun = factoryOwner.DefineMethod("Run", MethodAttributes.Public | MethodAttributes.Static,
            pairType, new[] { factoryParameter.MakeArrayType() });
        var factoryIl = factoryRun.GetILGenerator();
        factoryIl.Emit(OpCodes.Ldarg_0); factoryIl.Emit(OpCodes.Ldc_I4_1);
        factoryIl.Emit(OpCodes.Call, factoryCall); factoryIl.Emit(OpCodes.Ret);
        factoryOwner.CreateType();
        factorySession.Save(PortableExecutableKinds.ILOnly, ImageFileMachine.I386);
        factoryEmission.CompleteAssembly(factoryPath, factoryName);
        var factoryLoaded = Assembly.Load(File.ReadAllBytes(factoryPath));
        var inputArray = new[] { 42 };
        var pairResult = (System.Collections.Generic.KeyValuePair<int[], bool>)factoryLoaded.GetType("Factory`1")
            .MakeGenericType(typeof(int)).GetMethod("Run").Invoke(null, new object[] { inputArray });
        Check(ReferenceEquals(pairResult.Key, inputArray) && pairResult.Value,
            "Generic array constructor factory must preserve operands and execute");
        Check(factoryLoaded.GetTypes().Count(t => t.Name.StartsWith("<NemerleConstructorFactory>")) == 1,
            "Constructor factory is an internal implementation detail");
        var debugPath = Path.Combine(args[0], "DebugSession.dll");
        var debugName = new AssemblyName("DebugSession");
        var debugSigner = new ClrEmission { PersistedOutput = true };
        debugSigner.ConfigureSigning(debugName, args[1]);
        var debug = new ClrAssemblySession(debugName, debugPath, false, true);
        var sourcePath = Path.Combine(args[0], "debug.n");
        File.WriteAllText(sourcePath, "Run() : int { 42 }");
        var doc = debug.Module.DefineDocument(sourcePath, Guid.Empty);
        var debugType = debug.Module.DefineType("DebugProgram", TypeAttributes.Public);
        var debugMethod = debugType.DefineMethod("Run", MethodAttributes.Public | MethodAttributes.Static, typeof(int), Type.EmptyTypes);
        var debugIL = debugMethod.GetILGenerator();
        debugIL.BeginScope();
        var local = debugIL.DeclareLocal(typeof(int));
        local.SetLocalSymInfo("answer");
        debugIL.MarkSequencePoint(doc, 1, 1, 1, 18);
        debugIL.Emit(OpCodes.Ldc_I4, 42); debugIL.Emit(OpCodes.Stloc, local);
        debugIL.Emit(OpCodes.Ldloc, local); debugIL.Emit(OpCodes.Ret);
        debugIL.EndScope(); debugType.CreateType();
        var nativePath = Path.Combine(args[0], "native.res");
        using (var writer = new BinaryWriter(File.Create(nativePath)))
        {
            NativeEntry(writer, 0, 0, 0, new byte[0]);
            NativeEntry(writer, 10, 77, 1033, new byte[] { 3, 7, 11 });
            NativeEntry(writer, "CUSTOM", "widget", 0, new byte[] { 99 });
        }
        debug.AddUnmanagedResource(nativePath);
        debug.Save(PortableExecutableKinds.ILOnly, ImageFileMachine.I386);
        debugSigner.CompleteAssembly(debugPath, debugName);
        using (var pdbStream = File.OpenRead(Path.ChangeExtension(debugPath, ".pdb")))
        using (var provider = MetadataReaderProvider.FromPortablePdbStream(pdbStream))
        {
            var reader = provider.GetMetadataReader();
            Check(reader.Documents.Count == 1 && reader.GetString(reader.GetDocument(reader.Documents.First()).Name) == sourcePath,
                "Portable PDB must retain the source document after signing");
            Check(reader.MethodDebugInformation.Any(h => reader.GetMethodDebugInformation(h).GetSequencePoints().Any(p => p.StartLine == 1)),
                "Portable PDB must retain source sequence points after signing");
            Check(reader.LocalVariables.Any(h => reader.GetString(reader.GetLocalVariable(h).Name) == "answer"),
                "Portable PDB must retain named locals after signing");
        }
        using (var peStream = File.OpenRead(debugPath))
        using (var pe = new PEReader(peStream))
        {
            var codeView = pe.ReadCodeViewDebugDirectoryData(pe.ReadDebugDirectory().First(e => e.Type == DebugDirectoryEntryType.CodeView));
            Check(Path.GetFileName(codeView.Path) == "DebugSession.pdb", "PE must reference the final PDB filename: " + codeView.Path);
            var directory = pe.PEHeaders.PEHeader.ResourceTableDirectory;
            Check(directory.Size > 0, "PE must contain native resources after signing");
            var section = pe.GetSectionData(directory.RelativeVirtualAddress).GetContent().ToArray();
            int leaf = NativeChild(section, NativeChild(section, NativeChild(section, 0, 10), 77), 1033);
            int rva = BitConverter.ToInt32(section, leaf);
            Check(BitConverter.ToInt32(section, leaf + 4) == 3 && pe.GetSectionData(rva).GetContent(0, 3).SequenceEqual(new byte[] { 3, 7, 11 }),
                "Numeric native resource identifiers, language and payload must survive signing");
            leaf = NativeChild(section, NativeChild(section, NativeChild(section, 0, "CUSTOM"), "widget"), 0);
            Check(pe.GetSectionData(BitConverter.ToInt32(section, leaf)).GetContent(0, 1)[0] == 99,
                "Named native resources must survive signing");
        }
        bool linkedRefused = false;
        try { debug.AddLinkedResource("linked", resourcePath); } catch (NotSupportedException) { linkedRefused = true; }
        Check(linkedRefused, "Unusable CoreCLR external linked resources must produce an explicit error");
        bool malformed = false;
        File.WriteAllBytes(nativePath, new byte[] { 1, 2, 3 });
        var invalid = new ClrAssemblySession(new AssemblyName("InvalidNative"), Path.Combine(args[0], "invalid.dll"), false, false);
        try { invalid.AddUnmanagedResource(nativePath); } catch (InvalidDataException) { malformed = true; }
        Check(malformed, "Malformed native resource input must be rejected");
        Console.WriteLine("PASS: portable PDB documents, sequence points, locals, signing, native resources and linked-resource diagnostic");
#endif
        Console.WriteLine("PASS: signing and portable resource values");
        Console.WriteLine("PASS: assembly sessions, entry points, embedded resources and live execution");
    }
}
