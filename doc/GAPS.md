# Known gaps

Open edges of the current design, each with what happens today. None of them lets an invalid program through silently
unless it says so. These edges will be closed, which can change what happens there: do not rely on them (see
[HOW-IT-IS-BUILT.md](HOW-IT-IS-BUILT.md#what-is-supported)).

## Top-level code and state

- **Other patterns at the top level stay local.** `def (a, b) = ...` declares `a` and `b` as the file's state, but
  a pattern that can fail to match (`def [x, y] = list`, a variant pattern) binds locals of the top-level code, which
  functions cannot see; use `match` there, or a tuple.

## Scopes and spaces

- **A slot shared across copies of `Nemerle.dll` holds values, not types.** Scope storage is the process's, whichever
  copy of `Nemerle.dll` a plugin was loaded with. A value of a type the plugin loaded itself (its own copy of a
  library) is another type to the host, as anywhere in .NET; numbers, strings, framework types and the slots' own
  boxes are shared as they are.
## Targets

- **Android and Apple targets build libraries, not apps.** The app (APK, IPA) is packaged and compiled ahead of time
  by the platform's .NET workload; a Nemerle library goes into such an app project. Platform outputs are compiled
  here but not run (no device or Windows in `./bootstrap`).
- **Platform reference assemblies are read through stand-in copies.** The runtime does not load reference
  assemblies, so the compiler reads a cached copy without the reference marks, whose attribute types return
  defaults (`/tmp/nemerle-reference-copies`). An attribute whose value the compiler needs from its constructor
  would read as a default.
- **Targets not reached:** .NET Framework before 4.6.2 (the .NET Standard 2.0 `Nemerle.dll` needs 4.6.1+),
  .NET Standard 1.x, UWP and older dead platforms, and any .NET newer than the one the compiler runs on.
- **Older .NET is checked by its reference assemblies, not run** in `./bootstrap` unless that runtime is installed
  (Mono runs the `net48` checks).

## Tooling

- **Typed completion skips broken lines elsewhere.** When an unfinished line elsewhere in the file stops the
  compiler, the lines with errors are blanked and the file is typed again, so names bound only on those lines are
  not offered (keywords and syntax forms always are). A type is renamed only when its short name is unique (in the
  workspace and among the referenced libraries' types), and find-references and rename compile the whole workspace
  each time.
- **Windows installer:** `install.ps1` and `install.cmd` were run on Windows once; a .NET assembly version mismatch
  there still needs a small fix. The VS Code extension's Windows launch (`shell: true`) is untested.
