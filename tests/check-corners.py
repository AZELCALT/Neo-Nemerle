#!/usr/bin/env python3
"""The corners where features meet: small programs that combine them (the flow of values with closures, match, loops
and async; `content' with generics and overloads; `[...]' with overloads, `params', extensions and casts; file and
folder modules with their top-level state; spaces with scopes, dials and declarations), each compiled and run in
every mode that must agree with the others: a file, a script (one file), `-parallel', and `-incremental' (the second
compile of an unchanged program reuses the first).

    check-corners.py --toolchain DIR --references REFS [--only NAME]"""
import argparse, pathlib, shutil, subprocess, sys, tempfile

p = argparse.ArgumentParser()
p.add_argument('--toolchain', type=pathlib.Path, required=True)
p.add_argument('--references', type=pathlib.Path, required=True)
p.add_argument('--only', help='run the cases whose name has this')
a = p.parse_args()
T = a.toolchain.resolve(); R = a.references.resolve()
work = pathlib.Path(tempfile.mkdtemp(prefix='nemerle-corners-'))
W = 'System.Console.WriteLine'
YES = 'System.Environment.GetCommandLineArgs().Length > 0'   # true, as the compiler cannot know

# (name, {file: text}, what it prints, or `ERROR:<part of the first error>')
cases = [
    # ---- the flow of values, with what runs it later or again ----
    ('flow-closure-reads-latest', {'main.n': f'''
mutable x = 1;
def show() {{ {W}(x) }}
x = 2;
show();
when ({YES}) x = "three";
show()
'''}, 'ERROR:`x\' is int or string'),   # (code that runs at any time checks a top-level value of several types)
    ('flow-closure-checks-latest', {'main.n': f'''
mutable x = 1;
def show() {{ match (x) {{ | n is int => {W}(n) | s is string => {W}(s) }} }}
x = 2;
show();
when ({YES}) x = "three";
show()
'''}, '2\nthree'),
    ('flow-loop-grows-set', {'main.n': f'''
Run() : void
{{
  mutable v = 0;
  foreach (i in [1, 2, 3]) when (i == 2) v = "two";
  match (v) {{ | s is string => {W}("string " + s) | n is int => {W}("int " + n.ToString()) }}
}}
Run()
'''}, 'string two'),
    ('flow-match-arms-assign', {'main.n': f'''
Run(k : int) : void
{{
  mutable v = 1;
  match (k) {{ | 0 => v = 2.5 | 1 => v = "one" | _ => () }}
  {W}(v)
}}
Run(0); Run(1); Run(7)
'''}, '2.5\none\n1'),
    ('flow-if-without-else', {'main.n': f'''
Run(c : bool) : void
{{
  mutable v = 10;
  if (c) v = "ten";
  {W}(match (v) {{ | n is int => n + 1 | s is string => s.Length }})
}}
Run(true); Run(false)
'''}, '3\n11'),
    ('flow-while-condition-narrows', {'main.n': f'''
Run() : void
{{
  mutable v = 3;
  when ({YES}) v = "go";
  while (v is string) v = 0;
  {W}(v)
}}
Run()
'''}, '0'),
    ('flow-lambda-captures-set', {'main.n': f'''
Run() : void
{{
  mutable v = 1;
  def f = () => match (v) {{ | n is int => "int " + n.ToString() | s is string => "string " + s }};
  {W}(f());
  v = "now";
  {W}(f())
}}
Run()
'''}, 'int 1\nstring now'),
    ('flow-async-await-between', {'main.n': f'''
using System.Threading.Tasks;
async Twice(n : int) : Task[int] {{ await Task.Yield(); n * 2 }}
async Run() : Task
{{
  mutable v = await Twice(4);
  {W}(v + 1);
  v = "after";
  await Task.Yield();
  {W}(v)
}}
Run().Wait()
'''}, '9\nafter'),
    ('flow-top-level-function-checks', {'main.n': f'''
mutable state = 1;
Describe() : string {{ match (state) {{ | n is int => "n=" + n.ToString() | s is string => "s=" + s }} }}
{W}(Describe());
when ({YES}) state = "x";
{W}(Describe())
'''}, 'n=1\ns=x'),
    ('flow-use-not-fitting-is-error', {'main.n': f'''
Run() : void
{{
  mutable v = 1;
  when ({YES}) v = "s";
  {W}(v * 2)
}}
Run()
'''}, 'ERROR:this does not fit `v\' when it is string'),
    ('flow-redefined-def', {'main.n': f'''
def a = 1;
def b = a + 1;
def a = "now a string";
{W}(b);
{W}(a.Length)
'''}, '2\n12'),

    # ---- content ----
    ('content-generic-passthrough', {'main.n': f'''
Keep[T](x : T) : T {{ x }}
Show(c : content) : string {{ match (c) {{ | n is int => "int" | s is string => "string" | _ => "other" }} }}
mutable v = 1;
when ({YES}) v = "s";
def held : content = v;
{W}(Show(Keep(held)))
'''}, 'string'),
    ('generic-of-flow-value-differs', {'main.n': f'''
Keep[T](x : T) : T {{ x }}
mutable v = 1;
when ({YES}) v = "s";
{W}(Keep(v))
'''}, 'ERROR:this gives another type for each type of `v\''),
    ('content-in-lambda-result', {'main.n': f'''
def pick = (b : bool) => if (b) 1 else "one";
Show(c : content) : string {{ match (c) {{ | n is int => "int " + n.ToString() | s is string => s }} }}
{W}(Show(pick(true)));
{W}(Show(pick(false)))
'''}, 'int 1\none'),
    ('content-overload-vs-object', {'main.n': f'''
Take(o : object) : string {{ "object " + o.ToString() }}
Take(c : content) : string {{ "content " + c.Type.Name }}
mutable v = 1;
when ({YES}) v = "two";
{W}(Take(v));
{W}(Take(3))
'''}, 'object two\nobject 3'),   # (with several methods, a value is taken as it is: `content' holds it when it is the one)
    ('content-no-cast-even-from-content', {'main.n': f'''
Pick(b : bool) : content {{ if (b) 1 else "one" }}
def c = Pick(true);
def d = c :> content;
{W}(d)
'''}, '1'),   # (a content cast to content is itself)

    # ---- the structural [...] literal ----
    ('list-overload-prefers-list', {'main.n': f'''
F(xs : list[int]) : string {{ "list " + xs.Length.ToString() }}
F(xs : array[int]) : string {{ "array " + xs.Length.ToString() }}
{W}(F([1, 2, 3]))
'''}, 'list 3'),
    ('list-to-params', {'main.n': f'''
Sum(params xs : array[int]) : int {{ mutable t = 0; foreach (x in xs) t += x; t }}
{W}(Sum([1, 2, 3]));
{W}(Sum(4, 5))
'''}, '6\n9'),
    ('list-to-generic-collection', {'main.n': f'''
using System.Collections.Generic;
Count[T](xs : HashSet[T]) : int {{ xs.Count }}
{W}(Count.[int]([1, 2, 2, 3]))
'''}, '3'),
    ('list-to-span-and-back', {'main.n': f'''
Total(xs : System.ReadOnlySpan[int]) : int {{ mutable t = 0; foreach (x in xs) t += x; t }}
{W}(Total([10, 20, 12]))
'''}, '42'),
    ('list-cast-to-array', {'main.n': f'''
def a = ([3, 4] :> array[int]);
{W}(a.Length + a[1])
'''}, '6'),
    ('list-statement-start-iter', {'main.n': f'''
mutable n = 0;
[1, 2, 3].Iter(x => n += x);
{W}(n)
'''}, '6'),
    ('list-extension-on-array-target', {'main.n': f'''
Last(this xs : array[int]) : int {{ xs[xs.Length - 1] }}
def a : array[int] = [7, 8, 9];
{W}(a.:Last())
'''}, '9'),

    # ---- casts ----
    ('cast-of-flow-value', {'main.n': f'''
Run() : void
{{
  mutable v = 1;
  when ({YES}) v = 2.75;
  {W}((int)v)
}}
Run()
'''}, '2'),
    ('cast-array-type-paren', {'main.n': f'''
def o : object = array[1, 2, 3];
{W}(((array[int])o).Length)
'''}, '3'),
    ('cast-precedence-with-member', {'main.n': f'''
def o : object = "text";
{W}(((string)o).Length);
{W}((double)7 / 2)
'''}, '4\n3.5'),

    # ---- modules ----
    ('module-top-level-state-once', {'counter.n': f'''
public mutable Count : int = 0;
{W}("counter ready");
public Next() : int {{ Count++; Count }}
''', 'main.n': f'''
using counter;
{W}(Next());
{W}(Next() + counter.Count)
'''}, 'counter ready\n1\n4'),
    ('module-folder-hidden', {'a.n': '''
public Hello() : string { "a " + Shared() }
hidden Shared() : string { "shared" }
''', 'a/b.n': '''
public Hello() : string { "b " + a.Shared() }
''', 'main.n': f'''
using a;
{W}(Hello());
{W}(b.Hello())
'''}, 'a shared\nb shared'),
    ('module-register-and-extension', {'impl/words.n': '''
register text;
public Shout(this s : string) : string { s.ToUpper() + "!" }
''', 'main.n': f'''
using text.words;
{W}("hi".:Shout())
'''}, 'HI!'),
    ('module-mask-overloads', {'geo.n': '''
public mask circle { public Area(r : double) : double { 3.0 * r * r } }
public mask square { public Area(s : double) : double { s * s } }
''', 'main.n': f'''
using geo;
{W}(geo.circle.Area(1.0) + geo.square.Area(2.0))
'''}, '7'),
    ('module-top-level-flow-read-by-other-file', {'state.n': f'''
public mutable Mode = 1;
when ({YES}) Mode = "on";
''', 'main.n': f'''
using state;
{W}(match (state.Mode) {{ | s is string => s | n is int => n.ToString() }})
'''}, 'on'),   # (another file reads a file's value in full: `state.Mode')
    ('module-top-level-flow-needs-check', {'state.n': f'''
public mutable Mode = 1;
when ({YES}) Mode = "on";
''', 'main.n': f'''
using state;
def m : string = state.Mode;
{W}(m)
'''}, 'ERROR:expected string, got content'),

    # ---- spaces ----
    ('space-scope-and-dial-same-file', {'main.n': '''
scope A;
grammar G
{
  using Nemerle.Compiler.NitraDialectServices;
  using Nemerle.Compiler.Parsetree;
  syntax module M
  {
    using Nitra.Core;
    [StartRule] syntax Start = "double"
    {
      map (context : NitraDialectContext) PExpr = { def s = context.Scope("A"); s.Write("out", <[ $(s.Read("in")) * 2 ]>) };
    }
  }
}
scope.A.registery("in", type("int"));
scope.A.registery("out", type("int"));
scope.A.in = 21;
space G [A] { double }
System.Console.WriteLine(scope.A.out)
'''}, '42'),
    ('space-indented-with-quotes', {'main.n': '''#pragma indent
grammar Q
{
  using Nemerle.Compiler.Parsetree;
  syntax module M
  {
    using Nitra.Core;
    regex Quoted = "'" ("''" | (Any - '\\''))* "'";
    [StartRule] syntax Start = "say" Value=Quoted { map PExpr = { def q = GetText(this.Value); <[ System.Console.WriteLine($(q.Substring(1, q.Length - 2) : string)) ]> }; }
  }
}
space Q:
  say 'it''s { here }'
System.Console.WriteLine("after")
'''}, "it''s { here }\nafter"),
    ('space-declares-and-is-used-later', {'main.n': '''
grammar D
{
  using Nemerle.Compiler.Parsetree;
  syntax module M
  {
    using Nitra.Core;
    regex Digits = ['0'..'9']+;
    [StartRule] syntax Start = "answer" Value=Digits
    {
      map PExpr = <[ { $(PExpr.Quoted(SyntaxElement.ClassMember(<[ decl: public static Answer() : int { $(int.Parse(GetText(this.Value)) : int) } ]>))); () } ]>;
    }
  }
}
System.Console.WriteLine(Answer() + 1);
space D { answer 41 }
System.Console.WriteLine(main.Answer())
'''}, '42\n41'),

    # ---- a lambda or local function is a function: several types give a content ----
    ('lambda-several-types-matched', {'main.n': f'''
def pick = (b : bool) => if (b) 1 else "one";
match (pick(true)) {{ | n is int => {W}(n + 1) | s is string => {W}(s) }}
match (pick(false)) {{ | n is int => {W}(n + 1) | s is string => {W}(s) }}
'''}, '2\none'),
    ('local-function-several-types-recursive', {'main.n': f'''
Run() : void
{{
  def walk(n : int) {{ if (n == 0) "done" else if (n > 100) n else walk(n - 1) }}
  {W}(walk(3));
  {W}(walk(500))
}}
Run()
'''}, 'done\n500'),
    ('lambda-several-types-nested', {'main.n': f'''
def outer = (k : int) => {{ def inner = (b : bool) => if (b) k else "no"; inner(k > 1) }};
{W}(outer(5));
{W}(outer(0))
'''}, '5\nno'),
    ('lambda-one-type-stays', {'main.n': f'''
def twice = (x : int) => if (x > 0) x * 2 else 0;
{W}(twice(4) + 1)
'''}, '9'),
    ('lambda-declared-type-still-errors', {'main.n': f'''
def f = (b : bool) => {{ def v : int = if (b) 1 else "s"; v }};
{W}(f(true))
'''}, "ERROR:Cannot implicitly convert type 'string' to 'int'"),
    # ---- more meeting points ----
    ('async-match-if-without-else', {'main.n': f'''
using System.Threading.Tasks;
async Classify(n : int) : Task[string]
{{
  await Task.Yield();
  mutable label = "small";
  if (n > 10) label = "big";
  match (n % 2) {{ | 0 => label + " even" | _ => label + " odd" }}
}}
{W}(Classify(3).Result);
{W}(Classify(12).Result)
'''}, 'small odd\nbig even'),
    ('extension-generic-on-list-literal', {'main.n': f'''
Second[T](this xs : list[T]) : T {{ xs.Tail.Head }}
Twice[T](this xs : array[T]) : int {{ xs.Length * 2 }}
{W}([10, 20, 30].:Second());
def a : array[string] = ["x", "y"];
{W}(a.:Twice())
'''}, '20\n4'),
    ('extension-in-flow-check', {'main.n': f'''
Shout(this s : string) : string {{ s.ToUpper() }}
Run() : void
{{
  mutable v = 1;
  when ({YES}) v = "loud";
  match (v) {{ | s is string => {W}(s.:Shout()) | _ => () }}
}}
Run()
'''}, 'LOUD'),
    ('module-with-space-used-by-file', {'calc.n': '''
grammar C
{
  using Nemerle.Compiler.Parsetree;
  syntax module M
  {
    using Nitra.Core;
    regex Digits = ['0'..'9']+;
    [StartRule] syntax Start = "const" Value=Digits
    {
      map PExpr = <[ { $(PExpr.Quoted(SyntaxElement.ClassMember(<[ decl: public static Value() : int { $(int.Parse(GetText(this.Value)) : int) } ]>))); () } ]>;
    }
  }
}
space C { const 40 }
''', 'main.n': f'''
using calc;
{W}(calc.Value() + 2)
'''}, '42'),
    ('incremental-edit-in-body', {'helper.n': '''
public Word() : string { "helper" }
''', 'main.n': f'''
using helper;
Label() : string {{ "EDIT " + Word() }}
{W}(Label())
'''}, 'EDIT helper'),
    ('nested-closure-in-loop-captures', {'main.n': f'''
mutable fs = [];
foreach (i in [1, 2, 3]) fs ::= () => i * 10;
{W}(fs.Map(f => f()).Rev())
'''}, '[10, 20, 30]'),
    ('match-guard-last-alternative', {'main.n': f'''
Kind(n : int) : string {{ | 1 | 2 when n > 100 => "never" | 1 | 2 => "small" | _ => "other" }}
{W}(Kind(1) + " " + Kind(2) + " " + Kind(3))
'''}, 'never small other'),   # (a guard is the last alternative's: `| 1 | 2 when g' is `| 1 | (2 when g)')
]


# what a case still waits on (it must still fail in some mode, so the list stays true)
KNOWN = {}


def outcome(text, built):
    errors = [l.split('error:', 1)[1].strip() for l in text.splitlines() if 'error:' in l]
    return 'ERROR:' + (errors[0] if errors else '?') if errors or not built else None


def compile_run(d, extra):
    exe = d / 'main.exe'
    if exe.exists(): exe.unlink()
    r = subprocess.run(['dotnet', str(T / 'ncc.exe'), '-target-references:' + str(R), 'main.n', '-out:main.exe', '-launcher-',
                        '-no-color', *extra], cwd=d, capture_output=True, text=True)
    failed = outcome(r.stdout + r.stderr, exe.exists())
    if failed: return failed
    shutil.copy2(T / 'Nemerle.dll', d); shutil.copy2(T / 'ncc.runtimeconfig.json', d / 'main.runtimeconfig.json')
    x = subprocess.run(['dotnet', 'main.exe'], cwd=d, capture_output=True, text=True, timeout=60)
    return ('THROWS:' + x.stderr.strip().splitlines()[0][:200]) if x.returncode else x.stdout.strip()


def place(mode, name, files):
    d = work / mode / name
    for path, text in files.items():
        f = d / path
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text.lstrip('\n'))
    return d


def fits(got, expected):
    return got.startswith(expected) if expected.startswith('ERROR:') else got == expected


def check(case):
    """A case in every mode (each in a folder of its own): its failures, and how many runs."""
    name, files, expected = case
    results = {}
    results['file'] = compile_run(place('file', name, files), [])
    results['parallel'] = compile_run(place('parallel', name, files), ['-parallel'])
    d = place('incremental', name, files)
    state = d / 'incremental-state'
    first = compile_run(d, ['-incremental:' + str(state)])
    results['incremental'] = compile_run(d, ['-incremental:' + str(state)]) if first == results['file'] else first
    # (an edit between two incremental compiles: a function's body, a string in it; the second gives the edited one)
    if 'EDIT' in files.get('main.n', ''):
        (d / 'main.n').write_text((d / 'main.n').read_text().replace('EDIT', 'EDITED'))
        edited = compile_run(d, ['-incremental:' + str(state)])
        results['incremental-edit'] = edited.replace('EDITED', 'EDIT') if 'EDITED' in edited else 'not the edited program: ' + edited
    if len(files) == 1:
        d = place('script', name, {'main.ns': files['main.n']})
        r = subprocess.run(['dotnet', str(T / 'nscript.exe'), 'run', 'main.ns', '--no-cache'], cwd=d, capture_output=True,
                           text=True, timeout=180)
        results['script'] = outcome(r.stdout + r.stderr, True) or (('THROWS:' + r.stderr.strip()[:200]) if r.returncode else r.stdout.strip())
    wrong = ['%s [%s]: expected %r, got %r' % (name, mode, expected, got[:400]) for mode, got in results.items() if not fits(got, expected)]
    if name in KNOWN:
        return (['%s passes now: take it off KNOWN (%s)' % (name, KNOWN[name])] if not wrong else []), len(results)
    return wrong, len(results)


# (the cases at once, their failures reported in order)
import concurrent.futures, os
failures, runs = [], 0
chosen = [c for c in cases if not a.only or a.only in c[0]]
with concurrent.futures.ThreadPoolExecutor(max_workers=int(os.environ.get('NEMERLE_TEST_JOBS', max(2, (os.cpu_count() or 2) // 4)))) as pool:
    for wrong, n in pool.map(check, chosen):
        failures.extend(wrong); runs += n
if failures:
    print('FAILED (%d of %d runs):\n' % (len(failures), runs) + '\n'.join(failures)); sys.exit(1)
shutil.rmtree(work, ignore_errors=True)
print('PASS: %d runs of %d corner cases agree as files, scripts, -parallel and -incremental (%d wait: %s)' % (runs, len(cases), len(KNOWN), ', '.join(KNOWN)))
