using System;
using System.Collections.Generic;
using System.Reflection;

namespace Nemerle.Platform
{
    public static class ClrMetadata
    {
        // Legacy Nemerle has neither ref-return nor stack-only type semantics.
        // Do not import these overloads while looking up unrelated supported APIs.
        /// A ref struct: a value that lives only on the stack (Span<T>), which may not be boxed, captured by a closure,
        /// stored in a class's field or an array, or be a generic argument.
        public static bool IsByRefLike(Type type)
        {
            if (type == null || type.IsGenericParameter || type.HasElementType) return false;
            if (!type.IsValueType) return false;
            foreach (var attribute in CustomAttributeData.GetCustomAttributes(type))
                if (attribute.Constructor.DeclaringType.FullName == "System.Runtime.CompilerServices.IsByRefLikeAttribute") return true;
            return false;
        }

        /// Members with ref structs and `ref' returns are offered: a compiler that types them (reads and writes through
        /// returned references, and keeps ref structs where the runtime allows them) sets this; an older one, which
        /// cannot, leaves it off and sees those members hidden, as before.
        public static bool ByRefMembers { get; set; }

        public static MemberInfo[] GetSupportedMembers(Type type, BindingFlags flags)
        {
            var result = new List<MemberInfo>();
            var members = type.GetMembers(flags);
            foreach (var member in members)
                if (IsSupportedMember(member) && !HiddenSpanOverload(member, members)) result.Add(member);
            return result.ToArray();
        }

        // An overload taking a ref struct (WriteLine(ReadOnlySpan<char>), Concat(ReadOnlySpan<char>, ...)) next to
        // one that does not (WriteLine(string)) is left out: a call resolves as it does without spans, and a span is
        // passed where a method has only the span form, or through the span's own members.
        static bool HiddenSpanOverload(MemberInfo member, MemberInfo[] members)
        {
            if (!ByRefMembers) return false;
            var method = member as MethodBase;
            if (method == null || !TakesSpan(method)) return false;
            foreach (var other in members)
            {
                var alternative = other as MethodBase;
                if (alternative != null && alternative != method && alternative.Name == method.Name && !TakesSpan(alternative)
                    && alternative.IsStatic == method.IsStatic)
                    return true;
            }
            return false;
        }

        static bool TakesSpan(MethodBase method)
        {
            foreach (var parameter in method.GetParameters())
            {
                var type = parameter.ParameterType.IsByRef ? parameter.ParameterType.GetElementType() : parameter.ParameterType;
                if (IsByRefLike(type)) return true;
            }
            return false;
        }

        public static bool IsSupportedMember(MemberInfo member)
        {
            var method = member as MethodBase;
            if (method != null)
            {
                var function = method as MethodInfo;
                if (function != null && (function.ReturnType.IsByRef && !ByRefMembers || !SupportedType(function.ReturnType)))
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
                if (property.PropertyType.IsByRef && !ByRefMembers || !SupportedType(property.PropertyType)) return false;
                foreach (var parameter in property.GetIndexParameters())
                    if (!SupportedType(parameter.ParameterType)) return false;
            }
            var field = member as FieldInfo;
            if (field != null && !SupportedType(field.FieldType)) return false;
            return true;
        }

        // A ref struct (Span<T>, ReadOnlySpan<T>, their enumerators) is supported: the compiler keeps it where the
        // runtime allows one (see IsByRefLike, and the checks of Typer for boxing, capture and fields).
        private static bool SupportedType(Type type)
        {
            if (type.HasElementType) return SupportedType(type.GetElementType());
            if (type.IsGenericParameter) return true;
            if (!ByRefMembers)
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
