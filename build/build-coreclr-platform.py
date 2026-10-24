#!/usr/bin/env python3
"""Build the CLR adapter from source, using SDK csc only as a build input."""
import argparse
import pathlib
import subprocess
import tempfile
from tooling import net10_csc, verify_strong_name
p=argparse.ArgumentParser()
p.add_argument('--toolchain', type=pathlib.Path, required=True)
p.add_argument('--references', type=pathlib.Path, required=True)
a=p.parse_args()
repo=pathlib.Path(__file__).resolve().parents[1]
csc=net10_csc()
with tempfile.TemporaryDirectory(prefix='nemerle-platform-build-') as work:
 rsp=pathlib.Path(work)/'platform.rsp'
 rsp.write_text('\n'.join(['-nologo','-nostdlib+','-define:MODERN_CLR','-target:library',
  '-keyfile:"'+str(repo/'misc/keys/Nemerle.Compiler.snk')+'"',
  '-out:"'+str(a.toolchain.resolve()/'Nemerle.Platform.dll')+'"']+
  ['-r:"'+str(x.resolve())+'"' for x in sorted(a.references.glob('*.dll'))]+
  ['-r:"'+str(a.toolchain.resolve()/'Mono.Cecil.dll')+'"']+
  ['"'+str(x)+'"' for x in sorted((repo/'platform').glob('*.cs'))]))
 subprocess.run(['dotnet',str(csc),'@'+str(rsp)],check=True,timeout=60)
verify_strong_name(a.toolchain/'Nemerle.Platform.dll')
print('PASS: source-built signed CLR platform adapter')
