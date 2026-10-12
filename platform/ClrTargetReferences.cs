using System;
using System.Collections.Generic;
using System.IO;
using Mono.Cecil;

namespace Nemerle.Platform
{
    public sealed partial class ClrEmission
    {
        public string TargetReferenceDirectory { get; set; }

        // Runtime reflection describes implementation assemblies. Public DLLs
        // must refer to the target's contracts so ordinary SDK consumers work.
        // The caller supplies contracts; this code never searches an SDK layout.
        private void BindTargetContracts(ModuleDefinition output)
        {
            if (TargetReferenceDirectory == null) return;
            string root = Path.GetFullPath(TargetReferenceDirectory);
            string runtime = Path.Combine(root, "System.Runtime.dll");
            if (!File.Exists(runtime)) throw new ArgumentException("Target references must include System.Runtime.dll: " + root);
            if (System.Reflection.AssemblyName.GetAssemblyName(runtime).Version.Major != typeof(object).Assembly.GetName().Version.Major)
                throw new NotSupportedException("This backend currently requires target references matching the host runtime major version.");
            var contracts = new Dictionary<string, AssemblyNameReference>(StringComparer.Ordinal);
            foreach (var path in Directory.GetFiles(root, "*.dll"))
            using (var definition = AssemblyDefinition.ReadAssembly(path))
            {
                var name = definition.Name;
                var reference = new AssemblyNameReference(name.Name, name.Version) {
                    PublicKeyToken = name.PublicKeyToken, Culture = name.Culture
                };
                foreach (var type in definition.MainModule.Types) IndexContract(type, reference, contracts);
            }
            var imported = new Dictionary<string, AssemblyNameReference>(StringComparer.Ordinal);
            foreach (var reference in output.AssemblyReferences) imported[reference.FullName] = reference;
            foreach (var type in output.GetTypeReferences())
            {
                var owner = type;
                while (owner.DeclaringType != null) owner = owner.DeclaringType;
                var implementation = owner.Scope as AssemblyNameReference;
                if (implementation == null || !implementation.Name.StartsWith("System.Private.", StringComparison.Ordinal)) continue;
                AssemblyNameReference contract;
                if (!contracts.TryGetValue(owner.FullName, out contract))
                    throw new NotSupportedException("Type is absent from target public contracts: " + owner.FullName);
                AssemblyNameReference scope;
                if (!imported.TryGetValue(contract.FullName, out scope))
                {
                    scope = contract; output.AssemblyReferences.Add(scope); imported.Add(scope.FullName, scope);
                }
                owner.Scope = scope;
            }
        }
        private static void IndexContract(TypeDefinition type, AssemblyNameReference assembly,
            Dictionary<string, AssemblyNameReference> contracts)
        {
            if (type.IsPublic || type.IsNestedPublic) contracts[type.FullName] = assembly;
            foreach (var nested in type.NestedTypes) IndexContract(nested, assembly, contracts);
        }
    }
}
