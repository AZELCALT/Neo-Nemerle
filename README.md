# Nemerle (revived)

Nemerle is a statically typed language for .NET with functional, object-oriented and imperative features, a C#-like
syntax and a powerful macro system. This fork brings it back on **.NET 10**:

- **Self-hosting on CoreCLR.** The compiler, runtime and macros build themselves on .NET 10. No Mono or .NET Framework is needed to run them.
- **A file is its namespace.** `src/util/text.n` is the module `util.text`. `namespace` declarations are gone;
  `mask` groups members inside a file, and top-level statements are the file's `Main`. See [doc/FILE-MODULES.md](doc/FILE-MODULES.md).
- **Nitra built in.** Grammars are declared with `grammar` and used in place with `space`, mapping straight back into
  Nemerle code. See [grammar/](grammar) and [native-nitra/](native-nitra).
- **Scripting.** `nscript run`, `compile` and `repl`, with NuGet references. See [scripting/](scripting).
- **Language server.** LSP for any editor, with a VS Code client in [tools/language-server/](tools/language-server).

Only .NET 10 is targeted for now.

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
| `native-nitra/` | Nitra (runtime, grammar, compiler) as file modules |
| `scripting*/`, `tools/language-server/` | scripting host, NuGet adapter, language server |
| `build/` | build scripts and `bootstrap.py`; `build/migrations/` holds the one-off source migrations |
| `tests/` | test suites and their fixtures |
| `boot/coreclr/` | pinned .NET 10 toolchain used to bootstrap |
| `doc/` | documentation; `doc/revive/` has the notes from the port |

The original upstream README (Windows installer, Mono, Visual Studio) is kept in
[doc/ORIGINAL-README.md](doc/ORIGINAL-README.md). Those instructions are for the original .NET Framework tree, not this fork.

## License and credits

This fork is distributed under **GPL-2.0-or-later** ([LICENSE](LICENSE)). Nemerle (University of Wroclaw, Nemerle
Project Team) and Nitra (JetBrains) remain under their original BSD licenses, and their notices are kept. See
[NOTICE.md](NOTICE.md) for details and credits. The original authors are listed in [AUTHORS](AUTHORS).
