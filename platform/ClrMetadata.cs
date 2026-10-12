using System;
using System.Collections.Generic;
using System.Reflection;

namespace Nemerle.Platform
{
    public static class ClrMetadata
    {
        // Legacy Nemerle has neither ref-return nor stack-only type semantics.
        // Do not import these overloads while looking up unrelated supported APIs.
        public static MemberInfo[] GetSupportedMembers(Type type, BindingFlags flags)
        {
            var result = new List<MemberInfo>();
            foreach (var member in type.GetMembers(flags))
                if (IsSupportedMember(member)) result.Add(member);
            return result.ToArray();
        }

        public static bool IsSupportedMember(MemberInfo member)
        {
            var method = member as MethodBase;
            if (method != null)
            {
                var function = method as MethodInfo;
                if (function != null && (function.ReturnType.IsByRef || !SupportedType(function.ReturnType)))
                    return false;
                // The frontend cannot yet represent the combined struct+Enum
                // constraint used by newer generic Enum overloads. Keep the
                // existing Type-taking overload available instead.
                if (method.IsGenericMethod)
                    foreach (var argument in method.GetGenericArguments())
                        if (argument.IsGenericParameter &&
                            (argument.GenericParameterAttributes & GenericParameterAttributes.NotNullableValueTypeConstraint) != 0)
                            foreach (var constraint in argument.GetGenericParameterConstraints())
                                if (constraint == typeof(Enum)) return false;
                foreach (var parameter in method.GetParameters())
                    if (!SupportedType(parameter.ParameterType)) return false;
            }
            var property = member as PropertyInfo;
            if (property != null)
            {
                if (property.PropertyType.IsByRef || !SupportedType(property.PropertyType)) return false;
                foreach (var parameter in property.GetIndexParameters())
                    if (!SupportedType(parameter.ParameterType)) return false;
            }
            var field = member as FieldInfo;
            if (field != null && !SupportedType(field.FieldType)) return false;
            return true;
        }

        private static bool SupportedType(Type type)
        {
            if (type.HasElementType) return SupportedType(type.GetElementType());
            if (type.IsGenericParameter) return true;
            foreach (var attribute in CustomAttributeData.GetCustomAttributes(type))
                if (attribute.Constructor.DeclaringType.FullName ==
                    "System.Runtime.CompilerServices.IsByRefLikeAttribute") return false;
            if (type.IsGenericType)
                foreach (var argument in type.GetGenericArguments())
                    if (!SupportedType(argument)) return false;
            return true;
        }
    }
}
