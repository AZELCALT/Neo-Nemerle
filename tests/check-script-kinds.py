#!/usr/bin/env python3
"""Script kinds declared by libraries ([ScriptDefinition(".build.n")], like Kotlin's @KotlinScript).

    check-script-kinds.py --toolchain DIR --references REFS

A library declares a kind: its class is the scripts' base class, its imports are opened, and the library's grammar and
macros come with it (continuation section). A script `x.build.n` needs no setup lines. Kinds are found next to the
script and on NEMERLE_SCRIPT_PATH; compiled kind scripts load again; a static Configure refines the definition; plain
scripts are unaffected; a kind nobody declares is reported clearly."""
import argparse, os, pathlib, shutil, subprocess, tempfile

p = argparse.ArgumentParser()
p.add_argument('--toolchain', type=pathlib.Path, required=True)
p.add_argument('--references', type=pathlib.Path, required=True)
a = p.parse_args()
T = a.toolchain.resolve()
w = pathlib.Path(tempfile.mkdtemp(prefix='nemerle-script-kinds-'))
print('Script kind checks:', w, flush=True)


def run(command, cwd=None, env=None, ok=True):
    r = subprocess.run([str(c) for c in command], cwd=cwd, env=env, capture_output=True, text=True)
    if (r.returncode == 0) != ok:
        raise SystemExit('FAILED: %s\n%s%s' % (' '.join(map(str, command)), r.stdout, r.stderr))
    return r


KIND = '''using Nemerle.Compiler;
using Nemerle.Scripting.kinds;

grammar Steps
{
  using Nemerle.Compiler.Parsetree;
  syntax module Step
  {
    using Nitra.Core;
    [StartRule] syntax Input = Item { map PExpr { Item } }
    syntax Item
    {
      map PExpr;
      | Copy = "copy" { map PExpr = <[ System.Console.WriteLine("copying files") ]>; }
      | Pack = "pack" { map PExpr = <[ System.Console.WriteLine("packing") ]>; }
    }
  }
}

macro twice(e)
{
  <[ $e * 2 ]>
}

[ScriptDefinition(".build.n", DisplayName = "Build script", Imports = array["System.Console", "buildkind"])]
public class BuildScript
{
  public Target : string { get { "release" } }
  public Log(message : string) : void { System.Console.WriteLine("[build] " + message) }
}

/// A second kind configured in code: a static module only configures (no base class).
[ScriptDefinition(".task.n")]
public module TaskKind
{
  public Configure(definition : Nemerle.Scripting.contracts.ScriptDefinition) : void
  {
    definition.Imports.Add("System.Console");
    definition.CompilerOptions.Add("-define:TASK");
  }
}
'''
lib = w / 'libs'
lib.mkdir()
(lib / 'buildkind.n').write_text(KIND)
run([T / 'ncc', lib / 'buildkind.n', '-source-root:' + str(lib), '-target:library', '-out:' + str(lib / 'buildkind.dll'), '-no-color',
     '-r:' + str(T / 'Nemerle.Compiler.dll'), '-r:' + str(T / 'Nemerle.Scripting.dll')])
SCRIPT = 'Log("target " + Target);\nWriteLine(twice(21));\nspace Steps { copy }\n'
EXPECTED = ['[build] target release', '42', 'copying files']

# 1. the kind library next to the script
here = w / 'project'
here.mkdir()
shutil.copy2(lib / 'buildkind.dll', here / 'buildkind.dll')
(here / 'deploy.build.n').write_text(SCRIPT)
out = run([T / 'nscript', 'run', here / 'deploy.build.n', '--no-cache'], cwd=here).stdout.splitlines()
if out != EXPECTED:
    raise SystemExit('FAILED: kind next to the script printed %r' % out)
print('PASS: a .build.n script with no setup uses the kind\'s base class, imports, macro and grammar', flush=True)

# 2. the kind library on NEMERLE_SCRIPT_PATH; compile and load again
away = w / 'elsewhere'
away.mkdir()
(away / 'deploy.build.n').write_text(SCRIPT)
env = dict(os.environ, NEMERLE_SCRIPT_PATH=str(lib))
if run([T / 'nscript', 'run', away / 'deploy.build.n', '--no-cache'], cwd=away, env=env).stdout.splitlines() != EXPECTED:
    raise SystemExit('FAILED: kind found through NEMERLE_SCRIPT_PATH')
run([T / 'nscript', 'compile', away / 'deploy.build.n', away / 'deploy.dll', '--no-cache'], cwd=away, env=env)
if run([T / 'nscript', 'run-compiled', away / 'deploy.dll'], cwd=away, env=env).stdout.splitlines() != EXPECTED:
    raise SystemExit('FAILED: compiled kind script does not load again')
print('PASS: kinds are found on NEMERLE_SCRIPT_PATH, and a compiled kind script loads again', flush=True)

# 3. a kind configured by a static Configure (imports, compiler options)
(here / 'hello.task.n').write_text('#if TASK\nWriteLine("task mode");\n#endif\n')
if run([T / 'nscript', 'run', here / 'hello.task.n', '--no-cache'], cwd=here).stdout.strip() != 'task mode':
    raise SystemExit('FAILED: Configure did not refine the .task.n definition')
print('PASS: a kind\'s static Configure refines its definition', flush=True)

# 4. plain scripts are unaffected; an undeclared kind is reported
(here / 'plain.n').write_text('System.Console.WriteLine(6 * 7);\n')
if run([T / 'nscript', 'run', here / 'plain.n', '--no-cache'], cwd=here).stdout.strip() != '42':
    raise SystemExit('FAILED: plain script')
missing = w / 'missing'
missing.mkdir()
(missing / 'deploy.build.n').write_text(SCRIPT)
r = run([T / 'nscript', 'run', missing / 'deploy.build.n', '--no-cache'], cwd=missing, ok=False)
if 'no script kind declares the extension .build.n' not in r.stderr:
    raise SystemExit('FAILED: undeclared kind message\n' + r.stderr)
print('PASS: plain scripts use the default definition; an undeclared kind is reported', flush=True)
shutil.rmtree(w, ignore_errors=True)
print('PASS: library-declared script kinds', flush=True)
