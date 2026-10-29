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

### `dynamic` values

A C# member typed `dynamic` (a JSON reader's value, a COM object, a scripting bridge) gives a value whose type nobody
knows, not even as a set of types. C# then looks its members up at run time; Nemerle checks it before anything uses
it instead. Binding it to a name, matching on it and converting it are the checks; every other use is an error,
wherever it is (a member, an argument, an operator, an assignment, a result, a lambda):

```nemerle,ignore
def data = Reader.Value(json);       // a C# `dynamic`: bound, not used yet
def size = match (data)
{
  | s is string => s.Length          // here it is a string
  | n is int    => n
  | _           => 0                 // and anything else it may be
};
def ratio = Reader.Ratio :> double;  // a conversion is a check too (it throws when it is not one)
WriteLine(data.ToString())           // error: `data' is dynamic: check what it is before using it
```

Matching with a plain name (`| o => ...`) takes it as an `object`. Only a value whose type is `dynamic` as a whole is
checked; a `List<dynamic>` is a list (its elements are objects).

### Values C# declares nullable

A C# member typed `string?` (any nullable reference) gives a value that is a string or null. It is passed, compared,
bound and returned like any value, but a member of it is reached only where it is checked:

```nemerle,ignore
def name = Api.Find(id);                 // a C# `string?`
def a = if (name != null) name.Length else 0;
def b = match (name) { | null => 0 | n => n.Length };
def c = name?.Length;                    // null if it is null
def d = string.IsNullOrEmpty(name) || name.Length > 3;   // C# marks IsNullOrEmpty [NotNullWhen(false)]
def e = (name :> string).Length;         // a cast is the check: it throws NullReferenceException if it is null
when (name == null) throw ArgumentException(); // from here on it is not null (so after assert (name != null) too)
WriteLine(name.Length)                   // error: `name' can be null here (C# declares it `?')
```

A cast to the type the value has, `name :> string`, is the check. A cast to another type is .NET's as always (a null
stays null). Everything C# does not mark `?` is not null, as everywhere in .NET, and `ToString()` is never null.

### init, required, in, ref, records

The rest of what C#'s metadata says beyond the types is kept too:

- An `init` property is set where the object is made: `Settings() <- { Port = 80 }`. Setting it later is an error.
- A type's `required` members must all be set by that initializer, unless its constructor sets them itself.
- An `in` parameter takes a plain value, `Api.Measure(size)`, as C# does. `ref size` works too.
- A `ref` result can be written: `Api.At(0) = 42`, `Api.At(1) += 5`, `span[0]++`. A `ref readonly` one can't.
- A record's (any type's) `Deconstruct` is a positional pattern: `def (x, y) = point`, `| Point(0, y) => ...`.
  That works when its values are members of their names. Otherwise call it: `p.Deconstruct(out a, out b)`.
- `with` copies a record or a struct with some members changed: `def moved = point with { X = 5 }`.

### Extension members

A C# extension method is called as a member: `text.Shout()` is the static `Ext.Shout(text)`. C# 14 extension
properties and static extension members work the same way — a C# `extension` block adds instance members *and* static
members to a type, and Nemerle reaches all of them:

```nemerle,ignore
// C#
public static class Ext {
  extension(string s) {
    public int Twice => s.Length * 2;           // instance property
    public string Shout() => s.ToUpper();        // instance method
  }
  extension(string) {
    public static string Blank => "";            // static property, reached through the type
    public static string Of(int n) => new string('*', n);  // static method
  }
}

// Nemerle
def s = "hi";
WriteLine(s.Twice);          // 4   -- instance property, through its getter
WriteLine(s.Shout());        // HI  -- instance method
WriteLine(string.Blank);     //     -- a static member, reached through the type `string'
WriteLine(string.Of(3))      // *** -- a static method, same way
```

A property write goes through its setter (`s.Tag = 7`, `string.Slot = 3`). Every one of these also has an
extension-dot spelling, `.:`, which says "this is an extension" where a plain `.` would read as a real member:
`s.:Twice`, `s.:Shout()`, `string.:Blank`, `string.:Of(3)`. The plain static call is always available too:
`Ext.Shout(s)`, `Ext.Of(3)` are ordinary static methods.

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

A delegate type is declared with `delegate`, and an event with `event`: other code subscribes with `+=` and leaves
with `-=`, and the type that declares it raises it by calling it:

```nemerle
using System;
using System.Console;

public delegate Combine(a : int, b : int) : int;

public class Button
{
  public event Clicked : EventHandler;
  public Click() : void { when (Clicked != null) Clicked(this, EventArgs.Empty) }
}

def add = Combine((a, b) => a + b);
WriteLine(add(2, 3));

def button = Button();
def onClick = EventHandler((_, _) => WriteLine("clicked"));
button.Clicked += onClick;
button.Click();
button.Clicked -= onClick;
button.Click();
WriteLine("done")
```

```text
5
clicked
done
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

## Async functions

A function written `async` returns a `Task[T]` (or `Task`, `ValueTask[T]`, `ValueTask`, or `void`), and `await e` in
it waits for `e`, anything with a `GetAwaiter()` as a `Task` has, without blocking the thread: the rest of the function
runs when `e` completes, and `await` is its value. `async` and `await` are names otherwise; they are words of the
language only where they mean this.

```nemerle
using System;
using System.Threading.Tasks;

Fetch(name : string) : Task[string] { Task.Run(() => name.ToUpper()) }

async Greet(names : list[string]) : Task[int]
{
  mutable count = 0;
  foreach (name in names)
  {
    Console.WriteLine("hello " + await Fetch(name));
    count++
  }
  count
}

def greeted = await Greet(["ada", "alan"]);
Console.WriteLine($"$greeted greeted")
```

```text
hello ADA
hello ALAN
2 greeted
```

An `await` can be anywhere in the function's code: in a loop, in a condition, inside an expression (what is written
before it there is evaluated first, as without it, and `&&` and `||` still evaluate their right side only when
needed), in a `try` and in its `catch` and `finally` handlers. What the function throws completes its task with that
exception, which `await` on the task throws again, with its original stack trace; an `OperationCanceledException`
cancels it. A `return` (from `Nemerle.Imperative`) ends the function with its value; a `break`, `continue` or
`return` out of a `try` runs its `finally` first, also one that waits. A `void` async function is for an event
handler: nothing waits for it, and what it throws ends the process, as in C#.

As in C#, an async function is compiled to a *state machine*: a struct that keeps its locals between its waits.
A function that finishes without waiting allocates nothing, and one that waits moves the struct to the heap once.
An async lambda's is a struct too, and the locals that lambdas in a function share are a class's, which the struct
has (as C#'s display class).

An `async` function cannot have `ref` or `out` parameters, and the compiler refuses an `await` where it cannot work:

- in a `lock`: the rest of the body may run on another thread, which cannot release the lock (wait with
  `SemaphoreSlim.WaitAsync()` instead);
- in a lambda or local function that is not async (write it `async`, below);
- with a span in the function: its locals are kept between its waits, where a ref struct cannot be.

A lambda or local function is async when written so: `async (x) => ...`, `async x => ...`, `async fun (x) { ... }`
and `async def f(x) : Task[T] { ... }`. Its body waits as an async function's does, and it returns a `Task[T]`, or a
`Task` when its body has no value (given where a `Func[ValueTask[T]]` is wanted, a `ValueTask[T]`). One given where
a `void` delegate is wanted, an event handler, is started and not waited for, as C#'s `async void`: what it throws
ends the process, unless handled. A local function that returns `IAsyncEnumerable[T]` is a local async stream
(below), as in C#.

```nemerle
using System;
using System.Threading.Tasks;

def slowly = async (x : int) => { await Task.Delay(10); x * 2 };
def total = await Task.WhenAll(Task.Run(async () => await slowly(1)), slowly(2));
Console.WriteLine(total[0] + total[1])
```

```text
6
```

An async function that returns `IAsyncEnumerable[T]` is an *async stream*: it waits with `await` and produces its
items with `yield`, and `await foreach (x in stream)` goes over one, waiting for each item. `await using (x = value)`
disposes an `IAsyncDisposable` at the end, waiting for it. A loop that stops early (a `break`) disposes of the
stream, which runs its `finally` blocks, as C#'s does; a parameter marked `[EnumeratorCancellation]` is the token
the stream is enumerated with (`stream.WithCancellation(token)`). Each item allocates nothing. On .NET Standard 2.0
and .NET Framework, which have no `IAsyncEnumerable[T]`, a project uses the `Microsoft.Bcl.AsyncInterfaces` package
for them, as a C# project does.

```nemerle
using System;
using System.Collections.Generic;
using System.Threading.Tasks;

async Squares(count : int) : IAsyncEnumerable[int]
{
  for (mutable i = 1; i <= count; i++)
  {
    await Task.Delay(1);
    yield i * i
  }
}

mutable sum = 0;
await foreach (n in Squares(4)) sum += n;
Console.WriteLine(sum)
```

```text
30
```

The same as a local function, in a function or in top-level code:

```nemerle
using System;
using System.Collections.Generic;
using System.Threading.Tasks;

async def Countdown(from : int) : IAsyncEnumerable[int]
{
  for (mutable i = from; i > 0; i--) { await Task.Yield(); yield i }
}

await foreach (n in Countdown(3)) Console.Write(n);
Console.WriteLine()
```

```text
321
```

An async function runs on the runtime's own task builders, as C#'s does (one that completes without waiting makes no
task of its own beyond the result), and debugs as C#'s does: a breakpoint stops after an `await`, a step goes over
an `await` to the line after it, the debugger shows its locals, and a stack trace names the function.

A program's top-level code can `await` as well, and so can any file's: a file whose top-level code waits is an
*async file*, and so is a file that imports one. Its top-level code runs once, as any file's does, where a file
imports it, in `using` order, and the importing file waits for it there; its state is ready when the code after the
`using` runs. A function of the file called before that (from a file that does not import it, or from C#) waits for
its top-level code to end: an async one awaits it, another blocks until it has, as a type's members wait for its
static constructor; so does its public state, which other code (C# too) reaches through a property, a field's read
being one instruction that could wait for nothing. The file's own code does not wait for itself.

```nemerle
// file: lib/settings.n
using System.Threading.Tasks;
public def name = await Task.Run(() => "loaded");

// file: main.n
using lib.settings;
System.Console.WriteLine(lib.settings.name)
```

```text
loaded
```

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
