#!/usr/bin/env python3
"""Exercise settled structural objects and the direct compiler output bridge."""
import argparse,pathlib,subprocess,shutil,tempfile
p=argparse.ArgumentParser();p.add_argument('--toolchain',type=pathlib.Path,required=True);p.add_argument('--references',type=pathlib.Path,required=True);a=p.parse_args()
w=pathlib.Path(tempfile.mkdtemp(prefix='nemerle-nitra-structures-'));print('Structure checks:',w,flush=True)
for f in a.toolchain.iterdir():
 if f.is_file(): shutil.copy2(f,w/f.name)
v,r=subprocess.check_output(['dotnet','--list-sdks'],text=True).splitlines()[-1].split(' ',1);csc=pathlib.Path(r.strip('[]'))/v/'Roslyn/bincore/csc.dll'
rsp=w/'checks.rsp';rsp.write_text('\n'.join(['-nologo','-nostdlib+','-target:exe','-out:"'+str(w/'Checks.dll')+'"']+['-r:"'+str(f.resolve())+'"' for f in a.references.glob('*.dll')]+['-r:"'+str(w/f)+'"' for f in ['Nemerle.dll','Nemerle.Compiler.dll']]+['"'+str(pathlib.Path(__file__).with_name('NitraStructureChecks.cs').resolve())+'"']))
subprocess.run(['dotnet',str(csc),'@'+str(rsp)],check=True);shutil.copy2(w/'ncc.runtimeconfig.json',w/'Checks.runtimeconfig.json')
subprocess.run(['dotnet',str(w/'Checks.dll')],check=True,timeout=180)
here=pathlib.Path(__file__).resolve().parent
common=['dotnet',str(w/'ncc.exe'),'-target-references:'+str(a.references.resolve()),'-no-color','-source-root:'+str(here)]
subprocess.run(common+[str(here/'NitraTupleConstructor.n'),'-out:'+str(w/'ConstructorChecks.exe')],check=True,timeout=180)
shutil.copy2(w/'ncc.runtimeconfig.json',w/'ConstructorChecks.runtimeconfig.json')
subprocess.run(['dotnet',str(w/'ConstructorChecks.exe')],check=True,timeout=30)
bad=w/'InvalidEnum.n';bad.write_text((here/'NitraTupleConstructor.n').read_text()+'\nmask Invalid { Run() : void { _=GenericEnum.Identity(42); } }')
rejected=subprocess.run(common+[str(bad),'-source-root:'+str(w),'-target:library','-out:'+str(w/'InvalidEnum.dll')],capture_output=True,text=True,timeout=60)
assert rejected.returncode!=0 and 'not a subtype of System.Enum' in rejected.stdout+rejected.stderr and not (w/'InvalidEnum.dll').exists(), ('enum constraint must reject non-enum structs',rejected.stdout,rejected.stderr)
print('PASS: enum generic constraint accepts enums and rejects ordinary structs',flush=True)
subprocess.run(common+[str(here/'NativeOutputChecks.n'),'-target:library','-out:'+str(w/'NativeOutput.dll'),'-r:'+str(w/'Nemerle.Compiler.dll')],check=True,timeout=180)
subprocess.run(common+[str(here/'NitraDirectOutputConsumer.n'),'-out:'+str(w/'Consumer.exe'),'-r:'+str(w/'NativeOutput.dll')],check=True,timeout=180)
shutil.copy2(w/'ncc.runtimeconfig.json',w/'Consumer.runtimeconfig.json')
subprocess.run(['dotnet',str(w/'Consumer.exe')],check=True,timeout=30)
rsp=w/'source.rsp';rsp.write_text('\n'.join(['-nologo','-nostdlib+','-target:exe','-out:"'+str(w/'SourceChecks.dll')+'"']+['-r:"'+str(f.resolve())+'"' for f in a.references.glob('*.dll')]+['-r:"'+str(w/f)+'"' for f in ['Nemerle.dll','Nemerle.Compiler.dll','NativeOutput.dll']]+['"'+str(here/'NitraSourceChecks.cs')+'"','"'+str(here/'TopLevelSpaces.cs')+'"']))
subprocess.run(['dotnet',str(csc),'@'+str(rsp)],check=True);shutil.copy2(w/'ncc.runtimeconfig.json',w/'SourceChecks.runtimeconfig.json')
subprocess.run(['dotnet',str(w/'SourceChecks.dll'),str(w),str(a.references.resolve())],cwd=w,check=True,timeout=180)
