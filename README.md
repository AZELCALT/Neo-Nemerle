# Nemerle (revived)

Nemerle is a statically typed .NET language that was well ahead of its time. It offered variants and pattern matching,
type inference, first-class functions and a C#-like syntax years before mainstream languages adopted them, and it had a
macro system strong enough to grow the language itself: new syntax, embedded DSLs, compile-time code generation.

It was designed at the University of Wroclaw and carried on by an open-source community for more than a decade.
This fork brings their work back on **.NET 10**:

- **Self-hosting on CoreCLR.** The compiler, runtime and macros build themselves on .NET 10. No Mono or .NET Framework
  is needed to run them.
- **A file is its namespace.** `src/util/text.n` is the module `util.text`. `namespace` declarations are gone;
  `mask` groups members inside a file, and top-level statements are the file's `Main`. See [doc/FILE-MODULES.md](doc/FILE-MODULES.md).
- **Nitra built in.** Nitra, the language workbench from the same RSDN community (copyright JetBrains, 2014), is part of
  the language. Grammars are declared with `grammar` and used in place with `space`, mapping straight back into Nemerle
  code. See [grammar/](grammar) and [native-nitra/](native-nitra).
- **Scripting.** `nscript run`, `compile` and `repl`, with NuGet references. See [scripting/](scripting).
- **Language server.** LSP for any editor, with a VS Code client in [tools/language-server/](tools/language-server).

Only .NET 10 is targeted for now. **What changed compared with upstream: [CHANGELOG.md](CHANGELOG.md).**

**Learn the language: [The Nemerle Book](doc/book/src/SUMMARY.md)**: syntax and semantics chapter by chapter, from
values to macros, grammars and scripts. Every example in it is compiled and run by the test suite.

## Hello world

```nemerle
// hello.n
using System.Console;

WriteLine("Hello world")
```

```sh
boot/coreclr/ncc hello.n -out:hello.exe && dotnet hello.exe     # compile
boot/coreclr/nscript run hello.n                                 # or run as a script
```

## Building

Requirements: the .NET 10 SDK, Python 3, and `sn` (Mono's strong-name tool, used to verify signed outputs).

```sh
./bootstrap                  # boot/coreclr -> stage 1 -> stage 2, Nitra, scripting, LSP, then every test suite
./bootstrap --quick          # fast suites only
./bootstrap --update-boot    # also replace boot/coreclr with the result when everything passed
```

The new toolchain lands in `out/bootstrap/toolchain`, with one log per step in `out/bootstrap/logs`.
`boot/coreclr` is the pinned compiler that every build starts from. Update it only when a bootstrap passes.

| Directory | Contents |
|---|---|
| `ncc/`, `lib/`, `macros/` | compiler, standard library, standard macros |
| `native-nitra/`, `grammar/` | Nitra (runtime, grammar, compiler) as file modules; grammar/space docs and examples |
| `scripting*/`, `tools/language-server/` | scripting host, NuGet adapter, language server |
| `platform/` | CLR backend adapter (C#) |
| `build/` | build scripts and `bootstrap.py`; `build/migrations/` holds the one-off source migrations |
| `tests/`, `testsuite/` | test suites and fixtures; upstream's language testsuite |
| `boot/coreclr/` | pinned .NET 10 toolchain used to bootstrap |
| `doc/` | documentation; `doc/revive/` has the notes from the port |
| `misc/` | signing keys, editor modes |
| `legacy/` | upstream's .NET Framework / Mono / Visual Studio build files and side projects, kept unchanged ([legacy/README.md](legacy/README.md)) |

The original upstream README (Windows installer, Mono, Visual Studio) is kept in
[doc/ORIGINAL-README.md](doc/ORIGINAL-README.md). Those instructions are for the original .NET Framework tree, not this fork.

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
