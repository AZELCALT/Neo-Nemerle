#!/usr/bin/env python3
"""Check `extend T { ... }`: what a file adds to the global type `T`.

Where `T` is compiled with the extension (one program, a script and its sources) the compiler gathers the parts into
the type, then builds and checks it whole: members, interfaces, errors as for one declaration. Where `T` is compiled
already (a host's type, extended by a script it loads), what the extension adds lives in the extension slot every
exported class has, made the first time it is asked for, so objects made before the extension have it too.
"""
import argparse
import pathlib
import shutil
import subprocess
import tempfile

p = argparse.ArgumentParser()
p.add_argument('--toolchain', type=pathlib.Path, required=True)
a = p.parse_args()
T = a.toolchain.resolve()
work = pathlib.Path(tempfile.mkdtemp(prefix='nemerle-extend-'))
print('Extend artifacts:', work, flush=True)
checks = 0

def files(d, sources):
    d.mkdir(parents=True)
    for name, text in sources.items():
        (d / name).parent.mkdir(parents=True, exist_ok=True)
        (d / name).write_text(text)
    return [str(d / name) for name in sources]

def compile(d, sources, *extra, library=False):
    paths = files(d, sources)
    out = d / ('lib.dll' if library else 'main.exe')
    r = subprocess.run([str(T / 'ncc'), *paths, '-source-root:' + str(d), '-out:' + str(out), '-no-color', *extra,
                        *(['-target:library'] if library else ['-launcher-'])], capture_output=True, text=True)
    return r.returncode == 0, r.stdout + r.stderr

def run(d, *references):
    for f in ('Nemerle.dll', *references): shutil.copy2(T / f if f == 'Nemerle.dll' else f, d / pathlib.Path(f).name)
    shutil.copy2(T / 'ncc.runtimeconfig.json', d / 'main.runtimeconfig.json')
    r = subprocess.run(['dotnet', str(d / 'main.exe')], capture_output=True, text=True, timeout=60, cwd=d)
    return (r.stdout + r.stderr).strip()

def check(ok, message):
    global checks
    if not ok: raise SystemExit('FAILED: ' + message)
    checks += 1

# 1. one compilation: the parts are gathered into the type, in either order of the files
shapes = ('export interface IDrawable { Draw() : string; }\n'
          'export class Pen\n{\n  public mutable Width : int = 3;\n  public Grow() : void { Width *= 2 }\n}\n'
          'export variant Shape { | Dot | Line { len : int } }\n'
          'export struct Point { public X : int; public this(x : int) { X = x } }\n')
style = ('using System.Text;\n'
         'extend Pen : IDrawable\n{\n  public mutable Color : string = "red";\n  private secret : int = 1;\n'
         '  public Label : string { get { $"$Color pen" } }\n'
         '  public Draw() : string { StringBuilder().Append($"$Label of $Width").Append(secret).ToString() }\n}\n'
         'extend Shape { public Size() : int { match (this) { | Dot => 0 | Line(n) => n } } }\n'
         'extend Point { public Twice() : int { X * 2 } }\n')
main = ('def p = Pen();\np.Grow();\np.Color = "blue";\ndef d : IDrawable = p;\n'
        'System.Console.WriteLine($"$(p.Draw()) $(d.Draw()) $(Shape.Line(4).Size()) $(Point(5).Twice())")\n')
for name, order in (('export-first', ['lib/shapes.n', 'style.n', 'main.n']), ('extension-first', ['style.n', 'main.n', 'lib/shapes.n'])):
    sources = {'lib/shapes.n': shapes, 'style.n': style, 'main.n': main}
    ok, log = compile(work / name, {k: sources[k] for k in order})
    check(ok, 'one compilation (%s)\n%s' % (name, log))
    out = run(work / name)
    check(out == 'blue pen of 61 blue pen of 61 4 10', 'one compilation (%s) printed %r' % (name, out))
print('PASS: an extension in the same compilation is part of the type (fields, properties, methods, an interface; '
      'a class, a variant, a struct; its file\'s usings; in either order of the files)', flush=True)

# 2. what is checked as for one declaration, and what an extension may not say
for name, text, says in [
        ('twice', 'extend Pen { public Grow() : void { } }\n', 'redefinition of method Pen.Grow()'),
        ('unknown', 'extend Brush { public X : int = 1; }\n', "no type `Brush' is exported"),
        ('base', 'public class Base { }\nextend Pen : lib.Base { }\n', 'an extension adds interfaces'),
]:
    ok, log = compile(work / ('error-' + name), {'lib.n': shapes, 'ext.n': text, 'main.n': '()\n'})
    check(not ok and says in log, '%s: expected %r\n%s' % (name, says, log))
print('PASS: an extension is checked with its type (a member defined twice, a type that is not exported, a base class)', flush=True)

# 3. a type compiled already: the extension slot holds what is added, for objects made before as after
host = ('export class Pen\n{\n  public mutable Width : int = 3;\n  public Grow() : void { Width *= 2 }\n'
        '  public override ToString() : string { $"pen $Width" }\n}\n'
        'export class Marker : Pen { }\n'
        'public Made() : list[Pen] { [Pen(), Pen()] }\n')
ok, log = compile(work / 'host', {'engine.n': host}, library=True)
check(ok, 'the host library\n' + log)
engine = str(work / 'host' / 'lib.dll')
late = {
    'styles.n': ('extend Pen\n{\n  public mutable Style : string = "plain";\n  public Uses : int { get { Width * 10 } }\n'
                 '  public Describe() : string { $"$Style, $(this.Width) wide, used $Uses" }\n}\n'),
    'tags.n': 'extend Pen { public mutable Tag : string = "none"; }\n',
    'main.n': ('def pens = engine.Made();\ndef p = pens.Head;\np.Grow();\np.Style = "bold";\np.Tag = "first";\n'
               'System.Console.WriteLine(p.Describe() + " " + p.Tag + " " + p);\n'
               'System.Console.WriteLine(pens.Tail.Head.Describe() + " " + pens.Tail.Head.Tag);\n'
               'def m = Marker();\nm.Style = "marker";\nSystem.Console.WriteLine(m.Describe());\n'),
}
ok, log = compile(work / 'late', late, '-r:' + engine)
check(ok and not [l for l in log.splitlines() if 'warning' in l and '.nproj' not in l], 'extending a compiled type\n' + log)
out = run(work / 'late', engine).splitlines()
check(out == ['bold, 6 wide, used 60 first pen 6', 'plain, 3 wide, used 30 none', 'marker, 3 wide, used 30'],
      'extending a compiled type printed %r' % out)
for name, text, says in [
        ('interface', 'extend Pen : System.IDisposable { public Dispose() : void { } }\n', 'an interface is added where'),
        ('existing', 'extend Pen { public Grow() : void { } }\n', "has `Grow' already"),
        ('static', 'extend Pen { public static Make() : Pen { Pen() } }\n', 'adds instance fields, properties and methods'),
]:
    ok, log = compile(work / ('late-' + name), {'main.n': text + '()\n'}, '-r:' + engine)
    check(not ok and says in log, 'a compiled type, %s: expected %r\n%s' % (name, says, log))
print('PASS: an extension of a compiled type (its slot): fields, properties and methods with `this` the object, the '
      'type\'s members by name, objects made before it, two extensions of one type, a derived type; and what it may not add', flush=True)

# 4. a host that embeds scripts: a script extends the host's type, and the host's object has what it adds
app = ('using Nemerle.Scripting.contracts;\nusing Nemerle.Scripting.host;\n'
       'def pen = Pen();\npen.Grow();\ndef host = ScriptHost();\ndef definition = ScriptDefinition();\n'
       'definition.Properties.Add("pen", typeof(Pen));\n'
       'definition.TargetReferenceDirectory = System.IO.Path.Combine(System.AppContext.BaseDirectory, "references");\n'
       'def source = "extend Pen\\n{\\n  public mutable Style : string = \\"plain\\";\\n  public Describe() : string { $\\"$Style pen, $Width wide\\" }\\n}\\n"\n'
       '           + "System.Console.WriteLine(pen.Describe());\\npen.Style = \\"bold\\";\\npen.Describe()\\n";\n'
       'def compiled = host.Compile(ScriptSource(source, "styles.n"), definition);\n'
       'if (!compiled.Success) foreach (d in compiled.Diagnostics) System.Console.WriteLine($"$(d.Line): $(d.Message)")\n'
       'else\n{\n  def inputs = ScriptInputs();\n  inputs.Properties.Add("pen", pen);\n'
       '  def result = host.Evaluate(compiled.Script, inputs);\n'
       '  System.Console.WriteLine(if (result.Error != null) result.Error.ToString() else result.Value)\n}\n')
d = work / 'embedded'
ok, log = compile(d, {'main.n': app}, '-r:' + engine, '-r:' + str(T / 'Nemerle.Scripting.dll'))
check(ok, 'the embedding host\n' + log)
for item in T.iterdir():
    if item.is_dir(): shutil.copytree(item, d / item.name, dirs_exist_ok=True)
    elif not (d / item.name).exists(): shutil.copy2(item, d / item.name)
out = run(d, engine).splitlines()
check(out == ['plain pen, 6 wide', 'bold pen, 6 wide'], 'a script extending its host\'s type printed %r' % out)
print('PASS: a script extends its host\'s type, and the host\'s object has what it adds', flush=True)
print('PASS: %d extend checks' % checks)
