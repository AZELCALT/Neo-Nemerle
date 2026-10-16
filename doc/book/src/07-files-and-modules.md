# Files are modules

In Nemerle as revived here, **a source file is its namespace**. There are no `namespace` blocks. Where a file sits
decides the name of everything in it, and the only way to use another file is to name it.

## A file is a module

A file's module name is its path relative to the source root, with `/` replaced by `.` and without the extension:

| File | Module |
|---|---|
| `main.n` | `main` |
| `util/text.n` | `util.text` |
| `game/physics/body.n` | `game.physics.body` |

Everything declared at the top of a file is a member of its module: functions, values, classes, variants. Other files
reach them through the module's name, or open it with `using`:

```nemerle
// file: util/text.n
public Shout(s : string) : string { s.ToUpper() + "!" }
public Whisper(s : string) : string { s.ToLower() + "..." }

// file: main.n
using System.Console;
using util.text;

WriteLine(Shout("hello"));
WriteLine(util.text.Whisper("QUIET"))
```

```text
HELLO!
quiet...
```

A file's directory is never opened for it: `util/other.n` reaches its sibling as `util.text`, not as `text`. Imports
are per file, and nothing leaks from one file into another.

## Grouping inside a file: `mask`

To group members inside a file, use a `mask`. It is a named group, reached with a dot like a module:

```nemerle
// file: geometry.n
public mask circle
{
  public Area(r : double) : double { 3.14 * r * r }
  public Circumference(r : double) : double { 2.0 * 3.14 * r }
}
public mask square
{
  public Area(side : double) : double { side * side }
}

// file: main.n
using System.Console;

WriteLine(geometry.circle.Area(1.0));
WriteLine(geometry.square.Area(3.0))
```

```text
3.14
9
```

## Visibility

| Modifier | Visible to |
|---|---|
| *(none)* or `public` | everyone, including other assemblies |
| `internal` | other files of the same assembly |
| `private` | the same file (inside a mask: the mask) |

```nemerle,fail
// file: vault.n
public Open() : string { "open" }
private Combination() : int { 1234 }

// file: main.n
System.Console.WriteLine(vault.Combination())
```

```text
Combination
```

## Top-level code

Statements written at the top of a file, in source order, are the file's top-level code. Members may sit between
them. In a statement, `mutable x = ...` is a top-level value; `mutable x : T` declares a field of the module.

The program starts at `main.n`: its top-level code is the program's `Main`, as in classic Nemerle and C#. A program
with a single source file starts there whatever it is called, and `-main:file` names another file to start at.

```nemerle
using System.Console;

mutable counter : int = 40;
def twice = Twice(1);
Twice(x : int) : int { x * 2 }
WriteLine(counter + twice)
```

```text
42
```

Any other file's top-level code runs where a file imports it: `using lib.config;` runs `lib/config.n`'s top-level
code first, once for the whole program, as Python runs a module on import. A file without top-level code costs
nothing. The order of `using`s is the order in which top-level code runs, so code that depends on another file's
top-level state imports it first.

A file's top-level `def` and `mutable` are its state, kept for the program's whole run, so the file's functions can
use them. They are private to the file; `public def` lets a file that imports it read the value, always written in
full, `lib.config.name`, never as a bare `name`:

```nemerle
// file: lib/config.n
public def name = "config";
mutable count = 0;
System.Console.WriteLine("config is set up");
public Next() : int { count++; count }

// file: main.n
using lib.config;
System.Console.WriteLine("main starts");
System.Console.WriteLine(lib.config.name);
System.Console.WriteLine(lib.config.Next() + lib.config.Next())
```

```text
config is set up
main starts
config
3
```

A library's files work the same way: a program that imports a library's file runs its top-level code, so a library
can set up its state (and its scopes, see [Grammars and spaces](10-grammars.md)). Code in C# does not run it.

## The rules

The rules keep names unambiguous for Nemerle and for C# code that uses Nemerle assemblies:

- **No `namespace` declarations.** The file is the namespace:

  ```nemerle,fail
  namespace Shapes { public class Circle {} }
  ```

  ```text
  namespace declarations are not allowed
  ```

- **No `partial`.** A type lives in exactly one file.
- **A file may not sit beside a directory of the same name** (`a.n` next to `a/b.n`). The file would be a type and the
  directory a namespace with the same name, which .NET languages reject.
- **No member may have its file's name** (`text.n` cannot declare `class text`), because a class can't contain a member
  named like itself.
- **The same module path may not come from two assemblies.**

## The source root

`ncc` takes paths relative to the source root: `-source-root:DIR`, or else the current directory. Every path component
must be an identifier: `my-app/main.n` is not a valid module, `my_app/main.n` is.

With `-file-name-namespaces`, a module is named by its file name only (`util/text.n` is `text`). File names must then
be unique across the program.

## From C#

To C#, a file module is a static class, and its types are nested types. Nemerle's `util.text.Shout` is C#'s
`util.text.Shout`, and a class `Pen` declared in `util/text.n` is `util.text.Pen`. C# opens a module with
`using static util.text;`.
