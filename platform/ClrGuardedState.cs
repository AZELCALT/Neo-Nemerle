using System;
using System.Collections.Generic;
using System.Linq;
using Mono.Cecil;
using Mono.Cecil.Cil;

namespace Nemerle.Platform
{
    public sealed partial class ClrEmission
    {
        private sealed class GuardedState
        {
            internal string Type;
            internal string Field;
            internal string Wait;
            internal bool Writable;
        }
        private readonly List<GuardedState> guardedState = new List<GuardedState>();

        /// A public static field of an async file module (its top-level state): in the saved assembly it becomes a
        /// property of the same name whose accessors first call `wait' (which waits until the file's top-level code
        /// has ended), over the field, which the module itself goes on using. A read is one instruction, which can wait
        /// for nothing; a property's is a call. Code in other types reads and writes through the property.
        public void GuardStateField(string type, string field, string wait, bool writable)
        {
            guardedState.Add(new GuardedState { Type = type, Field = field, Wait = wait, Writable = writable });
        }

        private void GuardState(ModuleDefinition module)
        {
            foreach (var state in guardedState)
            {
                var owner = FindType(module.Types, state.Type.Replace('+', '/'));
                if (owner == null) throw new InvalidOperationException("Missing emitted type: " + state.Type);
                var field = owner.Fields.FirstOrDefault(f => f.Name == state.Field && f.IsStatic);
                var wait = owner.Methods.FirstOrDefault(m => m.Name == state.Wait && m.Parameters.Count == 0 && m.IsStatic);
                if (field == null || wait == null) continue;
                // the field keeps its value under another name; code of the module (and of the types in it, its state
                // machines) reaches it directly
                field.Name = "<" + state.Field + ">k__BackingField";
                field.Attributes = (field.Attributes & ~FieldAttributes.FieldAccessMask) | FieldAttributes.Assembly;
                var accessors = MethodAttributes.Public | MethodAttributes.Static | MethodAttributes.HideBySig | MethodAttributes.SpecialName;
                var property = new PropertyDefinition(state.Field, PropertyAttributes.None, field.FieldType);
                var getter = new MethodDefinition("get_" + state.Field, accessors, field.FieldType);
                var il = getter.Body.GetILProcessor();
                il.Emit(OpCodes.Call, wait);
                il.Emit(OpCodes.Ldsfld, field);
                il.Emit(OpCodes.Ret);
                owner.Methods.Add(getter);
                property.GetMethod = getter;
                MethodDefinition setter = null;
                if (state.Writable)
                {
                    setter = new MethodDefinition("set_" + state.Field, accessors, module.TypeSystem.Void);
                    setter.Parameters.Add(new ParameterDefinition("value", ParameterAttributes.None, field.FieldType));
                    il = setter.Body.GetILProcessor();
                    il.Emit(OpCodes.Call, wait);
                    il.Emit(OpCodes.Ldarg_0);
                    il.Emit(OpCodes.Stsfld, field);
                    il.Emit(OpCodes.Ret);
                    owner.Methods.Add(setter);
                    property.SetMethod = setter;
                }
                owner.Properties.Add(property);
                // other types' reads and writes go through the property
                foreach (var type in AllTypes(module.Types))
                {
                    if (Within(type, owner)) continue;
                    foreach (var method in type.Methods)
                    {
                        if (!method.HasBody) continue;
                        foreach (var instruction in method.Body.Instructions)
                        {
                            var target = instruction.Operand as FieldReference;
                            if (target == null || target.Resolve() != field) continue;
                            if (instruction.OpCode == OpCodes.Ldsfld) { instruction.OpCode = OpCodes.Call; instruction.Operand = getter; }
                            else if (instruction.OpCode == OpCodes.Stsfld && setter != null) { instruction.OpCode = OpCodes.Call; instruction.Operand = setter; }
                        }
                    }
                }
            }
        }

        private static IEnumerable<TypeDefinition> AllTypes(IEnumerable<TypeDefinition> types)
        {
            foreach (var type in types)
            {
                yield return type;
                foreach (var nested in AllTypes(type.NestedTypes)) yield return nested;
            }
        }

        private static bool Within(TypeDefinition type, TypeDefinition owner)
        {
            for (var t = type; t != null; t = t.DeclaringType) if (t == owner) return true;
            return false;
        }
    }
}
