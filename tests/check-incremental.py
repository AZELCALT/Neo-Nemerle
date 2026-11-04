#!/usr/bin/env python3
"""Check ncc -incremental: a compile that reuses the unchanged files' code from the previous build gives what a full
compile does.

The compiler (ncc/Nemerle/Compiler, copied to a temp folder) is compiled with -incremental:STATE, then:
  - again unchanged: every file is reused (but those always compiled, as one making a top-level type), and the assembly
    and messages are the full compile's;
  - after an edit inside a function body: only that file is compiled again, and the assembly and messages are what a
    full compile of the edited code gives;
  - after a declaration edit: everything is compiled (what the other files' code means may have changed);
and the compiler the body-edit compile spliced together compiles the runtime (lib/) to what the toolchain's own does.
Assemblies are printed by build/il-dump.cs and compared with the numbers of made-up names (`_N_..._123`) taken out: a
retyped file numbers what it makes from where the compile is. Messages are compared as sets: a reused file's are said
again when the reuse is decided, before the retyped files'.
"""
import argparse
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'build'))
from tooling import net10_csc, net10_runtime

p = argparse.ArgumentParser()
p.add_argument('--toolchain', type=pathlib.Path, required=True)
p.add_argument('--references', type=pathlib.Path, required=True)
a = p.parse_args()
T, R = a.toolchain.resolve(), a.references.resolve()
repo = pathlib.Path(__file__).resolve().parents[1]
work = pathlib.Path(tempfile.mkdtemp(prefix='nemerle-incremental-'))
print('Incremental artifacts:', work, flush=True)
runtime = net10_runtime()

if '-incremental' not in subprocess.run(['dotnet', str(T / 'ncc.exe'), '-help'], capture_output=True, text=True).stdout:
    print('SKIP: this ncc has no -incremental'); sys.exit(0)

dump = work / 'il-dump.dll'
subprocess.run(['dotnet', str(net10_csc()), '-nologo', '-nostdlib+', '-target:exe', '-out:' + str(dump),
                *['-r:' + str(r) for r in sorted(R.glob('*.dll'))], '-r:' + str(T / 'Mono.Cecil.dll'),
                str(repo / 'build/il-dump.cs')], check=True)
(work / 'il-dump.runtimeconfig.json').write_text((T / 'ncc.runtimeconfig.json').read_text())
(work / 'Mono.Cecil.dll').write_bytes((T / 'Mono.Cecil.dll').read_bytes())

src = work / 'ncc'
shutil.copytree(repo / 'ncc/Nemerle/Compiler', src / 'Nemerle/Compiler')
state = work / 'state'
compiler_refs = ['System.Linq', 'System.Collections.Specialized', 'System.ComponentModel.Primitives',
    'System.ComponentModel.TypeConverter', 'System.Diagnostics.Process', 'System.Diagnostics.TraceSource',
    'System.Xml.ReaderWriter', 'System.Xml.XmlDocument', 'System.Xml.XmlSerializer', 'System.Security.Cryptography',
    'System.Reflection.Emit', 'System.Reflection.Emit.ILGeneration', 'System.Reflection.Primitives',
    'System.Runtime.InteropServices']
common = ['-define:NET_4_0', '-define:MODERN_CLR', '-no-color', '-target:library', '-no-stdmacros', '-no-stdlib', '-parallel']
def compiler_args(tc):
    return [*sorted(map(str, src.glob('Nemerle/Compiler/*.n'))), *common, '-target-references:' + str(tc / 'references'),
            '-macros:' + str(tc / 'Nemerle.Macros.dll'), '-r:' + str(tc / 'Nemerle.dll'), '-source-root:' + str(src),
            '-r:' + str(tc / 'Nemerle.Platform.dll'), '-r:' + str(tc / 'System.CodeDom.dll'),
            *['-r:' + str(runtime / (n + '.dll')) for n in compiler_refs]]
def runtime_args(tc):
    return [*sorted(map(str, (repo / 'lib/Nemerle').rglob('*.n'))), *[c for c in common if c != '-parallel'], '-target-references:' + str(tc / 'references'),
            '-macros:' + str(tc / 'Nemerle.Macros.dll'), '-source-root:' + str(repo / 'lib'),
            *['-r:' + str(runtime / (n + '.dll')) for n in ('System.Xml.ReaderWriter', 'System.Xml.XmlDocument', 'System.Console')]]

generated = re.compile(r'[\w<>`$@%&|^!=+*/.-]*(?:_N_|d__|<>)[\w<>`$@%&|^!=+*/.-]*')
def normalized(text):
    blocks, cur = [], []
    for line in text.splitlines(keepends=True):
        if line.startswith('type ') and cur: blocks.append(''.join(cur)); cur = []
        cur.append(generated.sub(lambda m: re.sub(r'\d+', '#', m.group(0)), line))
    if cur: blocks.append(''.join(cur))
    return ''.join(sorted(blocks))

def build(name, args, label, tc=T, incremental=False):
    out = work / label; out.mkdir(exist_ok=True)
    env = dict(os.environ, NEMERLE_INCREMENTAL_DEBUG='1')
    started = time.time()
    r = subprocess.run(['dotnet', str(tc / 'ncc.exe'), *args, '-out:' + str(out / (name + '.dll')),
                        *(['-incremental:' + str(state)] if incremental else [])],
                       cwd=work, capture_output=True, text=True, timeout=1200, env=env)
    took = time.time() - started
    said = (r.stdout + r.stderr).replace(str(out), '<out>')
    if r.returncode: raise SystemExit('FAILED: %s did not compile (%s)\n%s' % (name, label, said[-3000:]))
    printed = subprocess.run(['dotnet', str(dump), str(out / (name + '.dll'))], capture_output=True, text=True, check=True).stdout
    (out / (name + '.txt')).write_text(printed)
    notes = [l for l in said.splitlines() if l.startswith('incremental:')]
    messages = sorted(l for l in said.splitlines() if not l.startswith('incremental:'))
    return normalized(printed), messages, notes, took

def same(what, full, incremental, labels):
    if full[1] != incremental[1]:
        raise SystemExit('FAILED: %s: the messages differ\n--- full\n%s\n--- incremental\n%s' % (what, '\n'.join(full[1])[-2000:], '\n'.join(incremental[1])[-2000:]))
    if full[0] != incremental[0]:
        (work / (labels[0] + '.norm')).write_text(full[0]); (work / (labels[1] + '.norm')).write_text(incremental[0])
        diff = subprocess.run(['diff', str(work / (labels[0] + '.norm')), str(work / (labels[1] + '.norm'))], capture_output=True, text=True).stdout
        raise SystemExit('FAILED: %s: the assemblies differ\n%s' % (what, diff[:3000]))

def reused(notes):
    for n in notes:
        m = re.match(r'incremental: (\d+) of (\d+) files reused', n)
        if m: return int(m.group(1)), int(m.group(2))
    return 0, None

def compiled(notes):
    return ', '.join(sorted(pathlib.Path(n.split(' is compiled')[0].split(': ', 1)[1]).name for n in notes if ' is compiled: ' in n)) or 'none'

C = 'Nemerle.Compiler'
cold = build(C, compiler_args(T), 'cold', incremental=True)
warm = build(C, compiler_args(T), 'warm', incremental=True)
count, total = reused(warm[2])
if not total or count < total - 2: raise SystemExit('FAILED: unchanged: %s files reused\n%s' % (count, '\n'.join(warm[2])))
same('unchanged', cold, warm, ('cold', 'warm'))
print('PASS: unchanged: %d of %d files reused (compiled: %s), the same assembly (%.1f s, full %.1f s)' % (count, total, compiled(warm[2]), warm[3], cold[3]), flush=True)

# a body edit (a message's text, in a function with a declared result)
typer = src / 'Nemerle/Compiler/typer.n'
text = typer.read_bytes().decode()
old = '$"unbound name `$expr\'");'
if text.count(old) != 1: raise SystemExit('FAILED: the body-edit target is not in typer.n once')
typer.write_bytes(text.replace(old, '$"unbound name `$expr\' (edited)");').encode())
edited = build(C, compiler_args(T), 'body-edit', incremental=True)
count, total = reused(edited[2])
if not any(n.endswith('typer.n is compiled: its text changed') for n in edited[2]) or count < total - 3:
    raise SystemExit('FAILED: body edit: not reused as expected\n' + '\n'.join(edited[2]))
full = build(C, compiler_args(T), 'body-edit-full')
same('body edit', full, edited, ('body-edit-full', 'body-edit'))
print('PASS: body edit: %d of %d files reused (compiled: %s), the full compile\'s assembly (%.1f s, full %.1f s)' % (count, total, compiled(edited[2]), edited[3], full[3]), flush=True)

# the compiler that compile made works
tc = work / 'toolchain'
shutil.copytree(T, tc)
shutil.copy2(work / 'body-edit' / (C + '.dll'), tc / (C + '.dll'))
mine = build('Nemerle', runtime_args(T), 'runtime-by-toolchain', tc=T)
theirs = build('Nemerle', runtime_args(tc), 'runtime-by-spliced', tc=tc)
same('the spliced compiler', mine, theirs, ('runtime-by-toolchain', 'runtime-by-spliced'))
print('PASS: the spliced compiler compiles the runtime as the toolchain does', flush=True)

# a declaration edit: everything is compiled
utility = src / 'Nemerle/Compiler/Utility.n'
utility.write_bytes(utility.read_bytes() + b'\ninternal class IncrementalProbe { }\n')
declared = build(C, compiler_args(T), 'declaration-edit', incremental=True)
if reused(declared[2])[0] != 0 or not any('everything is compiled' in n for n in declared[2]):
    raise SystemExit('FAILED: declaration edit: files were reused\n' + '\n'.join(declared[2]))
print('PASS: declaration edit: everything compiled', flush=True)
