#!/usr/bin/env python3
"""Compile grammar/space through native mappings, with no host callbacks.

External parsers are disabled in both the test host and its grammar compilation.
"""
import argparse, pathlib, shutil, subprocess, tempfile
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--toolchain', type=pathlib.Path, required=True)
p.add_argument('--native-core', type=pathlib.Path, required=True)
p.add_argument('--references', type=pathlib.Path, required=True)
p.add_argument('--checks', default='NitraAutomaticSourceChecks.cs', choices=['NitraAutomaticSourceChecks.cs','NitraDialectChecks.cs'])
a = p.parse_args()
w = pathlib.Path(tempfile.mkdtemp(prefix='nemerle-native-source-'))
print('Automatic native source checks:', w, flush=True)
for root in (a.toolchain, a.native_core):
    for f in root.iterdir():
        if f.is_file() and f.suffix in {'.dll', '.exe', '.json', '.nitrametadata'}:
            shutil.copy2(f, w / f.name)
v,r = subprocess.check_output(['dotnet','--list-sdks'],text=True).splitlines()[-1].split(' ',1)
csc = pathlib.Path(r.strip('[]'))/v/'Roslyn/bincore/csc.dll'
here = pathlib.Path(__file__).resolve().parent
rsp = w/'checks.rsp'
rsp.write_text('\n'.join(['-nologo','-nostdlib+','-target:exe','-out:"'+str(w/'Checks.dll')+'"']
    + ['-r:"'+str(f.resolve())+'"' for f in a.references.glob('*.dll')]
    + ['-r:"'+str(w/f)+'"' for f in ['Nemerle.dll','Nemerle.Compiler.dll']]
    + ['"'+str(here/a.checks)+'"', '"'+str(here/'TopLevelSpaces.cs')+'"']))
subprocess.run(['dotnet',str(csc),'@'+str(rsp)],check=True)
shutil.copy2(w/'ncc.runtimeconfig.json',w/'Checks.runtimeconfig.json')
subprocess.run(['dotnet',str(w/'Checks.dll'),str(w),str(a.references.resolve())],cwd=w,check=True,timeout=300)
