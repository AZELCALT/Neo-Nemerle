# Appendix: syntax at a glance

## Declarations

| Syntax | Meaning |
|---|---|
| `def x = e;` | immutable binding |
| `mutable x = e;` | mutable binding |
| `def (x, y) = e;` | declares `x` and `y` (the pattern must fit every value) |
| `def [x, y] = e else E;` | declares `x` and `y`; when `e` does not fit, `E` gives their values or leaves |
| `def f(a, b) { ... }` | local function |
| `Name(a : T) : R { ... }` | function (a member of the file module or type) |
| `class C : Base, IFace { ... }` | class |
| `struct S { ... }` | value type |
| `interface I { ... }` | interface |
| `variant V { \| A { x : int } \| B }` | variant (sum type) |
| `enum E { \| A \| B }` | enumeration |
| `module M { ... }` | static class |
| `mask m { ... }` | named group inside a file |
| `macro m(a) { ... }` | macro |
| `grammar G { ... }` | Nitra grammar |
| `grammar (A, B) { ... }` | how grammars `A` and `B` work together, for `space (A, B)` |
| `space G { ... }` | top-level code in a grammar's language (a logical file) |
| `scope A;` | a scope shared by the program and its spaces (`scope.A.x` reads a binding) |
| `[Attr] ...` | attribute or attribute macro |
| `register symbol;` | first directive: give the whole file a logical folder; `file.n` becomes `symbol.file` |
| `using symbol.file;` | open a file module's members; local `.n` dependencies are discovered automatically |
| `using path.to.folder;` | make immediate file names available for qualified use, such as `file.Member(...)` |
| `using System;` / `using X = a.b;` | open a CLR namespace / give a module or namespace an alias |
| `import helper;` | in a script header: load neighboring `helper.ns` and open its public names |
| `import "path/helper.ns";` | in a script header: load a child script relative to the importing script |

## Indented blocks

Put `#pragma indent` at the start of a file (or pass `-i` to `ncc`) to use
indentation syntax. A colon at the end of a logical line opens a block; indent
its body further, and return to an enclosing indentation level to close it.
There is no fixed number of spaces, but each level must use a consistent prefix.
Prefer spaces throughout a file rather than mixing spaces and tabs.

```nemerle
#pragma indent
Twice(n : int) : int:
    n * 2

when (true):
    System.Console.WriteLine(Twice(21))
System.Console.WriteLine("done")
```

```text
42
done
```

The trailing colon replaces the opening brace, and dedentation replaces the
closing brace. Newlines separate statements, so semicolons are optional.
Blank lines and comment-only lines do not count as a block body. An empty block
is an error; write `()` on an indented line when a block should do nothing.
Type annotations such as `n : int` and return types such as `: int` keep their
usual meaning: only the final colon introduces the block.

`space G:`, plain `space:`, and `space (A, B):` use the same rule. Every
nonblank content line of the foreign-language body must stay within the body's
indentation; dedenting ends the space and resumes ordinary Nemerle code. The
body is passed to its selected grammar with its whitespace intact. A grammar
declaration and its syntax rules still use the grammar language's own syntax.

Nemerle's named-block expression also keeps its meaning: `finish:` followed
by an indented body binds the exit function `finish` inside that body.

Explicit `{ ... }`, `( ... )`, `[ ... ]`, and quotation groups keep their usual
syntax; indentation is ignored inside them. In particular, use braces for nested
blocks within an explicit brace group. The older form that opens a block on an
increase in indentation without a colon remains supported for existing code.

## Expressions

| Syntax | Meaning |
|---|---|
| `if (c) a else b` | conditional expression |
| `when (c) e` / `unless (c) e` | one-armed conditionals |
| `match (e) { \| p => ... }` | pattern matching |
| `{ e1; e2 }` | block; its value is `e2` |
| `while`, `do ... while`, `for`, `foreach (x in xs)`, `repeat (n)` | loops |
| `try { } catch { \| e is T => } finally { }` | exceptions |
| `throw e` | raise an exception |
| `x => e`, `fun (x) { e }`, `_ + 1` | function values |
| `e :> T` / `e : T` | checked conversion / type statement |
| `(T)e` | the conversion `e :> T`, written as in C# |
| `x :: xs`, `[a, b]`, `$[e \| x in xs]`, `$[a .. b]` | lists |
| `(a, b)` | tuple |
| `array[a, b]`, `array(n)` | arrays |
| `$"text $x $(e)"` | string interpolation |
| `<[ code ]>`, `$e` | quotation and splice (in macros) |
| `dial:.file.G::member(...)` | a dial: a call into `space G` of `file` (`dial:.main.G::twice(2)`) |
| `dial:.file.(A, B)::member(...)` | a dial into the mixing space `space (A, B)` (any order) |
| `dial:.file::member(...)` | a dial into the plain `space { }` of `file` |
| `_ = e` | discard a value |

## Patterns

| Pattern | Matches |
|---|---|
| `_` | anything |
| `x` | anything, naming it |
| `42`, `"s"`, `true` | that literal |
| `(p1, p2)` | a tuple |
| `[]`, `[p1, p2]`, `h :: t` | lists |
| `V.Option(p1, p2)` | a variant option, by field order |
| `x is T` | a value of type `T` |
| `p1 \| p2` | either |
| `p when cond` | `p`, if `cond` holds |
| `p as x` | `p`, naming the whole |

## Operators

Arithmetic `+ - * / %`, comparison `== != < <= > >=`, logical `&& || !`, bitwise `& | ^ ~ << >>`, assignment `=` and
compound `+= -= *= /=`, increment `++ --`, `::` for list cons. `@+` declares the operator `+` as a static method.

## Common compiler options

| Option | Meaning |
|---|---|
| `-out:FILE` | output file (`.exe` or `.dll`); a program written as `NAME.exe` also gets a launcher |
| `-launcher-` | no launcher: the program alone, as `NAME.exe` |
| `-main:file` | start the program at `file` instead of `main.n` |
| `-target:library` | build a library |
| `-r:LIB.dll` | reference a library (and continue from its section) |
| `-source-root:DIR` | the root that module paths are relative to |
| `-file-name-namespaces` | name modules by file name only |
| `-define:NAME` | define a preprocessor symbol for `#if` |
| `-debug` | emit debug symbols |
| `-keyfile:KEY.snk` | sign the assembly |
| `-continue:BIN` | continue from a binary that is not referenced |
| `-no-continuation-section` | write no continuation section |
