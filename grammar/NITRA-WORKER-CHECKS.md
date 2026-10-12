# Experimental worker-owned candidate evaluation

This supersedes the Boolean-copy candidate filter described in earlier pool
checkpoints. The coordinator publishes immutable source, prepared structural
requirements, captured lexical evidence and an incoming candidate-set identity.
Initial family requests do not evaluate their leading guard before dispatch.
A guard job evaluates the requirements. The coordinator consumes the published
result, removes incompatible candidates and connects surviving shared edges.

## State and execution

Prepared families still share literal-prefix indexes and canonical operations.
Membership is grouped by next requirement before dispatch. One literal-index job
serves all active literal guards; identical general guards share a job. Jobs are
partitioned by covered active membership, within the existing process-wide
hardware cap. An indivisible shared requirement is not duplicated merely to fill
workers. Inline scheduling invokes the same job evaluator. Single-requirement frontiers
use a lightweight value result instead of allocating a reduction batch. New
nested family requests run that guard job before opening a recognition node;
the returned proof prevents another check when the node is requested.

Literal and established-evidence jobs avoid allocating a lexical evaluator.
Each worker range has a private lexical/first-character memo shared by jobs that
need uncached evaluation.
Each job publishes separate result dictionaries and scalar counters before its
release/acquire readiness flag. Those dictionaries are no longer modified after
publication, even while the range evaluates another job. Workers never mutate
recognition nodes, contexts, mappings or coordinator caches. Immutable prepared
ASCII dispatch tables are read under their publication lock.

The coordinator merges completed lexical spans and guard proofs. A subsequent
node request consumes the proof and cached spans instead of repeating the guard.
Incoming candidate sets are interned by family and sorted production identity.
A batch maintains a still-considered set: pending candidates remain present;
failed requirements remove members; successful edges carry their subset into
the next frontier. No candidate AST is constructed for this process.

Results are checked against session, evidence timestamp/version and incoming-set
identity. Published jobs can commit individually; duplicate commits do nothing.
Later evidence for the same owner respects earlier batches, while independent
owners can progress. Completion of the entire input still requires the requested
root span and established recursive/negative/longest-match constraints.

## Reuse and limits

A session-local 4096-entry LRU caches completed reductions. For literal-only
frontiers the lookup includes the incoming set, prepared node and an exact source
window bounded by the longest guard. Equivalent evidence can reuse the reduction
before checking predicates again; the relative literal spans are instantiated at
the new position. General guards reuse captured exact operation/position lexical
results and private range memos. No result is reused merely because it produced the same answer previously;
this is not an unbounded cache of semantic or recursive answers.

Workers evaluate leading structural/lexical requirements, not arbitrary user
macros or whole candidate ASTs. Unresolved nested/nonlexical structure is handled
by the existing linked recognition nodes. Structure selection and AST mapping
remain separate and are not optimized by this change. The detailed inspection
path still includes diagnostic regions; compact source compilation omits them.

## Dispatch and verification

The former 16384-member threshold measured Boolean copying and is superseded.
Actual guard calibration includes evaluation, scratch allocations, readiness and
result consumption, three fresh processes, two warmups and five samples of two
batches at 2..128 candidates. Three consecutive sizes must show at least 10%
parallel gain. With range-local memo reuse there is no qualifying crossover in
that tested range; the current default is int.MaxValue. Forced scheduling remains
available through existing internal harness overrides. Node-transition dispatch
has a separate policy and remains unchanged.

Tests cover real lexical checks in workers, hardware caps, range readiness,
failures, concurrent contexts, carried sets, partial commits, stale/duplicate
results and integration with native mappings. Current reports use the
`nitra-worker-checks` prefix; old node/pool reports remain historical evidence.
