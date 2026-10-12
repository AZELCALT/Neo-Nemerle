using System;
using System.IO;
using System.Reflection;
using System.Reflection.Emit;
#if MODERN_CLR
using System.Collections.Immutable;
using System.Reflection.Metadata;
using System.Reflection.Metadata.Ecma335;
using System.Reflection.PortableExecutable;
using System.Text;
using System.Text.Json;
using System.Security.Cryptography;
#endif

namespace Nemerle.Platform
{
    // Transport only. Grammar/block semantics belong to Nemerle.Compiler.
    public static class ClrCompilerSection
    {
        public const string Name = ".nemir";
        public static void WriteArchive(string path, string json, string keyFile, bool debug)
        {
#if MODERN_CLR
            var name = new AssemblyName(Path.GetFileNameWithoutExtension(path));
            var signer = new ClrEmission { PersistedOutput = true };
            if (!string.IsNullOrEmpty(keyFile)) signer.ConfigureSigning(name, keyFile);
            var session = new ClrAssemblySession(name, path, false, debug);
            session.SetCompilerSection(new UTF8Encoding(false, true).GetBytes(json),
                string.IsNullOrEmpty(keyFile) ? null : File.ReadAllBytes(keyFile));
            session.Save(PortableExecutableKinds.ILOnly, ImageFileMachine.I386);
            // Sign the final PE directly: metadata-rewrite tools may discard custom sections.
#else
            throw new NotSupportedException("Experimental compiler sections require the CoreCLR backend.");
#endif
        }
        // null means absent; malformed PE/section data throws InvalidDataException.
        public static string Read(string path)
        {
#if MODERN_CLR
            try
            {
                using (var stream = File.OpenRead(path))
                using (var pe = new PEReader(stream))
                {
                    SectionHeader? found = null;
                    foreach (var section in pe.PEHeaders.SectionHeaders)
                        if (section.Name == Name)
                        {
                            if (found.HasValue) throw new InvalidDataException("Duplicate .nemir section.");
                            found = section;
                        }
                    if (!found.HasValue) return null;
                    var s = found.Value;
                    if (s.VirtualSize <= 0 || s.SizeOfRawData < s.VirtualSize || s.PointerToRawData < 0 ||
                        (long)s.PointerToRawData + s.SizeOfRawData > stream.Length)
                        throw new InvalidDataException("Truncated or invalid .nemir section.");
                    stream.Position = s.PointerToRawData;
                    var bytes = new byte[s.VirtualSize];
                    stream.ReadExactly(bytes);
                    return new UTF8Encoding(false, true).GetString(bytes);
                }
            }
            catch (BadImageFormatException e) { throw new InvalidDataException("Invalid PE archive.", e); }
            catch (DecoderFallbackException e) { throw new InvalidDataException("Invalid UTF-8 compiler archive.", e); }
#else
            throw new NotSupportedException("Experimental compiler sections require the CoreCLR backend.");
#endif
        }
#if MODERN_CLR
        internal static void Sign(ManagedPEBuilder image, BlobBuilder blob, byte[] key)
        {
            using (var rsa = new RSACryptoServiceProvider())
            {
                rsa.ImportCspBlob(key);
                image.Sign(blob, content =>
                {
                    using (var hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA1))
                    {
                        foreach (var part in content)
                        {
                            var bytes = part.GetBytes();
                            hash.AppendData(bytes.Array, bytes.Offset, bytes.Count);
                        }
                        var signature = rsa.SignHash(hash.GetHashAndReset(), "SHA1");
                        Array.Reverse(signature);
                        return signature;
                    }
                });
            }
        }
        static JsonElement Property(string json, string name)
        {
            using (var doc = JsonDocument.Parse(json))
            {
                if (doc.RootElement.ValueKind != JsonValueKind.Object) throw new InvalidDataException("Expected archive object.");
                var names = new System.Collections.Generic.HashSet<string>(StringComparer.Ordinal);
                foreach (var property in doc.RootElement.EnumerateObject())
                    if (!names.Add(property.Name)) throw new InvalidDataException("Duplicate archive field.");
                if (!doc.RootElement.TryGetProperty(name, out var value)) throw new InvalidDataException("Missing archive field: " + name);
                return value.Clone();
            }
        }
#endif
        public static string JsonString(string json, string name)
        {
#if MODERN_CLR
            var value = Property(json, name);
            if (value.ValueKind != JsonValueKind.String) throw new InvalidDataException("Expected string: " + name);
            return value.GetString();
#else
            throw new NotSupportedException();
#endif
        }
        public static int JsonInt(string json, string name)
        {
#if MODERN_CLR
            var value = Property(json, name);
            if (!value.TryGetInt32(out var number)) throw new InvalidDataException("Expected integer: " + name);
            return number;
#else
            throw new NotSupportedException();
#endif
        }
        public static string[] JsonArray(string json, string name, bool strings)
        {
#if MODERN_CLR
            var value = Property(json, name);
            if (value.ValueKind != JsonValueKind.Array) throw new InvalidDataException("Expected array: " + name);
            var result = new System.Collections.Generic.List<string>();
            foreach (var item in value.EnumerateArray())
            {
                if (strings && item.ValueKind != JsonValueKind.String) throw new InvalidDataException("Expected string array: " + name);
                result.Add(strings ? item.GetString() : item.GetRawText());
            }
            return result.ToArray();
#else
            throw new NotSupportedException();
#endif
        }
    }
#if MODERN_CLR
    internal sealed class CompilerSectionPEBuilder : ManagedPEBuilder
    {
        readonly byte[] compilerData;
        internal CompilerSectionPEBuilder(PEHeaderBuilder header, MetadataRootBuilder metadata,
            BlobBuilder il, BlobBuilder fields, BlobBuilder resources, MethodDefinitionHandle entry,
            CorFlags flags, DebugDirectoryBuilder debug, ResourceSectionBuilder native, byte[] compilerData, int signatureSize)
            : base(header, metadata, il, mappedFieldData: fields, managedResources: resources,
                entryPoint: entry, flags: flags, debugDirectoryBuilder: debug, nativeResources: native,
                strongNameSignatureSize: signatureSize)
        { this.compilerData = compilerData; }
        protected override ImmutableArray<Section> CreateSections()
        {
            var sections = base.CreateSections();
            return compilerData == null ? sections : sections.Add(new Section(ClrCompilerSection.Name,
                SectionCharacteristics.ContainsInitializedData | SectionCharacteristics.MemRead));
        }
        protected override BlobBuilder SerializeSection(string name, SectionLocation location)
        {
            if (name != ClrCompilerSection.Name) return base.SerializeSection(name, location);
            var data = new BlobBuilder(); data.WriteBytes(compilerData); return data;
        }
    }
#endif
}
