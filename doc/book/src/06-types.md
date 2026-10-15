# Classes, structs and interfaces

## Classes

A class has fields, a constructor called `this`, properties and methods. Members are private unless marked otherwise:

```nemerle
using System.Console;

public class Account
{
  mutable balance : decimal;
  public Owner : string { get; }

  public this(owner : string, opening : decimal)
  {
    Owner = owner;
    balance = opening;
  }

  public Balance : decimal { get { balance } }

  public Deposit(amount : decimal) : void
  {
    when (amount <= 0) throw System.ArgumentException("amount must be positive");
    balance += amount
  }
}

def account = Account("ada", 100);
account.Deposit(50);
WriteLine($"$(account.Owner): $(account.Balance)")
```

```text
ada: 150
```

- **Fields** are immutable unless declared `mutable`.
- **`{ get; }`** declares an auto-property that only the constructor can set; **`{ get; set; }`** one that anyone can.
- **`new` isn't used** to create objects: `Account("ada", 100)` calls the constructor.

## `[Record]`

Writing a constructor that just copies its parameters into fields is common enough to have a macro. `[Record]` writes
it for you, taking the fields in order:

```nemerle
using System.Console;

[Record]
public class Point
{
  public X : int;
  public Y : int;
  public override ToString() : string { $"($X, $Y)" }
}

WriteLine(Point(3, 4))
```

```text
(3, 4)
```

## Inheritance

Classes inherit from one base class and any number of interfaces. Methods that may be overridden are `virtual` or
`abstract`, and the override says `override`:

```nemerle
using System.Console;

public abstract class Animal
{
  public abstract Sound() : string;
  public virtual Describe() : string { "an animal that says " + Sound() }
}

public class Dog : Animal
{
  public override Sound() : string { "woof" }
}

public class Puppy : Dog
{
  public override Describe() : string { "a small dog, " + base.Describe() }
}

foreach (a in [Dog() : Animal, Puppy()])
  WriteLine(a.Describe())
```

```text
an animal that says woof
a small dog, an animal that says woof
```

`Dog() : Animal` states the element type, so the list is a `list[Animal]` rather than a `list[Dog]`.

## Interfaces

```nemerle
using System.Console;

public interface IShape
{
  Area() : double;
  Name : string { get; }
}

public class Square : IShape
{
  side : double;
  public this(side : double) { this.side = side }
  public Area() : double { side * side }
  public Name : string { get { "square" } }
}

def shape : IShape = Square(3.0);
WriteLine($"$(shape.Name) of area $(shape.Area())")
```

```text
square of area 9
```

## Structs

A `struct` is a value type. It is copied on assignment and stored inline, like .NET's `int` or `DateTime`:

```nemerle
using System.Console;

[Record]
public struct Size
{
  public Width : int;
  public Height : int;
}

def a = Size(2, 3);
mutable b = a;
b = Size(10, b.Height);
WriteLine($"$(a.Width) $(b.Width)")
```

```text
2 10
```

## Static members and `module`

`static` members belong to the type rather than to an instance. A `module` is a class whose members are all static,
and which can't be instantiated:

```nemerle
using System.Console;

public class Temperature
{
  public static Freezing : double = 0.0;
  public static ToFahrenheit(celsius : double) : double { celsius * 9.0 / 5.0 + 32.0 }
}

public module Convert
{
  public Kilometres(miles : double) : double { miles * 1.609344 }
}

WriteLine(Temperature.ToFahrenheit(100.0));
WriteLine(Convert.Kilometres(10.0))
```

```text
212
16.09344
```

Every file is itself a module, as Chapter 7 explains. Its top-level functions are its static members.

## Generic types

```nemerle
using System.Console;

public class Stack[T]
{
  mutable items : list[T] = [];
  public Push(item : T) : void { items = item :: items }
  public Pop() : T
  {
    match (items)
    {
      | top :: rest => items = rest; top
      | [] => throw System.InvalidOperationException("empty stack")
    }
  }
  public IsEmpty : bool { get { items.IsEmpty } }
}

def stack = Stack();
stack.Push("a");
stack.Push("b");
WriteLine(stack.Pop());
WriteLine(stack.IsEmpty)
```

```text
b
False
```

`Stack()` needs no type argument here; the compiler infers `Stack[string]` from the pushes.

## Indexers and operators

```nemerle
using System.Console;

[Record]
public class Vector
{
  public X : int;
  public Y : int;
  public static @+(a : Vector, b : Vector) : Vector { Vector(a.X + b.X, a.Y + b.Y) }
  public Item[index : int] : int { get { if (index == 0) X else Y } }
}

def v = Vector(1, 2) + Vector(10, 20);
WriteLine($"$(v[0]) $(v[1])")
```

```text
11 22
```

An operator is a static method named `@` followed by the operator. A property named `Item` with parameters is the
type's indexer.
