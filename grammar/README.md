# Experimental source grammars

This prototype recognizes source-defined languages inside Nemerle `space` blocks.
It uses compiler-owned grammar matching, not Nitra binaries or a second runtime
interpreter. Its match records are captures with source locations, not a separate
semantic AST framework. Execution and normalization into Nemerle AST are part 2.
The declaration spelling is a draft for review, not a stable language contract.
All four planned phases remain experimental, even after implementation; see the
[roadmap](PART2.md). Future executable modes must retain an explicit experimental
gate and go through usage feedback before stabilization.

The compiler also has an opt-in [opaque block archive mode](ARCHIVES.md) for
`runtime`, `compile`, `grammar`, and `space` placeholders. Its DLL-carried IR does
not require phase-1 recognition or execute block contents.

A separate [structural projection side parser](STRUCTURAL-PROJECTION.md) starts
the shared-region recognition approach described in the architecture note. It is
an explicitly gated compiler API, with no new source syntax or AST consumer yet.

## Try it

Use the isolated compiler path recorded in `baseline/GRAMMAR-RESULT.md`:

```sh
dotnet /path/to/prototype/ncc.exe -parse-grammar-spaces -no-color \
  nemerle/grammar/examples/arithmetic.n
```

The option writes one JSON document to stdout, diagnostics to stderr, and exits
nonzero on failure. It does not emit an assembly. Normal compilation of these
constructs explicitly reports that normalization is not implemented. The installed
`toolchain/coreclr` is not replaced by the prototype build.

Build and verify from the workspace root:

```sh
python baseline/build-coreclr-toolchain.py --bootstrap toolchain/coreclr \
  --references /usr/share/dotnet/packs/Microsoft.NETCore.App.Ref/10.0.12/ref/net10.0
python baseline/check-grammars.py /path/to/build/stage2/ncc.exe \
  --references /usr/share/dotnet/packs/Microsoft.NETCore.App.Ref/10.0.12/ref/net10.0
```

## Declaration model

```nemerle
grammar Arithmetic {
  statement general form { "start" ...operation... "end" }
  syntax module Expressions {
    form general;
    semantic kind operation { | Evaluate = Value=Expr; }
    regex Digits = ['0'..'9']+;
    syntax Expr {
      | Number = Digits;
      | Parenthesized = "(" Expr ")";
      precedence Additive:
      | Add = Expr "+" Expr;
      precedence Multiplicative:
      | Multiply = Expr "*" Expr;
    }
  }
}
space Arithmetic { start 1 + 2 * 3 end }
```

`grammar` names the containing definition. A statement form establishes the
literal arrangement and content slots. A syntax module binds to a form and
supplies its details. A semantic kind owns the alternatives that can fill a slot;
it participates in parsing directly, not CLR-type classification after parsing.
One operation at the enclosing level may contain nested operations internally.
A slot is exact-one unless followed by `?`, `*`, or `+`.

Rule notation includes sequences, parenthesized alternatives, named captures,
character ranges, repetition, separated lists such as `(Expr; ",")+`, and `!`/`&`
lookahead. Repetition is greedy. Named expression precedence groups increase in
binding strength in declaration order. `right-associative`, `left-associative`,
and `Expr ^ Group` are recognized. An extension can insert a group with
`precedence Between order Additive < Between < Multiplicative:`.

Nonlexical rules skip whitespace and lexical `IgnoreToken` rules. Regex/token
rules match characters directly. Ordinary word literals have identifier boundaries;
prefixes beginning with digits, such as `"0x"`, can join another lexical component.
`[ExplicitSpaces]` disables implicit spacing for that rule. `Any` matches one
UTF-16 code unit. Core spacing/formatting markers are available; see the precise
compatibility limits in `COMPATIBILITY.md`.

## Selection and composition

```nemerle
space Arithmetic { start 42 end }
space (Arithmetic, Sql) { start 42 end SELECT * FROM players; }
space { start 42 end }
```

Plain space considers visible grammars, not every grammar in the compilation.
File owners qualify definitions: `using arithmetic;` opens definitions in
`arithmetic.n`; `using A = arithmetic.Arithmetic;` permits `space A { ... }`.
Source definitions are indexed before use, so changing source-file order does not
change resolution. Grammar definitions are currently file-level declarations.

Inside a syntax module, `using B = arithmetic.Arithmetic.Expressions;` opens a
module for rule references. `extend syntax B.Expr { ... }` and
`extend semantic kind B.operation { ... }` contribute alternatives when their
containing grammar participates in the selected composition. They do not mutate
other zones' definitions. Imported modules supply rule dependencies without
implicitly becoming root statement forms of a named space.

A `Space` rule can be included in a semantic-kind variant to accept a nested
`space Name { ... }`, list-selected space, or plain space at that position. Parsing
returns to the outer grammar after it. Cross-grammar composition and extensions
are retained capabilities, not prohibited by the statement-form model.

## Match and action inspection

The public host entry point is `ManagerClass.ParseGrammarSources()` using
`CompilationOptions.Sources`, `FileModules`, and `SourceRoot`. It initializes the
compiler scope and returns `GrammarParseResult`; it does not run hierarchy binding
or emission. `GrammarParsing.ParseSources(manager, sources, sourceRoot)` is the
lower-level API for an already prepared manager.

The result contains `Matches`, `Diagnostics`, `Actions`, `RuleEvaluations`, and
`MemoHits`, with `Success` and `ToJson()`. Match records contain kind, name,
grammar/module/variant identity, captures, children, and half-open UTF-16 source
offsets. Every match retains the original file path. Diagnostics carry file,
offset, and message. The JSON inspection format currently has version 1.

Rule action bodies use ordinary Nemerle blocks:

```nemerle
semantic kind operation {
  | Evaluate = Value=Expr { Outer.Helper(); };
}
```

Actions retain their original text, span, parsed Nemerle expression AST, and outer
file scope/imports. They do not execute, resolve types, or decide recognition in
this milestone. Calls are not confined to a closed grammar language. Custom
symbol resolution for foreign source inside space is separately deferred.

Recognition rejects ambiguous complete matches, missing references, precedence
cycles, unsupported left-recursive cycles, and non-progressing forms/repetitions.
Precedence expression recursion is supported. Prototype guardrails are 256 rule
nesting levels, 64 nested spaces, 4,096 competing states, and one million matching
steps per zone. Guardrail exhaustion is a diagnostic, not a successful partial parse.
These defaults are implementation limits for review, not a permanent language policy.

Examples include arithmetic, a small imperative language, and a SELECT-shaped SQL
subset. SQL is parsed only: there is no database connection or SQL execution.

The separate [experimental native Nitra side parser](NITRA-SYNTAX.md) validates
the pinned declaration surface and provides prepared static recognition through
a CLR host API. Semantic bodies are retained for later phases.
