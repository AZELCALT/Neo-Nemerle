#!/usr/bin/env python3
"""Check the project commands (`ncc init`, `build`, `run`, `clean`) and the .nproj file.

Usage: check-projects.py --toolchain <stage with the ncc launcher>

Covers: a program from `ncc init`, up-to-date builds and rebuilds after an edit, a library used by a program through
[references] projects, a plain assembly, a NuGet package from a local feed (offline, with a private package cache),
compiler options, a main file other than main.n, and the project file's errors at their line and column."""
import argparse, pathlib, os, shutil, subprocess, sys, tempfile, zipfile

p = argparse.ArgumentParser()
p.add_argument('--toolchain', type=pathlib.Path, required=True)
a = p.parse_args()
tc = a.toolchain.resolve()
ncc = [str(tc / 'ncc')] if os.name != 'nt' else ['dotnet', str(tc / 'ncc.exe'), '-target-references:' + str(tc / 'references')]
work = pathlib.Path(tempfile.mkdtemp(prefix='nemerle-projects-'))
env = dict(os.environ, XDG_DATA_HOME=str(work / 'data'), LOCALAPPDATA=str(work / 'data'))
checks = 0

def check(ok, message):
    global checks
    if not ok: raise SystemExit('FAIL: ' + message)
    checks += 1

def run(*args, cwd=work, ok=True):
    r = subprocess.run(ncc + [str(x) for x in args], cwd=cwd, env=env, capture_output=True, text=True)
    if ok and r.returncode != 0: raise SystemExit('FAIL: ncc %s\n%s%s' % (' '.join(map(str, args)), r.stdout, r.stderr))
    if not ok and r.returncode == 0: raise SystemExit('FAIL: ncc %s should fail\n%s' % (' '.join(map(str, args)), r.stdout))
    return r.stdout + r.stderr

def compile_library(name, text):
    source = work / (name + '.n'); source.write_text(text)
    out = work / (name + '.dll')
    subprocess.run(['dotnet', str(tc / 'ncc.exe'), '-target-references:' + str(tc / 'references'), '-source-root:' + str(work),
                    '-target:library', '-no-color', '-out:' + str(out), str(source)], check=True)
    return out

try:
    # 1. a program from `ncc init`
    out = run('init', 'hello')
    for f in ('hello.nproj', 'main.n', '.gitignore'): check((work / 'hello' / f).exists(), 'init writes ' + f)
    check('Next: cd hello && ncc run' in out, 'init says what to do next: ' + out)
    hello = work / 'hello'
    (hello / 'tool.ns').write_text('[assembly: DependsOn("nothing.dll")]\nthis is a script, not part of the project\n')
    check('Hello from hello!' in run('run', cwd=hello), 'the new program runs (a .ns script in its folder is not compiled)')
    check('hello: up to date' in run('run', cwd=hello), 'a second run does not rebuild')
    (hello / 'main.n').write_text('System.Console.WriteLine("edited");\n')
    out = run('run', cwd=hello)
    check('hello: built' in out and 'edited' in out, 'an edit rebuilds: ' + out)
    check('already a project' in run('init', 'hello', ok=False), 'init refuses an existing project')
    check((hello / 'out/Nemerle.dll').exists() and (hello / 'out/hello.runtimeconfig.json').exists(), 'the output runs on its own')
    out = subprocess.run(['dotnet', str(hello / 'out/hello.dll')], capture_output=True, text=True).stdout
    check(out.strip() == 'edited', 'dotnet out/hello.dll: ' + out)
    # the launcher (the .NET apphost) starts it directly: ./hello, hello.exe on Windows
    launcher = hello / ('out/hello.exe' if os.name == 'nt' else 'out/hello')
    check(launcher.exists(), 'a program has a launcher next to its .dll')
    out = subprocess.run([str(launcher)], capture_output=True, text=True).stdout
    check(out.strip() == 'edited', 'the launcher runs the program: ' + out)
    run('build', cwd=hello)
    check(launcher.stat().st_mtime > 0 and os.access(launcher, os.X_OK), 'the launcher is executable')
    run('clean', cwd=hello)
    check(not (hello / 'out').exists(), 'clean removes out/')
    print('PASS: init, run, up to date, rebuild after an edit, clean')

    # 2. a library used by a program; a plain assembly; a package from a local feed
    run('init', 'greet', '--lib')
    check((work / 'greet/greet.n').exists() and 'kind = "library"' in (work / 'greet/greet.nproj').read_text(), 'a library project')
    check('nothing to run' in run('run', work / 'greet', ok=False), 'a library is not run')
    run('init', 'app')
    app = work / 'app'
    (app / 'lib').mkdir()
    shutil.copy2(compile_library('engine', 'public Value() : int { 41 }\n'), app / 'lib/engine.dll')
    fixture = compile_library('fixture', 'public Answer() : int { 7 }\n')
    feed = work / 'feed'; feed.mkdir()
    with zipfile.ZipFile(feed / 'Fixture.1.0.0.nupkg', 'w') as z:
        z.writestr('Fixture.nuspec', '<?xml version="1.0"?><package><metadata><id>Fixture</id><version>1.0.0</version>'
                   '<authors>test</authors><description>fixture</description></metadata></package>')
        z.write(fixture, 'lib/net10.0/Fixture.dll')
    project = (app / 'app.nproj').read_text()
    project = project.replace('# projects = ["../engine"]', 'projects = ["../greet"]')
    project = project.replace('# assemblies = ["lib/Engine.dll"]', 'assemblies = ["lib/engine.dll"]')
    project = project.replace('# packages = { "Newtonsoft.Json" = "13.0.3" }', 'packages = { "Fixture" = "1.0.0" }')
    project = project.replace('# repositories = ["https://my.feed/v3/index.json"]', 'repositories = ["../feed"]')
    project = project.replace('# options = ["-debug+", "-define:TRACE"]', 'options = ["-define:FROM_PROJECT"]')
    (app / 'app.nproj').write_text(project)
    (app / 'main.n').write_text('using greet;\nusing engine;\nusing fixture;\n\n'
                                'System.Console.WriteLine(Greet("engine"));\n'
                                'System.Console.WriteLine(Value() + Answer() - 6);\n'
                                '#if FROM_PROJECT\nSystem.Console.WriteLine("defined");\n#endif\n')
    out = run('run', app, '--offline')  # from another folder: the feed is relative to the project, not the cwd
    check('Hello, engine!' in out and '42' in out and 'defined' in out, 'library, assembly, package and options: ' + out)
    again = run('run', app, '--offline')
    check('greet: up to date' in again and 'app: up to date' in again, 'nothing changed, nothing rebuilt: ' + again)
    for f in ('greet.dll', 'engine.dll', 'Fixture.dll', 'Nemerle.dll'): check((app / 'out' / f).exists(), f + ' next to the program')
    refs = (app / 'out/app.references').read_text().split()
    check(any(r.endswith('greet.dll') for r in refs) and any(r.endswith('Fixture.dll') for r in refs), 'the resolved references are listed: %s' % refs)
    (work / 'greet/greet.n').write_text('public Greet(who : string) : string { $"Hi, $who!" }\n')
    out = run('run', app, '--offline')
    check('greet: built' in out and 'Hi, engine!' in out, 'an edit in the used project rebuilds both: ' + out)
    print('PASS: project, assembly and package references, compiler options')

    # 2b. `ncc pack`: a NuGet package of a library, with the runtime package it depends on; used by a Nemerle project
    # from a folder feed, and by C# through the .NET SDK's own NuGet client
    run('init', 'shapes', '--lib')
    shapes = work / 'shapes'
    (shapes / 'shapes.n').write_text('public Area(w : int, h : int) : int { w * h }\npublic Names() : list[string] { ["square", "strip"] }\n')
    meta = (shapes / 'shapes.nproj').read_text().replace('# authors = "you"', 'authors = "tester"').replace('# license = "MIT"', 'license = "MIT"\nicon = "shapes.png"')
    shutil.copy2(tc / 'nemerle-icon.png', shapes / 'shapes.png') if (tc / 'nemerle-icon.png').exists() else (shapes / 'shapes.png').write_bytes(b'\x89PNG\r\n\x1a\n')
    (shapes / 'shapes.nproj').write_text(meta)
    out = run('pack', shapes)
    check('packed' in out and (shapes / 'out/shapes.0.1.0.nupkg').exists(), 'pack writes the package: ' + out)
    runtime = list((shapes / 'out').glob('Neo.Nemerle.Runtime.*.nupkg'))
    check(len(runtime) == 1, 'and the runtime package')
    with zipfile.ZipFile(shapes / 'out/shapes.0.1.0.nupkg') as z:
        spec = z.read('shapes.nuspec').decode()
        check('shapes.png' in z.namelist() and '<icon>shapes.png</icon>' in spec, 'the package icon: ' + spec)
        check('lib/net10.0/shapes.dll' in z.namelist() and '<authors>tester</authors>' in spec and 'Neo.Nemerle.Runtime' in spec
              and '<license type="expression">MIT</license>' in spec, 'the package layout and nuspec: ' + spec)
    with zipfile.ZipFile(runtime[0]) as z:
        check('lib/net10.0/Nemerle.dll' in z.namelist(), 'the runtime package carries Nemerle.dll')
        check('icon.png' in z.namelist() and '<icon>icon.png</icon>' in z.read('Neo.Nemerle.Runtime.nuspec').decode(), 'and Nemerle\'s logo')
    check('packs libraries' in run('pack', hello, ok=False), 'a program is not packed')
    feed2 = work / 'feed2'; feed2.mkdir()
    for f in (shapes / 'out').glob('*.nupkg'): shutil.copy2(f, feed2 / f.name)
    run('init', 'user')
    user = work / 'user'
    (user / 'user.nproj').write_text('name = "user"\n[references]\npackages = { "shapes" = "0.1.0" }\nrepositories = ["../feed2"]\n')
    (user / 'main.n').write_text('using shapes;\nSystem.Console.WriteLine(Area(6, 7));\n')
    check('42' in run('run', user, '--offline'), 'a Nemerle project uses the package')
    if shutil.which('dotnet') and subprocess.run(['dotnet', '--list-sdks'], capture_output=True, text=True).stdout.strip():
        cs = work / 'cs'; cs.mkdir()
        (cs / 'cs.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>'
                                      '<RestorePackagesPath>../nugetcache</RestorePackagesPath></PropertyGroup>'
                                      '<ItemGroup><PackageReference Include="shapes" Version="0.1.0" /></ItemGroup></Project>')
        (cs / 'Program.cs').write_text('System.Console.WriteLine(shapes.Area(6, 7));\nSystem.Console.WriteLine(shapes.Names());\n')
        (cs / 'nuget.config').write_text('<configuration><packageSources><clear /><add key="local" value="../feed2" />'
            '<add key="nuget.org" value="https://api.nuget.org/v3/index.json" /></packageSources><packageSourceMapping>'
            '<packageSource key="local"><package pattern="shapes" /><package pattern="Neo.Nemerle.Runtime" /></packageSource>'
            '<packageSource key="nuget.org"><package pattern="*" /></packageSource></packageSourceMapping></configuration>')
        r = subprocess.run(['dotnet', 'run'], cwd=cs, capture_output=True, text=True, env=dict(env, DOTNET_CLI_TELEMETRY_OPTOUT='1'))
        if r.returncode != 0 and ('NU1301' in r.stdout or 'Unable to load the service index' in r.stdout):
            print('SKIP: C# consumption (the SDK needs nuget.org, which is unreachable)')
        else:
            check(r.returncode == 0 and r.stdout.split()[-3:] == ['42', '[square,', 'strip]'], 'C# uses the package through the SDK: ' + r.stdout[-2000:])
            print('PASS: C# uses the package through the .NET SDK (dotnet run)')
    print('PASS: ncc pack (package, runtime package, metadata), used from a Nemerle project')

    # 3. a main file other than main.n, and program arguments
    run('init', 'tool')
    tool = work / 'tool'
    (tool / 'main.n').unlink()
    (tool / 'app').mkdir()
    (tool / 'app/start.n').write_text('def args = System.Environment.GetCommandLineArgs();\n'
                                      'System.Console.WriteLine(string.Join(",", args, 1, args.Length - 1));\n')
    (tool / 'tool.nproj').write_text('name = "tool"\nkind = "program"\nmain = "app/start.n"\n')
    out = run('run', tool, '--', 'a', 'b')
    check(out.strip().endswith('a,b'), 'main = "app/start.n" and program arguments: ' + out)
    print('PASS: main file and program arguments')

    # 4. the project file's errors, at their line and column
    bad = work / 'bad'; bad.mkdir()
    (bad / 'x.n').write_text('public X() : int { 1 }\n')
    cases = [
        ('name = "bad"\nverison = "1"\n', ':2:1:', 'unknown setting `verison\''),
        ('name = "bad"\nkind = "app"\n', ':2:8:', 'kind is "program" or "library"'),
        ('name = "bad"\nversion = 1.0\n', ':2:11:', 'a string is written in double quotes'),
        ('name = "bad"\n[refs]\n', ':2:1:', 'unknown section [refs]'),
        ('name = "bad"\nname = "again"\n', ':2:1:', 'set twice'),
        ('version = "1"\n', ':1:1:', 'has no name'),
        ('name = "bad"\n[references]\nprojects = [\n  "../greet",\n  "../app"]\n', ':5:3:', 'is a program'),
        ('name = "bad"\n[references]\nprojects = ["../missing"]\n', ':3:13:', 'does not exist'),
        ('name = "bad"\n[references]\nassemblies = ["none.dll"]\n', ':3:15:', 'does not exist'),
        ('name = "bad"\n[references]\npackages = { "Nope" = "1.0.0" }\nrepositories = ["../feed"]\n', ':3:23:', 'nope/1.0.0'),
        ('name = "bad"\n[references]\nassemblies = ["a.dll",\n', ':4:1:', 'the list is not closed'),
    ]
    for text, place, message in cases:
        (bad / 'bad.nproj').write_text(text)
        out = run('build', bad, '--offline', ok=False)
        check(place in out and message in out, 'error %r at %s: %s' % (message, place, out))
    mutual = [work / 'c1', work / 'c2']
    for me, other in (mutual, mutual[::-1]):
        me.mkdir(); (me / (me.name + 'x.n')).write_text('public V() : int { 1 }\n')
        (me / (me.name + '.nproj')).write_text('name = "%s"\nkind = "library"\n[references]\nprojects = ["../%s"]\n' % (me.name, other.name))
    check('in a cycle' in run('build', work / 'c1', ok=False), 'projects in a cycle')
    check('no project in' in run('build', work / 'nowhere', ok=False), 'a folder without a project')
    # a compile error fails the build
    (hello / 'main.n').write_text('def n : int = "no";\n')
    check('the build failed' in run('build', hello, ok=False), 'a compile error fails the build')
    # 5. an MSBuild project as upstream Nemerle wrote them: the content picks the reader, the model is the same
    legacy = work / 'legacy'; (legacy / 'src').mkdir(parents=True)
    (legacy / 'src/shout.n').write_text('public Shout(s : string) : string { s.ToUpper() + "!" }\n')
    (legacy / 'src/unlisted.n').write_text('this is not listed, so it is not compiled\n')
    (legacy / 'Legacy.Shout.nproj').write_text('''\ufeff<?xml version="1.0" encoding="utf-8"?>
<Project ToolsVersion="3.5" DefaultTargets="Build" xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
  <PropertyGroup>
    <Nemerle Condition=" '$(Nemerle)' == '' ">$(ProgramFiles)\\Nemerle</Nemerle>
    <OutputType>Library</OutputType>
    <AssemblyName>Legacy.Shout</AssemblyName>
  </PropertyGroup>
  <PropertyGroup Condition=" '$(Configuration)|$(Platform)' == 'Debug|AnyCPU' ">
    <OutputType>Exe</OutputType>
  </PropertyGroup>
  <ItemGroup>
    <Reference Include="mscorlib" />
    <Reference Include="System" />
    <Reference Include="Nemerle"><HintPath>$(Nemerle)\\Nemerle.dll</HintPath></Reference>
  </ItemGroup>
  <ItemGroup>
    <Compile Include="src\\shout.n"><SubType>Code</SubType></Compile>
    <Folder Include="src\\" />
  </ItemGroup>
  <Import Project="$(Nemerle)\\Nemerle.MSBuild.targets" />
</Project>
''')
    out = run('build', legacy)
    check('Legacy.Shout: built' in out and (legacy / 'out/Legacy.Shout.dll').exists(), 'an MSBuild library builds, listed sources only: ' + out)
    old = work / 'oldapp'; old.mkdir()
    shutil.copy2(compile_library('helper', 'public Twice(n : int) : int { n * 2 }\n'), old / 'helper.dll')
    (old / 'main.n').write_text('using src.shout;\nusing helper;\n'
                                'System.Console.WriteLine(Shout("legacy"));\n'
                                'System.Console.WriteLine(Twice(21));\n'
                                'System.Console.WriteLine(typeof(Nemerle.Compiler.manager_class.ManagerClass).Name);\n'
                                '#if OLD_STYLE\nSystem.Console.WriteLine("defined");\n#endif\n')
    (old / 'OldApp.nproj').write_text('''<Project xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
  <PropertyGroup>
    <OutputType>Exe</OutputType>
    <AssemblyName>OldApp</AssemblyName>
    <DefineConstants>OLD_STYLE;TRACE</DefineConstants>
  </PropertyGroup>
  <ItemGroup>
    <Reference Include="Nemerle.Compiler" />
    <Reference Include="helper"><HintPath>helper.dll</HintPath></Reference>
  </ItemGroup>
  <ItemGroup>
    <Compile Include="main.n" />
    <ProjectReference Include="..\\legacy\\Legacy.Shout.nproj"><Name>Legacy.Shout</Name></ProjectReference>
  </ItemGroup>
</Project>
''')
    out = run('run', old)
    check('LEGACY!' in out and '42' in out and 'ManagerClass' in out and 'defined' in out,
          'an MSBuild program: project, HintPath and toolchain references, DefineConstants: ' + out)
    mixed = work / 'mixed'; mixed.mkdir()
    (mixed / 'mixed.nproj').write_text('name = "mixed"\n[references]\nprojects = ["../legacy"]\n')
    (mixed / 'main.n').write_text('using src.shout;\nSystem.Console.WriteLine(Shout("mixed"));\n')
    check('MIXED!' in run('run', mixed), 'a declarative project uses an MSBuild one')
    for text, place, message in [
        ('<Project><ItemGroup><Compile Include="gone.n" /></ItemGroup></Project>', ':1:22:', 'the source `gone.n\' does not exist'),
        ('<Project>\n<ItemGroup>\n  <Reference Include="Some.Library" />\n</ItemGroup></Project>', ':3:4:', 'the reference `Some.Library\' is not found'),
        ('<Project>\n<ItemGroup>\n  <ProjectReference Include="x.csproj" />\n</ItemGroup></Project>', ':3:4:', 'is not a Nemerle project'),
        ('<Project><PropertyGroup><OutputType>Module</OutputType></PropertyGroup></Project>', ':1:1:', 'OutputType `Module\''),
        ('<Project>\n<ItemGroup>\n</Project>', ':3:3:', 'not well-formed'),
    ]:
        (bad / 'bad.nproj').write_text(text)
        out = run('build', bad, ok=False)
        check(place in out and message in out, 'MSBuild error %r at %s: %s' % (message, place, out))
    # the old TargetFrameworkVersion: 4.6.2 and later is that target, older is noted and left out
    fx = work / 'oldfx'; fx.mkdir(); (fx / 'main.n').write_text('System.Console.WriteLine("v3.5 project");\n')
    (fx / 'OldFx.nproj').write_text('<Project><PropertyGroup><OutputType>Exe</OutputType><AssemblyName>OldFx</AssemblyName>'
                                    '<TargetFrameworkVersion>v3.5</TargetFrameworkVersion></PropertyGroup>'
                                    '<ItemGroup><Compile Include="main.n" /></ItemGroup></Project>')
    out = run('run', fx)
    check('v3.5 project' in out and 'older than .NET Framework 4.6.2' in out, 'TargetFrameworkVersion v3.5 is noted and left out: ' + out)
    (fx / 'OldFx.nproj').write_text((fx / 'OldFx.nproj').read_text().replace('v3.5', 'v4.8'))
    out = run('build', fx, '--offline', ok=False)  # (offline: no 113 MB download in a check; the message names the target)
    check('net48 reference assemblies' in out, 'TargetFrameworkVersion v4.8 is the target net48: ' + out)
    print('PASS: MSBuild projects (upstream format): sources, references, defines, used by and using declarative projects, framework versions')
    print('PASS: project file errors located (setting, value, section, list item, package), cycles, compile errors')
    # a single-file program, -out:NAME.exe: a launcher next to it (NAME elsewhere; NAME.exe on Windows, with the
    # program in NAME.dll), so it starts directly on .NET; -launcher- writes none
    single = work / 'single'; single.mkdir()
    (single / 'hello.n').write_text('System.Console.WriteLine("launched");\n')
    run(single / 'hello.n', '-out:' + str(single / 'hello.exe'), '-no-color', cwd=single)
    program = single / ('hello.dll' if os.name == 'nt' else 'hello.exe')
    launcher = single / ('hello.exe' if os.name == 'nt' else 'hello')
    shutil.copy2(tc / 'Nemerle.dll', single / 'Nemerle.dll')
    check(program.exists() and launcher.exists(), 'ncc -out:hello.exe writes the program and a launcher: %s' % sorted(p.name for p in single.iterdir()))
    out = subprocess.run([str(launcher)], capture_output=True, text=True).stdout
    check(out.strip() == 'launched', 'the single-file launcher starts the program: ' + out)
    out = subprocess.run(['dotnet', str(program)], capture_output=True, text=True).stdout
    check(out.strip() == 'launched', 'dotnet runs the program itself: ' + out)
    plain = work / 'plain'; plain.mkdir()
    (plain / 'hello.n').write_text('System.Console.WriteLine("plain");\n')
    run(plain / 'hello.n', '-out:' + str(plain / 'hello.exe'), '-launcher-', '-no-color', cwd=plain)
    check((plain / 'hello.exe').exists() and not (plain / 'hello').exists() and not (plain / 'hello.dll').exists(),
          '-launcher- writes the program only: %s' % sorted(p.name for p in plain.iterdir()))
    print('PASS: a single-file program gets a launcher (-out:NAME.exe), and -launcher- leaves it out')
    print('PASS: %d project checks' % checks)
finally:
    shutil.rmtree(work, ignore_errors=True)
