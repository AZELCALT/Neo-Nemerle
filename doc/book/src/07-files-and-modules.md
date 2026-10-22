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

In the file a program starts at, the top-level code has the command-line arguments as `args` (an `array[string]`),
as a script has: `ncc run -- one two` or `./hello one two` gives `args` the two words.

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

A tuple on the left declares several values at once: `def (w, h) = (800, 600);` is `def w = 800; def h = 600;`, two
values of the file, each its own state. The tuple itself has no name, so there is nothing else to keep. With a value
that is not written out as a tuple (`def (w, h) = Size();`), the value is computed once and taken apart. `mutable (x, y)`
declares both mutable, and `public def (a, b)` both public. Any other pattern declares its names the same way, and
must fit every value or have an `else` ([Patterns in `def`](04-variants-and-matching.md#patterns-in-def)):

```nemerle
def (w, h) = (800, 600);
mutable (x, y) = (0, 0);
Area() : int { w * h }
Move() : void { x += 10; y += 5 }
Move();
System.Console.WriteLine($"$(Area()) at $x, $y")
```

```text
480000 at 10, 5
```

What a macro declares at the top level is the file's state too, as if written there: a macro `counter(name)` that
expands to `mutable $name = 0` makes `counter(hits);` a value `hits` of the file, which its functions see. (The macro's
own names, its temporaries, stay its own.)

A name is found from the closest scope out: a function's parameter or local first, then the file's top level, then
what the file imports. When a closer name hides a top-level one, `top name` reaches the top level:

```nemerle
mutable count = 1;
Add(count : int) : int { count + top count }       // the parameter, then the file's count
Name() : string { "file" }
Show() : string { def Name() { "local" }; Name() + " and " + top Name() }
System.Console.WriteLine($"$(Add(10)): $(Show())")
```

```text
11: local and file
```

`top` is no keyword: `top name` is the only meaning of two names side by side, so a variable called `top` (`top.x`,
`top + 1`) is as before.

A top-level value's type comes from the whole top-level code: `mutable items = [];` is a list whose element type a
later `items ::= 1` gives. A function, a lambda or a local function reads the value's storage, so it may be written
above the value's binding and sees whatever the storage holds when it runs. Binding a name again writes the same
storage: `def x = 5; def x = x * 2;` leaves 10.

A top-level value follows the rules of chapter 2: a `def` bound again, or a `mutable` without a type, may change
type, and the top-level code knows its type after each binding or assignment. Its storage is of that one type, or a
container when the type changes (which the compiler handles). Code outside the top-level code (a function, a lambda)
reads the value whenever it runs, so it does not rely on any one of its types: it checks it first, with `match` or
`if (x is T)`, which give it the value as the type checked. A use without a check is an error there:

```nemerle,fail
def y = 5;
def y = y.ToString();
Twice() : int { y * 2 }
System.Console.WriteLine(Twice())
```

```text
`y' is a top-level value of several types (int, string)
```

```nemerle
def y = 5;
def y = y.ToString() + "!";
Shout() : string { match (y) { | s is string => s.ToUpper() | _ => "a number" } }
System.Console.WriteLine(Shout())
```

```text
5!
```

A top-level `mutable` that a function of the file assigns can change at any time (an async function's assignment
comes later): the top-level code reads it from its storage too, and checks it when it has several types.

Before its first binding a value does not exist yet. Reading it there gives `NotYet`, which nothing accepts:

```nemerle,fail
System.Console.WriteLine(z);
def z = 1;
```

```text
`z' is NotYet here: its top-level binding is at line 2
```

A top-level `mutable x;` written without a value declares `x` but does not give it one: its first value is the first
top-level `x = ...`, and reading it before that is NotYet too. The error says where it gets its first value, or that it
never gets one.

Files that import each other while one of them has top-level code are reported. An imported file's top-level code
runs in its type initializer, which holds the file's lock until it ends: starting a thread or task there is warned,
and work that uses the file while the top-level code waits for it (as `Parallel` always does) is an error, since it
could never run. The compiler judges the calls themselves, however they are written.

A library's files work the same way: a program that imports a library's file runs its top-level code, so a library
can set up its state (and its scopes, see [Grammars and spaces](10-grammars.md)). Code in C# does not run it.

## Global types: `export`

A type lives in its file: `util/text.n`'s `Pen` is `util.text.Pen`, reached through `using util.text;` or its full
name. `export` makes a type global instead: one type by that name for the whole program, reached anywhere by its name
alone, and by programs that use the library it is in. It still comes from its file; importing that file is the same
type, not a second one.

```nemerle
// file: lib/shapes.n
export class Pen
{
  public Name() : string { "the global pen" }
}

// file: main.n
System.Console.WriteLine(Pen().Name())
```

```text
the global pen
```

Because the name is the type's everywhere, no other type can have it, in any file, mask or referenced library:

```nemerle,fail
// file: lib/shapes.n
export class Pen { }

// file: main.n
class Pen { }
System.Console.WriteLine(1)
```

```text
is exported by lib.shapes as a global type, so no other type can have that name
```

This is why `partial` is not needed: a type has one definition in one file, and `export` is how it is shared.
Only types are exported; functions and top-level values are reached through their file.

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
