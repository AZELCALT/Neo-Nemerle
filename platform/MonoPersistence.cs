using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Reflection.Emit;
using Mono.Cecil;

namespace Nemerle.Platform
{
    public sealed partial class ClrEmission
    {
        // Mono cannot save builder declarations in MethodImpl rows, and runtime
        // method tokens need not match the rows in the saved module. Resolve by
        // symbolic signature after saving, preserving every recorded override.
#if !MODERN_CLR
        public void RepairSavedOverrides(string path, StrongNameKeyPair signingKey)
        {
            CompleteSavedMetadata(path, signingKey);
        }

        public void CompleteSavedMetadata(string path, StrongNameKeyPair signingKey)
        {
            CompleteSavedMetadataCore(path, signingKey, null);
        }

#endif
        private void CompleteSavedMetadataCore(string path, object signingKey, byte[] signingKeyBlob)
        {
            bool needed = TargetReferenceDirectory != null || signingKeyBlob != null || savedAttributes.Count != 0 || methodAliases.Count != 0 || guardedState.Count != 0 || overrideDefinitions.Exists(item => PersistedOutput || item.Declaration is MethodBuilder);
            if (!needed) return;
            using (var resolver = new DefaultAssemblyResolver())
            {
                resolver.AddSearchDirectory(Path.GetDirectoryName(Path.GetFullPath(path)));
                resolver.AddSearchDirectory(AppDomain.CurrentDomain.BaseDirectory);
                resolver.AddSearchDirectory(Path.GetDirectoryName(typeof(object).Assembly.Location));
                if (TargetReferenceDirectory != null) resolver.AddSearchDirectory(Path.GetFullPath(TargetReferenceDirectory));
#if MODERN_CLR
                bool symbols = File.Exists(Path.ChangeExtension(path, ".pdb"));
#else
                bool symbols = false;
#endif
                using (var assembly = AssemblyDefinition.ReadAssembly(path,
                    new ReaderParameters { InMemory = true, AssemblyResolver = resolver, ReadSymbols = symbols,
                        // for another target the whole module is read up front, so references nothing uses any more can
                        // be removed (a lazily read signature points at reference rows by position)
                        ReadingMode = OtherTarget ? ReadingMode.Immediate : ReadingMode.Deferred }))
            {
                var replacements = new Dictionary<MethodDefinition, List<MethodReference>>();
                var localBodies = new HashSet<MethodDefinition>();
                foreach (var item in overrideDefinitions)
                {
                    var body = FindMethod(assembly.MainModule, item.Body);
                    List<MethodReference> declarations;
                    if (!replacements.TryGetValue(body, out declarations))
                    {
                        declarations = new List<MethodReference>();
                        replacements.Add(body, declarations);
                    }
                    if (PersistedOutput)
                    {
                        var template = item.Declaration is MethodBuilder
                            ? FindMethod(assembly.MainModule, item.Declaration)
                            : assembly.MainModule.ImportReference(item.Declaration);
                        var owner = ImportBoundType(assembly.MainModule, item.DeclaringType, body);
                        var declaration = new MethodReference(template.Name, template.ReturnType, owner) {
                            HasThis = template.HasThis, ExplicitThis = template.ExplicitThis,
                            CallingConvention = template.CallingConvention
                        };
                        foreach (var parameter in template.GenericParameters)
                            declaration.GenericParameters.Add(new GenericParameter(parameter.Name, declaration));
                        foreach (var parameter in template.Parameters)
                            declaration.Parameters.Add(new ParameterDefinition(parameter.ParameterType));
                        declarations.Add(declaration);
                        localBodies.Add(body);
                    }
                    else
                    {
                        var builder = item.Declaration as MethodBuilder;
                        if (builder != null)
                        {
                            declarations.Add(FindMethod(assembly.MainModule, builder));
                            localBodies.Add(body);
                        }
                        else declarations.Add(assembly.MainModule.ImportReference(item.Declaration));
                    }
                }
                foreach (var body in localBodies)
                {
                    body.Overrides.Clear();
                    foreach (var declaration in replacements[body]) body.Overrides.Add(declaration);
                }
                foreach (var bridge in overrideBridges)
                {
                    var method = FindMethod(assembly.MainModule, bridge);
                    method.DeclaringType.Methods.Remove(method);
                }
                foreach (var target in savedAttributes)
                    FindAttributeTarget(assembly, target).CustomAttributes.Add(CreateSavedAttribute(assembly.MainModule, target.Data));
                foreach (var alias in methodAliases)
                {
                    var method = FindMethod(assembly.MainModule, alias.Method);
                    var oldName = method.Name;
                    var ownerName = method.DeclaringType.FullName;
                    foreach (var member in assembly.MainModule.GetMemberReferences())
                    {
                        var reference = member as MethodReference;
                        if (reference != null && reference.Name == oldName && reference.DeclaringType.GetElementType().FullName == ownerName)
                            reference.Name = alias.OriginalName;
                    }
                    method.Name = alias.OriginalName;
                }
                GuardState(assembly.MainModule);
                BindTargetContracts(assembly.MainModule);
                var temporary = path + ".metadata-fix.tmp";
                try
                {
                    var writer = new WriterParameters { StrongNameKeyBlob = signingKeyBlob, WriteSymbols = symbols,
                        SymbolWriterProvider = symbols ? new FinalPortableSymbolWriter(path) : null };
#if !MODERN_CLR
                    writer.StrongNameKeyPair = (StrongNameKeyPair)signingKey;
#endif
                    assembly.Write(temporary, writer);
                    File.Copy(temporary, path, true);
                }
                finally { if (File.Exists(temporary)) File.Delete(temporary);
                    if (File.Exists(Path.ChangeExtension(temporary, ".pdb"))) File.Delete(Path.ChangeExtension(temporary, ".pdb")); }
                }
            }
        }

        // The PE is written to a temporary filename. Its CodeView entry must
        // point at the final PDB, rather than that temporary filename.
        private sealed class FinalPortableSymbolWriter : Mono.Cecil.Cil.ISymbolWriterProvider
        {
            readonly string finalPath;
            readonly Mono.Cecil.Cil.PortablePdbWriterProvider provider = new Mono.Cecil.Cil.PortablePdbWriterProvider();
            public FinalPortableSymbolWriter(string path) { finalPath = path; }
            public Mono.Cecil.Cil.ISymbolWriter GetSymbolWriter(ModuleDefinition module, string fileName)
            { return provider.GetSymbolWriter(module, finalPath); }
            public Mono.Cecil.Cil.ISymbolWriter GetSymbolWriter(ModuleDefinition module, Stream stream)
            { return provider.GetSymbolWriter(module, stream); }
        }

        private static TypeReference ImportBoundType(ModuleDefinition module, Type type, MethodDefinition context)
        {
            if (type.IsGenericParameter)
                return type.DeclaringMethod == null
                    ? context.DeclaringType.GenericParameters[type.GenericParameterPosition]
                    : context.GenericParameters[type.GenericParameterPosition];
            if (type.IsByRef) return new ByReferenceType(ImportBoundType(module, type.GetElementType(), context));
            if (type.IsPointer) return new PointerType(ImportBoundType(module, type.GetElementType(), context));
            if (type.IsArray) return new ArrayType(ImportBoundType(module, type.GetElementType(), context), type.GetArrayRank());
            if (type.IsGenericType && !type.IsGenericTypeDefinition)
            {
                var instance = new GenericInstanceType(ImportBoundType(module, type.GetGenericTypeDefinition(), context));
                foreach (var argument in type.GetGenericArguments()) instance.GenericArguments.Add(ImportBoundType(module, argument, context));
                return instance;
            }
            return type is TypeBuilder ? RequireType(module, type) : module.ImportReference(type);
        }

        private static Mono.Cecil.ICustomAttributeProvider FindAttributeTarget(AssemblyDefinition assembly, AttributeTarget target)
        {
            var module = assembly.MainModule;
            if (target.Member is AssemblyBuilder) return assembly;
            var type = target.Member as TypeBuilder;
            if (type != null) return RequireType(module, type);
            var method = target.Member as MethodBase;
            if (method != null)
            {
                var definition = FindMethod(module, method);
                if (!target.ParameterPosition.HasValue) return definition;
                var position = target.ParameterPosition.Value;
                if (position == 0) return definition.MethodReturnType;
                if (position < 1 || position > definition.Parameters.Count)
                    throw new InvalidOperationException("Invalid saved parameter target: " + method.Name);
                return definition.Parameters[position - 1];
            }
            var eventTarget = target.Member as EventTarget;
            if (eventTarget != null)
                foreach (var evt in RequireType(module, eventTarget.Owner).Events)
                    if (evt.Name == eventTarget.Name) return evt;
            var member = target.Member as MemberInfo;
            if (member != null)
            {
                var owner = RequireType(module, member.DeclaringType);
                if (member is FieldBuilder)
                    foreach (var field in owner.Fields) if (field.Name == member.Name) return field;
                if (member is PropertyBuilder)
                    foreach (var property in owner.Properties) if (property.Name == member.Name) return property;
            }
            throw new InvalidOperationException("Cannot locate saved attribute target: " + target.Member);
        }

        private static TypeDefinition RequireType(ModuleDefinition module, Type type)
        {
            var definition = FindType(module.Types, type.FullName.Replace('+', '/'));
            if (definition == null) throw new InvalidOperationException("Missing attribute target type: " + type);
            return definition;
        }

        private static CustomAttribute CreateSavedAttribute(ModuleDefinition module, AttributeData data)
        {
            var constructor = FindMethod(module, data.Constructor);
            var attribute = new CustomAttribute(constructor);
            for (int index = 0; index < data.Arguments.Length; index++)
                attribute.ConstructorArguments.Add(SavedArgument(module, constructor.Parameters[index].ParameterType, data.Arguments[index]));
            for (int index = 0; index < data.Properties.Length; index++)
                attribute.Properties.Add(new Mono.Cecil.CustomAttributeNamedArgument(data.Properties[index].Name,
                    SavedArgument(module, ImportAttributeType(module, data.Properties[index].PropertyType), data.PropertyValues[index])));
            for (int index = 0; index < data.Fields.Length; index++)
                attribute.Fields.Add(new Mono.Cecil.CustomAttributeNamedArgument(data.Fields[index].Name,
                    SavedArgument(module, ImportAttributeType(module, data.Fields[index].FieldType), data.FieldValues[index])));
            return attribute;
        }

        private static TypeReference ImportAttributeType(ModuleDefinition module, Type type)
        {
            if (type is TypeBuilder) return RequireType(module, type);
            return module.ImportReference(type);
        }

        private static CustomAttributeArgument SavedArgument(ModuleDefinition module, TypeReference type, object value)
        {
            if (value == null) return new CustomAttributeArgument(type, null);
            if (type.FullName == "System.Object")
            {
                var boxedType = value is Type ? module.ImportReference(typeof(Type)) : ImportAttributeType(module, value.GetType());
                return new CustomAttributeArgument(type, SavedArgument(module, boxedType, value));
            }
            var arrayType = type as ArrayType;
            if (arrayType != null)
            {
                var array = (Array)value;
                var arguments = new CustomAttributeArgument[array.Length];
                for (int index = 0; index < arguments.Length; index++)
                    arguments[index] = SavedArgument(module, arrayType.ElementType, array.GetValue(index));
                return new CustomAttributeArgument(type, arguments);
            }
            var referencedType = value as Type;
            if (referencedType != null) value = ImportAttributeType(module, referencedType);
            else if (value.GetType().IsEnum) value = Convert.ChangeType(value, Enum.GetUnderlyingType(value.GetType()));
            return new CustomAttributeArgument(type, value);
        }

        private static MethodDefinition FindMethod(ModuleDefinition module, MethodBase method)
        {
            var type = FindType(module.Types, method.DeclaringType.FullName.Replace('+', '/'));
            if (type == null) throw new InvalidOperationException("Missing emitted type: " + method.DeclaringType);
            var parameters = method.GetParameters();
            var methodParameters = method.IsGenericMethod ? method.GetGenericArguments() : Type.EmptyTypes;
            int arity = methodParameters.Length;
            foreach (var candidate in type.Methods)
            {
                if (candidate.Name != method.Name || candidate.GenericParameters.Count != arity ||
                    candidate.Parameters.Count != parameters.Length) continue;
                bool matches = true;
                for (int index = 0; index < parameters.Length; index++)
                    if (TypeSignature(candidate.Parameters[index].ParameterType) !=
                        TypeSignature(parameters[index].ParameterType, methodParameters)) matches = false;
                var function = method as MethodInfo;
                if (matches && (function == null || TypeSignature(candidate.ReturnType) == TypeSignature(function.ReturnType, methodParameters))) return candidate;
            }
            var expected = new List<string>();
            foreach (var parameter in parameters) expected.Add(TypeSignature(parameter.ParameterType, methodParameters));
            var available = new List<string>();
            foreach (var candidate in type.Methods)
                if (candidate.Name == method.Name) available.Add(candidate.FullName);
            throw new InvalidOperationException("Missing emitted method: " + method.DeclaringType + "." + method.Name +
                "<" + arity + ">(" + string.Join(",", expected.ToArray()) + ") -> " +
                (method is MethodInfo ? TypeSignature(((MethodInfo)method).ReturnType, methodParameters) : "void") +
                "; candidates: " + string.Join("; ", available.ToArray()));
        }

        private static TypeDefinition FindType(IEnumerable<TypeDefinition> types, string name)
        {
            foreach (var type in types)
            {
                if (type.FullName == name) return type;
                var nested = FindType(type.NestedTypes, name);
                if (nested != null) return nested;
            }
            return null;
        }

        private static string TypeSignature(Type type, Type[] methodParameters = null)
        {
            if (type.IsByRef) return TypeSignature(type.GetElementType(), methodParameters) + "&";
            if (type.IsPointer) return TypeSignature(type.GetElementType(), methodParameters) + "*";
            if (type.IsArray) return TypeSignature(type.GetElementType(), methodParameters) + "[" + new string(',', type.GetArrayRank() - 1) + "]";
            // PersistedAssemblyBuilder method parameters can report a null
            // DeclaringMethod before completion. Classify by their owning
            // method's parameter identities as well as reflection metadata.
            if (type.IsGenericParameter) return
                (type.DeclaringMethod != null || methodParameters != null && Array.IndexOf(methodParameters, type) >= 0 ? "!!" : "!") +
                type.GenericParameterPosition;
            if (type.IsGenericType && !type.IsGenericTypeDefinition)
            {
                var arguments = new List<string>();
                foreach (var argument in type.GetGenericArguments()) arguments.Add(TypeSignature(argument, methodParameters));
                return type.GetGenericTypeDefinition().FullName.Replace('+', '/') + "<" + string.Join(",", arguments.ToArray()) + ">";
            }
            return type.FullName.Replace('+', '/');
        }

        private static string TypeSignature(TypeReference type)
        {
            var parameter = type as GenericParameter;
            if (parameter != null) return (parameter.Type == GenericParameterType.Method ? "!!" : "!") + parameter.Position;
            var reference = type as ByReferenceType;
            if (reference != null) return TypeSignature(reference.ElementType) + "&";
            var pointer = type as PointerType;
            if (pointer != null) return TypeSignature(pointer.ElementType) + "*";
            var array = type as ArrayType;
            if (array != null) return TypeSignature(array.ElementType) + "[" + new string(',', array.Rank - 1) + "]";
            var generic = type as GenericInstanceType;
            if (generic != null)
            {
                var arguments = new List<string>();
                foreach (var argument in generic.GenericArguments) arguments.Add(TypeSignature(argument));
                return generic.ElementType.FullName + "<" + string.Join(",", arguments.ToArray()) + ">";
            }
            var modifier = type as IModifierType;
            if (modifier != null) return TypeSignature(((TypeSpecification)type).ElementType);
            return type.FullName;
        }
    }
}
