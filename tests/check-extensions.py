#!/usr/bin/env python3
"""Check `extension (recv : T) { ... }` blocks. Each function in the block becomes a plain function with the receiver
prepended (`F(recv : T, ...)`) and is called as an ordinary function (`F(obj, ...)`), never through a dot: an
extension is not a member of T, so it is not disguised as one. A block holds functions only, over one receiver. The
same in a file and in a script.
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
work = pathlib.Path(tempfile.mkdtemp(prefix='nemerle-extensions-'))
print('Extension artifacts:', work, flush=True)

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
    (s / 'e.ns').write_text(text)
    r = subprocess.run([str(T / 'nscript'), 'run', str(s / 'e.ns'), '--no-cache'], capture_output=True, text=True, timeout=120)
    return r.stdout.strip(), r.stdout + r.stderr

BLOCK = ('extension (s : string) { Shout() : string { s.ToUpper() } Twice() : int { s.Length * 2 } }\n'
         'extension (n : int) { Plus(k : int) : int { n + k } }\n')

# the functions are plain: called as F(obj, args), receiver prepended
out, log = compile_run('plain', BLOCK +
    'System.Console.WriteLine(Shout("hey"));\nSystem.Console.WriteLine(Twice("hey"));\nSystem.Console.WriteLine(Plus(5, 3))\n')
if out != 'HEY\n6\n8':
    raise SystemExit('FAILED: an extension function is called as a plain function\n%s\n%s' % (out, log[-800:]))
print('PASS: an extension function is a plain function with the receiver prepended (F(obj, args))', flush=True)

# the same in a script
out, log = run_script('script', BLOCK + 'System.Console.WriteLine(Shout("hi") + " " + Twice("hi").ToString())\n')
if out != 'HI 4':
    raise SystemExit('FAILED: extensions in a script\n%s\n%s' % (out, log[-800:]))
print('PASS: an extension block works in a script', flush=True)

# an extension is not a member: the dot does not reach it
out, log = compile_run('no-dot', BLOCK + 'System.Console.WriteLine("hey".Shout())\n')
if out is not None or "no member named `Shout'" not in log:
    raise SystemExit('FAILED: a dot must not reach an extension (it is not a member)\n%s' % log)
print('PASS: an extension is not reached through a dot (not disguised as a member)', flush=True)

# a block holds functions over one receiver
out, log = compile_run('field', 'extension (s : string) { mutable x : int; }\nSystem.Console.WriteLine(1)\n')
if out is not None or "an `extension' holds functions" not in log:
    raise SystemExit('FAILED: a non-function in an extension block is an error\n%s' % log)
print('PASS: an extension block holds functions, not fields/properties', flush=True)

out, log = compile_run('two', 'extension (s : string, n : int) { F() : int { n } }\nSystem.Console.WriteLine(1)\n')
if out is not None or "`extension' takes one receiver" not in log:
    raise SystemExit('FAILED: more than one receiver is an error\n%s' % log)
print('PASS: an extension block takes exactly one receiver', flush=True)
