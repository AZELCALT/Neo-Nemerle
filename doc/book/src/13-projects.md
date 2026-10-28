# Projects

A program compiles with `ncc file.n`, including the local files its `using`s discover. A *project* adds a named build,
configured references and compiler options: a folder with one `.nproj` file.
The folder is the source root, so every `.n` file under it is a module named by its path or its `register` directive
([chapter 7](07-files-and-modules.md#logical-folders-register)), and the
project file only says what the layout cannot: the project's name, what it references, and compiler options.

## Starting one

```sh
ncc init hello          # a program; `ncc init NAME --lib` makes a library
cd hello
ncc run
```

```text
Created program hello in /home/me/hello:
  hello.nproj
  main.n
  .gitignore
Next: cd hello && ncc run
hello: built out/hello.dll (1 file, 2.1 s)
Hello from hello!
```

`ncc init` writes three files and keeps any that already exist. `main.n` is where the program starts: its top-level
code is `Main`. A library gets a `NAME.n` instead, with one public function to show the shape.

## The commands

| Command | What it does |
|---|---|
| `ncc init [folder] [--lib] [--name NAME]` | makes a project in the folder (default: the current one) |
| `ncc build [project] [options]` | builds the project, after the projects it uses, into `out/` |
| `ncc run [project] [options] [-- arguments]` | builds a program and runs it with the arguments after `--` |
| `ncc pack [project] [options]` | builds a library and writes its NuGet package (see below) |
| `ncc clean [project]` | removes `out/` |

`[project]` is the project's folder or its `.nproj` file; the default is the current folder. Options given to
`build` and `run` are passed to the compiler (`ncc build -debug+`), and `--offline` resolves packages from the
local cache and local feeds only.

A build is skipped when nothing it depends on changed: the project file, the sources, the references, the options
and the compiler itself. The output folder is ready to run or ship: the binary, `Nemerle.dll`, and every assembly
the references need, so `dotnet out/hello.dll` works anywhere the .NET 10 runtime is installed.

A program also gets a launcher next to its `.dll`: `out/hello.exe` on Windows, `out/hello` elsewhere. It is the .NET
application host (the same one `dotnet build` gives a C# program), so `./out/hello` starts the program directly, on
the installed .NET runtime. The launcher is native: it is for the machine it was built on (or for Windows, with a
`-windows` target). It comes from the .NET SDK's host pack when one is installed, else from nuget.org; without
either, the build says so and the program still runs with `dotnet`. A .NET Framework program (`target = "net48"`)
is a `.exe` itself and needs no launcher.

## The project file

The project file is declarative: a small part of TOML, read by the compiler and the language server without running
any code. This is the file `ncc init` writes, with every setting shown:

```toml
# The project hello. Run `ncc build` here to build it; `ncc run` builds and starts a program.
# Every .n file under this folder is a source; out/, bin/, obj/ and nested projects are excluded.
# util/text.n is module util.text. Start that file with `register library.words;` to name it library.words.text.
# `using library.words.text;` opens its members; `using library.words;` lets you write text.Member(...).
# Local using paths discover .n files; external libraries still need references below.
name = "hello"
version = "0.1.0"
# kind = "library"          # default: a program when main.n exists, a library otherwise
# main = "main.n"            # the file whose top-level code is Main
# output = "out"
# target = "netstandard2.0"     # default: the compiler's .NET; or net8.0, netstandard2.1, net48, ...

[references]
# Paths below are relative to this project. Add a library here before using its modules.
# assemblies = ["lib/Engine.dll"]
# projects = ["../engine"]
# packages = { "Newtonsoft.Json" = "13.0.3" }
# repositories = ["https://my.feed/v3/index.json"]

[compiler]
# options = ["-debug+", "-define:TRACE"]
```

- **`name`** is required. It names the binary (`out/hello.dll`, and a program's launcher `out/hello`).
- **`kind`** is usually left out: a project with its main file is a program, one without is a library.
- **`main`** is the file the program starts at, when it is not `main.n`: `main = "app/start.n"`.
- **`target`** is the .NET the output is for, when it is not the compiler's own (see *Targets* below).
- **`assemblies`** are .NET assemblies by path, relative to the project.
- **`projects`** are other projects this one uses, each a folder or `.nproj` file. They are built first, and they
  must be libraries. Two projects that use each other are an error.
- **`packages`** are NuGet packages, each with an exact version. They are resolved with the same resolver and cache as
  scripts (chapter 11), from nuget.org and the `repositories` (URLs, or folders relative to the project).
- **`options`** are passed to the compiler as they are.

The sources are not listed. They are every `.n` file under the folder, except `out/`, folders whose name starts with
a dot, `bin/`, `obj/`, and folders that hold a project of their own.

For example, add `util/text.n`, declare `public Shout(s : string) : string { s.ToUpper() }`, then write
`using util.text;` in `main.n` and call `Shout("hello")`. Run `ncc run` again: the new file is included automatically.
To move that file without changing callers, first give it a logical folder with `register library.words;` and change
the caller to `using library.words.text;`. After that it may move anywhere under the project root with its name
`text.n` intact. `using library.words;` instead keeps the file name in calls: `text.Shout("hello")`.

`ncc build` and `ncc run` require a `.nproj` file; when it is missing, they explain how to create one with `ncc init`.
For a standalone source, `ncc file.n` still works without a project. It warns when no `.nproj` exists and resolves local `using` paths beside each source file, including transitive
imports. Scripts use the same resolution without the warning.

Settings the file does not know are errors, not ignored, and every error points at its line and column:

```text
hello.nproj:3:1: error: unknown setting `verison'; the settings are name, version, kind, main, output, target
hello.nproj:7:3: error: `../app' is a program; a project uses libraries only
```

## Publishing a library

`ncc pack` builds a library project and writes a NuGet package of it into `out/`:

```sh
ncc pack shapes
```

```text
shapes: built shapes/out/shapes.dll (1 file, 1.1 s)
shapes: packed shapes/out/shapes.0.1.0.nupkg
shapes: packed shapes/out/Neo.Nemerle.Runtime.1.2.0.665.nupkg (the runtime it depends on)
```

The package holds the library under `lib/<target>/` (with its `.pdb` when it is built with `-debug+`), and depends
on the packages and projects in `[references]` and on `Neo.Nemerle.Runtime`, the package of `Nemerle.dll`, which
`ncc pack` writes next to it. Publish both (`dotnet nuget push`), or put them in a folder feed: C# projects use the
library with an ordinary `PackageReference`, Nemerle projects with `packages`. The `[package]` section fills in the
package's metadata:

```toml
[package]
authors = "you"
description = "what it does"
license = "MIT"                  # an SPDX expression
repository = "https://github.com/you/shapes"
tags = ["geometry"]
icon = "icon.png"                # a PNG or JPEG, shown by NuGet
```

## Targets

By default a project is built for the .NET the compiler runs on (.NET 10). `target` builds it for another:

| `target` | Output | Runs on |
|---|---|---|
| `netcoreapp3.0`, `netcoreapp3.1`, `net5.0` ... `net9.0` | programs and libraries | that .NET or newer |
| `netstandard2.0`, `netstandard2.1` | libraries only | every .NET, .NET Framework 4.6.2+, Mono, Unity |
| `net462` ... `net481` | programs and libraries | .NET Framework, Mono |
| `net10.0-windows` (any .NET 5+ base) | programs and libraries (WinForms, WPF) | Windows, on the desktop runtime |
| `net10.0-android`, `net10.0-android36.0` | libraries | an Android app built by the .NET Android workload |
| `net10.0-ios`, `-maccatalyst`, `-macos`, `-tvos` | libraries | an Apple app built by its .NET workload |

A platform target also fetches the platform's own reference pack (`Microsoft.WindowsDesktop.App.Ref`,
`Microsoft.Android.Ref.<API>`, `Microsoft.iOS.Ref...`): the newest stable one for that .NET, or the version the name
gives (`net10.0-android35.0`). Android and Apple apps are packaged (and compiled ahead of time) by their workloads,
so a Nemerle project builds the libraries such an app uses; a platform library is used only by projects for the same
platform.

`ncc build` fetches the target's reference assemblies from nuget.org the first time (into the user's data folder,
`Nemerle/references`), and uses them offline after that. The compiler still types against the .NET it runs on, and
then checks the output against the target: anything the target does not have is an error, and no binary is written.

```text
bad.n:3: error: the method System.String.Contains(System.Char) is not in netstandard2.0 (used in bad.Has)
```

(The line is known when the project builds with `-debug+`; otherwise the error names the method.) The program runs
with the .NET Standard 2.0 build of `Nemerle.dll`, which `ncc build` copies next to it. A project may use another
only when its runtime can load it: a `netstandard2.0` library is usable from every target, while a library built
for .NET 10 is not usable from a `net48` program.

## MSBuild projects

Upstream Nemerle wrote its `.nproj` files as MSBuild XML. `ncc` reads those too: the file's content picks the
reader (XML starts with `<`), and both give the same project, so a declarative project can use an MSBuild one and
the other way round. From the XML it takes what such a project says plainly:

- `AssemblyName` (or `Name`), `OutputType` (`Exe`, `WinExe`, `Library`), `Version`, `TargetFramework` (or the old
  `TargetFrameworkVersion`: `v4.6.2` and later is that .NET Framework, an older one is noted and the project builds for
  the compiler's .NET) and `DefineConstants`, from property groups without a condition;
- `Compile` items: the sources, which are then only the listed files;
- `Reference` items: a `HintPath` that exists, a toolchain assembly (`Nemerle.Compiler`), or a .NET one (`System.*`);
- `ProjectReference` items to other `.nproj` projects, and `PackageReference` items with a `Version`.

Conditions, imports and targets are MSBuild's own and are left out; the build is always `ncc build`'s. The sources
are compiled as file modules, like any others, so code that still uses `namespace` blocks has to be moved to files
first.

## Using a library project

A library's files are modules like any others: a program that lists the library in `projects` imports them with
`using`.

```nemerle,ignore
// file: greet/greet.n   (the library project greet)
public Greet(who : string) : string { $"Hello, $who!" }

// file: app/main.n      (the program app; app.nproj has projects = ["../greet"])
using greet;

System.Console.WriteLine(Greet("engine"))
```

```text
greet: built ../greet/out/greet.dll (1 file, 2 s)
app: built out/app.dll (1 file, 1.8 s)
Hello, engine!
```

A library's `export class` types are global (chapter 7), so a program that uses the library sees them without a
`using`.

## Debugging

A project built with `options = ["-debug+"]` writes a `.pdb` next to its binary, and any .NET debugger steps through
the Nemerle source: breakpoints, the call stack with lines, parameters, locals, and top-level state by name
(`total`, or `main.total`). In VS Code and VSCodium, the extension's Run and Debug builds the project and starts it
under [netcoredbg](https://github.com/Samsung/netcoredbg); from a terminal, `netcoredbg --interpreter=cli -- dotnet
out/app.dll` does the same.

## The editor

The language server reads the project of the workspace folder: what the program starts at, whether it is a library,
and the references its last build resolved (`out/NAME.references`). So types from packages and other projects are
known to hover, go-to-definition and the typed diagnostics once the project has been built.

What it does, for Nemerle code and for `grammar` and `space` blocks:

- **Diagnostics** as you type: parse errors at once, then the compiler's own errors and warnings once edits pause.
- **Hover** with a value's type where the cursor is. A value whose type follows the flow shows its type there
  (`x : int` after `x = 1`), or the types it can be (`x : int | string`); where it is declared, every type it takes.
- **Inlay hints** with the types inferred where none is written.
- **Go to definition**, **find references** and **rename** (a type's name too, where it means that type).
- **Completion** of members, names in scope and keywords, and **signature help** in a call's arguments.
- **Formatting** of a file or a selection: each line is indented by the braces it is in, and keeps how it lines up
  inside them. Strings, comments and `#pragma indent` files are left as they are.
- **Quick fixes**: a name it cannot find gets a `using` of the namespace or module that has it, or the name written
  with it; a value never used gets its name prefixed with `_`.
