#!/usr/bin/env python3
"""Check a module beside a folder of its name (`a.n` and `a/b.n`, as a Python package and its `__init__`).

`using a` opens `a.n` and reaches the folder's modules by their short names (`b.F()` is `a.b.F()`). In the binary the
folder's modules are nested in `a`'s class, so C# uses both (a type and a namespace of one name would be CS0434). A
module's `private` members are its own: the folder's modules reach only those it declares `hidden`.
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
work = pathlib.Path(tempfile.mkdtemp(prefix='nemerle-folder-modules-'))
print('Folder module artifacts:', work, flush=True)

def files(d, sources):
    for name, text in sources.items():
        (d / name).parent.mkdir(parents=True, exist_ok=True)
        (d / name).write_text(text)
    return [str(d / name) for name in sources]

def ncc(d, sources, *extra):
    r = subprocess.run([str(T / 'ncc'), *files(d, sources), '-source-root:' + str(d), '-no-color', *extra], capture_output=True, text=True)
    return r.returncode == 0, r.stdout + r.stderr

modules = {
    'a.n': ('public Hello() : string { "module a" }\n'
            'hidden Shared() : string { "shared with its folder" }\n'
            'private Secret() : string { "its own" }\n'
            'public Uses() : string { Secret() + ", " + b.Hello() }\n'),
    'a/b.n': 'public Hello() : string { "module a.b, " + a.Shared() }\n',
    'a/x/c.n': 'public Hello() : string { "module a.x.c" }\n',
}
program = dict(modules)
program['main.n'] = ('using a;\nSystem.Console.WriteLine(Hello());\nSystem.Console.WriteLine(b.Hello());\n'
                     'System.Console.WriteLine(x.c.Hello());\nSystem.Console.WriteLine(a.b.Hello());\nSystem.Console.WriteLine(Uses())\n')
d = work / 'program'
ok, log = ncc(d, program, '-out:' + str(d / 'main.exe'), '-launcher-')
if not ok: raise SystemExit('FAILED: a module beside a folder of its name\n' + log)
shutil.copy2(T / 'Nemerle.dll', d / 'Nemerle.dll')
shutil.copy2(T / 'ncc.runtimeconfig.json', d / 'main.runtimeconfig.json')
out = subprocess.run(['dotnet', str(d / 'main.exe')], capture_output=True, text=True).stdout.strip().splitlines()
expected = ['module a', 'module a.b, shared with its folder', 'module a.x.c', 'module a.b, shared with its folder',
            'its own, module a.b, shared with its folder']
if out != expected: raise SystemExit('FAILED: a module beside a folder of its name printed %r' % out)
print('PASS: `using a` opens a.n and reaches its folder\'s modules by their short names; a.b.F() as written', flush=True)

d = work / 'private'
bad = dict(modules)
bad['a/b.n'] = 'public Hello() : string { a.Secret() }\n'
ok, log = ncc(d, bad, '-target:library', '-out:' + str(d / 'lib.dll'))
if ok or "cannot access `a.Secret'" not in log:
    raise SystemExit('FAILED: a folder\'s module reaches its module\'s private member\n' + log)
print('PASS: a module\'s private members are its own; its folder\'s modules reach those it declares hidden', flush=True)

# C#: the folder's modules are nested in a's class, so a and a.b are both C#'s to use
sdk = None
for line in subprocess.run(['dotnet', '--list-sdks'], capture_output=True, text=True).stdout.splitlines():
    version, root = line.split(' ', 1)
    candidate = pathlib.Path(root.strip('[]')) / version / 'Roslyn' / 'bincore' / 'csc.dll'
    if candidate.exists(): sdk = candidate
if sdk is None:
    print('SKIP: no .NET SDK C# compiler to check the C# side')
    raise SystemExit(0)
d = work / 'csharp'
ok, log = ncc(d, modules, '-target:library', '-out:' + str(d / 'lib.dll'))
if not ok: raise SystemExit('FAILED: the modules as a library\n' + log)
(d / 'use.cs').write_text('class P { static void Main() { System.Console.WriteLine(a.Hello()); '
                          'System.Console.WriteLine(a.b.Hello()); System.Console.WriteLine(a.x.c.Hello()); } }\n')
r = subprocess.run(['dotnet', str(sdk), '-nologo', *['-r:' + str(f) for f in sorted(a.references.glob('*.dll'))],
                    '-r:' + str(d / 'lib.dll'), '-r:' + str(T / 'Nemerle.dll'), '-out:' + str(d / 'use.exe'), str(d / 'use.cs')],
                   capture_output=True, text=True)
if r.returncode != 0: raise SystemExit('FAILED: C# uses a module and its folder\'s modules\n' + r.stdout + r.stderr)
shutil.copy2(T / 'Nemerle.dll', d / 'Nemerle.dll')
shutil.copy2(T / 'ncc.runtimeconfig.json', d / 'use.runtimeconfig.json')
out = subprocess.run(['dotnet', str(d / 'use.exe')], capture_output=True, text=True).stdout.strip().splitlines()
if out != ['module a', 'module a.b, shared with its folder', 'module a.x.c']:
    raise SystemExit('FAILED: C# calling a.Hello(), a.b.Hello(), a.x.c.Hello() printed %r' % out)
print('PASS: C# uses a module and its folder\'s modules (a.Hello(), a.b.Hello(), a.x.c.Hello())')
