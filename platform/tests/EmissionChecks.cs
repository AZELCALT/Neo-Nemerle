using System;
using System.IO;
using System.Reflection;
using System.Reflection.Emit;
using System.Runtime.CompilerServices;
using Nemerle.Platform;

class MetadataFixture
{
    static int value;
    public static ref int RefReturn() { return ref value; }
    public static void OrdinaryRef(ref int input) { input++; }
    public static void OrdinaryArray(int[] input) { }
#if MODERN_CLR
    public static void StackOnly(Span<int> input) { }
#endif
}

class EmissionChecks
{
    static void Check(bool value, string message)
    {
        if (!value) throw new Exception(message);
    }

    static ConstructorBuilder AttributeConstructor(TypeBuilder type)
    {
        var ctor = type.DefineConstructor(MethodAttributes.Public,
            CallingConventions.Standard, Type.EmptyTypes);
        var il = ctor.GetILGenerator();
        il.Emit(OpCodes.Ldarg_0);
        il.Emit(OpCodes.Call, typeof(Attribute).GetConstructor(
            BindingFlags.Instance | BindingFlags.NonPublic, null, Type.EmptyTypes, null));
        il.Emit(OpCodes.Ret);
        return ctor;
    }

    static void Main(string[] args)
    {
        Check(!ClrMetadata.IsSupportedMember(typeof(MetadataFixture).GetMethod("RefReturn")),
            "Unsupported ref-return signatures must be excluded");
        Check(ClrMetadata.IsSupportedMember(typeof(MetadataFixture).GetMethod("OrdinaryRef")),
            "Ordinary ref parameters must remain available");
        Check(ClrMetadata.IsSupportedMember(typeof(MetadataFixture).GetMethod("OrdinaryArray")),
            "Ordinary array parameters must remain available");
#if MODERN_CLR
        Check(ClrMetadata.IsSupportedMember(typeof(Enum).GetMethod("GetNames", new[] { typeof(Type) })),
            "Existing Enum overload must remain available");
        foreach (var enumMethod in typeof(Enum).GetMethods())
            if (enumMethod.Name == "GetNames" && enumMethod.IsGenericMethod)
                Check(!ClrMetadata.IsSupportedMember(enumMethod), "Unsupported enum constraints must not poison overload discovery");
        Check(!ClrMetadata.IsSupportedMember(typeof(MetadataFixture).GetMethod("StackOnly")),
            "Stack-only signatures must be excluded");
#endif
        var name = new AssemblyName("PlatformChecks");
        var session = new ClrAssemblySession(name, Path.Combine(args[0], name.Name + ".dll"), false, false);
        var assembly = session.Builder;
        var module = session.Module;
        var platform = new ClrEmission();
        var target = module.DefineType("Target", TypeAttributes.Public);
        var contract = module.DefineType("IValue", TypeAttributes.Public | TypeAttributes.Interface | TypeAttributes.Abstract);
        var declaration = contract.DefineMethod("Read", MethodAttributes.Public | MethodAttributes.Virtual | MethodAttributes.Abstract,
            typeof(int), Type.EmptyTypes);
        target.AddInterfaceImplementation(contract);
        var implementation = target.DefineMethod("IValue.Read", MethodAttributes.Private | MethodAttributes.Virtual,
            typeof(int), Type.EmptyTypes);
        var implementationIl = implementation.GetILGenerator();
        implementationIl.Emit(OpCodes.Ldc_I4, 7); implementationIl.Emit(OpCodes.Ret);
        platform.DefineMethodOverride(target, implementation, declaration);
        var genericDeclaration = contract.DefineMethod("Echo", MethodAttributes.Public | MethodAttributes.Virtual | MethodAttributes.Abstract);
        var declaredParameter = genericDeclaration.DefineGenericParameters("T")[0];
        genericDeclaration.SetReturnType(declaredParameter);
        genericDeclaration.SetParameters(declaredParameter);
        var genericImplementation = target.DefineMethod("IValue.Echo", MethodAttributes.Private | MethodAttributes.Virtual);
        var implementedParameter = genericImplementation.DefineGenericParameters("U")[0];
        genericImplementation.SetReturnType(implementedParameter);
        genericImplementation.SetParameters(implementedParameter);
        var genericIl = genericImplementation.GetILGenerator();
        genericIl.Emit(OpCodes.Ldarg_1); genericIl.Emit(OpCodes.Ret);
        platform.DefineMethodOverride(target, genericImplementation, genericDeclaration);
        var attribute = module.DefineType("LaterAttribute", TypeAttributes.Public, typeof(Attribute));
        var ctor = AttributeConstructor(attribute);
        target.SetCustomAttribute(new CustomAttributeBuilder(ctor, new object[0]));
        platform.RegisterAttribute(target, ctor);
        platform.RegisterAttribute(target, ctor); // repeated uses are one dependency
        var targetCtor = target.DefineDefaultConstructor(MethodAttributes.Public);
        targetCtor.SetCustomAttribute(new CustomAttributeBuilder(ctor, new object[0]));
        platform.RegisterAttribute(target, ctor);
        var parameterMethod = target.DefineMethod("WithParameter", MethodAttributes.Public | MethodAttributes.Static,
            typeof(void), new[] { typeof(int) });
        parameterMethod.DefineParameter(1, ParameterAttributes.None, "value").SetCustomAttribute(
            new CustomAttributeBuilder(ctor, new object[0]));
        platform.RegisterAttribute(target, ctor);
        parameterMethod.GetILGenerator().Emit(OpCodes.Ret);
        var flags = target.DefineNestedType("Flags", TypeAttributes.NestedPublic | TypeAttributes.Sealed, typeof(Enum));
        flags.DefineField("value__", typeof(int), FieldAttributes.Public | FieldAttributes.SpecialName | FieldAttributes.RTSpecialName);
        flags.DefineField("Zero", flags, FieldAttributes.Public | FieldAttributes.Static | FieldAttributes.Literal).SetConstant(0);
        var flagField = ClrEmission.DefineField(target, "flags", flags, Type.EmptyTypes, Type.EmptyTypes, FieldAttributes.Public);
        ClrEmission.DefineField(target, "ModifiedField", typeof(int), null,
            new[] { typeof(IsConst) }, FieldAttributes.Public);
        var readFlag = target.DefineMethod("ReadFlag", MethodAttributes.Public | MethodAttributes.Static,
            typeof(int), new Type[] { target });
        var flagIl = readFlag.GetILGenerator();
        flagIl.Emit(OpCodes.Ldarg_0); flagIl.Emit(OpCodes.Ldfld, flagField); flagIl.Emit(OpCodes.Ret);
        // Nemerle must finalize all enums, including nested enums, before owners.
        platform.TryCreateRuntimeType(flags, () => { });
        var method = target.DefineMethod("Value", MethodAttributes.Public | MethodAttributes.Static);
        ClrEmission.SetMethodSignature(method, typeof(int), Type.EmptyTypes, Type.EmptyTypes,
            Type.EmptyTypes, null, null);
        var il = method.GetILGenerator();
        il.Emit(OpCodes.Ldc_I4, 42);
        il.Emit(OpCodes.Ret);
        var modified = target.DefineMethod("Modified", MethodAttributes.Public | MethodAttributes.Static);
        ClrEmission.SetMethodSignature(modified, typeof(int), null, new[] { typeof(IsConst) },
            Type.EmptyTypes, null, null);
        var mil = modified.GetILGenerator();
        mil.Emit(OpCodes.Ldc_I4_0);
        mil.Emit(OpCodes.Ret);
        int retried = 0;
        Check(platform.TryCreateRuntimeType(target, () => {
            retried++;
            platform.TryCreateRuntimeType(target, () => { });
        }) == null, "Target must wait for its generated attribute");
        platform.TryCreateRuntimeType(attribute, () => { });
        platform.TryCreateRuntimeType(contract, () => { });
        platform.CompletePendingTypes();
        Check(retried == 1 && target.IsCreated(), "Deferred target must complete exactly once");
#if MODERN_CLR
        var path = Path.Combine(args[0], "PlatformChecks.dll");
        session.Save(PortableExecutableKinds.ILOnly, ImageFileMachine.I386);
        var loaded = Assembly.Load(File.ReadAllBytes(path));
#else
        session.Save(PortableExecutableKinds.ILOnly, ImageFileMachine.I386);
        platform.RepairSavedOverrides(Path.Combine(args[0], "PlatformChecks.dll"), null);
        var loaded = Assembly.LoadFile(Path.Combine(args[0], "PlatformChecks.dll"));
#endif
        var loadedType = loaded.GetType("Target");
        Check((int)loaded.GetType("IValue").GetMethod("Read").Invoke(Activator.CreateInstance(loadedType), null) == 7,
            "Explicit emitted interface implementations must save and execute");
        Check((string)loaded.GetType("IValue").GetMethod("Echo").MakeGenericMethod(typeof(string))
            .Invoke(Activator.CreateInstance(loadedType), new object[] { "echo" }) == "echo",
            "Generic explicit interface methods must save and execute");
        Check((int)loadedType.GetMethod("Value").Invoke(null, null) == 42, "Saved method must execute");
        Check(loadedType.GetCustomAttributes(false).Length == 1, "Attribute must survive persistence");
        Check(loadedType.GetConstructors()[0].GetCustomAttributes(false).Length == 1,
            "Generated constructor attributes must survive persistence");
        Check(loadedType.GetMethod("WithParameter").GetParameters()[0].GetCustomAttributes(false).Length == 1,
            "Generated parameter attributes must survive persistence");
        Check((int)loadedType.GetMethod("ReadFlag").Invoke(null, new[] { Activator.CreateInstance(loadedType) }) == 0,
            "Nested enum fields must save and execute");
        Check(loadedType.GetField("ModifiedField").GetOptionalCustomModifiers()[0] == typeof(IsConst),
            "Nonempty field modifiers must survive persistence");
        Check(loadedType.GetMethod("Modified").ReturnParameter.GetOptionalCustomModifiers()[0] ==
            typeof(IsConst), "Nonempty modifiers must survive persistence");

        var a = module.DefineType("A", TypeAttributes.Public, typeof(Attribute));
        var b = module.DefineType("B", TypeAttributes.Public, typeof(Attribute));
        platform.RegisterAttribute(a, AttributeConstructor(b));
        platform.RegisterAttribute(b, AttributeConstructor(a));
        bool cycle = false;
        platform.TryCreateRuntimeType(a, () => { });
        platform.TryCreateRuntimeType(b, () => { });
        try { platform.CompletePendingTypes(); }
        catch (InvalidOperationException e) { cycle = e.Message.Contains("cyclic"); }
        Check(cycle, "Attribute cycles must produce a managed diagnostic");

        platform = new ClrEmission();
        var unresolved = module.DefineType("Unresolved", TypeAttributes.Public);
        var missing = module.DefineType("MissingAttribute", TypeAttributes.Public, typeof(Attribute));
        platform.RegisterAttribute(unresolved, AttributeConstructor(missing));
        bool rejected = false;
        platform.TryCreateRuntimeType(unresolved, () => { });
        try { platform.CompletePendingTypes(); }
        catch (InvalidOperationException e) { rejected = e.Message.Contains("Unresolved"); }
        Check(rejected, "Unfinished attributes must be rejected before runtime type creation");
        Console.WriteLine("PASS: persistence, C# invocation, modifiers, attributes, cycles, unresolved dependencies and metadata filtering");
    }
}
