#!/usr/bin/env python3
"""Check C# calling Nemerle (the reverse direction). Nemerle compiles to an ordinary .NET assembly, so C# calls a
Nemerle class's methods and properties and uses its BCL-typed results directly. (A raw Nemerle function value still
surfaces as a Nemerle lambda type, not `Func`/`Action` — not covered here, see doc/GAPS.md "C# interop".)
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
work = pathlib.Path(tempfile.mkdtemp(prefix='nemerle-reverse-interop-'))
print('Reverse interop artifacts:', work, flush=True)

csc = None
for line in subprocess.run(['dotnet', '--list-sdks'], capture_output=True, text=True).stdout.splitlines():
    version, root = line.split(' ', 1)
    candidate = pathlib.Path(root.strip('[]')) / version / 'Roslyn' / 'bincore' / 'csc.dll'
    if candidate.exists(): csc = candidate
if csc is None:
    print('SKIP: no .NET SDK C# compiler to call Nemerle from C#')
    raise SystemExit(0)

# a Nemerle library: a class with a method, a property and a BCL-typed result (exported to the root namespace for C#)
(work / 'engine.n').write_text(
    'export public class Engine {\n'
    '  public Add(a : int, b : int) : int { a + b }\n'
    '  public Greeting : string { get { "hi from Nemerle" } }\n'
    '  public Names() : System.Collections.Generic.List[string] {\n'
    '    def l = System.Collections.Generic.List(); l.Add("a"); l.Add("b"); l\n'
    '  }\n'
    '}\n')
r = subprocess.run([str(T / 'ncc'), str(work / 'engine.n'), '-source-root:' + str(work), '-target:library',
                    '-out:' + str(work / 'engine.dll'), '-no-color'], capture_output=True, text=True)
if not (work / 'engine.dll').exists():
    raise SystemExit('FAILED: the Nemerle engine library\n' + r.stdout + r.stderr)

(work / 'use.cs').write_text(
    'class P { static void Main() {\n'
    '  var e = new Engine();\n'
    '  System.Console.WriteLine(e.Add(2, 3));\n'
    '  System.Console.WriteLine(e.Greeting);\n'
    '  System.Console.WriteLine(string.Join(",", e.Names()));\n'
    '} }\n')
r = subprocess.run(['dotnet', str(csc), '-nologo', '-out:' + str(work / 'use.exe'),
                    '-r:' + str(work / 'engine.dll'), '-r:' + str(T / 'Nemerle.dll'),
                    *['-r:' + str(f) for f in sorted(a.references.glob('*.dll'))], str(work / 'use.cs')],
                   capture_output=True, text=True)
if r.returncode != 0:
    raise SystemExit('FAILED: C# compiling against the Nemerle engine\n' + r.stdout + r.stderr)
shutil.copy2(T / 'Nemerle.dll', work / 'Nemerle.dll')
shutil.copy2(T / 'ncc.runtimeconfig.json', work / 'use.runtimeconfig.json')
out = subprocess.run(['dotnet', str(work / 'use.exe')], capture_output=True, text=True).stdout.strip().splitlines()
if out != ['5', 'hi from Nemerle', 'a,b']:
    raise SystemExit('FAILED: C# calling a Nemerle class printed %r' % out)
print('PASS: C# calls a Nemerle class (method, property, a List[string] result)', flush=True)
