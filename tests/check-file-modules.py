#!/usr/bin/env python3
"""Exercise source-module semantics through the real compiler and C# consumers."""
import argparse
import pathlib
import subprocess
import shutil
import json
import tempfile

parser = argparse.ArgumentParser()
parser.add_argument('compiler', type=pathlib.Path)
parser.add_argument('--runtime', choices=['mono', 'dotnet'], default='mono')
parser.add_argument('--target-references', type=pathlib.Path)
args = parser.parse_args()
compiler = args.compiler.resolve()
runtime = args.runtime
modern_references = []
if runtime == 'dotnet':
    if args.target_references is None: parser.error('--target-references is required for dotnet checks')
    sdk_version, sdk_root = subprocess.check_output(['dotnet', '--list-sdks'], text=True).splitlines()[-1].split(' ', 1)
    csharp = pathlib.Path(sdk_root.strip('[]')) / sdk_version / 'Roslyn/bincore/csc.dll'
    modern_references = ['-target-references:' + str(args.target_references.resolve())]
here = pathlib.Path(__file__).resolve().parent
work = pathlib.Path(tempfile.mkdtemp(prefix='nemerle-module-checks-'))
print('Module check artifacts:', work, flush=True)
# Macro assemblies carry runtime/compiler attributes; resolve them in consumers too.
for dependency in compiler.parent.glob('*.dll'):
    if dependency.name.startswith('Nemerle.') or dependency.name in ('Mono.Cecil.dll', 'System.CodeDom.dll'):
        shutil.copy2(dependency, work / dependency.name)

def run(command, success=True, diagnostic=None):
    result = subprocess.run([str(x) for x in command], cwd=work,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if (result.returncode == 0) != success:
        raise RuntimeError('Unexpected result: ' + ' '.join(map(str, command)) + '\n' + result.stdout)
    if diagnostic and diagnostic not in result.stdout:
        raise RuntimeError('Missing diagnostic ' + diagnostic + '\n' + result.stdout)
    if success and result.stdout.strip(): print(result.stdout.strip(), flush=True)
    return result

def compile_files(paths, output, success=True, diagnostic=None, extra=()):
    return run([runtime, compiler, *paths, '-source-root:' + str(work),
                '-target:library', '-out:' + str(work / output), '-no-color', *modern_references, *extra], success, diagnostic)

def compile_csharp(command):
    if runtime == 'mono': return run(command)
    output = next(str(arg)[5:] for arg in command if str(arg).startswith('-out:'))
    references = ['-r:' + str(path) for path in args.target_references.resolve().glob('*.dll')]
    result = run(['dotnet', csharp, '-nologo', '-nostdlib+', *references, *command[1:]])
    shutil.copy2(compiler.with_name('ncc.runtimeconfig.json'), pathlib.Path(output).with_suffix('.runtimeconfig.json'))
    return result

def source(name, text):
    path = work / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + '\n')
    return path

alpha = source('alpha.n', (here / 'file-modules/alpha.n').read_text())
beta = source('beta.n', (here / 'file-modules/beta.n').read_text())
for paths, filename in (([alpha, beta], 'files.dll'), ([beta, alpha], 'reverse.dll')):
    compile_files(paths, filename, extra=['-doc:' + str(work / (filename + '.xml'))])
    compile_csharp(['mcs', '-r:' + str(work / filename), '-out:' + str(work / 'Consumer.exe'),
         here / 'file-modules/Consumer.cs'])
    run([runtime, work / 'Consumer.exe'])

cases = [
    ('private-function', 'Run() : int { alpha.math.Secret() }', 'Secret'),
    ('private-mask', 'Run() : int { alpha.hidden.Value() }', 'hidden'),
    ('private-type', 'Run() : object { alpha.HiddenType() }', 'HiddenType'),
    ('import-leak', 'Run() : int { math.Twice(2) }', 'math'),
    ('namespace', 'namespace shared { public class Thing {} }', 'namespace declarations are not allowed'),
    ('partial', 'public partial class Thing {}', 'partial declarations are not allowed'),
    ('duplicate-mask', 'mask api {} mask api {}', 'partial'),
    # the file (bad.n) is a class: as in C# (CS0542) no member may have its name
    ('type-named-as-file', 'public class bad {}', 'names both the file module'),
    ('function-named-as-file', 'public bad() : int { 1 }', 'names both the file module'),
    ('mask-named-as-file', 'mask bad { }', 'names both the file module'),
]
for name, text, diagnostic in cases:
    bad = source('bad.n', text)
    compile_files([alpha, beta, bad], name + '.dll', False, diagnostic)
    print('PASS: rejected ' + name, flush=True)

compile_files([alpha, alpha], 'duplicate.dll', False, 'duplicate file module identity')
invalid = source('not-valid.n', 'class Thing {}')
compile_files([invalid], 'invalid.dll', False, 'path components must be identifiers')
conflict = source('alpha/child.n', 'class Thing {}')
compile_files([alpha, conflict], 'conflict.dll', False, 'conflicts with a directory')
outside = source('outside.n', 'class Thing {}')
compile_files([outside], 'outside.dll', False, 'outside the source root',
              extra=['-source-root:' + str(work / 'subroot')])

# Real foreign DLL imports and source-file precedence over a CLR namespace.
foreign = source('Foreign.cs', '''
namespace Foreign { public static class Api { public static int Value() { return 11; } } }
namespace alpha { public class ForeignOnly {} }
namespace folder { public static class ClrApi { public static int Value() { return 17; } } }
public class Node { public Node(string required) {} }
''')
compile_csharp(['mcs', '-target:library', '-out:' + str(work / 'Foreign.dll'), foreign])
interop = source('interop.n', '''
using Foreign;
using Short = alpha;
Run() : int { Api.Value() + Short.math.Twice(2) }
Make() : alpha.Node { alpha.Node() }
''')
compile_files([alpha, beta, interop], 'interop.dll', extra=['-r:' + str(work / 'Foreign.dll')])
host = source('Interop.cs', '''
class Host { static void Main() {
 if (interop.Run() != 15 || !(interop.Make() is alpha.Node)) throw new System.Exception();
 System.Console.WriteLine("PASS: CLR imports and module alias");
} }
''')
compile_csharp(['mcs', '-r:' + str(work / 'interop.dll'), '-out:' + str(work / 'InteropHost.exe'), host])
run([runtime, work / 'InteropHost.exe'])
selected = source('bad.n', 'Make() : alpha.ForeignOnly { null }')
compile_files([alpha, beta, selected], 'fallback.dll', False, 'ForeignOnly',
              extra=['-r:' + str(work / 'Foreign.dll')])

# Directory imports must not expose sibling source modules.
directory = source('folder/member.n', 'Value() : int { 5 }')
leak = source('bad.n', 'using folder; Run() : int { member.Value() }')
compile_files([directory, leak], 'directory-leak.dll', False, 'file module')
consumer = source('reader.n', 'using folder.member; Run() : int { Value() }')
compile_files([directory, consumer], 'directory-ok.dll')
# A module's own directory is not opened either: a sibling file is reached by its path.
sibling = source('folder/other.n', 'Run() : int { member.Value() }')
compile_files([directory, sibling], 'sibling-leak.dll', False, 'member')
sibling_ok = source('folder/other.n', 'using folder.member; Run() : int { Value() + folder.member.Value() }')
compile_files([directory, sibling_ok], 'sibling-ok.dll')
boxes = source('folder/boxes.n', 'public class Box { }')
sibling_type = source('folder/other.n', 'public class User { public Get() : boxes.Box { null } }')
compile_files([boxes, sibling_type], 'sibling-type-leak.dll', False, 'boxes')
sibling_type_ok = source('folder/other.n', 'using folder.boxes; public class User { public Get() : Box { null } }')
compile_files([boxes, sibling_type_ok], 'sibling-type-ok.dll')
clr_directory = source('reader.n', 'using folder; Run() : int { ClrApi.Value() }')
compile_files([directory, clr_directory], 'clr-directory.dll', extra=['-r:' + str(work / 'Foreign.dll')])
compile_files([directory, leak], 'clr-directory-leak.dll', False, 'member',
              extra=['-r:' + str(work / 'Foreign.dll')])
alias_leak = source('bad.n', 'using Dir = folder; Run() : int { Dir.member.Value() }')
compile_files([directory, alias_leak], 'directory-alias-leak.dll', False, 'member',
              extra=['-r:' + str(work / 'Foreign.dll')])

# A separately compiled module remains consumable through normal CLR references.
single = source('single.n', '''
mask api { Value() : int { 13 } private Secret() : int { 19 } }
private mask hidden { Value() : int { 23 } }
''')
compile_files([single], 'single.dll')
reader = source('reader.n', 'using single; Run() : int { api.Value() }')
compile_files([reader], 'reader.dll', extra=['-r:' + str(work / 'single.dll')])
for text, diagnostic in [
    ('Make() : object { single.hidden.Value() }', 'hidden'),
    ('Run() : int { single.api.Secret() }', 'Secret'),
]:
    bad = source('bad.n', text)
    compile_files([bad], 'external-private.dll', False, diagnostic,
                  extra=['-r:' + str(work / 'single.dll')])

# Preserve generic arity overloads, ordinary instance types, properties and fields.
generic = source('generic.n', '''
class Box[T] { public this() {} }
class Box[T, U] { public this() {} }
class Box[T, U, V] { public this() {} }
class Box[T, U, V, W] { public this() {} }
Make() : Box[int, string, bool] { Box() }
mask state {
  mutable Value : int = 3;
  Next : int { get { ++Value; Value } }
  Identity[T](value : T) : T { value }
}
Run() : int { state.Identity(state.Next) }
''')
compile_files([generic], 'generic.dll')
generic_host = source('GenericHost.cs', '''
class Host { static void Main() {
 if (generic.Run() != 4 || generic.Run() != 5 || generic.Make() == null)
   throw new System.Exception("Generic module or property failed");
 System.Console.WriteLine("PASS: generic arity overloads, fields, properties, generic mask functions");
} }
''')
compile_csharp(['mcs', '-r:' + str(work / 'generic.dll'), '-out:' + str(work / 'GenericHost.exe'), generic_host])
run([runtime, work / 'GenericHost.exe'])

# Preserve macro authoring as a separate compilation stage, including mask scope.
definitions = source('extensions.n', '''
macro Increment(value) { <[ $value + 1 ]> }
Base() : int { 4 }
macro WithBase(value) { <[ Base() + $value ]> }
mask api {
  Bias() : int { 2 }
  macro WithBias(value) { <[ Bias() + $value ]> }
  macro Twice(value) { <[ $value + $value ]> }
  macro Triple(value) syntax ("triple", value) { <[ $value * 3 ]> }
}
private mask hidden {
  macro Secret(value) { <[ $value + 100 ]> }
}
''')
compile_files([definitions], 'extensions.dll', extra=[
    '-r:' + str(compiler.parent / 'Nemerle.Compiler.dll')])
script = source('script.n', '''
using extensions;
using extensions.api;
Base() : int { 99 }
Bias() : int { 80 }
Run() : int { Increment(Twice(3)) + (triple 2) + WithBase(1) + WithBias(1) }
''')
compile_files([script], 'script.dll', extra=['-r:' + str(work / 'extensions.dll')])
macro_host = source('MacroHost.cs', '''
class Host { static void Main() {
 if (script.Run() != 21) throw new System.Exception("Macro expansion or definition-site scope failed");
 System.Console.WriteLine("PASS: file and mask macro definitions, syntax macro consumption");
} }
''')
compile_csharp(['mcs', '-r:' + str(work / 'script.dll'), '-out:' + str(work / 'MacroHost.exe'), macro_host])
run([runtime, work / 'MacroHost.exe'])
private_macro = source('bad.n', 'using extensions.hidden; Run() : int { Secret(1) }')
compile_files([private_macro], 'private-macro.dll', False, 'Secret',
              extra=['-macros:' + str(work / 'extensions.dll')])
shadow = source('extensions.n', 'Run() : int { Increment(1) }')
compile_files([shadow], 'macro-shadow.dll', False, 'Increment',
              extra=['-macros:' + str(work / 'extensions.dll')])
shadow = source('extensions.n', 'using extensions.api; Run() : int { triple 2 }')
compile_files([shadow], 'syntax-shadow.dll', False,
              extra=['-macros:' + str(work / 'extensions.dll')])
print('PASS: module naming, private access, import isolation, source precedence, DLL reuse', flush=True)

# Generated code (Nitra's grammars) under a source module's path nests in that module, and a generated partial part
# completes the source type of that name (source text itself can't say `partial`).
generator = source('generator.n', '''
using Nemerle.Compiler.Parsetree;
[MacroUsage(MacroPhase.BeforeInheritance, MacroTargets.Assembly)]
macro GenerateModel()
{
  def env = Nemerle.Macros.Manager().CoreEnv.EnterIntoNamespace(["app", "model"]);
  env.Define(<[ decl: public partial class Gen { public Extra() : int { 2 } } ]>).Compile();
  env.EnterIntoNamespace(["inner"]).Define(<[ decl: public class Deep { public Value() : int { 3 } } ]>).Compile();
}
''')
compile_files([generator], 'generator.dll', extra=['-r:' + str(compiler.parent / 'Nemerle.Compiler.dll')])
model = source('app/model.n', '''
using generator;
[assembly: GenerateModel()]
public class Gen { public Base() : int { 1 } }
public Run() : int { Gen().Base() + Gen().Extra() + inner.Deep().Value() }
''')
compile_files([model], 'model.dll', extra=['-macros:' + str(work / 'generator.dll')])
model_host = source('ModelHost.cs', '''
class Host { static void Main() {
 if (app.model.Run() != 6 || typeof(app.model.inner.Deep).DeclaringType != typeof(app.model.inner)) throw new System.Exception();
 System.Console.WriteLine("PASS: generated types nest in source modules; generated partial completes a source type");
} }
''')
compile_csharp(['mcs', '-r:' + str(work / 'model.dll'), '-out:' + str(work / 'ModelHost.exe'), model_host])
run([runtime, work / 'ModelHost.exe'])

# Top-level statements of a file module, in source order, are its Main; members may sit between them. A typeless
# `mutable x = ...` is a local of Main, `mutable x : T` a field.
program = source('program.n', """using System.Console;
mutable counter : int = 40;
def twice = Twice(1);
Twice(x : int) : int { x * 2 }
mutable local = counter + twice;
WriteLine(local);
mask m { public Seven() : int { 7 } }
WriteLine(m.Seven());""")
run([runtime, compiler, program, '-source-root:' + str(work), '-out:' + str(work / 'program.exe'), '-no-color', *modern_references])
if runtime != 'mono': shutil.copy2(compiler.with_name('ncc.runtimeconfig.json'), work / 'program.runtimeconfig.json')
ran = run([runtime, work / 'program.exe'])
if ran.stdout.split() != ['42', '7']: raise RuntimeError('top-level statements: ' + ran.stdout)
print('PASS: top-level statements of a file module are its Main (members in between, typeless mutable is a local)', flush=True)
# a top-level statement may continue on the next line, as in classic Nemerle
flow = source('flow.n', """using System.Console;
try { throw System.Exception("boom") }
catch { | e => WriteLine("caught " + e.Message) }
finally { WriteLine("finally") }
def n = 3;
if (n > 2)
  WriteLine("big")
else
  WriteLine("small");""")
run([runtime, compiler, flow, '-source-root:' + str(work), '-out:' + str(work / 'flow.exe'), '-no-color', *modern_references])
if runtime != 'mono': shutil.copy2(compiler.with_name('ncc.runtimeconfig.json'), work / 'flow.runtimeconfig.json')
ran = run([runtime, work / 'flow.exe'])
if ran.stdout.split('\n')[:3] != ['caught boom', 'finally', 'big']:
    raise RuntimeError('multi-line top-level statements: ' + ran.stdout)
print('PASS: top-level try/catch/finally and if/else continue across lines', flush=True)

# A file's top-level code runs once, where a file imports it (`using`), before the importer's own top-level code, as
# Python runs a module on import. Its `def`/`mutable` are the module's state: private, `public def` is reached as
# file.x by a file that imports it. The program starts at main.n (or the file -main: names).
init = work / 'init'
source('init/lib/config.n', """public def name = "config";
def secret = 42;
mutable count = 0;
System.Console.WriteLine("config runs");
public Next() : int { count++; count + secret - 42 }""")
source('init/helper.n', """using lib.config;
public Hello() : string { "hello from " + lib.config.name }""")
source('init/main.n', """using lib.config;
using helper;
System.Console.WriteLine("main");
System.Console.WriteLine(lib.config.name);
System.Console.WriteLine(helper.Hello());
System.Console.WriteLine(lib.config.Next() + lib.config.Next());""")
init_sources = [init / 'main.n', init / 'helper.n', init / 'lib/config.n']
run([runtime, compiler, *init_sources, '-source-root:' + str(init), '-out:' + str(work / 'init.exe'), '-no-color', *modern_references])
if runtime != 'mono': shutil.copy2(compiler.with_name('ncc.runtimeconfig.json'), work / 'init.runtimeconfig.json')
ran = run([runtime, work / 'init.exe'])
if ran.stdout.split() != ['config', 'runs', 'main', 'config', 'hello', 'from', 'config', '3']:
    raise RuntimeError('top-level code at using: ' + ran.stdout)
for name, text, diagnostic in (('bare', 'using lib.config;\nSystem.Console.WriteLine(name);', 'unbound name'),
                               ('unimported', 'System.Console.WriteLine(lib.config.name);', 'unbound name'),
                               ('private', 'using lib.config;\nSystem.Console.WriteLine(lib.config.secret);', 'cannot access'),
                               ('early', 'System.Console.WriteLine(x);\ndef x = 42;', 'is NotYet here'),
                               ('no-value', 'mutable x;\nSystem.Console.WriteLine($"$x");', 'declared at line 1 (mutable x;) but never given a value'),
                               ('later-value', 'mutable x;\nSystem.Console.WriteLine(x);\nx = 10;', 'gets its first one at line 3'),
                               ('hint', 'WriteLine("hi");', 'it is System.Console.WriteLine: add `using System.Console;\'')):
    source('init/main.n', text)
    run([runtime, compiler, init / 'main.n', init / 'lib/config.n', '-source-root:' + str(init), '-out:' + str(work / ('init-' + name + '.exe')),
         '-no-color', *modern_references], False, diagnostic)
source('init/main.n', 'System.Console.WriteLine("main");')
source('init/other.n', 'System.Console.WriteLine("other");')
run([runtime, compiler, init / 'other.n', init / 'helper.n', init / 'lib/config.n', '-source-root:' + str(init), '-out:' + str(work / 'init-nostart.exe'),
     '-no-color', *modern_references], False, 'a program starts at main.n')
run([runtime, compiler, init / 'other.n', init / 'helper.n', init / 'lib/config.n', '-main:other', '-source-root:' + str(init), '-out:' + str(work / 'init-other.exe'),
     '-no-color', *modern_references])
if runtime != 'mono': shutil.copy2(compiler.with_name('ncc.runtimeconfig.json'), work / 'init-other.runtimeconfig.json')

# `def (w, h) = ...` at the top level declares w and h (the tuple has no name, only its parts): each is the file's
# state, as `def w`, so functions read it; `mutable (x, y)` makes both mutable; nested parts, types and `_` work; a
# value that is not written out as a tuple is taken apart once; `public def (a, b)` makes both public
tuples = work / 'tuples'
source('tuples/sizes.n', 'public def (pw, ph) = (3, 4);')
source('tuples/main.n', '''using sizes;
mutable calls = 0;
def (w, h) = (800, 600);
mutable (x, y) = Size();
def (_, (a, b : string)) = (0, (1, "two"));
Size() : int * int { calls++; (2, 5) }
Area() : int { w * h }
Move() : void { x += 10; y += 1 }
Move();
System.Console.WriteLine($"$(Area()) $x $y $a $b $calls $(sizes.pw + sizes.ph)");''')
run([runtime, compiler, tuples / 'main.n', tuples / 'sizes.n', '-source-root:' + str(tuples), '-out:' + str(work / 'tuples.exe'), '-no-color', *modern_references])
if runtime != 'mono': shutil.copy2(compiler.with_name('ncc.runtimeconfig.json'), work / 'tuples.runtimeconfig.json')
ran = run([runtime, work / 'tuples.exe'])
if ran.stdout.split() != ['480000', '12', '6', '1', 'two', '1', '7']:
    raise RuntimeError('top-level tuple declarations: ' + ran.stdout)
source('tuples/main.n', 'def (w, h) = (1, 2);\nRun() : int { w + h }\nw = 3;')
run([runtime, compiler, tuples / 'main.n', '-source-root:' + str(tuples), '-out:' + str(work / 'tuples-readonly.exe'), '-no-color',
     *modern_references], False, "symbol `main.w', which is read-only")
print('PASS: a top-level `def (w, h)` declares w and h as the file\'s state (mutable, nested, typed, public, taken apart once)', flush=True)

# a def declares its names, so its pattern must always match: one that can fail (a list, a variant) is an error, in a
# function and at the top level, unless the shape is written out or an `else` (which must leave) takes the rest
for name, text in (('function', 'F(l : list[int]) : int { def [x, y] = l; x + y }\nSystem.Console.WriteLine(F([1, 2]));'),
                   ('top-level', 'def l = [1, 2];\ndef [x, y] = l;\nSystem.Console.WriteLine(x + y);'),
                   ('cons', 'def l : list[int] = [1, 2];\ndef (first :: _) = l;\nSystem.Console.WriteLine(first);')):
    source('shapes/main.n', text)
    run([runtime, compiler, work / 'shapes/main.n', '-source-root:' + str(work / 'shapes'), '-out:' + str(work / ('shapes-' + name + '.exe')),
         '-no-color', *modern_references], False, 'does not fit every value')
source('shapes/main.n', '''using System;
def [a, b] = [1, 2];
Two(l : list[int]) : list[int] { l }
def [p, q] = Two([3, 4]) else throw ArgumentException("need two");
def (v :: _) = Two([5]) else throw ArgumentException("need a value");
Sum() : int { a + b + p + q + v }
Pair(l : list[int]) : string
{
  def [x, y] = l else throw ArgumentException($"need two, got $(l.Length)");
  $"$x and $y"
}
Console.WriteLine(Sum());
Console.WriteLine(Pair([7, 8]));
try { Console.WriteLine(Pair([1, 2, 3])) } catch { | e is ArgumentException => Console.WriteLine(e.Message) }''')
run([runtime, compiler, work / 'shapes/main.n', '-source-root:' + str(work / 'shapes'), '-out:' + str(work / 'shapes.exe'), '-no-color', *modern_references])
if runtime != 'mono': shutil.copy2(compiler.with_name('ncc.runtimeconfig.json'), work / 'shapes.runtimeconfig.json')
ran = run([runtime, work / 'shapes.exe'])
if ran.stdout.splitlines() != ['15', '7 and 8', 'need two, got 3']:
    raise RuntimeError('def patterns with a shape written out or an else: ' + ran.stdout)
source('shapes/main.n', 'F() : list[int] -> int { fun (([a, b])) { a + b } }\nSystem.Console.WriteLine(F()([1, 2]));')
run([runtime, compiler, work / 'shapes/main.n', '-source-root:' + str(work / 'shapes'), '-out:' + str(work / 'shapes-parameter.exe'),
     '-no-color', *modern_references], False, "the parameter pattern `[a, b]' does not fit every value")
source('shapes/main.n', '''F(l : list[int]) : int
{
  def [x, y] = l else (0, 0);
  x + y
}
System.Console.WriteLine(F([3, 4]));
System.Console.WriteLine(F([1, 2, 3]));''')
run([runtime, compiler, work / 'shapes/main.n', '-source-root:' + str(work / 'shapes'), '-out:' + str(work / 'shapes-values.exe'), '-no-color', *modern_references])
if runtime != 'mono': shutil.copy2(compiler.with_name('ncc.runtimeconfig.json'), work / 'shapes-values.runtimeconfig.json')
ran = run([runtime, work / 'shapes-values.exe'])
if ran.stdout.split() != ['7', '0']:
    raise RuntimeError('def ... else with values: ' + ran.stdout)
print('PASS: a def whose pattern can fail is an error (function, top level, a cons, a parameter pattern said as one); a shape written out, or `def P = v else E`, '
      'declares its names for the whole scope', flush=True)

# an obsolete type of a library is reported where it is constructed, not only where it is named
source('obsolete/old.n', '[System.Obsolete("use New")] public class Old { public this() {} public static Helper() : int { 1 } public static Count : int = 2; }')
run([runtime, compiler, work / 'obsolete/old.n', '-source-root:' + str(work / 'obsolete'), '-target:library',
     '-out:' + str(work / 'old.dll'), '-no-color', *modern_references])
source('obsolete/main.n', 'def o = old.Old();\nSystem.Console.WriteLine(o != null);')
run([runtime, compiler, work / 'obsolete/main.n', '-source-root:' + str(work / 'obsolete'), '-r:' + str(work / 'old.dll'),
     '-out:' + str(work / 'obsolete.exe'), '-no-color', *modern_references], True, "old.Old is obsolete: 'use New'")
for name, text in (('static-method', 'System.Console.WriteLine(old.Old.Helper());'), ('static-field', 'System.Console.WriteLine(old.Old.Count);')):
    source('obsolete/main.n', text)
    run([runtime, compiler, work / 'obsolete/main.n', '-source-root:' + str(work / 'obsolete'), '-r:' + str(work / 'old.dll'),
         '-out:' + str(work / ('obsolete-' + name + '.exe')), '-no-color', *modern_references], True, "old.Old is obsolete: 'use New'")
print('PASS: an obsolete library type is warned where it is constructed and where a static member is reached through it', flush=True)
if run([runtime, work / 'init-other.exe']).stdout.split() != ['other']: raise RuntimeError('-main:other')
# a variable declared without a value and given one before it is read is fine
source('init/main.n', 'mutable x;\nx = 10;\nSystem.Console.WriteLine(x);')
run([runtime, compiler, init / 'main.n', '-source-root:' + str(init), '-out:' + str(work / 'init-assigned.exe'), '-no-color', *modern_references])
if runtime != 'mono': shutil.copy2(compiler.with_name('ncc.runtimeconfig.json'), work / 'init-assigned.runtimeconfig.json')
if run([runtime, work / 'init-assigned.exe']).stdout.split() != ['10']: raise RuntimeError('mutable x; x = 10')
source('init/main.n', 'def x : int = 42;\ndef show() { System.Console.WriteLine(x) }\nshow();')
run([runtime, compiler, init / 'main.n', '-source-root:' + str(init), '-out:' + str(work / 'init-typed.exe'), '-no-color', *modern_references])
if runtime != 'mono': shutil.copy2(compiler.with_name('ncc.runtimeconfig.json'), work / 'init-typed.runtimeconfig.json')
if run([runtime, work / 'init-typed.exe']).stdout.split() != ['42']: raise RuntimeError('typed top-level value')
# a top-level value's type comes from all of the top-level code: a lambda above its binding reads the storage, later
# uses refine it, a rebinding of the same type writes the same storage, and one that changes the type makes the storage
# a Content, unless something still uses the old type
cases = [
    ('lambda', 'def show() { System.Console.WriteLine(x) }\ndef x = 42;\nshow();', ['42']),
    ('refined', 'mutable items = [];\nitems ::= 1;\nitems ::= 2;\nSum() : int { items.FoldLeft(0, _ + _) }\nSystem.Console.WriteLine(Sum());', ['3']),
    ('rebound', 'def x = 5;\ndef x = x * 2;\nShow() : void { System.Console.WriteLine(x) }\nShow();', ['10']),
    ('retyped', 'def y = 5;\ndef y = y.ToString() + "!";\nSystem.Console.WriteLine(y.Length);\nShow() : void { System.Console.WriteLine(y.As.[string]()) }\nShow();', ['2', '5!']),
    ('final-type', 'def y = 5;\ndef y = y.ToString() + "?";\nShow() : void { System.Console.WriteLine(y.Length) }\nShow();', ['2']),
    ('open-use', 'def y = 5;\ndef y = "five";\nKeep(o : object) : string { match (o) { | c is Nemerle.Scopes.Content => "container of " + c.Type.Name + ": " + c.As.[string]() | _ => "bare" } }\nShow() : void { System.Console.WriteLine(Keep(y)) }\nShow();', ['container', 'of', 'String:', 'five']),
    ('splice-using', 'using System.Math;\nF() : string { $"$(Abs(-3))" }\nSystem.Console.WriteLine($"$(Abs(-4)) $(F())");', ['4', '3']),
    ('shadowing', 'def y = 5;\ndef y = "five";\nF() : int { def y = 3; y + 1 }\ndef g = fun (y : int) { y * 2 };\nSystem.Console.WriteLine(F());\nSystem.Console.WriteLine(g(4));\nSystem.Console.WriteLine(y);', ['4', '8', 'five']),
    ('tuple', 'def pair = (1, 2);\nSum() : int { def (a, b) = pair; a + b }\nSystem.Console.WriteLine(Sum());', ['3']),
]
for name, text, expected in cases + [(n + '-debug', t, e) for (n, t, e) in cases]:
    source('init/main.n', text)
    # each case also with debug information, which wraps the compiler's own writes
    run([runtime, compiler, init / 'main.n', '-source-root:' + str(init), '-out:' + str(work / ('state-' + name + '.exe')), '-no-color', *modern_references,
         *(['-debug+'] if name.endswith('-debug') else [])])
    if runtime != 'mono': shutil.copy2(compiler.with_name('ncc.runtimeconfig.json'), work / ('state-' + name + '.runtimeconfig.json'))
    got = run([runtime, work / ('state-' + name + '.exe')]).stdout.split()
    if got != expected: raise RuntimeError('top-level state ' + name + ': ' + ' '.join(got))
source('init/main.n', 'def y = 5;\ndef y = y.ToString();\nBad() : int { y + 1 }\nSystem.Console.WriteLine(Bad());')
run([runtime, compiler, init / 'main.n', '-source-root:' + str(init), '-out:' + str(work / 'state-bad.exe'), '-no-color', *modern_references],
    False, 'changes type here (from int to string), but line 3 uses it as int')
# a user's macro in the top-level code expands once (the inference pass that types a quiet copy of the code leaves
# it for the real code): a macro that counts its expansions sees one
counter = work / 'counter'; counter.mkdir()
(counter / 'counting.n').write_text('using Nemerle.Compiler;\nmodule Counter { public mutable Count : int; }\n'
                                     'macro Expansions() { Counter.Count++; <[ $(Counter.Count : int) ]> }\n')
run([runtime, compiler, counter / 'counting.n', '-source-root:' + str(counter), '-target:library', '-out:' + str(work / 'counting.dll'),
     '-r:' + str(compiler.with_name('Nemerle.Compiler.dll')), '-no-color', *modern_references])
source('init/main.n', 'using counting;\ndef n = Expansions();\nSystem.Console.WriteLine(n);')
run([runtime, compiler, init / 'main.n', '-source-root:' + str(init), '-out:' + str(work / 'state-macro.exe'), '-no-color',
     '-r:' + str(work / 'counting.dll'), *modern_references])
if runtime != 'mono': shutil.copy2(compiler.with_name('ncc.runtimeconfig.json'), work / 'state-macro.runtimeconfig.json')
got = run([runtime, work / 'state-macro.exe']).stdout.split()
if got != ['1']: raise RuntimeError('a user macro in the top-level code expanded %s times' % got)
print('PASS: top-level values: lambdas read the storage, later uses refine the type, rebinding keeps or retypes the storage', flush=True)
# an imported file's top-level code runs in its type initializer: starting work there is warned, and work that uses
# the file while the top-level code waits for it is a deadlock, an error (the calls are the resolved ones)
source('init/main.n', 'using worker;\nSystem.Console.WriteLine("main");')
source('init/worker.n', 'def t = System.Threading.Tasks.Task.Run(() => 1);')
run([runtime, compiler, init / 'main.n', init / 'worker.n', '-source-root:' + str(init), '-out:' + str(work / 'thread-warn.exe'), '-no-color',
     *modern_references], True, 'Task.Run in the top-level code of an imported file')
source('init/worker.n', 'using T = System.Threading.Tasks.Task;\nHelper() : int { 2 }\ndef t = T.Run(() => Helper());\nt.Wait();')
run([runtime, compiler, init / 'main.n', init / 'worker.n', '-source-root:' + str(init), '-out:' + str(work / 'thread-deadlock.exe'), '-no-color',
     *modern_references], False, 'Task.Run runs work that uses this file while its top-level code waits for it')
# a wait is for the task it is called on: waiting for other work leaves the first start a warning
source('init/worker.n', 'using T = System.Threading.Tasks.Task;\nHelper() : int { 2 }\ndef t = T.Run(() => Helper());\ndef u = T.Run(() => 1);\nu.Wait();')
run([runtime, compiler, init / 'main.n', init / 'worker.n', '-source-root:' + str(init), '-out:' + str(work / 'thread-other.exe'), '-no-color',
     *modern_references], True, 'Task.Run in the top-level code of an imported file')
# .Result waits, and so does a thread's Join
source('init/worker.n', 'using T = System.Threading.Tasks.Task;\nHelper() : int { 2 }\ndef t = T.Run(() => Helper());\ndef r = t.Result;')
run([runtime, compiler, init / 'main.n', init / 'worker.n', '-source-root:' + str(init), '-out:' + str(work / 'thread-result.exe'), '-no-color',
     *modern_references], False, 'runs work that uses this file while its top-level code waits for it')
source('init/worker.n', 'Helper() : void { }\ndef th = System.Threading.Thread(() => Helper());\nth.Start();\nth.Join();')
run([runtime, compiler, init / 'main.n', init / 'worker.n', '-source-root:' + str(init), '-out:' + str(work / 'thread-join.exe'), '-no-color',
     *modern_references], False, 'Thread.new runs work that uses this file while its top-level code waits for it')
# work that reaches the file only through another file's function: followed across files
source('init/worker.n', 'using T = System.Threading.Tasks.Task;\nusing relay;\npublic Value() : int { 1 }\ndef t = T.Run(() => relay.Call());\nt.Wait();')
source('init/relay.n', 'using worker;\npublic Call() : int { worker.Value() + 1 }')
run([runtime, compiler, init / 'main.n', init / 'worker.n', init / 'relay.n', '-source-root:' + str(init), '-out:' + str(work / 'thread-relay.exe'),
     '-no-color', *modern_references], False, 'Task.Run runs work that uses this file while its top-level code waits for it')
print('PASS: threads in an imported file\'s top-level code: warned; a provable deadlock is an error, for the task a wait is on '
      '(Wait, .Result, Join) and for work that reaches the file through other files', flush=True)
# `export` makes a type global: one type by that name everywhere, reached without a using; any other type of that
# name contradicts it (the exporting file itself is the same origin)
source('init/lib/shapes.n', 'export class Pen { public Name() : string { "global pen" } }')
source('init/main.n', 'System.Console.WriteLine(Pen().Name());')
run([runtime, compiler, init / 'main.n', init / 'lib/shapes.n', '-source-root:' + str(init), '-out:' + str(work / 'export.exe'), '-no-color', *modern_references])
if runtime != 'mono': shutil.copy2(compiler.with_name('ncc.runtimeconfig.json'), work / 'export.runtimeconfig.json')
if run([runtime, work / 'export.exe']).stdout.split() != ['global', 'pen']: raise RuntimeError('export')
source('init/other.n', 'public class Pen { }')
run([runtime, compiler, init / 'main.n', init / 'lib/shapes.n', init / 'other.n', '-source-root:' + str(init), '-out:' + str(work / 'export-clash.exe'),
     '-no-color', *modern_references], False, 'is exported by lib.shapes as a global type, so no other type can have that name')
source('init/main.n', 'using lib.shapes;\nSystem.Console.WriteLine(Pen().Name());')
run([runtime, compiler, init / 'main.n', init / 'lib/shapes.n', '-source-root:' + str(init), '-out:' + str(work / 'export-same.exe'), '-no-color', *modern_references])
print('PASS: export: a global type is one type by its name everywhere; another type of that name is an error', flush=True)
print('PASS: top-level code runs once at its using; top-level values are private state, public def is file.x after using; '
      'a program starts at main.n or -main:', flush=True)

# File modules are the only layout: a namespace block is an error, and the removed switches are unknown options.
plain = source('plain.n', 'public Run() : int { 1 }')
run([runtime, compiler, plain, '-source-root:' + str(work), '-target:library', '-out:' + str(work / 'default.dll'), '-no-color', *modern_references])
legacy = source('legacy.n', 'namespace shared { public class Thing {} }')
run([runtime, compiler, legacy, '-source-root:' + str(work), '-target:library', '-out:' + str(work / 'nolegacy.dll'), '-no-color', *modern_references],
    False, 'namespace declarations are not allowed')
for removed in ('-legacy-namespaces', '-file-modules'):
    run([runtime, compiler, plain, removed, '-source-root:' + str(work), '-target:library', '-out:' + str(work / 'removed.dll'), '-no-color', *modern_references],
        False, removed)
print('PASS: file modules only; namespace declarations rejected; -legacy-namespaces and -file-modules removed', flush=True)

# -file-name-namespaces: the namespace is the file name only; file names must be unique.
short_lib = source('deep/inside/textual.n', 'public Shout() : int { 5 }')
short_user = source('elsewhere/caller.n', 'using textual; public Run() : int { Shout() }')
compile_files([short_lib, short_user], 'short.dll', extra=['-file-name-namespaces'])
twin = source('other/textual.n', 'public Other() : int { 6 }')
compile_files([short_lib, twin], 'short-dup.dll', False, 'duplicate file module identity: textual', extra=['-file-name-namespaces'])
print('PASS: -file-name-namespaces (file name as namespace, duplicates rejected)', flush=True)
