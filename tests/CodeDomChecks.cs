using System; using System.CodeDom; using System.CodeDom.Compiler; using System.Reflection;
using static Nemerle.Compiler.nemerle_code_compiler;
class CodeDomChecks {
  static void Check(bool c, string m) { if (!c) throw new Exception(m); }
  static CompilerParameters P(string refs) {
    var p = new CompilerParameters { GenerateInMemory = false, GenerateExecutable = false, CompilerOptions = "-target-references:" + refs };
    p.TempFiles = new TempFileCollection(System.IO.Path.GetTempPath(), false);
    return p;
  }
  static void Main(string[] a) {
    var c = new NemerleCodeCompiler();
    var unit = new CodeCompileUnit();
    var ns = new CodeNamespace("Demo.Inner"); ns.Imports.Add(new CodeNamespaceImport("System"));
    var cls = new CodeTypeDeclaration("Greeter") { IsClass = true, TypeAttributes = TypeAttributes.Public };
    var m = new CodeMemberMethod { Name = "Answer", Attributes = MemberAttributes.Public | MemberAttributes.Static, ReturnType = new CodeTypeReference(typeof(int)) };
    m.Statements.Add(new CodeMethodReturnStatement(new CodePrimitiveExpression(42)));
    cls.Members.Add(m); ns.Types.Add(cls); unit.Namespaces.Add(ns);
    var sw = new System.IO.StringWriter(); ((ICodeGenerator)c).GenerateCodeFromCompileUnit(unit, sw, new CodeGeneratorOptions());
    Check(!sw.ToString().Contains("namespace"), "generated text has a namespace block:\n" + sw);
    var p = P(a[0]); p.OutputAssembly = System.IO.Path.Combine(a[1], "dom.dll");
    var r = c.CompileAssemblyFromDom(p, unit);
    foreach (CompilerError e in r.Errors) Console.WriteLine(e);
    Check(r.NativeCompilerReturnValue == 0, "dom compile failed");
    var asm = Assembly.LoadFrom(p.OutputAssembly);
    var t = asm.GetType("Demo.Inner+Greeter"); Check(t != null, "Demo.Inner+Greeter missing: " + string.Join(",", Array.ConvertAll(asm.GetTypes(), x => x.FullName)));
    Check((int)t.GetMethod("Answer").Invoke(null, null) == 42, "dom result");
    var p2 = P(a[0]); p2.OutputAssembly = System.IO.Path.Combine(a[1], "src.dll");
    var r2 = c.CompileAssemblyFromSource(p2, "public Answer() : int { 6 * 7 }");
    foreach (CompilerError e in r2.Errors) Console.WriteLine(e);
    Check(r2.NativeCompilerReturnValue == 0, "source compile failed");
    var s = Assembly.LoadFrom(p2.OutputAssembly).GetType("Source0");
    Check(s != null && (int)s.GetMethod("Answer").Invoke(null, null) == 42, "source result");
    var r3 = c.CompileAssemblyFromSource(P(a[0]), "namespace X { public class Y {} }");
    Check(r3.NativeCompilerReturnValue != 0, "namespace must be rejected");
    Console.WriteLine("PASS: CodeDOM writes file modules (Demo.Inner+Greeter, Source0) and rejects namespace text");
  }
}
