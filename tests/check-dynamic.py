#!/usr/bin/env python3
"""Check `dynamic` values (a C# member typed `dynamic`: .NET's object marked [Dynamic]): their type is not known at
all, so every use is checked first. Binding one to a name, matching on it (`match`, `is`) and converting it (`:>`) are
the checks; anything else touching it (a member, an argument, an operator, an assignment, a result, in a lambda too)
is an error, in files and scripts, in functions and in top-level code.
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
work = pathlib.Path(tempfile.mkdtemp(prefix='nemerle-dynamic-'))
print('Dynamic artifacts:', work, flush=True)

# the C# library: members typed `dynamic`, and one only part of whose type is
sdks = subprocess.run(['dotnet', '--list-sdks'], capture_output=True, text=True).stdout.split()
csc = None
for line in subprocess.run(['dotnet', '--list-sdks'], capture_output=True, text=True).stdout.splitlines():
    version, root = line.split(' ', 1)
    candidate = pathlib.Path(root.strip('[]')) / version / 'Roslyn' / 'bincore' / 'csc.dll'
    if candidate.exists(): csc = candidate
if csc is None:
    print('SKIP: no .NET SDK C# compiler to build the library with `dynamic` members')
    raise SystemExit(0)
(work / 'Api.cs').write_text('using System.Collections.Generic;\npublic static class Api\n{\n'
    '    public static dynamic Get(int n) => n > 0 ? (object)"text" : 42;\n'
    '    public static dynamic Field = 3.5;\n'
    '    public static dynamic Prop => new List<int> { 1, 2 };\n'
    '    public static List<dynamic> Parts => new List<dynamic> { 1 };\n'
    '    public static object Plain() => "plain";\n}\n')
subprocess.run(['dotnet', str(csc), '-nologo', '-target:library', '-out:' + str(work / 'Api.dll'),
                *['-r:' + str(r) for r in sorted(a.references.glob('*.dll'))], str(work / 'Api.cs')], check=True)

def compile(name, text):
    d = work / name
    d.mkdir()
    (d / 'main.n').write_text(text)
    r = subprocess.run([str(T / 'ncc'), str(d / 'main.n'), '-source-root:' + str(d), '-out:' + str(d / 'main.exe'),
                        '-launcher-', '-no-color', '-r:' + str(work / 'Api.dll')], capture_output=True, text=True)
    return d, r.returncode == 0, r.stdout + r.stderr

# the checks: a binding, a match (an `is'), a conversion; a part of a type that is dynamic is not checked
d, ok, log = compile('checked', 'def d = Api.Get(1);\ndef text = match (d) { | s is string => s.Length | n is int => n | _ => -1 };\n'
    'def f = Api.Field :> double;\ndef plain = match (Api.Prop) { | o => o };\ndef items = Api.Parts;\n'
    'Count() : int { match (d) { | s is string => s.Length | _ => 0 } }\n'
    'System.Console.WriteLine($"$text $f $(plain != null) $(items.Count) $(Count()) $(Api.Plain())")\n')
if not ok: raise SystemExit('FAILED: the checks of dynamic values\n' + log)
for f in (work / 'Api.dll', T / 'Nemerle.dll'): shutil.copy2(f, d / f.name)
shutil.copy2(T / 'ncc.runtimeconfig.json', d / 'main.runtimeconfig.json')
out = subprocess.run(['dotnet', str(d / 'main.exe')], capture_output=True, text=True).stdout.strip()
if out != '4 3.5 True 1 4 plain': raise SystemExit('FAILED: the checks of dynamic values printed %r' % out)
print('PASS: a dynamic value is bound, matched and converted (in top-level code and a function reading it)', flush=True)

# every other use is an error, each where it is
uses = [('an argument', 'System.Console.WriteLine(d);'), ('a member', 'def s = d.ToString();'),
        ('a call\'s value', 'def g = Api.Get(0).GetHashCode();'), ('an assignment', 'mutable m = null : object;\nm = Api.Field;'),
        ('an operator', 'def w = Api.Prop == null;'), ('a result', 'F() : object { Api.Get(2) }'),
        ('a lambda', 'def l = () => d.Equals(1);'), ('a function', 'G() : int { def x = Api.Get(1); x.GetHashCode() }')]
d, ok, log = compile('unchecked', 'def d = Api.Get(1);\n' + '\n'.join(text for _, text in uses) + '\n_ = (s, g, m, w, l);\n()\n')
reported = [l for l in log.splitlines() if 'is dynamic: its type is not known here' in l]
if ok or len(reported) != len(uses):
    raise SystemExit('FAILED: each unchecked use of a dynamic value is an error (%d of %d)\n%s' % (len(reported), len(uses), log))
print('PASS: each unchecked use of a dynamic value is an error (%s)' % ', '.join(n for n, _ in uses), flush=True)

# a script: the same
s = work / 'script'
s.mkdir()
shutil.copy2(work / 'Api.dll', s / 'Api.dll')
(s / 'uses.ns').write_text('[assembly: DependsOn("Api.dll")]\ndef d = Api.Get(1);\n'
                           'System.Console.WriteLine(match (d) { | t is string => t | _ => "?" });\n')
r = subprocess.run([str(T / 'nscript'), 'run', str(s / 'uses.ns'), '--no-cache'], capture_output=True, text=True, timeout=120)
if r.stdout.strip() != 'text': raise SystemExit('FAILED: a script checks a dynamic value\n' + r.stdout + r.stderr)
(s / 'blind.ns').write_text('[assembly: DependsOn("Api.dll")]\ndef d = Api.Get(1);\nSystem.Console.WriteLine(d.ToString())\n')
r = subprocess.run([str(T / 'nscript'), 'run', str(s / 'blind.ns'), '--no-cache'], capture_output=True, text=True, timeout=120)
if r.returncode == 0 or (r.stdout + r.stderr).count('is dynamic: its type is not known here') != 1:
    raise SystemExit('FAILED: a script\'s unchecked use of a dynamic value\n' + r.stdout + r.stderr)
print('PASS: a script checks a dynamic value, and an unchecked use is its error')
