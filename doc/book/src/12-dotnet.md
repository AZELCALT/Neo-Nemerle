# Working with .NET

Nemerle compiles to ordinary .NET assemblies. It uses any .NET library, and C# uses Nemerle's.

## Using .NET libraries

Classes, structs, interfaces, events, generics and extension methods from .NET work as they do in C#:

```nemerle
using System.Console;
using System.Linq;
using System.Text;

def builder = StringBuilder();
_ = builder.Append("Ne").Append("merle");
WriteLine(builder.ToString());

def evens = Enumerable.Range(1, 10).Where(n => n % 2 == 0).Select(n => n * n);
WriteLine(string.Join(", ", evens));

def now = System.DateTime(2026, 10, 15);
WriteLine(now.ToString("yyyy-MM-dd"))
```

```text
Nemerle
4, 16, 36, 64, 100
2026-10-15
```

Generic arguments go in square brackets: C#'s `List<int>` is `List[int]`. A method's own generic arguments, when you
must give them, are written `.[T]`: `Enumerable.Empty.[int]()`.

`ncc -r:library.dll` references a library. The .NET framework itself is available by default.

## Delegates and events

A Nemerle function value converts to a .NET delegate wherever one is expected:

```nemerle
using System.Console;

def numbers = System.Collections.Generic.List([5, 3, 8]);
numbers.Sort((a, b) => b.CompareTo(a));
WriteLine(string.Join(" ", numbers));

def handler = System.EventHandler((_, _) => WriteLine("clicked"));
handler(null, System.EventArgs.Empty)
```

```text
8 5 3
clicked
```

## Being used from C#

A Nemerle library is a normal .NET assembly. Its public classes, variants (as class hierarchies), interfaces and
generics look like C# types. Two things are specific:

- **Files are static classes.** `util/text.n` is C#'s static class `util.text`. Its types are nested in it
  (`util.text.Pen`), and `using static util.text;` opens it.
- **Nemerle's own types** (`list[T]`, `option[T]`, function types) come from `Nemerle.dll`, which a C# project
  references along with the library.
- **Exported types are at the top level**: `export class Pen` is C#'s `Pen`.
- **C# does not run a file's top-level code.** A Nemerle `using` runs it; C# has no such step. C# can use a Nemerle
  library that does not depend on its top-level code, and Nemerle can use any C# library.

```nemerle,ignore
// file: geometry/shapes.n   (compiled to geometry.dll)
public Area(radius : double) : double { 3.14159 * radius * radius }

// C#
using static geometry.shapes;
System.Console.WriteLine(Area(2.0));
```

## Spans

`Span[T]`, `ReadOnlySpan[T]` and `Memory[T]` are used as in C#: a span views part of an array or a string without
copying it, its indexer reads and writes through the view, and `foreach` goes over it.

```nemerle
using System;

Sum(values : Span[int]) : int
{
  mutable total = 0;
  foreach (x in values) total += x;
  total
}

Show() : string
{
  def data = array[1, 2, 3, 4];
  def view = Span.[int](data);
  view[0] = 10;                                  // writes data[0]
  def words = "hello world".AsSpan();
  $"$(data[0]) $(Sum(view.Slice(1, 2))) $(words.Slice(words.IndexOf(' ') + 1).ToString())"
}

Console.WriteLine(Show())
```

```text
10 5 world
```

A span is a *ref struct*: it lives on the stack only, so it is a parameter or a local of a function, and the compiler
refuses, where it is written, what the runtime would refuse:

- a top-level value holding one (a top-level value is the file's state, a field);
- a lambda or local function using one (it would keep it in its closure);
- boxing it, making it an `object` or an interface (`$"$span"` does: write `span.ToString()`);
- putting it inside another type: a list, an `option`, a tuple, an array.

When a method has both a span overload and another (`WriteLine(string)` and `WriteLine(ReadOnlySpan[char])`), a call
uses the other one, and an extension method on spans applies to a span itself, not to an array or string that would
convert to one: `array.Contains(x)` is LINQ's.

## Older .NET, .NET Framework and Mono

The compiler runs on .NET 10, and builds for it by default. `-target-framework:NAME` with that target's reference
assemblies (`-target-references:DIR`) builds for another: `net8.0`, `netstandard2.0` (libraries for every runtime,
Unity included), or `net48` (.NET Framework and Mono). A project says `target = "..."`, and `ncc build` fetches the
reference assemblies itself (chapter 13). What the target does not have is a compile error.

## The continuation section

Every assembly that defines grammars or macros carries a `.nemir` section. It holds the compiled grammars with a trace
of their declarations, an index of the macros, and the internal helpers those macros expand to. Compilations and
scripts that reference the assembly continue from it, so they use its grammars, macros and helpers directly.
`doc/CONTINUATION.md` describes it; `-no-continuation-section` turns it off.
