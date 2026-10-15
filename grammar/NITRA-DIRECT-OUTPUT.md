# Settled structures and direct Nemerle output

This slice provides a running recognition-to-compilation bridge. Semantic and
output callbacks are supplied by a compiler host or macro. It does **not** yet
automatically compile retained native `ast`, `map syntax`, rule-method, or
dependent-property declaration bodies. The complete semantic declaration compiler
is not ported.

## Pipeline and APIs

Equivalent structural operations are interned across native productions; variants
retain their identities. Recognition settles endpoint constraints without candidate
ASTs. `NitraSyntax.Structure(grammar, rule, source, resolver, true)` consumes the
retained evidence without recognizing source again. It materializes the selected
interpretation, sharing objects by operation/span. Ambiguity is diagnosed or resolved
through compact operation/span options before semantic evaluation.

`NitraStructure.Captures(name)` finds captures belonging to that production,
stopping at nested rule/capture boundaries. Text preserves exact spans, including
spacing consumed by native rules. Regular repetitions without visible captures
can remain opaque spans.

`NitraCompilation.Compile(grammar, rule, source, context, resolver, true)` returns
an expression, structure, and diagnostics. Contexts take the current macro `Typer`,
scope, and location, are single-use, and restore compiler ambient state afterward.

Register `context.Mappings[productionLabel]` callbacks returning `PExpr` directly.
Dispatch is on variants, not identically named call/rule wrappers. Single-body rules
use their qualified rule label; named alternatives append their name. Output is
constructed once per object. Wrappers forward one child; sequences can forward one
significant child after omitting `void`/marker spacing. Other sequences require a
mapping. Unsupported syntax is not silently discarded.

Callbacks use quotations, hygienic names, `context.At(node)`, and existing typing
facilities. The ordinary compiler and unchanged backend compile their output.
There is no completed executable Nitra AST followed by a conversion pass.

## Semantic services

Symbols retain identity separately from source declarations. Abstract scopes allow
programmable lookup; tables support local candidates and nearest-table shadowing.
`context.Resolve` requires one candidate or invokes a custom selection callback.

Explicit semantic properties have names, stages, prerequisites, and evaluators.
Missing and later-stage prerequisites are rejected before evaluation. Same-stage
dependencies are scheduled or diagnosed as cyclic. This is an explicit scheduler,
not Nitra's automatic source dependency compiler.

`NitraTypeSolver` supports structural type arguments, bounded variables, programmable
subtyping, occurs checks, and transactional unification. Speculative checks and failed
or throwing operations restore bindings. This adapts Nitra's constraint model rather
than implementing every type system.

Rejected/unresolved structures do not execute semantic/output callbacks. Compiler-state
restoration does not roll back arbitrary mutations of host-owned state by callbacks.

## Source envelopes and limits

Grammar and space blocks are compiled automatically. To use this host-configured
path instead, set `CompilationOptions.NitraSources` to a `NitraSourceConfiguration`
with a context factory. Native modules stay inside `grammar G { ... }`; custom
expressions stay inside `space G { ... }`, `space (G, H) { ... }`, or local bare
`space { ... }`. Selected modules must expose exactly one selected start rule.
Bare spaces select grammars in the same source; named selections use a compilation-local
registry. Normal grammar-name import aliases and full file-module visibility integration
are unfinished.

Declaration removal/internal expression hooks preserve source length and newlines.
The envelope reader scans braces with its existing string/comment conventions;
bodies are then recognized as raw foreign source. Arbitrary delimiter conventions,
nested custom-space execution, grammar-list interaction semantics, and runtime/compile
body execution remain unfinished. Compilation rejects inspection/archive/recognition-only
mode combinations. No configuration means ordinary compilation remains unchanged.

Materialization limits are depth 512 and 500,000 objects/interpretation states;
recognition retains its region/evaluation limits. No universal complexity claim is made.

## Checks and remaining work

Run `tests/check-nitra-structures.py` with `--toolchain
toolchain/nitra-direct-output-prototype` and the .NET reference directory via
`--references`. It compiles and executes arithmetic and variable dialects, tests
staged symbols, hygienic bindings, ambiguity, capture ownership, shared bodies,
long lists, type constraints/rollback, dependencies, source identity and recovery.

Remaining approved-plan work: automatic native semantic declaration/mapping generation,
broader semantic compatibility, full form/boundary projection integration, automatic
declaration output, and replacing the older prototype engine after equivalence checks.
Those are not claimed complete. The user's friendlier declaration dialect remains deferred.

## Native-core integration in progress

The current integration direction keeps native Nitra definitions inside `grammar`
and their use inside `space`; it does not activate custom syntax in surrounding
Nemerle. Native Nitra syntax modules remain active. The additional custom dialect
is suspended while the native semantic infrastructure is brought in.

`NitraSyntax.ReadSourceGrammar` retains custom statement forms, semantic kinds,
form bindings and runtime/compile placeholders in `NitraDocument.InactiveConstructs`,
blanking them before strict native validation without moving UTF-16 offsets or
newlines. Original source and declaration text are preserved. `Read` remains the
strict native reader. Inactive declarations do not contribute recognition rules.
Inspection JSON labels each retained construct `active: false`.

In the experimental source host, runtime/compile envelopes are also retained and
blanked before ordinary Nemerle parsing. Their bodies are not parsed as Nemerle or
executed. `NitraSourceConfiguration.InactiveConstructs` exposes the collected source
records. This does not enable any new runtime/compile behavior.

`build/build-nitra-core.py` rebuilds upstream native support in an isolated
bootstrap directory. Its parser is used for bootstrapping generated upstream
support only. These artifacts are not an integrated replacement recognizer, and
successful source builds do not mean automatic native semantic hosting is complete.

The source-built native compiler now has an experimental selected-tree input and
typed source-preserving tree factories. See [native integration status](../native-nitra/README.md)
for the exact implemented boundary, reproducible builds, and the remaining native
semantic bootstrap failure. Automatic grammar/space native semantic hosting and
native mapping-to-Nemerle construction remain unfinished.
