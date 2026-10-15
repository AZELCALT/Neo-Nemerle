# Changelog

What this fork changed compared with upstream [rsdn/nemerle](https://github.com/rsdn/nemerle) (`master`, last upstream
commit June 2026). Everything below is on top of the full upstream history, so `git log` still shows every original
commit. Detailed notes from the port are in [doc/revive/](doc/revive).

## Unreleased: the revival

### Platform: .NET 10 / CoreCLR
- The compiler, standard library and macros build themselves on .NET 10 (CoreCLR). Neither Mono nor .NET Framework is needed
  to run them.
- New CLR backend adapter in `platform/` (`Nemerle.Platform.dll`, C#). It covers emission, metadata, signing,
  resources, reference assemblies and assembly loading. Plugins such as macro libraries get an isolated load context when
  a compilation references a different build of their dependencies.
- Only .NET 10 is targeted for now. A mapping for older targets is not written yet.

### Language: a file is its namespace
- Every `.n` file is a module named by its path under the source root (`src/util/text.n` is `util.text`).
  `namespace` declarations are an error; members inside a file are grouped with `mask`.
- Top-level statements of a file, in source order, are its `Main` (as in classic Nemerle and C#).
- Rules aligned with C#, so the result is clean to use from C#:
  - a file may not sit beside a directory of the same name (CS0434);
  - no member may have its file's name (CS0542);
  - the same module path in two libraries is an error.
- `partial` is gone from source code. Macro-generated types nest into the source module of the same path, and a
  generated `partial` part completes the hand-written type.
- `-file-name-namespaces` shortens a module's name to the file name.
- The runtime (`lib/`), the macros (`macros/`), the compiler (`ncc/`) and Nitra were all migrated to this layout.
  Colliding macro paths got a `Macros` suffix (`Nemerle.CoreMacros`, `Nemerle.IOMacros`, ...). The compiler's modules
  have snake_case file names (`manager_class.n` holds `ManagerClass`). The `-legacy-namespaces` switch used during
  the migration has been removed.
- CodeDOM support writes each `CodeNamespace` to its own file module.

### Nitra in the language
- Nitra (runtime, grammar, compiler) is integrated and built from source in `native-nitra/`. Its sources are file
  modules too, one file per namespace; the moved names are listed in `native-nitra/NITRA-SYMBOLS.json`.
- `grammar` and `space` blocks are official syntax. A grammar is declared in Nemerle source and used in place, and its
  parse trees map straight back into Nemerle code (`PExpr`).
- New structural recognizer (flat region engine with a fast hybrid first pass), checked against upstream Nitra by a
  72-case differential.
- Known gap: grammars are compiled with their program, and there is no reusable compiled-grammar artifact yet.

### Tools
- **Scripting:** `nscript run`, `compile`, `run-compiled` and `repl`. Scripts can reference NuGet packages and run
  without the SDK installed.
- **Language server:** Nemerle's own parser, plus Nitra for `grammar`/`space` blocks, with a VS Code client
  (`tools/language-server/`).
- **Build:** `./bootstrap` builds everything from the pinned compiler in `boot/coreclr` and runs every test suite.
  `--update-boot` refreshes the pinned compiler once everything passes.

### Repository
- `build/` (build scripts, `bootstrap.py`, one-off migrations in `build/migrations/`) and `tests/` (suites and
  fixtures) are new. `boot/coreclr/` is the pinned .NET 10 toolchain.
- Upstream's .NET Framework / Mono / Visual Studio build files, installers, solutions, `snippets/` and
  `VsIntegration/` moved to [legacy/](legacy) unchanged. They are not built by this fork.
- Upstream's README is kept as [doc/ORIGINAL-README.md](doc/ORIGINAL-README.md) and its change log as
  [legacy/NEWS](legacy/NEWS).

### License
- The compiler and tools are GPL-2.0-or-later with the Nemerle Compiler Output Exception. The standard library, macros,
  Nitra runtime and DotNetLang stay BSD-3-Clause with their original notices. See [NOTICE.md](NOTICE.md).
