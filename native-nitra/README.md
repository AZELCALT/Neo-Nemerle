# Native Nitra integration

Nitra is written as file modules, one module per (dll, namespace): `Nitra.Runtime/Nitra/Declarations.n` is the module `Nitra.Declarations`. The runtime's root types live in `Nitra.Runtime` (`Nitra.Runtime.Location`), macros under another dll's path carry the `Macros` suffix (`NitraMacros`, `Nitra.Serialization2Macros`), and `NITRA-SYMBOLS.json` lists every name that moved. Our integration code is part of those modules; nothing is patched or appended at build time.


`upstream/` contains unchanged source from Nitra commit
`b287b8a42237fac4d993444e7e3af9240b601503`. `NITRA-UPSTREAM.json` records
every copied file and its SHA-256; the original license is retained.
Only the runtime, DotNet support, grammar model and semantic compiler are copied.

The approved source boundary is native definitions inside `grammar` and custom
syntax use inside `space`. Native Nitra `syntax module` stays active. Custom
forms and semantic kinds inside a grammar remain recognized inactive records.
The old `runtime`/`compile` blocks are not part of the language (Nitra covers
them); `grammar (A, B)` is the handler of grammars used together in `space (A, B)`.
No grammar activation extends into ordinary Nemerle.

## What is connected

The source-host boundary and inactive records work in the existing experimental
compiler. All four native components build from the pinned source on .NET 10
using the source-built Boot2 bootstrap. The port fixes persisted generic method
overrides, assembly attributes, generic-array tuple constructors and redundant
`Enum`/`ValueType` constraints.

`RecognizedNemerleFile` (in `upstream/Nitra/Nitra.Compiler/Nitra/Compiler.n`) adds an experimental input entry point to
the native semantic project. It holds the selected native tree and its original
source, supports semantic cache resets, and refuses upstream reparsing.
`CompilingNitraProject.AddRecognizedFile` registers it before native typing starts.

The chemical-construction part of the parse-tree emitter (in `upstream/Nitra/Nitra.Compiler/Nitra/Compiler.n`) extends Nitra's tree generator with
typed `CreateRecognizedParseTree` factories. They accept the original source
provider, span and native fields, then construct Nitra's existing temporary tree
objects. They do not recognize input, invent a foreign executable AST, or use
reflection. The upstream sources stay unchanged: the build driver applies this
small generation patch to an isolated compiler build input and records its hash.

Native `map Nemerle.Compiler.Parsetree.PExpr` declarations now generate direct
Nemerle expression output. Existing code mappings and recursive rule mappings
use the native mapping checker and emitter. Mapping parameters, native pattern
matches and extension dispatch are covered by execution checks. Normal imports
and type aliases resolve through Nemerle's type environment; native AST symbols
retain priority. Output mappings do not implement
`GetAstUntyped` (PExpr is not a native IAst); missing or ambiguous syntax raises
an error instead of manufacturing an executable node. PExpr collection
conversions are not connected yet.

`tests/check-native-output.py` builds a native definition fixture, constructs
its selected typed fields without parsing, runs two recursive native mappings,
then compiles and executes their Nemerle output (`42`). The upstream parser is
used only to bootstrap that fixture's definitions. This test does not establish
automatic grammar/space hosting.

See [dials and shared scopes](DIALECT-SCOPES.md) for top-level spaces, the
compiler-session registry, programmable resolution, and the scope API.

## Automatic source hosting

No option is needed: a compilation whose sources contain a `grammar` or `space`
block indexes all sources once and compiles those blocks (`-experimental-nitra-source`
is still accepted and does nothing). The Integrated.* dlls must sit next to
`Nemerle.Compiler.dll`; without them the block gets one clear error.
The toolchain directory keeps its historical name `toolchain/nitra-native-core-experimental`. It supplies the native semantic compiler as an internal
component; hosts do not register mappings or construct native fields.

`RecognitionEmitter` (in `upstream/Nitra/Nitra.Compiler/Nitra/Compiler.n`) generates a recognition graph from the same
normalized native rules that define tree fields. Its typed `CreateSelected`
adapters construct spans, references, tuples, lists and optional fields directly
from settled structural evidence. Singleton sequences select their non-void
member, including the member's span. Reflection discovers generated entry-point
delegates; it does not infer fields or construct them reflectively.

`NativeSourceHost` (in `upstream/Nitra/Nitra.Compiler/Nitra/Compiler.n`) recognizes grammar definitions with that graph,
registers selected trees through `AddRecognizedFile`, and runs the existing
native symbol, typing, mapping and emission passes in a grammar-only compilation.
Automatic hosting obtains module names from the resulting native schemas; it
does not run the inspection recognizer before recognizing definition input.
`space` selects its configured grammar, constructs its native fields, invokes
the root's PExpr mapping (parameterless or taking `NitraDialectContext`) and returns the result to the normal
Nemerle backend. There is no required mapping name or host callback. Existing
callback-based configurations remain supported.

Native binding-power relations, left/right associativity and longest-call
selection are preserved explicitly. Selection checks reuse retained endpoint
evidence and materialize one settled tree; they do not scan source again or build
candidate ASTs. Native regex fields retain spans, and void calls have no semantic
fields. Both the grammar-only compilation and the source-host tests disable
external parsers. `RecognizedNemerleFile.ParseResult` and `ReParse` throw rather
than entering the old parser.

`tests/check-native-source.py` verifies automatic definition compilation,
recursive native mappings, SQL-like input, native precedence and both
associativities, typed optional/list/tuple fields, ordinary-code isolation,
failure recovery and two grammars in one file. Its source host supplies no
mapping callbacks.

## Remaining integration

Native shorthand conversions collecting mapped PExpr results into lists or
optional output values remain unimplemented. Parsing repetition and constructing
native list/optional input fields already work; ordinary Nemerle code mappings
can build output containers explicitly.

The native semantic component remains an internal DLL loaded by the experimental
source path, rather than being physically source-linked into Nemerle.Compiler.
Full native equivalence, external grammar-assembly activation, dynamic grammar
callbacks and declaration-valued spaces
remain outside the verified expression path. Definition diagnostics can still
refer to the synthetic namespace envelope, especially when multiple definitions
share one file. These artifacts do not establish complete Nitra compatibility.

The native selfbootstrap crash is fixed. CLR delegate conversion can put closure
initializers inside its target expression. Typer4 skipped that expression, so
captured ref/out arguments lost their address requirements in release builds.
Typer4 now visits the delegate target before boxing it. A focused regression
fails with the previous compiler and passes in both release and debug with the
fix. All four native components successfully rebuild using the rebuilt native
compiler. This clears a bootstrap prerequisite; it does not establish full
semantic equivalence or complete source integration.

## Reproduction

From the workspace root, set `COMPILER` to a modern source-built Nemerle toolchain
and `REFS` to the .NET 10 reference-assembly directory. First run:

```sh
python build/build-nitra-core.py --bootstrap "$COMPILER" --references "$REFS"
```

Use the printed Boot2 output directory as `BOOT2`:

```sh
python build/build-nitra-core.py --bootstrap "$COMPILER" --references "$REFS" \
  --snapshot Nitra --native-bootstrap "$BOOT2"
```

Use the second output directory as `NATIVE`:

```sh
python tests/check-nitra-core.py --toolchain "$COMPILER" \
  --references "$REFS" --native-core "$NATIVE"
python tests/check-nitra-structures.py --toolchain "$COMPILER" --references "$REFS"
python tests/check-captured-delegate.py --toolchain "$COMPILER" --references "$REFS"
python tests/check-native-output.py --toolchain "$COMPILER" \
  --references "$REFS" --native-core "$NATIVE"
python tests/check-native-source.py --toolchain "$COMPILER" \
  --references "$REFS" --native-core "$NATIVE"
python tests/check-native-source.py --toolchain "$COMPILER" \
  --references "$REFS" --native-core "$NATIVE" --checks NitraDialectChecks.cs
```

Bootstrap generation uses the upstream parser solely to rebuild native support.
It is not installed in the grammar/space execution path. Do not globally register
the native compiler as a replacement parser.

## Differential correctness and performance

The [comparison harness](../../tests/nitra-comparison/README.md) runs the native
and side recognizers against the same compiled grammars, forces typed fields,
checks actual mapped AST execution, and records isolated timing/allocation samples.
It retains failures and publishes ratios only for matching workloads. This bounded
corpus does not establish full Nitra equivalence.


The experimental package now includes the discovery-time shared-sample scheduler correction. See [comparison protocol and measured results](../../tests/nitra-comparison/README.md#discovery-scheduler-correction-2026-10-11) and the packaged `DISCOVERY-INTEGRATION-STATUS.json` for historical discovery-stage provenance. The subsequent structural-depth correction removes that guard; that checkpoint is recorded in `STRUCTURE-INTEGRATION-STATUS.json`. See the comparison documentation for passing standard cases, the embedded compiler stack distinction, and remaining selection/SCC costs. Original Nitra remains faster on the measured workloads.

The subsequent retained-selection and lazy incremental-component correction is installed in the experimental package. Current artifact provenance is `RETENTION-INTEGRATION-STATUS.json`; see the comparison documentation for the final paired measurements, scaling tests and remaining embedded-backend stack limitation.

The shared candidate-set correction supersedes that checkpoint. Current compiler
provenance is `RELATIONAL-INTEGRATION-STATUS.json`; architecture and verification
are documented in [NITRA-CANDIDATE-SETS.md](../grammar/NITRA-CANDIDATE-SETS.md).

The adaptive proportional-worker update is now installed; current compiler
provenance is `POOL-INTEGRATION-STATUS.json`. See the candidate-set architecture
and `baseline/coreclr-verification/nitra-pool-results.json` for final verification.

The flat recognition-node update is installed; current provenance is
`NODES-INTEGRATION-STATUS.json`. See `grammar/NITRA-NODES.md` and the aggregate
`baseline/coreclr-verification/nitra-nodes-results.json` for verification.

Worker-owned checks supersede Boolean-copy filtering; current provenance is
`WORKER-CHECKS-INTEGRATION-STATUS.json`, design `grammar/NITRA-WORKER-CHECKS.md`.
