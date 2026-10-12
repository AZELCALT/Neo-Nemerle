# Experimental retained evidence pools

This replaces the default per-frontier lookahead guard batches audited in
`NITRA-WORKER-AUDIT.md`. Grammar syntax, selection and AST mapping are unchanged.

## Ownership and data flow

Prepared families assign dense production IDs and build immutable membership
masks for their edges, terminal sets and literal requirements. Prepared mask
storage becomes read-only after preparation. Each source session forks its own
mask interner and relational transition caches; concurrent sessions never mutate
one another's candidate state. Intersections, differences and unions reuse
numeric mask identities rather than sorting production IDs into string keys.

Prepared sequence prefixes with multiple consumers remain shared region
boundaries; they are not flattened into each caller. Unique local sequences
can still be flattened.

A family context retains its candidate pool and a lane for each activated shared
continuation. Literal lanes hold their trie cursor across successive character
observations. Large groups of independent general requirements have additional
retained lanes. These are logical states, not dedicated OS threads.

The coordinator publishes a value evidence record: source-session ID, context,
generation, evidence epoch, position and one character/end-of-input fact. Initial
general requirements also receive an immutable grammar first-character table.
A source-free inline start predicate screens new graph requests against the same
published fact before allocating a node. This is enabled only after grammar
preparation is complete; keyword-pattern preparation runs before those tables
are finalized. Source facts are retained by position within the session.
Workers have no source-string argument. A literal step advances one prepared
trie transition. A general step checks nullable/start compatibility and requests
shared structural dependencies; it does not recursively evaluate FirstGuard.

The existing recognition graph services those dependencies and establishes actual
endpoints, including token scanning. Token scanners still use the source and
existing exact lexical memo; they are shared recognition services, not candidate
worker lookahead. Endpoint facts travel once through the existing source-free typed work stream,
with an evidence epoch. Its worker resolves the prepared continuation and the
coordinator merges views and links. They are not duplicated as no-op lane jobs.
Closure facts return to retained lanes. A closed
dependency without endpoints eliminates its associated candidate mask. Pending
dependencies remain possible until established closure. Selection, recursive
settlement and negative/longest-match barriers remain authoritative.

Workers publish immutable effect snapshots. Only the coordinator changes live
pool masks and graph connections. A lane has one exclusive in-flight lease;
new facts queue behind it, and the lane resumes on the same retained state after
commit. Epochs are assigned when evidence is published. Duplicate applied facts
are ignored; foreign session/context/generation and mismatched current-epoch
results are rejected. Independent lanes may finish and commit separately.

## Reuse and dispatch

Character transitions are cached by prepared family/node/trie cursor, character
or EOF and requirement slice. Reuse substitutes the current evidence identity;
it does not reuse source endpoints. Character transition and mask relation caches
are session-local and bounded to 4096 entries per cache. Closure effects are
not cached as reusable semantic answers. Live interned masks remain available for
the session and are discarded with it.

Ready uncached lanes across contexts are dispatched together. The initial ratio
is 32 independent requirement checks per worker, bounded by ready lanes, the
configured maximum and the shared hardware cap. Ranges are balanced by the
number of requirements they cover. Shared literal trie traversal is indivisible
and is not duplicated to fill workers. Small/cached work runs inline through the identical evaluator and commit checks,
without allocating dispatch lists/arrays or staging an in-flight round trip.
Historical collections and deferred-fact queues are allocated only when used. Calibration
measures the new evidence checks, publication and consumption; the old guard-job
crossover is not applicable.

The historical `GuardBatchCompatibility` internal switch exists only for tests
of the old batching API. It is false by default. Historical harness results are
reported separately and do not establish evidence-model correctness.

## Verification

`check-nitra-evidence-pools.py` checks source-free evidence/lane records, retained
state, compatible transition reuse, dependency publication, real integrated
pooled execution, stale/duplicate facts, pending singleton input, recursion,
negative rules, concurrency and absence of old string-based set interning.
Existing discovery/component tests now pump evidence work before settlement.
Normal source/AST/execution and comparison fixtures use the new default.

Performance reports must name the compared compiler hashes. No speedup or
latency advantage is implied by these ownership and correctness properties.
