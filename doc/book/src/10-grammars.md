# Grammars and spaces

Macros extend the language one construct at a time. A **grammar** goes further: it defines a whole small language.
A **space** is code written in that language: a logical file of its own inside a Nemerle file. The grammar machinery
is Nitra, built into the compiler. The grammar is checked and compiled with the program, and a space is translated to
ordinary Nemerle code, so nothing of Nitra is needed when the program runs.

A space is always at the top level of its file, like a declaration. It is not an expression, and it does not go
inside a function or type. The program and its spaces communicate in two ways:

- **scopes**, a shared memory zone. The program puts bindings in a scope, a space reads them, and a space can write
  bindings back for the program to read;
- **dials**, direct calls into a space: `dial:.file.G::member(...)` reaches a member of the `space G` of a file.

## A first grammar

```nemerle
grammar Greetings
{
  using Nemerle.Compiler.Parsetree;
  syntax module Hello
  {
    using Nitra.Core;
    [StartRule] syntax Start = Greeting { map PExpr = <[ System.Console.WriteLine($(this.Greeting.GetAst())) ]>; }
    syntax Greeting
    {
      map PExpr;
      | Morning = "good" "morning" { map PExpr = <[ "Guten Morgen" ]>; }
      | Night = "good" "night" { map PExpr = <[ "Gute Nacht" ]>; }
    }
  }
}

space Greetings { good morning }
```

```text
Guten Morgen
```

Line by line:

- **`grammar Greetings`** declares a grammar. Its body is Nitra: `using`s, then one or more `syntax module`s.
- **`using Nitra.Core;`** brings the standard rules: whitespace, `IdentifierBody`, and more.
- **`[StartRule]`** marks where parsing of a space begins.
- **`syntax Greeting { | Morning = ... | Night = ... }`** is an *extensible rule* with alternatives.
  - A rule with `=` and no alternatives, like `Start`, is a sequence.
  - String literals are keywords; spaces between them are allowed by default.
- **`map PExpr`** says what each piece of syntax becomes: Nemerle code (`PExpr`), usually built with a quotation, as in
  macros. `this.Greeting.GetAst()` is the code its `Greeting` part maps to.
- **`space Greetings { ... }`** parses its body with the grammar's start rule. The mapped code takes the space's place
  in the file and runs there, as the file's top-level statements do. No `;` is needed after it.

## A calculator

Rules can have named parts, regular-expression tokens and precedence:

```nemerle
grammar Calc
{
  using Nemerle.Compiler.Parsetree;
  syntax module Arith
  {
    using Nitra.Core;
    [StartRule] syntax Start = Expr { map PExpr = <[ System.Console.WriteLine($(this.Expr.GetAst())) ]>; }
    regex Digits = ['0'..'9']+;
    syntax Expr
    {
      map PExpr;
      precedence Sum:
      | Add = Left=Expr "+" Right=Expr { map PExpr = <[ $(this.Left.GetAst()) + $(this.Right.GetAst()) ]>; }
      | Sub = Left=Expr "-" Right=Expr { map PExpr = <[ $(this.Left.GetAst()) - $(this.Right.GetAst()) ]>; }
      precedence Product:
      | Mul = Left=Expr "*" Right=Expr { map PExpr = <[ $(this.Left.GetAst()) * $(this.Right.GetAst()) ]>; }
      precedence 0:
      | Number = Value=Digits { map PExpr = <[ $(int.Parse(GetText(this.Value)) : int) ]>; }
      | Variable = Name=IdentifierBody { map PExpr = <[ $(GetText(this.Name) : usesite) ]>; }
      | Group = "(" Expr ")" { map PExpr { Expr } }
    }
  }
}

def width = 4;
space Calc { 2 + 3 * (width - 1) }
```

```text
11
```

- **`Left=Expr`** names a part so the mapping can use it: `this.Left.GetAst()` is the code it maps to.
- **`regex Digits = ['0'..'9']+;`** defines a token. `GetText(this.Value)` is the text it matched.
- **`precedence Sum:` / `precedence Product:`** group alternatives by binding strength, later groups binding tighter.
  `right-associative` after an alternative makes it group to the right.
- **`$(name : usesite)`** produces a reference to a name as seen where the space stands. Here `width` is a top-level
  variable of the file.

The space above compiles to exactly `System.Console.WriteLine(2 + 3 * (width - 1))`. No parsing happens when the
program runs.

## Scopes: shared storage

A scope is a dedicated global storage that the program and its spaces share, like global variables of their own:

- `scope A;` declares a scope, at the top level of a file.
- `scope.A.registery("name", type("t"))` appends a slot to the storage. Anything fits a slot. Its type is the
  grammar's: the space's resolver says which Nemerle type the token `"t"` stands for. A token that names a Nemerle type
  (`type("int")`) is that type, and any other token reads as `object`. The code that uses a slot is type-checked as
  usual.
- `scope.A.name = e` writes a slot, and `scope.A.name` reads it, anywhere in the program, when it runs.
- `space G [A, B] { ... }` attaches scopes to a space. Its mappings reach a scope through their `NitraDialectContext`:
  `Read("name")` and `Write("name", value)` give the code that reads and writes a slot, for the space's own code.

```nemerle
scope A;
grammar Demo
{
  using Nemerle.Compiler.NitraDialectServices;
  using Nemerle.Compiler.Parsetree;
  syntax module Query
  {
    using Nitra.Core;
    [StartRule] syntax Input = "answer"
    {
      map (context : NitraDialectContext) PExpr = {
        def shared = context.Scope("A");
        shared.Write("doubled", <[ $(shared.Read("answer")) * 2 ]>)
      };
    }
  }
}

scope.A.registery("answer", type("int"));
scope.A.registery("doubled", type("int"));
scope.A.answer = 21;
space Demo [A] { answer }
System.Console.WriteLine(scope.A.doubled);
```

```text
42
```

The program writes `answer`, the space's code reads it and writes `doubled`, and the program reads that. The values
live in the storage while the program runs; a space that is not attached to a scope cannot use it.

The storage is the process's, so an application and the plugin scripts it runs share the same values (see
[Scripts as plugins](11-scripts.md)).

## Dials: calling into a space

A dial is a direct call into a space: `dial:.file.G::member(arguments)`, or `dial:.file.G::member` for the member as
a function value. `file` is the file module that holds the space (`main` for `main.n`), and the part after it says
which of the file's spaces:

| Space | Dial |
|---|---|
| `space G { ... }` | `dial:.file.G::member` |
| `space (A, B) { ... }` | `dial:.file.(A, B)::member`, in any order: `(B, A)` is the same space |
| `space { ... }` (plain) | `dial:.file::member` |

Each of these exists once per file, so the path is enough to find it. `space G as Name` gives a space a second name,
`dial:.file.Name::member`.

The grammar has no Nemerle members of its own. A **resolver** answers for it:
it says which members exist, with which signatures, and what code a call becomes.

A resolver implements `INitraDialectResolver`. It lives in a library of its own, because a grammar is compiled
separately and sees only the binaries the program references:

```nemerle,lib=dialres
// ncc: -r:{toolchain}/Nemerle.Compiler.dll
// file: dialres.n
using System;
using Nemerle.Compiler.NitraDialectServices;
using Nemerle.Compiler.Parsetree;

public class Resolver : INitraDialectResolver
{
  public ResolveType(name : string, _context : NitraDialectContext) : NitraDialectType
  {
    if (name == "number") NitraDialectType(name, "int") else null
  }
  public Resolve(request : NitraDialectRequest) : NitraDialectResolution
  {
    match (request.Name)
    {
      | "twice" =>
        def answer = NitraDialectResolution();
        answer.Signatures.Add(NitraDialectSignature("twice", NitraDialectType("number"), array[NitraDialectType("number")]));
        answer.Lower = Func(r => if (r.IsCall) <[ $(r.Arguments[0]) * 2 ]> else <[ fun (x : int) { x * 2 } ]>);
        answer
      | "shared" =>
        def answer = NitraDialectResolution();
        answer.Signatures.Add(NitraDialectSignature("shared", NitraDialectType("number"), array[]));
        answer.Lower = Func(r => r.Context.Scope("A").Read("value"));
        answer
      | _ => null
    }
  }
}

public Create() : INitraDialectResolver { Resolver() }
```

The space's mapping registers the resolver, and the program calls into the space:

```nemerle
// ncc: -r:{chapter}/dialres.dll -r:{toolchain}/Nemerle.Compiler.dll
scope A;
grammar G
{
  using Nemerle.Compiler.NitraDialectServices;
  using Nemerle.Compiler.Parsetree;
  syntax module M
  {
    using Nitra.Core;
    [StartRule] syntax Start = "go"
    {
      map PExpr = {
        def c = NitraDialectContext.Current;
        when (c.Space.Resolver == null) c.RegisterResolver(dialres.Create());
        <[ () ]>
      };
    }
  }
}

scope.A.registery("value", type("number"));
scope.A.value = 21;
space G [A] { go }
System.Console.WriteLine(dial:.main.G::twice(21));
System.Console.WriteLine(dial:.main.G::shared());
def f = dial:.main.G::twice;
System.Console.WriteLine(f(5));
```

```text
42
21
10
```

Calls are checked against the resolver's signatures, and a dial may stand before its space in the file.

## Which grammars a space uses

- **`space G { ... }`** uses grammar `G`.
- **`space (A, B) { ... }`** mixes grammars `A` and `B`: their rules combine, and together they must have one start
  rule. It is a space of its own, next to the file's `space A` and `space B`.
- **`space { ... }`** is a plain space, over full Nitra and across grammars. It uses the grammars of its own file;
  when those do not give exactly one start rule (or there are none), it uses every grammar the file can see: those of
  the other files and of referenced libraries.

## One space per grammar per file

A file uses each grammar in one space. That keeps a language's code in one place instead of scattered across a file:

```nemerle,fail
grammar Small
{
  using Nemerle.Compiler.Parsetree;
  syntax module M
  {
    using Nitra.Core;
    [StartRule] syntax Start = "one" { map PExpr = <[ System.Console.WriteLine(1) ]>; }
  }
}

space Small { one }
space Small { one }
```

```text
duplicate space
```

`space Small as Other { ... }` gives the space a second name, which a dial can use (`dial:.file.Other::member`). It
is still the file's one `Small` space. A mixing space `space (Small, Big) { ... }` and the plain `space { ... }` are
different spaces, so they can stand next to `space Small` in the same file.

## Spaces are top level

A space inside a function or a type, or used as a value, is an error:

```nemerle,fail
grammar Small
{
  using Nemerle.Compiler.Parsetree;
  syntax module M
  {
    using Nitra.Core;
    [StartRule] syntax Start = "one" { map PExpr = <[ 1 ]>; }
  }
}

Twice() : int { 2 * space Small { one } }
```

```text
a space must be at the top level of the file
```

Results come back through a scope or a dial instead.

## Sharing grammars

A grammar compiled into a library travels with it. The library's continuation section (see `doc/CONTINUATION.md`)
stores the compiled grammar and, next to it, the library's scopes with their slots. A program that references the
library uses the grammar in a space without compiling it again, and knows the library's scopes:

```nemerle,lib=calclib
// file: calclib.n
grammar Units
{
  using Nemerle.Compiler.Parsetree;
  syntax module Length
  {
    using Nitra.Core;
    [StartRule] syntax Start = Value=Digits Unit
    {
      map PExpr = <[ System.Console.WriteLine($(int.Parse(GetText(this.Value)) : int) * $(this.Unit.GetAst())) ]>;
    }
    regex Digits = ['0'..'9']+;
    syntax Unit
    {
      map PExpr;
      | Metres = "m" { map PExpr = <[ 1 ]>; }
      | Kilometres = "km" { map PExpr = <[ 1000 ]>; }
    }
  }
}
```

```nemerle
// ncc: -r:{chapter}/calclib.dll
space Units { 3 km }
```

```text
3000
```

The program has no grammar of its own, so a plain `space { 3 km }` would find `Units` as well.

A scope travels as its layout, its slots and their types; the values stay in the storage of the running program. A
slot that holds a dial reference (`scope.A.registery("f", dial:.file.G::member)`) is not stored; the space it points to
is (see below).

When a program redefines a stored grammar and only some alternatives changed, the compiler recompiles just those
alternatives.

The section also stores the library's spaces, together with the scopes they use. A program that references the library
can dial into them, `dial:.file.G::member` with the library's file, as it dials into its own.

Scripts continue from libraries the same way, which makes a script a plugin of the application that hosts it. A
script can use the host's grammars, scopes and dials without defining any of them (see [Scripts](11-scripts.md)).

Like macros, grammars are language extensions: a distributed grammar comes with its source under the GPL.
