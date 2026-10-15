# Functions as values

Functions are values: they can be stored, passed and returned. The type of a function from `int` to `string` is
written `int -> string`; a function of two ints is `int * int -> int`.

## Writing a function value

There are three ways to write one inline:

```nemerle
using System.Console;

def add = fun (a : int, b : int) { a + b };   // fun, as in ML
def triple = x => x * 3;                       // a lambda arrow
def plusOne = _ + 1;                           // partial application
WriteLine($"$(add(2, 3)) $(triple(5)) $(plusOne(9))")
```

```text
5 15 10
```

`_` stands for "the argument": `_ + 1` means `x => x + 1`. It applies to the nearest operator or call only, so
`_ % 2 == 0` is not a predicate. Write `x => x % 2 == 0` for that.

## Passing functions

```nemerle
using System.Console;

ApplyTwice(f : int -> int, x : int) : int { f(f(x)) }
Compose(f : int -> int, g : int -> int) : int -> int { x => g(f(x)) }

WriteLine(ApplyTwice(_ * 2, 5));
def incThenSquare = Compose(_ + 1, x => x * x);
WriteLine(incThenSquare(4));
WriteLine(["a", "bb", "ccc"].Map(_.Length))
```

```text
20
25
[1, 2, 3]
```

`_.Length` is a partial application too: "take the argument's `Length`". A method with a single overload can be
passed by name, like `Console.WriteLine` can't but `Twice` below can.

## Closures

A function value captures the variables around it, mutable ones included:

```nemerle
using System.Console;

MakeCounter() : void -> int
{
  mutable count = 0;
  fun () { count++; count }
}

def next = MakeCounter();
_ = next();
_ = next();
WriteLine(next())
```

```text
3
```

`_ = expression` discards a value on purpose. Nemerle warns when a non-`void` value is silently dropped.

## Generic functions

Type parameters go in square brackets after the name. A `where` clause constrains them:

```nemerle
using System.Console;

Twice[T](f : T -> T, x : T) : T { f(f(x)) }

Largest[T](items : list[T]) : T where T : System.IComparable[T]
{
  items.FoldLeft(items.Head, (x, best) => if (x.CompareTo(best) > 0) x else best)
}

WriteLine(Twice(s => s + "!", "hey"));
WriteLine(Largest([3, 17, 5]));
WriteLine(Largest(["pear", "apple", "zebra"]))
```

```text
hey!!
17
zebra
```

## Extension methods

A function whose first parameter is marked `this` can be called as if it were a method of that type:

```nemerle
using System.Console;

Doubled(this n : int) : int { n * 2 }
Shout(this s : string) : string { s.ToUpper() + "!" }

WriteLine(21.Doubled());
WriteLine("hello".Shout())
```

```text
42
HELLO!
```

## Default and named arguments

```nemerle
using System.Console;

Greet(name : string, greeting : string = "Hello", punctuation : string = "!") : string
{
  greeting + ", " + name + punctuation
}

WriteLine(Greet("ada"));
WriteLine(Greet("ada", punctuation = "?"))
```

```text
Hello, ada!
Hello, ada?
```
