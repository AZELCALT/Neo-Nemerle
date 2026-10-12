# Experimental shared candidate sets

The experimental Nitra recognizer now prepares shared structural families and
reduces their candidate membership using timestamped evidence. This replaces
per-production sequence activation for rule/alternative/sequence families. The
public declaration language, grammar/space scope, native typed-tree factories,
ambiguity resolver and Nemerle output contracts remain unchanged.

## Prepared structure and source-local facts

A prepared family contains stable candidate IDs and an index of shared next
requirements. The prefix index is grammar data, not a source nesting/history tree.
Equal requirements are represented once while production and capture identities
remain attached as provenance. A called structural interface opens a shared local
region; it is not recursively unfolded into every enclosing candidate.

At each source start, recognition uses that family and tracks established edges,
boundaries and pending requirements. A newly established edge is consumed once.
New provenance can propagate over already established edges without rereading the
source. Recursive dependencies use iterative completion and the retained component
settler; they are not unfolded into candidate ASTs. Uncertain negative/longest
constraints retain the existing closure requirements and cyclic diagnostics.

Literal-start conditions use a prepared character-prefix index. The coordinator
observes the prefix once and classifies matching requirements, rather than testing
every literal separately. Nonliteral conditions consult the existing lexical and
structural evidence. Unknown structural requirements stay eligible and pending.
Only proven incompatibility removes a member. A singleton does not bypass pending
requirements, end boundaries, or later semantic checks.

The existing endpoint-selection bridge receives compact operation/span evidence
projected from these shared connections. Native typed trees and mappings are
created afterward; no speculative candidate ASTs are used during recognition.
The selector still has its own retained endpoint/search machinery: this change
does not claim every downstream allocation or performance gap is eliminated.

## Logical timestamps and workers

The coordinator owns the logical evidence clock, source/context facts and commits.
Worker results do not advance that clock. A reduction batch names its session,
context, evidence timestamp, input-set version and prepared relation. Foreign or
stale results cannot commit, and duplicate completion cannot change pending counts.
Ready results commit in timestamp order within their owning context. Independent
contexts can continue while another batch is pending. The coordinator drains ready
batches first, and waits only when no independent evidence work can proceed; a
delayed earlier batch cannot block a ready batch belonging to another context.

For N candidates and hardware pool capacity P=max(1, processor count-1),
reductions below the offline-measured dispatch threshold execute inline. At or
above the threshold, choose W=min(N,P,configured maximum), then worker i owns
[floor(i*N/W), floor((i+1)*N/W)). An empty set schedules no work. Overrides never
increase the process-wide hardware cap. For example, 1,000 candidates and a
10-worker maximum produce ten ranges of 100 when parallel dispatch is enabled.

The default threshold is 16,384 for the current cheap membership lookup. The
recorded three-process calibration requires at least a 10% parallel advantage at
that size and the next two doubling sizes; smaller sets did not qualify. This is
an offline policy for this filter, not automatic runtime tuning or a prediction
for future expensive predicates. Internal overrides allow forced-parallel tests.

Workers apply immutable classified evidence and write only their assigned mask
range. Range jobs are value records, published under one queue lock per batch.
There are no per-range closures or completion tasks. One completion object and an
atomic remaining-job count coordinate a parallel batch, including worker errors;
inline batches need no completion object. The existing bounded CLR thread-pool
pumps drain the shared reusable queue across recognition sessions. No dedicated
idle OS threads are introduced. Workers never invoke macros, mappings, compiler
type resolution or mutable recognition methods. Identity reductions and cache
hits avoid dispatch entirely.

The parser continues available evidence work before waiting for unfinished jobs.
Dependency settlement cannot run while published notifications or reduction batches
are pending. This ordering is necessary: committing a completed worker can publish
new notifications even when the previous notification queue was empty.

## Relational cache and diagnostics

Completed reductions are cached per recognition session by prepared family/state
identity and an exact evidence-class signature. The literal-prefix class and
nonliteral condition outcomes identify the reduction. Grammar, lexical and
precedence distinctions are retained in prepared operation identities; source
positions and concrete endpoints are not reused through this cache. It has a
4,096-entry LRU bound. Active contexts and established facts are separate from
this eviction policy. Recursive histories are not cache keys.

This caches applicability of currently implemented structural constraints. It
does not implement deferred semantic-kind/type-system plugins or runtime/compile
blocks. Future mutable semantic inputs must participate in relation identity and
invalidation before their results can be reused.

Public Recognize and Structure retain detailed Regions for inspection. Internal
Nemerle compilation uses StructureCompact and avoids exporting that diagnostic
graph. Both consume the same established endpoint evidence. Internal counters
record family discovery, identity reductions, cache hits, tested/eliminated members,
worker partitions, prefix observations and the evidence timestamp.

## Verification

Run from the workspace root, substituting the installed reference directory:

```sh
python3 baseline/check-nitra-candidate-sets.py \
  --toolchain toolchain/nitra-native-core-experimental \
  --references /usr/share/dotnet/packs/Microsoft.NETCore.App.Ref/10.0.12/ref/net10.0
```

The checks cover balanced partitions including uneven/empty ranges, 134 competing
productions sharing one body, repeated and mixed evidence classes, concurrent
sessions, serial/parallel agreement, legacy differential recognition, foreign and
stale results, duplicate completion and compact evidence availability.

`baseline/check-nitra-comparison.py` accepts `--side-workers`, `--side-minimum` and
`--side-legacy`. Defaults exercise the new recognizer. Legacy mode is an explicit
internal differential control, never an automatic production fallback. Fixture
preparation verifies the selected compiler hash and snapshots harness sources.

Source-built and installed checks also cover declarations, captures, precedence,
ambiguity, recursion, grammar/space execution, dialect scopes and native mappings.
The standard corpus passes in default and forced-parallel modes. The expanded
corpus retains the shared embedded-backend stack limit on chain-2048; both engines
execute that case using the existing CLI-sized stack. Full Nitra equivalence and
performance parity are not established by these checks.

## Adaptive pool verification

`baseline/check-nitra-pool.py` checks the real dispatch path, hardware clamping,
empty masks, complete masks, concurrent batches, failure propagation and recovery.
Its optional offline benchmark compares actual Start/Wait calls at 128 through
65,536 candidates with identical mask allocation and reflective call overhead,
20 warmups, seven samples of 100 reductions, and three fresh sequential processes.
The benchmark reverses mode order in the middle process. The selected threshold
is recorded in `baseline/coreclr-verification/nitra-pool-crossover.json`.

The subsequent [flat-node recognition update](NITRA-NODES.md) replaces sample
objects and subscriber callbacks with segmented records and explicit links.
It shares the bounded worker queue while calibrating node dispatch separately.
