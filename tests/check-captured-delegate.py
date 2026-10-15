#!/usr/bin/env python3
"""Verify CLR delegate target initialization in release and debug output."""
import argparse
import pathlib
import shutil
import subprocess
import tempfile

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--toolchain', type=pathlib.Path, required=True)
p.add_argument('--references', type=pathlib.Path, required=True)
a = p.parse_args()
work = pathlib.Path(tempfile.mkdtemp(prefix='nemerle-captured-delegate-'))
print('Delegate argument checks:', work, flush=True)
for source in a.toolchain.iterdir():
    if source.is_file():
        shutil.copy2(source, work / source.name)
source = pathlib.Path(__file__).with_name('CapturedDelegateArguments.n')
for mode in ('release', 'debug'):
    output = work / (mode + '.exe')
    subprocess.run([
        'dotnet', str(work / 'ncc.exe'), str(source.resolve()), '-source-root:' + str(source.resolve().parent),
        '-out:' + str(output), '-no-color',
        '-debug+' if mode == 'debug' else '-debug-',
        '-target-references:' + str(a.references.resolve()),
    ], check=True, timeout=120)
    shutil.copy2(work / 'ncc.runtimeconfig.json', work / (mode + '.runtimeconfig.json'))
    subprocess.run(['dotnet', str(output)], check=True, timeout=30)
