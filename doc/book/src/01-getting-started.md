# Getting started

## Getting the compiler

The toolchain lives in the repository. You need the .NET 10 SDK, Python 3 and Mono's `sn` tool (used to verify signed
assemblies). Then:

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

## A project

For more than one file, make a project. `ncc init` writes one, and `ncc run` builds and runs it:

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

Every `.n` file is a module named by its path. `ncc` takes that path relative to the *source root*: the
`-source-root:DIR` option, or the current directory. Chapter 7 explains this; for now, keep your files in one
directory and compile from there.
