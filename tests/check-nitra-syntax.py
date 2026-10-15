#!/usr/bin/env python3
"""Build a CLR host and exercise native declarations and raw foreign recognition."""
import argparse,pathlib,subprocess,shutil,tempfile
p=argparse.ArgumentParser();p.add_argument('--toolchain',type=pathlib.Path,required=True);p.add_argument('--references',type=pathlib.Path,required=True);a=p.parse_args()
w=pathlib.Path(tempfile.mkdtemp(prefix='nemerle-nitra-checks-'));print('Nitra checks:',w,flush=True)
for f in a.toolchain.iterdir():
 if f.is_file(): shutil.copy2(f,w/f.name)
v,r=subprocess.check_output(['dotnet','--list-sdks'],text=True).splitlines()[-1].split(' ',1);csc=pathlib.Path(r.strip('[]'))/v/'Roslyn/bincore/csc.dll'
rsp=w/'checks.rsp';rsp.write_text('\n'.join(['-nologo','-nostdlib+','-target:exe','-out:"'+str(w/'Checks.dll')+'"']+['-r:"'+str(f.resolve())+'"' for f in a.references.glob('*.dll')]+['-r:"'+str(w/f)+'"' for f in ['Nemerle.dll','Nemerle.Compiler.dll']]+['"'+str(pathlib.Path(__file__).with_name('NitraSyntaxChecks.cs').resolve())+'"']))
subprocess.run(['dotnet',str(csc),'@'+str(rsp)],check=True);shutil.copy2(w/'ncc.runtimeconfig.json',w/'Checks.runtimeconfig.json')
subprocess.run(['dotnet',str(w/'Checks.dll'),str(pathlib.Path(__file__).resolve().parents[1]/'grammar/examples/nitra-native')],check=True,timeout=180)
# Verify the inspection-only CLI and mode isolation from an ordinary host process.
source=w/'native.nitra'; source.write_text('syntax module Demo { [StartRule] syntax Start = "x"; }')
result=subprocess.run(['dotnet',str(w/'ncc.exe'),'-nitra-syntax',str(source),'-out:'+str(w/'unused.dll'),'-no-color'],capture_output=True,text=True,timeout=60)
assert result.returncode==0,(result.stdout,result.stderr)
import json
assert json.loads(result.stdout)['surfaceValidated']
assert not (w/'unused.dll').exists()
alias=subprocess.run(['dotnet',str(w/'ncc.exe'),'-experimental-nitra-syntax',str(source),'-out:'+str(w/'unused.dll'),'-no-color'],capture_output=True,text=True,timeout=60)
assert alias.returncode==0 and json.loads(alias.stdout)['surfaceValidated'],(alias.stdout,alias.stderr)
assert not (w/'unused.dll').exists()
print('PASS: inspection CLI (-nitra-syntax, old alias accepted) emits JSON only')
