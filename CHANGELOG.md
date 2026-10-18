# Changelog

What this fork changed compared with upstream [rsdn/nemerle](https://github.com/rsdn/nemerle) (`master`, last upstream
commit June 2026). Everything below is on top of the full upstream history, so `git log` still shows every original
commit. Detailed notes from the port are in [doc/revive/](doc/revive).

## Unreleased: the revival

Open edges of the current design are listed in [doc/GAPS.md](doc/GAPS.md).

### Platform: .NET 10
- The compiler, standard library and macros build themselves on .NET 10. Neither Mono nor .NET Framework (what upstream ran on) is needed
  to run them.
- New CLR backend adapter in `platform/` (`Nemerle.Platform.dll`, C#). It covers emission, metadata, signing,
  resources, reference assemblies and assembly loading. Plugins such as macro libraries get an isolated load context when
  a compilation references a different build of their dependencies.
- Output for other targets: `-target-framework:` (and `target = "..."` in a project) builds for older .NET
  (`net5.0`+), .NET Standard 2.0/2.1 and .NET Framework 4.6.2+ / Mono. The output is moved to the target's reference
  assemblies (fetched from nuget.org by `ncc build`), every member it uses is checked against them, and programs run
  with a .NET Standard 2.0 build of `Nemerle.dll`. Platform targets (`net10.0-windows`, `-android`, `-ios`,
  `-maccatalyst`, `-macos`, `-tvos`) also fetch the platform's reference pack: Windows programs run on the desktop
  runtime, Android and Apple libraries go into apps their workloads build. Reference assemblies (which the runtime
  does not load) are read through cached stand-in copies.

### Language: a file is its namespace
- Every `.n` file is a module named by its path under the source root (`src/util/text.n` is `util.text`).
  `namespace` declarations are an error; members inside a file are grouped with `mask`.
- Top-level code: the program starts at `main.n` (or the file `-main:` names; a single-file program at its file),
  whose top-level code is `Main`. Any other file's top-level code runs once where a file imports it (`using`), as
  Python runs a module on import; its top-level `def`/`mutable` are the module's state, private, or `public def`
  reached as `file.x` by an importer. The continuation section records every module's top-level code (kind, lines,
  fingerprint, imports, state), so Nemerle binaries know each other's modules.
- Rules aligned with C#, so the result is clean to use from C#:
  - a file may not sit beside a directory of the same name (CS0434);
  - no member may have its file's name (CS0542);
  - the same module path in two libraries is an error.
- `export class Pen { }` makes a type global: one type by that name for the program and the programs that use its
  library, reached without a `using`, emitted at the top level (C#'s `Pen`); any other type of that name is an error.
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
- A `scope` is a dedicated global storage shared by the program and its spaces (and by a host application and the
  plugin scripts it runs): `scope.A.registery(...)` appends a slot, typed by the grammar or as `object`, and
  `scope.A.x` reads and writes it when the program runs. A scope belongs to its file (`app.A`) and is reached
  through `using`. A slot of no fixed type holds a `Content` (value plus its current type, checked on use); a slot
  may hold a dial member, stored as a function value, or as a Content of its forms when it has several. The runtime part is `Nemerle.Scopes.Scope` in `Nemerle.dll`.
- `grammar (A, B) { ... }` holds how grammars `A` and `B` work together (as Objective-C++ needs more than C++ and
  Objective-C side by side). A mixing space is its grammars in sorted order, then every handler whose grammars are
  all present (extensions under that condition), then the handler of exactly its set; it starts at that handler's
  start rule, else at the first grammar's. The old `runtime`/`compile`
  blocks are removed: Nitra covers them.
- Errors in grammar/space source (a misplaced space, a duplicate slot) are reported at their line and column.
- A `space` is a top-level logical file in a grammar's language. A space inside a function or a type, or used as an
  expression, is an error. The program talks to its spaces through **scopes** (shared bindings, read and written by
  both sides) and **dials** (`dial:.file.G::member(...)`; `dial:.file.(A, B)::` for a mixing space, `dial:.file::` for the plain one;
  lowered by a resolver). A plain `space { }` looks across
  grammars: its file's own, or every visible one (other files, referenced libraries) when those don't give one start
  rule. A file has one space per grammar, one per mix of grammars (in any order) and one plain space. A
  library's section stores its spaces with its scopes, so a program or plugin script can dial into them.
  `NitraSourceConfiguration.SpaceValueTarget` lets an embedding host collect a space's value.

### Continuation section
- Every output that defines grammars or macros carries a `.nemir` section with its compiled Nitra grammar (plus a
  per-declaration mark trace), its shared scopes with their bindings, a macro index, and the internal members its
  macros expand to. A compilation or script
  that references the binary continues from it. It uses the stored grammar in `space` without compiling it (120-rule
  grammar: 8.3 s to 1.5 s), recompiles only edited alternatives, and uses the binary's macros and their helpers. See
  [doc/CONTINUATION.md](doc/CONTINUATION.md).

### Tools
- **Scripting:** `nscript run`, `compile`, `run-compiled` and `repl`. Scripts can reference NuGet packages and run
  without the SDK installed.
  Libraries can declare script kinds (`[ScriptDefinition(".build.n")]`, as Kotlin's `@KotlinScript`): a script
  named `x.build.n` gets the kind's base class, imports, grammars and macros without setup lines.
- **Language server:** Nemerle's own parser, plus Nitra for `grammar`/`space` blocks, as you type; typed
  diagnostics for the workspace (across `using` and exported types), hover and go-to-definition from a background
  compile (`nemerle-lsp --check`). The VS Code / VSCodium extension ships as a `.vsix` carrying the server
  (`tools/language-server/`).
- **Projects:** a folder with a `.nproj` file (a small declarative TOML subset: name, version, references to
  assemblies, other projects and NuGet packages, compiler options) is a project; its sources are every `.n` file
  under it. `ncc init`, `ncc build`, `ncc run` and `ncc clean` make, build (incrementally, used projects first) and
  run it, and the language server reads it. Upstream's MSBuild `.nproj` files are read too (sources, references,
  project and package references, defines), into the same model.
- **Build:** `./bootstrap` builds everything from the pinned compiler in `boot/coreclr` and runs every test suite.
  `--update-boot` refreshes the pinned compiler once everything passes.

### Installation
- `install/install.sh` (Linux, macOS) and `install/install.cmd` / `install.ps1` (Windows; PowerShell 7 elsewhere) install
  the toolchain, build the language server, put `ncc`, `nscript` and `nemerle-lsp` on `PATH`, set up the VS Code /
  VSCodium extension, and uninstall again. Only the .NET 10 runtime is required.

### Documentation
- [The Nemerle Book](doc/book/src/SUMMARY.md): a guide to the language in the style of the Rust book, from values
  and functions to variants, files as modules, macros, grammars and scripts. Its 79 examples run as tests
  (`tests/check-book.py`, part of `./bootstrap`).

### Repository
- `build/` (build scripts, `bootstrap.py`, one-off migrations in `build/migrations/`) and `tests/` (suites and
  fixtures) are new. `boot/coreclr/` is the pinned .NET 10 toolchain.
- Upstream's .NET Framework / Mono / Visual Studio build files, installers, solutions, `snippets/` and
  `VsIntegration/` moved to [legacy/](legacy) unchanged. They are not built by this fork.
- Upstream's README is kept as [doc/ORIGINAL-README.md](doc/ORIGINAL-README.md) and its change log as
  [legacy/NEWS](legacy/NEWS).

### License
- The compiler, standard macros, Nitra and the tools are GPL-2.0-or-later with the Nemerle Compiler Output Exception.
  Compiled programs can be closed. Language extensions (macros and Nitra grammars, inline or as libraries) must be
  published under the GPL. The standard library stays BSD-3-Clause with its original notice. See [NOTICE.md](NOTICE.md).
