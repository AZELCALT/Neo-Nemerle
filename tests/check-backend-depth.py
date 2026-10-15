#!/usr/bin/env python3
"""Diagnose ordinary Nemerle backend depth independently of grammar/space parsing."""
import argparse,hashlib,json,os,pathlib,shutil,subprocess,tempfile
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--toolchain',type=pathlib.Path,required=True)
p.add_argument('--references',type=pathlib.Path,required=True)
p.add_argument('--output',type=pathlib.Path,required=True)
a=p.parse_args();w=pathlib.Path(tempfile.mkdtemp(prefix='nemerle-backend-depth-'))
for f in a.toolchain.iterdir():
    if f.is_file():shutil.copy2(f,w/f.name)
env=dict(os.environ,DOTNET_CLI_HOME=str(w/'dotnet-home'),DOTNET_TieredCompilation='0',DOTNET_gcServer='0')
report={'diagnostic_only':True,'work':str(w),'toolchain':str(a.toolchain.resolve()),'uses_custom_syntax':False,'stack_size_override':False,'compiler_thread_policy':'unmodified ncc CLI default; see nemerle/ncc/Nemerle/CommandlineCompiler.n:141-157 (160 MiB stack on this 64-bit CLR)','timeout_seconds':None,'cases':[]}
a.output.parent.mkdir(parents=True,exist_ok=True)
for count in [512,2048]:
    source=w/('Depth'+str(count)+'.n');exe=source.with_suffix('.exe')
    source.write_text('module BackendControl { Main() : void { System.Console.WriteLine('+ '+'.join(['7']*count)+'); } }\n')
    command=['dotnet',str(w/'ncc.exe'),'-no-color','-target-references:'+str(a.references.resolve()),'-out:'+str(exe),'-source-root:'+str(w),str(source)]
    result=subprocess.run(command,cwd=w,env=env,capture_output=True,text=True)
    source.with_suffix('.compile.stdout').write_text(result.stdout);source.with_suffix('.compile.stderr').write_text(result.stderr)
    row={'terms':count,'source':str(source),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'command':command,'compile_exit_code':result.returncode,'stderr_tail':result.stderr[-5000:]}
    if result.returncode==0:
        shutil.copy2(w/'ncc.runtimeconfig.json',exe.with_suffix('.runtimeconfig.json'))
        ran=subprocess.run(['dotnet',str(exe)],cwd=w,env=env,capture_output=True,text=True)
        row.update(execution_exit_code=ran.returncode,stdout=ran.stdout.strip(),expected=7*count)
    report['cases'].append(row);a.output.write_text(json.dumps(report,indent=2)+'\n');print('terms',count,'compile exit',result.returncode,flush=True)
print('Report:',a.output)
