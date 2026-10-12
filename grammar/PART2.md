# Experimental grammar roadmap

All four phases remain experimental, including after phase 4 is implemented.
Completing the roadmap does not stabilize the syntax or API. Real usage, diagnostics,
feedback, and subsequent design revisions are required before stabilization. Keep
these facilities behind explicit experimental options; the current phase-1 entry
point is `-parse-grammar-spaces`. Future compilation modes need an explicit
experimental gate too; their option spelling is not decided here.

## Phase 1: recognition foundation

The current prototype supplies forms, syntax modules, recursive semantic kinds,
grammar composition, captures, source spans, and inspectable matches. Forms provide
generic enclosing templates; syntax modules own detailed internal variants;
semantic kinds group reusable parsing roles. Current recognition limits are
implementation limits, not restrictions on the intended model. Actions are parsed
and retained but not bound or executed.

A separate [structural projection side parser](STRUCTURAL-PROJECTION.md) now starts
the kind-directed shared-region approach in the workspace architecture note. It is
an explicitly opted-in host API, not yet a replacement for the phase-1 grammar
engine. Shared regions, boundary-family elimination, recursive reuse and unresolved
tail relationships are implemented for its documented first-slice form model.

## Placeholder infrastructure (implemented, semantics pending)

The separate `-experimental-grammar-ir` archive mode retains opaque runtime,
compile, grammar, and space blocks, including grammar-list headers, in `.nemir`
sections of metadata-only DLLs. See [archive documentation](ARCHIVES.md). This
reserves syntax/IR extension points; it does not complete phases 2–4 or assign
interaction semantics.

## Phase 2: Nitra syntax-module surface and structural mapping

Latest user priority: establish at least the Nitra syntax-module surface before
populating compiler/runtime facilities. Reuse Nitra declaration syntax for syntax
modules and their detailed rules instead of inventing a replacement notation.
Forms remain reusable enclosing templates; syntax modules populate their positions.
Semantic kinds are explicit syntax-position types, describing structural shape,
permitted occupants, and recursion/nesting/precedence/associativity constraints.
An operand can admit numbers, variable references, function results, and operations
without requiring a new delimiter around every occupant. Existing examples are not
yet a complete reusable operand/expression preset.

Map recognition declarations to shared structural components and kind interfaces.
Preserve detailed rule distinctions for later consumers, without eagerly expanding
candidate ASTs. Use the compatibility inventory and actual Nitra declarations to
track surface coverage. This is compatibility of the declaration interface, not a
requirement to reproduce Nitra's internal architecture.

When declarations contain deeper compiler/semantic operations, retain their source
and structural attachment for the later compiler/runtime side. Recognizing or
retaining a declaration does not mean its behavior is implemented. Report those
boundaries explicitly; do not silently execute, discard, or claim support for the
retained behavior. Define detailed mapping against the actual upstream syntax
before expanding the reader. Full workbench/IDE infrastructure is not required to
establish syntax-module coverage.

## Phase 3: populate compiler and runtime facilities

After the syntax-module surface and structural mapping are established, design
`compile name { ... }` and `runtime name { ... }` facilities with the user. Their
headers can already be archived; their body languages and semantics remain open.
Compiler facilities provide symbol lookup, overload resolution, construction and
transformation. Runtime facilities provide operations such as dispatch. Constructs
may require both. Preserve recognized components until their responsible phase,
and connect normalization to existing Nemerle AST, macros, typing and CLR emission
where appropriate.

Define action binding, phase contracts, foreign-space lookup, compiler-time state,
and diagnostics before exposing these facilities. Grammar-side Nemerle code uses
ordinary enclosing scope, distinct from foreign-space symbol resolution. Do not
reduce all custom constructs to immediate runtime expression evaluation, or treat
current ambiguity diagnostics as the final meaning-based resolution policy.

## Phase 4: longer-lived IR and extension

Retain an intermediate representation suitable for later reuse and additions.
Adding rules enlarges a bounded compilation composition, like adding source files;
it does not inherently require unpredictable rule mutation during parsing. Resolve
and validate the applicable composition for each compilation operation.

The proposed `grammar { ... }` and `grammar (list_of_grammar) { ... }` interaction
blocks allow explicit, finer-grained cross-grammar behavior. Their headers now have archive placeholders; body syntax,
visibility, and resolution contracts remain to be designed. They are not required
for every composition. Existing named and list-selected `space` blocks control
recognition scope and are not these proposed interaction declarations.

## Feedback and validation

Together these facilities form a compiler-building system within Nemerle: grammar
definition, recognition, compiler operations, runtime integration, and retained
models. Provide inspectable intermediate results and useful diagnostics as the
phases evolve, and use examples and user feedback to revise the design. The exact
feedback interfaces remain open. Finishing phase 4 alone is not a stability claim.

Measure rule evaluations, memo reuse, memory, and timing on broader compositions.
Reduced authoring boilerplate and bounded compositions are useful design choices,
not an automatic linear-time performance guarantee.
