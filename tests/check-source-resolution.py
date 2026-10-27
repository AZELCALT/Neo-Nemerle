#!/usr/bin/env python3
"""Check standalone compiler and script lookup, including transitive imports and cache invalidation."""
import argparse
import pathlib
import shutil
import subprocess
import tempfile

p = argparse.ArgumentParser()
p.add_argument('--toolchain', type=pathlib.Path, required=True)
p.add_argument('--references', type=pathlib.Path, required=True)
a = p.parse_args()
tc = a.toolchain.resolve()
refs = a.references.resolve()
work = pathlib.Path(tempfile.mkdtemp(prefix='nemerle-source-resolution-'))
print('Resolution artifacts:', work, flush=True)
app = work / 'app'
app.mkdir()


def source(name, text):
    path = app / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + '\n')
    return path


def compile_run(source, expected):
    output = app / 'program.dll'
    result = subprocess.run(['dotnet', str(tc / 'ncc.exe'), str(source), '-out:' + str(output),
                             '-launcher-', '-target-references:' + str(refs), '-no-color'],
                            cwd=work, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0 and 'no .nproj' in result.stderr, result.stdout + result.stderr
    shutil.copy2(tc / 'Nemerle.dll', app / 'Nemerle.dll')
    shutil.copy2(tc / 'ncc.runtimeconfig.json', output.with_suffix('.runtimeconfig.json'))
    result = subprocess.run(['dotnet', str(output)], cwd=work, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0 and result.stdout.strip() == expected, result.stdout + result.stderr


source('util/tail.n', 'public Value() : int { 2 }')
source('util/helper.n', 'using tail;\npublic Value() : int { tail.Value() + 40 }')
main = source('main.n', 'using util.helper;\nSystem.Console.WriteLine(Value())')
compile_run(main, '42')
main.write_text('using util;\nSystem.Console.WriteLine(helper.Value())\n')
compile_run(main, '42')
source('greeting.n', 'register examples;\npublic Message() : string { "registered" }')
main.write_text('using examples.greeting;\nSystem.Console.WriteLine(Message())\n')
compile_run(main, 'registered')
entry = source('start.n', 'using util.helper;\nSystem.Console.WriteLine(Value())')
compile_run(entry, '42')
print('PASS: standalone warning, source-relative lookup, transitive imports, folder names and registration', flush=True)

source('System.n', 'public Unrelated() : int { 0 }')
script = source('run.ns', 'using System;\nusing util.helper;\nConsole.WriteLine(Value())')
cache = work / 'cache'


def script_run(expected):
    result = subprocess.run(['dotnet', str(tc / 'nscript.exe'), '--cache-dir', str(cache), 'run', str(script)],
                            cwd=work, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0 and result.stdout.strip() == expected, result.stdout + result.stderr
    assert 'no .nproj' not in result.stderr, result.stderr


script_run('42')
script_run('42')
source('neighbor.n', 'public Value() : int { 42 }')
(work / 'neighbor.n').write_text('public Value() : int { 999 }\n')
script.write_text('using neighbor;\nSystem.Console.WriteLine(Value())\n')
script_run('42')
script_run('42')
source('neighbor.n', 'public Value() : int { 43 }')
script_run('43')
script.write_text('using System;\nusing util.helper;\nConsole.WriteLine(Value())\n')
source('util/tail.n', 'public Value() : int { 3 }')
script_run('43')
script.write_text('using examples;\nSystem.Console.WriteLine(greeting.Message())\n')
script_run('registered')
source('waiting.n', 'using System.Threading.Tasks;\nawait Task.Yield();\npublic Value() : int { 7 }')
script.write_text('using waiting;\nSystem.Console.WriteLine(Value())\n')
script_run('7')
print('PASS: scripts discover local modules without warning, reuse cache, and invalidate after a transitive edit', flush=True)
