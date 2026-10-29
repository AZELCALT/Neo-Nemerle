#!/usr/bin/env python3
"""Fast single-pass rebuild of Nemerle.Compiler.dll (+ ncc.exe) into a copy of boot, using the boot compiler and its
macros. For iterating on compiler sources only; not a bootstrap. Prints the toolchain dir on success."""
import argparse, pathlib, shutil, subprocess, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from tooling import net10_runtime, verify_strong_name

repo = pathlib.Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser()
p.add_argument('--boot', type=pathlib.Path, default=repo / 'boot/coreclr')
p.add_argument('--references', type=pathlib.Path, default=repo / 'boot/coreclr/references')
p.add_argument('--output', type=pathlib.Path, default=repo / 'out/fast')
a = p.parse_args()
boot, refs, out = a.boot.resolve(), a.references.resolve(), a.output.resolve()
runtime = net10_runtime()
T = out / 'toolchain'
if out.exists(): shutil.rmtree(out)
out.mkdir(parents=True)
shutil.copytree(boot, T)

names = ['System.Linq', 'System.Collections.Specialized', 'System.ComponentModel.Primitives',
    'System.ComponentModel.TypeConverter', 'System.Diagnostics.Process', 'System.Diagnostics.TraceSource',
    'System.Xml.ReaderWriter', 'System.Xml.XmlDocument', 'System.Xml.XmlSerializer',
    'System.Security.Cryptography', 'System.Reflection.Emit', 'System.Reflection.Emit.ILGeneration',
    'System.Reflection.Primitives', 'System.Runtime.InteropServices']
def build(label, output, source_files, references, extra, keyname='Nemerle.Compiler.snk', use_boot_macros=True):
    macros = ['-no-stdmacros', '-macros:' + str((boot if use_boot_macros else T) / 'Nemerle.Macros.dll')]
    cmd = ['dotnet', str(boot / 'ncc.exe'), *map(str, source_files), '-out:' + str(output),
           '-define:NET_4_0', '-define:MODERN_CLR', '-target-references:' + str(refs),
           '-keyfile:' + str(repo / 'misc/keys' / keyname), '-no-color', *macros, *extra]
    cmd += ['-r:' + str(r) for r in references]
    log = out / (label + '.log')
    print('Building:', label, flush=True)
    with log.open('w') as s:
        r = subprocess.run(cmd, cwd=repo, stdout=s, stderr=subprocess.STDOUT)
    if r.returncode:
        print(log.read_text(), flush=True); raise SystemExit(r.returncode)
    verify_strong_name(output)
    print('PASS:', label, flush=True)

# Standard macros from source first (the `.:' operator and its priority live here, so stale boot macros would parse
# the dot-call wrong); overlaid into the toolchain so its ncc.exe parses with the current macros.
build('macros', T / 'Nemerle.Macros.dll', sorted((repo / 'macros').rglob('*.n')),
      [boot / 'Nemerle.Compiler.dll', boot / 'Nemerle.Platform.dll',
       runtime / 'System.Data.Common.dll', runtime / 'System.Xml.ReaderWriter.dll',
       runtime / 'System.Xml.XmlSerializer.dll', runtime / 'System.Xml.XDocument.dll', runtime / 'System.Linq.dll'],
      ['-target:library', '-source-root:' + str(repo / 'macros')])

sources = sorted(repo.glob('ncc/Nemerle/Compiler/*.n'))
build('compiler', T / 'Nemerle.Compiler.dll', sources,
      [boot / 'Nemerle.Platform.dll', boot / 'System.CodeDom.dll'] + [runtime / (n + '.dll') for n in names],
      ['-target:library', '-no-stdlib', '-r:' + str(boot / 'Nemerle.dll'), '-source-root:' + str(repo / 'ncc')])
cli_refs = [T / 'Nemerle.Compiler.dll', T / 'Nemerle.Platform.dll', runtime / 'System.Console.dll',
    runtime / 'System.Linq.dll', runtime / 'System.Net.Http.dll', runtime / 'System.IO.Compression.dll',
    runtime / 'System.Text.Json.dll', runtime / 'System.Memory.dll', runtime / 'System.Reflection.Metadata.dll',
    runtime / 'System.Collections.Immutable.dll', runtime / 'System.IO.Compression.ZipFile.dll']
build('cli', T / 'ncc.exe', [repo / 'ncc/Nemerle/CommandlineCompiler.n', repo / 'ncc/Nemerle/ProjectCommands.n'],
      cli_refs, ['-no-stdlib', '-r:' + str(boot / 'Nemerle.dll'), '-source-root:' + str(repo / 'ncc')])
print('Fast toolchain:', T, flush=True)
