#!/usr/bin/env python3
"""Probe source-text runtime compilation through the existing compiler API."""
import argparse
import pathlib
import shutil
import subprocess
import tempfile

parser = argparse.ArgumentParser()
parser.add_argument('--toolchain', type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[1] / 'boot/coreclr')
parser.add_argument('--references', type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[1] / 'boot/coreclr' / 'references')
args = parser.parse_args()
here = pathlib.Path(__file__).resolve().parent
work = pathlib.Path(tempfile.mkdtemp(prefix='nemerle-runtime-compile-'))
print('Runtime compilation artifacts:', work, flush=True)
for path in args.toolchain.iterdir():
    if path.is_file() and path.suffix in ('.dll', '.json'):
        shutil.copy2(path, work / path.name)
version, sdk_root = subprocess.check_output(['dotnet', '--list-sdks'], text=True).splitlines()[-1].split(' ', 1)
csc = pathlib.Path(sdk_root.strip('[]')) / version / 'Roslyn/bincore/csc.dll'
response = work / 'checks.rsp'
response.write_text('\n'.join(['-nologo', '-nostdlib+', '-target:exe', '-out:"' + str(work / 'Checks.dll') + '"'] +
    ['-r:"' + str(p.resolve()) + '"' for p in args.references.glob('*.dll')] +
    ['-r:"' + str(work / name) + '"' for name in ('Nemerle.dll', 'Nemerle.Compiler.dll')] +
    ['"' + str(here / 'RuntimeCompilationChecks.cs') + '"']))
subprocess.run(['dotnet', str(csc), '@' + str(response)], check=True, timeout=60)
shutil.copy2(work / 'ncc.runtimeconfig.json', work / 'Checks.runtimeconfig.json')
subprocess.run(['dotnet', str(work / 'Checks.dll'), str(work)], cwd=work, check=True, timeout=120)
