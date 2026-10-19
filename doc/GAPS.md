# Known gaps

Open edges of the current design, each with what happens today. None of them lets an invalid program through silently
unless it says so.

## Top-level code and state

- **Threads: indirect use is not proven.** In an imported file's top-level code, work started through `Thread`, `Task`,
  `Parallel`, `ThreadPool` or `Timer` is an error only when it refers to the file's own members (in its lambda too)
  and the top-level code waits. Work that reaches the file only through another file's function gets the warning, not
  the error, though it can deadlock the same way.
- **Threads: any wait counts.** A `Wait`, `Join`, `.Result` or `GetResult` anywhere in the top-level code counts as
  waiting for every task started there, not only for the task it is called on.
- **Type changes: names are matched by spelling.** A function parameter with the value's name hides it, but a lambda
  parameter or a local of the same name inside a function is still read as the top-level value.
- **The inference pass expands macros twice.** It types a copy of the top-level code, so macros used there expand once
  for it and once for the real code. The compiler's own macros (spaces, scopes, dials) are safe to repeat; a user
  macro with side effects sees both expansions. When the pass fails, a value's type falls back to its first
  initializer, as before the pass existed.
- **Tuple destructuring stays local.** `def (a, b) = ...` at the top level binds locals, not state; `def pair = (a, b)`
  is the form functions can reach. A nicer way to reference tuple parts is not designed yet.

## Scopes and spaces

- **Scope storage is per runtime copy of `Nemerle.dll`.** Scripts share the host's storage because the script loader
  takes `Nemerle.dll` from the host. A plugin loaded by other means with its own copy of `Nemerle.dll` gets its own,
  empty storage.
- **The top-level rule for spaces is token-level.** A space must stand at the top level of its file; the check looks
  at the tokens before it, not at the parsed tree.

## Targets

- **The target check names a line only with debug information.** Without `-debug+`, a member the target lacks is
  reported with the method that uses it, not its line.
- **Unused references to .NET 10 assemblies stay in the output.** After the output is moved to the target's
  assemblies, references nothing uses any more are kept (removing them corrupts lazily read signatures). They are
  never loaded, so the binary runs; a strict checker (Unity's) may still list them.
- **Old MSBuild `TargetFrameworkVersion` is not read.** `v3.5`/`v4.0` name frameworks this toolchain does not
  target; an SDK-style `TargetFramework` is read.
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

- **Debugging needs netcoredbg installed.** The extension finds it on `PATH` (or `nemerle.debugger.path`) and
  points to its releases otherwise; the installers do not fetch it.

- **Typed completion skips broken lines elsewhere.** When an unfinished line elsewhere in the file stops the
  compiler, the lines with errors are blanked and the file is typed again, so names bound only on those lines are
  not offered (keywords and syntax forms always are). Types are not renamed yet (type annotations are not facts),
  and find-references and rename compile the whole workspace each time.
- **Windows installer:** `install.ps1` and `install.cmd` were run on Windows once; a .NET assembly version mismatch
  there still needs a small fix. The VS Code extension's Windows launch (`shell: true`) is untested.
