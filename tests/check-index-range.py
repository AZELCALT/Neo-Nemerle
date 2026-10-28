#!/usr/bin/env python3
"""Check C#'s index-from-end `#n` and range `i..j`. `#n` is a `System.Index` counted from the end; `i..j` is a
`System.Range` (either bound may be `#k`). Indexing an array or string with one reads from the end (`a[#1]` is the
last) or slices (`a[1..3]` copies a sub-array, `s[1..3]` a Substring). Plain integer indexing is unchanged.
"""
import argparse
import pathlib
import shutil
import subprocess
import tempfile

p = argparse.ArgumentParser()
p.add_argument('--toolchain', type=pathlib.Path, required=True)
a = p.parse_args()
T = a.toolchain.resolve()
work = pathlib.Path(tempfile.mkdtemp(prefix='nemerle-index-range-'))
print('Index/range artifacts:', work, flush=True)

def compile_run(name, text):
    d = work / name
    d.mkdir()
    (d / 'main.n').write_text(text)
    r = subprocess.run([str(T / 'ncc'), str(d / 'main.n'), '-source-root:' + str(d), '-out:' + str(d / 'main.exe'),
                        '-launcher-', '-no-color'], capture_output=True, text=True)
    if r.returncode != 0 or not (d / 'main.exe').exists():
        return None, r.stdout + r.stderr
    shutil.copy2(T / 'Nemerle.dll', d / 'Nemerle.dll')
    shutil.copy2(T / 'ncc.runtimeconfig.json', d / 'main.runtimeconfig.json')
    out = subprocess.run(['dotnet', str(d / 'main.exe')], capture_output=True, text=True).stdout.strip()
    return out, r.stdout + r.stderr

def run_script(name, text):
    s = work / name
    s.mkdir()
    (s / 'r.ns').write_text(text)
    r = subprocess.run([str(T / 'nscript'), 'run', str(s / 'r.ns'), '--no-cache'], capture_output=True, text=True, timeout=120)
    return r.stdout.strip(), r.stdout + r.stderr

# #n and i..j are first-class System.Index / System.Range
out, log = compile_run('values', 'def i = #1;\ndef r = 1 .. 3;\n'
    'System.Console.WriteLine($"$(i.IsFromEnd) $(i.Value) $(r.Start.Value) $(r.End.Value)")\n')
if out != 'True 1 1 3':
    raise SystemExit('FAILED: #n is a System.Index, i..j a System.Range\n%s\n%s' % (out, log[-800:]))
print('PASS: `#n` is a System.Index from the end, `i..j` a System.Range', flush=True)

# arrays: from-end reads, ranges copy a sub-array
out, log = compile_run('array', 'def a = array[10, 20, 30, 40];\n'
    'def mid = a[1 .. 3];\ndef tail = a[1 .. #1];\n'
    'System.Console.WriteLine($"$(a[#1]) $(a[#2]) $(mid.Length):$(mid[0]):$(mid[1]) $(tail.Length)")\n')
if out != '40 30 2:20:30 2':
    raise SystemExit('FAILED: array index-from-end and range\n%s\n%s' % (out, log[-800:]))
print('PASS: an array reads from the end (`a[#1]`) and slices (`a[1..3]`, `a[1..#1]`)', flush=True)

# strings: from-end char, range Substring
out, log = compile_run('string', 'def s = "hello";\n'
    'System.Console.WriteLine($"$(s[#1]) $(s[1 .. 3]) $(s[1 .. #1])")\n')
if out != 'o el ell':
    raise SystemExit('FAILED: string index-from-end and range\n%s\n%s' % (out, log[-800:]))
print('PASS: a string reads from the end (`s[#1]`) and slices (`s[1..3]`, `s[1..#1]`)', flush=True)

# plain integer indexing is unchanged
out, log = compile_run('plain', 'def a = array[5, 6, 7];\ndef i = 1;\ndef s = "abc";\n'
    'System.Console.WriteLine($"$(a[i]) $(a[0]) $(s[0]) $(s[2])")\n')
if out != '6 5 a c':
    raise SystemExit('FAILED: plain integer indexing is unchanged\n%s\n%s' % (out, log[-800:]))
print('PASS: plain integer indexing is unchanged', flush=True)

# the same in a script
out, log = run_script('script', 'def a = array[1, 2, 3, 4];\nSystem.Console.WriteLine($"$(a[#1]) $(a[0 .. 2].Length)")\n')
if out != '4 2':
    raise SystemExit('FAILED: index-from-end and range in a script\n%s\n%s' % (out, log[-800:]))
print('PASS: index-from-end and range work in a script', flush=True)
