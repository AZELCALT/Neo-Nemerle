#!/usr/bin/env python3
"""EXPERIMENT: the continuation section (doc/CONTINUATION.md), stage by stage.

    check-continuation.py --toolchain DIR --references REFS [--stage E1]

E1: -experimental-continuation writes a .nemir section with the grammar image and marks; the output still runs and
    verifies when signed; without the flag nothing is written.
E2: a program with only `space Demo { ... }` compiles with -experimental-continue:<host binary> against the host's
    stored grammar (no grammar in its source, no nested grammar compile) and prints the same result."""
import argparse, pathlib, shutil, subprocess, tempfile, time

p = argparse.ArgumentParser()
p.add_argument('--toolchain', type=pathlib.Path, required=True)
p.add_argument('--references', type=pathlib.Path, required=True)
p.add_argument('--stage', default='E2', help='run the stages up to and including this one')
a = p.parse_args()
here = pathlib.Path(__file__).resolve().parent
repo = here.parent
T = a.toolchain.resolve()
R = a.references.resolve()
w = pathlib.Path(tempfile.mkdtemp(prefix='nemerle-continuation-'))
print('Continuation checks:', w, flush=True)
key = repo / 'misc/keys/Nemerle.snk'


def grammar_program(rules):
    """A grammar with `rules` alternatives of one extensible rule, and a Main that expands the last one."""
    alternatives = '\n'.join('      | A%d = "k%d" { map PExpr = <[ %d ]>; }' % (i, i, i) for i in range(rules))
    return '''grammar Demo
{
  using Nemerle.Compiler.Parsetree;
  syntax module Query
  {
    using Nitra.Core;
    [StartRule] syntax Input = Item { map PExpr { Item } }
    syntax Item
    {
      map PExpr;
%s
    }
  }
}
module Program
{
  Main() : void { System.Console.WriteLine(space Demo { k%d }); }
}
''' % (alternatives, rules - 1)


def run(command, **kw):
    r = subprocess.run([str(c) for c in command], capture_output=True, text=True, **kw)
    if r.returncode != 0:
        raise SystemExit('FAILED: %s\n%s%s' % (' '.join(map(str, command)), r.stdout, r.stderr))
    return r


def compile_program(name, rules, extra):
    root = w / name
    root.mkdir()
    source = root / 'demo.n'
    source.write_text(grammar_program(rules))
    started = time.time()
    run([T / 'ncc', source, '-source-root:' + str(root), '-out:' + str(root / 'demo.exe'), '-no-color', *extra])
    elapsed = time.time() - started
    shutil.copy2(T / 'ncc.runtimeconfig.json', root / 'demo.runtimeconfig.json')
    output = run(['dotnet', root / 'demo.exe'], cwd=root).stdout.strip()
    if output != str(rules - 1):
        raise SystemExit('FAILED: %s printed %r, expected %d' % (name, output, rules - 1))
    return root / 'demo.exe', elapsed


# the C# reader of the section
version, folder = subprocess.check_output(['dotnet', '--list-sdks'], text=True).splitlines()[-1].split(' ', 1)
csc = pathlib.Path(folder.strip('[]')) / version / 'Roslyn/bincore/csc.dll'
rsp = w / 'checks.rsp'
rsp.write_text('\n'.join(['-nologo', '-nostdlib+', '-target:exe', '-out:"' + str(w / 'Checks.dll') + '"']
    + ['-r:"' + str(f) + '"' for f in sorted(R.glob('*.dll'))]
    + ['-r:"' + str(T / n) + '"' for n in ('Nemerle.dll', 'Nemerle.Compiler.dll', 'Nemerle.Platform.dll')]
    + ['"' + str(here / 'ContinuationChecks.cs') + '"']))
run(['dotnet', csc, '@' + str(rsp)])
for f in T.glob('*.dll'):
    shutil.copy2(f, w / f.name)
shutil.copy2(T / 'ncc.runtimeconfig.json', w / 'Checks.runtimeconfig.json')


def reader(*args):
    return run(['dotnet', w / 'Checks.dll', *args], cwd=w).stdout.strip()


plain, t_plain = compile_program('plain', 10, [])
print(reader(plain, T), flush=True)
unsigned, t_cont = compile_program('unsigned', 10, ['-experimental-continuation'])
print(reader(unsigned, T, 'Demo', unsigned.parent / 'demo.n', '10'), flush=True)
signed, _ = compile_program('signed', 10, ['-experimental-continuation', '-keyfile:' + str(key)])
print(reader(signed, T, 'Demo'), flush=True)
verify = subprocess.run(['sn', '-vf', str(signed)], capture_output=True, text=True)
if 'is strongnamed' not in verify.stdout:
    raise SystemExit('FAILED: signed output with a continuation section does not verify\n' + verify.stdout + verify.stderr)
print('PASS: signed output with a continuation section verifies (sn -vf)', flush=True)
print('E1 times (10 rules): plain compile %.2fs, with continuation %.2fs' % (t_plain, t_cont), flush=True)
print('PASS: E1 continuation section written, signed, readable', flush=True)


def space_program(name, expression, expected, host):
    """A program that uses the host's grammar Demo in a space block but defines no grammar itself."""
    root = w / name
    root.mkdir()
    source = root / 'use.n'
    source.write_text('module Program\n{\n  Main() : void { System.Console.WriteLine(space Demo { %s }); }\n}\n' % expression)
    started = time.time()
    run([T / 'ncc', source, '-source-root:' + str(root), '-out:' + str(root / 'use.exe'), '-no-color',
         '-experimental-continue:' + str(host)])
    elapsed = time.time() - started
    shutil.copy2(T / 'ncc.runtimeconfig.json', root / 'use.runtimeconfig.json')
    output = run(['dotnet', root / 'use.exe'], cwd=root).stdout.strip()
    if output != str(expected):
        raise SystemExit('FAILED: %s printed %r, expected %s' % (name, output, expected))
    return elapsed


if a.stage >= 'E2':
    t10 = space_program('use10', 'k3', 3, unsigned)
    host120, t_fresh120 = compile_program('host120', 120, ['-experimental-continuation'])
    t120 = space_program('use120', 'k117', 117, host120)
    t_plain120 = min(compile_program('fresh120-%d' % i, 120, [])[1] for i in range(2))
    print('E2 times: 10-rule grammar fresh %.2fs, continued %.2fs; 120-rule grammar fresh %.2fs, continued %.2fs'
          % (t_cont, t10, t_plain120, t120), flush=True)
    print('PASS: E2 programs continue from a stored grammar without compiling it', flush=True)
shutil.rmtree(w, ignore_errors=True)
