# Appendix: syntax at a glance

## Declarations

| Syntax | Meaning |
|---|---|
| `def x = e;` | immutable binding |
| `mutable x = e;` | mutable binding |
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
| `space G { ... }` | top-level code in a grammar's language (a logical file) |
| `scope A;` | a scope shared by the program and its spaces (`scope.A.x` reads a binding) |
| `[Attr] ...` | attribute or attribute macro |
| `using a.b;` / `using X = a.b;` | open a module or namespace / alias it |

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
| `-out:FILE` | output file (`.exe` or `.dll`) |
| `-target:library` | build a library |
| `-r:LIB.dll` | reference a library (and continue from its section) |
| `-source-root:DIR` | the root that module paths are relative to |
| `-file-name-namespaces` | name modules by file name only |
| `-define:NAME` | define a preprocessor symbol for `#if` |
| `-debug` | emit debug symbols |
| `-keyfile:KEY.snk` | sign the assembly |
| `-continue:BIN` | continue from a binary that is not referenced |
| `-no-continuation-section` | write no continuation section |
