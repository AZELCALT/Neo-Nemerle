#!/usr/bin/env python3
"""Pascal as a grammar library (samples/pascal): pascalfront.n (the front end) and pascal.n (the grammar) are compiled
as libraries, and each program of samples/pascal/programs, a Nemerle file with a `space Pascal { ... }` (or a folder
whose main.n uses units, found as files are), is compiled against it and run, with its .in file as its input; it must
print its .out file (a last line `THROWS: <message>' is an exception the program ends with).

The grammar is written on the toolchain as it is. KNOWN lists the programs a compiler gap stops, with the gap: such a
program must still fail (so the list is kept true), and passes once the gap is closed.

    check-pascal.py --toolchain DIR --references REFS"""
import argparse, pathlib, shutil, subprocess, sys, tempfile

p = argparse.ArgumentParser()
p.add_argument('--toolchain', type=pathlib.Path, required=True)
p.add_argument('--references', type=pathlib.Path, required=True)
a = p.parse_args()
T = a.toolchain.resolve(); R = a.references.resolve()
here = pathlib.Path(__file__).resolve().parent.parent / 'samples' / 'pascal'
work = pathlib.Path(tempfile.mkdtemp(prefix='nemerle-pascal-'))

KNOWN = {}


def ncc(*args):
    return subprocess.run(['dotnet', str(T / 'ncc.exe'), '-target-references:' + str(R), '-no-color', *map(str, args)],
                          cwd=work, capture_output=True, text=True)


r = ncc(here / 'pascalfront.n', '-target:library', '-out:pascalfront.dll', '-r:' + str(T / 'Nemerle.Compiler.dll'),
        '-r:' + str(T / 'Integrated.Nitra.Runtime.dll'))
if not (work / 'pascalfront.dll').exists():
    raise SystemExit('FAILED: the Pascal front end does not compile:\n' + (r.stdout + r.stderr)[-3000:])
r = ncc(here / 'pascal.n', '-target:library', '-out:pascal.dll', '-r:pascalfront.dll', '-r:' + str(T / 'Nemerle.Compiler.dll'))
if not (work / 'pascal.dll').exists():
    raise SystemExit('FAILED: the Pascal grammar library does not compile:\n' + (r.stdout + r.stderr)[-3000:])
shutil.copy2(T / 'Nemerle.dll', work)

failures, passed, known = [], 0, 0
programs = [(s.stem, s, work) for s in sorted((here / 'programs').glob('*.n'))]
for folder in sorted(p for p in (here / 'programs').iterdir() if p.is_dir()):
    # (a program of units: its folder copied whole; main.n alone is compiled, its units are found from its uses)
    place = work / folder.name
    shutil.copytree(folder, place)
    for dll in ('pascal.dll', 'pascalfront.dll'): shutil.copy2(work / dll, place / dll)
    programs.append((folder.name, folder / 'main.n', place))
for name, source, place in programs:
    expected = source.with_suffix('.out').read_text().rstrip('\n')
    if place == work: shutil.copy2(source, work / source.name)
    exe = place / (source.stem + '.exe')
    r = subprocess.run(['dotnet', str(T / 'ncc.exe'), '-target-references:' + str(R), '-no-color', '-r:pascal.dll', source.name,
                        '-out:' + exe.name, '-launcher-'], cwd=place, capture_output=True, text=True)
    if exe.exists():
        shutil.copy2(T / 'ncc.runtimeconfig.json', place / (exe.stem + '.runtimeconfig.json'))
        shutil.copy2(T / 'Nemerle.dll', place)
        given = source.with_suffix('.in')
        x = subprocess.run(['dotnet', str(exe)], cwd=place, capture_output=True, text=True, timeout=60,
                           input=given.read_text() if given.exists() else '')
        got = x.stdout.rstrip('\n')
        if x.returncode:
            message = next((l.split(':', 1)[1].strip() for l in x.stderr.splitlines() if 'Exception:' in l), '?')
            got = (got + '\n' if got else '') + 'THROWS: ' + message
    else:
        got = 'COMPILE ERROR: ' + next((l for l in (r.stdout + r.stderr).splitlines() if 'error' in l), '?')
    ok = got == expected
    if name in KNOWN:
        if ok: failures.append('%s passes now: take it off KNOWN (%s)' % (name, KNOWN[name]))
        else: known += 1
    elif ok: passed += 1
    else: failures.append('%s:\n  expected: %r\n  got:      %r' % (name, expected, got))
# what the compiler says about a Pascal program: at the Pascal line and column, once (a body the typer restarts expands
# its space again), and nothing more (no bare "parse error" after it)
ERRORS = [
    ('syntax', 'program Bad;\n  begin\n    writeln(1);\n    if then writeln(1)\n  end.', '6:13', 'source does not match Pascal.Program.Start'),
    ('type', 'program Bad;\n  var\n    x : Nothing;\n  begin\n    writeln(1)\n  end.', '5:9', "unknown type `Nothing'"),
    ('typing', 'program Bad;\n  var\n    n : integer;\n  begin\n    n := 1;\n    n := true\n  end.', '8:10', 'the assigned value is boolean, not integer'),
    # (a name Pascal does not declare is the Nemerle program's: Nemerle says it has none)
    ('name', 'program Bad;\n  begin\n    writeln(count + 1)\n  end.', '5:13', "unbound name `count'"),
    ('unit', 'program Bad;\n  uses Nowhere;\n  begin\n  end.', '4:8', "no unit `Nowhere'"),
    ('loopvariable', 'program Bad;\n  var\n    i : integer;\n  begin\n    for i := 1 to 3 do i := 2\n  end.', '7:24', "is the variable of a for loop"),
]
for name, body, at, message in ERRORS:
    source = work / ('error_' + name + '.n')
    source.write_text('space Pascal\n{\n  ' + body + '\n}\n')
    r = ncc('-r:pascal.dll', source.name, '-out:error_' + name + '.exe', '-launcher-')
    errors = [l for l in (r.stdout + r.stderr).splitlines() if 'error:' in l]
    if len(errors) != 1 or (':%s:' % at) not in errors[0] or message not in errors[0]:
        failures.append('the %s error: expected one, at %s, saying %r; got %r' % (name, at, message, errors))

# the grammar machinery on its own: a space body with another language's quotes (a pre-scan must not read it as
# Nemerle, as a file and as a script), and a C-style `for' in map code, plain and in a quotation
machinery = """grammar Q
{
  using Nemerle.Compiler.Parsetree;
  syntax module M
  {
    using Nitra.Core;
    regex Quoted = "'" ("''" | (Any - '\\''))* "'";
    [StartRule] syntax Start = "say" Value=Quoted
    {
      map PExpr = {
        def q = GetText(this.Value);
        mutable n = 0;
        for (mutable i = 0; i < 3; i++) n += i;
        <[ { for (mutable j = 0; j < 2; j++) System.Console.WriteLine($(q.Substring(1, q.Length - 2) : string) + $(n : int).ToString() + j.ToString()) } ]>
      };
    }
  }
}
space Q { say 'x = it''s { ' }
"""
(work / 'machinery.n').write_text(machinery)
r = ncc('machinery.n', '-out:machinery.exe', '-launcher-')
if not (work / 'machinery.exe').exists():
    failures.append('machinery (file): ' + next((l for l in (r.stdout + r.stderr).splitlines() if 'error' in l), '?'))
else:
    shutil.copy2(T / 'ncc.runtimeconfig.json', work / 'machinery.runtimeconfig.json')
    out = subprocess.run(['dotnet', str(work / 'machinery.exe')], cwd=work, capture_output=True, text=True).stdout.strip()
    if out != "x = it''s { 30\nx = it''s { 31": failures.append('machinery (file) printed %r' % out)
(work / 'machinery.ns').write_text(machinery)
s = subprocess.run(['dotnet', str(T / 'nscript.exe'), 'run', 'machinery.ns', '--no-cache'], cwd=work, capture_output=True, text=True, timeout=180)
if s.stdout.strip() != "x = it''s { 30\nx = it''s { 31":
    failures.append('machinery (script): %r' % (s.stdout + s.stderr)[-600:])

if failures:
    print('FAILED:\n' + '\n'.join(failures)); sys.exit(1)
shutil.rmtree(work, ignore_errors=True)
print('PASS: %d Pascal programs (a grammar library) compile and print what they should (%d wait on a compiler gap); its errors are where they are, once; a space body keeps its own quotes, and map code its for loops' % (passed, known))
