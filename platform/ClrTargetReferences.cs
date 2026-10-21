using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Mono.Cecil;
using Mono.Cecil.Cil;

namespace Nemerle.Platform
{
    public sealed partial class ClrEmission
    {
        public string TargetReferenceDirectory { get; set; }

        /// The other assemblies the output is compiled with (packages, by path): a framework type the target's reference
        /// assemblies do not define may be one of theirs (a polyfill, as ValueTask in System.Threading.Tasks.Extensions).
        public IEnumerable<string> TargetLibraries { get; set; }

        internal static IEnumerable<string> ExistingLibraries(IEnumerable<string> libraries)
        {
            if (libraries == null) yield break;
            foreach (var library in libraries)
            {
                string path;
                try { path = Path.GetFullPath(library); } catch (Exception) { continue; }
                if (File.Exists(path)) yield return path;
            }
        }

        /// The target framework; null: the one the target references are for (or the host's without them).
        public ClrTarget Target { get; set; }

        /// The target is not the host's .NET.
        public bool OtherTarget { get { return TargetReferenceDirectory != null && !EffectiveTarget.SameAs(ClrTarget.Host); } }

        public ClrTarget EffectiveTarget
        {
            get { return Target ?? (TargetReferenceDirectory != null ? ClrTarget.FromReferences(TargetReferenceDirectory) : ClrTarget.Host); }
        }

        // Runtime reflection describes the host's implementation assemblies. The output must name the target's public
        // assemblies (its reference assemblies) instead, so every type the output uses from the host framework is
        // moved to the target assembly that defines it publicly; for a target other than the host, every member it
        // uses must exist there too, since the compiler typed against the host's (larger) API.
        private void BindTargetContracts(ModuleDefinition output)
        {
            if (TargetReferenceDirectory == null) return;
            string root = Path.GetFullPath(TargetReferenceDirectory);
            var target = EffectiveTarget;
            var references = ClrTarget.FromReferences(root);
            if (!references.SameAs(target) && !(references.Family == "netframework" && target.Family == "netframework"))
                throw new NotSupportedException("the target references in " + root + " are for " + references + ", not " + target);
            if (target.Family == "netcore" && target.Version.Major > ClrTarget.Host.Version.Major)
                throw new NotSupportedException("this compiler runs on " + ClrTarget.Host + " and cannot target the newer " + target);
            // the target's public types, by full name
            var contracts = new Dictionary<string, AssemblyNameReference>(StringComparer.Ordinal);
            var definitions = new Dictionary<string, TypeDefinition>(StringComparer.Ordinal);
            var opened = new List<AssemblyDefinition>();
            try
            {
                foreach (var path in Directory.GetFiles(root, "*.dll"))
                {
                    AssemblyDefinition definition;
                    try { definition = AssemblyDefinition.ReadAssembly(path); }
                    catch (Exception) { continue; } // not an assembly (the folder holds other files too)
                    opened.Add(definition);
                    var name = definition.Name;
                    var reference = new AssemblyNameReference(name.Name, name.Version) {
                        PublicKeyToken = name.PublicKeyToken, Culture = name.Culture
                    };
                    foreach (var type in definition.MainModule.Types) IndexContract(type, reference, contracts, definitions);
                }
                // (then the packages': a type the target lacks may be theirs)
                foreach (var path in ExistingLibraries(TargetLibraries))
                {
                    AssemblyDefinition definition;
                    try { definition = AssemblyDefinition.ReadAssembly(path); }
                    catch (Exception) { continue; }
                    opened.Add(definition);
                    var name = definition.Name;
                    var reference = new AssemblyNameReference(name.Name, name.Version) {
                        PublicKeyToken = name.PublicKeyToken, Culture = name.Culture
                    };
                    var found = new Dictionary<string, AssemblyNameReference>(StringComparer.Ordinal);
                    var types = new Dictionary<string, TypeDefinition>(StringComparer.Ordinal);
                    foreach (var type in definition.MainModule.Types) IndexContract(type, reference, found, types);
                    foreach (var pair in found)
                        if (!contracts.ContainsKey(pair.Key)) { contracts[pair.Key] = pair.Value; definitions[pair.Key] = types[pair.Key]; }
                }
                // the host framework's assemblies: the ones runtime reflection names
                var host = new HashSet<string>(Directory.GetFiles(Path.GetDirectoryName(typeof(object).Assembly.Location), "*.dll")
                    .Select(Path.GetFileNameWithoutExtension), StringComparer.Ordinal);
                var imported = new Dictionary<string, AssemblyNameReference>(StringComparer.Ordinal);
                foreach (var reference in output.AssemblyReferences) imported[reference.FullName] = reference;
                var problems = new List<string>();
                // every type reference the module uses, including the ones imported in memory by this pass (method
                // overrides): the original TypeRef table alone misses those
                foreach (var type in UsedTypeReferences(output))
                {
                    var owner = type;
                    while (owner.DeclaringType != null) owner = owner.DeclaringType;
                    var implementation = owner.Scope as AssemblyNameReference;
                    if (implementation == null || !host.Contains(implementation.Name)) continue;
                    AssemblyNameReference contract;
                    if (!contracts.TryGetValue(owner.FullName, out contract))
                    {
                        problems.Add("the type " + owner.FullName + " is not in " + target);
                        continue;
                    }
                    if (contract.FullName == implementation.FullName) continue;
                    AssemblyNameReference scope;
                    if (!imported.TryGetValue(contract.FullName, out scope))
                    {
                        scope = contract; output.AssemblyReferences.Add(scope); imported.Add(scope.FullName, scope);
                    }
                    owner.Scope = scope;
                }
                var targetAssemblies = new HashSet<string>(contracts.Values.Select(c => c.FullName), StringComparer.Ordinal);
                if (!target.SameAs(ClrTarget.Host)) CheckMembers(output, target, targetAssemblies, definitions, problems);
                if (problems.Count > 0) throw new ClrTargetException(target.Name, problems.Distinct().ToList());
                // References to host assemblies that nothing names any more: for another target (the module read up
                // front) they go, so the output names only the target's assemblies; for the host they stay (signatures
                // read lazily point at reference rows by position, and a reference that is not used is never loaded).
                if (!target.SameAs(ClrTarget.Host))
                {
                    var used = new HashSet<string>(StringComparer.Ordinal);
                    foreach (var type in UsedTypeReferences(output))
                    {
                        var owner = type;
                        while (owner.DeclaringType != null) owner = owner.DeclaringType;
                        var scope = owner.Scope as AssemblyNameReference;
                        if (scope != null) used.Add(scope.FullName);
                    }
                    foreach (var reference in output.AssemblyReferences.ToList())
                        if (host.Contains(reference.Name) && !used.Contains(reference.FullName) && !targetAssemblies.Contains(reference.FullName))
                            output.AssemblyReferences.Remove(reference);
                }
            }
            finally { foreach (var d in opened) d.Dispose(); }
        }

        // The type references a module uses, found through everything that can name a type.
        private static List<TypeReference> UsedTypeReferences(ModuleDefinition module)
        {
            var found = new List<TypeReference>();
            var seen = new HashSet<TypeReference>();
            var visitedMembers = new HashSet<MemberReference>();
            Action<TypeReference> type = null;
            Action<MethodReference> method = null;
            Action<FieldReference> field = null;
            Action<Mono.Collections.Generic.Collection<CustomAttribute>> attributes = null;
            type = t =>
            {
                if (t == null || !seen.Add(t)) return;
                var spec = t as TypeSpecification;
                if (spec != null)
                {
                    type(spec.ElementType);
                    var generic = t as GenericInstanceType;
                    if (generic != null) foreach (var a in generic.GenericArguments) type(a);
                    var modified = t as IModifierType;
                    if (modified != null) type(modified.ModifierType);
                    var pointer = t as FunctionPointerType;
                    if (pointer != null) { type(pointer.ReturnType); foreach (var p in pointer.Parameters) type(p.ParameterType); }
                    return;
                }
                if (t is GenericParameter) return;
                if (t.DeclaringType != null) type(t.DeclaringType);
                if (!(t is TypeDefinition)) found.Add(t);
            };
            method = m =>
            {
                if (m == null || !visitedMembers.Add(m)) return;
                type(m.DeclaringType); type(m.ReturnType);
                foreach (var p in m.Parameters) type(p.ParameterType);
                var generic = m as GenericInstanceMethod;
                if (generic != null) { method(generic.ElementMethod); foreach (var a in generic.GenericArguments) type(a); }
            };
            field = f =>
            {
                if (f == null || !visitedMembers.Add(f)) return;
                type(f.DeclaringType); type(f.FieldType);
            };
            attributes = list =>
            {
                foreach (var a in list)
                {
                    method(a.Constructor);
                    foreach (var arg in a.ConstructorArguments) { type(arg.Type); var v = arg.Value as TypeReference; if (v != null) type(v); }
                    foreach (var named in a.Fields.Concat(a.Properties)) { type(named.Argument.Type); var v = named.Argument.Value as TypeReference; if (v != null) type(v); }
                }
            };
            Action<Mono.Collections.Generic.Collection<GenericParameter>> parameters = list =>
            {
                foreach (var g in list) { foreach (var c in g.Constraints) { type(c.ConstraintType); attributes(c.CustomAttributes); } attributes(g.CustomAttributes); }
            };
            attributes(module.Assembly.CustomAttributes);
            attributes(module.CustomAttributes);
            foreach (var t in module.GetTypes())
            {
                type(t.BaseType);
                foreach (var i in t.Interfaces) { type(i.InterfaceType); attributes(i.CustomAttributes); }
                attributes(t.CustomAttributes); parameters(t.GenericParameters);
                foreach (var f in t.Fields) { type(f.FieldType); attributes(f.CustomAttributes); }
                foreach (var p in t.Properties) { type(p.PropertyType); attributes(p.CustomAttributes); foreach (var x in p.Parameters) type(x.ParameterType); }
                foreach (var e in t.Events) { type(e.EventType); attributes(e.CustomAttributes); }
                foreach (var m in t.Methods)
                {
                    type(m.ReturnType); attributes(m.CustomAttributes); attributes(m.MethodReturnType.CustomAttributes); parameters(m.GenericParameters);
                    foreach (var p in m.Parameters) { type(p.ParameterType); attributes(p.CustomAttributes); }
                    foreach (var o in m.Overrides) method(o);
                    if (!m.HasBody) continue;
                    foreach (var v in m.Body.Variables) type(v.VariableType);
                    foreach (var h in m.Body.ExceptionHandlers) type(h.CatchType);
                    foreach (var i in m.Body.Instructions)
                    {
                        var operand = i.Operand;
                        if (operand is TypeReference) type((TypeReference)operand);
                        else if (operand is MethodReference) method((MethodReference)operand);
                        else if (operand is FieldReference) field((FieldReference)operand);
                        else if (operand is CallSite) { var c = (CallSite)operand; type(c.ReturnType); foreach (var p in c.Parameters) type(p.ParameterType); }
                    }
                }
            }
            // and the TypeRef table itself, for anything named only there
            foreach (var t in module.GetTypeReferences()) type(t);
            return found;
        }

        private static void IndexContract(TypeDefinition type, AssemblyNameReference assembly,
            Dictionary<string, AssemblyNameReference> contracts, Dictionary<string, TypeDefinition> definitions)
        {
            if (type.IsPublic || type.IsNestedPublic) { contracts[type.FullName] = assembly; definitions[type.FullName] = type; }
            foreach (var nested in type.NestedTypes) IndexContract(nested, assembly, contracts, definitions);
        }

        // Each method, field, property and event accessor the code uses from the framework must be defined in the
        // target's public type (or one of its base types there).
        private static void CheckMembers(ModuleDefinition output, ClrTarget target, HashSet<string> targetAssemblies,
            Dictionary<string, TypeDefinition> definitions, List<string> problems)
        {
            foreach (var type in output.GetTypes())
            foreach (var method in type.Methods)
            {
                if (!method.HasBody) continue;
                foreach (var instruction in method.Body.Instructions)
                {
                    var member = instruction.Operand as MemberReference;
                    if (member == null || member is TypeReference || member.DeclaringType == null) continue;
                    var owner = member.DeclaringType.GetElementType();
                    var top = owner;
                    while (top.DeclaringType != null) top = top.DeclaringType;
                    var scope = top.Scope as AssemblyNameReference;
                    if (scope == null || !targetAssemblies.Contains(scope.FullName)) continue;
                    TypeDefinition definition;
                    if (!definitions.TryGetValue(owner.FullName, out definition)) continue; // reported as a type
                    if (Defines(definition, member, definitions)) continue;
                    problems.Add(Display(member) + " is not in " + target + " (used in " + type.FullName + "." + method.Name + Line(method, instruction) + ")");
                }
            }
        }

        private static bool Defines(TypeDefinition type, MemberReference member, Dictionary<string, TypeDefinition> definitions)
        {
            for (var t = type; t != null; )
            {
                var field = member as FieldReference;
                if (field != null && t.Fields.Any(f => f.Name == field.Name)) return true;
                var method = member as MethodReference;
                if (method != null && t.Methods.Any(m => m.Name == method.Name && SameParameters(m, method))) return true;
                if (t.BaseType == null) return false;
                TypeDefinition next;
                t = definitions.TryGetValue(t.BaseType.GetElementType().FullName, out next) ? next : null;
            }
            return false;
        }

        // parameters agree in number, and in type wherever the type does not involve a generic parameter
        private static bool SameParameters(MethodDefinition definition, MethodReference reference)
        {
            if (definition.Parameters.Count != reference.Parameters.Count) return false;
            if (definition.GenericParameters.Count != (reference is GenericInstanceMethod ? ((GenericInstanceMethod)reference).ElementMethod.GenericParameters.Count : reference.GenericParameters.Count)) return false;
            var element = reference.GetElementMethod();
            for (int i = 0; i < definition.Parameters.Count; i++)
            {
                var a = definition.Parameters[i].ParameterType;
                var b = element.Parameters[i].ParameterType;
                if (a.ContainsGenericParameter || b.ContainsGenericParameter) continue;
                if (a.FullName != b.FullName) return false;
            }
            return true;
        }

        private static string Display(MemberReference member)
        {
            var method = member as MethodReference;
            if (method == null) return "the field " + member.DeclaringType.GetElementType().FullName + "." + member.Name;
            var element = method.GetElementMethod();
            string name = element.Name == ".ctor" ? "the constructor " + element.DeclaringType.GetElementType().FullName
                : (element.Name.StartsWith("get_", StringComparison.Ordinal) || element.Name.StartsWith("set_", StringComparison.Ordinal)
                   ? "the property " + element.DeclaringType.GetElementType().FullName + "." + element.Name.Substring(4)
                   : "the method " + element.DeclaringType.GetElementType().FullName + "." + element.Name);
            return name + "(" + string.Join(", ", element.Parameters.Select(p => p.ParameterType.FullName)) + ")";
        }

        private static string Line(MethodDefinition method, Instruction instruction)
        {
            if (!method.DebugInformation.HasSequencePoints) return "";
            SequencePoint point = null;
            foreach (var p in method.DebugInformation.SequencePoints)
                if (p.Offset <= instruction.Offset && !p.IsHidden) point = p;
            return point == null ? "" : ", " + Path.GetFileName(point.Document.Url) + ":" + point.StartLine;
        }
    }
}
