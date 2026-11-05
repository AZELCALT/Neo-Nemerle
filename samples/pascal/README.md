# Pascal in Nemerle

Pascal, as ISO 7185 has it, with Turbo Pascal's units, as a grammar library. A Nemerle file holds a Pascal program or a
unit in a space:

```nemerle
// file: geometry.n
space Pascal
{
  unit Geometry;
  interface
    type Point = record x, y : real end;
    function Distance(a, b : Point) : real;
  implementation
    function Distance(a, b : Point) : real;
    begin Distance := sqrt(sqr(a.x - b.x) + sqr(a.y - b.y)) end;
  end.
}

// file: main.n
space Pascal
{
  program Main;
  uses Geometry;
  var p, q : Point;
  begin
    q.x := 3; q.y := 4;
    writeln(Distance(p, q):4:1)
  end.
}
```

`ncc -r:pascal.dll main.n` finds geometry.n from `uses Geometry`, as a `using` finds a file. Each space is translated
when its file is compiled: a program's or a unit's declarations become members of its file's module (its variables
fields, its routines methods, its records classes), its statements the file's top-level code. So the program runs as
the same code written in Nemerle would, nothing parses Pascal at run time, and Nemerle (or C#) calls a unit's
interface as it calls any module: `geometry.Distance(a, b)`.

```sh
ncc samples/pascal/pascalfront.n -target:library -out:pascalfront.dll -r:Nemerle.Compiler.dll -r:Integrated.Nitra.Runtime.dll
ncc samples/pascal/pascal.n -target:library -out:pascal.dll -r:pascalfront.dll -r:Nemerle.Compiler.dll
ncc -r:pascal.dll samples/pascal/programs/sort.n -out:sort.exe
```

`tests/check-pascal.py` builds both and runs every program of `programs/` (and the folder `programs/units/`) against
its `.out` file, with its `.in` file as its input.

## How it is made

- **`pascal.n`, the grammar:** Pascal's syntax, case-insensitive (each keyword in any case, never the start of a
  longer name). Its rule methods (`Ast() : object`) build the front end's syntax tree; its root mapping hands that tree
  to the front end. It also holds what the translated programs use at run time: arrays with their own bounds,
  pointers, sets, the base of records, text and typed files, the standard routines' helpers.
- **`pascalfront.n`, the front end:** Pascal's scopes and types, its checks (each error at its Pascal line), and the
  Nemerle code. It runs in the compiler, when the space is mapped; it is a library of its own, found beside pascal.dll.

The front end stands on the grammar lane's facilities for a space that is a logical file (book, chapter 10): a space
that declares is mapped before the program is typed, its `<[ decl: ... ]>` members are its file module's, and
`SpaceFiles.Import`/`Export` are how a unit finds another's interface. `PascalImports` (an `ISpaceImports`) tells the
compiler what a Pascal space `uses`, so the units' files are found.

## What is in

- **Programs and units:** `program Name(input, output);`, `uses`; `unit Name; interface ... implementation ...
  [begin ...] end.` (a unit is in the file of its name), `uses` in the interface and in the implementation (two units
  may use each other through an implementation), initialization in the order of use, after the units a unit uses.
- **Declarations:** `label`, `const`, `type`, `var`, `procedure` and `function`, nested to any depth, recursive,
  `forward`; value, `var` and procedural parameters (`function f(x : real) : real`, `procedure p(var a : integer)`),
  and conformant array parameters (ISO's level 1: `a : array [lo..hi : integer] of real`, of one or more dimensions,
  `lo` and `hi` its bounds).
- **Types:** `integer`, `real`, `boolean`, `char`, enumerations, subranges (checked), `array` of any index types
  (`array [Color] of string`, `array [1..3, 1..3]`), `record` with a variant part, `set of`, `file of`, `text`, pointers
  (`^T`, declared before their target in the same section), `packed`; Turbo's `string`.
- **Statements:** `:=`, `begin ... end`, `if`, `while`, `repeat`, `for ... to/downto`, `case` (with Turbo's `else`
  and `1..5:` labels), `with`, `goto` (to a label declared in its block's `label` section, of a statement sequence
  around it, in its routine or in a routine around it: out of a recursion), procedure calls; a loop's variable is not
  assigned inside it, and a function assigns its result.
- **Expressions:** Pascal's precedence, `div`/`mod` (Pascal's), `/` real, set constructors (`['a'..'z', '_']`),
  `in`, set `+ - *` and `= <> <= >=`, `nil`, string comparison and concatenation.
- **Standard routines:** `read`, `readln`, `write`, `writeln` (on files too, with `x:w` and `r:w:d`), `eof`, `eoln`,
  `reset`, `rewrite`, `get`, `put`, `page`, `new`, `dispose`, `pack`, `unpack`, `abs`, `sqr`, `sqrt`, `sin`, `cos`,
  `arctan`, `exp`, `ln`, `trunc`, `round`, `odd`, `ord`, `chr`, `succ`, `pred`; Turbo's `assign`, `close`,
  `length`, `copy`, `pos`, `concat`, `upcase`, `inc`, `dec`, `halt`.
- **With Nemerle:** a name the Pascal program does not declare is the Nemerle program's, as written: Pascal calls the
  file's functions and reads its values.

A `var` parameter is the variable itself (a `ref` parameter), in a routine at any depth: a nested routine gets the
`var` parameters of the routines around it that it uses as parameters of its own, so it changes the caller's variable,
not a copy. A procedural parameter with `var` parameters is a delegate, which a routine with those parameters is
given as.

Where the choice is the implementation's, ISO lets it be:

- **A set is of 0..255** (ISO leaves the largest set to the implementation, as Turbo's is): of an enumeration, of
  `0..255`, of `char`. It is 256 bits, so `+ - *` and `in` are a few instructions on four words, and a set is a value,
  as Pascal's are. A wider base type is an error where it is declared; a `set of char` holds the characters 0..255,
  and another character is an error where it is put in one, when the program runs.
- **A file of any type is a value per line, as JSON** (records with arrays and sets among them), so another program
  can read it.
- **A record is a class that assignment copies.**

One thing .NET does not do: keep a reference to a variable in a value. So a nested routine that uses a `var`
parameter of a routine around it is not passed as a procedural parameter (the routine passed would need the variable,
and the parameter's value cannot keep it); the error says which parameter. Passing one that uses none, or a top-level
routine, is fine.

## What it found

Writing the first version (statements only) turned up these in the compiler and the grammar machinery; they are fixed
and `tests/check-pascal.py` keeps them so:

1. **A space's body was read by the Nemerle lexer before its own lane**: the pre-scans for a file's `using`s and a
   script's dependencies lexed the raw file, and the lane's envelope scan read quotes Nemerle's way.
2. **Map code rejected `;` inside parentheses** (a C-style `for` in a mapping), from upstream Nitra.
3. **Mapped code had no location of its own**, so an error pointed at the `space` line.
4. **A space's syntax error was an offset, reported twice**, then a bare "parse error".

Making `var` parameters the variables themselves at any depth turned up two more, fixed in the compiler: a local
function could not have `ref` or `out` parameters, and a lambda with them could not be a delegate (C#'s
`(ref int x) => ...`). And a delegate a space declares had no environment.

Units needed what a space could not do yet: declare members, be mapped before typing, find another space, and be
found as a file. Those are the facilities above. And two are how Nitra is: a keyword's boundary check belongs in a
`token` (a `syntax` rule skips spaces before a predicate), and literals are case-sensitive.
