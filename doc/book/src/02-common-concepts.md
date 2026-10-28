# Common concepts

## Values and mutability

The examples open `System.Console` with `using System.Console;`, so `WriteLine` is short for
`System.Console.WriteLine`. Without that line, write the full name.

These examples use braces for blocks. You can also opt into
[`#pragma indent` and colon-led blocks](appendix-syntax.md#indented-blocks),
where indentation determines the body of each block.

`def` binds a name to a value. The binding can't change:

```nemerle
using System.Console;

def answer = 42;
def greeting = "hello";
WriteLine($"$greeting, the answer is $answer")
```

```text
hello, the answer is 42
```

Assigning to a `def` is a compile error:

```nemerle,fail
def answer = 42;
answer = 43
```

```text
answer
```

When a value really has to change, say so with `mutable`:

```nemerle
using System.Console;

mutable count = 0;
count = count + 1;
count += 10;
count++;
WriteLine(count)
```

```text
12
```

Prefer `def`. A `mutable` tells the reader to watch for changes.

A name can be bound again with a new `def`; the new binding hides the old one from that point on:

```nemerle
using System.Console;

def x = 5;
def x = x * 2;
WriteLine(x)
```

```text
10
```

A name keeps its kind: a `def` is not bound again as a `mutable`, nor the other way round.

### A mutable whose type changes

A `mutable` written without a type can be given a value of another type. That is not dynamic typing: the compiler
follows the code, and after each assignment it knows the one type the value has.

```nemerle
using System.Console;

mutable answer = 42;
WriteLine(answer + 1);
answer = "forty-two";
WriteLine(answer.Length)
```

```text
43
9
```

Where the compiler cannot know which type the value has (after an `if` that changes it on one way only, around a loop,
inside a lambda, which runs whenever it is called), the value has a *set* of types. A use without a check must fit
every type in the set (`WriteLine(value)` takes an `int` and a `string` alike); a check picks the types it handles:

```nemerle
using System.Console;

def describe(n : int) : string
{
  mutable value = n;
  when (n > 10) value = "big";
  match (value)
  {
    | i is int => $"the number $i"
    | s is string => s
  }
}

WriteLine(describe(3));
WriteLine(describe(30))
```

```text
the number 3
big
```

`if (value is string)` is a check too: inside it, `value` is a `string`. A use that does not fit one of the types is
an error, which says which:

```nemerle,fail
def doubled(n : int) : int
{
  mutable value = n;
  when (n > 10) value = "big";
  value * 2
}
System.Console.WriteLine(doubled(3))
```

```text
this does not fit `value' when it is string: `value' is int or string here (int from line 3, string from line 4)
```

The error names the types the value can be at that point and the lines that give it each, and it goes on with the
check to write: `match (value) { | v is int => ... | v is string => ... }`.

The value is stored as its one type where its type never changes. Where it does, it is kept as an object, so a value
type assigned to it (an `int`, a `double`) is boxed. In a loop or a lambda, which may run many times, the compiler
warns (`N10014`, which `-nowarn:10014` turns off): give the value one type, or write `mutable total : object` to say
it is meant to be kept as an object.

A `mutable` with a type written down (`mutable count : int = 0`) keeps that type. One written without a value
(`mutable total;`) is *NotYet* until the code gives it one: reading it where some way to the read has not assigned
it is an error. An `out` argument assigns it.

```nemerle,fail
def total(c : bool) : int
{
  mutable sum;
  when (c) sum = 1;
  sum
}
System.Console.WriteLine(total(true))
```

```text
`sum' is NotYet here
```

## Types and inference

Every value has a type, fixed at compile time. You rarely write it down: the compiler infers types from how values are
used. When you want to, write the type after a colon:

```nemerle
using System.Console;

def small : int = 7;
def big : long = 7;
def ratio = 1.5;            // double
def name = "Nemerle";       // string
def yes = true;             // bool
def letter = 'n';           // char
WriteLine($"$(small.GetType().Name) $(big.GetType().Name) $(ratio.GetType().Name) $(name.GetType().Name) $(yes.GetType().Name) $(letter.GetType().Name)")
```

```text
Int32 Int64 Double String Boolean Char
```

The basic types are .NET's: `int`, `long`, `short`, `byte`, `double`, `float`, `decimal`, `bool`, `char`,
`string`, and `object` at the top. Nemerle adds its own on top of them, such as `list[T]` and `option[T]`, which
later chapters meet.

`:>` converts a value to another type and checks at run time. `:` only states a type the value already has:

```nemerle
using System.Console;

def d = 3.9;
def i = d :> int;
def o : object = "text";
def s = o :> string;
WriteLine($"$i $s")
```

```text
3 text
```

C#'s way of writing it, `(T)x`, is the same conversion. It applies to the operand as a prefix operator does, so
`(double)a / b` divides a `double`, and `(int)(a * b)` converts the product:

```nemerle
using System.Console;

def a = 7;
def b = 2;
def ratio = (double)a / b;
def product = (int)(a * b);
def o : object = "text";
def s = (string)o;
WriteLine($"$ratio $product $s")
```

```text
3.5 14 text
```

Parentheses are a conversion when they hold a type and an operand follows: a name, a literal, `(`, `!`, `~` or `$`,
and `+` or `-` after a built-in type's name (`(int)-x`; `(a) - b` subtracts). `(f)(x)` stays a call when `f` is a
value, and converts when `f` names a type. Like `:>`, the conversion checks at run time: `(byte)300` throws an
`OverflowException` (inside `unchecked (...)` it gives 44, as in C#).

## Functions

A function lists its parameters with their types, then its return type after a colon. The body is a block, and the
block's value is its last expression. There is no `return` statement:

```nemerle
using System.Console;

Add(a : int, b : int) : int
{
  a + b
}

Greet(name : string) : void
{
  WriteLine("Hello, " + name)
}

WriteLine(Add(2, 3));
Greet("world")
```

```text
5
Hello, world
```

`void` means "no value". Functions declared at the top of a file belong to the file's module. Their order doesn't
matter, and top-level statements can call functions defined further down.

A function's return type may be left out: its result is the type its body gives. When its return points give
different types, the result is one of them, as a value whose type follows the flow is (above): a caller has those
types, and checks it as it would such a value. A use that fits each type is fine, a `match` picks them, and a use
that does not fit one of them is an error:

```nemerle
using System.Console;

Twice(n : int) { n * 2 }
Pick(first : bool) { if (first) "one" else 1 }

def size = Twice(4);
def picked = Pick(System.Environment.GetCommandLineArgs().Length > 99);
WriteLine(size + 1);
WriteLine(picked);
WriteLine(match (picked) { | s is string => s.Length | n is int => n });
WriteLine(Pick(true).Length)
```

```text
9
1
1
3
```

`picked` is `string` or `int`: its argument is known only when the program runs. `Pick(true)` is a `string`: a
call whose constant arguments decide which return point it reaches has that point's type (here its `if` is decided),
so its `Length` needs no check.

```nemerle,fail
Pick(first : bool) { if (first) "one" else 1 }
Show(first : bool) : void { def n : int = Pick(first) * 2; System.Console.WriteLine(n) }
Show(true)
```

```text
this does not fit `Pick(first)' when it is string
```

A recursive call gives the function's own result, so it adds no type of its own. A top-level value bound to such a
result has the function's types too, and the file's functions check it before they use it when it has several.
Other .NET languages see the result as a `Nemerle.Scopes.Content` when it has several types, and its result says
which: `[return: Nemerle.Scopes.ContentTypes(typeof(string), typeof(int))]`. Compiling with `-flow-log` adds a hint at
each return point saying the type it gives, for when a set's types are not the ones expected.

Inside a block, `def` declares a *local* function. Its parameter and return types may be left out; they are inferred:

```nemerle
using System.Console;

def square(x) { x * x }
def area(w, h) { w * h }
WriteLine(square(9) + area(2, 3))
```

```text
87
```

Local functions can call themselves, so they are also the usual way to write a loop:

```nemerle
using System.Console;

def sum(n, acc)
{
  if (n == 0) acc else sum(n - 1, acc + n)
}
WriteLine(sum(100, 0))
```

```text
5050
```

A call in tail position, like `sum(n - 1, acc + n)` here, becomes a jump, so the stack doesn't grow.

## Comments

```nemerle
// a line comment
/* a block comment */
/// a documentation comment, attached to the declaration that follows
Twice(x : int) : int { x * 2 }

System.Console.WriteLine(Twice(4))
```

```text
8
```

## Control flow is made of expressions

`if` is an expression with a value. Both branches must be present and have the same type:

```nemerle
using System.Console;

def temperature = 31;
def feeling = if (temperature > 25) "hot" else "fine";
WriteLine(feeling)
```

```text
hot
```

For a branch without an `else`, Nemerle has `when` (do it when the condition holds) and `unless` (do it when it
doesn't):

```nemerle
using System.Console;

def n = 7;
when (n > 5) WriteLine("more than five");
unless (n % 2 == 0) WriteLine("odd")
```

```text
more than five
odd
```

A block `{ ... }` is an expression too. Its value is the value of its last expression:

```nemerle
using System.Console;

def total =
{
  def a = 10;
  def b = 32;
  a + b
};
WriteLine(total)
```

```text
42
```

### Loops

`while`, `do ... while`, `for` and `foreach` work as in C-like languages:

```nemerle
using System.Console;

mutable i = 0;
while (i < 3) { Write(i); i++ }
WriteLine();

for (mutable j = 3; j > 0; j--) Write(j);
WriteLine();

foreach (fruit in ["apple", "pear"]) WriteLine(fruit);

foreach (letter in ["a", "b", "c"] with index) WriteLine($"$index $letter");

repeat (3) Write("*");
WriteLine()
```

```text
012
321
apple
pear
0 a
1 b
2 c
***
```

`foreach ... with index` numbers the elements from 0. `repeat (n)` runs its body n times.

A statement may continue on the next line, as with `else` and the `catch` of a `try`:

```nemerle
using System.Console;

def n = 3;
if (n > 2)
  WriteLine("big")
else
  WriteLine("small")
```

```text
big
```
