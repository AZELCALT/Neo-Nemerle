# Common concepts

## Values and mutability

The examples open `System.Console` with `using System.Console;`, so `WriteLine` is short for
`System.Console.WriteLine`. Without that line, write the full name.

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
