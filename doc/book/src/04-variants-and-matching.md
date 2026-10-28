# Variants and pattern matching

## Variants

A `variant` is a type whose values come in a fixed set of shapes. Rust calls this an enum with data, and ML calls it an
algebraic data type. Each shape is an *option* with its own fields:

```nemerle
using System.Console;

variant Shape
{
  | Circle { radius : double }
  | Rectangle { width : double; height : double }
  | Point
}

def shapes = [Shape.Circle(1.0), Shape.Rectangle(2.0, 3.0), Shape.Point()];
WriteLine(shapes.Length)
```

```text
3
```

## `match`

`match` takes a value apart by its shape. The first case whose pattern fits is taken, and its value is the value of
the whole `match`:

```nemerle
using System.Console;

variant Shape
{
  | Circle { radius : double }
  | Rectangle { width : double; height : double }
  | Point
}

Area(shape : Shape) : double
{
  match (shape)
  {
    | Shape.Circle(r) => 3.14 * r * r
    | Shape.Rectangle(w, h) => w * h
    | Shape.Point => 0.0
  }
}

foreach (s in [Shape.Circle(1.0), Shape.Rectangle(2.0, 3.0), Shape.Point()])
  WriteLine(Area(s))
```

```text
3.14
6
0
```

The compiler checks that a `match` covers every case. Leave one out and it warns you.

A function whose whole body is a `match` on its parameters can drop the `match (...)` and list the cases directly:

```nemerle
using System.Console;

Describe(n : int) : string
{
  | 0 => "zero"
  | 1 | 2 | 3 => "small"
  | _ => "many"
}

WriteLine($"$(Describe(0)) $(Describe(2)) $(Describe(40))")
```

```text
zero small many
```

`_` matches anything, and `|` between patterns means "any of these".

### Patterns

Patterns can look inside lists, tuples, variants and types, and can be refined with a `when` guard:

```nemerle
using System.Console;

Sum(items : list[int]) : int
{
  | [] => 0
  | first :: rest => first + Sum(rest)
}

Classify(point : int * int) : string
{
  | (0, 0) => "origin"
  | (x, 0) => $"on the x axis at $x"
  | (x, y) when x == y => "on the diagonal"
  | _ => "somewhere else"
}

Kind(value : object) : string
{
  | s is string => $"a string of length $(s.Length)"
  | n is int when n < 0 => "a negative int"
  | _ is int => "an int"
  | _ => "something else"
}

WriteLine(Sum([1, 2, 3, 4]));
WriteLine(Classify((3, 0)));
WriteLine(Classify((2, 2)));
WriteLine(Kind("hello"));
WriteLine(Kind(-5));
WriteLine(Kind(2.5))
```

```text
10
on the x axis at 3
on the diagonal
a string of length 5
a negative int
something else
```

- **`[]`** matches the empty list; **`first :: rest`** matches a non-empty one and names its head and tail.
- **`x is T`** matches when the value has type `T`, and names it with that type.
- **`as`** names the whole of a matched part: `| (_, y) as pair => ...`.

### Patterns in `def`

`def` takes a pattern as well, and declares the names it binds for the rest of the scope: `def (x, y) = point;`. A
definition's names are used from then on, so its pattern must fit every value its type allows. A tuple always does,
and so does a list written out to the same length (`def [a, b] = [1, 2];`). A pattern that can fail, such as a list of
some length or one shape of a variant, is an error, unless an `else` takes the values it does not fit. The `else`
gives the names their values instead (in the order they are written), or it leaves, by throwing or returning:

```nemerle
using System;

Pair(items : list[int]) : string
{
  def [x, y] = items else throw ArgumentException($"two items expected, got $(items.Length)");
  $"$x and $y"
}

Console.WriteLine(Pair([7, 8]));
try { Console.WriteLine(Pair([1, 2, 3])) }
catch { | e is ArgumentException => Console.WriteLine(e.Message) }
```

```text
7 and 8
two items expected, got 3
```

With values: `def [x, y] = items else (0, 0);`. Without an `else`, the compiler names a value the pattern misses:

```nemerle,fail
First(items : list[int]) : int
{
  def (first :: _) = items;
  first
}
```

```text
does not fit every value
```

For several shapes that each mean something, write a `match`. A pattern that starts with a constructor or a cons is
written in parentheses, `def (Some(v)) = found else 0;` or `def (first :: _) = items`, since `def Name(...)` is a
local function.

## `option`

`option[T]` is the standard variant for "a value or nothing", with the shapes `Some(value)` and `None()`. It replaces
`null` for values that may be missing:

```nemerle
using System.Console;

Find(names : list[string], wanted : string) : option[int]
{
  def search(items, index)
  {
    match (items)
    {
      | [] => None()
      | name :: rest => if (name == wanted) Some(index) else search(rest, index + 1)
    }
  }
  search(names, 0)
}

Show(found : option[int]) : string
{
  | Some(index) => $"found at $index"
  | None => "not there"
}

def names = ["ada", "alan", "grace"];
WriteLine(Show(Find(names, "alan")));
WriteLine(Show(Find(names, "linus")))
```

```text
found at 1
not there
```

Match on a value whose type is `option[T]`, such as a parameter or a return value. A bare `Some(5)` has the narrower
type `Some[int]`, so a `None` case wouldn't fit it.

## Variants with members

A variant can have methods like a class. Inside them, `this` is the value being matched:

```nemerle
using System.Console;

variant Expr
{
  | Number { value : int }
  | Add { left : Expr; right : Expr }
  | Multiply { left : Expr; right : Expr }

  public Eval() : int
  {
    match (this)
    {
      | Number(v) => v
      | Add(l, r) => l.Eval() + r.Eval()
      | Multiply(l, r) => l.Eval() * r.Eval()
    }
  }

  public override ToString() : string
  {
    match (this)
    {
      | Number(v) => v.ToString()
      | Add(l, r) => $"($l + $r)"
      | Multiply(l, r) => $"$l * $r"
    }
  }
}

def e = Expr.Add(Expr.Number(2), Expr.Multiply(Expr.Number(3), Expr.Number(4)));
WriteLine($"$e = $(e.Eval())")
```

```text
(2 + 3 * 4) = 14
```

## Enums

For plain named constants without data, use a .NET `enum`:

```nemerle
using System.Console;

enum Colour { | Red | Green | Blue }

def c = Colour.Green;
WriteLine(c);
WriteLine(c :> int)
```

```text
Green
1
```

A constant can have its value written, and `[System.Flags]` makes an enum of bits, combined with `|`. A `match`
picks constants as it picks variant options, and .NET's `Enum` methods work on them:

```nemerle
using System.Console;

[System.Flags]
enum Access { | None = 0 | Read = 1 | Write = 2 | Run = 4 }
enum Level { | Low = 10 | High = 20 }

def rights = Access.Read | Access.Write;
WriteLine(rights);
WriteLine(rights.HasFlag(Access.Write));
WriteLine(Level.High :> int);
def describe(level : Level) : string
{
  match (level) { | Level.Low => "low" | Level.High => "high" | _ => "other" }
}
WriteLine(describe(Level.Low));
WriteLine(System.Enum.Parse(typeof(Level), "High"))
```

```text
Read, Write
True
20
low
High
```

The `_` case is there because an enum can hold any number of its type, not only its constants.
