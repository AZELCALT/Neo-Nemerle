#!/usr/bin/env python3
"""Check that a compile gives the same assembly every time, and (once ncc has -parallel) that typing methods in parallel
gives what typing them in order does.

The runtime (lib/) and the compiler (ncc/) are compiled twice with the toolchain; each assembly is printed by
build/il-dump.cs (types and members, each method's IL with its operands named, in a stable order) and the two prints
are compared, with the messages the compiles gave. Without -parallel the two compiles are the same and their prints
must be equal byte for byte (a compile does not depend on anything but its input). With -parallel the second types in
parallel, and the names the compiler makes up (`_N_..._123`, which are numbered as they are made) are compared with
their numbers taken out: the order methods are typed in may number them differently, nothing else may differ.
"""
import argparse
import pathlib
import re
import subprocess
import sys
import tempfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'build'))
from tooling import net10_csc, net10_runtime

p = argparse.ArgumentParser()
p.add_argument('--toolchain', type=pathlib.Path, required=True)
p.add_argument('--references', type=pathlib.Path, required=True)
a = p.parse_args()
T, R = a.toolchain.resolve(), a.references.resolve()
repo = pathlib.Path(__file__).resolve().parents[1]
work = pathlib.Path(tempfile.mkdtemp(prefix='nemerle-parallel-typing-'))
print('Parallel typing artifacts:', work, flush=True)
runtime = net10_runtime()

# the printer, built with the SDK's C# compiler against the toolchain's Mono.Cecil
dump = work / 'il-dump.dll'
subprocess.run(['dotnet', str(net10_csc()), '-nologo', '-nostdlib+', '-target:exe', '-out:' + str(dump),
                *['-r:' + str(r) for r in sorted(R.glob('*.dll'))], '-r:' + str(T / 'Mono.Cecil.dll'),
                str(repo / 'build/il-dump.cs')], check=True)
(work / 'il-dump.runtimeconfig.json').write_text((T / 'ncc.runtimeconfig.json').read_text())
(work / 'Mono.Cecil.dll').write_bytes((T / 'Mono.Cecil.dll').read_bytes())

parallel = '-parallel' in subprocess.run(['dotnet', str(T / 'ncc.exe'), '-help'], capture_output=True, text=True).stdout
compiler_refs = ['System.Linq', 'System.Collections.Specialized', 'System.ComponentModel.Primitives',
    'System.ComponentModel.TypeConverter', 'System.Diagnostics.Process', 'System.Diagnostics.TraceSource',
    'System.Xml.ReaderWriter', 'System.Xml.XmlDocument', 'System.Xml.XmlSerializer', 'System.Security.Cryptography',
    'System.Reflection.Emit', 'System.Reflection.Emit.ILGeneration', 'System.Reflection.Primitives',
    'System.Runtime.InteropServices']
common = ['-define:NET_4_0', '-define:MODERN_CLR', '-target-references:' + str(T / 'references'), '-no-color',
          '-target:library', '-no-stdmacros', '-macros:' + str(T / 'Nemerle.Macros.dll')]
corpora = {
    'Nemerle': [*sorted(map(str, (repo / 'lib/Nemerle').rglob('*.n'))), *common, '-no-stdlib', '-source-root:' + str(repo / 'lib'),
                *['-r:' + str(runtime / (n + '.dll')) for n in ('System.Xml.ReaderWriter', 'System.Xml.XmlDocument', 'System.Console')]],
    'Nemerle.Compiler': [*sorted(map(str, repo.glob('ncc/Nemerle/Compiler/*.n'))), *common, '-no-stdlib',
                         '-r:' + str(T / 'Nemerle.dll'), '-source-root:' + str(repo / 'ncc'), '-r:' + str(T / 'Nemerle.Platform.dll'),
                         '-r:' + str(T / 'System.CodeDom.dll'), *['-r:' + str(runtime / (n + '.dll')) for n in compiler_refs]],
}

generated = re.compile(r'[\w<>`$@%&|^!=+*/.-]*(?:_N_|d__|<>)[\w<>`$@%&|^!=+*/.-]*')
def normalized(text):
    """The print with the numbers of made-up names taken out, its types in the order of that text, and each type's
    members too (made-up members, such as two local functions of one name in two methods, are ordered by their numbers,
    which typing in parallel gives in another order)."""
    def members(block):
        head, parts, cur = [], [], None
        for line in block.splitlines(keepends=True):
            if line.startswith('  ') and not line.startswith('   '):
                if cur is not None: parts.append(''.join(cur))
                cur = [line]
            elif cur is None: head.append(line)
            else: cur.append(line)
        if cur is not None: parts.append(''.join(cur))
        return ''.join(head) + ''.join(sorted(parts))
    blocks, cur = [], []
    for line in text.splitlines(keepends=True):
        if line.startswith('type ') and cur: blocks.append(''.join(cur)); cur = []
        cur.append(generated.sub(lambda m: re.sub(r'\d+', '#', m.group(0)), line))
    if cur: blocks.append(''.join(cur))
    return ''.join(sorted(members(b) for b in blocks))

def build(name, args, extra, label):
    out = work / label; out.mkdir(exist_ok=True)
    r = subprocess.run(['dotnet', str(T / 'ncc.exe'), *args, '-out:' + str(out / (name + '.dll')), *extra],
                       cwd=repo, capture_output=True, text=True, timeout=1200)
    if r.returncode: raise SystemExit('FAILED: %s did not compile (%s)\n%s' % (name, label, (r.stdout + r.stderr)[-3000:]))
    printed = subprocess.run(['dotnet', str(dump), str(out / (name + '.dll'))], capture_output=True, text=True, check=True).stdout
    (out / (name + '.txt')).write_text(printed)
    # (the messages, without the build's own paths)
    return printed, (r.stdout + r.stderr).replace(str(out), '<out>')

for name, args in corpora.items():
    first, said1 = build(name, args, [], 'in-order')
    second, said2 = build(name, args, ['-parallel'] if parallel else [], 'parallel' if parallel else 'again')
    if said1 != said2:
        raise SystemExit('FAILED: %s: the compiles gave different messages\n--- first\n%s\n--- second\n%s' % (name, said1[-2000:], said2[-2000:]))
    if parallel: first, second = normalized(first), normalized(second)
    if first != second:
        # (the difference of what is compared: the made-up names' numbers out, the types in order)
        import difflib
        diff = ''.join(difflib.unified_diff(first.splitlines(True), second.splitlines(True), 'in order', 'parallel' if parallel else 'again', n=2))
        raise SystemExit('FAILED: %s: the two compiles gave different assemblies\n%s' % (name, diff[:3000]))
    print('PASS: %s: %s (%d lines of IL and metadata)' % (
        name, 'typing in parallel gives what typing in order does' if parallel else 'two compiles give the same assembly',
        first.count('\n')), flush=True)
