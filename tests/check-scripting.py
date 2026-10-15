#!/usr/bin/env python3
"""Check the public scripting API and source/AOT/runtime-only CLI paths."""
import argparse
import pathlib
import shutil
import subprocess
import tempfile

parser = argparse.ArgumentParser()
parser.add_argument('--toolchain', type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[1] / 'boot/coreclr')
parser.add_argument('--references', type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[1] / 'boot/coreclr' / 'references')
args = parser.parse_args()
here = pathlib.Path(__file__).resolve().parent
work = pathlib.Path(tempfile.mkdtemp(prefix='nemerle-scripting-'))
print('Scripting artifacts:', work, flush=True)
for path in args.toolchain.iterdir():
    if path.is_file() and path.suffix in ('.dll', '.json'):
        shutil.copy2(path, work / path.name)
version, sdk_root = subprocess.check_output(['dotnet', '--list-sdks'], text=True).splitlines()[-1].split(' ', 1)
csc = pathlib.Path(sdk_root.strip('[]')) / version / 'Roslyn/bincore/csc.dll'
response = work / 'checks.rsp'
response.write_text('\n'.join(['-nologo', '-nostdlib+', '-debug:portable', '-target:exe', '-out:"' + str(work / 'Checks.dll') + '"'] +
    ['-r:"' + str(p.resolve()) + '"' for p in args.references.glob('*.dll')] +
    ['-r:"' + str(work / name) + '"' for name in ('Nemerle.dll', 'Nemerle.Compiler.dll', 'Nemerle.Scripting.dll')] +
    ['"' + str(here / 'ScriptingChecks.cs') + '"']))
subprocess.run(['dotnet', str(csc), '@' + str(response)], check=True, timeout=60)
shutil.copy2(work / 'ncc.runtimeconfig.json', work / 'Checks.runtimeconfig.json')
subprocess.run(['dotnet', str(work / 'Checks.dll'), str(work)], cwd=work, check=True, timeout=120)

source = work / 'cli.n'
source.write_text('args.Length + 40\n')
runner = args.toolchain.resolve() / 'nscript.exe'
def cli(*arguments):
    result = subprocess.run(['dotnet', str(runner), '--cache-dir', str(work / 'cli-cache'), *map(str, arguments)], cwd=work,
        capture_output=True, text=True, timeout=120)
    if result.returncode: raise RuntimeError(result.stdout + result.stderr)
    return result.stdout.strip()
assert cli('run', source, '--', 'a', 'b') == '42'
artifact = work / 'cli.dll'
cli('compile', source, artifact)
assert cli('run-compiled', artifact, '--', 'a', 'b') == '42'
runtime_only = work / 'runtime-only'
runtime_only.mkdir()
for name in ('Nemerle.dll', 'Nemerle.Platform.dll', 'Nemerle.Scripting.dll', 'nscript.exe', 'nscript.runtimeconfig.json'):
    shutil.copy2(args.toolchain / name, runtime_only / name)
result = subprocess.run(['dotnet', str(runtime_only / 'nscript.exe'), 'run-compiled', str(artifact), '--', 'a', 'b'],
    cwd=runtime_only, capture_output=True, text=True, timeout=60)
assert result.returncode == 0 and result.stdout.strip() == '42', result.stdout + result.stderr
child = work / 'child.n'
child.write_text('Answer() : int { 42 }\n')
graph = work / 'graph.n'
graph.write_text('[assembly: Import("child.n")]\nchild.Answer()\n')
graph_artifact = work / 'graph.dll'
cli('compile', graph, graph_artifact)
graph_run = subprocess.run(['dotnet', str(runtime_only / 'nscript.exe'), 'run-compiled', str(graph_artifact)], cwd=runtime_only, capture_output=True, text=True, timeout=60)
assert graph_run.returncode == 0 and graph_run.stdout.strip() == '42', graph_run.stdout + graph_run.stderr
print('PASS: imported script graph evaluated without compiler, macros or SDK')
repl = subprocess.run(['dotnet', str(runner), 'repl', '--cache-dir', str(work / 'repl-cache')],
    input='mutable count : int = 1;\ncount = count + 1; count\n:begin\nRead() : int { count }\nRead()\n:end\n:quit\n', cwd=work, capture_output=True, text=True, timeout=120)
assert repl.returncode == 0 and '2' in repl.stdout, repl.stdout + repl.stderr
reopened = subprocess.run(['dotnet', str(runner), 'repl', '--cache-dir', str(work / 'repl-cache')],
    input=':history\n:quit\n', cwd=work, capture_output=True, text=True, timeout=120)
assert reopened.returncode == 0 and 'count' in reopened.stdout, reopened.stdout + reopened.stderr
auto = subprocess.run(['dotnet', str(runner), 'repl', '--cache-dir', str(work / 'auto-cache')], input='40 +\n2\nRead() : int {\n42\n}\nRead()\n:quit\n', cwd=work, capture_output=True, text=True, timeout=120)
assert auto.returncode == 0 and auto.stdout.count('42') == 2 and 'error' not in auto.stderr, auto.stdout + auto.stderr
print('PASS: automatic multiline expressions and declarations')
print('PASS: interactive submissions, multiline input and persistent history without automatic replay')
print('PASS: source-run, compile, artifact-run and artifact evaluation without compiler/macros/SDK reference assemblies')
