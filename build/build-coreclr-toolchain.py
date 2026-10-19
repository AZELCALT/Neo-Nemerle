#!/usr/bin/env python3
"""Source-build the compiler using a working CoreCLR bootstrap; keep all logs."""
import argparse
import re
import pathlib
import shutil
import subprocess
import tempfile

parser = argparse.ArgumentParser()
parser.add_argument('--bootstrap', type=pathlib.Path, required=True)
parser.add_argument('--references', type=pathlib.Path, required=True)
parser.add_argument('--early-macros', type=pathlib.Path,
                    help='prebuilt Nemerle.Macros.dll with the current macro paths (bridging from a toolchain whose macros predate them)')
args = parser.parse_args()
repo = pathlib.Path(__file__).resolve().parents[1]
work = pathlib.Path(tempfile.mkdtemp(prefix='nemerle-core-selfbuild-'))
print('CoreCLR source-build artifacts:', work, flush=True)
previous = args.bootstrap.resolve()
# The compiler is every file module under ncc/Nemerle/Compiler (source root ncc).
sources = sorted(repo.glob('ncc/Nemerle/Compiler/*.n'))
runtime_rows = [line.split() for line in subprocess.check_output(['dotnet', '--list-runtimes'], text=True).splitlines() if line.startswith('Microsoft.NETCore.App ')]
selected_runtime = max(runtime_rows, key=lambda row: tuple(int(v) for v in row[1].split('.')))
runtime = pathlib.Path(selected_runtime[2].strip('[]')) / selected_runtime[1]
# Explicit references to implementation assemblies used by the source compiler.
# Output contracts are independently bound using --references.
names = ['System.Linq', 'System.Collections.Specialized', 'System.ComponentModel.Primitives',
    'System.ComponentModel.TypeConverter', 'System.Diagnostics.Process', 'System.Diagnostics.TraceSource',
    'System.Xml.ReaderWriter', 'System.Xml.XmlDocument', 'System.Xml.XmlSerializer',
    'System.Security.Cryptography', 'System.Reflection.Emit', 'System.Reflection.Emit.ILGeneration',
    'System.Reflection.Primitives', 'System.Runtime.InteropServices']
def build(label, compiler, source_files, output, references, key, extra=()):
    command = ['dotnet', str(compiler / 'ncc.exe'), *map(str, source_files),
        '-out:' + str(output), '-define:NET_4_0', '-define:MODERN_CLR',
        '-target-references:' + str(args.references.resolve()),
        '-keyfile:' + str(repo / 'misc/keys' / key), '-no-color', *extra]
    command.extend('-r:' + str(reference) for reference in references)
    log = work / (label + '.log')
    print('Building:', label, flush=True)
    with log.open('w') as stream:
        result = subprocess.run(command, cwd=repo, stdout=stream, stderr=subprocess.STDOUT)
    if result.returncode:
        print(log.read_text(), flush=True); raise SystemExit(result.returncode)
    subprocess.run(['sn', '-vf', str(output)], check=True, stdout=subprocess.DEVNULL)
    print('PASS:', label, flush=True)

# The standard macros (file modules under macros/) are built first, by the bootstrap compiler with its own macros,
# and every build below uses them, so sources can name macros by their current paths.
early = work / 'macros-early'; early.mkdir()
macro_sources = sorted((repo / 'macros').rglob('*.n'))
if args.early_macros: shutil.copy2(args.early_macros, early / 'Nemerle.Macros.dll')
else: build('macros-early', previous, macro_sources, early / 'Nemerle.Macros.dll',
      [previous / 'Nemerle.Compiler.dll', previous / 'Nemerle.Platform.dll'] + [runtime / 'System.Data.Common.dll',
      runtime / 'System.Xml.ReaderWriter.dll', runtime / 'System.Xml.XmlSerializer.dll',
      runtime / 'System.Xml.XDocument.dll', runtime / 'System.Linq.dll'],
      'Nemerle.Compiler.snk', ['-target:library', '-source-root:' + str(repo / 'macros')])
new_macros = ['-no-stdmacros', '-macros:' + str(early / 'Nemerle.Macros.dll')]
for number in (1, 2):
    current = work / ('stage' + str(number)); current.mkdir()
    for path in previous.iterdir():
        if path.is_file(): shutil.copy2(path, current / path.name)
    if number == 2:
        # The runtime is written as file modules (lib/Nemerle/Core.n is module Nemerle.Core). Its version is the
        # compiler's git-derived one (macros/GeneratedAssemblyVersion.n: "$GitTag.0.$GitRevision", defaults 1.2 / 9999).
        described = subprocess.run(['git', 'describe', '--tags', '--long'], cwd=repo, capture_output=True, text=True).stdout.strip()
        parts = described.rsplit('-', 2)
        tag = re.sub(r'[^\d.]', '', parts[0]) if len(parts) == 3 else ''
        version = (tag if tag and tag != '.' else '1.2') + '.0.' + (parts[1] if len(parts) == 3 else '9999')
        build('runtime2', previous, sorted((repo / 'lib' / 'Nemerle').rglob('*.n')), current / 'Nemerle.dll',
              [runtime / 'System.Xml.ReaderWriter.dll', runtime / 'System.Xml.XmlDocument.dll', runtime / 'System.Console.dll'],
              'Nemerle.snk', ['-target:library', '-no-stdlib', '-source-root:' + str(repo / 'lib'), '-assembly-version:' + version, *new_macros])
    # Stage 2 compiles against the runtime it just built (the stage-1 compiler itself still runs on the previous one;
    # references load in their own context), so runtime layout changes reach the compiler, macros and CLI.
    new_runtime = ['-no-stdlib', '-r:' + str(current / 'Nemerle.dll')] if number == 2 else []
    build('compiler' + str(number), previous, sources, current / 'Nemerle.Compiler.dll',
          [previous / 'Nemerle.Platform.dll', previous / 'System.CodeDom.dll'] +
          [runtime / (name + '.dll') for name in names], 'Nemerle.Compiler.snk',
          ['-target:library', '-source-root:' + str(repo / 'ncc'), *new_runtime, *new_macros])
    # Stage 2 runs on the stage-1 compiler, whose API may differ from the previous one (Phase 5 moved the compiler to
    # file modules): its macros are built again by the previous compiler against stage 1's Nemerle.Compiler.dll.
    if number == 1:
        stage_macros = work / 'macros-stage1'; stage_macros.mkdir()
        build('macros-stage1', previous, macro_sources, stage_macros / 'Nemerle.Macros.dll',
              [current / 'Nemerle.Compiler.dll', previous / 'Nemerle.Platform.dll'] + [runtime / 'System.Data.Common.dll',
              runtime / 'System.Xml.ReaderWriter.dll', runtime / 'System.Xml.XmlSerializer.dll',
              runtime / 'System.Xml.XDocument.dll', runtime / 'System.Linq.dll'],
              'Nemerle.Compiler.snk', ['-target:library', '-source-root:' + str(repo / 'macros'), *new_macros])
        # and so is its command-line front end (the copied one was built against the previous API)
        build('cli1', previous, [repo / 'ncc/Nemerle/CommandlineCompiler.n', repo / 'ncc/Nemerle/ProjectCommands.n'],
              current / 'ncc.exe', [current / 'Nemerle.Compiler.dll', current / 'Nemerle.Platform.dll', runtime / 'System.Console.dll', runtime / 'System.Linq.dll', runtime / 'System.Net.Http.dll', runtime / 'System.IO.Compression.dll', runtime / 'System.Text.Json.dll', runtime / 'System.Memory.dll', runtime / 'System.Reflection.Metadata.dll', runtime / 'System.Collections.Immutable.dll', runtime / 'System.IO.Compression.ZipFile.dll'], 'Nemerle.Compiler.snk',
              ['-source-root:' + str(repo / 'ncc'), *new_macros])
        new_macros = ['-no-stdmacros', '-macros:' + str(stage_macros / 'Nemerle.Macros.dll')]
    # Compile macros in an isolated output directory with their real identity;
    # never replace the executing compiler's standard macro assembly.
    if number == 2:
        build('macros2', previous, macro_sources, current / 'Nemerle.Macros.dll',
              [current / 'Nemerle.Compiler.dll', previous / 'Nemerle.Platform.dll'] + [runtime / 'System.Data.Common.dll',
               runtime / 'System.Xml.ReaderWriter.dll', runtime / 'System.Xml.XmlSerializer.dll',
               runtime / 'System.Xml.XDocument.dll', runtime / 'System.Linq.dll'],
              'Nemerle.Compiler.snk', ['-target:library', '-source-root:' + str(repo / 'macros'), *new_runtime, *new_macros])
        build('cli2', previous, [repo / 'ncc/Nemerle/CommandlineCompiler.n', repo / 'ncc/Nemerle/ProjectCommands.n'],
              current / 'ncc.exe', [current / 'Nemerle.Compiler.dll', current / 'Nemerle.Platform.dll', runtime / 'System.Console.dll', runtime / 'System.Linq.dll', runtime / 'System.Net.Http.dll', runtime / 'System.IO.Compression.dll', runtime / 'System.Text.Json.dll', runtime / 'System.Memory.dll', runtime / 'System.Reflection.Metadata.dll', runtime / 'System.Collections.Immutable.dll', runtime / 'System.IO.Compression.ZipFile.dll'], 'Nemerle.Compiler.snk', ['-source-root:' + str(repo / 'ncc'), *new_runtime, *new_macros])
    previous = current
print('Verified CoreCLR source toolchain:', previous / 'ncc.exe', flush=True)
