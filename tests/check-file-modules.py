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
if (work / 'init-nostart.exe').exists():
    raise RuntimeError('a failed compilation left its output behind (init-nostart.exe)')
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

# a file's values are inferred after those of the files it imports, whatever the order on the command line: here
# main.n (first) uses a member of lib's value while its own `items' gets its type from a later binding
source('order/lib.n', 'public def name = "x";')
source('order/main.n', 'using lib;\nmutable items = [];\nitems ::= 3;\nSystem.Console.WriteLine(lib.name.Length + items.Length);')
run([runtime, compiler, work / 'order/main.n', work / 'order/lib.n', '-source-root:' + str(work / 'order'), '-out:' + str(work / 'order.exe'),
     '-no-color', *modern_references])
if runtime != 'mono': shutil.copy2(compiler.with_name('ncc.runtimeconfig.json'), work / 'order.runtimeconfig.json')
if run([runtime, work / 'order.exe']).stdout.strip() != '2':
    raise RuntimeError('values inferred in import order')
print('PASS: top-level values are inferred in import order, not command-line order', flush=True)

# a file in a folder is a module in a namespace: `using geo.shapes;' brings its extension methods, as a root file's
source('ext/geo/shapes.n', 'public Doubled(this s : string) : string { s + s }\npublic module Inner { public Tripled(this s : string) : string { s + s + s } }')
source('ext/main.n', 'using geo.shapes;\nusing geo.shapes.Inner;\nSystem.Console.WriteLine("ab".Doubled() + " " + "c".Tripled());')
run([runtime, compiler, work / 'ext/main.n', work / 'ext/geo/shapes.n', '-source-root:' + str(work / 'ext'), '-out:' + str(work / 'ext.exe'), '-no-color', *modern_references])
if runtime != 'mono': shutil.copy2(compiler.with_name('ncc.runtimeconfig.json'), work / 'ext.runtimeconfig.json')
if run([runtime, work / 'ext.exe']).stdout.strip() != 'abab ccc':
    raise RuntimeError('extension methods of a module in a folder')
print('PASS: extension methods of a module in a folder (and of a module in it) come with its using', flush=True)

# a program's top-level code has its command-line arguments, as a script's has
source('argv/main.n', 'System.Console.WriteLine(args.Length.ToString() + " " + string.Join("+", args));')
run([runtime, compiler, work / 'argv/main.n', '-source-root:' + str(work / 'argv'), '-out:' + str(work / 'argv.exe'), '-no-color', *modern_references])
if runtime != 'mono': shutil.copy2(compiler.with_name('ncc.runtimeconfig.json'), work / 'argv.runtimeconfig.json')
if run([runtime, work / 'argv.exe', 'one', 'two']).stdout.strip() != '2 one+two':
    raise RuntimeError('args in a program')
print('PASS: a program\'s top-level code has args', flush=True)

# Span[T] and the other ref structs: their members (an indexer returning a reference, read and written through it;
# AsSpan, Slice, Memory.Span, foreach), and the rules of a value that lives on the stack only, each an error where it
# is broken (not boxed, captured, put inside another type, or kept in a field: a top-level value is a field)
if runtime != 'mono':   # (Span[T] is .NET's; the Mono run checks .NET Framework references)
    source('spans/main.n', '''using System;
    Sum(s : Span[int]) : int { mutable total = 0; foreach (x in s) total += x; total }
    Use() : string
    {
      def data = array[1, 2, 3, 4];
      def s = Span.[int](data);
      s[0] = 10;
      def words = "hello world".AsSpan();
      def at = words.IndexOf(" ".AsSpan());
      def bytes = Memory.[byte](array[1b, 2b, 3b]);
      $"$(data[0]) $(s[1]) $(Sum(s.Slice(1, 2))) $(words.Slice(at + 1).ToString()) $(bytes.Span.Slice(1).ToArray().Length)"
    }
    Console.WriteLine(Use());''')
    run([runtime, compiler, work / 'spans/main.n', '-source-root:' + str(work / 'spans'), '-out:' + str(work / 'spans.exe'), '-no-color', *modern_references])
    if runtime != 'mono': shutil.copy2(compiler.with_name('ncc.runtimeconfig.json'), work / 'spans.runtimeconfig.json')
    if run([runtime, work / 'spans.exe']).stdout.strip() != '10 2 5 world 2':
        raise RuntimeError('spans')
    for name, text, diagnostic in (
            ('top-level', 'using System;\ndef s = "abc".AsSpan();\nConsole.WriteLine(s.Length);', 'would be a top-level value holding'),
            ('captured', 'using System;\nF() : int { def s = "abc".AsSpan(); def g = () => s.Length; g() }', 'a lambda or local function cannot use it'),
            ('boxed', 'using System;\nF() : object { def s = "abc".AsSpan(); s }', 'cannot be boxed'),
            ('interpolated', 'using System;\nF() : string { def s = "abc".AsSpan(); $"$s" }', 'cannot be boxed'),
            ('in a tuple', 'using System;\nF() : int { def s = "abc".AsSpan(); def t = (s, 1); t[1] }', 'cannot be inside')):
        source('spans/rule.n', text)
        run([runtime, compiler, work / 'spans/rule.n', '-source-root:' + str(work / 'spans'), '-target:library', '-out:' + str(work / ('spans-' + name.replace(' ', '-') + '.dll')),
             '-no-color', *modern_references], False, diagnostic)
    print('PASS: Span[T]: indexer read and write, AsSpan, Slice, IndexOf, Memory.Span, foreach; and its rules (top level, '
          'capture, boxing, interpolation, inside a tuple) as errors', flush=True)

# async functions and `await': values, Task, ValueTask and void functions, waits in loops (a loop's closure kept
# across them), in expressions (evaluated in order, && and || still short), in try/catch and try/finally and in their
# handlers, exceptions and cancellation; top-level await, and async files (a file whose top-level code waits, or
# runs one that does first) awaited where they are imported, in `using' order; and the rules as errors
if runtime != 'mono':   # (ValueTask is .NET's; the Mono run checks .NET Framework references)
    source('async/lib/remote.n', '''using System.Threading.Tasks;
System.Console.WriteLine("remote starts");
public def greeting = await Task.Run(() => "hello from an async file");
System.Console.WriteLine("remote is ready");''')
    source('async/lib/middle.n', '''using lib.remote;
public def shout = lib.remote.greeting.ToUpper();''')
    source('async/lib/plain.n', '''public def seven = 7;
System.Console.WriteLine("plain is set up");''')
    source('async/main.n', '''using System;
using System.Threading;
using System.Threading.Tasks;
using lib.plain;
using lib.middle;

Later[T](v : T) : Task[T] { Task.Run(() => v) }
async Boom(message : string) : Task[int] { await Task.Delay(1); throw InvalidOperationException(message) }
mutable order : list[string] = [];
Note(s : string, v : int) : int { order ::= s; v }

async Sum(n : int) : Task[int]
{
  mutable total = 0;
  for (mutable i = 1; i <= n; i++) { def v = await Task.Run(() => i); total += v }
  total
}
async Exprs() : Task[string]
{
  def sum = 1 + await Later(2) + await Later(3);
  def len = (await Later("four")).Length;
  def ok = await Later(true) && await Later(false) || await Later(true);
  def text = if (await Later(false)) "then" else "else";
  def counted = Note("b", 1) + await Later(Note("c", 2));
  $"$sum $len $ok $text $counted $(order.Rev())"
}
async Caught() : Task[string]
{
  try { def b = await Boom("inner"); $"not $b" }
  catch { | e is InvalidOperationException => def note = await Later("logged"); $"$note $(e.Message)" }
}
mutable log : list[string] = [];
async Nested() : Task[int]
{
  for (mutable i = 0; i < 3; i++)
    try
    {
      await Task.Delay(1);
      try { when (i == 1) _ = await Boom("one"); log ::= $"ok $i" }
      finally { await Task.Yield(); log ::= $"finally $i" }
    }
    catch { | e => log ::= "caught " + e.Message }
  log.Length
}
async Small() : ValueTask[int] { await Task.Delay(1); 7 }
mutable fired = false;
async Fire() : void { await Task.Delay(1); fired = true }
async Wait(token : CancellationToken) : Task { await Task.Delay(10000, token) }
class Counter
{
  mutable count : int;
  public async Bump(by : int) : Task[int] { await Task.Delay(1); count += by; count }
}

Console.WriteLine("main starts");
Console.WriteLine(lib.middle.shout);
Console.WriteLine(await Sum(10));
Console.WriteLine(await Exprs());
Console.WriteLine(await Caught());
Console.WriteLine($"$(await Nested()) $(log.Rev())");
Console.WriteLine(await Small() + await Counter().Bump(lib.plain.seven));
Fire();
Thread.Sleep(200);
def source = CancellationTokenSource();
def pending = Wait(source.Token);
source.Cancel();
try { await pending } catch { | _ is OperationCanceledException => Console.WriteLine($"fired $fired, canceled $(pending.IsCanceled)") }
Console.WriteLine(args.Length)''')
    run([runtime, compiler, work / 'async/main.n', work / 'async/lib/remote.n', work / 'async/lib/middle.n', work / 'async/lib/plain.n',
         '-source-root:' + str(work / 'async'), '-out:' + str(work / 'async.exe'), '-no-color', *modern_references])
    shutil.copy2(compiler.with_name('ncc.runtimeconfig.json'), work / 'async.runtimeconfig.json')
    expected = '''plain is set up
remote starts
remote is ready
main starts
HELLO FROM AN ASYNC FILE
55
6 4 True else 3 [b, c]
logged inner
6 [ok 0, finally 0, finally 1, caught one, ok 2, finally 2]
14
fired True, canceled True
2'''
    got = run([runtime, work / 'async.exe', 'one', 'two']).stdout.strip()
    if got != expected:
        raise RuntimeError('async: got\n' + got)
    for name, text, diagnostic in (
            ('lock', 'using System.Threading.Tasks;\nasync F() : Task { def o = object(); lock (o) { await Task.Delay(1) } }', "`await' in a `lock'"),
            ('lambda', 'using System.Threading.Tasks;\nasync F() : Task[int] { def f = () => await Task.FromResult(1); f() }', "`await' in a lambda"),
            ('span', 'using System;\nusing System.Threading.Tasks;\nasync F() : Task[int] { def s = "abc".AsSpan(); await Task.Delay(1); s.Length }', 'keeps its locals between its steps'),
            ('return type', 'using System.Threading.Tasks;\nasync F() : int { await Task.Delay(1); 1 }', 'an async function returns Task'),
            ('yield', 'using System.Threading.Tasks;\nasync F() : Task { await Task.Delay(1); yield 1 }', "`yield' in an async function that returns a task")):
        source('async/rule.n', text)
        run([runtime, compiler, work / 'async/rule.n', '-source-root:' + str(work / 'async'), '-target:library', '-out:' + str(work / ('async-' + name.replace(' ', '-') + '.dll')),
             '-no-color', *modern_references], False, diagnostic)
    source('async/lambdas.n', '''using System;
using System.Collections.Generic;
using System.Threading.Tasks;

Later[T](v : T) : Task[T] { Task.Run(() => v) }

Twice(f : int -> Task[int], x : int) : Task[int] { f(x) }

// an async lambda in a plain (not async) function
Run() : int
{
  def add = async (x : int) => { def y = await Later(x); y + 1 };
  def logged = List();
  def log = async fun (s : string) { await Task.Delay(1); logged.Add(s) };
  log("one").Wait();
  add(41).Result + logged.Count
}

async Outer() : Task[string]
{
  mutable total = 0;
  def bump = async (n : int) => { await Task.Yield(); total += n; total };   // captures the outer function's local
  _ = await bump(2);
  def again = await bump(3);
  async def twice(s : string) : Task[string] { def a = await Later(s); a + a }
  def tasks = [1, 2, 3].Map(i => Task.Run(async () => { await Task.Delay(i); i * 10 }));
  mutable sum = 0;
  foreach (t in tasks) sum += await t;
  def ab = await twice("ab");
  $"$again $ab $sum $(await Twice(async x => await Later(x * 2), 21))"
}

async Throws() : Task
{
  def f = async () => { await Task.Delay(1); throw InvalidOperationException("from a lambda") };
  try { await f() } catch { | e => Console.WriteLine("caught " + e.Message) }
}

Console.WriteLine(Run());
Console.WriteLine(await Outer());
await Throws();
// a top-level async lambda
def square = async (x : int) => { await Task.Delay(1); x * x };
Console.WriteLine(await square(9))
''')
    run([runtime, compiler, work / 'async/lambdas.n', '-source-root:' + str(work / 'async'), '-out:' + str(work / 'async-lambdas.exe'), '-no-color', *modern_references])
    shutil.copy2(compiler.with_name('ncc.runtimeconfig.json'), work / 'async-lambdas.runtimeconfig.json')
    got = run([runtime, work / 'async-lambdas.exe']).stdout.strip()
    if got != '''43
5 abab 60 42
caught from a lambda
81''':
        raise RuntimeError('async lambdas: got\n' + got)
    source('async/each.n', '''using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

mutable log : list[string] = [];

class Countdown : IAsyncEnumerable[int]
{
  from : int;
  public this(from : int) { this.from = from }
  public GetAsyncEnumerator(_token : CancellationToken = default(CancellationToken)) : IAsyncEnumerator[int] { Steps(from) }
  class Steps : IAsyncEnumerator[int]
  {
    mutable left : int;
    public this(from : int) { left = from + 1 }
    public Current : int { get { left } }
    public MoveNextAsync() : ValueTask[bool] { left--; ValueTask(Task.Run(() => left > 0)) }
    public DisposeAsync() : ValueTask { log ::= "disposed"; ValueTask(Task.Delay(1)) }
  }
}

class Resource : IAsyncDisposable
{
  name : string;
  public this(name : string) { this.name = name }
  public DisposeAsync() : ValueTask { log ::= "closed " + name; ValueTask(Task.Delay(1)) }
}

async Sum() : Task[int]
{
  mutable total = 0;
  await foreach (x in Countdown(4)) { await Task.Yield(); total += x }
  total
}

async Use() : Task[string]
{
  await using (a = Resource("a"), b = Resource("b")) { await Task.Delay(1); log ::= "using" }
  "used"
}

Console.WriteLine(await Sum());
Console.WriteLine(await Use());
Console.WriteLine(log.Rev());
''')
    run([runtime, compiler, work / 'async/each.n', '-source-root:' + str(work / 'async'), '-out:' + str(work / 'async-each.exe'), '-no-color', *modern_references])
    shutil.copy2(compiler.with_name('ncc.runtimeconfig.json'), work / 'async-each.runtimeconfig.json')
    got = run([runtime, work / 'async-each.exe']).stdout.strip()
    if got != '''10
used
[disposed, using, closed b, closed a]''':
        raise RuntimeError('async each: got\n' + got)
    source('async/streams.n', '''using System;
using System.Collections.Generic;
using System.Threading.Tasks;

mutable log : list[string] = [];

async Numbers(count : int) : IAsyncEnumerable[int]
{
  try
  {
    for (mutable i = 1; i <= count; i++)
    {
      await Task.Delay(1);
      yield i * i
    }
  }
  finally { log ::= "numbers done" }
}

async Words() : IAsyncEnumerable[string]
{
  await foreach (n in Numbers(3)) yield $"#$n";
  yield "end"
}

async Fails() : IAsyncEnumerable[int]
{
  yield 1;
  await Task.Delay(1);
  throw InvalidOperationException("stream broke")
}

async Read() : Task[string]
{
  mutable seen = [];
  await foreach (w in Words()) seen ::= w;
  // stop early: the stream's finally runs when the enumeration is disposed
  $"$(seen.Rev())"
}

async Broken() : Task[string]
{
  mutable got = [];
  try { await foreach (n in Fails()) got ::= n } catch { | e => got ::= -1; log ::= e.Message }
  $"$(got.Rev())"
}

Console.WriteLine(await Read().ContinueWith(t => if (t.IsCanceled) "canceled" else t.Result));
Console.WriteLine(await Broken());
Console.WriteLine(log.Rev());
''')
    run([runtime, compiler, work / 'async/streams.n', '-source-root:' + str(work / 'async'), '-out:' + str(work / 'async-streams.exe'), '-no-color', *modern_references])
    shutil.copy2(compiler.with_name('ncc.runtimeconfig.json'), work / 'async-streams.runtimeconfig.json')
    got = run([runtime, work / 'async-streams.exe']).stdout.strip()
    if got != '''[#1, #4, #9, end]
[1, -1]
[numbers done, stream broke]''':
        raise RuntimeError('async streams: got\n' + got)
    # as C#'s: leaving a stream early resumes it to run its finally blocks (waiting in them), no catch sees that, a
    # [EnumeratorCancellation] parameter gets WithCancellation's token, each enumeration after the first is a copy;
    # and break, continue and return leave a try through its finally, waiting or not
    source('async/exits.n', '''using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Nemerle.Imperative;

mutable log : list[string] = [];

async Guarded(name : string) : IAsyncEnumerable[string]
{
  try
  {
    try { yield name + "1"; yield name + "2"; yield name + "3" }
    catch { | e => log ::= "caught " + e.GetType().Name }
  }
  finally { await Task.Delay(1); log ::= "finally " + name }
}

async Ticks([EnumeratorCancellation] token : CancellationToken = default(CancellationToken)) : IAsyncEnumerable[int]
{
  mutable i = 0;
  while (true) { await Task.Delay(1, token); i++; yield i }
}

async Squares(count : int) : IAsyncEnumerable[int]
{
  for (mutable i = 1; i <= count; i++) { await Task.Yield(); yield i * i }
}

async Loops() : Task
{
  mutable i = 0;
  while (i < 3)
  {
    i++;
    try { await Task.Yield(); when (i == 1) continue; break } finally { log ::= $"plain $i" }
  }
  while (true) { try { await Task.Yield(); break } finally { await Task.Delay(1); log ::= "waiting" } }
  foreach (x in [1, 2]) using (closing = Closing(x)) { await Task.Yield(); when (x == 1) break; _ = closing }
}

async Early(n : int) : Task[int]
{
  try { await Task.Yield(); when (n > 0) return n * 10 } finally { await Task.Delay(1); log ::= $"early $n" }
  -1
}

class Closing : IDisposable { n : int; public this(n : int) { this.n = n } public Dispose() : void { log ::= $"closed $n" } }

await foreach (x in Guarded("a")) { log ::= x; when (x == "a2") break }
def s = Squares(3);
mutable total = 0;
await foreach (x in s) total += x;
await foreach (x in s) total += x;
def cts = CancellationTokenSource();
mutable seen = 0;
try { await foreach (x in Ticks().WithCancellation(cts.Token)) { seen = x; when (x == 3) cts.Cancel() } }
catch { | _ is OperationCanceledException => log ::= $"cancelled at $seen" }
await Loops();
Console.WriteLine($"$total $(await Early(4)) $(await Early(0))");
Console.WriteLine(log.Rev());
''')
    run([runtime, compiler, work / 'async/exits.n', '-source-root:' + str(work / 'async'), '-out:' + str(work / 'async-exits.exe'), '-no-color', *modern_references])
    shutil.copy2(compiler.with_name('ncc.runtimeconfig.json'), work / 'async-exits.runtimeconfig.json')
    got = run([runtime, work / 'async-exits.exe']).stdout.strip()
    if got != '''28 40 -1
[a1, a2, finally a, cancelled at 3, plain 1, plain 2, waiting, closed 1, early 4, early 0]''':
        raise RuntimeError('async exits: got\n' + got)
    # an async lambda given where a ValueTask is wanted; and stack traces with C#'s frames (each function once, but a
    # rethrow after a wait, once more)
    source('async/values.n', '''using System;
using System.Threading.Tasks;

Twice(f : Func[ValueTask[int]]) : ValueTask[int] { f() }
Done(f : Func[ValueTask]) : ValueTask { f() }

async Boom() : Task[int] { await Task.Delay(1); throw InvalidOperationException("boom") }
async Rethrow() : Task[int] { try { await Boom() } catch { | _ => await Task.Delay(1); throw } }
async Plain() : Task[int] { await Boom() }

def typed : Func[ValueTask[int]] = async () => { await Task.Yield(); 5 };
Console.WriteLine((await typed()) + (await Twice(async () => 6)));
await Done(async () => { await Task.Delay(1); Console.WriteLine("done") });
def frames(t : Task[int]) : string
{
  try { _ = t.Result; "" }
  catch { | e is AggregateException => string.Join(" ", $[l.Trim().Split(' ')[1] | l in e.InnerException.StackTrace.Split('\\n')]) }
}
Console.WriteLine(frames(Rethrow()));
Console.WriteLine(frames(Plain()))
''')
    run([runtime, compiler, work / 'async/values.n', '-debug+', '-source-root:' + str(work / 'async'), '-out:' + str(work / 'async-values.exe'), '-no-color', *modern_references])
    shutil.copy2(compiler.with_name('ncc.runtimeconfig.json'), work / 'async-values.runtimeconfig.json')
    got = run([runtime, work / 'async-values.exe']).stdout.strip()
    if got != '''11
done
values.Boom() values.Rethrow() values.Rethrow()
values.Boom() values.Plain()''':
        raise RuntimeError('async values and traces: got\n' + got)
    # the locals that lambdas use, in a struct state machine, are a class's (as C#'s display class): shared with them,
    # `this' too, a loop's per iteration, in a generic function, through nested lambdas and async lambdas
    source('async/display.n', '''using System;
using System.Collections.Generic;
using System.Threading.Tasks;

async Shared() : Task[string]
{
  mutable count = 0;
  def inc = () => { count++; count };
  await Task.Yield();
  _ = inc();
  count += 10;
  await Task.Delay(1);
  def seen = inc();
  $"$count $seen"
}

class Counter
{
  mutable total : int;
  public async Add(xs : list[int]) : Task[int]
  {
    def add = x => total += x;   // captures `this'
    foreach (x in xs) { await Task.Yield(); add(x) }
    total
  }
}

async Loops() : Task[int]
{
  def fs = List();
  for (mutable i = 0; i < 3; i++) { def j = i; await Task.Yield(); fs.Add(() => j * 10) }
  mutable sum = 0;
  foreach (f in fs) sum += f();
  sum
}

async Generic[T](x : T, n : int) : Task[list[T]]
{
  def make = k => $[x | _ in [1 .. k]];
  await Task.Yield();
  make(n)
}

async Nested(a : int) : Task[int]
{
  def outer = b => { def inner = c => a + b + c; inner(1) };
  await Task.Delay(1);
  outer(2) + a
}

async AsyncInAsync(a : int) : Task[int]
{
  mutable acc = a;
  def step = async (k : int) => { await Task.Yield(); acc += k; def twice = () => acc * 2; twice() };
  def r1 = await step(1);
  def r2 = await step(2);
  r1 + r2 + acc
}

Console.WriteLine(await Shared());
Console.WriteLine(await Counter().Add([1, 2, 3]));
Console.WriteLine(await Loops());
Console.WriteLine(await Generic("ab", 3));
Console.WriteLine(await Nested(5));
Console.WriteLine(await AsyncInAsync(10))
''')
    run([runtime, compiler, work / 'async/display.n', '-source-root:' + str(work / 'async'), '-out:' + str(work / 'async-display.exe'), '-no-color', *modern_references])
    shutil.copy2(compiler.with_name('ncc.runtimeconfig.json'), work / 'async-display.runtimeconfig.json')
    got = run([runtime, work / 'async-display.exe']).stdout.strip()
    if got != '''12 12
6
30
[ab, ab, ab]
13
61''':
        raise RuntimeError('async display classes: got\n' + got)
    # an async file's function called before its top-level code has ended (from a file that does not import it)
    # waits for it; the code's own calls do not; what it threw comes out of each call
    source('early/config.n', '''using System;
using System.Threading.Tasks;

mutable settings : string = null;
async Load() : Task[string] { await Task.Delay(50); "loaded" }
settings = await Load();
Console.WriteLine("config sees " + Get());

public Get() : string { settings }
public async GetAsync() : Task[string] { await Task.Yield(); settings + "!" }
''')
    source('early/broken.n', '''using System.Threading.Tasks;
await Task.Delay(10);
throw System.InvalidOperationException("broken failed");
public Get() : int { 1 }
''')
    source('early/main.n', '''using System;
// its public state is a property that waits too (a field's read could not), as C# and reflection see it
Console.WriteLine(config.settings);
def property = typeof(config).GetProperty("settings");
def noField = object.ReferenceEquals(typeof(config).GetField("settings"), null);
Console.WriteLine($"$(property != null) $(property.GetValue(null)) $noField");
Console.WriteLine(config.Get());
Console.WriteLine(config.GetAsync().Result);
def fails() { try { _ = broken.Get(); "no" } catch { | e => e.Message } }
Console.WriteLine(fails() + " " + fails());
// a ValueTask lambda by a delegate's constructor, as a ValueTask's state machine
def made = Func.[System.Threading.Tasks.ValueTask[int]](async () => { await System.Threading.Tasks.Task.Yield(); 7 });
Console.WriteLine(made().Result)
''')
    run([runtime, compiler, work / 'early/main.n', work / 'early/config.n', work / 'early/broken.n', '-source-root:' + str(work / 'early'),
         '-out:' + str(work / 'early.exe'), '-no-color', *modern_references])
    shutil.copy2(compiler.with_name('ncc.runtimeconfig.json'), work / 'early.runtimeconfig.json')
    got = run([runtime, work / 'early.exe']).stdout.strip()
    if got != '''config sees loaded
loaded
True loaded True
loaded
loaded!
broken failed broken failed
7''':
        raise RuntimeError('async files called early: got\n' + got)
    # top-level state: the inference pass sees the values a `$"..."' string names (they are its locals there too),
    # and an initializer typed on its own (the pass could not settle it) has its overloads resolved before its types
    # are fixed (`x == null' with == overloaded)
    source('dollar/main.n', '''using System;
using System.Reflection;
mutable m = null;
def property = typeof(string).GetProperty("Length");
def noField = typeof(string).GetField("x") == null;
Console.WriteLine($"$m $(property.Name) $noField");
m = "set";
def field = typeof(main).GetField("m", BindingFlags.NonPublic | BindingFlags.Static);
Console.WriteLine(field.FieldType.Name)
''')
    source('dollar/other.n', '''public One() : int { 1 }
''')
    run([runtime, compiler, work / 'dollar/main.n', work / 'dollar/other.n', '-source-root:' + str(work / 'dollar'),
         '-out:' + str(work / 'dollar.exe'), '-no-color', *modern_references])
    shutil.copy2(compiler.with_name('ncc.runtimeconfig.json'), work / 'dollar.runtimeconfig.json')
    got = run([runtime, work / 'dollar.exe']).stdout.strip()
    if got != '''Length True
String''':
        raise RuntimeError('top-level state named in a $ string: got\n' + got)
    source('async/iterators.n', '''using System;
using System.Collections.Generic;
using System.Linq;

// an iterator local function and an iterator lambda, in an ordinary function
Evens(limit : int) : list[int]
{
  def evens(from : int) : IEnumerable[int]
  {
    for (mutable i = from; i <= limit; i += 2) yield i   // `limit' is the enclosing function's
  }
  def squares = fun (xs : list[int]) : IEnumerable[int] { foreach (x in xs) yield x * x };
  $[x | x in evens(0).Concat(squares([3, 4]))]
}

// lazily: nothing runs until it is enumerated, and each enumeration runs afresh
mutable started = 0;
def counter = fun () : IEnumerable[int] { started++; yield 1; yield 2 };
def c = counter();
Console.WriteLine($"$started $(c.Count()) $(c.Count()) $started");
Console.WriteLine(Evens(6));
// an iterator in an iterator method
Pairs() : IEnumerable[string]
{
  def inner(n : int) : IEnumerable[string] { yield $"$n-a"; yield $"$n-b" }
  foreach (n in [1, 2]) foreach (s in inner(n)) yield s
}
Console.WriteLine($[s | s in Pairs()])
''')
    run([runtime, compiler, work / 'async/iterators.n', '-source-root:' + str(work / 'async'), '-out:' + str(work / 'async-iterators.exe'), '-no-color', *modern_references])
    shutil.copy2(compiler.with_name('ncc.runtimeconfig.json'), work / 'async-iterators.runtimeconfig.json')
    got = run([runtime, work / 'async-iterators.exe']).stdout.strip()
    if got != '''0 2 2 2
[0, 2, 4, 6, 9, 16]
[1-a, 1-b, 2-a, 2-b]''':
        raise RuntimeError('async iterators: got\n' + got)
    source('async/handlers.n', '''using System;
using System.Threading.Tasks;
class Button { public event Click : EventHandler; public Press() : void { Click(this, EventArgs.Empty) } }
def b = Button();
mutable clicked = 0;
b.Click += async (_, _) => { await Task.Delay(1); clicked++ };
def act : Action = async () => { await Task.Delay(1); clicked++ };
b.Press(); act();
System.Threading.Thread.Sleep(300);
Console.WriteLine(clicked);
def viaRun = Task.Run(async () => { await Task.Delay(1); clicked += 10 });
viaRun.Wait();
Console.WriteLine(clicked)
''')
    run([runtime, compiler, work / 'async/handlers.n', '-source-root:' + str(work / 'async'), '-out:' + str(work / 'async-handlers.exe'), '-no-color', *modern_references])
    shutil.copy2(compiler.with_name('ncc.runtimeconfig.json'), work / 'async-handlers.runtimeconfig.json')
    got = run([runtime, work / 'async-handlers.exe']).stdout.strip()
    if got != '''2
12''':
        raise RuntimeError('async handlers: got\n' + got)
    print('PASS: async functions and await (in loops, expressions, try/catch/finally and handlers, ValueTask, void, '
          'cancellation), async lambdas and local functions (async void ones as event handlers), iterator lambdas, await '
          'foreach and await using, async streams, top-level '
          'await and async files in import order; and their rules as errors', flush=True)

# what a macro declares at the top level is the file's state, as if written there: the file's functions see it;
# `top name' reaches the file's top level past a closer name, and `top' stays an ordinary name otherwise
source('macros/gen.n', '''using Nemerle.Compiler;
macro counter(name) { <[ mutable $name = 0 ]> }
macro bump(name) { <[ $name += 1 ]> }
macro pairOf(a, b, x, y) { <[ def ($a, $b) = ($x, $y) ]> }''')
run([runtime, compiler, work / 'macros/gen.n', '-source-root:' + str(work / 'macros'), '-target:library',
     '-out:' + str(work / 'gen.dll'), '-no-color', *modern_references, '-r:' + str(compiler.with_name('Nemerle.Compiler.dll'))])
source('macros/main.n', '''using gen;
counter(hits);
bump(hits);
bump(hits);
pairOf(w, h, 3, 4);
Hits() : int { hits }
Area() : int { w * h }
Shadowed(hits : int) : int { hits + top hits }
Local() : int { def Area() { 1 }; Area() + top Area() }
Named() : int { def top = 40; top + 2 }
System.Console.WriteLine($"$(Hits()) $(Area()) $(Shadowed(10)) $(Local()) $(Named())");''')
run([runtime, compiler, work / 'macros/main.n', '-source-root:' + str(work / 'macros'), '-out:' + str(work / 'macros.exe'), '-no-color',
     *modern_references, '-r:' + str(work / 'gen.dll')])
if runtime != 'mono': shutil.copy2(compiler.with_name('ncc.runtimeconfig.json'), work / 'macros.runtimeconfig.json')
shutil.copy2(work / 'gen.dll', work / 'macros' / 'gen.dll')
ran = run([runtime, work / 'macros.exe'])
if ran.stdout.split() != ['2', '12', '12', '13', '42']:
    raise RuntimeError('macro declarations as state, top name: ' + ran.stdout)
print('PASS: a macro\'s top-level declarations are the file\'s state; `top name` reaches the top level past a closer name', flush=True)

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
