using System;
using System.IO;
using System.Reflection;

namespace Nemerle.Platform
{
    public sealed partial class ClrEmission
    {
        private byte[] signingBlob;
        public bool HasSigningKey { get { return signingBlob != null; } }

        public void ConfigureSigning(AssemblyName assembly, string path)
        {
            var key = File.ReadAllBytes(path);
#if MODERN_CLR
            assembly.SetPublicKey(ReadPublicKey(path));
#else
            assembly.KeyPair = new StrongNameKeyPair(key);
#endif
            signingBlob = key;
        }

        public static byte[] ReadPublicKey(string path)
        {
            var key = File.ReadAllBytes(path);
            // CAPI RSA private-key blob -> strong-name public-key blob. Keep key
            // handling here; the compiler never constructs StrongNameKeyPair.
            if (key.Length < 20 || key[0] != 7 || BitConverter.ToUInt32(key, 8) != 0x32415352)
                throw new ArgumentException("Expected a CAPI RSA private-key blob in signing key file: " + path);
            int modulusBytes = checked((int)BitConverter.ToUInt32(key, 12) / 8);
            if (modulusBytes < 64 || key.Length < 20 + modulusBytes)
                throw new ArgumentException("Invalid RSA signing key: " + path);
            var publicKey = new byte[12 + 20 + modulusBytes];
            Array.Copy(BitConverter.GetBytes(0x2400U), 0, publicKey, 0, 4);
            Array.Copy(BitConverter.GetBytes(0x8004U), 0, publicKey, 4, 4);
            Array.Copy(BitConverter.GetBytes((uint)(20 + modulusBytes)), 0, publicKey, 8, 4);
            Array.Copy(key, 0, publicKey, 12, 20 + modulusBytes);
            publicKey[12] = 6;
            Array.Copy(BitConverter.GetBytes(0x31415352U), 0, publicKey, 20, 4);
            return publicKey;
        }

        public void CompleteAssembly(string path, AssemblyName name)
        {
#if MODERN_CLR
            CompleteSavedMetadataCore(path, null, signingBlob);
#else
            CompleteSavedMetadataCore(path, name.KeyPair, null);
#endif
        }
    }
}
