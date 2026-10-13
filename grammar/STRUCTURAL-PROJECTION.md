# Structural projection side parser

Design reference: `typed_recursive_syntax_chunks_for_codex.txt` in the workspace
root. The intended system preserves Nitra-style syntax capabilities with shared
recognition and a more explicit authoring interface. This first slice is not a
full implementation of that target, and does not replace the earlier parser.

## Current operation

A host explicitly prepares a bounded set of kinds and forms with
`StructuralProjection.Prepare(kinds, forms)`. No additional source-language spelling is introduced.
A form in this slice has a name, one opener token, a body kind, and a nonempty
sequence of ending marks. A kind supplies a structural token-validation callback.
That callback checks observed body evidence; it does not build or resolve an AST.

Preparation groups forms by shared opener/body interface. Boundaries dispatch to
shared tail-prefix tries. Recognition observes the source token stream forward,
opens recursive regions, and closes bodies when their structural boundary is
established. Parents retain child IDs; they do not re-observe their contents.
Parentheses, brackets, and braces create shared child regions and protect inner
marks from closing outer bodies. Quoted marks and comments are not boundaries.

For `A: start Body ;`, `B: start Body end`, `C: start Body end start`, recognizing
`start this end start` retains:

- One closed body containing `this`, with its established `end` boundary.
- Elimination of the incompatible semicolon termination family.
- Shared terminal metadata for B and C at their different ending positions.
- A provisional open region at the final `start`, referenced by the tail's
  ownership relationship. It is not a committed second statement.

No candidate ASTs are allocated. No body is reparsed to choose B versus C.
If a longer tail partially matches and then fails, the shorter terminal group and
observed suffix remain with an `unresolved-suffix` relationship. Later resolution
must account for that suffix; it is not silently accepted as a valid program.

## Retained data and inspection

`StructuralProjectionPlan.Recognize(text, file)` returns
`StructuralProjectionResult`: original source/file, tokens, regions, tail
relationships, diagnostics, and counters. Regions retain half-open UTF-16 spans,
body token intervals, kind, parent/child IDs, boundary facts and invalid evidence.
Open regions survive incomplete input. Tail relationships retain shared terminal
groups, observed endpoints, pending state, and shared-region references.

`HasErrors == false` is not a declaration that an exact grammar production or a
whole program has been validated. The result may contain open regions, unresolved
ownership, and unresolved suffixes. Detailed sequence validation, production
identity, types and meaning belong to later consumers. Source and token intervals
are retained for those consumers without reconstructing a discarded prefix.

Counters measure token visits, kind checks, boundary checks, tail checks, child
region reuse and eliminated boundary families. They measure this recognizer's
work, not total future compilation cost or a universal complexity guarantee.
Only active tails are revisited; closed tails are retained without scanning their
history on every token. The stack handles deep nesting without recursive calls.

## Explicit first-slice limits

- Kinds validate individual body tokens; richer structural interfaces, placement,
  precedence, associativity and exact expression consumers are pending.
- One body kind is supported per opener, and implicit nesting currently requires
  the same kind. Different-kind containment needs a later interface.
- Opening marks cannot also be initial boundary marks. Tail marks that could close
  enclosing bodies or act as bracket delimiters are explicitly unsupported during
  preparation. Future ownership machinery must preserve these distinctions.
- Lexical input currently uses the existing experimental envelope tokenizer, with
  ordinary quotes and C comments. Arbitrary custom tokenization is pending.
- Error/incomplete evidence is retained; editor recovery policies and repairs are
  not implemented. Token validators run synchronously; `ArgumentException` is
  retained as a diagnostic, and other host callback exceptions propagate.
- Full grammar-source adaptation, compile/runtime facilities, exact AST consumers,
  archive serialization of these regions, and longer-lived IR remain future work.

These limits describe this implementation slice, not capability bans in the design.
The existing grammar parser and opaque `.nemir` archives remain separate facilities.

## Example host and verification

```csharp
var kinds = new[] { new StructuralKind("Body", token => true) };
var forms = new[] {
    new StructuralForm("A", "start", "Body", new[] { ";" }),
    new StructuralForm("B", "start", "Body", new[] { "end" }),
    new StructuralForm("C", "start", "Body", new[] { "end", "start" })
};
var plan = StructuralProjection.Prepare(kinds, forms);
var observed = plan.Recognize("start this end start", "example");
// observed.KindChecks == 1; inspect observed.Regions and observed.Tails.
```

Run `baseline/check-structural-projection.py --toolchain /path/to/prototype
--references /path/to/net10.0/refs`. The checks cover the architecture example,
recursive reuse, brackets/quotes, extension collisions, partial tails, incomplete
input, invalid evidence, UTF-16 spans, isolation, and flat/deep operation counts.
