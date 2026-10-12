using System;
using System.Collections.Generic;
using System.Reflection;
using System.Reflection.Emit;

namespace Nemerle.Platform
{
    public sealed partial class ClrEmission
    {
        public bool PersistedOutput { get; set; }
        private static readonly bool IsMono = typeof(object).Assembly.GetType("Mono.Runtime") != null;
        // PersistedAssemblyBuilder also needs local attribute constructors
        // fixed after saving, notably on assembly-level attributes.
        private bool UseMetadataAttributes { get { return PersistedOutput; } }

        private sealed class AttributeData
        {
            internal ConstructorInfo Constructor;
            internal object[] Arguments;
            internal PropertyInfo[] Properties;
            internal object[] PropertyValues;
            internal FieldInfo[] Fields;
            internal object[] FieldValues;
        }
        private sealed class EventTarget
        {
            internal TypeBuilder Owner;
            internal string Name;
        }
        private sealed class AttributeTarget
        {
            internal object Member;
            internal int? ParameterPosition;
            internal AttributeData Data;
        }
        private readonly Dictionary<CustomAttributeBuilder, AttributeData> attributeData =
            new Dictionary<CustomAttributeBuilder, AttributeData>();
        private readonly List<AttributeTarget> savedAttributes = new List<AttributeTarget>();

        public CustomAttributeBuilder CreateAttribute(ConstructorInfo constructor, object[] arguments,
            PropertyInfo[] properties, object[] propertyValues, FieldInfo[] fields, object[] fieldValues)
        {
            var builder = new CustomAttributeBuilder(constructor, arguments, properties, propertyValues, fields, fieldValues);
            if (UseMetadataAttributes && constructor.DeclaringType is TypeBuilder)
                attributeData.Add(builder, new AttributeData {
                    Constructor = constructor, Arguments = CopyValues(arguments),
                    Properties = (PropertyInfo[])properties.Clone(), PropertyValues = CopyValues(propertyValues),
                    Fields = (FieldInfo[])fields.Clone(), FieldValues = CopyValues(fieldValues)
                });
            return builder;
        }

        private static object[] CopyValues(object[] values)
        {
            var result = new object[values.Length];
            for (int index = 0; index < values.Length; index++) result[index] = CopyValue(values[index]);
            return result;
        }
        private static object CopyValue(object value)
        {
            var array = value as Array;
            if (array == null) return value;
            var copy = (Array)array.Clone();
            for (int index = 0; index < copy.Length; index++) copy.SetValue(CopyValue(array.GetValue(index)), index);
            return copy;
        }

        public void SetAttribute(object target, CustomAttributeBuilder attribute)
        {
            AttributeData data;
            if (attributeData.TryGetValue(attribute, out data))
            {
                if (target is EventBuilder) throw new ArgumentException("Use SetEventAttribute to supply the event identity", "target");
                savedAttributes.Add(new AttributeTarget { Member = target, Data = data });
                return;
            }
            var type = target as TypeBuilder;
            if (type != null) { type.SetCustomAttribute(attribute); return; }
            var method = target as MethodBuilder;
            if (method != null) { method.SetCustomAttribute(attribute); return; }
            var constructor = target as ConstructorBuilder;
            if (constructor != null) { constructor.SetCustomAttribute(attribute); return; }
            var field = target as FieldBuilder;
            if (field != null) { field.SetCustomAttribute(attribute); return; }
            var property = target as PropertyBuilder;
            if (property != null) { property.SetCustomAttribute(attribute); return; }
            var evt = target as EventBuilder;
            if (evt != null) { evt.SetCustomAttribute(attribute); return; }
            var assembly = target as AssemblyBuilder;
            if (assembly != null) { assembly.SetCustomAttribute(attribute); return; }
            throw new ArgumentException("Unsupported custom attribute target", "target");
        }

        public void SetEventAttribute(TypeBuilder owner, string name, EventBuilder target, CustomAttributeBuilder attribute)
        {
            AttributeData data;
            if (attributeData.TryGetValue(attribute, out data))
            {
                savedAttributes.Add(new AttributeTarget { Member = new EventTarget { Owner = owner, Name = name }, Data = data });
                return;
            }
            target.SetCustomAttribute(attribute);
        }

        public void SetParameterAttribute(MethodBase method, ParameterBuilder parameter, CustomAttributeBuilder attribute)
        {
            AttributeData data;
            if (attributeData.TryGetValue(attribute, out data))
            {
                savedAttributes.Add(new AttributeTarget { Member = method, ParameterPosition = parameter.Position, Data = data });
                return;
            }
            parameter.SetCustomAttribute(attribute);
        }
    }
}
