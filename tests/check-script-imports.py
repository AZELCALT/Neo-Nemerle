#!/usr/bin/env python3
"""Exercise ordinary .n using and script .ns import through the real runner."""
import argparse
import json
import pathlib
import shutil
import subprocess
import tempfile

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--toolchain', type=pathlib.Path, required=True)
p.add_argument('--server', type=pathlib.Path, help='also check script diagnostics through the language server')
a = p.parse_args()
tc = a.toolchain.resolve()
work = pathlib.Path(tempfile.mkdtemp(prefix='nemerle script imports '))
scripts = work / 'scripts'
scripts.mkdir()
print('Script import artifacts:', work, flush=True)


def source(name, text):
    path = scripts / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + '\n')
    return path


def run(path, expected=None, error=None, command='run', extra=()):
    r = subprocess.run(['dotnet', str(tc / 'nscript.exe'), '--cache-dir', str(work / 'cache'),
                        command, str(path), *map(str, extra)], cwd=work,
                       capture_output=True, text=True, timeout=120)
    if error:
        assert r.returncode != 0 and error in r.stdout + r.stderr, r.stdout + r.stderr
    else:
        assert r.returncode == 0 and r.stdout.strip() == expected, r.stdout + r.stderr


child = source('counter.ns', 'mutable count : int = 0;\nSystem.Console.WriteLine("ready");\n'
               'public Next() : int { count++; count }\nprivate Hidden() : int { 99 }')
main = source('main.ns', 'import counter;\nSystem.Console.WriteLine(Next());\nSystem.Console.WriteLine(counter.Next())')
run(main, 'ready\n1\n2')
run(main, 'ready\n1\n2')
child.write_text(child.read_text().replace('count++; count', 'count += 2; count'))
run(main, 'ready\n2\n4')
print('PASS: short imports open public names, share child state and invalidate cached parents', flush=True)

source('local.n', 'public Twice(x : int) : int { x * 2 }')
source('local.ns', 'public Twice(x : int) : int { 999 }')
main.write_text('using local;\nimport counter;\nSystem.Console.WriteLine(Twice(21));\nSystem.Console.WriteLine(Next())\n')
run(main, 'ready\n42\n2')
source('tools/numbers.ns', 'public Answer() : int { 42 }')
(work / 'numbers.ns').write_text('public Answer() : int { 999 }\n')
for directive in ('import tools.numbers;', 'import "tools/numbers.ns";', 'import /* header */ tools.numbers;'):
    main.write_text(directive + '\nSystem.Console.WriteLine(Answer());\nSystem.Console.WriteLine(numbers.Answer())\n')
    run(main, '42\n42')
main.write_text('#pragma indent\nimport tools.numbers\nwhen (true):\n    System.Console.WriteLine(Answer())\n')
run(main, '42')
print('PASS: .n using, dotted/quoted paths, comments, caller-relative lookup and indentation', flush=True)

main.write_text('import tools.numbers;\nSystem.Console.WriteLine(Answer())\n')
artifact = work / 'saved.dll'
run(main, '', command='compile', extra=(artifact,))
relocated = work / 'relocated'
relocated.mkdir()
for path in (artifact, pathlib.Path(str(artifact) + '.script')):
    shutil.copy2(path, relocated / path.name)
shutil.copytree(str(artifact) + '.dependencies', relocated / (artifact.name + '.dependencies'))
source('tools/numbers.ns', 'public Answer() : int { 17 }')
run(relocated / artifact.name, '42', command='run-compiled')
run(main, '17')
print('PASS: saved imports relocate independently and source runs see later dependency edits', flush=True)

for text, message in [
    ('import "local.n";', 'use using for .n sources'),
    ('import "library.dll";', 'DependsOn for assemblies'),
    ('import tools.;', 'Expected a script name'),
    ('import counter\nSystem.Console.WriteLine(1)', "Expected ';'"),
    ('import missing;', 'missing.ns'),
    ('import counter;\nSystem.Console.WriteLine(Hidden())', 'Hidden'),
    ('import counter;\nimport "counter.ns";', 'Duplicate script import'),
]:
    main.write_text(text + '\n')
    run(main, error=message)
source('cycle.ns', 'import cycle;\n()')
main.write_text('import cycle;\n()\n')
run(main, error='Cyclic script import')
main.write_text('def text = "import missing;";\nSystem.Console.WriteLine(text)\n')
run(main, 'import missing;')
main.write_text('import(x : int) : int { x + 1 }\nSystem.Console.WriteLine(import(41))\n')
run(main, '42')
main.write_text('[assembly: Import("counter.ns")]\nSystem.Console.WriteLine(counter.Next())\n')
run(main, 'ready\n2')
print('PASS: diagnostics, privacy, cycles, ordinary identifiers and legacy metadata compatibility', flush=True)

repl = subprocess.run(['dotnet', str(tc / 'nscript.exe'), '--cache-dir', str(work / 'cache'),
                       'repl', '--history', str(work / 'history')],
                      cwd=scripts, input='import counter;\nNext()\nNext()\n:quit\n',
                      capture_output=True, text=True, timeout=120)
assert repl.returncode == 0 and repl.stdout.strip() == 'ready\n2\n4', repl.stdout + repl.stderr
print('PASS: CLI REPL imports retain public names and child state across submissions', flush=True)

if a.server:
    for extension in ('.ns', '.n'):
        text = 'import counter;\ndef bad : string = Next();\n'
        path = source('editor' + extension, text)
        request = {'root': str(scripts), 'references': str(tc / 'references'),
                   'files': [{'path': str(path), 'text': text}], 'fileNameNamespaces': True}
        result = subprocess.run([str(a.server.resolve()), '--check'], input=json.dumps(request),
                                capture_output=True, text=True, timeout=120)
        assert result.returncode == 0, result.stdout + result.stderr
        errors = [d for d in json.loads(result.stdout)['diagnostics'] if d['severity'] == 1]
        assert len(errors) == 1 and errors[0]['line'] == 2 and 'string' in errors[0]['message'], errors
    print('PASS: .ns and script .n imports receive correctly located editor diagnostics without execution', flush=True)
