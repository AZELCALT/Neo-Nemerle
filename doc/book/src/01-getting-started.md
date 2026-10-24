# Getting started

## Getting the compiler

The toolchain lives in the repository. From the root of a cloned or downloaded repository on Windows, the installer handles missing prerequisites through winget:

```bat
install\install.cmd          rem install the toolchain; installs .NET 10 runtime if needed
install\install.cmd -Build   rem build from source; also installs SDK, Python, Mono's sn and Git if needed
```

It checks the compiler and script host before replacing an existing installation. It also checks that the app-local
`System.CodeDom.dll` matches the compiler, repairing it when necessary. There is no need to copy a DLL out of a
different SDK. Prerequisites are available in the same installer process after installation; Windows may request
elevation for system packages. `-NoDependencies` opts out of automatic prerequisite installation and online repair.

For a source build on Linux or macOS, install the .NET 10 SDK, Python 3 and Mono's `sn` tool (used to verify signed
assemblies), then:

```sh
git clone https://github.com/AZELCALT/Neo-Nemerle.git
cd Neo-Nemerle
./bootstrap --quick
```

`boot/coreclr` already holds a working compiler, so you can use it right away. `./bootstrap` rebuilds everything from
it and runs the tests; the new toolchain lands in `out/bootstrap/toolchain`. In this book, `ncc` and `nscript` mean
the ones in either directory.

## Hello, world

Create a file named `hello.n`:

```nemerle
// file: hello.n
using System.Console;

WriteLine("Hello, world!")
```

```text
Hello, world!
```

Compile and run it:

```sh
ncc hello.n -out:hello.exe
./hello            # Windows: hello.exe
```

`-out:hello.exe` writes the program and a launcher for it, a small native executable that starts it on .NET (the one
`dotnet build` gives a C# program). On Linux and macOS the launcher is `hello` and the program stays `hello.exe`,
which `dotnet hello.exe` also runs. On Windows the launcher is `hello.exe`, since that is the name you start, and the
program is `hello.dll` (`dotnet hello.dll`): Windows would start a .NET program named `.exe` on the old .NET Framework.
`-launcher-` writes the program alone.

Three things are worth noticing already:

- **`using System.Console;`** opens a .NET class, so `WriteLine` can be called without its owner's name.
- **Statements written at the top of a file run as the program.** They become the file's `Main`.
- **There is no semicolon after the last expression.** Semicolons separate expressions; they don't end them. A
  trailing one is allowed but not needed.

A program that uses the standard library needs `Nemerle.dll` next to it at run time. It is in the toolchain directory;
copy it with your program.

## Using a neighboring file

A standalone program does not need a project file. Put these two files together:

```nemerle
// file: helpers.n
public Greeting(name : string) : string { $"Hello, $name!" }

// file: main.n
using helpers;
System.Console.WriteLine(Greeting("Ada"))
```

```text
Hello, Ada!
```

Compile only the entry file with `ncc main.n -out:hello.exe`. The compiler discovers `helpers.n` beside it, then
resolves that file's imports too. With no `.nproj` it prints a warning and continues. `nscript run main.n` uses the
same lookup without the project warning. References to external DLLs and packages still need to be declared.

## A project

A project is useful when you want a named build, references, compiler options, or automatic inclusion of all your
source files. `ncc init` writes a commented `.nproj` that explains the settings, and `ncc run` builds and runs it:

```sh
ncc init hello
cd hello
ncc run
```

The project's folder is its source root, and `hello.nproj` names it and lists what it references. Chapter 13
covers projects.

## Running a file as a script

The same file runs without a build step:

```sh
nscript run hello.n
```

`nscript` compiles in memory, caches the result, and runs it. Chapter 11 covers scripts in depth.

## Where the source root is

Every `.n` file is a module named by its path relative to the *source root*. `-source-root:DIR` sets it explicitly;
otherwise the compiler uses the containing project root, or the first source file's directory for a standalone
program. A script starts at its own directory. Each explicit `using helpers;` also looks beside the file that wrote
it, so supporting files can use their own neighbors.

For a name that stays the same after moving a file, start `text.n` with `register library.words;`. Its module then
becomes `library.words.text`, used with `using library.words.text;`. A file has one identity and one registration for
its entire contents. `using library.words;` instead makes file names available for calls such as `text.Shout(...)`.
[Files are modules](07-files-and-modules.md) explains both forms.
