# Known gaps

Open edges of the current design, each with what happens today. None of them lets an invalid program through silently
unless it says so. These edges will be closed, which can change what happens there: do not rely on them (see
[HOW-IT-IS-BUILT.md](HOW-IT-IS-BUILT.md#what-is-supported)).

## Scopes and spaces

- **A slot's type is one .NET type.** A plugin compiled against the binary that declares the scope uses that binary's
  types (chapter 11, scripts as plugins). Two binaries compiled apart, each with its own copy of a type, cannot share
  a value of it: .NET makes an object of one copy, and Nemerle does not convert it (a copy would be another value).
  Reading or writing the slot with the other copy is an error that says so; a slot of no fixed type (a `Content`)
  takes either.

## Values

- **A top-level value's types are those the top-level code gives it.** Its storage (one type, or a container) is
  decided from the top-level code. When that code gives it one type, a function of the file that assigns it a value
  of another type is an error there (`expected int`), as before; a container takes any. A function's own locals
  follow the flow in full.

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
