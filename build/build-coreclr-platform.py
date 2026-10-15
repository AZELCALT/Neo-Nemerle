#!/usr/bin/env python3
"""Build the CLR adapter from source, using SDK csc only as a build input."""
import argparse
import pathlib
import subprocess
import tempfile
p=argparse.ArgumentParser()
p.add_argument('--toolchain', type=pathlib.Path, required=True)
p.add_argument('--references', type=pathlib.Path, required=True)
a=p.parse_args()
repo=pathlib.Path(__file__).resolve().parents[1]
version, sdk_root=subprocess.check_output(['dotnet','--list-sdks'],text=True).splitlines()[-1].split(' ',1)
csc=pathlib.Path(sdk_root.strip('[]'))/version/'Roslyn/bincore/csc.dll'
with tempfile.TemporaryDirectory(prefix='nemerle-platform-build-') as work:
 rsp=pathlib.Path(work)/'platform.rsp'
 rsp.write_text('\n'.join(['-nologo','-nostdlib+','-define:MODERN_CLR','-target:library',
  '-keyfile:"'+str(repo/'misc/keys/Nemerle.Compiler.snk')+'"',
  '-out:"'+str(a.toolchain.resolve()/'Nemerle.Platform.dll')+'"']+
  ['-r:"'+str(x.resolve())+'"' for x in sorted(a.references.glob('*.dll'))]+
  ['-r:"'+str(a.toolchain.resolve()/'Mono.Cecil.dll')+'"']+
  ['"'+str(x)+'"' for x in sorted((repo/'platform').glob('*.cs'))]))
 subprocess.run(['dotnet',str(csc),'@'+str(rsp)],check=True,timeout=60)
subprocess.run(['sn','-vf',str(a.toolchain/'Nemerle.Platform.dll')],check=True)
print('PASS: source-built signed CLR platform adapter')
