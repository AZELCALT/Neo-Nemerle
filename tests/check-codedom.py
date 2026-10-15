#!/usr/bin/env python3
"""CodeDOM compiles file modules: each CodeNamespace becomes <Ns path>.n, source text Source<i>.n; namespace text is rejected.

    check-codedom.py --toolchain DIR --references REFS"""
import argparse, pathlib, shutil, subprocess, tempfile

p = argparse.ArgumentParser()
p.add_argument('--toolchain', type=pathlib.Path, required=True)
p.add_argument('--references', type=pathlib.Path, required=True)
a = p.parse_args()
here = pathlib.Path(__file__).resolve().parent
w = pathlib.Path(tempfile.mkdtemp(prefix='nemerle-codedom-'))
print('CodeDOM checks:', w, flush=True)
for f in a.toolchain.iterdir():
    if f.is_file() and f.suffix in {'.dll', '.json'}: shutil.copy2(f, w / f.name)
version, folder = subprocess.check_output(['dotnet', '--list-sdks'], text=True).splitlines()[-1].split(' ', 1)
csc = pathlib.Path(folder.strip('[]')) / version / 'Roslyn/bincore/csc.dll'
rsp = w / 'checks.rsp'
rsp.write_text('\n'.join(['-nologo', '-nostdlib+', '-target:exe', '-out:"' + str(w / 'Checks.dll') + '"']
    + ['-r:"' + str(f) + '"' for f in sorted(a.references.resolve().glob('*.dll'))]
    + ['-r:"' + str(w / n) + '"' for n in ('Nemerle.dll', 'Nemerle.Compiler.dll', 'System.CodeDom.dll')]
    + ['"' + str(here / 'CodeDomChecks.cs') + '"']))
subprocess.run(['dotnet', str(csc), '@' + str(rsp)], check=True)
shutil.copy2(w / 'ncc.runtimeconfig.json', w / 'Checks.runtimeconfig.json')
subprocess.run(['dotnet', str(w / 'Checks.dll'), str(a.references.resolve()), str(w)], cwd=w, check=True, timeout=300)
