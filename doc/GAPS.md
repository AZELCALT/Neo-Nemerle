# Known gaps

Open edges of the current design, each with what happens today. None of them lets an invalid program through silently
unless it says so. These edges will be closed, which can change what happens there: do not rely on them (see
[HOW-IT-IS-BUILT.md](HOW-IT-IS-BUILT.md#what-is-supported)).

## Scopes and spaces

- **A value of another copy of a type is copied when a slot is read** (chapter 11, scripts as plugins). The reader
  gets its own copy, not the writer's object: writing to it changes nothing in the slot until it is written back.
  Arrays of such values are copied too; a generic collection of them (`List[Point]`) is not, and reading one as
  the other copy's is an error that names both. A script that references a library its host has loaded shares the
  host's copy, so none of this applies there.

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

- **Renaming a type checks the workspace** (members and locals are renamed from the symbol index), and the names
  it edits are those its files' identifiers mean: a name in a string or a comment is left as it is.
- **Windows is checked by running it there, not in `./bootstrap`.** `install.ps1` runs whole under PowerShell 7 in
  `./bootstrap`'s installer check, and is written for Windows PowerShell 5.1 (its native calls, its zip and tar
  reading), but 5.1 itself and the launchers' Windows side (`hello.exe` starting `hello.dll`) are run on Windows by
  hand. The VS Code extension's Windows launch (`shell: true`) is untested.
