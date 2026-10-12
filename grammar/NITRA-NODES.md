# Experimental flat recognition nodes

Recognition uses session-owned tables of node headers, collection entries,
consumer links and typed continuation records. Tables grow in 1,024-record
segments after a small initial block (64 records for nodes/links and 256 for
collection arenas). Existing records are never copied during growth. Headers
store collection IDs rather than redundant arena handles. A NitraSample is a value handle containing its store and integer ID;
there is no allocated sample object and no subscriber delegate per transition.
Scalar node mutations address the stored header fields directly, avoiding whole-header
copies. Table, node and collection enumerators are value records; generic interface
iteration remains available for external projection.
Public recognition and mapping contracts are unchanged.

## Nodes and links

Canonical lookup remains prepared structural operation plus source position.
Production and capture provenance is retained separately, including the original
operation views projected for native mappings. Distinct source positions remain
distinct nodes: this is compact storage, not reuse of unvalidated source answers.

Node collections use shared arenas. New empty/small collections allocate no hash index;
sets above eight live entries promote to a dictionary mapping members to entry
IDs. Removal unlinks entries from the active list in constant time once indexed,
and scans at most eight live entries otherwise. Previously removed history is
not scanned on later removals. A promoted index may be retained as the collection
shrinks, and Clear releases it. Entry IDs remain stable for the session.

Each consumer link names a child and a complete typed continuation payload.
Identical child/continuation pairs are deduplicated; different owners, stages,
repeat counts, family contexts or capture edges remain distinct. Links track the
last delivered endpoint entry. Late subscribers replay existing endpoints once;
subsequent publication visits only newly appended entries. Endpoints are append
only. Delivery is queued before dependency closure notifications.

Explicit continuation kinds cover initialization, candidates, sequence and
repetition advancement, item/separator results, shared-family edges, dependency
closure and lookahead/subtraction notifications. Greedy/all-end repetition,
nullable/nonprogress diagnostics and trailing separators keep their prior rules.

Recursive components still use the existing iterative closure algorithm,
adapted to node IDs and arena-backed dependency collections. No component closes
while queued deliveries, reduction batches or transition proposals remain.
Structure selection and the optional diagnostic Regions projection are unchanged;
export materializes their existing endpoint-set contracts from node storage.

## Parallel frontiers

The same pure evaluator handles inline and pooled transitions. Inputs contain a
work record, immutable prepared operation, owner start and node version. Outputs
contain a continuation effect, target operation, next continuation and candidate
flags or a diagnostic. Discovery, lexical caches, node creation, links, endpoint
publication and compiler/mapping state remain coordinator-owned.

Pooled frontiers use the existing candidate-filter queue and process-wide
hardware limit. Workers own balanced ranges, publish readiness with release/acquire
ordering, and signal one shared session progress condition. There is one completion
object per parallel batch, not per node or range. A failed worker propagates through
batch completion; other queued work retains the pool's capacity.

The coordinator checks session/version/epoch before committing each effect.
Duplicate commits do nothing. Earlier work for the same owner precedes later
work, including candidate-filter reductions; ready independent owners may commit
while another range is pending. A shared progress condition prevents polling and
lost wakeups when both filter and node jobs are outstanding.

## Dispatch policy and measurements

`MinimumNodeWork` is an internal test/configuration field. Its default is
`int.MaxValue`: the offline calibration found no qualifying crossover through
65,536 transitions when comparing the allocation-free inline path with pooled
allocation, dispatch, completion and effect consumption. The pool is implemented
and forced-parallel correctness is tested; no unmeasured default speedup is claimed.
The candidate-filter threshold remains its separate 16,384-candidate policy.

The calibration uses three fresh sequential processes, seven samples of twenty
batches after five warmups, alternating mode order. It requires at least a 10%
parallel advantage at three consecutive doubling sizes. Both modes use the same
transition evaluator and checksum. `nitra-nodes-crossover-batch-only.json` preserves
an exploratory symmetric-allocation control; it does not describe production
inline execution and is superseded by `nitra-nodes-crossover.json`.

## Verification

`baseline/check-nitra-nodes.py --checks-only` exercises segmentation, promoted and
small collections, late subscribers, duplicate delivery, serial/parallel proposals,
concurrent recognition, stale/foreign effects and independent ready owners.
`--side-node-minimum 1` forces frontier dispatch in the paired comparison harness;
`--side-workers 1` forces inline execution. Internal overrides do not raise the
hardware cap. Native source mappings and the existing language corpus remain the
integration checks; original Nitra and the saved pre-change compiler are separate
performance references.

Observed median/p95/p99 use dedicated sequential workers and are not population
tail guarantees. Phase diagnostics, isolated transition calibration and full
forced-tree/mapping benchmarks measure different work and must be reported
separately. Whole-operation caller-thread allocation counters exclude allocations
on worker threads. No compiler plugin, new syntax or parallel lexical engine is
introduced by this change.

The paired throughput harness is `baseline/benchmark-nitra-node-throughput.py`;
it takes a completed `--comparison-report`, the saved `--previous-toolchain`
and an `--output` path. It runs all six workloads in three fresh processes per
engine, alternating engine order, with two warmups and five samples of three
operations. The latency harness takes those same arguments plus `--wide-report`.
Wide-family measurements use `benchmark-nitra-candidate-families.py` with
`--sizes 134 512 4096`. Run these timing jobs sequentially after builds and
correctness checks complete.

The worker-owned candidate-evaluation correction supersedes the candidate-filter
Boolean-copy workload and its threshold. See `NITRA-WORKER-CHECKS.md` for the
current evaluator, carried sets, partial commits and separate dispatch policy.
