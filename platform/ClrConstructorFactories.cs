using System;
using System.Collections.Generic;
using System.Reflection;
using System.Reflection.Emit;

namespace Nemerle.Platform
{
    public sealed partial class ClrEmission
    {
        readonly Dictionary<ModuleBuilder, Dictionary<ConstructorInfo, MethodBuilder>> constructorFactories =
            new Dictionary<ModuleBuilder, Dictionary<ConstructorInfo, MethodBuilder>>();

        // PersistedAssemblyBuilder cannot import some external generic
        // constructors with array-of-generic-parameter arguments. Construct
        // through a generic method whose own constructor uses plain parameters.
        // The caller still supplies exactly the original constructor operands.
        public MethodInfo GetConstructorFactory(ModuleBuilder module, Type constructedType, ConstructorInfo definition)
        {
#if MODERN_CLR
            if (!PersistedOutput || !constructedType.IsGenericType || !definition.IsPublic ||
                !IsRuntimeType(constructedType.GetGenericTypeDefinition())) return null;
            var arguments = constructedType.GetGenericArguments();
            if (!Array.Exists(arguments, HasGenericElementType)) return null;
            var owner = constructedType.GetGenericTypeDefinition();
            // Normalize the template to the external generic definition.
            definition = (ConstructorInfo)owner.GetMemberWithSameMetadataDefinitionAs(definition);
            Dictionary<ConstructorInfo, MethodBuilder> factories;
            if (!constructorFactories.TryGetValue(module, out factories))
            {
                factories = new Dictionary<ConstructorInfo, MethodBuilder>();
                constructorFactories.Add(module, factories);
            }
            MethodBuilder factory;
            if (!factories.TryGetValue(definition, out factory))
            {
                var holder = module.DefineType("<NemerleConstructorFactory>" + factories.Count,
                    TypeAttributes.NotPublic | TypeAttributes.Abstract | TypeAttributes.Sealed);
                factory = holder.DefineMethod("Create", MethodAttributes.Public | MethodAttributes.Static);
                var sourceParameters = owner.GetGenericArguments();
                var names = new string[sourceParameters.Length];
                for (int i = 0; i < names.Length; i++) names[i] = "T" + i;
                var parameters = factory.DefineGenericParameters(names);
                for (int i = 0; i < parameters.Length; i++)
                {
                    parameters[i].SetGenericParameterAttributes(sourceParameters[i].GenericParameterAttributes &
                        GenericParameterAttributes.SpecialConstraintMask);
                    var interfaces = new List<Type>();
                    foreach (var constraint in sourceParameters[i].GetGenericParameterConstraints())
                    {
                        var bound = BindType(constraint, parameters, Type.EmptyTypes);
                        if (constraint.IsInterface) interfaces.Add(bound);
                        else parameters[i].SetBaseTypeConstraint(bound);
                    }
                    parameters[i].SetInterfaceConstraints(interfaces.ToArray());
                }
                var result = owner.MakeGenericType(parameters);
                var signature = definition.GetParameters();
                var input = new Type[signature.Length];
                for (int i = 0; i < input.Length; i++)
                    input[i] = BindType(signature[i].ParameterType, parameters, Type.EmptyTypes);
                factory.SetReturnType(result); factory.SetParameters(input);
                var il = factory.GetILGenerator();
                for (int i = 0; i < input.Length; i++) il.Emit(OpCodes.Ldarg, (short)i);
                il.Emit(OpCodes.Newobj, TypeBuilder.GetConstructor(result, definition));
                il.Emit(OpCodes.Ret);
                holder.CreateType();
                factories.Add(definition, factory);
            }
            return factory.MakeGenericMethod(arguments);
#else
            return null;
#endif
        }

        static bool HasGenericElementType(Type type)
        {
            // Some persisted builder array types incorrectly report false
            // for ContainsGenericParameters; inspect their elements instead.
            if (type.HasElementType && ContainsOpenParameter(type.GetElementType())) return true;
            return type.IsGenericType && Array.Exists(type.GetGenericArguments(), HasGenericElementType);
        }
        static bool ContainsOpenParameter(Type type)
        {
            if (type.IsGenericParameter) return true;
            if (type.HasElementType) return ContainsOpenParameter(type.GetElementType());
            return type.IsGenericType && Array.Exists(type.GetGenericArguments(), ContainsOpenParameter);
        }
    }
}
