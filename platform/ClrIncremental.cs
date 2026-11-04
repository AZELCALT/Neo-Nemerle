using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using Mono.Cecil;
using Mono.Cecil.Cil;

namespace Nemerle.Platform
{
    // Incremental compilation (ncc -incremental): the methods of the files that did not change are emitted as stubs, and
    // their code -- bodies, debug information, and the types and members their lowering made -- is copied here from the
    // previous build's output into the new one, every reference rebound to the new module's definitions.
    public sealed partial class ClrEmission
    {
        string reusePrevious;
        readonly List<MethodBase> reuseMethods = new List<MethodBase>();
        readonly List<string> reuseTypes = new List<string>();
        readonly List<KeyValuePair<string, string>> reuseMembers = new List<KeyValuePair<string, string>>();

        /// Take from `previous' the bodies of `methods' (emitted as stubs), the types `types' (CLR full names, nested with
        /// '/') and the members `members' (declaring type, member name) the new build lacks.
        public void ReuseFrom(string previous, List<MethodBase> methods, List<string> types, List<KeyValuePair<string, string>> members)
        {
            reusePrevious = previous;
            reuseMethods.AddRange(methods);
            reuseTypes.AddRange(types);
            reuseMembers.AddRange(members);
        }

        bool Reusing { get { return reusePrevious != null; } }

        void Splice(ModuleDefinition module, IAssemblyResolver resolver, bool symbols)
        {
            bool oldSymbols = symbols && File.Exists(Path.ChangeExtension(reusePrevious, ".pdb"));
            using (var old = ModuleDefinition.ReadModule(reusePrevious,
                new ReaderParameters { InMemory = true, AssemblyResolver = resolver, ReadSymbols = oldSymbols }))
            {
                var types = new TypeIndex(module);
                var oldTypes = new TypeIndex(old);
                var copier = new Copier(module, old, oldSymbols && symbols, types);
                // the types first, as shells (so what refers to them can be rebound), then their contents
                var clonedTypes = new List<KeyValuePair<TypeDefinition, TypeDefinition>>();
                foreach (var name in reuseTypes)
                {
                    if (types[name] != null) continue;   // (the new build made it too)
                    var from = oldTypes[name];
                    if (from == null) continue;
                    var parentName = from.DeclaringType == null ? null : from.DeclaringType.FullName;
                    if (parentName != null && reuseTypes.Contains(parentName) && types[parentName] == null) continue;   // (with its parent)
                    var parent = parentName == null ? null : types[parentName];
                    if (parentName != null && parent == null) continue;
                    copier.Shell(from, parent, clonedTypes);
                }
                var whole = new HashSet<TypeDefinition>();
                foreach (var pair in clonedTypes) whole.Add(pair.Value);
                var clonedMembers = new List<KeyValuePair<IMemberDefinition, IMemberDefinition>>();
                foreach (var member in reuseMembers)
                {
                    var to = types[member.Key];
                    var from = oldTypes[member.Key];
                    if (to == null || from == null || whole.Contains(to)) continue;   // (a cloned type brings its members)
                    foreach (var field in from.Fields)
                        if (field.Name == member.Value && !Has(to.Fields, field.Name)) clonedMembers.Add(new KeyValuePair<IMemberDefinition, IMemberDefinition>(field, copier.Field(field, to)));
                    foreach (var method in from.Methods)
                        if (method.Name == member.Value && copier.Counterpart(method, to) == null) clonedMembers.Add(new KeyValuePair<IMemberDefinition, IMemberDefinition>(method, copier.MethodShell(method, to)));
                }
                foreach (var pair in clonedTypes) copier.Fill(pair.Key, pair.Value);
                copier.Bodies();
                foreach (var pair in clonedMembers)
                {
                    var method = pair.Key as MethodDefinition;
                    if (method != null) copier.Body(method, (MethodDefinition)pair.Value);
                }
                foreach (var stub in reuseMethods)
                {
                    var to = FindMethodIn(types[stub.DeclaringType.FullName.Replace('+', '/')], stub);
                    MethodDefinition from;
                    try { from = FindMethodIn(oldTypes[stub.DeclaringType.FullName.Replace('+', '/')], stub); }
                    catch (InvalidOperationException) { throw new InvalidOperationException("incremental: the previous build has no " + to.FullName); }
                    copier.Body(from, to);
                    foreach (var a in from.CustomAttributes) reusedAttributes.Add(new KeyValuePair<MethodDefinition, CustomAttribute>(to, copier.Attribute(a, to)));
                }
            }
        }

        // a reused method's attributes the new build lacks (typing added them: AsyncStateMachine...); added after the
        // saved attributes, as the declaration's own come from those too
        readonly List<KeyValuePair<MethodDefinition, CustomAttribute>> reusedAttributes = new List<KeyValuePair<MethodDefinition, CustomAttribute>>();
        void AddReusedAttributes()
        {
            var have = new Dictionary<MethodDefinition, HashSet<string>>();
            foreach (var pair in reusedAttributes)
            {
                HashSet<string> names;
                if (!have.TryGetValue(pair.Key, out names))
                {
                    names = new HashSet<string>();
                    foreach (var a in pair.Key.CustomAttributes) names.Add(a.AttributeType.FullName);
                    have[pair.Key] = names;
                }
                if (!names.Contains(pair.Value.AttributeType.FullName)) pair.Key.CustomAttributes.Add(pair.Value);
            }
            reusedAttributes.Clear();
        }

        // every type of a module by its full name (FindType walks them all, building each name, per call)
        sealed class TypeIndex
        {
            readonly Dictionary<string, TypeDefinition> types = new Dictionary<string, TypeDefinition>();
            public TypeIndex(ModuleDefinition module) { foreach (var type in module.Types) Add(type); }
            public void Add(TypeDefinition type)
            {
                types[type.FullName] = type;
                foreach (var nested in type.NestedTypes) Add(nested);
            }
            public TypeDefinition this[string name] { get { TypeDefinition type; return types.TryGetValue(name, out type) ? type : null; } }
        }

        static bool Has(IEnumerable<FieldDefinition> fields, string name)
        {
            foreach (var field in fields) if (field.Name == name) return true;
            return false;
        }

        // Copies definitions of `old' into `module', rebinding references to `old's own definitions to `module's.
        sealed class Copier
        {
            readonly ModuleDefinition module, old;
            readonly bool symbols;
            readonly Dictionary<string, Document> documents = new Dictionary<string, Document>();

            readonly TypeIndex types;
            public Copier(ModuleDefinition module, ModuleDefinition old, bool symbols, TypeIndex types)
            {
                this.module = module; this.old = old; this.symbols = symbols; this.types = types;
            }

            bool Own(TypeReference type)
            {
                var definition = type as TypeDefinition;
                if (definition != null) return definition.Module == old;
                return type.Scope == old || type.Scope is ModuleDefinition && ((ModuleDefinition)type.Scope).Assembly == old.Assembly
                    || type.Scope is AssemblyNameReference && ((AssemblyNameReference)type.Scope).Name == old.Assembly.Name.Name;
            }

            public void Shell(TypeDefinition from, TypeDefinition parent, List<KeyValuePair<TypeDefinition, TypeDefinition>> made)
            {
                var to = new TypeDefinition(from.Namespace, from.Name, from.Attributes);
                foreach (var parameter in from.GenericParameters) to.GenericParameters.Add(new GenericParameter(parameter.Name, to) { Attributes = parameter.Attributes });
                if (parent == null) module.Types.Add(to); else parent.NestedTypes.Add(to);
                types.Add(to);
                made.Add(new KeyValuePair<TypeDefinition, TypeDefinition>(from, to));
                foreach (var nested in from.NestedTypes) Shell(nested, to, made);
            }

            public void Fill(TypeDefinition from, TypeDefinition to)
            {
                to.PackingSize = from.PackingSize; to.ClassSize = from.ClassSize;
                if (from.BaseType != null) to.BaseType = Type(from.BaseType, to);
                for (int i = 0; i < from.GenericParameters.Count; i++)
                    foreach (var constraint in from.GenericParameters[i].Constraints)
                        to.GenericParameters[i].Constraints.Add(new GenericParameterConstraint(Type(constraint.ConstraintType, to)));
                foreach (var face in from.Interfaces) to.Interfaces.Add(new InterfaceImplementation(Type(face.InterfaceType, to)));
                foreach (var field in from.Fields) Field(field, to);
                var methods = new List<KeyValuePair<MethodDefinition, MethodDefinition>>();
                foreach (var method in from.Methods) methods.Add(new KeyValuePair<MethodDefinition, MethodDefinition>(method, MethodShell(method, to)));
                foreach (var property in from.Properties)
                {
                    var p = new PropertyDefinition(property.Name, property.Attributes, Type(property.PropertyType, to));
                    if (property.GetMethod != null) p.GetMethod = Counterpart(property.GetMethod, to);
                    if (property.SetMethod != null) p.SetMethod = Counterpart(property.SetMethod, to);
                    foreach (var parameter in property.Parameters) p.Parameters.Add(new ParameterDefinition(parameter.Name, parameter.Attributes, Type(parameter.ParameterType, to)));
                    Attributes(property, p, to);
                    to.Properties.Add(p);
                }
                foreach (var e in from.Events)
                {
                    var made = new EventDefinition(e.Name, e.Attributes, Type(e.EventType, to));
                    if (e.AddMethod != null) made.AddMethod = Counterpart(e.AddMethod, to);
                    if (e.RemoveMethod != null) made.RemoveMethod = Counterpart(e.RemoveMethod, to);
                    to.Events.Add(made);
                }
                Attributes(from, to, to);
                pending.AddRange(methods);
            }

            // the bodies of filled types' methods: after every cloned type has its members, as they refer to each other
            readonly List<KeyValuePair<MethodDefinition, MethodDefinition>> pending = new List<KeyValuePair<MethodDefinition, MethodDefinition>>();
            public void Bodies()
            {
                foreach (var pair in pending) Body(pair.Key, pair.Value);
                pending.Clear();
            }

            public FieldDefinition Field(FieldDefinition from, TypeDefinition to)
            {
                var field = new FieldDefinition(from.Name, from.Attributes, Type(from.FieldType, to));
                if (from.HasConstant) field.Constant = from.Constant;
                if (from.InitialValue != null && from.InitialValue.Length > 0) field.InitialValue = from.InitialValue;
                Attributes(from, field, to);
                to.Fields.Add(field);
                return field;
            }

            public MethodDefinition MethodShell(MethodDefinition from, TypeDefinition to)
            {
                var method = new MethodDefinition(from.Name, from.Attributes, module.TypeSystem.Void) { ImplAttributes = from.ImplAttributes, CallingConvention = from.CallingConvention, HasThis = from.HasThis, ExplicitThis = from.ExplicitThis };
                foreach (var parameter in from.GenericParameters) method.GenericParameters.Add(new GenericParameter(parameter.Name, method) { Attributes = parameter.Attributes });
                to.Methods.Add(method);
                for (int i = 0; i < from.GenericParameters.Count; i++)
                    foreach (var constraint in from.GenericParameters[i].Constraints)
                        method.GenericParameters[i].Constraints.Add(new GenericParameterConstraint(Type(constraint.ConstraintType, method)));
                method.ReturnType = Type(from.ReturnType, method);
                foreach (var parameter in from.Parameters)
                {
                    var p = new ParameterDefinition(parameter.Name, parameter.Attributes, Type(parameter.ParameterType, method));
                    if (parameter.HasConstant) p.Constant = parameter.Constant;
                    method.Parameters.Add(p);
                }
                foreach (var overridden in from.Overrides) method.Overrides.Add(Method(overridden, method));
                Attributes(from, method, method);
                return method;
            }

            /// `from's counterpart in `to' (the same name and signature), or null.
            public MethodDefinition Counterpart(MethodReference from, TypeDefinition to)
            {
                foreach (var candidate in to.Methods)
                {
                    if (candidate.Name != from.Name || candidate.Parameters.Count != from.Parameters.Count || candidate.GenericParameters.Count != from.GenericParameters.Count) continue;
                    bool same = Signature(candidate.ReturnType) == Signature(from.ReturnType);
                    for (int i = 0; same && i < from.Parameters.Count; i++)
                        same = Signature(candidate.Parameters[i].ParameterType) == Signature(from.Parameters[i].ParameterType);
                    if (same) return candidate;
                }
                return null;
            }

            static string Signature(TypeReference type)
            {
                var parameter = type as GenericParameter;
                if (parameter != null) return (parameter.Type == GenericParameterType.Method ? "!!" : "!") + parameter.Position;
                var spec = type as TypeSpecification;
                var generic = type as GenericInstanceType;
                if (generic != null)
                {
                    var parts = new List<string>();
                    foreach (var argument in generic.GenericArguments) parts.Add(Signature(argument));
                    return generic.ElementType.FullName + "<" + string.Join(",", parts.ToArray()) + ">";
                }
                if (spec != null) return Signature(spec.ElementType) + spec.MetadataType;
                return type.FullName;
            }

            void Attributes(Mono.Cecil.ICustomAttributeProvider from, Mono.Cecil.ICustomAttributeProvider to, IGenericParameterProvider context)
            {
                foreach (var a in from.CustomAttributes) to.CustomAttributes.Add(Attribute(a, context));
            }

            public CustomAttribute Attribute(CustomAttribute from, IGenericParameterProvider context)
            {
                var a = new CustomAttribute(Method(from.Constructor, context));
                foreach (var argument in from.ConstructorArguments) a.ConstructorArguments.Add(Argument(argument, context));
                foreach (var named in from.Fields) a.Fields.Add(new Mono.Cecil.CustomAttributeNamedArgument(named.Name, Argument(named.Argument, context)));
                foreach (var named in from.Properties) a.Properties.Add(new Mono.Cecil.CustomAttributeNamedArgument(named.Name, Argument(named.Argument, context)));
                return a;
            }

            CustomAttributeArgument Argument(CustomAttributeArgument from, IGenericParameterProvider context)
            {
                object value = from.Value;
                var type = value as TypeReference;
                if (type != null) value = Type(type, context);
                var array = value as CustomAttributeArgument[];
                if (array != null)
                {
                    var copy = new CustomAttributeArgument[array.Length];
                    for (int i = 0; i < array.Length; i++) copy[i] = Argument(array[i], context);
                    value = copy;
                }
                if (value is CustomAttributeArgument) value = Argument((CustomAttributeArgument)value, context);
                return new CustomAttributeArgument(Type(from.Type, context), value);
            }

            // ---- references, rebound ----

            public TypeReference Type(TypeReference type, IGenericParameterProvider context)
            {
                var parameter = type as GenericParameter;
                if (parameter != null)
                {
                    if (parameter.Type == GenericParameterType.Method)
                    {
                        var method = context as MethodReference;
                        return method != null && parameter.Position < method.GenericParameters.Count ? method.GenericParameters[parameter.Position] : parameter;
                    }
                    var owner = context as TypeReference ?? (context as MethodReference)?.DeclaringType;
                    while (owner != null && owner.GenericParameters.Count <= parameter.Position) owner = owner.DeclaringType;
                    return owner != null ? owner.GenericParameters[parameter.Position] : parameter;
                }
                var generic = type as GenericInstanceType;
                if (generic != null)
                {
                    var made = new GenericInstanceType(Type(generic.ElementType, context));
                    foreach (var argument in generic.GenericArguments) made.GenericArguments.Add(Type(argument, context));
                    return made;
                }
                var array = type as ArrayType;
                if (array != null) return new ArrayType(Type(array.ElementType, context), array.Rank);
                var byRef = type as ByReferenceType;
                if (byRef != null) return new ByReferenceType(Type(byRef.ElementType, context));
                var pointer = type as PointerType;
                if (pointer != null) return new PointerType(Type(pointer.ElementType, context));
                var pinned = type as PinnedType;
                if (pinned != null) return new PinnedType(Type(pinned.ElementType, context));
                var required = type as RequiredModifierType;
                if (required != null) return new RequiredModifierType(Type(required.ModifierType, context), Type(required.ElementType, context));
                var optional = type as OptionalModifierType;
                if (optional != null) return new OptionalModifierType(Type(optional.ModifierType, context), Type(optional.ElementType, context));
                if (Own(type))
                {
                    var found = types[type.FullName];
                    if (found == null) throw new InvalidOperationException("incremental: the new build has no type " + type.FullName);
                    return found;
                }
                return module.ImportReference(type, context);
            }

            public MethodReference Method(MethodReference method, IGenericParameterProvider context)
            {
                var instance = method as GenericInstanceMethod;
                if (instance != null)
                {
                    var made = new GenericInstanceMethod(Method(instance.ElementMethod, context));
                    foreach (var argument in instance.GenericArguments) made.GenericArguments.Add(Type(argument, context));
                    return made;
                }
                var declaring = method.DeclaringType;
                if (!Own(declaring.GetElementType())) return module.ImportReference(method, context);
                var owner = Type(declaring, context);
                if (owner is TypeDefinition)
                {
                    var target = Counterpart(method, (TypeDefinition)owner) ?? ByShape(method, (TypeDefinition)owner);
                    if (target == null) throw new InvalidOperationException("incremental: the new build has no method " + method.FullName);
                    return target;
                }
                // a method of an instance of one of this module's generic types: the same shape on the new instance
                var made2 = new MethodReference(method.Name, module.TypeSystem.Void, owner) { HasThis = method.HasThis, ExplicitThis = method.ExplicitThis, CallingConvention = method.CallingConvention };
                foreach (var parameter in method.GenericParameters) made2.GenericParameters.Add(new GenericParameter(parameter.Name, made2));
                made2.ReturnType = Type(method.ReturnType, made2);
                foreach (var parameter in method.Parameters) made2.Parameters.Add(new ParameterDefinition(Type(parameter.ParameterType, made2)));
                return made2;
            }

            static MethodDefinition ByShape(MethodReference method, TypeDefinition owner)
            {
                foreach (var candidate in owner.Methods)
                    if (candidate.Name == method.Name && candidate.Parameters.Count == method.Parameters.Count && candidate.GenericParameters.Count == method.GenericParameters.Count)
                        return candidate;
                return null;
            }

            public FieldReference Field(FieldReference field, IGenericParameterProvider context)
            {
                var declaring = field.DeclaringType;
                if (!Own(declaring.GetElementType())) return module.ImportReference(field, context);
                var owner = Type(declaring, context);
                var definition = owner as TypeDefinition;
                if (definition != null)
                {
                    foreach (var candidate in definition.Fields) if (candidate.Name == field.Name) return candidate;
                    throw new InvalidOperationException("incremental: the new build has no field " + field.FullName);
                }
                return new FieldReference(field.Name, Type(field.FieldType, context), owner);
            }

            // ---- bodies ----

            public void Body(MethodDefinition from, MethodDefinition to)
            {
                if (!from.HasBody) return;
                var source = from.Body;
                var body = new Mono.Cecil.Cil.MethodBody(to) { InitLocals = source.InitLocals, MaxStackSize = source.MaxStackSize };
                to.Body = body;
                var variables = new Dictionary<VariableDefinition, VariableDefinition>();
                foreach (var variable in source.Variables)
                {
                    var local = new VariableDefinition(Type(variable.VariableType, to));
                    body.Variables.Add(local);
                    variables[variable] = local;
                }
                var map = new Dictionary<Instruction, Instruction>();
                var made = new List<Instruction>();
                foreach (var instruction in source.Instructions)
                {
                    var copy = Copy(instruction, to, body, variables);
                    map[instruction] = copy;
                    made.Add(copy);
                }
                foreach (var copy in made)
                {
                    var target = copy.Operand as Instruction;
                    if (target != null) copy.Operand = map[target];
                    var targets = copy.Operand as Instruction[];
                    if (targets != null)
                    {
                        var mapped = new Instruction[targets.Length];
                        for (int i = 0; i < targets.Length; i++) mapped[i] = map[targets[i]];
                        copy.Operand = mapped;
                    }
                    body.Instructions.Add(copy);
                }
                foreach (var handler in source.ExceptionHandlers)
                    body.ExceptionHandlers.Add(new ExceptionHandler(handler.HandlerType) {
                        TryStart = At(map, handler.TryStart), TryEnd = At(map, handler.TryEnd),
                        HandlerStart = At(map, handler.HandlerStart), HandlerEnd = At(map, handler.HandlerEnd),
                        FilterStart = At(map, handler.FilterStart),
                        CatchType = handler.CatchType == null ? null : Type(handler.CatchType, to) });
                if (symbols && from.DebugInformation != null && from.DebugInformation.HasSequencePoints)
                {
                    var debug = to.DebugInformation;
                    foreach (var point in from.DebugInformation.SequencePoints)
                    {
                        Instruction at;
                        if (!InstructionAt(source, point.Offset, map, out at)) continue;
                        debug.SequencePoints.Add(new SequencePoint(at, DocumentFor(point.Document)) {
                            StartLine = point.StartLine, StartColumn = point.StartColumn, EndLine = point.EndLine, EndColumn = point.EndColumn });
                    }
                    if (from.DebugInformation.Scope != null) debug.Scope = Scope(from.DebugInformation.Scope, source, map, variables);
                }
            }

            static bool InstructionAt(Mono.Cecil.Cil.MethodBody body, int offset, Dictionary<Instruction, Instruction> map, out Instruction at)
            {
                foreach (var instruction in body.Instructions)
                    if (instruction.Offset == offset) { at = map[instruction]; return true; }
                at = null;
                return false;
            }

            ScopeDebugInformation Scope(ScopeDebugInformation from, Mono.Cecil.Cil.MethodBody body, Dictionary<Instruction, Instruction> map, Dictionary<VariableDefinition, VariableDefinition> variables)
            {
                Instruction start, end;
                InstructionAt(body, from.Start.Offset, map, out start);
                InstructionAt(body, from.End.IsEndOfMethod ? -1 : from.End.Offset, map, out end);
                var scope = new ScopeDebugInformation(start, end);
                foreach (var variable in from.Variables)
                {
                    VariableDefinition local = null;
                    foreach (var pair in variables) if (pair.Key.Index == variable.Index) local = pair.Value;
                    if (local != null) scope.Variables.Add(new VariableDebugInformation(local, variable.Name) { Attributes = variable.Attributes });
                }
                foreach (var inner in from.Scopes) scope.Scopes.Add(Scope(inner, body, map, variables));
                return scope;
            }

            Document DocumentFor(Document from)
            {
                Document document;
                if (!documents.TryGetValue(from.Url, out document))
                {
                    document = new Document(from.Url) { Language = from.Language, LanguageVendor = from.LanguageVendor, Type = from.Type, HashAlgorithm = from.HashAlgorithm, Hash = from.Hash };
                    documents[from.Url] = document;
                }
                return document;
            }

            static Instruction At(Dictionary<Instruction, Instruction> map, Instruction from)
            {
                return from == null ? null : map[from];
            }

            Instruction Copy(Instruction from, MethodDefinition to, Mono.Cecil.Cil.MethodBody body, Dictionary<VariableDefinition, VariableDefinition> variables)
            {
                var operand = from.Operand;
                var op = from.OpCode;
                if (operand == null) return Instruction.Create(op);
                if (operand is Instruction) return Instruction.Create(op, (Instruction)operand);   // (rebound after)
                if (operand is Instruction[]) return Instruction.Create(op, (Instruction[])operand);
                if (operand is VariableDefinition) return Instruction.Create(op, variables[(VariableDefinition)operand]);
                if (operand is ParameterDefinition)
                {
                    var parameter = (ParameterDefinition)operand;
                    return Instruction.Create(op, parameter.Index < 0 ? body.ThisParameter : to.Parameters[parameter.Index]);
                }
                if (operand is TypeReference) return Instruction.Create(op, Type((TypeReference)operand, to));
                if (operand is MethodReference) return Instruction.Create(op, Method((MethodReference)operand, to));
                if (operand is FieldReference) return Instruction.Create(op, Field((FieldReference)operand, to));
                if (operand is CallSite)
                {
                    var site = (CallSite)operand;
                    var made = new CallSite(Type(site.ReturnType, to)) { HasThis = site.HasThis, ExplicitThis = site.ExplicitThis, CallingConvention = site.CallingConvention };
                    foreach (var parameter in site.Parameters) made.Parameters.Add(new ParameterDefinition(Type(parameter.ParameterType, to)));
                    return Instruction.Create(op, made);
                }
                if (operand is string) return Instruction.Create(op, (string)operand);
                if (operand is sbyte) return Instruction.Create(op, (sbyte)operand);
                if (operand is byte) return Instruction.Create(op, (byte)operand);
                if (operand is int) return Instruction.Create(op, (int)operand);
                if (operand is long) return Instruction.Create(op, (long)operand);
                if (operand is float) return Instruction.Create(op, (float)operand);
                if (operand is double) return Instruction.Create(op, (double)operand);
                throw new InvalidOperationException("incremental: cannot copy the operand " + operand.GetType());
            }
        }
    }
}
