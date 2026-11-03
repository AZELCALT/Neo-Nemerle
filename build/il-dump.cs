// Prints an assembly's types and members, each method with its IL, in a stable order and with operands named, not
// numbered: two builds of the same program print the same text whatever tokens and module id they got. Used to check
// that compiling in parallel gives what compiling in order does (tests/check-parallel-typing.py).
//
//     il-dump ASSEMBLY > dump.txt
using System;
using System.Linq;
using Mono.Cecil;
using Mono.Cecil.Cil;

static class IlDump
{
    static int Main(string[] args)
    {
        if (args.Length != 1) { Console.Error.WriteLine("usage: il-dump ASSEMBLY"); return 2; }
        var resolver = new DefaultAssemblyResolver();
        resolver.AddSearchDirectory(System.IO.Path.GetDirectoryName(System.IO.Path.GetFullPath(args[0])));
        var module = ModuleDefinition.ReadModule(args[0], new ReaderParameters { AssemblyResolver = resolver });
        foreach (var type in module.GetTypes().OrderBy(t => t.FullName, StringComparer.Ordinal))
        {
            Console.WriteLine("type " + type.FullName + " : " + (type.BaseType?.FullName ?? "-") + " [" + type.Attributes + "]");
            foreach (var i in type.Interfaces.Select(i => i.InterfaceType.FullName).OrderBy(n => n, StringComparer.Ordinal))
                Console.WriteLine("  implements " + i);
            foreach (var a in Attributes(type)) Console.WriteLine("  [" + a + "]");
            foreach (var f in type.Fields.OrderBy(f => f.Name, StringComparer.Ordinal))
                Console.WriteLine("  field " + f.FieldType.FullName + " " + f.Name + " [" + f.Attributes + "]");
            foreach (var p in type.Properties.OrderBy(p => p.Name, StringComparer.Ordinal))
                Console.WriteLine("  property " + p.PropertyType.FullName + " " + p.Name);
            foreach (var m in type.Methods.OrderBy(m => m.FullName, StringComparer.Ordinal))
            {
                Console.WriteLine("  method " + m.FullName + " [" + m.Attributes + "]");
                foreach (var a in Attributes(m)) Console.WriteLine("    [" + a + "]");
                if (!m.HasBody) continue;
                var body = m.Body;
                Console.WriteLine("    maxstack " + body.MaxStackSize + " init " + body.InitLocals);
                foreach (var v in body.Variables) Console.WriteLine("    local " + v.Index + " " + v.VariableType.FullName);
                foreach (var h in body.ExceptionHandlers)
                    Console.WriteLine("    handler " + h.HandlerType + " " + Offset(h.TryStart) + "-" + Offset(h.TryEnd) + " -> "
                        + Offset(h.HandlerStart) + "-" + Offset(h.HandlerEnd) + " " + (h.CatchType?.FullName ?? ""));
                foreach (var ins in body.Instructions)
                    Console.WriteLine("    " + Offset(ins) + " " + ins.OpCode.Name + Operand(ins.Operand));
            }
        }
        return 0;
    }

    static string Offset(Instruction i) => i == null ? "end" : "IL_" + i.Offset.ToString("x4");

    static string Operand(object operand) => operand switch
    {
        null => "",
        Instruction target => " " + Offset(target),
        Instruction[] targets => " (" + string.Join(", ", targets.Select(Offset)) + ")",
        VariableDefinition v => " V_" + v.Index,
        ParameterDefinition p => " " + (string.IsNullOrEmpty(p.Name) ? "A_" + p.Index : p.Name),
        MemberReference r => " " + r.FullName,
        string s => " \"" + s.Replace("\\", "\\\\").Replace("\"", "\\\"").Replace("\n", "\\n") + "\"",
        _ => " " + Convert.ToString(operand, System.Globalization.CultureInfo.InvariantCulture)
    };

    static System.Collections.Generic.IEnumerable<string> Attributes(ICustomAttributeProvider provider) =>
        provider.CustomAttributes.Select(Attribute).OrderBy(s => s, StringComparer.Ordinal);

    // (an argument of an enum from an assembly that is not found cannot be decoded: its raw bytes are what is compared)
    static string Attribute(CustomAttribute a)
    {
        try { return a.AttributeType.FullName + "(" + string.Join(", ", a.ConstructorArguments.Select(c => Convert.ToString(c.Value, System.Globalization.CultureInfo.InvariantCulture))) + ")"; }
        catch (Exception) { return a.AttributeType.FullName + "(blob " + Convert.ToHexString(a.GetBlob()) + ")"; }
    }
}
