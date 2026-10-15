#!/usr/bin/env python3
"""Run focused upstream lexer/parser/macro fixtures on the prototype CLR compiler."""
import argparse
import pathlib
import re
import shutil
import subprocess
import tempfile

p=argparse.ArgumentParser()
p.add_argument('--toolchain',type=pathlib.Path,required=True)
p.add_argument('--references',type=pathlib.Path,required=True)
a=p.parse_args()
repo=pathlib.Path(__file__).resolve().parents[1]
work=pathlib.Path(tempfile.mkdtemp(prefix='nemerle-grammar-upstream-'))
print('Upstream parser/macro artifacts:',work,flush=True)
for f in a.toolchain.iterdir():
    if f.is_file(): shutil.copy2(f,work/f.name)
for name in ['parser','lexer','basic-macros','std-macros','quotations']:
    # A file is its module: the fixture is compiled as <name with _>.n in a source root of its own.
    source=(repo/'testsuite/positive'/(name+'.n')).read_text(encoding='utf-8-sig')
    root=work/'src'/name; root.mkdir(parents=True)
    fixture=root/(name.replace('-','_')+'.n'); fixture.write_text(source,encoding='utf-8')
    output=work/(name+'.exe')
    command=['dotnet',str(work/'ncc.exe'),str(fixture),'-source-root:'+str(root),'-no-color','-nowarn:10003',
        '-out:'+str(output),'-target-references:'+str(a.references.resolve()),
        '-r:'+str(work/'Nemerle.Compiler.dll')]
    if name == "quotations": command.append("-target:library")
    compiled=subprocess.run(command,cwd=work,text=True,capture_output=True,timeout=90)
    (work/(name+'.compile.log')).write_text(compiled.stdout+compiled.stderr)
    assert compiled.returncode==0,(name,compiled.stdout,compiled.stderr)
    if name == 'quotations':
        print('PASS: upstream quotations (library compilation)',flush=True)
        continue
    shutil.copy2(work/'ncc.runtimeconfig.json',output.with_suffix('.runtimeconfig.json'))
    executed=subprocess.run(['dotnet',str(output)],cwd=work,text=True,capture_output=True,timeout=60)
    (work/(name+'.run.log')).write_text(executed.stdout+executed.stderr)
    assert executed.returncode==0,(name,executed.stdout,executed.stderr)
    expected=re.search(r'BEGIN-OUTPUT\r?\n(.*?)END-OUTPUT',source,re.S)
    if expected: assert executed.stdout.replace('\r\n','\n').strip()==expected.group(1).replace('\r\n','\n').strip(),(name,executed.stdout,expected.group(1))
    print('PASS: upstream '+name,flush=True)
