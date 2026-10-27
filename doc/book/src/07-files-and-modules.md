# Files are modules

In Nemerle as revived here, **a source file is its module**. There are no `namespace` blocks. Its path supplies its
name by default; `register` gives the whole file a logical folder instead. Other files use its module name.

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

A file's directory is not opened implicitly. `util/other.n` can explicitly open its sibling with `using text;`,
or use the full name `util.text`. Imports are per file, and nothing leaks from one file into another.

Use `using the_symbol.file_name;` to open a file module: the dotted prefix identifies its containing path, and the
last component identifies the file without `.n`. For example, `using game.physics.body;` opens the module from
`game/physics/body.n`. The same spelling works when that module comes from a referenced Nemerle library.

`using` performs name lookup in the current compilation and its referenced .NET assemblies. It can open a file
module, a mask, or a CLR namespace such as `System`; a separate `import` keyword is not needed. Named local `.n`
sources are discovered beside the importing file and under the source root, including their own imports. External
assembly references still belong in the [project file](13-projects.md#the-project-file) or compiler options.
Opening a containing folder, such as `using game.physics;`, makes its immediate file names available for qualified use.

## Logical folders: `register`

Write `register the_symbol;` as the first directive of a file, before its `using`s and declarations. It replaces the
physical containing path with a logical folder. The filename still supplies the final component:

```nemerle
// file: implementation/text.n
register library.words;
public Shout(s : string) : string { s.ToUpper() }

// file: main.n
using library.words.text;
System.Console.WriteLine(Shout("hello"))
```

```text
HELLO
```

The module is `library.words.text`, wherever `text.n` sits under the source root. Moving it to another directory
preserves that identity; renaming the file changes the final component. `implementation.text` is no longer an
alternative name. The declaration applies to the entire file: one registration, no blocks, and no splitting a file
between logical folders. Two files cannot own the same module name. Registration does not change visibility; it
works the same way in a library, whose consumers use the registered name.

## Shorter qualification: using a folder

`using library.words;` makes the immediate file names in that physical or logical folder available. Each use
still names its file; the files' members do not become bare names:

```nemerle
// file: implementation/text.n
register library.words;
public Shout(s : string) : string { s.ToUpper() }

// file: main.n
using library.words;
System.Console.WriteLine(text.Shout("hello"))
```

```text
HELLO
```

Here `text.Shout(...)` works, while bare `Shout(...)` requires `using library.words.text;`. Subfolders are not opened
recursively. A folder import opens its immediate modules in ordinal name order, including their normal top-level
initialization. It works with source modules and modules from referenced Nemerle libraries. As with other `using`s,
an unresolved namespace is diagnosed, and a name it cannot supply fails where it is used. A standalone compiler
invocation warns when no `.nproj` is present, then continues. Scripts resolve local sources without that warning.
Neither mode fetches DLLs or packages merely because a name appears in `using`.

For one file with a chosen short name, use `using Words = library.words.text;`.

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
`y' is int or string (declared at lines 1, 2): it is a top-level value, and this code can run at any time
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

Other .NET languages see a top-level value of several types as what it is stored in, a `Nemerle.Scopes.Content`
(its `Value`, and the `Type` it currently is). Its field says which types it can be, with
`[Nemerle.Scopes.ContentTypes(typeof(int), typeof(string))]`, so C# code (and its tools) can read them by reflection
and check for each.

The type of a top-level value changes in the top-level code only. A function of the file that assigns it gives it a
value of a type it already has there: another type is an error, as anywhere a value's type is fixed. Since such a
function can assign it at any time (an async function's assignment comes later), the top-level code then reads it
from its storage too, and checks it when it has several types.

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

A type is declared once, in the file that exports it, and `export` is how it is shared. Only types are exported;
functions and top-level values are reached through their file.

## Adding to a type: `extend`

Other files add to an exported type with `extend`: fields, properties, methods, and interfaces it implements. The
compiler gathers what each file adds into the type, then builds and checks it whole, as if it had been written in one
place:

```nemerle
// file: lib/shapes.n
export interface IDrawable { Draw() : string; }
export class Pen
{
  public mutable Width : int = 3;
}

// file: styles.n
extend Pen : IDrawable
{
  public mutable Color : string = "red";
  public Draw() : string { $"$Color pen, $Width wide" }
}

// file: main.n
def pen = Pen();
pen.Color = "blue";
def shown : IDrawable = pen;
System.Console.WriteLine(shown.Draw())
```

```text
blue pen, 3 wide
```

The type is still one type: a member written twice is an error, wherever each is written, and what it derives from
is said where it is exported (an `extend` adds interfaces, not a base class). `extend` adds to an exported type only:

```nemerle,fail
// file: main.n
extend Brush { public Size : int = 1; }
System.Console.WriteLine(1)
```

```text
no type `Brush' is exported
```

A type can also be extended after it is compiled: a program, or a script a host loads, extends a type of a library
it uses. Every exported class carries an extension slot for that (a field the compiler adds, hidden from other .NET
languages), and what an `extend` compiled later adds lives there, made the first time it is used on an object:
objects made before the script was loaded have it too, with its fields at their initial values. Inside such an
`extend`, `this` is the object and the type's own public members are named as in the type. It adds fields, properties
and methods; the type's interfaces, and its static members, are where it is compiled.

## The rules

The rules keep names unambiguous for Nemerle and for C# code that uses Nemerle assemblies:

- **No `namespace` declarations.** The file owns one module name, optionally under a registered logical folder:

  ```nemerle,fail
  namespace Shapes { public class Circle {} }
  ```

  ```text
  namespace declarations are not allowed
  ```

- **No `partial`.** A type is declared in exactly one file; other files add to it with `extend`.
- **A module may not have the same name as a containing folder** (`a.n` next to `a/b.n`, unless registration separates
  their identities). The file would be a type and the
  directory a namespace with the same name, which .NET languages reject.
- **No member may have its file's name** (`text.n` cannot declare `class text`), because a class can't contain a member
  named like itself.
- **The same module path may not come from two assemblies.**

## The source root

`ncc` takes module paths relative to the source root: `-source-root:DIR`, otherwise the containing project root,
or the first source file's directory for a standalone compilation. Scripts start at their own directory. Every path component
must be an identifier: `my-app/main.n` is not a valid module, `my_app/main.n` is.

With `-file-name-namespaces`, a module is named by its file name only (`util/text.n` is `text`). File names must then
be unique across the program.

## From C#

To C#, a file module is a static class, and its types are nested types. Nemerle's `util.text.Shout` is C#'s
`util.text.Shout`, and a class `Pen` declared in `util/text.n` is `util.text.Pen`. C# opens a module with
`using static util.text;`.
