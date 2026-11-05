# Pascal in Nemerle

`pascal.n` is Pascal (the core of ISO 7185) as a grammar library. A Nemerle file that references `pascal.dll` can
hold a Pascal program in a space:

```nemerle
space Pascal
{
  program Factorials;
  var
    i : integer;

  function Factorial(n : integer) : integer;
  begin
    if n <= 1 then Factorial := 1
    else Factorial := n * Factorial(n - 1)
  end;

  begin
    for i := 1 to 6 do writeln(i, Factorial(i):6)
  end.
}
```

The program is translated to Nemerle code when the file is compiled, so it runs as fast as the same code written in
Nemerle, and nothing parses Pascal at run time. It is a demo of the grammar machinery and a test of it: the grammar is
written on the toolchain as it is, with no change to the compiler for it.

```sh
ncc samples/pascal/pascal.n -target:library -out:pascal.dll
ncc -r:pascal.dll samples/pascal/programs/sort.n -out:sort.exe
```

`tests/check-pascal.py` builds the library and runs every program in `programs/` against its `.out` file.

## What is in

- **Programs and blocks:** `program Name(input, output);`, `const`, `type`, `var`, nested `procedure`s and
  `function`s (recursive, reading and changing the variables around them), `begin ... end.`
- **Statements:** `:=`, `if ... then ... else`, `while ... do`, `repeat ... until`, `for ... to/downto ... do` (bounds
  evaluated once), `case ... of` with several labels and `else`, compound statements, the empty statement.
- **Types:** `integer`, `real`, `boolean`, `char`, `string`, subranges, `array [a..b, c..d] of T` (indexed from its own
  bounds, range-checked, `m[i, j]` is `m[i][j]`), named types.
- **Parameters:** value parameters and `var` parameters (copied in, and back when the routine returns; see below).
- **Expressions:** Pascal's precedence (`not`; `* / div mod and`; `+ - or`; relations), `/` gives a real.
- **Standard routines:** `write`, `writeln` (with `x:width` and `r:width:decimals`), `read`, `readln`, `abs`, `sqr`,
  `sqrt`, `sin`, `cos`, `arctan`, `exp`, `ln`, `trunc`, `round`, `odd`, `ord`, `chr`, `succ`, `pred`, `length`.
- **Lexical:** case-insensitive keywords and names, `(* ... *)` and `{ ... }` comments, `'it''s'` strings.
- **With Nemerle:** a name the Pascal program does not declare is the Nemerle program's, as written: Pascal calls the
  file's functions and reads its values (`programs/interop.n`).

Not in: records, pointers, sets, files, `goto`, `with`, enumerated types, `forward`, functions as parameters.

## How it maps

Each rule says what it becomes (`map PExpr`): a Pascal routine is a local function, a `var` a mutable, `for` a loop
with its bound kept once. The tables a mapping needs from earlier declarations (types, routines, the function being
mapped, its `var` parameters, the names declared) are kept while one program is mapped; Pascal declares before use,
so a declaration is always mapped before the code that uses it.

Two choices come from what the target allows: a local function takes no `ref` parameter, so a `var` parameter is a
cell (`PascalVar`) whose value is copied back after the call (the same as Pascal's, except when one variable is passed
twice); and a space's code is statements, so a Pascal program cannot declare types (hence no records).

## What it found

Writing it turned up these, investigated and kept as they are for now (the grammar works around them, or `KNOWN`
in the check lists them):

1. **A space's body is read by the Nemerle lexer before its own lane.** The lane is right: the main parse lexes the
   file with space bodies blanked (`DefaultParser.Parse`, `NitraSourceSession.Rewrite`). But two pre-scans lex the raw
   file first: `FileModuleRegistry.SourceUsings` (finding the `using`s, for `ncc`; a lexer exception there is an
   internal compiler error) and `ScriptMetadata.Collect` (finding a script's dependencies, for `nscript`). Nemerle's
   lexer reads `'x = '` as a character literal ("Newline in constant"). The lane's own envelope scan (`GReader.Block`)
   reads `'...'` and `"..."` with Nemerle's rules too (backslash escapes), so an apostrophe in a `{ ... }` comment
   leaves a quote open. `hello`, `factorial`, `sieve` and `casegrades` wait on it.
2. **Map code rejects `;` inside parentheses.** `NitraSyntax`'s `Parentheses = "(" Expression? ")"`, so a C-style
   `for (a; b; c)` in a mapping does not parse; the grammar uses `while`.
3. *(not a bug)* **A keyword's boundary check belongs in a `token`.** In a `syntax` rule Nitra skips spaces after each
   token, so `syntax K = KText !IdentifierPartCharacters;` checks the character after the space (`program Upper`
   fails at `U`); a `token` skips none, as Nitra's own `token Keyword = ... !IdentifierPartCharacters;` does.
4. **Mapped code has no location of its own:** the mappings' quotations take the space's location (the native host's
   `Output` runs them without locating each in its node's span), so an error in the Pascal program is reported at the
   `space` line.
5. **A space's syntax error is an offset** (`at offset 37`, into the body; `Expand` does not turn it into a line and
   column), **reported twice**: the typer restarts a body (`RestartRunBodyTyperException`), the space is expanded on
   each pass, and `Expand` reports with `Message.Error` directly rather than through the typer.
6. **Literals are case-sensitive**, with no option for a case-insensitive language: the grammar spells each keyword as
   a regular expression of both cases and keeps names from being reserved words with a predicate.
