# Projects

A file compiles on its own with `ncc file.n`. Anything bigger is a *project*: a folder with one `.nproj` file.
The folder is the source root, so every `.n` file under it is a module named by its path (chapter 7), and the
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
hello: built out/hello.exe (1 file, 2.1 s)
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
| `ncc clean [project]` | removes `out/` |

`[project]` is the project's folder or its `.nproj` file; the default is the current folder. Options given to
`build` and `run` are passed to the compiler (`ncc build -debug+`), and `--offline` resolves packages from the
local cache and local feeds only.

A build is skipped when nothing it depends on changed: the project file, the sources, the references, the options
and the compiler itself. The output folder is ready to run or ship: the binary, `Nemerle.dll`, and every assembly
the references need, so `dotnet out/hello.exe` works anywhere the .NET 10 runtime is installed.

## The project file

The project file is declarative: a small part of TOML, read by the compiler and the language server without running
any code. This is the file `ncc init` writes, with every setting shown:

```toml
# The project hello. Its sources are every .n file under this folder; a file's path is its module.
name = "hello"
version = "0.1.0"
# kind = "library"          # default: a program when main.n exists, a library otherwise
# main = "main.n"            # the file whose top-level code is Main
# output = "out"

[references]
# assemblies = ["lib/Engine.dll"]
# projects = ["../engine"]
# packages = { "Newtonsoft.Json" = "13.0.3" }
# repositories = ["https://my.feed/v3/index.json"]

[compiler]
# options = ["-debug+", "-define:TRACE"]
```

- **`name`** is required. It names the binary (`out/hello.exe` or `out/hello.dll`).
- **`kind`** is usually left out: a project with its main file is a program, one without is a library.
- **`main`** is the file the program starts at, when it is not `main.n`: `main = "app/start.n"`.
- **`assemblies`** are .NET assemblies by path, relative to the project.
- **`projects`** are other projects this one uses, each a folder or `.nproj` file. They are built first, and they
  must be libraries. Two projects that use each other are an error.
- **`packages`** are NuGet packages, each with an exact version. They are resolved with the same resolver and cache as
  scripts (chapter 11), from nuget.org and the `repositories` (URLs, or folders relative to the project).
- **`options`** are passed to the compiler as they are.

The sources are not listed. They are every `.n` file under the folder, except `out/`, folders whose name starts with
a dot, `bin/`, `obj/`, and folders that hold a project of their own.

Settings the file does not know are errors, not ignored, and every error points at its line and column:

```text
hello.nproj:3:1: error: unknown setting `verison'; the settings are name, version, kind, main, output
hello.nproj:7:3: error: `../app' is a program; a project uses libraries only
```

## MSBuild projects

Upstream Nemerle wrote its `.nproj` files as MSBuild XML. `ncc` reads those too: the file's content picks the
reader (XML starts with `<`), and both give the same project, so a declarative project can use an MSBuild one and
the other way round. From the XML it takes what such a project says plainly:

- `AssemblyName` (or `Name`), `OutputType` (`Exe`, `WinExe`, `Library`), `Version` and `DefineConstants`, from
  property groups without a condition;
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
app: built out/app.exe (1 file, 1.8 s)
Hello, engine!
```

A library's `export class` types are global (chapter 7), so a program that uses the library sees them without a
`using`.

## The editor

The language server reads the project of the workspace folder: what the program starts at, whether it is a library,
and the references its last build resolved (`out/NAME.references`). So types from packages and other projects are
known to hover, go-to-definition and the typed diagnostics once the project has been built.
