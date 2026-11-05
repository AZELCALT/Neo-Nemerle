#!/usr/bin/env python3
"""C#'s cast `(T)x' (the conversion `x :> T'), each case as a file, as a script and with `#pragma indent': what it
converts, what binds tighter than it (`(double)7 / 2', `(int)s.Length', `(a) - b' subtracts, `(f)(x)' calls), the
types it names (built-in, qualified, generic, array and multi-dimensional array, user, interface, type parameter, enum),
user-defined conversions, a value of several types, and that it checks at run time (`(byte)300', a bad unbox).

    check-casts.py --toolchain DIR --references REFS"""
import argparse, pathlib, shutil, subprocess, sys, tempfile

p = argparse.ArgumentParser()
p.add_argument('--toolchain', type=pathlib.Path, required=True)
p.add_argument('--references', type=pathlib.Path, required=True)
a = p.parse_args()
T = a.toolchain.resolve(); R = a.references.resolve()
work = pathlib.Path(tempfile.mkdtemp(prefix='nemerle-casts-'))
W = 'System.Console.WriteLine'
YES = 'System.Environment.GetCommandLineArgs().Length > 0'   # true, as the compiler cannot know
# (name, code, what it prints, `THROWS:<exception>' or `ERROR:<start of the message>')
cases = [
 ('trunc',        f'{W}((int)3.7)', '3'),
 ('neg-trunc',    f'{W}((int)-3.9)', '-3'),
 ('prec-div',     f'{W}((double)7 / 2)', '3.5'),
 ('unary-minus',  f'def x = 5; {W}((int)-x)', '-5'),
 ('paren-minus',  f'def a = 10; def b = 3; {W}((a) - b)', '7'),
 ('paren-plus',   f'def a = 10; def b = 3; {W}((a) + b)', '13'),
 ('to-object',    f'{W}((object)"s")', 's'),
 ('unbox-string', f'def o : object = "hi"; {W}((string)o)', 'hi'),
 ('unbox-int',    f'def o : object = 42; {W}((int)o + 1)', '43'),
 ('widen-add',    f'{W}((long)int.MaxValue + 1)', '2147483648'),
 ('checked-byte', f'def n = 300; {W}((byte)n)', 'THROWS:OverflowException'),
 ('member-prec',  f'def s = "abc"; {W}((double)s.Length / 2)', '1.5'),
 ('call-prec',    f'{W}((int)System.Math.Round(2.6))', '3'),
 ('generic',      f'def o : object = System.Collections.Generic.List.[int](); {W}(((System.Collections.Generic.List[int])o).Count)', '0'),
 ('chain',        f'{W}((int)(double)5)', '5'),
 ('paren-operand',f'{W}((int)(3.9))', '3'),
 ('arg',          f'F(n : int) : int {{ n * 2 }}\ndef d = 4.2; {W}(F((int)d))', '8'),
 ('tilde',        f'{W}((int)~5)', '-6'),
 ('not',          f'def b = false; {W}((bool)!b)', 'True'),
 ('value-call',   f'def f = n => n + 1; {W}((f)(2))', '3'),
 ('qualified',    f'{W}((System.Int64)3 + 1)', '4'),
 ('char-to-int',  f"{W}((int)'A')", '65'),
 ('int-to-char',  f'{W}((char)66)', 'B'),
 ('to-enum',      f'{W}((System.DayOfWeek)1)', 'Monday'),
 ('from-enum',    f'{W}((int)System.DayOfWeek.Friday)', '5'),
 ('interp',       f'{W}($"v=$((int)2.5)")', 'v=2'),
 ('dollar',       f'def s = (string)$"a$(1)"; {W}(s)', 'a1'),
 ('bad-cast',     f'def o : object = "x"; {W}((int)o)', 'THROWS:InvalidCastException'),
 ('no-conv',      f'{W}((int)"5")', 'ERROR:'),
 ('in-match',     f'def o : object = 7; {W}(match ((int)o) {{ | 7 => "seven" | _ => "?" }})', 'seven'),
 ('return',       f'G(d : double) : int {{ (int)d }}\n{W}(G(9.9))', '9'),
 ('lambda',       f'def h = (d : double) => (int)d; {W}(h(2.2))', '2'),
 ('nested-neg',   f'{W}(-(int)2.5)', '-2'),
 ('mul-prec',     f'{W}((int)2.5 * 2)', '4'),
 ('decimal-op',   f'{W}((decimal)3.5 + 1)', '4.5'),
 ('from-decimal', f'{W}((int)3.99m)', '3'),
 ('interface',    f'def o : object = System.IO.MemoryStream(); {W}(((System.IDisposable)o) != null)', 'True'),
 ('to-array',     f'def o : object = array[1, 2, 3]; {W}(((array[int])o).Length)', '3'),
 ('to-array-2d', f'def o : object = array.[2][[1, 2], [3, 4]]; {W}(((array.[2][int])o)[1, 0])', '3'),
 ('to-list-of-array', f'def o : object = [array["a"]]; {W}(((list[array[string]])o).Head[0])', 'a'),
 ('to-list',      f'def o : object = [4, 5]; {W}(((list[int])o).Head)', '4'),
 ('user-class',   f'public class A {{ public V : int = 7 }}\ndef o : object = A(); {W}(((A)o).V)', '7'),
 ('type-param',   f'Get[T](o : object) : T {{ (T)o }}\n{W}(Get.[int](5) + 1)', '6'),
 ('flow-value',   f'mutable v = 1;\nwhen (System.Environment.GetCommandLineArgs().Length > 0) v = 2.5;\n{W}((int)v)', '2'),   # fits each type
 ('flow-checked', f'mutable v = 1;\nwhen (System.Environment.GetCommandLineArgs().Length > 0) v = 2.5;\n{W}(match (v) {{ | d is double => (int)d | i is int => i }})', '2'),
]


def outcome(text, built):
    errors = [l.split('error:', 1)[1].strip() for l in text.splitlines() if 'error:' in l]
    return 'ERROR:' + (errors[0] if errors else '?') if errors or not built else None


def thrown(text):
    return 'THROWS:' + next((l.split(':')[0].split('.')[-1] for l in text.splitlines() if 'Exception' in l), '?')


def run(mode, name, code):
    d = work / mode / name
    d.mkdir(parents=True)
    if mode == 'script':
        (d / 'm.ns').write_text(code + '\n')
        r = subprocess.run(['dotnet', str(T / 'nscript.exe'), 'run', 'm.ns', '--no-cache'], cwd=d, capture_output=True, text=True, timeout=120)
        return outcome(r.stdout + r.stderr, True) or (thrown(r.stdout + r.stderr) if r.returncode else r.stdout.strip())
    (d / 'm.n').write_text(code + '\n')
    r = subprocess.run(['dotnet', str(T / 'ncc.exe'), '-target-references:' + str(R), 'm.n', '-out:m.exe', '-no-color'],
                       cwd=d, capture_output=True, text=True)
    failed = outcome(r.stdout + r.stderr, (d / 'm.exe').exists())
    if failed: return failed
    shutil.copy2(T / 'Nemerle.dll', d); shutil.copy2(T / 'ncc.runtimeconfig.json', d / 'm.runtimeconfig.json')
    x = subprocess.run(['dotnet', 'm.exe'], cwd=d, capture_output=True, text=True, timeout=60)
    return thrown(x.stderr) if x.returncode else x.stdout.strip()


def fits(got, expected):
    if expected.endswith(':'): return got.startswith(expected)
    if expected.startswith('THROWS:'): return got.startswith('THROWS:') and got.split(':')[1] == expected.split(':')[1]
    return got == expected


failures, count, runs = [], 0, []
for mode in ('file', 'script', 'indent'):
    for name, code, expected in cases:
        if mode == 'indent':
            if '{' in code: continue   # (a braced body has a layout of its own)
            code = '#pragma indent\n' + code.replace('; ', '\n')
        runs.append((mode, name, code, expected))
# (each run in a folder of its own: several at once, reported in order)
import concurrent.futures, os
with concurrent.futures.ThreadPoolExecutor(max_workers=int(os.environ.get('NEMERLE_TEST_JOBS', max(2, (os.cpu_count() or 2) // 4)))) as pool:
    results = list(pool.map(lambda r: run(r[0], r[1], r[2]), runs))
for (mode, name, _, expected), got in zip(runs, results):
    count += 1
    if not fits(got, expected):
        failures.append('%s [%s]: expected %s, got %s' % (name, mode, expected, got))
if failures:
    print('FAILED:\n' + '\n'.join(failures)); sys.exit(1)
shutil.rmtree(work, ignore_errors=True)
print('PASS: %d casts (as files, scripts and with #pragma indent) convert, bind and check as C#\'s do' % count)
