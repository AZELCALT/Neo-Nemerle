# Grammars and spaces

Macros extend the language one construct at a time. A **grammar** goes further: it defines a whole small language.
A **space** is code written in that language: a logical file of its own inside a Nemerle file. The grammar machinery
is Nitra, built into the compiler. The grammar is checked and compiled with the program, and a space is translated to
ordinary Nemerle code, so nothing of Nitra is needed when the program runs.

A space is always at the top level of its file, like a declaration. It is not an expression, and it does not go
inside a function or type. The program and its spaces communicate in two ways:

- **scopes**, a shared memory zone. The program puts bindings in a scope, a space reads them, and a space can write
  bindings back for the program to read;
- **dials**, direct calls into a space: `dial:.file.space::member(...)` reaches a member of one space of one file.

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

## Scopes: shared memory

A scope is a named set of bindings that the program and its spaces share:

- `scope A;` declares a scope.
- `scope.A.registery("name", type("t"))` adds a binding. The type is a token that the space's dial gives meaning to.
- `scope.A.name = e` gives a binding its value, and `scope.A.name` reads it.
- `space G [A] { ... }` attaches the scope to a space. A mapping reaches it through its `NitraDialectContext`, with
  `Get` and `Set`.

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
        shared.Set("doubled", <[ $(shared.Get("answer").Value :> PExpr) * 2 ]>);
        <[ () ]>
      };
    }
  }
}

scope.A.registery("answer", type("integer"));
scope.A.registery("doubled", type("integer"));
scope.A.answer = 21;
space Demo [A] { answer }
System.Console.WriteLine(scope.A.doubled);
```

```text
42
```

The program writes `answer`, the space reads it and writes `doubled`, and the program reads that. A binding holds
code, not a run-time value: `scope.A.doubled` is replaced by `21 * 2`. A space that is not attached to a scope cannot
see it.

## Dials: calling into a space

A dial is a direct call into a space: `dial:.file.space::member(arguments)`, or `dial:.file.space::member` for the
member as a function value.

- `dial` is the grammar the space is written in (`G`);
- `file` is the file module that holds the space (`main` for `main.n`);
- `space` is the space's name, given with `space G as Name { ... }`;
- `member` is what the call reaches in that space.

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
    if (name == "number") NitraDialectType(name) else null
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
        answer.Lower = Func(r => r.Context.Scope("A").Get("value").Value :> PExpr);
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
space G as Tools [A] { go }
System.Console.WriteLine(G:.main.Tools::twice(21));
System.Console.WriteLine(G:.main.Tools::shared());
def f = G:.main.Tools::twice;
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
  rule.
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
duplicate dialect space
```

When a file really needs a second one, give it a name of its own with `space Small as Other { ... }`.

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
stores the compiled grammar and, next to it, the library's scopes with their bindings. A program that references the
library uses the grammar in a space without compiling it again, and starts with the library's scope bindings:

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

A binding whose value is code is stored as that code's text. A binding that holds a dial reference
(`scope.A.f = G:.file.space::member`) points into the library's own spaces and is not stored.

When a program redefines a stored grammar and only some alternatives changed, the compiler recompiles just those
alternatives.

Scripts continue from libraries the same way, which makes a script a plugin of the application that hosts it. A
script can use the host's grammars, scopes and dials without defining any of them (see [Scripts](11-scripts.md)).

Like macros, grammars are language extensions: a distributed grammar comes with its source under the GPL.
