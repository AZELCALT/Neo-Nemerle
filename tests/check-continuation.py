#!/usr/bin/env python3
"""The continuation section (doc/CONTINUATION.md), stage by stage.

    check-continuation.py --toolchain DIR --references REFS [--stage E1]

E1: an output with a grammar carries a .nemir section with the grammar image and marks; it still runs and verifies
    when signed; -no-continuation-section writes none.
E2: a program with only `space Demo { ... }` compiles with -continue:<host binary> against the host's
    stored grammar (no grammar in its source, no nested grammar compile) and prints the same result.
E3: a program that redefines the stored grammar gets an exact mark diff (changed / added / removed declarations);
    layout-only edits are clean. The grammar still compiles in full.
E5: a host library's macros are indexed in its section (name, class, source span) and a program that continues
    from it (a plain -r reference) uses them without -m.
E6: a host macro that expands to an internal helper of its module works in a continued program (type subsection +
    IgnoresAccessChecksTo); internals of modules without macros stay hidden.
S:  a script that depends on such a host library (DependsOn) continues from it by default: it uses the host's
    grammar in `space`, its macros and the internal helper a macro expands to, with no grammar compile of its own.
E4: redefining the stored 120-rule grammar with only alternative edits compiles a patch grammar of just those
    alternatives over the stored image; other edits fall back to the full compile; results are identical.
P:  spaces are top-level logical files reached through scopes and dials: a host's scope bindings travel in the section
    (scope subsection), a plugin script with no grammar (or no space at all) uses them and the host's grammar, a plain
    space looks across the visible grammars, and a space inside a function or used as an expression is rejected."""
import argparse, pathlib, shutil, subprocess, tempfile, time

p = argparse.ArgumentParser()
p.add_argument('--toolchain', type=pathlib.Path, required=True)
p.add_argument('--references', type=pathlib.Path, required=True)
p.add_argument('--stage', default='E6',
                help='run the stages up to and including this one')
a = p.parse_args()
here = pathlib.Path(__file__).resolve().parent
repo = here.parent
T = a.toolchain.resolve()
R = a.references.resolve()
w = pathlib.Path(tempfile.mkdtemp(prefix='nemerle-continuation-'))
print('Continuation checks:', w, flush=True)
key = repo / 'misc/keys/Nemerle.snk'


def grammar_program(rules):
    """A grammar with `rules` alternatives of one extensible rule, and a top-level space that prints the last one."""
    alternatives = '\n'.join('      | A%d = "k%d" { map PExpr = <[ %d ]>; }' % (i, i, i) for i in range(rules))
    return '''grammar Demo
{
  using Nemerle.Compiler.Parsetree;
  syntax module Query
  {
    using Nitra.Core;
    [StartRule] syntax Input = Item { map PExpr = <[ System.Console.WriteLine($(this.Item.GetAst())) ]>; }
    syntax Item
    {
      map PExpr;
%s
    }
  }
}
space Demo { k%d }
''' % (alternatives, rules - 1)


RESOLVER = """using System;
using Nemerle.Compiler.NitraDialectServices;
using Nemerle.Compiler.Parsetree;

public class Resolver : INitraDialectResolver
{
  public ResolveType(name : string, _context : NitraDialectContext) : NitraDialectType
  {
    if (name == "number") NitraDialectType(name, "int") else null
  }
  public Resolve(request : NitraDialectRequest) : NitraDialectResolution
  {
    match (request.Name)
    {
      | "twice" =>
        def answer = NitraDialectResolution();
        answer.Signatures.Add(NitraDialectSignature("twice", NitraDialectType("number"), array[NitraDialectType("number")]));
        answer.Lower = Func(r => if (r.IsCall) <[ $(r.Arguments[0]) * 2 ]> else <[ fun (x : int) { x * 2 } ]>);
        answer
      | "both" =>
        // two forms: both(n) and both()
        def answer = NitraDialectResolution();
        answer.Signatures.Add(NitraDialectSignature("both", NitraDialectType("number"), array[NitraDialectType("number")]));
        answer.Signatures.Add(NitraDialectSignature("both", NitraDialectType("number"), array[]));
        answer.Lower = Func(r => if (r.Arguments.Length == 1) <[ $(r.Arguments[0]) + 1 ]> else <[ 100 ]>);
        answer
      | "shared" =>
        def answer = NitraDialectResolution();
        answer.Signatures.Add(NitraDialectSignature("shared", NitraDialectType("number"), array[]));
        answer.Lower = Func(r => r.Context.Scope("A").Read("value"));
        answer
      | _ => null
    }
  }
}

public Create() : INitraDialectResolver { Resolver() }
"""

SPACE_HOST = """scope A;
grammar G
{
  using Nemerle.Compiler.NitraDialectServices;
  using Nemerle.Compiler.Parsetree;
  syntax module M
  {
    using Nitra.Core;
    [StartRule] syntax Start = "go"
    {
      map PExpr = {
        def c = NitraDialectContext.Current;
        when (c.Space.Resolver == null) c.RegisterResolver(res.Create());
        <[ () ]>
      };
    }
  }
}

scope.A.registery("value", type("number"));
scope.A.value = 21;
space G [A] { go }
"""

# a host application: it sets its scope, runs plugin scripts in its own process, then reads what they wrote
APP = SPACE_HOST + """
// a slot can hold anything, a dial's member too: plugins get it as a function value from the storage
scope.A.registery("f", dial:.app.G::twice);
// a member with two forms is held as a Content of both: a plugin's call runs the form that fits
scope.A.registery("g", dial:.app.G::both);
def run(file : string) : void
{
  def host = Nemerle.Scripting.host.ScriptHost();
  def definition = Nemerle.Scripting.contracts.ScriptDefinition();
  definition.TargetReferenceDirectory = System.Environment.GetCommandLineArgs()[1];
  definition.References.Add(System.Reflection.Assembly.GetEntryAssembly().Location);
  definition.References.Add(System.IO.Path.Combine(System.AppContext.BaseDirectory, "res.dll"));
  def compiled = host.Compile(Nemerle.Scripting.contracts.ScriptSource(System.IO.File.ReadAllText(file), file), definition);
  if (!compiled.Success) foreach (d in compiled.Diagnostics) System.Console.WriteLine("error " + d.Message)
  else
  {
    def result = host.Evaluate(compiled.Script, Nemerle.Scripting.contracts.ScriptInputs());
    when (result.Error != null) System.Console.WriteLine("error " + result.Error.ToString());
  }
}
def args = System.Environment.GetCommandLineArgs();
for (mutable i = 2; i < args.Length; i++) run(args[i]);
System.Console.WriteLine("host " + scope.A.value.ToString());
"""


def run(command, **kw):
    r = subprocess.run([str(c) for c in command], capture_output=True, text=True, **kw)
    if r.returncode != 0:
        raise SystemExit('FAILED: %s\n%s%s' % (' '.join(map(str, command)), r.stdout, r.stderr))
    return r


def compile_program(name, rules, extra):
    root = w / name
    root.mkdir()
    source = root / 'demo.n'
    source.write_text(grammar_program(rules))
    started = time.time()
    run([T / 'ncc', source, '-source-root:' + str(root), '-out:' + str(root / 'demo.exe'), '-no-color', *extra])
    elapsed = time.time() - started
    shutil.copy2(T / 'ncc.runtimeconfig.json', root / 'demo.runtimeconfig.json')
    output = run(['dotnet', root / 'demo.exe'], cwd=root).stdout.strip()
    if output != str(rules - 1):
        raise SystemExit('FAILED: %s printed %r, expected %d' % (name, output, rules - 1))
    return root / 'demo.exe', elapsed


# the C# reader of the section
version, folder = subprocess.check_output(['dotnet', '--list-sdks'], text=True).splitlines()[-1].split(' ', 1)
csc = pathlib.Path(folder.strip('[]')) / version / 'Roslyn/bincore/csc.dll'
rsp = w / 'checks.rsp'
rsp.write_text('\n'.join(['-nologo', '-nostdlib+', '-target:exe', '-out:"' + str(w / 'Checks.dll') + '"']
    + ['-r:"' + str(f) + '"' for f in sorted(R.glob('*.dll'))]
    + ['-r:"' + str(T / n) + '"' for n in ('Nemerle.dll', 'Nemerle.Compiler.dll', 'Nemerle.Platform.dll')]
    + ['"' + str(here / 'ContinuationChecks.cs') + '"']))
run(['dotnet', csc, '@' + str(rsp)])
for f in T.glob('*.dll'):
    shutil.copy2(f, w / f.name)
shutil.copy2(T / 'ncc.runtimeconfig.json', w / 'Checks.runtimeconfig.json')


def reader(*args):
    return run(['dotnet', w / 'Checks.dll', *args], cwd=w).stdout.strip()


plain, t_plain = compile_program('plain', 10, ['-no-continuation-section'])
print(reader(plain, T), flush=True)
unsigned, t_cont = compile_program('unsigned', 10, [])
print(reader(unsigned, T, 'Demo', unsigned.parent / 'demo.n', '10'), flush=True)
signed, _ = compile_program('signed', 10, ['-keyfile:' + str(key)])
print(reader(signed, T, 'Demo'), flush=True)
verify = subprocess.run(['sn', '-vf', str(signed)], capture_output=True, text=True)
if 'is strongnamed' not in verify.stdout:
    raise SystemExit('FAILED: signed output with a continuation section does not verify\n' + verify.stdout + verify.stderr)
print('PASS: signed output with a continuation section verifies (sn -vf)', flush=True)
print('E1 times (10 rules): without section %.2fs, with section %.2fs' % (t_plain, t_cont), flush=True)
print('PASS: E1 continuation section written, signed, readable', flush=True)


def space_program(name, expression, expected, host):
    """A program that uses the host's grammar Demo in a space block but defines no grammar itself."""
    root = w / name
    root.mkdir()
    source = root / 'use.n'
    source.write_text('space Demo { %s }\n' % expression)
    started = time.time()
    run([T / 'ncc', source, '-source-root:' + str(root), '-out:' + str(root / 'use.exe'), '-no-color',
         '-continue:' + str(host)])
    elapsed = time.time() - started
    shutil.copy2(T / 'ncc.runtimeconfig.json', root / 'use.runtimeconfig.json')
    output = run(['dotnet', root / 'use.exe'], cwd=root).stdout.strip()
    if output != str(expected):
        raise SystemExit('FAILED: %s printed %r, expected %s' % (name, output, expected))
    return elapsed


if a.stage >= 'E2':
    t10 = space_program('use10', 'k3', 3, unsigned)
    host120, t_fresh120 = compile_program('host120', 120, [])
    t120 = space_program('use120', 'k117', 117, host120)
    t_plain120 = min(compile_program('fresh120-%d' % i, 120, ['-no-continuation-section'])[1] for i in range(2))
    print('E2 times: 10-rule grammar fresh %.2fs, continued %.2fs; 120-rule grammar fresh %.2fs, continued %.2fs'
          % (t_cont, t10, t_plain120, t120), flush=True)
    print('PASS: E2 programs continue from a stored grammar without compiling it', flush=True)


def diff_of(name, text, expected_output):
    """Compile an edited copy of the 10-rule grammar program against the stored one; return the reported diff."""
    import os, re
    root = w / name
    root.mkdir()
    source = root / 'demo.n'
    source.write_text(text)
    env = dict(os.environ, NEMERLE_CONTINUATION_DIFF='1')
    r = subprocess.run([str(T / 'ncc'), str(source), '-source-root:' + str(root), '-out:' + str(root / 'demo.exe'),
                        '-no-color', '-continue:' + str(unsigned)], capture_output=True, text=True, env=env)
    if r.returncode != 0:
        raise SystemExit('FAILED: %s\n%s%s' % (name, r.stdout, r.stderr))
    shutil.copy2(T / 'ncc.runtimeconfig.json', root / 'demo.runtimeconfig.json')
    output = run(['dotnet', root / 'demo.exe'], cwd=root).stdout.strip()
    if output != expected_output:
        raise SystemExit('FAILED: %s printed %r, expected %r' % (name, output, expected_output))
    line = next((l for l in (r.stdout + r.stderr).splitlines() if l.startswith('continuation diff Demo:')), None)
    if line is None:
        raise SystemExit('FAILED: %s reported no diff\n%s%s' % (name, r.stdout, r.stderr))
    parts = dict(re.findall(r'(\w+)=\[([^\]]*)\]', line))
    return {k: [x for x in v.split(',') if x] for k, v in parts.items()}, line


if a.stage >= 'E3':
    base = grammar_program(10)
    cases = [
        ('body', base.replace('<[ 3 ]>', '<[ 33 ]>').replace('space Demo { k9 }', 'space Demo { k3 }'), '33',
         lambda d: d['added'] == [] and d['removed'] == [] and d['changed'] and all('A3' in c or c.startswith('retained') for c in d['changed'])),
        ('added', base.replace('      | A9 = "k9" { map PExpr = <[ 9 ]>; }', '      | A9 = "k9" { map PExpr = <[ 9 ]>; }\n      | A10 = "k10" { map PExpr = <[ 10 ]>; }').replace('space Demo { k9 }', 'space Demo { k10 }'), '10',
         lambda d: d['added'] == ['alternative:A10'] and d['removed'] == []),
        ('renamed', base.replace('| A3 = ', '| B3 = '), '9',
         lambda d: d['added'] == ['alternative:B3'] and d['removed'] == ['alternative:A3'] and d['changed'] == []),
        ('layout', base.replace('\n      | A5', '\n\n         |   A5').replace('map PExpr = <[ 7 ]>', 'map   PExpr =   <[ 7 ]>'), '9',
         lambda d: d['added'] == [] and d['removed'] == [] and d['changed'] == []),
    ]
    for name, text, expected, ok in cases:
        d, line = diff_of('edit-' + name, text, expected)
        print('  %-8s %s' % (name, line.split(': ', 1)[1]), flush=True)
        if not ok(d):
            raise SystemExit('FAILED: E3 %s diff is not exact: %s' % (name, line))
    print('PASS: E3 mark diff is exact for body, added, renamed and layout-only edits', flush=True)

if a.stage >= 'E5':
    root = w / 'macrohost'
    root.mkdir()
    (root / 'host.n').write_text('using Nemerle.Compiler;\n\nmacro twice(e)\n{\n  <[ $e * 2 ]>\n}\n\npublic Hello() : string { "host" }\n')
    run([T / 'ncc', root / 'host.n', '-source-root:' + str(root), '-target:library', '-out:' + str(root / 'host.dll'), '-no-color',
         '-r:' + str(T / 'Nemerle.Compiler.dll')])
    print(reader(root / 'host.dll', T, '--macros', root / 'host.n'), flush=True)
    user = w / 'macrouser'
    user.mkdir()
    (user / 'use.n').write_text('using host;\n\nmodule Program\n{\n  Main() : void { System.Console.WriteLine(twice(21)); }\n}\n')
    run([T / 'ncc', user / 'use.n', '-source-root:' + str(user), '-out:' + str(user / 'use.exe'), '-no-color',
         '-r:' + str(root / 'host.dll')])
    shutil.copy2(T / 'ncc.runtimeconfig.json', user / 'use.runtimeconfig.json')
    shutil.copy2(root / 'host.dll', user / 'host.dll')
    output = run(['dotnet', user / 'use.exe'], cwd=user).stdout.strip()
    if output != '42':
        raise SystemExit('FAILED: E5 program printed %r, expected 42' % output)
    print('PASS: E5 a continued program uses the host\'s macro (twice(21) = 42) without -m', flush=True)

if a.stage >= 'E6':
    root = w / 'scopehost'
    root.mkdir()
    (root / 'host.n').write_text('using Nemerle.Compiler;\n\nmacro tripled(e)\n{\n  <[ host.Helper($e) ]>\n}\n\ninternal Helper(x : int) : int { x * 3 }\n')
    (root / 'other.n').write_text('internal Secret() : int { 7 }\n')
    run([T / 'ncc', root / 'host.n', root / 'other.n', '-source-root:' + str(root), '-target:library', '-out:' + str(root / 'host.dll'),
         '-no-color', '-r:' + str(T / 'Nemerle.Compiler.dll')])
    print(reader(root / 'host.dll', T, '--macros', root / 'host.n'), flush=True)
    user = w / 'scopeuser'
    user.mkdir()
    (user / 'use.n').write_text('using host;\n\nmodule Program\n{\n  Main() : void { System.Console.WriteLine(tripled(14)); }\n}\n')
    run([T / 'ncc', user / 'use.n', '-source-root:' + str(user), '-out:' + str(user / 'use.exe'), '-no-color',
         '-r:' + str(root / 'host.dll')])
    shutil.copy2(T / 'ncc.runtimeconfig.json', user / 'use.runtimeconfig.json')
    shutil.copy2(root / 'host.dll', user / 'host.dll')
    output = run(['dotnet', user / 'use.exe'], cwd=user).stdout.strip()
    if output != '42':
        raise SystemExit('FAILED: E6 program printed %r, expected 42' % output)
    hidden = w / 'scopehidden'
    hidden.mkdir()
    (hidden / 'peek.n').write_text('module Program\n{\n  Main() : void { System.Console.WriteLine(other.Secret()); }\n}\n')
    r = subprocess.run([str(T / 'ncc'), str(hidden / 'peek.n'), '-source-root:' + str(hidden), '-out:' + str(hidden / 'peek.exe'),
                        '-no-color', '-r:' + str(root / 'host.dll')],
                       capture_output=True, text=True)
    if r.returncode == 0 or 'Secret' not in r.stdout + r.stderr:
        raise SystemExit('FAILED: E6 an internal of a module without macros must stay hidden\n' + r.stdout + r.stderr)
    print('PASS: E6 a host macro expanding to an internal helper works in a continued program (tripled(14) = 42); '
          'internals of modules without macros stay hidden', flush=True)

if a.stage in ('E4', 'E6'):
    import os
    base = grammar_program(120)
    def edited(name, text, expected):
        root = w / ('e4-' + name)
        root.mkdir()
        (root / 'demo.n').write_text(text)
        env = dict(os.environ, NEMERLE_CONTINUATION_DIFF='1')
        started = time.time()
        r = subprocess.run([str(T / 'ncc'), str(root / 'demo.n'), '-source-root:' + str(root), '-out:' + str(root / 'demo.exe'),
                            '-no-color', '-continue:' + str(host120)], capture_output=True, text=True, env=env)
        elapsed = time.time() - started
        if r.returncode != 0:
            raise SystemExit('FAILED: E4 %s\n%s%s' % (name, r.stdout, r.stderr))
        shutil.copy2(T / 'ncc.runtimeconfig.json', root / 'demo.runtimeconfig.json')
        output = run(['dotnet', root / 'demo.exe'], cwd=root).stdout.strip()
        if output != expected:
            raise SystemExit('FAILED: E4 %s printed %r, expected %r' % (name, output, expected))
        how = next((l.split(' ')[1] for l in r.stderr.splitlines() if l.startswith('continuation ') and not l.startswith('continuation diff')), '?')
        return how, elapsed
    cases = [
        ('body', base.replace('<[ 3 ]>', '<[ 33 ]>').replace('space Demo { k119 }', 'space Demo { k3 }'), '33', 'patch'),
        ('added', base.replace('      | A119 = "k119" { map PExpr = <[ 119 ]>; }', '      | A119 = "k119" { map PExpr = <[ 119 ]>; }\n      | A120 = "k120" { map PExpr = <[ 120 ]>; }').replace('space Demo { k119 }', 'space Demo { k120 }'), '120', 'patch'),
        ('renamed', base.replace('| A3 = ', '| B3 = ').replace('space Demo { k119 }', 'space Demo { k3 }'), '3', 'patch'),
        ('unchanged', base.replace('space Demo { k119 }', 'space Demo { k7 }'), '7', 'reuse'),
        ('new-rule', base.replace('    [StartRule] syntax Input', '    regex Digits = [\'0\'..\'9\']+;\n    [StartRule] syntax Input'), '119', 'fallback'),
    ]
    for name, text, expected, way in cases:
        how, elapsed = edited(name, text, expected)
        print('  %-9s %-8s %.2fs (fresh 120-rule compile %.2fs)' % (name, how, elapsed, t_plain120), flush=True)
        if how != way:
            raise SystemExit('FAILED: E4 %s took the %s path, expected %s' % (name, how, way))
    print('PASS: E4 alternative edits compile as patches over the stored grammar; other edits fall back; results identical', flush=True)

if a.stage == 'E6':
    lib = w / 'scriptlib'
    lib.mkdir()
    (lib / 'host.n').write_text('''using Nemerle.Compiler;

grammar Demo
{
  using Nemerle.Compiler.Parsetree;
  syntax module Query
  {
    using Nitra.Core;
    [StartRule] syntax Input = Item { map PExpr = <[ System.Console.WriteLine($(this.Item.GetAst())) ]>; }
    syntax Item
    {
      map PExpr;
      | A0 = "k0" { map PExpr = <[ 40 ]>; }
      | A1 = "k1" { map PExpr = <[ 2 ]>; }
    }
  }
}

macro twice(e)
{
  <[ $e * 2 ]>
}

macro tripled(e)
{
  <[ host.Helper($e) ]>
}

internal Helper(x : int) : int { x * 3 }
''')
    run([T / 'ncc', lib / 'host.n', '-source-root:' + str(lib), '-target:library', '-out:' + str(lib / 'host.dll'), '-no-color',
         '-r:' + str(T / 'Nemerle.Compiler.dll')])
    script = w / 'script'
    script.mkdir()
    shutil.copy2(lib / 'host.dll', script / 'host.dll')
    (script / 'use.n').write_text('[assembly: DependsOn("host.dll")]\nusing host;\nspace Demo { k0 }\n'
                                  'System.Console.WriteLine(twice(21));\nSystem.Console.WriteLine(tripled(14));\n')
    started = time.time()
    output = run([T / 'nscript', 'run', script / 'use.n', '--no-cache'], cwd=script).stdout.split()
    elapsed = time.time() - started
    if output != ['40', '42', '42']:
        raise SystemExit('FAILED: script continuation printed %r' % output)
    print('PASS: S a script depending on the host library uses its grammar, macros and internal helper (%.2fs)' % elapsed, flush=True)
    # the same through ncc: a plain reference is continued from
    prog = w / 'refprogram'
    prog.mkdir()
    (prog / 'use.n').write_text('using host;\n\nspace Demo { k1 }\nSystem.Console.WriteLine(twice(20));\n')
    run([T / 'ncc', prog / 'use.n', '-source-root:' + str(prog), '-out:' + str(prog / 'use.exe'), '-no-color', '-r:' + str(lib / 'host.dll')])
    shutil.copy2(T / 'ncc.runtimeconfig.json', prog / 'use.runtimeconfig.json')
    shutil.copy2(lib / 'host.dll', prog / 'host.dll')
    if run(['dotnet', prog / 'use.exe'], cwd=prog).stdout.split() != ['2', '40']:
        raise SystemExit('FAILED: an ncc program referencing the host library does not continue from it')
    print('PASS: S an ncc program that references the host library (-r) uses its grammar and macro', flush=True)
    # a compiled script with a grammar carries the section, so it can be continued from in turn
    own = w / 'scriptgrammar'
    own.mkdir()
    (own / 'g.n').write_text(grammar_program(3))
    run([T / 'nscript', 'compile', own / 'g.n', own / 'g.dll', '--no-cache'], cwd=own)
    if reader(own / 'g.dll', T, 'Demo').find('PASS') < 0:
        raise SystemExit('FAILED: nscript compile output has no continuation section')
    print('PASS: S nscript compile of a script with a grammar writes the continuation section', flush=True)

if a.stage == 'E6':
    # spaces are top-level logical files; scopes (shared memory) and dials (calls) connect them to the program, and the
    # scopes travel in the section next to the grammars. A resolver lives in its own library: the grammar's nested
    # compile sees only referenced binaries.
    res = w / 'res'
    res.mkdir()
    (res / 'res.n').write_text(RESOLVER)
    run([T / 'ncc', res / 'res.n', '-source-root:' + str(res), '-target:library', '-out:' + str(res / 'res.dll'), '-no-color',
         '-r:' + str(T / 'Nemerle.Compiler.dll')])
    shost = w / 'app'
    shost.mkdir()
    for f in T.iterdir():
        if f.is_file() and f.suffix in {'.dll', '.exe', '.json', '.nitrametadata'}:
            shutil.copy2(f, shost / f.name)
    shutil.copy2(res / 'res.dll', shost / 'res.dll')
    (shost / 'app.n').write_text(APP)
    run([T / 'ncc', shost / 'app.n', '-source-root:' + str(shost), '-out:' + str(shost / 'app.exe'), '-no-color',
         '-r:' + str(T / 'Nemerle.Compiler.dll'), '-r:' + str(T / 'Nemerle.Scripting.dll'), '-r:' + str(shost / 'res.dll')])
    shutil.copy2(T / 'ncc.runtimeconfig.json', shost / 'app.runtimeconfig.json')
    plugins = [
        ('reader.n', 'using app;\nSystem.Console.WriteLine(scope.A.value);\n'),
        ('user.n', 'using app;\nspace G [A] { go }\nSystem.Console.WriteLine(dial:.user.G::twice(scope.A.value));\n'
                   'System.Console.WriteLine(dial:.user.G::shared());\n'),
        ('named.n', 'using app;\nspace G as Named [A] { go }\nSystem.Console.WriteLine(dial:.named.Named::twice(5));\n'),
        ('caller.n', 'using app;\nSystem.Console.WriteLine(dial:.app.G::twice(2));\nSystem.Console.WriteLine(dial:.app.G::shared());\n'),
        ('function.n', 'using app;\nSystem.Console.WriteLine(scope.A.f(8));\n'),
        ('overloads.n', 'using app;\nSystem.Console.WriteLine(scope.A.g(1));\nSystem.Console.WriteLine(scope.A.g());\n'),
        ('writer.n', 'using app;\nscope.A.value = scope.A.value + 29;\n'),
    ]
    for name, text in plugins:
        (shost / name).write_text(text)
    output = run(['dotnet', shost / 'app.exe', T / 'references', *[shost / n for n, _ in plugins]], cwd=shost).stdout.split('\n')
    output = [l for l in output if l.strip()]
    expected = ['21', '42', '21', '10', '4', '21', '16', '2', '100', 'host 50']
    if output != expected:
        raise SystemExit('FAILED: the host application and its plugins printed %r, expected %r' % (output, expected))
    print('PASS: P plugins run in the host application read its scope storage (a plugin with no space as well), use '
          'its grammar (space G [A] / as Name), dial into their own spaces and into the host\'s, call a dial member '
          'the host stored in a slot, and write the storage back to the host', flush=True)
    # a plugin with its own copy of Nemerle.dll (an isolated load context) shares the process's scope storage
    copies = w / 'copies'; (copies / 'plugin').mkdir(parents=True)
    (copies / 'plugin/plug.n').write_text(
        'public Run() : string\n{\n  def s = Nemerle.Scopes.Scope.Of("app.A");\n  def v = s.Read.[int]("value");\n'
        '  s.Set("value", v + 29);\n  s.Read.[string]("box") + " " + v.ToString() + " " + typeof(Nemerle.Scopes.Scope).Assembly.Location\n}\n')
    run([T / 'ncc', copies / 'plugin/plug.n', '-source-root:' + str(copies / 'plugin'), '-target:library',
         '-out:' + str(copies / 'plugin/plug.dll'), '-no-color'])
    shutil.copy2(T / 'Nemerle.dll', copies / 'plugin/Nemerle.dll')
    (copies / 'host.n').write_text('''using System.IO;
using System.Reflection;
using System.Runtime.Loader;

class PluginContext : AssemblyLoadContext
{
  dir : string;
  public this(dir : string) { base("plugin", true); this.dir = dir }
  protected override Load(name : AssemblyName) : Assembly
  {
    def path = Path.Combine(dir, name.Name + ".dll");
    if (File.Exists(path)) LoadFromAssemblyPath(path) else null
  }
}

def s = Nemerle.Scopes.Scope.Of("app.A");
s.Set("value", 21);
s.Set("box", Nemerle.Scopes.Content.Of("boxed"));
def dir = Path.Combine(System.AppContext.BaseDirectory, "plugin");
def plugin = PluginContext(dir).LoadFromAssemblyPath(Path.Combine(dir, "plug.dll"));
mutable run : MethodInfo = null;
foreach (t in plugin.GetTypes()) when (run == null) run = t.GetMethod("Run");
def said = run.Invoke(null, null) :> string;
def own = said.EndsWith(Path.Combine("plugin", "Nemerle.dll"));
System.Console.WriteLine(said.Substring(0, said.LastIndexOf(' ')) + (if (own) " (its own Nemerle.dll)" else " (the host's Nemerle.dll)"));
System.Console.WriteLine("host " + s.Read.[int]("value").ToString());
''')
    run([T / 'ncc', copies / 'host.n', '-source-root:' + str(copies), '-out:' + str(copies / 'host.exe'), '-no-color'])
    shutil.copy2(T / 'Nemerle.dll', copies / 'Nemerle.dll')
    shutil.copy2(T / 'ncc.runtimeconfig.json', copies / 'host.runtimeconfig.json')
    output = [l for l in run(['dotnet', copies / 'host.exe'], cwd=copies).stdout.split('\n') if l.strip()]
    if output != ['boxed 21 (its own Nemerle.dll)', 'host 50']:
        raise SystemExit('FAILED: a plugin with its own Nemerle.dll printed %r, expected it to share the scope storage' % output)
    print('PASS: a plugin loaded with its own copy of Nemerle.dll shares the process\'s scope storage (reads 21 and a '
          'Content, writes 50 back)', flush=True)
    # `scope A;' creates the scope where it is written; every use is access to that one: a use before the declaration
    # has run fails (no empty copy is made), and a scope nobody declared cannot be reached
    declared = w / 'declared'; declared.mkdir()
    (declared / 'main.n').write_text(
        'try { System.Console.WriteLine(scope.S.n) } catch { | e is System.InvalidOperationException => System.Console.WriteLine(e.Message) }\n'
        'scope S;\nscope.S.registery("n", type("int"));\nscope.S.n = 5;\nSystem.Console.WriteLine(scope.S.n);\n'
        'try { _ = Nemerle.Scopes.Scope.Access("nowhere.A") } catch { | e is System.InvalidOperationException => System.Console.WriteLine(e.Message) }\n')
    run([T / 'ncc', declared / 'main.n', '-source-root:' + str(declared), '-out:' + str(declared / 'main.exe'), '-launcher-', '-no-color'])
    shutil.copy2(T / 'Nemerle.dll', declared / 'Nemerle.dll')
    shutil.copy2(T / 'ncc.runtimeconfig.json', declared / 'main.runtimeconfig.json')
    output = [l for l in run(['dotnet', declared / 'main.exe'], cwd=declared).stdout.split('\n') if l.strip()]
    if not (len(output) == 3 and output[0].startswith('scope main.S is not set up in this process') and output[1] == '5'
            and output[2].startswith('scope nowhere.A is not set up in this process')):
        raise SystemExit('FAILED: scope declaration and access printed %r' % output)
    print('PASS: `scope A;` creates the scope where it is written, every use is access to it (a use before it, or of a '
          'scope nobody declared, fails instead of making an empty copy)', flush=True)
    # a scope's slot is one value, the same object to every reader. To .NET a type is a copy of an assembly and a name,
    # so a type compiled twice is two types; a compilation that continues from the binary declaring the scope makes no
    # copy of the types its slots reach: the same file module is the binary's module, the same type under another name
    # an alias of the binary's type (the binary records them, with their code, in its continuation section). A copy
    # compiled apart is another type, and reading or writing the slot with it says so.
    shapes = ('public class Point\n{\n  public mutable X : int;\n  public Y : int;\n  public this(x : int, y : int) { X = x; Y = y }\n'
              '  public override ToString() : string { $"($X, $Y)" }\n}\n'
              'public variant Shape\n{\n  | Dot { at : Point }\n  | Line { from : Point; to : Point }\n}\n'
              'public class Hidden { public N : int; public this(n : int) { N = n } }\n')
    ident = w / 'identity'
    for d in ('same', 'renamed', 'apart', 'other', 'util'):
        (ident / d).mkdir(parents=True)
    (ident / 'shapes.n').write_text(shapes)
    (ident / 'util.n').write_text('public Twice(x : int) : int { x * 2 }\n')
    (ident / 'main.n').write_text(
        'using System.IO;\nusing System.Reflection;\n'
        'scope A;\nscope.A.registery("p", type("shapes.Point"));\nscope.A.registery("s", type("shapes.Shape"));\n'
        'scope.A.p = shapes.Point(3, 4);\n'
        'scope.A.s = shapes.Shape.Line(shapes.Point(1, 2), shapes.Point(5, 6));\n'
        'System.Console.WriteLine(util.Twice(1));\n'
        'def call(dir : string) : string\n{\n'
        '  def plugin = Assembly.LoadFrom(Path.Combine(System.AppContext.BaseDirectory, dir, dir + ".dll"));\n'
        '  mutable run : MethodInfo = null;\n'
        '  foreach (t in plugin.GetTypes()) when (run == null) run = t.GetMethod("Run");\n'
        '  run.Invoke(null, null) :> string\n}\n'
        'def p = scope.A.p;\n'
        'foreach (dir in ["same", "renamed", "apart"]) System.Console.WriteLine(call(dir));\n'
        'System.Console.WriteLine($"$(scope.A.p) $(object.ReferenceEquals(p, scope.A.p))");\n')
    run([T / 'ncc', ident / 'main.n', ident / 'shapes.n', ident / 'util.n', '-source-root:' + str(ident), '-out:' + str(ident / 'main.exe'),
         '-launcher-', '-no-color'])
    # the same file, compiled against the host: the host's module, so the plugin works on the host's object
    (ident / 'same/shapes.n').write_text(shapes)
    (ident / 'same/plug.n').write_text(
        'public Run() : string\n{\n'
        '  def a = Nemerle.Scopes.Scope.Access("main.A");\n'
        '  def p = a.Read.[shapes.Point]("p");\n'
        '  p.X = 7;\n'
        '  def line = match (a.Read.[shapes.Shape]("s")) { | shapes.Shape.Line(f, t) => $"line $f $t" | _ => "?" };\n'
        '  $"same: $p $line $(typeof(shapes.Point).Assembly.GetName().Name)"\n}\n')
    # the same type under another name: that type
    (ident / 'renamed/mine.n').write_text(shapes.split('public variant')[0].replace('Point', 'Pt'))
    (ident / 'renamed/plug.n').write_text(
        'public Run() : string\n{\n'
        '  def p = Nemerle.Scopes.Scope.Access("main.A").Read.[mine.Pt]("p");\n'
        '  $"renamed: $p $(typeof(mine.Pt).Assembly.GetName().Name)"\n}\n')
    # the same code compiled apart (not against the host): another .NET type, which the read reports
    (ident / 'apart/shapes.n').write_text(shapes)
    (ident / 'apart/plug.n').write_text(
        'public Run() : string\n{\n'
        '  try { _ = Nemerle.Scopes.Scope.Access("main.A").Read.[shapes.Point]("p"); "apart: read" }\n'
        '  catch { | e is System.InvalidCastException => "apart: " + (if (e.Message.Contains("compiled apart")) "compiled apart" else e.Message) }\n}\n')
    for d, extra in (('same', ['shapes.n']), ('renamed', ['mine.n']), ('apart', ['shapes.n'])):
        refs = [] if d == 'apart' else ['-r:' + str(ident / 'main.exe')]
        run([T / 'ncc', ident / d / 'plug.n', *[ident / d / f for f in extra], '-source-root:' + str(ident / d), '-target:library',
             '-out:' + str(ident / d / (d + '.dll')), '-no-color', *refs])
    shutil.copy2(T / 'Nemerle.dll', ident / 'Nemerle.dll')
    shutil.copy2(T / 'ncc.runtimeconfig.json', ident / 'main.runtimeconfig.json')
    output = [l for l in run(['dotnet', ident / 'main.exe'], cwd=ident).stdout.split('\n') if l.strip()]
    if output != ['2', 'same: (7, 4) line (1, 2) (5, 6) main', 'renamed: (7, 4) main', 'apart: compiled apart', '(7, 4) True']:
        raise SystemExit('FAILED: a scope slot\'s value through copies of its type printed %r' % output)
    # a file module the host has with other code, or one the host has no record of, is an error, not a second copy
    (ident / 'other/shapes.n').write_text(shapes.replace('  public Y : int;\n', '  public Y : int;\n  public Z : int;\n'))
    (ident / 'util/util.n').write_text('public Twice(x : int) : int { x * 2 }\n')
    for d, f, says in (('other', 'shapes.n', 'module shapes is in main.exe already, with other code'),
                       ('util', 'util.n', 'module util is in main.exe already')):
        r = subprocess.run([str(T / 'ncc'), str(ident / d / f), '-source-root:' + str(ident / d), '-target:library',
                            '-out:' + str(ident / d / (d + '.dll')), '-no-color', '-r:' + str(ident / 'main.exe')], capture_output=True, text=True)
        if r.returncode == 0 or says not in r.stdout + r.stderr:
            raise SystemExit('FAILED: a second copy of a host module (%s) is not reported\n%s%s' % (d, r.stdout, r.stderr))
    recorded = reader(ident / 'main.exe', T, '--identities')
    names = sorted(l.split(' : ')[0] for l in recorded.splitlines())
    # (a file's types are nested in its module's class: shapes+Point)
    if names != ['shapes+Point', 'shapes+Shape', 'shapes+Shape+Dot', 'shapes+Shape+Line']:
        raise SystemExit('FAILED: the host records the types its slots reach, and only those\n' + recorded)
    print('PASS: a scope slot\'s value is one object: a plugin with the same file module or the same type under another '
          'name uses the host\'s type (a write through it is the host\'s), a copy compiled apart is reported, and a '
          'second copy of a host module with other code (or no record) is an error', flush=True)
    # the host's copy: a script referencing a library the host has loaded shares its types
    common = w / 'common'; common.mkdir()
    (common / 'box.n').write_text('public class Box { public N : int; public this(n : int) { N = n } }\n')
    run([T / 'ncc', common / 'box.n', '-source-root:' + str(common), '-target:library', '-out:' + str(common / 'box.dll'), '-no-color'])
    for f in T.iterdir():
        if f.is_file() and f.suffix in {'.dll', '.json', '.nitrametadata'}:
            shutil.copy2(f, common / f.name)
    (common / 'use.n').write_text('def b = Nemerle.Scopes.Scope.Access("main.A").Read.[box.Box]("b");\n'
                                  'System.Console.WriteLine($"$(b.N) $(object.ReferenceEquals(b.GetType(), typeof(box.Box)))");\n')
    (common / 'main.n').write_text(
        'scope A;\nscope.A.registery("b", type("box.Box"));\nscope.A.b = box.Box(42);\n'
        'def host = Nemerle.Scripting.host.ScriptHost();\n'
        'def definition = Nemerle.Scripting.contracts.ScriptDefinition();\n'
        'definition.TargetReferenceDirectory = System.Environment.GetCommandLineArgs()[1];\n'
        'definition.References.Add(System.Reflection.Assembly.GetEntryAssembly().Location);\n'
        'definition.References.Add(System.IO.Path.Combine(System.AppContext.BaseDirectory, "box.dll"));\n'
        'def file = System.IO.Path.Combine(System.AppContext.BaseDirectory, "use.n");\n'
        'def compiled = host.Compile(Nemerle.Scripting.contracts.ScriptSource(System.IO.File.ReadAllText(file), file), definition);\n'
        'if (!compiled.Success) foreach (d in compiled.Diagnostics) System.Console.WriteLine("error " + d.Message)\n'
        'else\n{\n'
        '  def result = host.Evaluate(compiled.Script, Nemerle.Scripting.contracts.ScriptInputs());\n'
        '  when (result.Error != null) System.Console.WriteLine("error " + result.Error.ToString());\n}\n')
    run([T / 'ncc', common / 'main.n', '-source-root:' + str(common), '-out:' + str(common / 'main.exe'), '-no-color',
         '-r:' + str(T / 'Nemerle.Compiler.dll'), '-r:' + str(T / 'Nemerle.Scripting.dll'), '-r:' + str(common / 'box.dll')])
    shutil.copy2(T / 'ncc.runtimeconfig.json', common / 'main.runtimeconfig.json')
    output = [l for l in run(['dotnet', common / 'main.exe', T / 'references'], cwd=common).stdout.split('\n') if l.strip()]
    if output != ['42 True']:
        raise SystemExit('FAILED: a script referencing a library its host has loaded printed %r, expected the host\'s type' % output)
    print('PASS: a script referencing a library its host has loaded gets the host\'s copy (one type, nothing recorded)', flush=True)
    # a grammar that does not parse is reported at its own line and column, with the text there (it was the
    # file's 1:1 with an offset), also below other code in the file
    badgrammar = w / 'badgrammar'; badgrammar.mkdir()
    (badgrammar / 'bad.n').write_text('using System;\n\ngrammar Bad\n{\n  using Nemerle.Compiler.Parsetree;\n  syntax module M\n  {\n'
        '    using Nitra.Core;\n    [StartRule] syntax Start = Expr { map PExpr = <[ () ]>; }\n    syntax Expr\n    {\n      map PExpr;\n'
        '      | Sum = Expr "+" Expr precedence 10 { map PExpr = <[ 1 ]>; }\n    }\n  }\n}\n')
    r = subprocess.run([str(T / 'ncc'), str(badgrammar / 'bad.n'), '-source-root:' + str(badgrammar), '-target:library',
                        '-out:' + str(badgrammar / 'bad.dll'), '-no-color', '-r:' + str(T / 'Nemerle.Compiler.dll')], capture_output=True, text=True)
    if r.returncode == 0 or 'bad.n:13:40' not in r.stdout + r.stderr or "at `10 {" not in r.stdout + r.stderr:
        raise SystemExit('FAILED: a grammar error is located at its line and column\n' + r.stdout + r.stderr)
    print('PASS: a grammar that does not parse is reported at its line and column, with the text there', flush=True)
    plain = w / 'plainspace'
    plain.mkdir()
    for f in ('app.exe', 'res.dll'):
        shutil.copy2(shost / f, plain / f)
    (plain / 'prog.n').write_text('space { go }\nSystem.Console.WriteLine(dial:.prog::twice(4));\n')
    run([T / 'ncc', plain / 'prog.n', '-source-root:' + str(plain), '-out:' + str(plain / 'prog.exe'), '-no-color',
         '-r:' + str(plain / 'app.exe'), '-r:' + str(plain / 'res.dll')])
    shutil.copy2(T / 'ncc.runtimeconfig.json', plain / 'prog.runtimeconfig.json')
    if run(['dotnet', plain / 'prog.exe'], cwd=plain).stdout.split() != ['8']:
        raise SystemExit('FAILED: a plain space does not look across grammars')
    print('PASS: P a plain space with no grammar in its file selects the visible grammars (cross-grammar lookup)', flush=True)
    for name, text, where in (('in-function', 'f() : void { space G { go } }\n', 'bad.n:1:14:'),
                              ('expression', 'def x = space G { go };\n', 'bad.n:1:9:'),
                              ('operand', 'def y = 1 + space G { go };\n', 'bad.n:1:13:'),
                              ('argument', 'System.Console.WriteLine(space G { go });\n', 'bad.n:1:26:')):
        d = w / ('reject-' + name)
        d.mkdir()
        shutil.copy2(shost / 'app.exe', d / 'app.exe')
        (d / 'bad.n').write_text(text)
        r = subprocess.run([str(T / 'ncc'), str(d / 'bad.n'), '-source-root:' + str(d), '-out:' + str(d / 'bad.exe'),
                            '-no-color', '-r:' + str(d / 'app.exe')], capture_output=True, text=True)
        if r.returncode == 0 or 'top-level' not in r.stdout + r.stderr and 'top level' not in r.stdout + r.stderr:
            raise SystemExit('FAILED: a space %s is not rejected\n%s%s' % (name, r.stdout, r.stderr))
        if where not in r.stdout + r.stderr:
            raise SystemExit('FAILED: the error for a space %s is not at %s\n%s%s' % (name, where, r.stdout, r.stderr))
    print('PASS: P a space inside a function or as an expression is rejected at its line and column (spaces are top level)', flush=True)
shutil.rmtree(w, ignore_errors=True)
