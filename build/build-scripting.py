#!/usr/bin/env python3
"""Build the optional Nemerle-authored scripting host with a source-built compiler."""
import argparse
import pathlib
import subprocess
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
subprocess.run(command, check=True, timeout=120)
subprocess.run(['dotnet', str(toolchain / 'ncc.exe'), str(repo / 'scripting-cli/main.n'), '-source-root:' + str(repo / 'scripting-cli'),
    '-out:' + str(toolchain / 'nscript.exe'), '-launcher-', '-r:' + str(toolchain / 'Nemerle.Scripting.dll'),
    '-target-references:' + str(a.references.resolve()), '-no-color'], check=True, timeout=120)
(toolchain / 'nscript.runtimeconfig.json').write_text((toolchain / 'ncc.runtimeconfig.json').read_text())
(toolchain / 'nscript').write_text('#!/bin/sh\nexec dotnet "$(dirname "$0")/nscript.exe" "$@"\n')
(toolchain / 'nscript').chmod(0o755)
