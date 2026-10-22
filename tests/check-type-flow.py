#!/usr/bin/env python3
"""Check the flow of values: a value's type, as a file and as a script (each case must print or fail the same).

A `def` has its value's type; a `mutable` written without a type has a type that follows the flow: after each
assignment its one type, and a set of types where the flow cannot know which (a branch, a loop, a lambda). A use must
fit each type of the set, or check first (`match`, `if (x is T)`), which picks those it handles. Code outside the
top-level code (a function, a lambda) checks a top-level value of several types before it uses it. `mutable x;` is
NotYet until each way to a read has assigned it. A name keeps its kind (def or mutable).
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
work = pathlib.Path(tempfile.mkdtemp(prefix='nemerle-type-flow-'))
print('Type flow artifacts:', work, flush=True)

W = 'System.Console.WriteLine'
YES = 'System.Environment.GetCommandLineArgs().Length > 0'   # true, as the compiler cannot know
AWAIT = 'await System.Threading.Tasks.Task.Yield();\n'
# (name, source, expected output, or the text of the expected error)
cases = [
    # linear: after each assignment, its one type
    ('linear', f'mutable x = 1;\n{W}(x + 1);\nx = "five";\n{W}(x.Length)\n', '2\n4', None),
    ('linear-local', f'Run() : void\n{{\n  mutable x = 1;\n  {W}(x + 1);\n  x = "five";\n  {W}(x.Length)\n}}\nRun()\n', '2\n4', None),
    # a branch that changes it on one way: a set; a use that fits each is fine, one that does not is an error
    ('branch-fits', f'mutable x = 1;\nwhen ({YES}) x = "one";\n{W}(x)\n', 'one', None),
    ('branch-misfit', f'mutable x = 1;\nwhen ({YES}) x = "one";\ndef y : int = x + 1;\n{W}(y)\n', None, "`x' can be"),
    # a check picks the types it handles
    ('narrow-match', f'mutable x = 1;\nwhen ({YES}) x = "one";\n{W}(match (x) {{ | n is int => n + 1 | s is string => s.Length }})\n', '3', None),
    ('narrow-if', f'Run() : void\n{{\n  mutable x = 1;\n  when ({YES}) x = "one";\n  if (x is string) {W}("a string") else {W}("an int")\n}}\nRun()\n', 'a string', None),
    # a loop: the types it may give, after it
    ('loop', f'Run() : void\n{{\n  mutable x = 0;\n  foreach (i in [1, 2, 3]) when (i == 2) x = "two";\n  {W}(x)\n}}\nRun()\n', 'two', None),
    # a lambda runs whenever it is called: it sees every type the value has
    ('lambda', f'Run() : void\n{{\n  mutable x = 1;\n  def show() {{ {W}(x) }}\n  show();\n  x = "one";\n  show()\n}}\nRun()\n', '1\none', None),
    # a function reads a top-level value whenever it runs: checked first
    ('function-unchecked', f'mutable x = 1;\nx = "one";\nLen() : int {{ x.Length }}\n{W}(Len())\n', None, 'is a top-level value of several types'),
    ('function-match', f'mutable x = 1;\nx = "one";\nLen() : int {{ match (x) {{ | s is string => s.Length | _ => 0 }} }}\n{W}(Len())\n', '3', None),
    ('function-if', f'mutable x = 1;\nx = "one";\nLen() : int {{ if (x is string) x.Length else 0 }}\n{W}(Len())\n', '3', None),
    # a function that assigns a top-level value: the top-level code reads it back after the call
    ('writer', f'mutable count = 0;\nInc() : void {{ count++ }}\nInc();\nInc();\n{W}(count)\n', '2', None),
    # a `def' bound again: a new value, of its own type
    ('redefined', f'def y = 5;\ndef y = y.ToString() + "0";\n{W}(y.Length)\n', '2', None),
    ('redefined-function', f'def y = 5;\ndef y = y.ToString();\nTwice() : int {{ y * 2 }}\n{W}(Twice())\n', None, 'is a top-level value of several types'),
    # a type written down is the type
    ('typed', f'mutable x : int = 1;\nx = "one";\n{W}(x)\n', None, 'expected int'),
    # a name keeps its kind
    ('kind', f'Run() : void {{ def a = 1; mutable a = 2; {W}(a) }}\nRun()\n', None, 'keeps its kind'),
    # `mutable x;' is NotYet until each way to a read gives it a value
    ('notyet', f'Run() : void {{ mutable x; {W}(x) }}\nRun()\n', None, 'is NotYet here'),
    ('notyet-one-way', f'Run(c : bool) : void {{ mutable x; when (c) x = 1; {W}(x) }}\nRun(true)\n', None, 'is NotYet here'),
    ('notyet-out', f'Run() : void {{ mutable x; _ = int.TryParse("5", out x); {W}(x + 1) }}\nRun()\n', '6', None),
    ('notyet-do', f'Run() : void {{ mutable x; do {{ x = 3 }} while (false); {W}(x) }}\nRun()\n', '3', None),
    ('notyet-function', f'mutable x;\nx = 5;\nF() : int {{ x }}\n{W}(F())\n', '5', None),
    # the same in code that waits (an async file's top-level code, a waiting script)
    ('async-linear', f'mutable x = 1;\n{AWAIT}x = "one";\n{W}(x.Length)\n', '3', None),
    ('async-lambda', f'mutable x = 1;\n{AWAIT}x = "one";\ndef show = () => {W}(x);\nx = 2;\nshow()\n', None, 'is a top-level value of several types'),
    # (an error in code that waits is reported once: its typed-only copy does not report it again)
    ('async-type-error', f'{AWAIT}def n : int = "text";\n{W}(n)\n', None, 'expected int'),
    ('async-lambda-checked', f'mutable x = 1;\n{AWAIT}x = "one";\ndef show = () => match (x) {{ | s is string => {W}(s) | n is int => {W}(n) }};\nx = 2;\nshow()\n', '2', None),
]

def compile_file(name, text):
    d = work / 'file' / name
    d.mkdir(parents=True)
    (d / 'main.n').write_text(text)
    r = subprocess.run([str(T / 'ncc'), str(d / 'main.n'), '-source-root:' + str(d), '-out:' + str(d / 'main.exe'), '-launcher-',
                        '-no-color'], capture_output=True, text=True)
    if r.returncode != 0:
        return None, r.stdout + r.stderr
    shutil.copy2(T / 'Nemerle.dll', d / 'Nemerle.dll')
    shutil.copy2(T / 'ncc.runtimeconfig.json', d / 'main.runtimeconfig.json')
    run = subprocess.run(['dotnet', str(d / 'main.exe')], capture_output=True, text=True, timeout=60)
    return run.stdout.strip(), run.stderr

def run_script(name, text):
    d = work / 'script' / name
    d.mkdir(parents=True)
    script = d / (name.replace('-', '_') + '.ns')   # (a script's file name is its module's)
    script.write_text(text)
    r = subprocess.run([str(T / 'nscript'), 'run', str(script), '--no-cache'], capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        return None, r.stdout + r.stderr
    return r.stdout.strip(), r.stderr

failures = []
for name, text, expected, error in cases:
    for kind, runner in (('file', compile_file), ('script', run_script)):
        output, messages = runner(name, text)
        if error is not None:
            if output is not None or error not in messages:
                failures.append('%s as a %s: expected the error %r, got %r %r' % (name, kind, error, output, messages[-400:]))
            elif messages.count(error) != 1:
                failures.append('%s as a %s: the error %r is reported %d times' % (name, kind, error, messages.count(error)))
        elif output != expected:
            failures.append('%s as a %s: printed %r, expected %r\n%s' % (name, kind, output, expected, messages[-600:]))
if failures:
    raise SystemExit('FAILED:\n' + '\n'.join(failures))
print('PASS: %d cases of the flow of values print or fail the same as files and as scripts' % len(cases))
