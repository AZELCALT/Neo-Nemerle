# Errors

Nemerle reports errors with .NET exceptions, and represents values that may be missing with `option`.

## Throwing and catching

`throw` raises an exception. `try` runs code, `catch` handles exceptions by matching their types, and `finally` runs
in every case:

```nemerle
using System.Console;

ParsePort(text : string) : int
{
  def port = int.Parse(text);
  when (port < 1 || port > 65535) throw System.ArgumentOutOfRangeException("text", "not a port number");
  port
}

Try(text : string) : void
{
  try
  {
    WriteLine($"port $(ParsePort(text))")
  }
  catch
  {
    | e is System.FormatException => WriteLine($"not a number: $text")
    | e is System.ArgumentOutOfRangeException => WriteLine($"out of range: $text")
  }
  finally
  {
    WriteLine("checked " + text)
  }
}

Try("8080");
Try("http");
Try("99999")
```

```text
port 8080
checked 8080
not a number: http
checked http
out of range: 99999
checked 99999
```

The cases of a `catch` are patterns, like those of `match`. `| e => ...` catches everything.

A `try` is an expression too, so it can produce a fallback value:

```nemerle
using System.Console;

def number = try { int.Parse("x") } catch { | _ => -1 };
WriteLine(number)
```

```text
-1
```

## Your own exceptions

```nemerle
using System.Console;

public class InsufficientFunds : System.Exception
{
  public Missing : decimal { get; }
  public this(missing : decimal) { base($"missing $missing"); Missing = missing }
}

try { throw InsufficientFunds(25) }
catch { | e is InsufficientFunds => WriteLine($"$(e.Message) ($(e.Missing))") }
```

```text
missing 25 (25)
```

A `catch` case can have a `when` guard, as a `match` case can; the first case that fits handles the exception. A
`finally` runs whether the `try` ended or threw:

```nemerle
using System.Console;

def parse(text : string) : int
{
  try int.Parse(text)
  catch
  {
    | _ is System.FormatException when text.Length == 0 => WriteLine("empty"); 0
    | _ is System.FormatException => WriteLine($"not a number: $text"); -1
  }
  finally WriteLine($"parsed '$text'")
}
WriteLine(parse("12"));
WriteLine(parse(""));
WriteLine(parse("x"))
```

```text
parsed '12'
12
empty
parsed ''
0
not a number: x
parsed 'x'
-1
```

## `option` instead of `null`

When "no result" is an ordinary outcome rather than an error, return an `option` (Chapter 4). The caller then has to
handle both cases:

```nemerle
using System.Console;

Divide(a : int, b : int) : option[int]
{
  if (b == 0) None() else Some(a / b)
}

Show(result : option[int]) : string
{
  | Some(value) => value.ToString()
  | None => "undefined"
}

WriteLine(Show(Divide(10, 2)));
WriteLine(Show(Divide(1, 0)));
WriteLine(Divide(9, 3).WithDefault(0))
```

```text
5
undefined
3
```

## Cleaning up: `using`

`using (name = expression) body` disposes the value when the body ends, whether normally or by an exception. This is
the same as C#'s `using` statement. At the top of a file `using` always opens a namespace, so a `using` statement goes
inside a function or block:

```nemerle
using System.Console;

public class Resource : System.IDisposable
{
  public this() { WriteLine("opened") }
  public Dispose() : void { WriteLine("closed") }
}

Work() : void
{
  using (r = Resource())
  {
    WriteLine("working")
  }
}

Work()
```

```text
opened
working
closed
```

## Checks

`assert` throws when its condition is false. Use it for things that can only fail through a bug:

```nemerle
using System.Console;

Average(values : list[double]) : double
{
  assert(!values.IsEmpty);
  values.FoldLeft(0.0, _ + _) / values.Length
}

WriteLine(Average([1.0, 2.0, 6.0]))
```

```text
3
```
