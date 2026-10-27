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
- **No `namespace` blocks and no `partial`.** A type is declared in exactly one file; `extend T { ... }` in another
  file adds members and interfaces to the exported type `T` (its parts are gathered, then it is built and checked
  whole), and to a type compiled already through its extension slot (`lib/Nemerle/Extend.n`).
- **Groups inside a file use `mask`.**
- **Top-level statements are the file's `Main`.** Statements written at file level, in source order, become
  `public Main() : void` of the module, as in classic Nemerle and C#. Members may sit between them; a statement's
  `def`/`mutable` locals are locals of `Main`. `mutable x : T ...` is a field; `mutable x = ...` without a type is a local.
- **No member has its file's name.** The file is a class, and as in C# (CS0542) a member cannot have the name
  of its enclosing type: `typer.n` may hold `class Typer`, but `Typer.n` may not.
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

The compiler is written this way too: `ncc/Nemerle/Compiler/typer.n` is the module `Nemerle.Compiler.typer`
(source root `ncc`), holding the class `Typer`. Consumers import the modules whose names they use,
`using Nemerle.Compiler.typer;` or in C# `using static Nemerle.Compiler.typer;`, and qualify a class through its
module (`Nemerle.Compiler.manager_class.ManagerClass`). `ncc/Nemerle/Compiler/SYMBOLS.json` lists which module holds
each name; `build/migrations/rename-compiler-references.py` and `rename-compiler-modules.py` move sources onto these paths.

## Nitra

Nitra's sources follow the same rule, one file per (dll, namespace): `native-nitra/upstream/Nitra/<project>/<Ns path>.n`
(source root = the project directory), sub-namespaces as masks. Names that moved are listed in
`native-nitra/NITRA-SYMBOLS.json`: the root `Nitra` types are `Nitra.Runtime.*` (C# `Nitra.Runtime+Location`), the
compiler's macros under paths other dlls own are `NitraMacros`, `Nitra.InternalMacros` and `Nitra.Serialization2Macros`.
Grammars (`.nitra`) keep their own `namespace` syntax; the code Nitra generates nests in the source module of the
same path, and a generated `partial` part completes the hand-written type.

## Hosts

Every compilation is file modules (scripts keep their own scope). A host that compiles text names each source by a path
under `SourceRoot` that is a valid module path: NativeSourceHost's stub is `NativeGrammar_<guid>.n` under its own
directory, and the CodeDOM compiler writes each `CodeNamespace` to `<Ns path>.n` (types outside a namespace to
`Global.n`, source text to `Source<i>.n`) under a fresh temporary root.
