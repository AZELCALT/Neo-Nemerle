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
    ('same-type-loop', f'Run() : void {{ mutable x = 0; foreach (i in [1, 2, 3]) x += i; {W}(x) }}\nRun()\n', '6', None),
    ('same-type-capture', f'Run() : void {{ mutable x = 0; def inc() {{ x = x + 1 }} inc(); inc(); {W}(x) }}\nRun()\n', '2', None),
    ('same-type-out', f'Run() : void {{ mutable x = 0; _ = int.TryParse("5", out x); {W}(x) }}\nRun()\n', '5', None),
    ('empty-list', f'Run() : void {{ mutable xs = []; xs ::= 1; xs ::= 2; {W}(xs.Head + xs.Tail.Head) }}\nRun()\n', '3', None),
    ('same-type-check', f'Run() : void {{ mutable x = 1; {W}(match (x) {{ | n is int => n + 1 | _ => 0 }}) }}\nRun()\n', '2', None),
    ('same-type-span', f'Run() : void {{ def a = array[1, 2]; mutable s = System.Span.[int](a); s[0] = 3; {W}(s[0]) }}\nRun()\n', '3', None),
    ('copied-set', f'Run() : void {{ mutable x = 1; when ({YES}) x = "one"; def y = x; {W}(match (y) {{ | s is string => s.Length | _ => 0 }}) }}\nRun()\n', '3', None),
    ('changing-out', f'Run() : void {{ mutable x = 1; _ = int.TryParse("5", out x); x = "one"; {W}(x) }}\nRun()\n', None, 'has several types in this scope'),
    # a branch that changes it on one way: a set; a use that fits each is fine, one that does not is an error
    ('branch-fits', f'mutable x = 1;\nwhen ({YES}) x = "one";\n{W}(x)\n', 'one', None),
    ('branch-misfit', f'mutable x = 1;\nwhen ({YES}) x = "one";\ndef y = x * 2;\n{W}(y)\n', None,
     "this does not fit `x' when it is string: `x' is int or string here (int from line 1, string from line 2)"),
    ('branch-differs', f'mutable x = 1;\nwhen ({YES}) x = "one";\ndef y = x + 1;\n{W}(y)\n', None,
     "this gives another type for each type of `x' (int when it is int, string when it is string)"),
    # a check picks the types it handles
    ('narrow-match', f'mutable x = 1;\nwhen ({YES}) x = "one";\n{W}(match (x) {{ | n is int => n + 1 | s is string => s.Length }})\n', '3', None),
    ('narrow-if', f'Run() : void\n{{\n  mutable x = 1;\n  when ({YES}) x = "one";\n  if (x is string) {W}("a string") else {W}("an int")\n}}\nRun()\n', 'a string', None),
    # a loop: the types it may give, after it
    ('loop', f'Run() : void\n{{\n  mutable x = 0;\n  foreach (i in [1, 2, 3]) when (i == 2) x = "two";\n  {W}(x)\n}}\nRun()\n', 'two', None),
    # a lambda runs whenever it is called: it sees every type the value has
    ('lambda', f'Run() : void\n{{\n  mutable x = 1;\n  def show() {{ {W}(x) }}\n  show();\n  x = "one";\n  show()\n}}\nRun()\n', '1\none', None),
    # a function reads a top-level value whenever it runs: checked first
    ('function-unchecked', f'mutable x = 1;\nx = "one";\nLen() : int {{ x.Length }}\n{W}(Len())\n', None, 'it is a top-level value, and this code can run at any time'),
    ('function-match', f'mutable x = 1;\nx = "one";\nLen() : int {{ match (x) {{ | s is string => s.Length | _ => 0 }} }}\n{W}(Len())\n', '3', None),
    ('function-if', f'mutable x = 1;\nx = "one";\nLen() : int {{ if (x is string) x.Length else 0 }}\n{W}(Len())\n', '3', None),
    # a function that assigns a top-level value: the top-level code reads it back after the call
    ('writer', f'mutable count = 0;\nInc() : void {{ count++ }}\nInc();\nInc();\n{W}(count)\n', '2', None),
    # a `def' bound again: a new value, of its own type
    ('redefined', f'def y = 5;\ndef y = y.ToString() + "0";\n{W}(y.Length)\n', '2', None),
    ('redefined-function', f'def y = 5;\ndef y = y.ToString();\nTwice() : int {{ y * 2 }}\n{W}(Twice())\n', None, "`y' is int or string"),
    # the operators that assign (`+=', `++') assign a value of another type as `=' does
    ('compound', f'mutable v = 0;\nv += 1;\nv++;\nv = "s" + v.ToString();\nv += "!";\n{W}(v)\n', 's2!', None),
    ('compound-local', f'Run() : void\n{{\n  mutable v = 0;\n  v += 1;\n  v = "s";\n  v += "!";\n  {W}(v)\n}}\nRun()\n', 's!', None),
    # a function written without its result's type: the type its body gives; return points of several types give a
    # Content holding one of them, and its callers check what they use against that set
    ('result-inferred', f'Twice(n : int) {{ n * 2 }}\nSay(n : int) {{ $"n=$n" }}\nCount(n : int) {{ if (n <= 0) 0 else Count(n - 1) + 1 }}\n'
                        f'{W}(Say(Twice(4)) + Count(3))\n', 'n=83', None),
    ('result-set', f'Pick(c : bool) {{ if (c) "one" else 1 }}\nShow(yes : bool) : void\n{{\n  def a = Pick(yes);\n  {W}(a);\n'
                   f'  {W}(match (a) {{ | s is string => s.Length | n is int => n }});\n  {W}(match (Pick(!yes)) {{ | s is string => s | n is int => $"int $n" }})\n}}\nShow({YES})\n',
     'one\n3\nint 1', None),
    # (constant arguments decide the return point a call reaches: its type, not the set)
    ('result-constant', f'Pick(c : bool) {{ if (c) "one" else 1 }}\nKind(n : int) {{ match (n) {{ | 0 => "zero" | _ => n }} }}\n'
                        f'Show() : void {{ {W}(Pick(true).Length + Pick(false) + Kind(0).Length + Kind(7) * 2) }}\nShow()\n', '22', None),
    ('result-set-flow', f'Flow(c : bool)\n{{\n  mutable x = 1;\n  when (c) x = "two";\n  x\n}}\n{W}(Flow(true))\n', 'two', None),
    ('result-set-misfit', f'Pick(c : bool) {{ if (c) "one" else 1 }}\nShow(yes : bool) : void {{ def n : int = Pick(yes) * 2; {W}(n) }}\nShow({YES})\n', None,
     "this does not fit `Pick(yes)' when it is string"),
    # top-level code bound to such a result: the function's type, or one of its set, which functions check first
    ('result-top-level', f'def size = 10;\nTwice() {{ size * 2 }}\nPick(c : bool) {{ if (c) "one" else 1 }}\ndef doubled = Twice();\n'
                         f'def picked = Pick(!({YES}));\n{W}(doubled + 1);\n{W}(match (picked) {{ | s is string => s | n is int => $"int $n" }});\n'
                         f'Plain() : int {{ doubled * 3 }}\nChecked() : int {{ match (picked) {{ | s is string => s.Length | n is int => n }} }}\n{W}(Plain() + Checked())\n',
     '21\nint 1\n61', None),
    ('result-top-level-unchecked', f'Pick(c : bool) {{ if (c) "one" else 1 }}\ndef picked = Pick({YES});\nBlind() : string {{ picked.ToString() }}\n{W}(Blind())\n',
     None, 'it is a top-level value, and this code can run at any time'),
    # a type written down is the type
    ('typed', f'mutable x : int = 1;\nx = "one";\n{W}(x)\n', None, 'expected int'),
    # a name keeps its kind
    ('kind', f'Run() : void {{ def a = 1; mutable a = 2; {W}(a) }}\nRun()\n', None, 'keeps its kind'),
    # `mutable x;' is NotYet until each way to a read gives it a value
    ('notyet', f'Run() : void {{ mutable x; {W}(x) }}\nRun()\n', None, 'is NotYet here'),
    ('notyet-one-way', f'Run(c : bool) : void {{ mutable x; when (c) x = 1; {W}(x) }}\nRun(true)\n', None, 'is NotYet here'),
    ('notyet-out', f'Run() : void {{ mutable x; _ = int.TryParse("5", out x); {W}(x + 1) }}\nRun()\n', '6', None),
    ('notyet-do', f'Run() : void {{ mutable x; do {{ x = 3 }} while (false); {W}(x) }}\nRun()\n', '3', None),
    ('notyet-changing', f'Run() : void {{ mutable x; x = 1; def show() {{ {W}(x) }} show(); x = "one"; show() }}\nRun()\n', '1\none', None),
    ('notyet-function', f'mutable x;\nx = 5;\nF() : int {{ x }}\n{W}(F())\n', '5', None),
    # the same in code that waits (an async file's top-level code, a waiting script)
    ('async-linear', f'mutable x = 1;\n{AWAIT}x = "one";\n{W}(x.Length)\n', '3', None),
    ('async-lambda', f'mutable x = 1;\n{AWAIT}x = "one";\ndef show = () => {W}(x);\nx = 2;\nshow()\n', None, 'it is a top-level value, and this code can run at any time'),
    # (an error in code that waits is reported once: its typed-only copy does not report it again)
    ('async-type-error', f'{AWAIT}def n : int = "text";\n{W}(n)\n', None, 'expected int'),
    # an error in the last statement is its own (a script's result waits for the call's type, it asks nothing of it)
    ('last-call-error', f'{W}(1 + "x" * 2)\n', None, 'got string'),
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
    return run.stdout.strip(), r.stdout + r.stderr + run.stderr

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
            # (what uses a value reported as unchecked is not an error of its own)
            elif messages.count('error:') != 1:
                failures.append('%s as a %s: the error comes with others it causes\n%s' % (name, kind, messages[-800:]))
            elif 'each overload has an error' in messages:
                failures.append('%s as a %s: the error is followed by others it causes\n%s' % (name, kind, messages[-600:]))
        elif output != expected:
            failures.append('%s as a %s: printed %r, expected %r\n%s' % (name, kind, output, expected, messages[-600:]))
# a value whose type changes, boxed in a loop each time it runs: a warning, once (not one per attempt of the typing)
boxing = 'Run() : void\n{\n  mutable total = 0;\n  total = "none";\n  foreach (i in [1, 2, 3]) total = i;\n  match (total) { | n is int => System.Console.WriteLine(n) | _ => () }\n}\nRun()\n'
for kind, runner in (('file', compile_file), ('script', run_script)):
    output, messages = runner('boxing', boxing)
    if (output != '3' or messages.count('boxes its int value each time it runs') != 1
            or kind == 'file' and messages.count('N10014') != 1 or 'not exhaustive' in messages):
        failures.append('boxing as a %s: printed %r, warned %r' % (kind, output, messages[-600:]))
# a top-level value of several types says them on its field, for other languages (which see a Content)
output, messages = compile_file('content-types', 'using System.Reflection;\nmutable x = 1;\nx = "one";\n'
    'def f = typeof(main).GetField("x", BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic);\n'
    'foreach (a is Nemerle.Scopes.ContentTypesAttribute in f.GetCustomAttributes(false)) System.Console.WriteLine(string.Join(" ", System.Array.ConvertAll(a.Types, t => t.Name)))\n')
if output != 'Int32 String':
    failures.append('the types of a Content field: printed %r\n%s' % (output, messages[-600:]))
# Storage is chosen after typing: a single-type local is an int, a changing-type local is an object.
# Read the emitted method bodies rather than inferring the representation from runtime results.
output, messages = compile_file('storage', '''using System.Reflection;
Fixed() : int { mutable x = 1; x = 2; x }
Changing() : int { mutable x = 1; x = "text"; x.Length }
System.Console.WriteLine(Fixed());
System.Console.WriteLine(Changing());
foreach (name in ["Fixed", "Changing"])
{
  def method = typeof(main).GetMethod(name, BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static);
  mutable hasInt = false;
  mutable hasObject = false;
  foreach (local in method.GetMethodBody().LocalVariables)
  {
    when (local.LocalType == typeof(int)) hasInt = true;
    when (local.LocalType == typeof(object)) hasObject = true
  }
  System.Console.WriteLine(name + ":" + hasInt + ":" + hasObject)
}
''')
if output != '2\n4\nFixed:True:False\nChanging:False:True':
    failures.append('lowered local storage: printed %r\n%s' % (output, messages[-1000:]))
for kind, runner in (('file', compile_file), ('script', run_script)):
    output, messages = runner('no-boxing', 'Run() : void { mutable x = 0; foreach (i in [1, 2, 3]) x = i; System.Console.WriteLine(x) }\nRun()\n')
    if output != '3' or 'boxes its' in messages:
        failures.append('single-type loop as a %s: printed %r, warned %r' % (kind, output, messages[-800:]))
# a function's result of several types says them on its result, for other languages; -flow-log says where each comes from
d = work / 'file' / 'result-types'
d.mkdir(parents=True)
(d / 'main.n').write_text('using System.Reflection;\nPick(c : bool) { if (c) "one" else 1 }\n'
    'def m = typeof(main).GetMethod("Pick", BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic);\n'
    'foreach (a is Nemerle.Scopes.ContentTypesAttribute in m.ReturnParameter.GetCustomAttributes(false)) '
    'System.Console.WriteLine(m.ReturnType.Name + " " + string.Join(" ", System.Array.ConvertAll(a.Types, t => t.Name)))\n')
r = subprocess.run([str(T / 'ncc'), str(d / 'main.n'), '-source-root:' + str(d), '-out:' + str(d / 'main.exe'), '-launcher-', '-no-color', '-flow-log'],
                   capture_output=True, text=True)
log = r.stdout + r.stderr
if r.returncode != 0 or "main.n:2:25:2:30: hint: flow: `Pick' gives string here" not in log or "main.n:2:36:2:37: hint: flow: `Pick' gives int here" not in log:
    failures.append('-flow-log of a result of several types:\n' + log[-600:])
else:
    shutil.copy2(T / 'Nemerle.dll', d / 'Nemerle.dll')
    shutil.copy2(T / 'ncc.runtimeconfig.json', d / 'main.runtimeconfig.json')
    out = subprocess.run(['dotnet', str(d / 'main.exe')], capture_output=True, text=True).stdout.strip()
    if out != 'Content String Int32': failures.append('the types of a result of several types: printed %r' % out)
if failures:
    raise SystemExit('FAILED:\n' + '\n'.join(failures))
print('PASS: %d cases of the flow of values print or fail the same as files and as scripts' % len(cases))
