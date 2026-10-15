#!/usr/bin/env python3
"""Check resolver graphs and scripted dependencies entirely with a local feed."""
import argparse
import pathlib
import shutil
import subprocess
import tempfile
import zipfile
import functools
import http.server
import json
import threading
p=argparse.ArgumentParser()
p.add_argument('--toolchain',type=pathlib.Path,required=True)
p.add_argument('--references',type=pathlib.Path,required=True)
p.add_argument('--require-http',action='store_true',help='Fail rather than skip when the HTTP fixture cannot open a socket.')
a=p.parse_args()
root=pathlib.Path(__file__).resolve().parent
work=pathlib.Path(tempfile.mkdtemp(prefix='nemerle-nuget-check-'))
print('NuGet checks:',work,flush=True)
tc=a.toolchain.resolve(); refs=a.references.resolve()
for path in tc.iterdir():
    if path.suffix in ('.dll','.json'): shutil.copy2(path,work/path.name)
version,sdkroot=subprocess.check_output(['dotnet','--list-sdks'],text=True).splitlines()[-1].split(' ',1)
csc=pathlib.Path(sdkroot.strip('[]'))/version/'Roslyn/bincore/csc.dll'
feed=work/'feed'; feed.mkdir()
def compile_cs(name,text,extra=()):
    source=work/(name+'.cs');source.write_text(text)
    output=work/(name+'.dll');rsp=work/(name+'.rsp')
    rsp.write_text('\n'.join(['-nologo','-nostdlib+','-target:library','-out:"'+str(output)+'"']+['-r:"'+str(x)+'"' for x in refs.glob('*.dll')]+['-r:"'+str(x)+'"' for x in extra]+['"'+str(source)+'"']))
    subprocess.run(['dotnet',str(csc),'@'+str(rsp)],check=True)
    return output
helper=compile_cs('Helper','public static class HelperApi { public static int Value() => 40; }')
example=compile_cs('Example','public static class ExampleApi { public static int Value() => HelperApi.Value()+2; }',[helper])
def package(name,version,library=None,dependencies=()):
    with zipfile.ZipFile(feed/(name+'.'+version+'.nupkg'),'w') as z:
        deps=''.join('<dependency id="'+n+'" version="'+v+'" />' for n,v in dependencies)
        z.writestr(name+'.nuspec','<?xml version="1.0"?><package><metadata><id>'+name+'</id><version>'+version+'</version><authors>test</authors><description>fixture</description><dependencies><group targetFramework="net10.0">'+deps+'</group></dependencies></metadata></package>')
        if library: z.write(library,'lib/net10.0/'+library.name)
package('Helper','1.0.0',helper)
package('Helper','2.0.0',helper)
package('Example','1.0.0',example,[('Helper','[1.0.0,2.0.0)')])
package('Other','1.0.0',None,[('Helper','[1.0.0]')])
package('Conflict','1.0.0',None,[('Helper','[2.0.0]')])
native=compile_cs('Native','using System.Runtime.InteropServices; public static class NativeFixture { [DllImport("script_fixture", CallingConvention=CallingConvention.Cdecl)] public static extern int Answer(); }')
c_source=work/'native.c';c_source.write_text('int Answer(void) { return 42; }\n')
native_library=work/'libscript_fixture.so'
subprocess.run(['gcc','-shared','-fPIC',str(c_source),'-o',str(native_library)],check=True)
package('Native','1.0.0',native)
with zipfile.ZipFile(feed/'Native.1.0.0.nupkg','a') as z: z.write(native_library,'runtimes/unix-x64/native/libscript_fixture.so')
macro_source=work/'macrofixture.n';macro_source.write_text('using Nemerle.Compiler;\nmacro Answer() syntax ("answer") { <[ 42 : int ]> }\n')
macro_image=work/'macrofixture.dll'
subprocess.run(['dotnet',str(tc/'ncc.exe'),'-source-root:'+str(work),str(macro_source),'-target:library','-out:'+str(macro_image),'-target-references:'+str(refs),'-r:'+str(tc/'Nemerle.Compiler.dll'),'-no-color'],check=True)
package('MacroFixture','1.0.0',macro_image)
source=root/'NuGetScriptingChecks.cs'
rsp=work/'Checks.rsp';rsp.write_text('\n'.join(['-nologo','-nostdlib+','-target:exe','-out:"'+str(work/'NuGetChecks.dll')+'"']+['-r:"'+str(x)+'"' for x in refs.glob('*.dll')]+['-r:"'+str(work/name)+'"' for name in ('Nemerle.dll','Nemerle.Scripting.dll','Nemerle.Scripting.NuGet.dll')]+['"'+str(source)+'"']))
subprocess.run(['dotnet',str(csc),'@'+str(rsp)],check=True)
shutil.copy2(tc/'ncc.runtimeconfig.json',work/'NuGetChecks.runtimeconfig.json')
v3=work/'v3';v3.mkdir()
class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self,format,*args): print('HTTP fixture: '+format%args,flush=True)
try:
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(QuietHandler,directory=str(v3)))
except PermissionError:
    if a.require_http: raise
    server=None
    print('SKIP: HTTP v3 feed check; sandbox disallows socket creation',flush=True)
base='http://127.0.0.1:'+str(server.server_port) if server else ''
(v3/'index.json').write_text(json.dumps({'version':'3.0.0','resources':[{'@id':base+'/flat/','@type':'PackageBaseAddress/3.0.0'}]}))
for archive in feed.glob('*.nupkg'):
    name,version=archive.stem.split('.',1); identity=name.lower();target=v3/'flat'/identity/version;target.mkdir(parents=True)
    shutil.copy2(archive,target/(identity+'.'+version+'.nupkg'))
for directory in (v3/'flat').iterdir():
    (directory/'index.json').write_text(json.dumps({'versions':sorted(x.name for x in directory.iterdir())}))
if server:
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
try:
    subprocess.run(['dotnet',str(work/'NuGetChecks.dll'),str(work),str(refs)]+([base+'/index.json'] if server else []),cwd=work,check=True,timeout=120)
finally:
    if server:
        server.shutdown();server.server_close();thread.join()

runtime_only=work/'runtime-only';runtime_only.mkdir()
for name in ('Nemerle.dll','Nemerle.Platform.dll','Nemerle.Scripting.dll','nscript.exe','nscript.runtimeconfig.json'):
    shutil.copy2(tc/name,runtime_only/name)
shutil.copy2(work/'saved.dll',runtime_only/'saved.dll');shutil.copy2(work/'saved.dll.script',runtime_only/'saved.dll.script')
shutil.copytree(work/'saved.dll.dependencies',runtime_only/'saved.dll.dependencies')
run=subprocess.run(['dotnet',str(runtime_only/'nscript.exe'),'run-compiled',str(runtime_only/'saved.dll')],cwd=runtime_only,capture_output=True,text=True,timeout=60)
assert run.returncode==0 and run.stdout.strip()=='42',run.stdout+run.stderr
print('PASS: relocated bundled dependencies with compiler, SDK references and NuGet adapter absent')
