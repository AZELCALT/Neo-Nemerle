#!/usr/bin/env python3
"""Compile and execute indentation syntax through the real compiler."""
import argparse
import pathlib
import shutil
import subprocess
import tempfile

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--toolchain', type=pathlib.Path, required=True)
p.add_argument('--references', type=pathlib.Path, required=True)
a = p.parse_args()
tc, refs = a.toolchain.resolve(), a.references.resolve()
work = pathlib.Path(tempfile.mkdtemp(prefix='nemerle-indent-'))
shutil.copy2(tc / 'Nemerle.dll', work)
print('Indentation artifacts:', work, flush=True)


def check(name, body, expected=None, error=None, extra=()):
    src = work / (name + '.n')
    src.write_text(body)
    output = src.with_suffix('.dll')
    result = subprocess.run([
        'dotnet', str(tc / 'ncc.exe'), str(src), '-no-color', '-launcher-',
        '-target-references:' + str(refs), '-out:' + str(output), *extra,
    ], capture_output=True, text=True, timeout=120)
    diagnostics = result.stdout + result.stderr
    if error:
        assert result.returncode != 0 and error in diagnostics, (name, diagnostics)
    else:
        assert result.returncode == 0, (name, diagnostics)
        shutil.copy2(tc / 'ncc.runtimeconfig.json', output.with_suffix('.runtimeconfig.json'))
        ran = subprocess.run(['dotnet', str(output)], capture_output=True, text=True, timeout=30)
        assert ran.returncode == 0 and ran.stdout.strip() == expected, (name, ran.stdout, ran.stderr)
    print('PASS:', name, flush=True)


check('blocks', '''#pragma indent
using System.Console;
Twice(n : int) : int:
    n * 2
mutable count : int = 0
while (count < 2):
    if (count == 0):
        WriteLine(Twice(21))
    else:
        WriteLine("second")
    count++
WriteLine("done")
''', '42\nsecond\ndone')
check('event_accessors', '''#pragma indent
class Signals:
    public event Changed : System.Action:
        add:
            System.Console.WriteLine("add")
        remove:
            System.Console.WriteLine("remove")
def signal = Signals()
def handler = System.Action(() => ())
signal.Changed += handler
signal.Changed -= handler
''', 'add\nremove')
check('comments', '''#pragma indent
when (true): // a block follows

    // blank and comment-only lines do not form its body
    System.Console.WriteLine("ok")
''', 'ok')
check('types', '''#pragma indent
class Box:
    public Value() : int:
        42
System.Console.WriteLine(Box().Value())
''', '42')
check('property', '''#pragma indent
class Box:
    mutable stored : int = 0
    public Value : int:
        get:
            stored
        set:
            stored = value
def box = Box()
box.Value = 42
System.Console.WriteLine(box.Value)
''', '42')
check('explicit_groups', '''#pragma indent
Value() : int { 42 }
def total = (
    Value() +
    1
)
when (true):
    System.Console.WriteLine(total)
''', '43')
check('legacy', '''#pragma indent
when (true)
    System.Console.WriteLine("legacy")
''', 'legacy')
check('match_and_handlers', '''#pragma indent
def answer = match (2):
    | 1 => 0
    | _ =>
        42
try:
    System.Console.WriteLine(answer)
    throw System.Exception("caught")
catch:
    | e is System.Exception =>
        System.Console.WriteLine(e.Message)
finally:
    System.Console.WriteLine("finally")
''', '42\ncaught\nfinally')
check('mask', '''#pragma indent
mask math:
    Twice(n : int) : int:
        n * 2
System.Console.WriteLine(math.Twice(21))
''', '42')
check('named_block', '''#pragma indent
Value() : int:
    def answer = finish:
        when (true):
            finish(42)
        0
    answer
System.Console.WriteLine(Value())
''', '42')
grammar = '''grammar G {
    using Nemerle.Compiler.Parsetree;
    syntax module Test {
        using Nitra.Core;
        [StartRule] syntax Start = "hello" {
            map PExpr = <[ System.Console.WriteLine("space") ]>;
        }
    }
}
'''
for header in ('space', 'space G', 'space (G)', 'space G as Example'):
    check('space_' + str(len(header)), '#pragma indent\n' + grammar + header + ''':
    hello
System.Console.WriteLine("outside")
''', 'space\noutside')
check('space_flag', grammar + 'space G:\n    hello\nSystem.Console.WriteLine("outside")\n',
      'space\noutside', extra=('-i',))
check('foreign_brace', '#pragma indent\n' + grammar.replace('syntax Start = "hello"', 'syntax Start = "hello" "}"') +
      'space G:\n    hello }\nSystem.Console.WriteLine("outside")\n', 'space\noutside')
check('empty_space', '#pragma indent\n' + grammar + 'space G:\n',
      error="expected an indented block after ':'")
check('space_bad_indent', '#pragma indent\n' + grammar + 'space G:\n    hello\n  hello\n',
      error='inconsistent indentation in space body')
check('flag', '''when (true):
    System.Console.WriteLine("flag")
''', 'flag', extra=('-i',))
for name, body in [
    ('same_level', 'when (true):\nSystem.Console.WriteLine("bad")\n'),
    ('empty_eof', 'when (true):'),
    ('comment_eof', 'when (true): // no body\n'),
    ('nested_empty', 'when (true):\n    when (true):\n    ()\n'),
]:
    check(name, '#pragma indent\n' + body, error="expected an indented block after ':'")
check('bad_dedent', '#pragma indent\nwhen (true):\n    ()\n  ()\n',
      error='inconsistent indentation')
check('mixed_prefix', '#pragma indent\nwhen (true):\n\twhen (true):\n        ()\n',
      error='inconsistent indentation')

script = work / 'script.ns'
script.write_text('''#pragma indent
using System.Console
Twice(n : int) : int:
    n * 2
when (true):
    WriteLine(Twice(21))
''')
ran = subprocess.run(['dotnet', str(tc / 'nscript.exe'), '--cache-dir', str(work / 'cache'),
                      'run', str(script)], capture_output=True, text=True, timeout=120)
assert ran.returncode == 0 and ran.stdout.strip() == '42', ran.stdout + ran.stderr
print('PASS: script runner uses the same indentation parser', flush=True)

(work / 'child.ns').write_text('''#pragma indent
public Next() : int:
    42
''')
script.write_text('''#pragma indent
[assembly: Import("child.ns")]
using C = child
when (true):
    System.Console.WriteLine(C.Next())
''')
ran = subprocess.run(['dotnet', str(tc / 'nscript.exe'), '--cache-dir', str(work / 'cache'),
                      'run', str(script)], capture_output=True, text=True, timeout=120)
assert ran.returncode == 0 and ran.stdout.strip() == '42', ran.stdout + ran.stderr
print('PASS: indented scripts support imported scripts and newline-terminated aliases', flush=True)
