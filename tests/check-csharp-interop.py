#!/usr/bin/env python3
"""Check what a C# library's metadata says beyond its members' types, kept as C# keeps it: `init' properties are set
where the object is made, `required' members by its initializer, a `string?' value is checked before a member of it
is reached (a match, `!= null', `?.', a [NotNullWhen] method, or a cast that throws if it is null); `in' parameters
take plain values, a `ref' result is written through, a `Deconstruct' is a positional pattern, `with' copies a record
or a struct, and `out'/`ref' arguments write top-level values.
"""
import argparse
import pathlib
import shutil
import subprocess
import tempfile

p = argparse.ArgumentParser()
p.add_argument('--toolchain', type=pathlib.Path, required=True)
p.add_argument('--references', type=pathlib.Path, required=True)
a = p.parse_args()
T = a.toolchain.resolve()
work = pathlib.Path(tempfile.mkdtemp(prefix='nemerle-csharp-interop-'))
print('C# interop artifacts:', work, flush=True)

csc = None
for line in subprocess.run(['dotnet', '--list-sdks'], capture_output=True, text=True).stdout.splitlines():
    version, root = line.split(' ', 1)
    candidate = pathlib.Path(root.strip('[]')) / version / 'Roslyn' / 'bincore' / 'csc.dll'
    if candidate.exists(): csc = candidate
if csc is None:
    print('SKIP: no .NET SDK C# compiler to build the C# library')
    raise SystemExit(0)
(work / 'Api.cs').write_text('''#nullable enable
using System;
namespace Lib;
public record Point(int X, int Y);
public record struct Size(int W, int H);
public class Init { public int A { get; init; } public string B { get; set; } = ""; }
public class Req { public required string Name { get; set; } public int Age { get; set; } }
public class Deco { public void Deconstruct(out int a, out string b) { a = 1; b = "one"; } }
public static class Ext {
  static System.Collections.Generic.Dictionary<string,int> tags = new();
  extension(string s) {
    public int Twice => s.Length * 2;
    public string Shout() => s.ToUpper();
    public int Tag { get => tags.TryGetValue(s, out var v) ? v : 0; set => tags[s] = value; }
  }
}
public static class Api
{
    public static string? MaybeNull(bool b) => b ? null : "x";
    public static string? Field = "field";
    public static int In(in int x) => x + 1;
    static int[] store = { 1, 2, 3 };
    public static ref int At(int i) => ref store[i];
    public static ref readonly int AtRO(int i) => ref store[i];
    public static int Store(int i) => store[i];
    public static bool TryGet(int k, out string v) { v = "v" + k; return true; }
    public static void Twice(ref int x) => x *= 2;
}
''')
subprocess.run(['dotnet', str(csc), '-nologo', '-target:library', '-out:' + str(work / 'Api.dll'),
                *['-r:' + str(r) for r in sorted(a.references.glob('*.dll'))], str(work / 'Api.cs')], check=True)

def compile(name, text):
    d = work / name
    d.mkdir()
    (d / 'main.n').write_text('using Lib;\nusing Nemerle.ExtensionsMacros;\n' + text)
    r = subprocess.run([str(T / 'ncc'), str(d / 'main.n'), '-source-root:' + str(d), '-out:' + str(d / 'main.exe'),
                        '-launcher-', '-no-color', '-r:' + str(work / 'Api.dll')], capture_output=True, text=True)
    return d, r.returncode == 0, r.stdout + r.stderr

def run(name, text, expected, what):
    d, ok, log = compile(name, text)
    if not ok: raise SystemExit('FAILED: %s\n%s' % (what, log))
    for f in (work / 'Api.dll', T / 'Nemerle.dll'): shutil.copy2(f, d / f.name)
    shutil.copy2(T / 'ncc.runtimeconfig.json', d / 'main.runtimeconfig.json')
    out = subprocess.run(['dotnet', str(d / 'main.exe')], capture_output=True, text=True).stdout.strip().splitlines()
    if out != expected: raise SystemExit('FAILED: %s printed %r, not %r' % (what, out, expected))
    print('PASS:', what, flush=True)

def rejected(name, text, message, count, what):
    _, ok, log = compile(name, text)
    if ok or log.count(message) != count:
        raise SystemExit('FAILED: %s (%d of %d reported)\n%s' % (what, log.count(message), count, log))
    print('PASS:', what, flush=True)

# init and required: set where the object is made
run('made', 'def i = Init() <- { A = 1; B = "b" };\ndef r = Req() <- { Name = "n"; Age = 3 };\n'
            'System.Console.WriteLine($"$(i.A) $(i.B) $(r.Name)")\n', ['1 b n'],
    'an init property and the required members are set by the initializer')
rejected('init', 'def i = Init();\ni.A = 2;\nF(j : Init) : void { j.A = 3 }\n', "is init-only (C#'s `init')", 2,
         'an init property set after the object is made is an error (in top-level code and a function)')
rejected('required', 'def r = Req();\ndef s = Req() <- { Age = 3 };\n_ = (r, s);\n', 'has required members (Name)', 2,
         'an object made without its required members is an error')

# nullable: checked before a member is reached
run('checked', 'def s = Api.MaybeNull(false);\n'
               'def a = if (s != null) s.Length else -1;\n'
               'def b = match (s) { | null => -1 | t => t.Length };\n'
               'def c = match (s) { | t is string => t.Length | _ => -1 };\n'
               'def d = s?.Length;\n'
               'def e = s == null || s.Length > 0;\n'
               'def f = string.IsNullOrEmpty(s) || s.Length > 0;\n'
               'def g = (s :> string).Length + (Api.MaybeNull(false) :> string).Length;\n'
               'def h = Api.MaybeNull(false);\nwhen (h == null) throw System.ArgumentException();\n'
               'def i = Api.MaybeNull(false);\nassert(i != null);\n'
               'def j = Api.MaybeNull(false);\nSystem.Diagnostics.Debug.Assert(j != null);\n'
               '_ = h.Length + i.Length + j.Length;\n'
               'Count() : int { match (Api.Field) { | null => 0 | v => v.Length } }\n'
               'System.Console.WriteLine($"$a $b $c $d $e $f $g $(Count()) $(Api.MaybeNull(true) == null)");\n'
               'try { _ = Api.MaybeNull(true) :> string } catch { | e => System.Console.WriteLine(e.GetType().Name) }\n',
    ['1 1 1 1 True True 2 5 True', 'NullReferenceException'],
    'a value C# declares `?\' is checked (if, match, is, ?., ||, [NotNullWhen], a guard that throws, assert, '
    '[DoesNotReturnIf], a cast that throws on null)')
rejected('unchecked', 'def s = Api.MaybeNull(false);\n_ = s.Length;\n_ = Api.MaybeNull(true).Length;\n'
                      'F() : int { Api.Field.Length }\nG() : int { def v = Api.MaybeNull(false); v.Length }\n'
                      '_ = s == null && s.Length > 0;\n', "can be null here (C# declares it `?')", 5,
         'a member of an unchecked `?\' value is an error (a binding, a call, a field, a function, after == null &&)')

# in parameters, ref results
run('refs', 'System.Console.WriteLine(Api.In(4));\ndef y = 6;\nSystem.Console.WriteLine(Api.In(y + 1));\n'
            'Api.At(0) = 42;\nApi.At(1) += 5;\nApi.At(2)++;\n'
            'System.Console.WriteLine($"$(Api.Store(0)) $(Api.Store(1)) $(Api.Store(2))")\n',
    ['5', '8', '42 7 4'], 'an `in\' parameter takes a plain value; a `ref\' result is written through (=, +=, ++)')
rejected('readonly', 'Api.AtRO(0) = 1;\n', 'needed a writable location', 1, 'a `ref readonly\' result is not written')

# Deconstruct, with
run('records', 'def (x, y) = Point(3, 4);\n'
               'def n = match (Point(1, 20)) { | Point(1, v) => v | _ => 0 };\n'
               'def p = Point(1, 2);\ndef q = p with { X = 5 };\ndef s = Size(1, 2) with { H = 9 };\n'
               'System.Console.WriteLine($"$(x + y) $n $q $s $(p with { X = 7; Y = 8 })");\n'
               'match (1) { | 1 when n > 0 with z = "guard" => System.Console.WriteLine(z) | _ => () }\n',
    ['7 20 Point { X = 5, Y = 2 } Size { W = 1, H = 9 } Point { X = 7, Y = 8 }', 'guard'],
    'a Deconstruct is a positional pattern; `with\' copies a record and a struct (a case\'s `with\' as before)')
rejected('deconstruct', 'def (a, b) = Deco();\n_ = (a, b);\n', 'has a Deconstruct giving 2, but not all of them are members', 1,
         'a Deconstruct whose values are not members of their names is called, not matched')
rejected('with', 'def i = Init();\n_ = i with { A = 1 };\n', "`with' copies a record", 1,
         '`with\' on a type that is not a record or a struct is an error')

# out and ref arguments write top-level values
run('outs', 'mutable v;\n_ = Api.TryGet(3, out v);\nF() : string { v }\nmutable x = 4;\nApi.Twice(ref x);\nG() : int { x }\n'
            'System.Console.WriteLine($"$v $(F()) $x $(G())")\n', ['v3 v3 8 8'],
    'an `out\'/`ref\' argument writes a top-level value (a function reads what it wrote)')

# C# 14 extension members: an extension method already works; an extension property reads through its getter
run('ext14', 'def s = "hi";\nSystem.Console.WriteLine($"$(s.Shout()) $(s.Twice)")\n', ['HI 4'],
    'a C# 14 extension method and extension property (`s.Shout()`, `s.Twice`)')

# an extension property write goes through its setter, read through its getter
run('ext14_set', 'def s = "k";\ns.Tag = 7;\nAfter() : int { s.Tag }\nSystem.Console.WriteLine($"$(s.Tag) $(After())")\n', ['7 7'],
    'a C# 14 extension property write (`s.Tag = 7` -> set_Tag) and read (`s.Tag` -> get_Tag)')

# the `.:` dot-call: C#'s `x.M()` form, spelled as an extension; method, property read, and property write
run('dotcolon', 'def s = "hey";\ns.:Tag = 9;\nSystem.Console.WriteLine($"$(s.:Shout()) $(s.:Twice) $(s.:Tag)")\n', ['HEY 6 9'],
    'the `.:` extension dot-call (`s.:Shout()`, `s.:Twice`, `s.:Tag = 9`)')
