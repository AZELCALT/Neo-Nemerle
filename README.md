# Nemerle (revived)

Nemerle is a statically typed language for .NET. It combines functional, object-oriented and imperative programming,
infers types, and has a macro system strong enough to grow the language itself. It was well ahead of its time when the
University of Wroclaw created it in 2003. This repository brings it back on **.NET 10**, with its compiler, a language
server, scripting and grammars built into the language.

```nemerle
using System.Console;

variant Shape
{
  | Circle { radius : double }
  | Rectangle { width : double; height : double }
}

Area(shape : Shape) : double
{
  | Shape.Circle(r) => 3.14 * r * r
  | Shape.Rectangle(w, h) => w * h
}

foreach (shape in [Shape.Circle(1.0), Shape.Rectangle(2.0, 3.0)])
  WriteLine(Area(shape))
```

## Goals

- **A living Nemerle.** The original work went quiet after 2015, on .NET Framework and Mono. Here it runs on today's
  .NET and builds itself from source, so it can keep evolving.
- **Extensible, and disciplined.** You can extend the language with macros and with whole grammars (`grammar` and
  `space`). The structure stays predictable:
  - a source file is its namespace, so there is no namespace spaghetti;
  - a file uses each grammar in one place;
  - language extensions are always published as source, so nobody ships a private dialect that users mistake for
    Nemerle.
- **Tooling you can rely on.**
  - one install for the compiler, scripts and a language server for any editor;
  - scripts that configure themselves the way Kotlin's do;
  - compiled grammars and macros that travel inside the libraries that define them.
- **Classic Nemerle stays Nemerle.** Only `namespace` blocks and `partial` are gone; everything else of the classic
  language works. Where the compiler behaves differently from classic Nemerle in other ways, that's treated as a bug.

## Install

You need the **.NET 10 runtime** ([download](https://dotnet.microsoft.com/download/dotnet/10.0)). Then clone the
repository and run the installer for your system:

```sh
git clone https://github.com/AZELCALT/Neo-Nemerle.git
cd Neo-Nemerle
install/install.sh            # Linux, macOS (sh)
```

```bat
install\install.cmd           :: Windows (Command Prompt or PowerShell)
```

The installer:
1. copies the toolchain (compiler, standard library and macros, Nitra, scripting) into a folder of your own;
2. builds the language server from source with that compiler;
3. puts `ncc`, `nscript` and `nemerle-lsp` on your `PATH`;
4. installs the VS Code / VSCodium extension if it finds the editor and `npm`;
5. checks that a script runs.

| | Linux / macOS (`install.sh`) | Windows (`install.cmd`, `install.ps1`) |
|---|---|---|
| Installs to | `~/.local/share/nemerle` (`--prefix`) | `%LOCALAPPDATA%\Nemerle` (`-Prefix`) |
| Commands go to | `~/.local/bin` (`--bin`) | `%LOCALAPPDATA%\Nemerle\bin`, added to your user `PATH` |
| Build from source first | `--build` | `-Build` |
| Skip the language server | `--no-lsp` | `-NoLsp` |
| Editor extension | `--editor auto\|code\|codium\|none` | `-Editor auto\|code\|codium\|none` |
| Remove everything | `--uninstall` | `-Uninstall` |

`install/install.ps1` also runs under PowerShell 7 on Linux and macOS. The Windows-specific parts (`.cmd` launchers, the
user `PATH`) have not been tested on Windows yet; please report problems.

**Without installing**, everything also runs straight from the clone: `boot/coreclr/ncc` and `boot/coreclr/nscript`.

### Editors

The language server speaks LSP over stdio. It gives diagnostics, semantic highlighting, folding and document symbols,
including inside `grammar` and `space` blocks.
- **VS Code / VSCodium:** the installer sets up the extension. It runs `nemerle-lsp` from `PATH`, or the
  `nemerle.languageServer.path` setting.
- **The extension on its own:** `./bootstrap` also writes `out/bootstrap/nemerle-0.2.0.vsix` (or run
  `build/build-vscode-extension.py`). It carries its language server and needs only the .NET 10 runtime:
  `code --install-extension nemerle-0.2.0.vsix`, `codium --install-extension nemerle-0.2.0.vsix`, or
  *Install from VSIX...* in the Extensions view.
- **Other editors:** configure an LSP client to start `nemerle-lsp` for `*.n` files.

Details are in [tools/language-server/README.md](tools/language-server/README.md).

## Your first program

```sh
echo 'System.Console.WriteLine("Hello, world!")' > hello.n
nscript run hello.n              # run it as a script
ncc hello.n -out:hello.exe       # or compile it
dotnet hello.exe
```

A compiled program needs `Nemerle.dll`, the standard library, next to it when it uses the library. Find it in the
installed toolchain folder.

For more than one file, make a project: `ncc init hello && cd hello && ncc run`. The `.nproj` file names the
project and lists its references (assemblies, other projects, NuGet packages); `ncc build` puts a ready-to-run
program, with `Nemerle.dll` and its references, in `out/`. See [Projects](doc/book/src/13-projects.md).

## Learn more

- **[The Nemerle Book](doc/book/src/SUMMARY.md):** the language from the ground up, from values and functions to
  pattern matching, files as modules, macros, grammars and scripts. Every example in it is compiled and tested.
- **[CHANGELOG.md](CHANGELOG.md):** what this revival changed compared with upstream Nemerle.
- **Reference notes:**
  - [doc/FILE-MODULES.md](doc/FILE-MODULES.md) for files as modules;
  - [doc/CONTINUATION.md](doc/CONTINUATION.md) for the continuation section;
  - [scripting/README.md](scripting/README.md) for the scripting API.

## Building from source

Building needs the .NET 10 SDK, Python 3 and `sn` (Mono's strong-name tool, which verifies signed outputs).

```sh
./bootstrap                  # boot/coreclr -> stage 1 -> stage 2, Nitra, scripting, LSP, then every test suite
./bootstrap --quick          # fast suites only
./bootstrap --update-boot    # also replace boot/coreclr with the result when everything passed
```

The new toolchain lands in `out/bootstrap/toolchain`, with one log per step in `out/bootstrap/logs`. `boot/coreclr` is
the pinned compiler that every build starts from; update it only when a bootstrap passes.

| Directory | Contents |
|---|---|
| `ncc/`, `lib/`, `macros/` | compiler, standard library, standard macros |
| `native-nitra/`, `grammar/` | Nitra (runtime, grammar, compiler) as file modules; grammar/space notes and examples |
| `scripting*/`, `tools/language-server/` | scripting host, NuGet adapter, language server and VS Code extension |
| `platform/` | CLR backend adapter (C#) |
| `install/` | the installers |
| `build/` | build scripts and `bootstrap.py`; `build/migrations/` holds the one-off source migrations |
| `tests/`, `testsuite/` | test suites and fixtures; upstream's language testsuite |
| `boot/coreclr/` | pinned .NET 10 toolchain used to bootstrap |
| `doc/` | the book, reference notes, and `doc/revive/` with the notes from the port |
| `misc/` | signing keys, editor modes |
| `legacy/` | upstream's .NET Framework / Mono / Visual Studio build files and side projects, kept unchanged ([legacy/README.md](legacy/README.md)) |

The original upstream README (Windows installer, Mono, Visual Studio) is kept in
[doc/ORIGINAL-README.md](doc/ORIGINAL-README.md). Those instructions are for the original .NET Framework tree.

## The people behind Nemerle

Everything here stands on the work of the original team, and the revival exists because that work was good enough
to bring back.

- **Nemerle was born at the University of Wroclaw.** The first commit in this history dates from September 2003.
  It was led by **Michal Moskal**, with **Kamil Skalski** and **Pawel Olszta**. Dawid Duda wrote the standard library,
  and Ewa Dacko, Bartosz Podlejski, Jacek Sliwerski, Wojtek Knapik and many others contributed. See [AUTHORS](AUTHORS).
- **The Nemerle Project Team and the [RSDN](https://rsdn.org) community** carried it from 2008 on. They added the
  Visual Studio integration, the PEG parser, computation expressions and much more. The busiest years were 2010 and
  2011, with about a thousand commits each.
- **[Nitra](https://github.com/rsdn/nitra)**, the language workbench published under the same RSDN organization
  (copyright JetBrains, 2014), supplies the grammar machinery this fork builds into the language.

The most active committers in the upstream history, by git handle: malekith, nazgul, VladD2, hardcase, olszta,
CodingUnit, NN, Dmitry Ivankov, rampelstinskin, rzyj, Pavel Bludov, earendil and Igor Tkachev. Hundreds of commits
by others are kept in this repository's history too (`git shortlog -sn master`).

Upstream development went quiet after 2015. This fork picks up where they stopped. Thank you.

## License

The compiler is **GPL-2.0-or-later** with an output exception: programs you compile with it are yours, under any
license you choose. Language extensions are the exception: macros and Nitra grammars change the language itself,
so their source must be published under the GPL, also when they are part of a closed program. The standard library
stays **BSD-3-Clause** like the original, so it can ship inside your programs. The original Nemerle and Nitra copyright notices are kept with their
code. See [NOTICE.md](NOTICE.md) for the full map.
