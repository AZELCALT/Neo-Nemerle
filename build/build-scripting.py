#!/usr/bin/env python3
"""Build the optional Nemerle-authored scripting host with a source-built compiler."""
import argparse
import pathlib
import subprocess
import sys
import tempfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import buildcache
p = argparse.ArgumentParser()
p.add_argument('--toolchain', type=pathlib.Path, required=True)
p.add_argument('--references', type=pathlib.Path, required=True)
a = p.parse_args()
repo = pathlib.Path(__file__).resolve().parents[1]
root = repo / 'scripting'
toolchain = a.toolchain.resolve()
command = ['dotnet', str(toolchain / 'ncc.exe'), '-source-root:' + str(root),
    *map(str, sorted(root.glob('Nemerle/Scripting/*.n'))), '-target:library',
    '-out:' + str(toolchain / 'Nemerle.Scripting.dll'),
    '-target-references:' + str(a.references.resolve()), '-no-color']
command += ['-r:' + str(toolchain / (name + '.dll')) for name in ('Nemerle.Compiler', 'Nemerle.Platform')]
logs = pathlib.Path(tempfile.mkdtemp(prefix='nemerle-scripting-build-'))
def compile(label, command):   # (an unchanged compile is reused)
    log = logs / (label + '.log')
    code = buildcache.run(command, log)
    sys.stdout.write(log.read_text())
    if code: raise SystemExit(code)
compile('scripting', command)
compile('nscript', ['dotnet', str(toolchain / 'ncc.exe'), str(repo / 'scripting-cli/main.n'), '-source-root:' + str(repo / 'scripting-cli'),
    '-out:' + str(toolchain / 'nscript.exe'), '-launcher-', '-r:' + str(toolchain / 'Nemerle.Scripting.dll'),
    '-target-references:' + str(a.references.resolve()), '-no-color'])
(toolchain / 'nscript.runtimeconfig.json').write_text((toolchain / 'ncc.runtimeconfig.json').read_text())
(toolchain / 'nscript').write_text('#!/bin/sh\nexec dotnet "$(dirname "$0")/nscript.exe" "$@"\n')
(toolchain / 'nscript').chmod(0o755)
