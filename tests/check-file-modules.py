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
