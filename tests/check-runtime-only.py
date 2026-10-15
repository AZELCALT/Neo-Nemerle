#!/usr/bin/env python3
"""Verify the compiler runs with a runtime-only dotnet host."""
import argparse
import os
import pathlib
import shutil
import subprocess
import tempfile

parser = argparse.ArgumentParser()
parser.add_argument('--compiler', type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[1] / 'boot/coreclr' / 'ncc.exe')
parser.add_argument('--references', type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[1] / 'boot/coreclr' / 'references')
args = parser.parse_args()
here = pathlib.Path(__file__).resolve().parent
installation = pathlib.Path(shutil.which('dotnet')).resolve().parent
root = pathlib.Path(tempfile.mkdtemp(prefix='nemerle-runtime-only-'))
shutil.copy2(installation / 'dotnet', root / 'dotnet')
(root / 'host').mkdir()
(root / 'host/fxr').symlink_to(installation / 'host/fxr', target_is_directory=True)
(root / 'shared').mkdir()
(root / 'shared/Microsoft.NETCore.App').symlink_to(installation / 'shared/Microsoft.NETCore.App', target_is_directory=True)
env = os.environ.copy()
env['DOTNET_ROOT'] = str(root)
env['DOTNET_MULTILEVEL_LOOKUP'] = '0'
sdks = subprocess.check_output([str(root / 'dotnet'), '--list-sdks'], env=env, text=True)
if sdks.strip(): raise RuntimeError('Runtime-only host unexpectedly sees an SDK: ' + sdks)
subprocess.run([str(root / 'dotnet'), str(args.compiler.resolve()),
    '-target-references:' + str(args.references.resolve()),
    '-source-root:' + str(here / 'file-modules'),
    str(here / 'file-modules/alpha.n'), str(here / 'file-modules/beta.n'),
    '-target:library', '-out:' + str(root / 'sample.dll')], env=env, check=True)
print('Runtime-only host:', root)
print('PASS: no SDK visible to host; module sample compiled using bundled reference contracts')
