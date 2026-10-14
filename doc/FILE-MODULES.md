# A source file is its namespace

Nemerle in this fork has no namespace declarations. Every `.n` file is a module, and its name is the
file's path relative to the source root, without the extension:

| File | Module |
|---|---|
| `src/util/text.n` | `util.text` |
| `src/physics/body.n` | `physics.body` |

```nemerle
// src/app/main.n
using util.text;                 // another file: explicit path
using System.Text;               // .NET / C# namespaces work as before
public Main() : void { System.Console.WriteLine(Shout("hi")); }
mask helpers { public Two() : int { 2 } }   // a named group inside the file
```

- **Imports are per file.** A file sees another file only through `using path.to.file;` or a qualified
  name (`util.text.Shout`). Opening a directory exposes nothing, and a file's own directory is not in scope
  either: `util/other.n` reaches its sibling as `util.text`, never as `text`.
- **No `namespace` blocks and no `partial`.** A type lives in exactly one file.
- **Groups inside a file use `mask`.**
- **A file may not sit beside a directory of the same name** (`a.n` with `a/b.n`). The file would be a type and
  the directory a namespace with the same name, which C# and other .NET languages reject (CS0434).
- **The source root** is `-source-root:DIR`, else the project path (or its directory when it names a
  project file), else the current directory. Path components must be identifiers.
- **Other languages' files are not modules.** Only `.n` sources are; `.nitra` files, for example, keep
  their own rules.
- **Scripts keep their own scope.** Script compilation does not use file modules.
- **CLR shape.** A file is a static class and its types are nested in it, so C# and other .NET code write
  `util.text.Pen`, `util.text.Shout(...)` and `util.text.helpers.Two()`.
- **Quoted code keeps its file.** A name inside `<[ ... ]>` is looked up in the file that wrote the quotation
  (its module and imports), then in the types around the code it was expanded into, never in the caller file's
  top-level helpers.

## Short names: `-file-name-namespaces`

With this flag a file's namespace is its file name only (`text`, not `util.text`), both in `using` and
in the output. File names must then be unique across the compilation; a duplicate is an error that
names both files.

## The compiler's own modules

The compiler is written this way too: `ncc/Nemerle/Compiler/Typer.n` is the module `Nemerle.Compiler.Typer`
(source root `ncc`). Consumers import the modules whose names they use, `using Nemerle.Compiler.Typer;` or in
C# `using static Nemerle.Compiler.Typer;`, and qualify a class through its module
(`Nemerle.Compiler.ManagerClass.ManagerClass`). `ncc/Nemerle/Compiler/SYMBOLS.json` lists which module holds each
name; `baseline/rename-compiler-references.py` moves sources onto these paths.

## Temporary: `-legacy-namespaces`

`-legacy-namespaces` restores classic `namespace` declarations. It exists only while the compiler,
runtime, macros and Nitra sources are migrated, and it will be removed when that is done. Build scripts
pass it through `baseline/ncc_flags.py`, which adds it only for compilers that know it.
`-file-modules` is still accepted and does nothing.
