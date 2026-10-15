# Macros

A macro is a function that runs inside the compiler. It receives code and returns code. Much of what looks like built-in
syntax is macros: `when`, `unless`, `foreach`, `repeat`, string interpolation and `[Record]`. You can write your own,
and they look exactly like the built-in ones.

## Using macros

Macros come from libraries and are opened with `using`, like functions. A few useful standard ones:

```nemerle
using System.Console;
using Nemerle.IOMacros;     // printf, sprintf
using NemerleMacros;        // lazy
using Nemerle.Imperative;   // break, continue, return

printf("%d + %d = %d\n", 2, 3, 2 + 3);

def value = lazy({ WriteLine("computing"); 42 });
WriteLine("before");
WriteLine(value.Value);

foreach (n in [1, 2, 3, 4, 5])
{
  when (n == 4) break;
  Write(n)
}
WriteLine()
```

```text
2 + 3 = 5
before
computing
42
123
```

## Writing a macro

A macro is declared with `macro` in a library that references `Nemerle.Compiler.dll`. Its body builds code with a
*quotation*, `<[ ... ]>`, and `$name` splices code in:

```nemerle,lib=mymacros
// ncc: -r:{toolchain}/Nemerle.Compiler.dll
// file: mymacros.n
using Nemerle.Compiler;

macro twice(e)
{
  <[ $e * 2 ]>
}

macro swap(a, b)
{
  <[ def tmp = $a; $a = $b; $b = tmp ]>
}
```

A program that references the library uses the macros like functions:

```nemerle
// ncc: -r:{chapter}/mymacros.dll
using System.Console;
using mymacros;

WriteLine(twice(21));
mutable a = 1;
mutable b = 2;
swap(a, b);
WriteLine($"$a $b")
```

```text
42
2 1
```

Unlike a function, `twice` receives the *code* `21`, not its value, and `swap` changes the caller's variables. That is
something no function can do.

A macro can't be used in the compilation that defines it, because the compiler needs the macro compiled before it can
run it. That is why macros live in their own library.

## New syntax

`syntax (...)` gives a macro its own syntax instead of a call:

```nemerle,lib=loops
// ncc: -r:{toolchain}/Nemerle.Compiler.dll
// file: loops.n
using Nemerle.Compiler;

macro forever(body)
syntax ("forever", body)
{
  <[ while (true) $body ]>
}
```

```nemerle
// ncc: -r:{chapter}/loops.dll
using System.Console;
using Nemerle.Imperative;
using loops;

mutable n = 0;
forever
{
  n++;
  when (n == 3) break
}
WriteLine(n)
```

```text
3
```

## Looking at code

A quotation is also a pattern, so a macro can take apart the code it receives:

```nemerle,lib=inspect
// ncc: -r:{toolchain}/Nemerle.Compiler.dll
// file: inspect.n
using Nemerle.Compiler;

macro describe(e)
{
  match (e)
  {
    | <[ $left + $right ]> => <[ "a sum of " + $(left.ToString() : string) + " and " + $(right.ToString() : string) ]>
    | <[ $f($arg) ]> => <[ "a call of " + $(f.ToString() : string) ]>
    | _ => <[ "something else" ]>
  }
}
```

```nemerle
// ncc: -r:{chapter}/inspect.dll
using System.Console;
using inspect;

WriteLine(describe(1 + 2));
WriteLine(describe(Foo(3)));
WriteLine(describe(7))
```

```text
a sum of 1 and 2
a call of Foo
something else
```

`$(value : string)` splices a value as a literal of that type. Code is held in `PExpr` objects, so a macro can print
them, compare them and build new ones.

## Macros on declarations

A macro can also be an attribute. It then receives the declaration and may add to it. Here it adds a method to every
class it marks:

```nemerle,lib=greeter
// ncc: -r:{toolchain}/Nemerle.Compiler.dll
// file: greeter.n
using Nemerle.Compiler;

[MacroUsage(MacroPhase.BeforeInheritance, MacroTargets.Class)]
macro Greeter(type : TypeBuilder)
{
  type.Define(<[ decl: public Hello() : string { "hello from " + $(type.Name : string) } ]>)
}
```

```nemerle
// ncc: -r:{chapter}/greeter.dll
using System.Console;
using greeter;

[Greeter]
public class Robot {}

WriteLine(Robot().Hello())
```

```text
hello from Robot
```

`MacroPhase` chooses when the macro runs. `BeforeInheritance` runs before types are related to each other;
`WithTypedMembers` runs when member types are known, so a macro can inspect them. `[Record]` is an attribute macro of
this kind.

## Macros and the license

Macros change the language. This fork's license therefore asks that a distributed macro library, and any macro or
grammar definition built into a distributed program, come with its source under the GPL (see `NOTICE.md`). A program
that only *uses* macros can stay closed.
