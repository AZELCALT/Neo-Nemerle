using System;
using System.Collections.Generic;
using System.Reflection;
using System.Reflection.Emit;
using System.Runtime.CompilerServices;

namespace Nemerle.Platform
{
    // One instance per compilation. This adapter does not own language semantics.
    public sealed partial class ClrEmission
    {
        // Mono changes TypeBuilder's hash after CreateType. Compiler state uses identity.
        private sealed class BuilderIdentity : IEqualityComparer<TypeBuilder>
        {
            internal static readonly BuilderIdentity Instance = new BuilderIdentity();
            public bool Equals(TypeBuilder x, TypeBuilder y) { return ReferenceEquals(x, y); }
            public int GetHashCode(TypeBuilder value) { return RuntimeHelpers.GetHashCode(value); }
        }

        public static int GetMemberToken(MemberInfo member)
        {
            var legacy = member.GetType().GetMethod("GetToken", Type.EmptyTypes);
            if (legacy != null)
            {
                var token = legacy.Invoke(member, null);
                return (int)token.GetType().GetProperty("Token").GetValue(token, null);
            }
            return member.MetadataToken;
        }

        public static bool IsRuntimeType(Type type)
        {
            return type != null && type.GetType() == typeof(object).GetType();
        }
        private readonly Dictionary<TypeBuilder, HashSet<TypeBuilder>> dependencies =
            new Dictionary<TypeBuilder, HashSet<TypeBuilder>>(BuilderIdentity.Instance);
        private readonly Dictionary<TypeBuilder, Action> pending = new Dictionary<TypeBuilder, Action>(BuilderIdentity.Instance);

        private readonly Dictionary<TypeBuilder, List<Action>> overrides =
            new Dictionary<TypeBuilder, List<Action>>(BuilderIdentity.Instance);

        private sealed class OverrideDefinition
        {
            internal TypeBuilder Owner;
            internal MethodInfo Body;
            internal MethodInfo Declaration;
            internal Type DeclaringType;
        }
        private readonly List<OverrideDefinition> overrideDefinitions = new List<OverrideDefinition>();

        public void DefineMethodOverride(TypeBuilder owner, MethodInfo body, MethodInfo declaration)
        {
            DefineMethodOverride(owner, body, declaration.DeclaringType, declaration, declaration);
        }

        public void DefineMethodOverride(TypeBuilder owner, MethodInfo body, Type declaringType,
            MethodInfo definition, MethodInfo declaration)
        {
            overrideDefinitions.Add(new OverrideDefinition { Owner = owner, Body = body,
                Declaration = definition, DeclaringType = declaringType });
            // Persisted output receives complete MethodImpl rows after saving.
            // Mono cannot encode all builder-based generic declarations here.
            if (PersistedOutput && IsMono && !(declaration is MethodBuilder) &&
                !IsRuntimeType(declaration.DeclaringType))
            {
                var typeDefinition = declaringType.IsGenericType ? declaringType.GetGenericTypeDefinition() : declaringType;
                var emittedDefinition = typeDefinition as TypeBuilder;
                if (emittedDefinition != null) RegisterDependency(owner, emittedDefinition);
                List<Action> bridgeActions;
                if (!overrides.TryGetValue(owner, out bridgeActions))
                {
                    bridgeActions = new List<Action>();
                    overrides.Add(owner, bridgeActions);
                }
                bridgeActions.Add(() => CreateOverrideBridge(owner, body, declaringType, definition));
                return;
            }
            var builder = declaration as MethodBuilder;
            if (builder == null) { owner.DefineMethodOverride(body, declaration); return; }
            RegisterDependency(owner, (TypeBuilder)builder.DeclaringType);
            List<Action> actions;
            if (!overrides.TryGetValue(owner, out actions))
            {
                actions = new List<Action>();
                overrides.Add(owner, actions);
            }
            actions.Add(() => owner.DefineMethodOverride(body, ResolveMethod(builder)));
        }

        private sealed class MethodAlias
        {
            internal MethodBuilder Method;
            internal string OriginalName;
        }
        private readonly List<MethodAlias> methodAliases = new List<MethodAlias>();
        public MethodBuilder DefineMethod(TypeBuilder owner, string name, MethodAttributes attributes)
        {
            if (PersistedOutput && IsMono && (attributes & MethodAttributes.MemberAccessMask) != MethodAttributes.Public &&
                (attributes & MethodAttributes.Virtual) != 0)
            {
                var method = owner.DefineMethod("__nemerle_live_" + methodAliases.Count + "_" + name, attributes);
                methodAliases.Add(new MethodAlias { Method = method, OriginalName = name });
                return method;
            }
            return owner.DefineMethod(name, attributes);
        }

        private readonly List<MethodBuilder> overrideBridges = new List<MethodBuilder>();

        private void CreateOverrideBridge(TypeBuilder owner, MethodInfo body, Type declaringType, MethodInfo definition)
        {
            if (body.Name == definition.Name)
                throw new InvalidOperationException("Generic explicit implementation needs a distinct method name: " + body.Name);
            var attributes = MethodAttributes.Public | MethodAttributes.Virtual | MethodAttributes.HideBySig;
            if (definition.DeclaringType.IsInterface) attributes |= MethodAttributes.NewSlot;
            var bridge = owner.DefineMethod(definition.Name, attributes);
            var methodArguments = Type.EmptyTypes;
            if (definition.IsGenericMethodDefinition)
            {
                var names = new List<string>();
                foreach (var argument in definition.GetGenericArguments()) names.Add(argument.Name);
                methodArguments = bridge.DefineGenericParameters(names.ToArray());
            }
            var typeArguments = declaringType.IsGenericType ? declaringType.GetGenericArguments() : Type.EmptyTypes;
            var parameters = definition.GetParameters();
            var parameterTypes = new Type[parameters.Length];
            for (int index = 0; index < parameterTypes.Length; index++)
                parameterTypes[index] = BindType(parameters[index].ParameterType, typeArguments, methodArguments);
            bridge.SetReturnType(BindType(definition.ReturnType, typeArguments, methodArguments));
            bridge.SetParameters(parameterTypes);
            for (int index = 0; index < parameters.Length; index++)
                bridge.DefineParameter(index + 1, parameters[index].Attributes, parameters[index].Name);
            var il = bridge.GetILGenerator();
            il.Emit(OpCodes.Ldarg_0);
            for (int index = 0; index < parameters.Length; index++) il.Emit(OpCodes.Ldarg, (short)(index + 1));
            il.Emit(OpCodes.Call, body.IsGenericMethodDefinition ? body.MakeGenericMethod(methodArguments) : body);
            il.Emit(OpCodes.Ret);
            overrideBridges.Add(bridge);
        }

        private static Type BindType(Type type, Type[] typeArguments, Type[] methodArguments)
        {
            if (type.IsGenericParameter)
                return (type.DeclaringMethod == null ? typeArguments : methodArguments)[type.GenericParameterPosition];
            if (type.IsByRef) return BindType(type.GetElementType(), typeArguments, methodArguments).MakeByRefType();
            if (type.IsPointer) return BindType(type.GetElementType(), typeArguments, methodArguments).MakePointerType();
            if (type.IsArray)
            {
                var element = BindType(type.GetElementType(), typeArguments, methodArguments);
                return type.GetArrayRank() == 1 ? element.MakeArrayType() : element.MakeArrayType(type.GetArrayRank());
            }
            if (type.IsGenericType && !type.IsGenericTypeDefinition)
            {
                var arguments = type.GetGenericArguments();
                for (int index = 0; index < arguments.Length; index++) arguments[index] = BindType(arguments[index], typeArguments, methodArguments);
                return type.GetGenericTypeDefinition().MakeGenericType(arguments);
            }
            return type;
        }

        private static MethodInfo ResolveMethod(MethodBuilder builder)
        {
            var type = ((TypeBuilder)builder.DeclaringType).CreateType();
            // PersistedAssemblyBuilder produces metadata types, not runtime types.
            if (!IsRuntimeType(type)) return builder;
            // Mono exposes GetToken; newer CLR APIs expose MetadataToken.
            var getToken = typeof(MethodBuilder).GetMethod("GetToken", Type.EmptyTypes);
            int token;
            if (getToken != null)
            {
                var value = getToken.Invoke(builder, null);
                token = (int)value.GetType().GetProperty("Token").GetValue(value, null);
            }
            else token = builder.MetadataToken;
            foreach (var method in type.GetMethods(BindingFlags.Public | BindingFlags.NonPublic |
                BindingFlags.Static | BindingFlags.Instance | BindingFlags.DeclaredOnly))
                if (method.MetadataToken == token) return method;
            throw new InvalidOperationException("Cannot resolve emitted override declaration: " + builder.Name);
        }

        public Type TryCreateRuntimeType(TypeBuilder type, Action retry)
        {
            if (type == null) throw new ArgumentNullException("type");
            if (retry == null) throw new ArgumentNullException("retry");
            if (!DependenciesReady(type))
            {
                pending[type] = retry;
                return null;
            }
            List<Action> actions;
            if (overrides.TryGetValue(type, out actions))
            {
                foreach (var action in actions) action();
                overrides.Remove(type);
            }
            var result = type.CreateType();
            dependencies.Remove(type);
            pending.Remove(type);
            return result;
        }

        private bool DependenciesReady(TypeBuilder type)
        {
            HashSet<TypeBuilder> required;
            if (dependencies.TryGetValue(type, out required))
                foreach (var dependency in required)
                    if (!dependency.IsCreated()) return false;
            return true;
        }

        // Called after a compiler emission phase, when queued method bodies are ready.
        public void CompletePendingTypes()
        {
            while (pending.Count != 0)
            {
                bool progress = false;
                foreach (var item in new List<KeyValuePair<TypeBuilder, Action>>(pending))
                {
                    if (!DependenciesReady(item.Key)) continue;
                    item.Value();
                    if (!item.Key.IsCreated())
                        throw new InvalidOperationException("Type finalization did not complete: " + item.Key.FullName);
                    pending.Remove(item.Key);
                    progress = true;
                }
                if (!progress)
                {
                    var names = new List<string>();
                    foreach (var type in pending.Keys)
                    {
                        HashSet<TypeBuilder> required;
                        if (dependencies.TryGetValue(type, out required))
                            foreach (var dependency in required)
                                if (!dependency.IsCreated()) names.Add(type.FullName + " -> " + dependency.FullName);
                    }
                    names.Sort(StringComparer.Ordinal);
                    throw new InvalidOperationException("Unresolved or cyclic emitted type dependencies: " +
                        string.Join(", ", names.ToArray()));
                }
            }
        }

        public static FieldBuilder DefineField(TypeBuilder owner, string name, Type fieldType,
            Type[] requiredModifiers, Type[] optionalModifiers, FieldAttributes attributes)
        {
            return owner.DefineField(name, fieldType, Normalize(requiredModifiers),
                Normalize(optionalModifiers), attributes);
        }

        public static void SetMethodSignature(MethodBuilder method, Type returnType,
            Type[] requiredReturnModifiers, Type[] optionalReturnModifiers,
            Type[] parameterTypes, Type[][] requiredParameterModifiers,
            Type[][] optionalParameterModifiers)
        {
            method.SetSignature(returnType, Normalize(requiredReturnModifiers),
                Normalize(optionalReturnModifiers), parameterTypes,
                requiredParameterModifiers, optionalParameterModifiers);
        }

        private static Type[] Normalize(Type[] modifiers)
        {
            return modifiers == null || modifiers.Length == 0 ? null : modifiers;
        }

        public void RegisterAttribute(TypeBuilder owner, ConstructorInfo constructor)
        {
            if (owner == null) throw new ArgumentNullException("owner");
            if (constructor == null) throw new ArgumentNullException("constructor");
            var dependency = constructor.DeclaringType as TypeBuilder;
            if (dependency == null || PersistedOutput) return;
            RegisterDependency(owner, dependency);
        }

        private void RegisterDependency(TypeBuilder owner, TypeBuilder dependency)
        {
            HashSet<TypeBuilder> required;
            if (!dependencies.TryGetValue(owner, out required))
            {
                required = new HashSet<TypeBuilder>(BuilderIdentity.Instance);
                dependencies.Add(owner, required);
            }
            required.Add(dependency);
        }
    }
}
