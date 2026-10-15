#!/usr/bin/env python3
"""Load and exercise source-built native Nitra support without its parser."""
import argparse,pathlib,subprocess,shutil,tempfile,json
p=argparse.ArgumentParser();p.add_argument('--toolchain',type=pathlib.Path,required=True);p.add_argument('--native-core',type=pathlib.Path,required=True);p.add_argument('--references',type=pathlib.Path,required=True);a=p.parse_args()
w=pathlib.Path(tempfile.mkdtemp(prefix='nemerle-native-core-checks-'));print('Native core checks:',w,flush=True)
for root in [a.toolchain,a.native_core]:
 for f in root.iterdir():
  if f.is_file() and f.suffix in {'.dll','.json'}:shutil.copy2(f,w/f.name)
v,r=subprocess.check_output(['dotnet','--list-sdks'],text=True).splitlines()[-1].split(' ',1);csc=pathlib.Path(r.strip('[]'))/v/'Roslyn/bincore/csc.dll'
rsp=w/'checks.rsp';rsp.write_text('\n'.join(['-nologo','-nostdlib+','-target:exe','-out:"'+str(w/'Checks.dll')+'"']+['-r:"'+str(f.resolve())+'"' for f in a.references.glob('*.dll')]+['-r:"'+str(w/f)+'"' for f in ['Nemerle.dll','Nemerle.Compiler.dll','Integrated.Nitra.Runtime.dll','Integrated.DotNetLang.dll','Integrated.Nitra.Grammar.dll','Integrated.Nitra.Compiler.dll']]+['"'+str(pathlib.Path(__file__).with_name('NitraCoreChecks.cs').resolve())+'"']))
subprocess.run(['dotnet',str(csc),'@'+str(rsp)],check=True);shutil.copy2(w/'ncc.runtimeconfig.json',w/'Checks.runtimeconfig.json')
subprocess.run(['dotnet',str(w/'Checks.dll'),str(w)],check=True,timeout=60)
