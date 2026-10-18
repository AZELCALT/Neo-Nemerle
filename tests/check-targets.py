#!/usr/bin/env python3
"""Check target frameworks: output for .NET Standard, an older .NET and .NET Framework (Mono), from projects.

Usage: check-targets.py --toolchain <stage with the ncc launcher>

Needs the reference assemblies of each target (fetched by `ncc build` into its cache, so the first run needs the
network); a part whose reference assemblies cannot be fetched, or whose runtime is not installed (Mono for net48,
.NET 8 for net8.0), is skipped and says so."""
import argparse, os, pathlib, shutil, subprocess, tempfile

p = argparse.ArgumentParser()
p.add_argument('--toolchain', type=pathlib.Path, required=True)
a = p.parse_args()
tc = a.toolchain.resolve()
ncc = [str(tc / 'ncc')] if os.name != 'nt' else ['dotnet', str(tc / 'ncc.exe'), '-target-references:' + str(tc / 'references')]
work = pathlib.Path(tempfile.mkdtemp(prefix='nemerle-targets-'))
checks = 0

def check(ok, message):
    global checks
    if not ok: raise SystemExit('FAIL: ' + message)
    checks += 1

def run(*args, ok=True):
    r = subprocess.run(ncc + [str(x) for x in args], cwd=work, capture_output=True, text=True)
    out = r.stdout + r.stderr
    if ok and r.returncode != 0: raise SystemExit('FAIL: ncc %s\n%s' % (' '.join(map(str, args)), out))
    if not ok and r.returncode == 0: raise SystemExit('FAIL: ncc %s should fail\n%s' % (' '.join(map(str, args)), out))
    return out

def project(name, settings, files):
    d = work / name; d.mkdir()
    (d / (name + '.nproj')).write_text('name = "%s"\n%s' % (name, settings))
    for f, text in files.items(): (d / f).write_text(text)
    return d

def unreachable(out): return 'could not fetch' in out

try:
    if not (tc / 'netstandard2.0/Nemerle.dll').exists():
        print('SKIP: this toolchain has no netstandard2.0/Nemerle.dll (built offline)'); raise SystemExit(0)
    # 1. a .NET Standard 2.0 library, used by a program for the compiler's own .NET
    lib = project('shapes', 'kind = "library"\ntarget = "netstandard2.0"\n',
                  {'shapes.n': 'public Area(w : int, h : int) : int { w * h }\npublic Names() : list[string] { ["square", "strip"] }\n'})
    out = subprocess.run(ncc + ['build', str(lib)], cwd=work, capture_output=True, text=True)
    if out.returncode != 0 and unreachable(out.stdout + out.stderr):
        print('SKIP: the reference assemblies cannot be fetched (offline)'); raise SystemExit(0)
    check(out.returncode == 0, 'netstandard2.0 library: ' + out.stdout + out.stderr)
    app = project('app', '[references]\nprojects = ["../shapes"]\n',
                  {'main.n': 'using shapes;\nSystem.Console.WriteLine(Area(6, 7));\nSystem.Console.WriteLine(Names());\n'})
    out = run('run', app)
    check('42' in out and '[square, strip]' in out, 'a .NET 10 program uses the netstandard2.0 library: ' + out)
    print('PASS: a netstandard2.0 library, used from the compiler\'s .NET')

    # 2. the target's API is checked; .NET Standard has libraries only
    bad = project('bad', 'kind = "library"\ntarget = "netstandard2.0"\n[compiler]\noptions = ["-debug+"]\n',
                  {'bad.n': 'public Has(s : string) : bool\n{\n  s.Contains(\'x\')\n}\n'})
    out = run('build', bad, ok=False)
    check('System.String.Contains(System.Char) is not in netstandard2.0' in out and 'bad.n:3' in out, 'a member the target lacks, at its line: ' + out)
    check(not (bad / 'out/bad.dll').exists(), 'no binary for it')
    exe = project('exe', 'target = "netstandard2.1"\n', {'main.n': 'System.Console.WriteLine(1);\n'})
    check('has libraries only' in run('build', exe, ok=False), '.NET Standard has no programs')
    old = project('old', 'target = "net48"\n[references]\nprojects = ["../app"]\n', {'main.n': '()\n'})
    check('is a program' in run('build', old, ok=False), 'a program is not used as a library')
    mixed = project('mixed', 'target = "net48"\n[references]\nprojects = ["../plain"]\n', {'main.n': '()\n'})
    project('plain', 'kind = "library"\n', {'plain.n': 'public One() : int { 1 }\n'})
    check('cannot load' in run('build', mixed, ok=False), 'a net48 program cannot use a library for the compiler\'s .NET')
    check('unknown target framework' in run('build', project('typo', 'target = "net4.8"\n', {'main.n': '()\n'}), ok=False), 'an unknown target')
    print('PASS: the target\'s API is checked (with lines), .NET Standard has libraries only, used projects must fit')

    # 3. .NET Framework 4.8, run on Mono
    fx = project('fx', 'target = "net48"\n[references]\nprojects = ["../shapes"]\n',
                 {'main.n': 'using shapes;\ndef xs = [3, 1, 2].Sort(_ - _);\nSystem.Console.WriteLine($"$xs $(Area(2, 21))");\n'
                            'def o : option[int] = Some(1);\nmatch (o) { | Some(n) => System.Console.WriteLine(n + 1) | None => () }\n'})
    run('build', fx)
    check(not (fx / 'out/fx.runtimeconfig.json').exists(), 'a .NET Framework program has no runtimeconfig')
    if shutil.which('mono'):
        out = subprocess.run(['mono', str(fx / 'out/fx.exe')], capture_output=True, text=True)
        check(out.stdout.split() == ['[1,', '2,', '3]', '42', '2'], 'net48 on Mono: ' + out.stdout + out.stderr)
        print('PASS: a net48 program with the standard library and a netstandard2.0 library runs on Mono')
    else:
        print('SKIP: no mono to run the net48 program')

    # 4. an older .NET
    n8 = project('n8', 'target = "net8.0"\n', {'main.n': 'System.Console.WriteLine("on .NET 8");\n'})
    run('build', n8)
    config = (n8 / 'out/n8.runtimeconfig.json').read_text()
    check('"net8.0"' in config and '"8.0.0"' in config, 'the net8.0 runtimeconfig: ' + config)
    core = project('core31', 'target = "netcoreapp3.1"\n', {'main.n': 'System.Console.WriteLine("on .NET Core 3.1");\n'})
    run('build', core)
    config = (core / 'out/core31.runtimeconfig.json').read_text()
    check('"netcoreapp3.1"' in config and '"3.1.0"' in config, 'the netcoreapp3.1 runtimeconfig: ' + config)
    runtimes = subprocess.run(['dotnet', '--list-runtimes'], capture_output=True, text=True).stdout
    if 'Microsoft.NETCore.App 8.' in runtimes:
        out = subprocess.run(['dotnet', str(n8 / 'out/n8.exe')], capture_output=True, text=True).stdout
        check('on .NET 8' in out, 'runs on .NET 8: ' + out)
        print('PASS: a net8.0 program runs on .NET 8')
    else:
        print('PASS: a net8.0 program names .NET 8 (SKIP running it: no .NET 8 runtime installed)')
    print('PASS: %d target checks' % checks)
finally:
    shutil.rmtree(work, ignore_errors=True)
