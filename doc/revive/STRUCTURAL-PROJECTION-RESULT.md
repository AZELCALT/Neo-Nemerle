# Structural projection starting slice

Architecture context is saved in workspace `MEMORY.md`, referencing the user's
`typed_recursive_syntax_chunks_for_codex.txt`. The design target is Nitra-style
capability with shared structural recognition and an explicit authoring interface,
not a deliberately reduced language or a universal linear-time claim.

Implemented a separate experimental Nemerle-authored side parser in
`nemerle/ncc/parsing/StructuralProjection.n`. Its host preparation API requires
explicit experimental opt-in. It prepares shared opener/body families and tail
tries, observes tokens forward, retains reusable recursive regions, eliminates
incompatible boundary families, and preserves unresolved tail/token ownership.
Source, tokens and spans survive for later consumers. No candidate ASTs are built,
no source rewinds are performed, and closed bodies are not reparsed per form.

## Verification

The final source-built compiler is `/tmp/nemerle-core-selfbuild-nrsa9u4i/stage2`.
Both CoreCLR self-build stages passed using .NET 10 reference assemblies (10.0.12).
The isolated package is `toolchain/structural-projection-prototype`; its binaries
match the final build. Previously packaged coreclr, grammar, and archive toolchains
still match their recorded hashes and are unchanged.

- [Structural checks](coreclr-verification/structural-projection-api.log): passed.
  Covers the user example, recursive child reuse, brackets/quotes/comments,
  shared-form collisions, 100 extension endings, tail-prefix failures, parent/tail
  ownership, incomplete regions, invalid evidence, UTF-16 spans and isolation.
- [Existing grammar recognition](coreclr-verification/structural-projection-grammar-regressions.log): all 47 cases passed.
- [Archive API/signing](coreclr-verification/structural-projection-archive-regressions.log): passed.
- [Upstream lexer/parser/macro fixtures](coreclr-verification/structural-projection-upstream.log): five passed.
- [Two-stage build](coreclr-verification/structural-projection-selfbuild-final.log): passed.

For `start this end start`, four tokens are visited and the body validator is
called once. The closed body survives with both ending groups and a shared-token
reference to the provisional next region. Adding 100 shared-body extension forms
does not multiply body observations; tail dispatch takes one check for the selected
next token in the tested case.

Flat 10/100/1000-region inputs produce 30/300/3000 token visits and 10/100/1000 kind
checks. Nesting depth 1000 produces 2001 token visits, one kind check and 999 child
region reuses. These are operation measurements for the tested structural subset,
not proof of full grammar equivalence or total compiler performance.

[Distribution/source hashes](coreclr-verification/structural-projection-distribution.json).

## Use and next boundary

See [the API example and limitations](../nemerle/grammar/STRUCTURAL-PROJECTION.md).
Run from the workspace root:

```sh
python baseline/check-structural-projection.py --toolchain toolchain/structural-projection-prototype --references /usr/share/dotnet/packs/Microsoft.NETCore.App.Ref/10.0.12/ref/net10.0
```

This slice deliberately has no new source syntax. Full grammar-source adaptation,
richer kind interfaces and ownership cases, precedence/associativity consumers,
AST lowering, compiler/runtime facilities and persisted structural IR remain
unfinished. `HasErrors == false` is not full-production acceptance; unresolved or
incomplete structure is explicitly retained. All facilities remain experimental.
