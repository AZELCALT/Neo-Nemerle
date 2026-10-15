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
        // ---- Continuation section (experimental): raw bytes in .nemir, added to a finished image. ----

        /// The raw .nemir payload of an image file, or null when it has none.
        public static byte[] ReadBytes(string path)
        {
            return ReadBytes(File.ReadAllBytes(path));
        }

        /// The raw .nemir payload of an image in memory, or null when it has none.
        public static byte[] ReadBytes(byte[] image)
        {
#if MODERN_CLR
            try
            {
                using (var pe = new PEReader(new MemoryStream(image, false)))
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
                    if (s.VirtualSize <= 0 || s.SizeOfRawData < s.VirtualSize || (long)s.PointerToRawData + s.VirtualSize > image.Length)
                        throw new InvalidDataException("Truncated or invalid .nemir section.");
                    var bytes = new byte[s.VirtualSize];
                    Array.Copy(image, s.PointerToRawData, bytes, 0, s.VirtualSize);
                    return bytes;
                }
            }
            catch (BadImageFormatException e) { throw new InvalidDataException("Invalid PE image.", e); }
#else
            throw new NotSupportedException("Compiler sections require the CoreCLR backend.");
#endif
        }

        /// Adds a .nemir section to a finished image file (after any metadata rewrite, which would drop it) and, when
        /// a key is given, strong-name signs the result again. The header must have room for one more section header.
        public static void AppendToFile(string path, byte[] data, byte[] signingKey)
        {
            var image = File.ReadAllBytes(path);
            File.WriteAllBytes(path, Append(image, data, signingKey));
        }

        public static byte[] Append(byte[] image, byte[] data, byte[] signingKey)
        {
            if (data == null || data.Length == 0) throw new ArgumentException("empty compiler section");
            int pe = BitConverter.ToInt32(image, 0x3c);
            if (BitConverter.ToUInt32(image, pe) != 0x00004550) throw new InvalidDataException("not a PE image");
            int coff = pe + 4;
            int sections = BitConverter.ToUInt16(image, coff + 2);
            int optionalSize = BitConverter.ToUInt16(image, coff + 16);
            int opt = coff + 20;
            bool pe32Plus = BitConverter.ToUInt16(image, opt) == 0x20b;
            uint sectionAlign = BitConverter.ToUInt32(image, opt + 32), fileAlign = BitConverter.ToUInt32(image, opt + 36);
            int table = opt + optionalSize;
            int firstRaw = int.MaxValue; uint lastEnd = 0;
            for (int i = 0; i < sections; i++)
            {
                int h = table + 40 * i;
                if (System.Text.Encoding.ASCII.GetString(image, h, 8).TrimEnd('\0') == Name) throw new InvalidDataException("Image already has a .nemir section.");
                int raw = BitConverter.ToInt32(image, h + 20);
                if (raw > 0) firstRaw = Math.Min(firstRaw, raw);
                uint end = BitConverter.ToUInt32(image, h + 12) + Math.Max(BitConverter.ToUInt32(image, h + 8), BitConverter.ToUInt32(image, h + 16));
                lastEnd = Math.Max(lastEnd, end);
            }
            int header = table + 40 * sections;
            if (header + 40 > firstRaw) throw new NotSupportedException("No room for a .nemir section header in this image (experimental limit).");
            Func<long, uint, long> align = (v, a) => (v + a - 1) / a * a;
            uint va = (uint)align(lastEnd, sectionAlign);
            long rawAt = align(image.Length, fileAlign);
            uint rawSize = (uint)align(data.Length, fileAlign);
            var result = new byte[rawAt + rawSize];
            Array.Copy(image, result, image.Length);
            Array.Copy(data, 0, result, rawAt, data.Length);
            var name = System.Text.Encoding.ASCII.GetBytes(Name);
            Array.Copy(name, 0, result, header, name.Length);
            BitConverter.GetBytes((uint)data.Length).CopyTo(result, header + 8);   // VirtualSize
            BitConverter.GetBytes(va).CopyTo(result, header + 12);                 // VirtualAddress
            BitConverter.GetBytes(rawSize).CopyTo(result, header + 16);            // SizeOfRawData
            BitConverter.GetBytes((uint)rawAt).CopyTo(result, header + 20);        // PointerToRawData
            BitConverter.GetBytes(0x40000040u).CopyTo(result, header + 36);        // initialized data, readable
            BitConverter.GetBytes((ushort)(sections + 1)).CopyTo(result, coff + 2);
            BitConverter.GetBytes(BitConverter.ToUInt32(result, opt + 8) + rawSize).CopyTo(result, opt + 8); // SizeOfInitializedData
            BitConverter.GetBytes((uint)align(va + (uint)data.Length, sectionAlign)).CopyTo(result, opt + 56); // SizeOfImage
            BitConverter.GetBytes(0u).CopyTo(result, opt + 64);                    // CheckSum: not required for managed images
            if (signingKey != null) StrongNameSign(result, pe32Plus, opt, table, sections + 1, signingKey);
            return result;
        }

        static int RvaToOffset(byte[] image, int table, int sections, uint rva)
        {
            for (int i = 0; i < sections; i++)
            {
                int h = table + 40 * i;
                uint va = BitConverter.ToUInt32(image, h + 12), size = Math.Max(BitConverter.ToUInt32(image, h + 8), BitConverter.ToUInt32(image, h + 16));
                if (rva >= va && rva < va + size) return (int)(rva - va + BitConverter.ToUInt32(image, h + 20));
            }
            throw new InvalidDataException("RVA outside every section");
        }

        /// SHA-1 over the headers up to the end of the section table, then every section byte from the first section
        /// to the end of the file except the signature blob; the RSA signature is stored little-endian in the CLI
        /// header's strong-name blob. This is the region Mono.Cecil signs and sn/CoreCLR accept.
        static void StrongNameSign(byte[] image, bool pe32Plus, int opt, int table, int sections, byte[] key)
        {
#if MODERN_CLR
            int directories = opt + (pe32Plus ? 112 : 96);
            uint cliRva = BitConverter.ToUInt32(image, directories + 8 * 14);
            if (cliRva == 0) throw new InvalidDataException("not a managed image");
            int cli = RvaToOffset(image, table, sections, cliRva);
            uint sigRva = BitConverter.ToUInt32(image, cli + 32), sigSize = BitConverter.ToUInt32(image, cli + 36);
            if (sigRva == 0 || sigSize == 0) throw new InvalidDataException("image has no strong-name signature slot");
            int sig = RvaToOffset(image, table, sections, sigRva);
            int headerEnd = table + 40 * sections, firstRaw = int.MaxValue;
            for (int i = 0; i < sections; i++)
            {
                int raw = BitConverter.ToInt32(image, table + 40 * i + 20);
                if (raw > 0) firstRaw = Math.Min(firstRaw, raw);
            }
            using (var hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA1))
            {
                hash.AppendData(image, 0, headerEnd);
                hash.AppendData(image, firstRaw, sig - firstRaw);
                hash.AppendData(image, sig + (int)sigSize, image.Length - sig - (int)sigSize);
                using (var rsa = new RSACryptoServiceProvider())
                {
                    rsa.ImportCspBlob(key);
                    var signature = rsa.SignHash(hash.GetHashAndReset(), "SHA1");
                    if (signature.Length != sigSize) throw new InvalidDataException("signature size does not match the image's slot");
                    Array.Reverse(signature);
                    Array.Copy(signature, 0, image, sig, signature.Length);
                }
            }
#else
            throw new NotSupportedException();
#endif
        }

        public static byte[] Compress(byte[] data)
        {
            var output = new MemoryStream();
            using (var deflate = new System.IO.Compression.DeflateStream(output, System.IO.Compression.CompressionLevel.Optimal, true))
                deflate.Write(data, 0, data.Length);
            return output.ToArray();
        }

        public static byte[] Decompress(byte[] data)
        {
            var output = new MemoryStream();
            using (var deflate = new System.IO.Compression.DeflateStream(new MemoryStream(data, false), System.IO.Compression.CompressionMode.Decompress))
                deflate.CopyTo(output);
            return output.ToArray();
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
