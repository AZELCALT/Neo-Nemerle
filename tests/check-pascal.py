#!/usr/bin/env python3
"""Pascal as a grammar library (samples/pascal): pascal.n is compiled as a library, and each program of
samples/pascal/programs, a Nemerle file with a `space Pascal { ... }`, is compiled against it and run; it must print
its .out file (a last line `THROWS: <message>' is an exception the program ends with).

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

# (a space's body is read by the Nemerle lexer before the grammar sees it: a Pascal string such as 'x = ' is taken
# for a Nemerle character literal)
LEXER = 'space body read by the Nemerle lexer (Pascal strings)'
KNOWN = {'hello': LEXER, 'factorial': LEXER, 'sieve': LEXER, 'casegrades': LEXER}


def ncc(*args):
    return subprocess.run(['dotnet', str(T / 'ncc.exe'), '-target-references:' + str(R), '-no-color', *map(str, args)],
                          cwd=work, capture_output=True, text=True)


r = ncc(here / 'pascal.n', '-target:library', '-out:pascal.dll')
if not (work / 'pascal.dll').exists():
    raise SystemExit('FAILED: the Pascal grammar library does not compile:\n' + (r.stdout + r.stderr)[-3000:])
shutil.copy2(T / 'Nemerle.dll', work)

failures, passed, known = [], 0, 0
for source in sorted((here / 'programs').glob('*.n')):
    name = source.stem
    expected = source.with_suffix('.out').read_text().rstrip('\n')
    shutil.copy2(source, work / source.name)
    exe = work / (name + '.exe')
    r = ncc('-r:pascal.dll', source.name, '-out:' + exe.name, '-launcher-')
    if exe.exists():
        shutil.copy2(T / 'ncc.runtimeconfig.json', work / (name + '.runtimeconfig.json'))
        x = subprocess.run(['dotnet', str(exe)], cwd=work, capture_output=True, text=True, timeout=60)
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
if failures:
    print('FAILED:\n' + '\n'.join(failures)); sys.exit(1)
shutil.rmtree(work, ignore_errors=True)
print('PASS: %d Pascal programs (a grammar library) compile and print what they should; %d wait on a compiler gap' % (passed, known))
