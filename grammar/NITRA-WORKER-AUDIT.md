# Worker design mismatch audit — 2026-10-12

Read-only implementation audit after the worker-checks checkpoint. No compiler changes in this audit.

The checkpoint fixes predicate ownership for dispatched guard jobs. It does not implement the complete evidence-driven candidate-pool model described by the user.

1. Jobs receive the full source and a position, then run Possible/FirstGuard/Lexical. Lexical can walk sequences and repetitions ahead of the current position. There is no explicit advancing evidence record consumed by retained candidate continuations (NitraGuardEvaluation.n Test/Lexical).
2. Candidate sets are attached to family node/position frontiers. VisitFamily scans edge candidate membership, then scans node members again for multi-edge batches. CommitFamilyReady scans surviving memberships and node members again, and InternSet sorts IDs and creates a string signature even on hits. This is substantial coordinator preparation/reconstruction around each frontier, not only merging worker elimination results.
3. Relational reduction reuse covers literal-only multi-edge frontiers. The single-edge path exits before this cache. General guards reuse operation/absolute-position lexical results and range-private memos, not cached candidate-set transitions keyed by compatible evidence/context relations.
4. Evaluator memo lifetime is one worker range of one batch. NitraFilterJob.Run starts with a null evaluator for every job range. Threads are pooled, but evaluator state is not a retained logical worker across evidence updates.
5. Timestamp increments on probe/batch creation. Session/version checks prevent stale commits, but this is task ordering, not an explicit shared evidence-step schedule.
6. The default threshold is int.MaxValue: normal execution is inline. Small independent requirements across batches are not combined for dispatch; batching policy is local to each frontier. A singleton can run inline sensibly, but the present policy cannot establish the intended pooled scheduling model or its performance.

Observed performance: all six whole-operation medians regress 12–34% relative to the saved pre-correction compiler. Sample creation counts match; lists/SQL have fewer evaluation steps and zero full reduction batches but higher allocation. Chain/rejected alternatives create more reduction batches. These facts identify avoidable bookkeeping and the different work model; they are not exact CPU attribution or a demonstration that the user's design is slower.

Tests verify parser outputs and selected local ownership/publication properties. They do not verify equivalence to the complete evidence-driven architecture. Integrated guard benchmarks report zero PooledGuardChecks even in forced mode and must not be cited as pooled execution evidence; the direct ownership harness does prove actual pooled predicate execution.

A faithful correction should define an evidence-step record and retained pool/continuation identity, prepare static candidate membership once, apply deltas rather than reconstruct sets, reuse compatible relational transitions with explicit evidence dependencies, and distinguish pooled threads from retained logical worker state. Preserve pending/accepted/rejected distinctions: one surviving candidate is not sufficient to accept an unfinished input.

Implementation follow-up: `NITRA-EVIDENCE-POOLS.md` describes the replacement
path. This audit remains a record of the earlier worker-checks checkpoint;
verification and performance results for the replacement use `nitra-retained-*`.
