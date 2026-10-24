#!/usr/bin/env python3
"""Exercise registered file identities and folder lookup through the real CLR compiler."""
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
work = pathlib.Path(tempfile.mkdtemp(prefix='nemerle-logical-modules-'))
print('Logical module artifacts:', work, flush=True)
shutil.copy2(tc / 'Nemerle.dll', work / 'Nemerle.dll')


def source(name, text):
    path = work / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + '\n')
    return path


def compile(name, files, *, library=False, references=(), error=None, extra=()):
    output = work / (name + '.dll')
    result = subprocess.run(['dotnet', str(tc / 'ncc.exe'), *map(str, files),
                             '-source-root:' + str(work), '-target-references:' + str(refs),
                             '-out:' + str(output), '-launcher-', '-no-color',
                             *(['-target:library'] if library else []),
                             *['-r:' + str(r) for r in references], *extra],
                            cwd=work, capture_output=True, text=True, timeout=120)
    said = result.stdout + result.stderr
    if error:
        assert result.returncode != 0 and error in said, (name, said)
    else:
        assert result.returncode == 0, (name, said)
        shutil.copy2(tc / 'ncc.runtimeconfig.json', output.with_suffix('.runtimeconfig.json'))
    return output


def prints(output, expected):
    result = subprocess.run(['dotnet', str(output)], cwd=work, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0 and result.stdout.strip() == expected, result.stdout + result.stderr


text = source('implementation/text.n', '/* header */\nregister library.words;\n'
              'public Shout(s : string) : string { s.ToUpper() }\npublic class Box {}')
main = source('main.n', 'using library.words.text;\nSystem.Console.WriteLine(Shout("hello"))')
prints(compile('registered', [main, text]), 'HELLO')
moved = work / 'moved/text.n'
moved.parent.mkdir()
text.rename(moved)
prints(compile('moved', [moved, main]), 'HELLO')
main.write_text('using library.words;\nSystem.Console.WriteLine(text.Shout("hello"));\n'
                'def b : text.Box = text.Box();\nSystem.Console.WriteLine(b != null)\n')
prints(compile('folder', [main, moved]), 'HELLO\nTrue')
bad = source('bad.n', 'using library.words;\nSystem.Console.WriteLine(Shout("hello"))')
compile('no_bare_members', [bad, moved], error='Shout')
bad.write_text('System.Console.WriteLine(moved.text.Shout("hello"))\n')
compile('no_old_identity', [bad, moved], error='moved')
deep = source('nested/deeper.n', 'register library.words.deep;\npublic Value() : int { 7 }')
bad.write_text('using library.words;\nSystem.Console.WriteLine(deeper.Value())\n')
compile('not_recursive', [bad, moved, deep], error='deeper')
bad.write_text('using missing;\nSystem.Console.WriteLine(missing.Value())\n')
compile('missing_folder', [bad], error='missing')
bad.write_text('using library.words;\nSystem.Console.WriteLine(1)\n')
prints(compile('ordinary_directory', [bad, moved], extra=['-main:bad']), '1')
duplicate = source('duplicate/text.n', 'register library.words;\npublic Other() : int { 1 }')
compile('duplicate_identity', [moved, duplicate], library=True, error='duplicate file module identity')
for name, body, message in [
    ('twice', 'register other;\nregister other;\npublic Value() : int { 1 }', 'exactly one logical folder'),
    ('two_folders', 'register other;\nregister another;\npublic Value() : int { 1 }', 'first directive'),
    ('late', 'using System;\nregister other;\npublic Value() : int { 1 }', 'first directive'),
    ('block', 'register other { public Value() : int { 1 } }', 'without a block'),
]:
    compile(name, [source(name + '.n', body)], library=True, error=message)

# Folder qualification and identity survive separate compilation, including module initialization.
first = source('physical/first.n', 'register packaged;\nSystem.Console.WriteLine("first");\n'
               'public def answer = 40;\npublic Value() : int { answer }')
second = source('physical/second.n', 'register packaged;\nSystem.Console.WriteLine("second");\n'
                'public Value() : int { 2 }')
binary = compile('logical_library', [second, first, moved], library=True)
main.write_text('using packaged;\nusing library.words;\n'
                'System.Console.WriteLine(first.Value() + second.Value());\n'
                'System.Console.WriteLine(packaged.first.answer);\nSystem.Console.WriteLine(text.Shout("ok"))\n')
prints(compile('binary_folder', [main], references=[binary]), 'first\nsecond\n42\n40\nOK')

# Registered main files still use physical entry-file selection, including explicit -main.
main.write_text('register app;\nSystem.Console.WriteLine("entry")\n')
prints(compile('registered_main', [main, moved]), 'entry')
entry = source('entry/start.n', 'register app;\nSystem.Console.WriteLine("selected")')
prints(compile('selected_main', [entry, moved], extra=['-main:entry.start']), 'selected')

# Ordinary namespace/module names called `folder` remain legal.
ordinary = source('folder.n', 'public Value() : int { 8 }')
main.write_text('using folder;\nSystem.Console.WriteLine(Value())\n')
prints(compile('ordinary_folder_name', [main, ordinary]), '8')
physical = source('plain/member.n', 'public Value() : int { 9 }')
main.write_text('using plain;\nSystem.Console.WriteLine(member.Value())\n')
prints(compile('physical_folder', [main, physical]), '9')
print('PASS: registration, relocation, qualified folder lookup, library metadata, initialization and diagnostics', flush=True)

# Logical module names are ordinary CLR names for C# callers too.
version, sdk = subprocess.check_output(['dotnet', '--list-sdks'], text=True).splitlines()[-1].split(' ', 1)
csc = pathlib.Path(sdk.strip('[]')) / version / 'Roslyn/bincore/csc.dll'
consumer = source('Consumer.cs', 'class Consumer { static void Main() { '
                  'System.Console.WriteLine(library.words.text.Shout("clr")); } }')
output = work / 'Consumer.dll'
result = subprocess.run(['dotnet', str(csc), '-nologo', '-nostdlib+', '-target:exe',
                         '-out:' + str(output), *['-r:' + str(r) for r in refs.glob('*.dll')],
                         '-r:' + str(binary), '-r:' + str(tc / 'Nemerle.dll'), str(consumer)],
                        cwd=work, capture_output=True, text=True, timeout=60)
assert result.returncode == 0, result.stdout + result.stderr
shutil.copy2(tc / 'ncc.runtimeconfig.json', output.with_suffix('.runtimeconfig.json'))
prints(output, 'CLR')
print('PASS: C# consumes the registered module through its CLR name', flush=True)

# Scripting uses the same folder resolution against a referenced library.
script = source('folder_script.ns', '[assembly: DependsOn("logical_library.dll")]\n'
                'using library.words;\nSystem.Console.WriteLine(text.Shout("script"))')
result = subprocess.run(['dotnet', str(tc / 'nscript.exe'), '--cache-dir', str(work / 'cache'),
                         'run', str(script)], cwd=work, capture_output=True, text=True, timeout=120)
assert result.returncode == 0 and result.stdout.strip() == 'SCRIPT', result.stdout + result.stderr
print('PASS: nscript resolves a registered library through ordinary using', flush=True)

# Generated guidance and project source discovery use the same semantics.
project = work / 'project'
result = subprocess.run(['dotnet', str(tc / 'ncc.exe'), 'init', str(project)], cwd=work,
                        capture_output=True, text=True, timeout=30)
assert result.returncode == 0, result.stdout + result.stderr
config = (project / 'project.nproj').read_text()
assert 'register library.words;' in config and 'using library.words;' in config, config
(project / 'main.n').write_text('using example;\nSystem.Console.WriteLine(greeting.Message())\n')
helper = project / 'old' / 'greeting.n'
helper.parent.mkdir()
helper.write_text('register example;\npublic Message() : string { "project" }\n')
for move in (False, True):
    if move:
        (project / 'new').mkdir()
        helper.rename(project / 'new' / helper.name)
    result = subprocess.run(['dotnet', str(tc / 'ncc.exe'), 'run', str(project), '-launcher-',
                             '-target-references:' + str(refs)], cwd=work,
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0 and result.stdout.strip().endswith('project'), result.stdout + result.stderr
result = subprocess.run(['dotnet', str(tc / 'ncc.exe'), 'build', str(work / 'empty')], cwd=work,
                        capture_output=True, text=True, timeout=30)
assert result.returncode != 0 and 'no project' in result.stderr and 'ncc init' in result.stderr, result.stderr
print('PASS: init guidance, automatic project sources, relocation and missing-project diagnostic', flush=True)
