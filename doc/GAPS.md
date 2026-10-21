# Known gaps

Open edges of the current design, each with what happens today. None of them lets an invalid program through silently
unless it says so. These edges will be closed, which can change what happens there: do not rely on them (see
[HOW-IT-IS-BUILT.md](HOW-IT-IS-BUILT.md#what-is-supported)).

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
  assemblies, so the compiler reads a cached copy without the reference marks (`/tmp/nemerle-reference-copies`).
  The attributes the compiler reads (`Obsolete`, `DefaultMember`, `Conditional`, `InternalsVisibleTo`) are the
  core library's and come through whole; an attribute type defined inside such a copy returns defaults if the
  compiler ever constructs one.
- **Targets not reached:** .NET Framework before 4.6.2 (the .NET Standard 2.0 `Nemerle.dll` needs 4.6.1+),
  .NET Standard 1.x, UWP and older dead platforms, and any .NET newer than the one the compiler runs on.
- **Older .NET is checked by its reference assemblies, not run** in `./bootstrap` unless that runtime is installed
  (Mono runs the `net48` checks).

## Tooling

- **Completion after a broken line elsewhere** offers the names of the file's last good check (and keywords and
  syntax forms), not names written since. A type is renamed only when its short name is unique (in the workspace and
  among the referenced libraries' types); renaming a type still checks the workspace (members and locals are renamed
  from the symbol index).
- **Windows is checked by running it there, not in `./bootstrap`.** `install.ps1` runs whole under PowerShell 7 in
  `./bootstrap`'s installer check, and is written for Windows PowerShell 5.1 (its native calls, its zip and tar
  reading), but 5.1 itself and the launchers' Windows side (`hello.exe` starting `hello.dll`) are run on Windows by
  hand. The VS Code extension's Windows launch (`shell: true`) is untested.
