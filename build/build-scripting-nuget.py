#!/usr/bin/env python3
"""Build the optional NuGet adapter from explicitly pinned client libraries.
The supplied libraries are build inputs; runtime consumers receive sibling DLLs
and never invoke or locate an SDK/MSBuild installation.
"""
import argparse
import hashlib
import json
import pathlib
import shutil
import subprocess
import tempfile
p = argparse.ArgumentParser()
p.add_argument('--toolchain', type=pathlib.Path, required=True)
p.add_argument('--references', type=pathlib.Path, required=True)
p.add_argument('--nuget-libraries', type=pathlib.Path, required=True)
a = p.parse_args()
repo = pathlib.Path(__file__).resolve().parents[1]
manifest = json.loads((repo / 'scripting-nuget/client-libraries.lock.json').read_text())
for name, expected in manifest['files'].items():
    path = a.nuget_libraries / name
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise SystemExit('Pinned NuGet build input changed: ' + name)
version, sdk_root = subprocess.check_output(['dotnet', '--list-sdks'], text=True).splitlines()[-1].split(' ', 1)
csc = pathlib.Path(sdk_root.strip('[]')) / version / 'Roslyn/bincore/csc.dll'
with tempfile.TemporaryDirectory(prefix='nemerle-nuget-build-') as directory:
    response = pathlib.Path(directory) / 'adapter.rsp'
    response.write_text('\n'.join(['-nologo', '-nostdlib+', '-target:library',
        '-out:"' + str(a.toolchain.resolve() / 'Nemerle.Scripting.NuGet.dll') + '"'] +
        ['-r:"' + str(path.resolve()) + '"' for path in a.references.glob('*.dll')] +
        ['-r:"' + str(a.nuget_libraries.resolve() / name) + '"' for name in manifest['files'] if name.endswith('.dll')] +
        ['-r:"' + str(a.toolchain.resolve() / name) + '"' for name in ('Nemerle.dll', 'Nemerle.Scripting.dll')] +
        ['"' + str(repo / 'scripting-nuget/NuGetScriptResolver.cs') + '"']))
    subprocess.run(['dotnet', str(csc), '@' + str(response)], check=True)
for name in manifest['files']:
    target = 'NuGet.RuntimeGraph.json' if name == 'PortableRuntimeIdentifierGraph.json' else name
    shutil.copy2(a.nuget_libraries / name, a.toolchain / target)
shutil.copy2(repo / 'scripting-nuget/THIRD-PARTY-NOTICES.txt', a.toolchain / 'Nemerle.Scripting.NuGet.NOTICES.txt')
print('PASS: SDK-independent NuGet adapter built with verified client-library inputs')
