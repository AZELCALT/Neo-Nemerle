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
# the embedded compiler is the compiler: the same program run as a script and compiled as a file prints the same
# (top-level await, a binding whose value waits, await foreach, local async functions and streams, async lambdas, and
# bindings as a file's top-level code has them)
parity = work / 'parity'
parity.mkdir()
programs = {
    'inferred_async_binding': ('using System.Threading.Tasks;\n'
                               'async def Value() : Task[int] { await Task.Yield(); 5 }\n'
                               'def answer = Value().Result;\nawait Task.Yield();\nSystem.Console.WriteLine(answer)\n', '5'),
    'wait': ('using System.Threading.Tasks;\ndef x = await Task.FromResult(41);\nSystem.Console.WriteLine(x + 1)\n', '42'),
    'each': ('using System;\nusing System.Collections.Generic;\nusing System.Threading.Tasks;\n'
             'async Numbers(n : int) : IAsyncEnumerable[int] { for (mutable i = 1; i <= n; i++) { await Task.Yield(); yield i } }\n'
             'mutable t = 0;\nawait foreach (x in Numbers(3)) t += x;\nConsole.WriteLine(t)\n', '6'),
    'local': ('using System;\nusing System.Collections.Generic;\nusing System.Threading.Tasks;\n'
              'async def S(k : int) : IAsyncEnumerable[int] { yield k; await Task.Yield(); yield k * 2 }\n'
              'async def T() : Task[int] { await Task.Yield(); 5 }\n'
              'def r = T().Result;\nmutable t = r;\nawait foreach (x in S(10)) t += x;\nConsole.WriteLine(t)\n', '35'),
    'mixed': ('using System;\nusing System.Threading.Tasks;\n'
              'def vt : Func[ValueTask[int]] = async () => { await Task.Yield(); 7 };\n'
              'def p = typeof(string).GetProperty("Length");\n'
              'def same = typeof(string).GetField("x") == null;\n'
              'await Task.Yield();\nConsole.WriteLine($"$(await vt()) $(p.Name) $same")\n', '7 Length True'),
    # (many streams at once, some left early: a stream's machine is touched by one thread at a time)
    'streams': ('using System;\nusing System.Collections.Generic;\nusing System.Linq;\nusing System.Threading.Tasks;\nusing Nemerle.Imperative;\n'
                'async Numbers(n : int) : IAsyncEnumerable[int] { for (mutable i = 1; i <= n; i++) { await Task.Yield(); yield i } }\n'
                'async Sum(k : int) : Task[int]\n{\n'
                '  async def Local(n : int) : IAsyncEnumerable[int] { for (mutable i = 1; i <= n; i++) { await Task.Yield(); yield i } }\n'
                '  mutable t = 0;\n  await foreach (x in Numbers(10)) { t += x; when (k % 3 == 0 && x == 5) break }\n'
                '  await foreach (x in Local(4)) t += x;\n  t\n}\n'
                'def all = await Task.WhenAll(Enumerable.Range(0, 4000).Select(k => Sum(k)));\nConsole.WriteLine(all.Sum())\n', '206640'),
    # (bindings that read earlier ones and the local functions above them, `mutable' as `def')
    'bindings': ('def T() : int { 5 }\ndef a = T();\nmutable t = a;\nt += 1;\ndef b = t * 2;\n'
                 'System.Console.WriteLine($"$a $t $b")\n', '5 6 12'),
    # (a local async stream with the token its enumeration is given, as C#'s [EnumeratorCancellation])
    'cancel': ('using System;\nusing System.Collections.Generic;\nusing System.Threading;\nusing System.Runtime.CompilerServices;\n'
               'using System.Threading.Tasks;\n'
               'async def S(n : int, [EnumeratorCancellation] token : CancellationToken = default(CancellationToken)) : IAsyncEnumerable[int]\n'
               '{ for (mutable i = 0; i < n && !token.IsCancellationRequested; i++) { await Task.Yield(); yield i } }\n'
               'def source = CancellationTokenSource();\nmutable t = 0;\n'
               'await foreach (x in S(10).WithCancellation(source.Token)) { t += x; when (x == 3) source.Cancel() }\n'
               'Console.WriteLine(t)\n', '6'),
    'plain': ('async def T() : System.Threading.Tasks.Task[int] { await System.Threading.Tasks.Task.Yield(); 2 }\n'
              'def n = T().Result;\nSystem.Console.WriteLine(n * 21)\n', '42'),
}
ncc = args.toolchain.resolve() / 'ncc.exe'
for name, (text, expected) in programs.items():
    script = parity / (name + '.ns')
    script.write_text(text)
    said = cli('run', script)
    assert said == expected, '%s as a script printed %r, expected %r' % (name, said, expected)
    program = parity / name
    program.mkdir()
    (program / (name + '.n')).write_text(text)
    built = subprocess.run(['dotnet', str(ncc), str(program / (name + '.n')), '-source-root:' + str(program), '-out:' + str(program / (name + '.exe')),
        '-launcher-', '-no-color'], cwd=program, capture_output=True, text=True, timeout=120)
    assert built.returncode == 0, built.stdout + built.stderr
    shutil.copy2(args.toolchain / 'Nemerle.dll', program / 'Nemerle.dll')
    shutil.copy2(args.toolchain / 'ncc.runtimeconfig.json', program / (name + '.runtimeconfig.json'))
    ran = subprocess.run(['dotnet', str(program / (name + '.exe'))], cwd=program, capture_output=True, text=True, timeout=60)
    assert ran.returncode == 0 and ran.stdout.strip() == expected, '%s as a file printed %r %r' % (name, ran.stdout, ran.stderr)
print('PASS: %d programs (async code, bindings) print the same as scripts (the embedded compiler) and as compiled files' % len(programs))
