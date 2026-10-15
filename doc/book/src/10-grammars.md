# Grammars and spaces

Macros extend the language one construct at a time. A **grammar** goes further: it defines a whole small language, and
a **space** block writes code in it, right inside a Nemerle program. The grammar machinery is Nitra, built into the
compiler. The grammar is checked and compiled with the program, and a `space` is translated to ordinary Nemerle code,
so nothing of Nitra is needed when the program runs.

## A first grammar

```nemerle
using System.Console;

grammar Greetings
{
  using Nemerle.Compiler.Parsetree;
  syntax module Hello
  {
    using Nitra.Core;
    [StartRule] syntax Start = Greeting { map PExpr { Greeting } }
    syntax Greeting
    {
      map PExpr;
      | Morning = "good" "morning" { map PExpr = <[ "Guten Morgen" ]>; }
      | Night = "good" "night" { map PExpr = <[ "Gute Nacht" ]>; }
    }
  }
}

WriteLine(space Greetings { good morning })
```

```text
Guten Morgen
```

Line by line:

- **`grammar Greetings`** declares a grammar. Its body is Nitra: `using`s, then one or more `syntax module`s.
- **`using Nitra.Core;`** brings the standard rules: whitespace, `IdentifierBody`, and more.
- **`[StartRule]`** marks where parsing of a `space` begins.
- **`syntax Greeting { | Morning = ... | Night = ... }`** is an *extensible rule* with alternatives.
  - A rule with `=` and no alternatives, like `Start`, is a sequence.
  - String literals are keywords; spaces between them are allowed by default.
- **`map PExpr`** says what each piece of syntax becomes: Nemerle code (`PExpr`), usually built with a quotation, as in
  macros. `{ Greeting }` maps a rule to the mapping of its only part.
- **`space Greetings { ... }`** parses its body with the grammar's start rule and replaces itself with the mapped code.

## A calculator

Rules can have named parts, regular-expression tokens and precedence:

```nemerle
using System.Console;

grammar Calc
{
  using Nemerle.Compiler.Parsetree;
  syntax module Arith
  {
    using Nitra.Core;
    [StartRule] syntax Start = Expr { map PExpr { Expr } }
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
WriteLine(space Calc { 2 + 3 * (width - 1) })
```

```text
11
```

- **`Left=Expr`** names a part so the mapping can use it: `this.Left.GetAst()` is the code it maps to.
- **`regex Digits = ['0'..'9']+;`** defines a token. `GetText(this.Value)` is the text it matched.
- **`precedence Sum:` / `precedence Product:`** group alternatives by binding strength, later groups binding tighter.
  `right-associative` after an alternative makes it group to the right.
- **`$(name : usesite)`** produces a reference to a name as seen at the `space`. Here `width` is the Nemerle variable
  of the program; a grammar can reach the code around it.

The `space` above compiles to exactly `2 + 3 * (width - 1)`. No parsing happens when the program runs.

## One space per grammar per file

A file uses each grammar in one `space` block. That keeps a language's code in one place instead of scattered across a
file:

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

System.Console.WriteLine(space Small { one } + space Small { one })
```

```text
duplicate dialect space
```

When a file really needs a second one, give it a name of its own with `space Small as Other { ... }`.

## Sharing grammars

A grammar compiled into a library travels with it. The library's continuation section stores the compiled grammar (see
`doc/CONTINUATION.md`). A program that references the library uses the grammar in `space` without compiling it again:

```nemerle,lib=calclib
// file: calclib.n
grammar Units
{
  using Nemerle.Compiler.Parsetree;
  syntax module Length
  {
    using Nitra.Core;
    [StartRule] syntax Start = Value=Digits Unit { map PExpr = <[ $(int.Parse(GetText(this.Value)) : int) * $(this.Unit.GetAst()) ]>; }
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
System.Console.WriteLine(space Units { 3 km })
```

```text
3000
```

When a program redefines a stored grammar and only some alternatives changed, the compiler recompiles just those
alternatives.

Like macros, grammars are language extensions: a distributed grammar comes with its source under the GPL.
