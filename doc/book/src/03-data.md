# Lists, tuples, arrays and strings

## Lists

`list[T]` is an immutable singly linked list, the workhorse of functional Nemerle. Square brackets build one:

```nemerle
using System.Console;

def numbers = [1, 2, 3, 4, 5];
WriteLine(numbers);
WriteLine(numbers.Head);
WriteLine(numbers.Tail);
WriteLine(numbers.Length)
```

```text
[1, 2, 3, 4, 5]
1
[2, 3, 4, 5]
5
```

`::` puts an element in front of a list without changing the original, and `+` joins two lists:

```nemerle
using System.Console;

def tail = [2, 3];
def whole = 1 :: tail;
WriteLine(whole);
WriteLine(tail);
WriteLine(whole + [4, 5])
```

```text
[1, 2, 3]
[2, 3]
[1, 2, 3, 4, 5]
```

Lists come with the usual functional operations. Each takes a function; Chapter 5 shows the ways to write one:

```nemerle
using System.Console;

def numbers = [1, 2, 3, 4, 5, 6];
WriteLine(numbers.Map(n => n * n));
WriteLine(numbers.Filter(n => n % 2 == 0));
WriteLine(numbers.FoldLeft(0, (n, total) => n + total));
WriteLine(numbers.Exists(n => n > 5));
WriteLine(numbers.ForAll(n => n > 0));
WriteLine(numbers.Rev());
WriteLine(numbers.Contains(4))
```

```text
[1, 4, 9, 16, 25, 36]
[2, 4, 6]
21
True
True
[6, 5, 4, 3, 2, 1]
True
```

### List comprehensions and ranges

`$[ ... ]` builds a list from a pattern, like set-builder notation in mathematics. `..` gives a range:

```nemerle
using System.Console;

WriteLine($[1 .. 5]);
WriteLine($[x * x | x in [1 .. 6], x % 2 == 1]);
WriteLine($[(x, y) | x in [1, 2], y in ["a", "b"]])
```

```text
[1, 2, 3, 4, 5]
[1, 9, 25]
[(1, a), (1, b), (2, a), (2, b)]
```

## Tuples

A tuple groups a fixed number of values that may have different types. `def` can take one apart:

```nemerle
using System.Console;

def pair = (7, "seven");
def (number, word) = pair;
WriteLine($"$number is $word");

MinMax(values : list[int]) : int * int
{
  (values.FoldLeft(values.Head, (x, m) => if (x < m) x else m), values.FoldLeft(values.Head, (x, m) => if (x > m) x else m))
}
def (low, high) = MinMax([4, 8, 1, 9]);
WriteLine($"$low to $high")
```

```text
7 is seven
1 to 9
```

The type of a tuple is written with `*`: `int * string`. A function can return several values that way.

## Arrays

Arrays are .NET arrays: fixed size, mutable, indexed from 0. `array[...]` lists the elements; `array(n)` makes `n`
default values:

```nemerle
using System.Console;

def primes = array[2, 3, 5, 7];
WriteLine(primes[2]);
primes[0] = 1;
WriteLine(primes.Length);

def slots : array[string] = array(3);
slots[1] = "middle";
WriteLine(slots[1]);

def grid = array.[2][[1, 2], [3, 4]];
WriteLine(grid[1, 0])
```

```text
5
4
middle
3
```

`array.[2]` builds a two-dimensional array, which is indexed with `[row, column]`.

## Strings

Strings are .NET strings. A `$` in front of a string literal turns on interpolation: `$name` inserts a variable, and
`$(...)` inserts any expression:

```nemerle
using System.Console;

def item = "tea";
def price = 2.5;
WriteLine($"$item costs $price");
WriteLine($"two of them cost $(price * 2)");
WriteLine($"$(item.ToUpper()) has $(item.Length) letters")
```

```text
tea costs 2.5
two of them cost 5
TEA has 3 letters
```

A verbatim string starts with `@` and keeps backslashes as they are. A recursive string `<# ... #>` may contain quotes
and span lines:

```nemerle
using System.Console;

WriteLine(@"C:\temp\new");
WriteLine(<#He said "hi"#>)
```

```text
C:\temp\new
He said "hi"
```

All .NET string methods are available, such as `Split`, `Trim`, `Replace`, `Substring` and `string.Join`. `Split`
returns a .NET array. `using Nemerle.Collections;` gives arrays and every other .NET collection the same `Map`,
`Filter` and friends that lists have:

```nemerle
using System.Console;
using Nemerle.Collections;

def line = "  red, green ,blue ";
def colours = line.Split(',').Map(c => c.Trim());
WriteLine(string.Join("|", colours))
```

```text
red|green|blue
```

## .NET collections

Every .NET collection works as it does in C#. Generic type arguments are written in square brackets, and `.[T]` gives
them explicitly where a constructor needs them:

```nemerle
using System.Console;
using System.Collections.Generic;

def ages = Dictionary.[string, int]();
ages["ada"] = 36;
ages["alan"] = 41;
foreach (pair in ages) WriteLine($"$(pair.Key): $(pair.Value)");

def queue = Queue();
queue.Enqueue("first");
queue.Enqueue("second");
WriteLine(queue.Dequeue())
```

```text
ada: 36
alan: 41
first
```

The second constructor needs no type: the compiler infers `Queue[string]` from the `Enqueue` calls.
