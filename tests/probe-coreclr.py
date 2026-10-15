#!/usr/bin/env python3
"""Build the modern platform offline, then exercise the real compiler on CoreCLR."""
import argparse
import json
import pathlib
import shutil
import subprocess
import tempfile

parser = argparse.ArgumentParser()
parser.add_argument('--compiler', required=True, type=pathlib.Path)
parser.add_argument('--support', required=True, type=pathlib.Path)
args = parser.parse_args()
here = pathlib.Path(__file__).resolve().parent
repo = here.parent
work = pathlib.Path(tempfile.mkdtemp(prefix='nemerle-coreclr-'))
print('CoreCLR artifacts:', work, flush=True)
for folder in (args.support, args.compiler):
    for path in folder.glob('*'):
        if path.suffix in ('.dll', '.exe'): shutil.copy2(path, work / path.name)
sdk_version, sdk_root = subprocess.check_output(['dotnet', '--list-sdks'], text=True).splitlines()[-1].split(' ', 1)
sdk = pathlib.Path(sdk_root.strip('[]')) / sdk_version
# The compiler's optional CodeDOM facade is a separate compatibility dependency.
shutil.copy2(sdk / 'System.CodeDom.dll', work / 'System.CodeDom.dll')
ref = max((sdk.parent.parent / 'packs/Microsoft.NETCore.App.Ref').iterdir(),
          key=lambda p: tuple(int(v) for v in p.name.split('.')))
tfm = 'net' + ref.name.split('.')[0] + '.0'
cecil = sorted(pathlib.Path('/usr/lib/mono/gac/Mono.Cecil').glob('0.11*__*/Mono.Cecil.dll'))[-1]
shutil.copy2(cecil, work / 'Mono.Cecil.dll')
rsp = work / 'platform.rsp'
rsp.write_text('\n'.join(['-nologo', '-nostdlib+', '-define:MODERN_CLR', '-target:library',
    '-out:"' + str(work / 'Nemerle.Platform.dll') + '"',
    '-keyfile:"' + str(repo / 'misc/keys/Nemerle.Compiler.snk') + '"',
    '-r:"' + str(cecil) + '"'] +
    ['-r:"' + str(p) + '"' for p in (ref / 'ref' / tfm).glob('*.dll')] +
    ['"' + str(p) + '"' for p in (repo / 'platform').glob('*.cs')]))
subprocess.run(['dotnet', str(sdk / 'Roslyn/bincore/csc.dll'), '@' + str(rsp)], check=True)
(work / 'ncc.runtimeconfig.json').write_text(json.dumps({'runtimeOptions': {
    'tfm': tfm, 'framework': {'name': 'Microsoft.NETCore.App', 'version': ref.name}}}))
fixture = work / 'sample.n'
fixture.write_text('using System;\nmask api { Twice(x : int) : int { x * 2 } }\nRun() : int { api.Twice(21) }\n')
command = ['dotnet', str(work / 'ncc.exe'), '-source-root:' + str(work),
           str(fixture), '-target-references:' + str(ref / 'ref' / tfm), '-target:library', '-out:' + str(work / 'sample.dll'), '-no-color', '-keyfile:' + str(repo / 'misc/keys/Nemerle.Compiler.snk')]
print('Running:', ' '.join(command), flush=True)
result = subprocess.run(command, cwd=work, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
(work / 'compiler.log').write_text(result.stdout)
print(result.stdout, flush=True)
if result.returncode: raise SystemExit(result.returncode)
subprocess.run(['sn', '-vf', str(work / 'sample.dll')], check=True)

def compile_nemerle(source, output, extra=()):
    command = ['dotnet', str(work / 'ncc.exe'), '-source-root:' + str(work),
               str(source), '-target-references:' + str(ref / 'ref' / tfm), '-target:library', '-out:' + str(work / output), '-no-color', *extra]
    run = subprocess.run(command, cwd=work, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    (work / (output + '.log')).write_text(run.stdout)
    print(run.stdout, flush=True)
    if run.returncode: raise SystemExit(run.returncode)

macros = work / 'extensions.n'
macros.write_text('Base() : int { 4 }\nmacro WithBase(value) { <[ Base() + $value ]> }\n')
compile_nemerle(macros, 'extensions.dll', ['-r:' + str(work / 'Nemerle.Compiler.dll')])
consumer = work / 'consumer.n'
consumer.write_text('using extensions;\nBase() : int { 99 }\nRun() : int { WithBase(1) }\n')
compile_nemerle(consumer, 'consumer.dll', ['-r:' + str(work / 'extensions.dll')])
host = work / 'Host.cs'
host.write_text('using System; class Host { static void Main() { if (sample.Run() != 42 || consumer.Run() != 5) throw new Exception("Modern compilation failed"); Console.WriteLine("PASS: real CoreCLR compiler, file modules, masks, macro compilation and expansion, C# execution"); } }')
host_rsp = work / 'host.rsp'
host_rsp.write_text('\n'.join(['-nologo', '-nostdlib+', '-target:exe', '-out:"' + str(work / 'Host.dll') + '"'] +
    ['-r:"' + str(p) + '"' for p in (ref / 'ref' / tfm).glob('*.dll')] +
    ['-r:"' + str(work / name) + '"' for name in ['sample.dll', 'consumer.dll']] + ['"' + str(host) + '"']))
subprocess.run(['dotnet', str(sdk / 'Roslyn/bincore/csc.dll'), '@' + str(host_rsp)], check=True)
shutil.copy2(work / 'ncc.runtimeconfig.json', work / 'Host.runtimeconfig.json')
subprocess.run(['dotnet', str(work / 'Host.dll')], cwd=work, check=True)


# Real compiler hosting uses runnable emission rather than persisted metadata.
in_memory_rsp = work / 'in-memory.rsp'
in_memory_rsp.write_text('\n'.join(['-nologo', '-nostdlib+', '-target:exe', '-out:"' + str(work / 'InMemoryHost.dll') + '"'] +
    ['-r:"' + str(p) + '"' for p in (ref / 'ref' / tfm).glob('*.dll')] +
    ['-r:"' + str(work / name) + '"' for name in ['Nemerle.dll', 'Nemerle.Compiler.dll']] +
    ['"' + str(here / 'InMemoryHost.cs') + '"']))
subprocess.run(['dotnet', str(sdk / 'Roslyn/bincore/csc.dll'), '@' + str(in_memory_rsp)], check=True)
shutil.copy2(work / 'ncc.runtimeconfig.json', work / 'InMemoryHost.runtimeconfig.json')
subprocess.run(['dotnet', str(work / 'InMemoryHost.dll'), str(here / 'hello.n')], cwd=work, check=True)
print('PASS: real CoreCLR in-memory compiler hosting', flush=True)

# Executables get a runtime configuration without requiring SDK tooling at run time.
subprocess.run(['dotnet', str(work / 'ncc.exe'), str(here / 'hello.n'), '-source-root:' + str(here),
    '-out:' + str(work / 'hello.exe'), '-target-references:' + str(ref / 'ref' / tfm), '-no-color'], cwd=work, check=True)
subprocess.run(['dotnet', str(work / 'hello.exe')], cwd=work, check=True)
print('PASS: saved CoreCLR executable and generated runtime configuration', flush=True)

runtime_rsp = work / 'runtime-checks.rsp'
runtime_rsp.write_text('\n'.join(['-nologo', '-nostdlib+', '-target:exe', '-out:"' + str(work / 'RuntimeChecks.dll') + '"'] +
    ['-r:"' + str(p) + '"' for p in (ref / 'ref' / tfm).glob('*.dll')] +
    ['-r:"' + str(work / 'Nemerle.dll') + '"', '"' + str(here / 'RuntimeChecks.cs') + '"']))
subprocess.run(['dotnet', str(sdk / 'Roslyn/bincore/csc.dll'), '@' + str(runtime_rsp)], check=True)
shutil.copy2(work / 'ncc.runtimeconfig.json', work / 'RuntimeChecks.runtimeconfig.json')
subprocess.run(['dotnet', str(work / 'RuntimeChecks.dll')], cwd=work, check=True)
