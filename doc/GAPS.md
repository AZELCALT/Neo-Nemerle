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

## C# interop

What a C# library's metadata says beyond its members' types is read (a nullable `string?`, `init`, `required`), and
`with`, Deconstruct, `in` and `ref`-returns call into C# (chapter 12). The rest is **not yet**, not refused — none of
it violates the type system, the same way generic types were "not here yet" before they were added:

- **`params Span<T>`/`ReadOnlySpan<T>`.** Calling with a prebuilt span or array works (`F(a)`, and with other
  parameters before it); the C# 13 loose-literal sugar (`F(1, 2, 3)`) is intentionally not provided — pass an array.
- **C# 14 extension properties and static extension members.** Extension *methods* in an `extension(T) { … }` block
  already work (they emit as ordinary `[Extension]` statics); the block's properties are not imported yet.
- **Nemerle's own shapes as C# sees them** (the reverse direction). A Nemerle function type surfaces as its own
  delegate type rather than `Func`/`Action`; a value of several types surfaces as a `Content` with no C#-friendly
  read; the output carries no nullable (`?`) annotations, so C# sees the API as null-oblivious; `[Extension]` is
  written twice on an extension method. The planned route is a C# support library the output passes through to
  present these shapes, rather than emitting each one natively.

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

## Hiding members

- **Hiding stops at the access boundary and the name.** `private`, `hidden` and the folder-module rules are
  compile-time boundaries (chapter 7); a hidden member is still emitted as a CLR-private metadata row, so reflection
  in the same process can enumerate and invoke it. The CLR has no flag that hides a live, callable method from
  reflection — every metadata row is visible, and `SuppressIldasmAttribute` is a no-op on modern .NET. Past the
  boundary the only lever is obfuscating the name. The member itself is as stable as any other; what is **unstable
  is reaching for an already-private member by name** — a reflection lookup of a hidden member breaks as its
  obfuscated name changes. That is intended: depending on a private reference that way already means reverse
  engineering. Making a member genuinely unreachable through metadata (rather than only un-named) is still open and
  needs discussion before it is settled.

## Tooling

- **Renaming a type checks the workspace** (members and locals are renamed from the symbol index), and the names
  it edits are those its files' identifiers mean: a name in a string or a comment is left as it is.
- **Windows is checked by running it there, not in `./bootstrap`.** `install.ps1` runs whole under PowerShell 7 in
  `./bootstrap`'s installer check, and is written for Windows PowerShell 5.1 (its native calls, its zip and tar
  reading), but 5.1 itself and the launchers' Windows side (`hello.exe` starting `hello.dll`) are run on Windows by
  hand. The VS Code extension's Windows launch (`shell: true`) is untested.
