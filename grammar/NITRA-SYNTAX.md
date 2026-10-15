# Native Nitra declarations and static recognition

This is a separate, explicitly opted-in side parser. It accepts the declaration
surface described by the pinned upstream Nitra grammar, and maps recognition
rules to compiler-owned shared operations. It does not add another scripting
language, execute Nitra's compiler, or change ordinary Nemerle compilation.

## Baseline and retained semantics

The baseline is Nitra commit `b287b8a42237fac4d993444e7e3af9240b601503`.
`NITRA-BASELINE.json` records source hashes; `NITRA-NOTICES.txt` preserves the
upstream BSD notice. `build/generate-nitra-bootstrap.py` embeds Core,
CStyleComments, NitraLiterals and NitraSyntax as declaration data. Upstream
assemblies are neither loaded nor distributed as dependencies.

The native self-describing grammar validates modules, namespace/import/alias
syntax, attributes, literals, markers, keyword regexes, nested rules, extensions,
precedence declarations, rule methods, languages/styles, AST/declaration/symbol
structures, maps, dependent properties and stages. Recognition definitions are
extracted into an explicit model. Semantic declarations and method bodies retain
their original source, spans, scope and declaration attachment. They are not
bound, type-checked, generated or executed. Successful syntax inspection therefore
does not assert that a mapping, property dependency or compiler callback works.

Runnable recognition inputs and native grammar examples are in
`grammar/examples/nitra-native/`. Supply the grammar text to the CLR host API
and select `Arithmetic.Start` or `Sql.Query`; neither performs runtime work.

The current coverage report is
`baseline/coreclr-verification/nitra-syntax-corpus.json` in the workspace. It lists
every pinned recognition production and each inspected source, including
unexercised interfaces. Matched-interface counts include provisional alternatives;
they are not exhaustive correctness proofs or evidence of unique AST selection.
In particular, upstream semantic negative tests can pass declaration parsing.

## CLI inspection

```
dotnet toolchain/nitra-syntax-prototype/ncc.exe \
  -nitra-syntax example.nitra -no-color
```

The command writes one declaration JSON object per source and emits no assembly
(`-experimental-nitra-syntax` is still accepted as an alias). It rejects in-memory
compilation. This inspection mode does not compile source blocks; an ordinary
compilation compiles every `grammar`/`space` block it finds, with no option;
see [NITRA-DIRECT-OUTPUT.md](NITRA-DIRECT-OUTPUT.md).
`[StartRule]` is not bound to a form.

## CLR host API

```csharp
var document = NitraSyntax.Read(grammarText, "example.nitra");
if (!document.Success || !document.SurfaceValidated)
    throw new Exception(document.ToJson());
var definitions = NitraSyntax.BaselineDefinitions().Append(document);
var prepared = NitraSyntax.Prepare(definitions, new[] { "Example" });
var result = prepared.Recognize("Example.Query", foreignText);
```

`Prepare` selects an explicit module set and its resolvable grammar imports. It
resolves nested names, namespace-relative imports and import aliases, applies
static extensions to its own prepared composition, and retains `[StartRule]`
metadata. It does not modify the input declaration models. The prepared object
can recognize multiple inputs, including concurrent inputs; recognition state is
per invocation. Callers should treat the returned metadata lists as read-only.

`ReadDefinitions` is the extraction/bootstrap API. Its `Success` means extraction
had no diagnostics; its `SurfaceValidated` remains false. Use `Read` for native
surface validation. The older overloads with a trailing `experimental` flag still
exist (obsolete, the flag is ignored). `BaselineDefinitions` returns fresh models, not the cached validator.

`Complete` means recognition reached a settled result without a deferred action
or resource/convergence diagnostic. `Accepted` additionally requires the explicit
rule to consume the entire input. Rejection can be complete. Dynamic syntax
extender/extension-point execution produces an explicit incomplete diagnostic;
the implementation does not silently treat a callback as an empty rule.

## Recognition model

Foreign input is raw UTF-16 source, independent of the Nemerle envelope tokenizer.
Static operations support literals, Unicode/inverted classes, regex subtraction,
recursion, bounded repetition, separated/trailing lists, predicates, captures,
precedence bindings and associativity, imports and extensions. Nitra's greedy syntax-list
behavior, regular-language regex composition, longest lexical matches and implicit/explicit spacing are applied.
Keyword followers are selected using the module's keyword regex declarations.

Preparation groups common sequence prefixes and collapses identity wrappers into
shared structural interfaces. Rule, production and capture identities remain
consumer views; lexical and precedence differences stay in the compiled children.
A per-input sample is keyed by interface and source start. Opening another
compatible consumer reuses that sample rather than creating a child AST.

Discovery filters incompatible requirements before activating dependent samples.
A prepared lexical opener guard checks full known openers, not just their first
character, and reuses that observation. Unknown requirements remain suspended.
Sequences retain slot/position continuations; repetitions retain their frontier,
count and separator state. Each new endpoint advances subscribed continuations;
established prefix traversal is not restarted. Lexical results remain memoized. Immutable ASCII character-dispatch tables are
shared by the prepared grammar with synchronized initialization and a 128-entry
bound. Non-ASCII dispatch stays local to each recognition run. Source-specific
samples and observations are never shared across input strings.
A mismatch does not discard an established shared body or its boundary evidence.
Real ambiguity remains available to the structural resolver.

Samples close through dependency-completion notifications. Negative lookahead,
subtraction, longest matches and greedy lists publish results only after their
dependencies settle. Stalled positive recursive components settle together;
cyclic negative/longest-match constraints remain explicit diagnostics. This is
not a universal linear-time claim or a complete implementation of future semantic
kinds, runtime facilities, or compiler plugins.

`NitraRegion.Sample` identifies views that share one sample. `Children` references
canonical region views of structural dependencies, not an unfolded AST. Regions
can include failed/provisional contexts and retained short/long tail endpoints.
`SampleCreations`, `SampleReuse`, `PrefixSamples`, `PrefixReuse`,
`FamilyEliminations`, `ContinuationAdvances`, `DuplicateTransitionsAvoided`, and
`PrefixReplays` expose discovery work. `DispatchBuilds` counts freshly built
character-dispatch tables, including per-input non-ASCII tables. `Evaluations` counts scheduled actions and
lexical matcher steps; it is not an instruction count or every preparation check.
The JSON inspection retains its existing fields and includes the principal
sample/continuation counters. Prefix-specific counters and shared sample IDs are
also available on the typed API. Native tree selection consumes retained evidence
through the existing operation/span interface, without recognizing the input again.

The earlier `StructuralProjection` API remains the explicit form/body/boundary
prototype. This native-rule graph supplies a broader recognition foundation; it
does not claim that the future semantic-kind subsystem or form adapter is finished.
The previous source-only grammar prototype is parked; see `grammar/obsolete/`.

## Deferred facilities

Automatic native semantic declaration/mapping generation, language services,
runtime/compile population and dynamic grammar callbacks remain deferred. The
direct-output bridge supplies host callbacks and explicit semantic services; it
does not execute retained native declaration bodies. Loading executable grammar
definitions from other assemblies and
long-lived IR integration are future work. Existing opaque block archives reserve
those attachment points but do not implement them. No new persistence keyword,
form-binding spelling or script/compiled interaction syntax is introduced here.

The recognizer has explicit limits (500,000 graph regions and five million
operation evaluations per recognition). Exhausting a limit returns a diagnostic,
not a successful partial result. These are prototype safeguards, not language
capability restrictions.

## Verification

```
python tests/check-nitra-syntax.py --toolchain toolchain/nitra-syntax-prototype \
  --references /usr/share/dotnet/packs/Microsoft.NETCore.App.Ref/10.0.12/ref/net10.0
python baseline/build-nitra-inspector.py --toolchain toolchain/nitra-syntax-prototype \
  --references /usr/share/dotnet/packs/Microsoft.NETCore.App.Ref/10.0.12/ref/net10.0
python baseline/check-nitra-corpus.py --inspector <printed-Inspect.dll> \
  --reference nitra-reference --output baseline/coreclr-verification/nitra-syntax-corpus.json
```

Host checks cover raw arithmetic and SQL syntax, keyword boundaries, spacing,
Unicode scalars, subtraction, predicates, greedy/bounded/separated lists, capture
spans, module aliases, static extensions, reuse, invalid declarations and deferred
dynamic behavior. Corpus checks include the self-grammar, Core, samples and bundled
grammars. Six explicitly listed historical/draft files use syntax outside the
pinned self-grammar; they are reported rather than silently accepted.

Discovery regressions and scaling assertions:

```sh
python3 baseline/check-nitra-discovery.py --toolchain /path/to/toolchain \
  --references /path/to/net10.0/refs
```

These checks exercise shared opener/body prefixes, capture views, retained tail
relationships, incomplete input, recursive closure, negative cycles and growing
lists. See `tests/nitra-comparison/README.md` for differential timing runs.


### Structural construction depth

Selected structure construction, feasibility dependencies, sequence suffix checks,
and capture discovery use explicit work stacks. There is no fixed 512-level
construction ceiling. Suspended construction resumes after each selected child,
so resolver callbacks retain depth-first source order. Feasibility keeps its
candidate cursor while dependencies complete, and native greedy calls cache their
longest feasible endpoint per operation/start position. Raw suffix reachability
filters impossible prefix spans before semantic feasibility or construction. This
filter does not select among viable alternatives. Selection still consumes
settled recognition evidence; it does not recognize source again. Active-span
cycle detection and the 500,000 structural-object budget remain enforced.

The structure checks cover 2,048 chained operands, 1,024 nested parentheses,
source spans, operand counts, resolver ordering, cyclic interpretations and
recovery. These are tested workloads, not a claim of unlimited depth throughout
native mapping or the rest of the compiler.


### Retained selection and recursive dependency progress

Selection retains search records for each sequence operation, child slot, source
position and required end. Raw suffix starts are derived by backward joins over
settled endpoint evidence. Candidate enumeration intersects those starts with the
child's endpoints, using the smaller input and preserving historical search order.
Endpoint membership and original views are prepared once per invocation; sorted
and rank indexes are allocated only when requested, with no extra indexes for
singleton endpoints.
Keys use typed operation/position tuples rather than allocated string encodings.

Feasibility may stop at its first successful connection, retaining both that
connection and the candidate cursor. Construction resumes the same record until
all viable alternatives are known, orders resolver options as before, and creates
only the selected structural nodes. Alternative-child searches likewise retain
successful child references. Resolver choices themselves are never cached.
Single-child wrappers follow their fixed child directly; empty repetitions use
their nullable result without allocating a search graph. Repetition retains
body/separator transitions, the reachability graph and reverse
viability results, preserving bounded counts and trailing separators. Searches
that encounter an active semantic cycle are conservatively invalidated before a
subsequent independent request, so provisional failures are not reused globally.

Recognition permits at most two ordinary SCC settlement passes before building
a retained component graph on a third stall, then maintains it as samples and
edges arrive. Inputs that close without a stall, or after at most two passes,
allocate no component index. This bounds initial whole-graph scans while avoiding
index setup on short-lived recursive inputs. Immutable lexical samples that close immediately do not allocate
components, and a target without outgoing dependencies needs no cycle search.
Forward source dependencies cannot form cycles; equal-position
edges use local reachability and merge affected components when necessary. Closure
removes completed components and updates their dependants. When positive work
stalls, settlement uses a snapshot of ready leaf components, then allows queued
notifications to run before settling newly ready parents. It does not recompute
SCCs across the entire open graph on every stall. A diagnostic full-SCC oracle
checks the incremental state between queued actions in regression tests.

All source-dependent caches are invocation-local. Existing source recognition,
ambiguity diagnostics, depth-first resolver order, cycle rejection and object
budgets remain unchanged. This is an experimental implementation improvement,
not a claim that arbitrary grammars have linear complexity.

### Timestamped candidate families (2026-10-11)

The current experimental recognizer uses prepared shared candidate families,
relational reduction reuse, timestamped proportional worker partitions and compact
compiler evidence. See [NITRA-CANDIDATE-SETS.md](NITRA-CANDIDATE-SETS.md) for the
architecture, context/cache validity, scheduling defaults and reproduction commands.
Earlier operation-by-position scheduling descriptions document previous versions.
Public diagnostic regions remain available; internal compilation avoids their
unconditional export. Ordinary Nemerle syntax and deferred custom facilities are
unchanged.
