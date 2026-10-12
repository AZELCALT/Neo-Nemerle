using System;
using System.IO;
using System.Reflection;
using System.Reflection.Emit;
using Nemerle.Platform;

class AttributeChecks
{
    static void Check(bool value, string message) { if (!value) throw new Exception(message); }
    static ConstructorInfo BaseConstructor()
    {
        return typeof(Attribute).GetConstructor(BindingFlags.Instance | BindingFlags.NonPublic, null, Type.EmptyTypes, null);
    }
    static ConstructorBuilder EmptyConstructor(TypeBuilder type)
    {
        var ctor = type.DefineConstructor(MethodAttributes.Public, CallingConventions.Standard, Type.EmptyTypes);
        var il = ctor.GetILGenerator();
        il.Emit(OpCodes.Ldarg_0); il.Emit(OpCodes.Call, BaseConstructor()); il.Emit(OpCodes.Ret);
        return ctor;
    }
    static CustomAttributeBuilder EmptyAttribute(ClrEmission emission, ConstructorInfo constructor)
    {
        return emission.CreateAttribute(constructor, new object[0], new PropertyInfo[0], new object[0], new FieldInfo[0], new object[0]);
    }
    static void Main(string[] args)
    {
        var name = new AssemblyName("AttributeChecksOutput");
        var session = new ClrAssemblySession(name, Path.Combine(args[0], name.Name + ".dll"), false, false);
        var assembly = session.Builder;
        var module = session.Module;
        var emission = new ClrEmission { PersistedOutput = true };
        var self = module.DefineType("SelfAttribute", TypeAttributes.Public, typeof(Attribute));
        var signature = new[] { typeof(string), typeof(Type), typeof(object), typeof(int[]), typeof(AttributeTargets) };
        var names = new[] { "Text", "Kind", "Box", "Values", "Targets" };
        var fields = new FieldBuilder[signature.Length];
        for (int index = 0; index < fields.Length; index++) fields[index] = self.DefineField(names[index], signature[index], FieldAttributes.Public);
        var extra = self.DefineField("Extra", typeof(int), FieldAttributes.Public);
        var noteField = self.DefineField("note", typeof(string), FieldAttributes.Private);
        var note = self.DefineProperty("Note", PropertyAttributes.None, typeof(string), Type.EmptyTypes);
        var getter = self.DefineMethod("get_Note", MethodAttributes.Public | MethodAttributes.SpecialName, typeof(string), Type.EmptyTypes);
        var gil = getter.GetILGenerator(); gil.Emit(OpCodes.Ldarg_0); gil.Emit(OpCodes.Ldfld, noteField); gil.Emit(OpCodes.Ret);
        var setter = self.DefineMethod("set_Note", MethodAttributes.Public | MethodAttributes.SpecialName, typeof(void), new[] { typeof(string) });
        var sil = setter.GetILGenerator(); sil.Emit(OpCodes.Ldarg_0); sil.Emit(OpCodes.Ldarg_1); sil.Emit(OpCodes.Stfld, noteField); sil.Emit(OpCodes.Ret);
        note.SetGetMethod(getter); note.SetSetMethod(setter);
        var ctor = self.DefineConstructor(MethodAttributes.Public, CallingConventions.Standard, signature);
        var il = ctor.GetILGenerator(); il.Emit(OpCodes.Ldarg_0); il.Emit(OpCodes.Call, BaseConstructor());
        for (int index = 0; index < fields.Length; index++)
        { il.Emit(OpCodes.Ldarg_0); il.Emit(OpCodes.Ldarg, (short)(index + 1)); il.Emit(OpCodes.Stfld, fields[index]); }
        il.Emit(OpCodes.Ret);
        var values = new[] { 1, 2 };
        var arguments = new object[] { "kept", self, 42, values, AttributeTargets.Parameter };
        var data = emission.CreateAttribute(ctor, arguments, new PropertyInfo[] { note }, new object[] { "named" }, new FieldInfo[] { extra }, new object[] { 7 });
        emission.RegisterAttribute(self, ctor);
        emission.SetAttribute(self, data);
        emission.SetAttribute(assembly, data);
        emission.SetAttribute(ctor, data);
        emission.SetParameterAttribute(ctor, ctor.DefineParameter(1, ParameterAttributes.None, "text"), data);
        emission.SetAttribute(fields[0], data);
        emission.SetAttribute(note, data);
        var value = self.DefineMethod("Value", MethodAttributes.Public | MethodAttributes.Static, typeof(int), Type.EmptyTypes);
        var vil = value.GetILGenerator(); vil.Emit(OpCodes.Ldc_I4, 42); vil.Emit(OpCodes.Ret);
        emission.SetAttribute(value, data);
        emission.SetParameterAttribute(value, value.DefineParameter(0, ParameterAttributes.None, null), data);
        arguments[0] = "mutated"; values[0] = 99;
        emission.TryCreateRuntimeType(self, () => { });

        var a = module.DefineType("AAttribute", TypeAttributes.Public, typeof(Attribute));
        var b = module.DefineType("BAttribute", TypeAttributes.Public, typeof(Attribute));
        var ac = EmptyConstructor(a); var bc = EmptyConstructor(b);
        emission.RegisterAttribute(a, bc); emission.RegisterAttribute(b, ac);
        emission.SetAttribute(a, EmptyAttribute(emission, bc));
        emission.SetAttribute(b, EmptyAttribute(emission, ac));
        emission.TryCreateRuntimeType(a, () => { }); emission.TryCreateRuntimeType(b, () => { });
        var contract = module.DefineType("IBound`1", TypeAttributes.Public | TypeAttributes.Interface | TypeAttributes.Abstract);
        var contractParameter = contract.DefineGenericParameters("T")[0];
        var contractMethod = contract.DefineMethod("Echo", MethodAttributes.Public | MethodAttributes.Virtual | MethodAttributes.Abstract,
            contractParameter, new Type[] { contractParameter });
        var implementation = module.DefineType("Bound`1", TypeAttributes.Public);
        var implementationParameter = implementation.DefineGenericParameters("U")[0];
        var boundContract = contract.MakeGenericType(implementationParameter);
        implementation.AddInterfaceImplementation(boundContract);
        var echo = emission.DefineMethod(implementation, "Echo", MethodAttributes.Private | MethodAttributes.Virtual);
        echo.SetReturnType(implementationParameter); echo.SetParameters(implementationParameter);
        var eil = echo.GetILGenerator(); eil.Emit(OpCodes.Ldarg_1); eil.Emit(OpCodes.Ret);
        emission.DefineMethodOverride(implementation, echo, boundContract, contractMethod, TypeBuilder.GetMethod(boundContract, contractMethod));
        var genericContract = contract.DefineMethod("EchoBoth", MethodAttributes.Public | MethodAttributes.Virtual | MethodAttributes.Abstract);
        var declaredMethodParameter = genericContract.DefineGenericParameters("V")[0];
        var declaredPair = typeof(Tuple<,>).MakeGenericType(contractParameter, declaredMethodParameter);
        genericContract.SetReturnType(declaredPair); genericContract.SetParameters(declaredPair);
        var genericEcho = emission.DefineMethod(implementation, "EchoBoth", MethodAttributes.Private | MethodAttributes.Virtual);
        var implementedMethodParameter = genericEcho.DefineGenericParameters("W")[0];
        var implementedPair = typeof(Tuple<,>).MakeGenericType(implementationParameter, implementedMethodParameter);
        genericEcho.SetReturnType(implementedPair); genericEcho.SetParameters(implementedPair);
        var genericIl = genericEcho.GetILGenerator(); genericIl.Emit(OpCodes.Ldarg_1); genericIl.Emit(OpCodes.Ret);
        emission.DefineMethodOverride(implementation, genericEcho, boundContract, genericContract, TypeBuilder.GetMethod(boundContract, genericContract));
        emission.TryCreateRuntimeType(contract, () => { });
        emission.TryCreateRuntimeType(implementation, () => { });
        emission.CompletePendingTypes();
        var path = Path.Combine(args[0], name.Name + ".dll");
#if MODERN_CLR
        session.Save(PortableExecutableKinds.ILOnly, ImageFileMachine.I386);
        emission.CompleteAssembly(path, name);
#else
        session.Save(PortableExecutableKinds.ILOnly, ImageFileMachine.I386);
        emission.CompleteSavedMetadata(path, null);
#endif
        var loaded = Assembly.Load(File.ReadAllBytes(path));
        var bound = loaded.GetType("Bound`1").MakeGenericType(typeof(string));
        var boundInterface = loaded.GetType("IBound`1").MakeGenericType(typeof(string));
        var pair = Tuple.Create("generic", 42);
        Check(ReferenceEquals(boundInterface.GetMethod("EchoBoth").MakeGenericMethod(typeof(int)).Invoke(
            Activator.CreateInstance(bound), new object[] { pair }), pair),
            "Method and type generic parameters at the same position must remain distinct");
        Check((string)boundInterface.GetMethod("Echo").Invoke(Activator.CreateInstance(bound), new object[] { "bound" }) == "bound",
            "Generic builder interface override was lost");
        Check(bound.GetMethod("Echo", BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.DeclaredOnly) != null,
            "Original private method name must survive persistence");
        foreach (var method in bound.GetMethods(BindingFlags.Public | BindingFlags.Instance | BindingFlags.DeclaredOnly))
            Check(method.Name != "Echo" && !method.Name.StartsWith("__nemerle_live_"), "Temporary bridge leaked into public API");
        var type = loaded.GetType("SelfAttribute");
        var attribute = type.GetCustomAttributes(false)[0];
        Check(loaded.GetCustomAttributes(false).Length == 1 &&
            loaded.GetCustomAttributes(false)[0].GetType() == type,
            "Assembly attribute using a local constructor must survive persistence");
        Check((string)type.GetField("Text").GetValue(attribute) == "kept", "Constructor string data lost or mutated");
        Check((Type)type.GetField("Kind").GetValue(attribute) == type, "Emitted typeof reference lost");
        Check((int)type.GetField("Box").GetValue(attribute) == 42, "Boxed data lost");
        Check(((int[])type.GetField("Values").GetValue(attribute))[0] == 1, "Array data lost or mutated");
        Check((AttributeTargets)type.GetField("Targets").GetValue(attribute) == AttributeTargets.Parameter, "Enum data lost");
        Check((int)type.GetField("Extra").GetValue(attribute) == 7 && (string)type.GetProperty("Note").GetValue(attribute, null) == "named", "Named field/property data lost");
        Check(type.GetConstructors()[0].GetCustomAttributes(false).Length == 1, "Constructor annotation lost");
        Check(type.GetConstructors()[0].GetParameters()[0].GetCustomAttributes(false).Length == 1, "Parameter annotation lost");
        Check(type.GetField("Text").GetCustomAttributes(false).Length == 1, "Field annotation lost");
        Check(type.GetProperty("Note").GetCustomAttributes(false).Length == 1, "Property annotation lost");
        Check(type.GetMethod("Value").GetCustomAttributes(false).Length == 1, "Method annotation lost");
        Check(type.GetMethod("Value").ReturnParameter.GetCustomAttributes(false).Length == 1, "Return annotation lost");
        Check((int)type.GetMethod("Value").Invoke(null, null) == 42, "Saved method does not execute");
        Check(loaded.GetType("AAttribute").GetCustomAttributes(false)[0].GetType().Name == "BAttribute", "Cross-cycle A annotation lost");
        Check(loaded.GetType("BAttribute").GetCustomAttributes(false)[0].GetType().Name == "AAttribute", "Cross-cycle B annotation lost");
        Console.WriteLine("PASS: self/cyclic attributes, constructor/named values, target identities, C# loading and invocation");
    }
}
