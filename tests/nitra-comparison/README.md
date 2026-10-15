# Native Nitra / side recognizer comparison

Run from the workspace root:

```sh
python3 tests/check-nitra-comparison.py \
  --toolchain toolchain/nitra-native-core-experimental \
  --references /usr/share/dotnet/packs/Microsoft.NETCore.App.Ref/10.0.12/ref/net10.0
```

Use the reference directory installed on your machine. `--native-core DIR` supplies
native assemblies separately when the toolchain does not contain them.
`--profile smoke` runs a smaller corpus; `--profile stress` increases chains/lists
to 2,048 elements and nesting to 1,024. Stress is intended to expose limits:
stack overflow, timeout and verifier errors count as failures. The current snapshot
traversal uses an explicit stack; historical reports used a depth guard. Default
standard sizes reach 128 elements and 64 nesting levels. `--seed`, `--repeats`
and `--timeout` are recorded in the report. Default timeout is 30 seconds per
worker, with three fresh processes per engine per benchmark workload.

The report is `baseline/coreclr-verification/nitra-comparison.json`. Raw inputs,
stdout, stderr, build logs and compiled artifacts remain in the temporary
`work` directory named there. `--prepare-only` builds without running;
`--reuse DIR` requires matching harness source hashes. `--no-benchmarks` completes
all correctness, recovery, comparator and backend execution checks without
launching repeated timing workers. Use it for a broad boundary audit, then run
matched timing repeats on selected workloads.

## Correctness protocol

The original native parser compiles one fixture assembly. Both engines consume
that exact assembly: its native parser descriptors on one path, its generated
recognition graphs and selected-tree factories on the other. Both use native
typed temporary trees and native Nemerle mappings. The native parser is a baseline
from the integrated upstream port, not an independently validated original
historical Nitra binary. Thus agreement cannot prove absence of shared bugs.

The corpus covers precedence, left/right associativity, nesting, whitespace,
optional/tuple/list fields, separators, SQL-shaped statements, lookahead, regex
subtraction, overlapping alternatives, ambiguity and grammar declarations.
Seeded arithmetic generation adds valid expressions and invalid mutations.
Explicit expected acceptance and simple mapping checks supplement differential
agreement. Every accepted input is followed by an invalid input and the original
input again to detect leaked parser state.

Comparison forces and snapshots typed fields, source spans and list/optional/tuple
contents. Generated implementation class identities are excluded. Mappings are
also compared. Actual mapped PExpr objects are injected through the test-only
Replay macro into a fresh normal compiler and executed against independent
arithmetic/count oracles. Printed expressions are not reparsed: the pretty-printer
can omit grouping. This execution check is outside timed samples.

A native/native repeat checks baseline stability. Deliberately corrupted status,
tree digest, mapping and consumed boundary must all be caught by the comparator.
Recovered native input is never treated as successful parsing: a fail-fast
callback disables recovery. Exceptions, crashes, nondeterminism and timeouts
remain failures. Ambiguous input must remain ambiguous without arbitrary lowering.

## Timing protocol and limits

Workers run sequentially, in randomized paired order, under the same runtime,
GC and tiering settings. Compiler type-context initialization, grammar preparation
and cold parsing are reported separately. Warm results have two warmups and five
samples of three operations each, repeated across fresh processes. Per-process
medians and their min/max are retained. All correctness checks run before timing;
failed workloads receive no speed ratio.

The main measured operation includes source snapshot creation, recognition,
root construction, forced field materialization/canonical serialization, and
mapping/pretty-printing. Native root-only timing is not comparable to side eager
tree construction. Snapshot instrumentation adds overhead to both paths, so these
numbers measure the complete instrumented operation, not a pure parser kernel.
Allocation counts cover the executing thread. Peak working set covers the whole
worker, including runtime, setup and JIT; it is not parser-only memory usage.
Ratios are side/native, with smaller values better. There is no aggregate speedup
claim. Machine/environment and artifact/source hashes are recorded for replication.

This is a bounded regression/scaling corpus, not proof of full Nitra equivalence.
It does not measure IDE recovery, incremental editing, all upstream grammars,
all mapping/property constructs, dialect registry APIs or arbitrary user macros.
Run existing integration checks alongside it. Repeat on an otherwise idle machine
before treating small timing differences as significant.

## Recorded run

The standard report records 71/72 passing cases and 75 executed mapped outputs.
The side path rejects the valid 128-term addition chain at its structural
materialization depth limit (512); native Nitra accepts it. That workload has no
speed ratio. Comparator corruption controls and the native repeat control pass.

Among passing workloads, the instrumented side path is slower and allocates more.
Examples from this machine's three-process run:

| Workload | Native median ms | Side median ms | Side/native time |
| --- | ---: | ---: | ---: |
| 32-term addition | 0.156 | 3.465 | 22.2 |
| 128-element list | 0.506 | 32.401 | 64.0 |
| Invalid 128-term near miss | 0.024 | 22.251 | 912.4 |

Read exact values and all samples from the JSON report; these are measurements
of the current implementation and protocol, not architectural lower bounds.
The failing command intentionally exits nonzero.

To reproduce the additional boundary run without repeating smaller cases:

```sh
python3 tests/check-nitra-comparison.py \
  --toolchain toolchain/nitra-native-core-experimental \
  --references /usr/share/dotnet/packs/Microsoft.NETCore.App.Ref/10.0.12/ref/net10.0 \
  --profile stress --repeats 1 \
  --case-pattern '^(chain|list|sql|near-miss)-(512|2048)$|^nesting-(256|1024)$' \
  --output baseline/coreclr-verification/nitra-comparison-stress.json
```

This selects ten explicitly named boundary workloads. Its single-process timing
repeats are exploratory; the standard run's three-process repeats carry more
weight. `--case-pattern` is also useful for rerunning a failure. Selection is
recorded, and selecting no cases is an error.

The completed boundary report has 5/10 correctness cases passing. Side structural
materialization rejects chains of 512/2,048 terms and nesting of 256/1,024 levels.
The 2,048-column SQL correctness worker times out. The native 2,048-term chain
hits the **harness snapshot guard**, so its native parser limit is not established
by this case. These are separate failure causes, preserved in raw output.

Three boundary workloads complete repeated benchmarks. The side 2,048-element
list and invalid near-miss workers exceed the 30-second **whole-worker** benchmark
timeout even though their correctness checks pass. This is an endurance budget
failure, not evidence that one parse alone takes 30 seconds. No timing ratios are
published for these incomplete benchmarks. Both commands exit nonzero because
the reports contain failures; failures have not been converted into skips or passes.

## Running to completion and CLR fairness

`native` in these reports means the original Nitra parser machinery. **Both
engines are managed .NET code**, launched with the same `dotnet` host. The recorded
runtime for both is .NET 10.0.12 x64. This is not a native C versus CLR comparison.
Framework, grammar assemblies, GC settings and JIT settings are shared. Warmups,
paired randomized order and fresh-process repetitions reduce startup/JIT and
machine noise; they do not eliminate all noise. Cold/setup values are separate
from warm sample medians. Larger allocation/GC costs within the operation are
part of that implementation's measured cost, not removed from one competitor.

Use `--timeout 0` to wait for each worker to finish, without a time limit. The
30-second reports retain their original budget failures; the additional report
is separate so completion can be distinguished from exceeding a budget:

```sh
python3 tests/check-nitra-comparison.py \
  --toolchain toolchain/nitra-native-core-experimental \
  --references /usr/share/dotnet/packs/Microsoft.NETCore.App.Ref/10.0.12/ref/net10.0 \
  --profile stress --timeout 0 --repeats 3 \
  --case-pattern '^(list|sql|near-miss)-2048$' \
  --output baseline/coreclr-verification/nitra-comparison-unbounded.json
```

The JSON records a null timeout for this mode. These selected workloads previously
hit a correctness or repeated-work benchmark timeout. Removing the timeout does
not change compiler depth guards. No compiler implementation is patched by the
comparison harness.

The no-timeout run **completed successfully**: all three correctness cases and
all three benchmark workloads pass, with no failure records and three fresh
process repeats each. The 2,048-column SQL correctness worker takes about 32.8
seconds in total. Warm full-operation medians are:

| 2,048-element workload | Original Nitra (CLR), ms | Side (CLR), ms |
| --- | ---: | ---: |
| List | 9.393 | 6,236.564 |
| SQL columns | 6.736 | 7,735.341 |
| Invalid addition near miss | 0.534 | 3,874.291 |

The earlier timeout findings are budget failures, not evidence these inputs
cannot finish. The depth-limit findings are independent and remain unchanged.

For a separate diagnostic splitting recognition from structural selection:

```sh
python3 baseline/check-nitra-phases.py \
  --comparison-report baseline/coreclr-verification/nitra-comparison-unbounded.json \
  --output baseline/coreclr-verification/nitra-comparison-phases.json
```

Run this after the comparison finishes. It invokes the same internal recognition
and structure-builder calls used by `NitraSyntax.Structure`, through reflection,
with three sequential iterations per input. It records phase time, allocations,
recognition counters and selected-node count. This is an implementation diagnostic,
not a second competitive benchmark; its first iteration is cold. It also has no
worker timeout. The completed comparison's temporary artifacts must still exist.

The completed phase diagnostic locates the main cost in recognition, not selected
tree construction. Median phase times (including the cold iteration among three):

| Workload | Recognition ms | Structural selection ms |
| --- | ---: | ---: |
| List 2,048 | 6,060.686 | 93.250 |
| SQL 2,048 | 7,527.640 | 111.833 |
| Invalid near miss 2,048 | 4,312.150 | 0.394 |

The list records 4,296,736 internal evaluations for 4,097 source observations;
SQL records 4,323,487 evaluations for 4,101 observations. These counters identify
substantial recognizer work; they do not alone establish which internal loop or
allocation site to optimize. The rejection case produces zero selected nodes.


### Discovery scheduler correction (2026-10-11)

The recognizer now filters incompatible families before activation, shares canonical structural samples and prepared sequence prefixes, and advances retained sequence/repetition continuations instead of replaying prefixes. Production and capture identity remain separate views of shared evidence. Completion notifications and SCC settlement handle dependency closure. The scheduler uses serial queued work; it does not spawn OS threads. Prepared grammars cache bounded immutable ASCII dispatch tables; source evidence remains local to each invocation.

The rebuilt experimental package is `toolchain/nitra-native-core-experimental`; `DISCOVERY-INTEGRATION-STATUS.json` records artifact hashes and provenance. The compiler completed a two-stage selfbuild and the integrated native components rebuilt successfully. Regression checks passed: discovery 41, syntax 175, structures 47, native core 77, automatic source 39, dialect scopes 179, plus executable mapping/output checks.

Final standard comparison: **71/72**, with the unchanged chain-128 structural-materialization depth guard (512) as the only failure. All three selected 2,048-element cases completed without timeouts and matched original Nitra. Both engines ran on .NET 10.0.12; “native” in reports means original Nitra machinery, not native machine code. Sequential paired timing used three processes per engine.

| Workload | Previous side recognizer, ms | Corrected side, ms | Original Nitra, ms |
| --- | ---: | ---: | ---: |
| list-2048 | 6236.564 | 254.053 | 9.053 |
| sql-2048 | 7735.341 | 279.639 | 6.382 |
| near-miss-2048 | 3874.291 | 173.445 | 0.452 |

These are full-operation warm medians from separate before/after runs on this machine, not universal speed guarantees. Original Nitra remains faster. Phase diagnostics show list recognition at roughly 119 ms (three-iteration median including one cold iteration), with selection at 118 ms; SQL recognition at 137 ms and selection at 116 ms. Evaluation counts fell from 4,296,736 to 69,671 for the list and from 4,323,487 to 77,947 for SQL. Counters measure scheduled actions and lexical matching steps, not every instruction or preparation operation. Dedicated size-doubling tests verify bounded continuation growth and zero prefix replays for their list grammar; this does not prove linear complexity for every grammar.

Reports: `baseline/coreclr-verification/nitra-comparison-discovery.json`, `nitra-comparison-discovery-unbounded.json`, and `nitra-comparison-discovery-phases.json`. Earlier reports remain unchanged. Full Nitra equivalence and removal of the structural depth guard remain unfinished.


### Structure traversal and slow-case diagnostics

The structure builder now uses explicit construction and feasibility work stacks.
It preserves depth-first resolver order, capture boundaries and cyclic-structure
diagnostics while removing the old 512-level construction ceiling. Feasibility
retains candidate cursors across dependencies, returns cached answers before
allocating work, and caches native greedy endpoints. The comparison snapshotter
also uses an explicit traversal stack, equally for both engines; older reports
used a 2,048-level snapshot guard. Consequently current timing numbers should
be compared between engines within the same report. Earlier timings used a
different snapshot implementation.

For detailed diagnostics after a completed comparison:

```sh
python3 baseline/check-nitra-phases.py \
  --comparison-report baseline/coreclr-verification/nitra-comparison-structure.json \
  --case-pattern '^(chain|nesting)-' \
  --output /tmp/nitra-structure-phases.json
```

Add `--settlement-probe` to count recursive dependency-settlement passes and the
cumulative live samples seen by those passes. This reflective diagnostic executes
the same serial scheduler operations and records settlement time separately;
its total recognition timing includes instrumentation overhead. It is not a
comparative benchmark. Uninstrumented diagnostics also record feasibility cache
entries and greedy endpoint counts. Never run diagnostic probes concurrently
with comparative timing workers.


## Structural depth correction and remaining costs (2026-10-11)

Structural construction and capture traversal now use explicit work stacks. The old 512-depth materialization guard is removed; cycle detection and the 500,000-object budget remain. Resumable feasibility checks, cached greedy endpoints and raw suffix filtering avoid repeated work while preserving resolver order and ambiguity behavior. Compiler completed a two-stage selfbuild; regression checks passed 63 structure assertions, 118 source integration assertions and 41 discovery assertions.

All 72 original standard comparison cases now pass end to end. The expanded corpus passes 81/82 on the ordinary embedded compiler thread. Both engines recognize, materialize and map the remaining `chain-2048` case identically, then overflow the recursive Nemerle type checker on that thread. The unmodified CLI already uses a 160 MiB compiler stack on this 64-bit CLR: ordinary Nemerle sums of 512 and 2,048 terms compile and execute there, yielding 3584 and 14336. This is a host stack distinction, not a parsing rejection or an iterative-backend fix. The separate compiler-stack control records the same custom-syntax case for both engines; the default-host failure remains in the original report.

Selected warm full-operation medians (side / original Nitra, milliseconds): chain-128 42.218 / 0.794; list-2048 297.718 / 11.199; SQL-2048 323.767 / 6.546; near-miss-2048 172.168 / 0.487; nesting-256 246.278 / 1.025. Both engines run on .NET 10.0.12, with sequential paired workers and no timeouts. These results do not establish full Nitra equivalence or a general speed advantage.

Two substantial costs remain. At chain-2048, phase diagnostics measure recognition at 158 ms and structure selection at 11,397 ms: endpoint searches in feasibility/sequence selection remain expensive despite roughly linear cache-entry growth. At nesting-1024, recognition takes 3,744 ms versus selection 89 ms. Instrumentation finds 2,050 SCC settlement passes and 15,766,550 cumulative live-sample visits: repeatedly scanning the open dependency graph dominates this case. Instrumented timings include probe overhead; phase medians include one cold iteration and must not be compared directly with warm benchmark medians. Neither remaining bottleneck is claimed fixed.

Final reports: `baseline/coreclr-verification/nitra-comparison-structure.json`, `nitra-comparison-structure-performance.json`, `nitra-comparison-structure-phases.json`, `nitra-comparison-structure-settlement.json`, `nitra-backend-depth.json`, and `nitra-comparison-structure-compiler-stack.json`. These supersede earlier claims that chain-128 still hits a structural depth guard. The experimental package's current provenance is `STRUCTURE-INTEGRATION-STATUS.json`.


## Retained selection and dependency components (2026-10-11)

Selection now shares endpoint views, backward suffix joins, resumable sequence connections, alternative-child results and repetition transition/viability graphs between feasibility and construction. Existence checks retain a witness and cursor; construction completes the alternatives before invoking the resolver. Single-child wrappers and empty repetitions avoid generic search records. Sorted and rank indexes are lazy. Source-dependent caches remain local, and provisional semantic-cycle results are invalidated before a later independent request.

Recognition allocates no component graph for inputs that close without a recursive stall. It permits at most two unindexed settlement passes; a third stall builds SCCs once and promotes to a retained component graph, updated as dependencies arrive or close. Short-lived stalls avoid index setup. Leaf settlement snapshots prevent parent closure before queued notifications run. Regression tests compare the incremental graph against a full SCC oracle, including forced early initialization to exercise insertion and merging.

The two-stage source build passed. Checks passed: 108 structure/selection, 118 source integration, 89 discovery/component, 175 declaration/recognition, 39 automatic native source and 179 dialect assertions, plus mapped Nemerle execution of 42. Installed package checks passed 108 structure, 118 source, 89 discovery and 39 automatic-source assertions, and its artifact hashes match the verified builds. Native support assemblies are unchanged; compiler provenance is in `RETENTION-INTEGRATION-STATUS.json`.

All 72 original standard cases pass. Expanded default-host comparison is 81/82: both engines parse and map chain-2048 identically, then overflow the existing recursive backend on the ordinary embedded thread. Both execute 14336 under the existing CLI-equivalent 160 MiB stack control. This is not a backend-stack fix. Both report ambiguity where expected; equality of unresolved ambiguous forests is not claimed.

Warm full-operation medians use the same .NET 10.0.12 host, unchanged worker/grammar sources, sequential paired workers, three processes per engine, two warmups and five samples of three iterations. No worker timeouts. Previous-side results were rerun in this session with the same protocol; original Nitra is measured alongside each version. Smaller is better.

| Workload | Previous side, ms | Revised side, ms | Original Nitra, ms | Previous / revised allocations, MB |
| --- | ---: | ---: | ---: | ---: |
| chain-128 | 44.565 | 9.535 | 0.802 | 44.44 / 12.09 |
| list-2048 | 297.511 | 265.662 | 11.304 | 228.80 / 160.74 |
| sql-2048 | 321.084 | 314.239 | 6.534 | 256.13 / 183.30 |
| near-miss-2048 | 166.769 | 167.334 | 0.468 | 101.51 / 101.81 |
| nesting-64 | 18.763 | 6.613 | 0.239 | 23.24 / 8.54 |
| nesting-256 | 231.410 | 54.836 | 0.936 | 259.04 / 33.27 |

Six paired baseline workloads and ten additional scaling workloads pass full correctness and execution checks. Original Nitra remains faster on these measured workloads. Timing results are specific to this machine and corpus, not a proof of general complexity or full Nitra equivalence.

Phase diagnostics put chain-2048 selection at **104.622 ms**, versus **11397.174 ms** at the previous checkpoint. Nesting-1024 recognition measures **195.138 ms**, versus **3744.106 ms**. These three-iteration phase medians include a cold iteration and are distinct from the warm table above. Nesting retains 2050 settlement passes, but performs only 1 initial component build and updates retained components thereafter; it performs at most two initial unindexed passes rather than recomputing SCCs across all open samples each pass.

Reports: [aggregate results](../coreclr-verification/nitra-retention-results.json), [previous baseline](../coreclr-verification/nitra-comparison-retention-before.json), [revised paired timings](../coreclr-verification/nitra-comparison-retention-performance.json), [scaling timings](../coreclr-verification/nitra-comparison-retention-scaling.json), [expanded corpus](../coreclr-verification/nitra-comparison-retention.json), [phase diagnostics](../coreclr-verification/nitra-comparison-retention-phases.json), and [compiler stack control](../coreclr-verification/nitra-comparison-retention-compiler-stack.json). The `retention-first`, `retention-second` and `retention-third` reports retain intermediate measurements that exposed bookkeeping regressions; they are superseded by these final results.

## Performance attribution audit (2026-10-11)

[Performance investigation](PERFORMANCE-AUDIT.md) documents the timed-path audit,
fresh-parse verification, phase allocations, scheduler/region census and concrete
optimization targets. New diagnostics reproduce the large gap without changing
production compiler behavior. Original Nitra generates specialized parser methods
and uses integer-array records; the side implementation pays for generic sample
scheduling, detailed region export and separate structural selection. Final
normalization is small on the measured cases. Reports: `nitra-performance-audit.json`
and `nitra-scheduler-audit.json` in `baseline/coreclr-verification`.

## Timestamped candidate-family correction (2026-10-11)

The current implementation groups candidate requirements before source activation,
uses a shared literal-start index, retains relational reductions, and partitions
nontrivial filtering proportionally to set size and available workers. Details:
[architecture](../../nemerle/grammar/NITRA-CANDIDATE-SETS.md).

`--side-workers N` and `--side-minimum N` configure internal test scheduling;
`--side-legacy` explicitly exercises the former scheduler. Defaults use the new
recognizer. No automatic fallback is permitted. Comparison preparation now gives
the selected toolchain priority over support files, verifies its compiler hash,
and snapshots harness sources. An early smoke report from this implementation
session used an accidentally overlaid previous compiler and is superseded by the
final reports with verified compiler hashes.

Final correctness reports: `nitra-comparison-relational-final.json` (expanded
corpus), `nitra-comparison-relational-parallel.json` (forced-parallel standard
corpus), and `nitra-comparison-relational-compiler-stack.json` (explicit stack
control). All report files are in `baseline/coreclr-verification`.

## Final shared candidate-set checkpoint

The rebuilt compiler is installed in `toolchain/nitra-native-core-experimental`;
current provenance is `RELATIONAL-INTEGRATION-STATUS.json`. All 312 candidate-set
checks pass, including independent-ready scheduling. Standard corpus: 72/72 in
forced-parallel mode. Expanded corpus: 81/82; both engines hit the shared backend
stack limit on chain-2048 and both execute it with the existing CLI-sized stack.

Sequential paired measurements, milliseconds, three fresh processes per engine:

| Case | Previous recognizer | Shared sets | Original Nitra |
|---|---:|---:|---:|
| chain-128 | 10.129 | 10.693 | 0.821 |
| list-2048 | 269.051 | 257.099 | 11.564 |
| sql-2048 | 320.694 | 321.579 | 6.964 |
| near-miss-2048 | 173.916 | 177.009 | 0.523 |
| nesting-64 | 7.050 | 5.242 | 0.244 |
| nesting-256 | 55.103 | 37.050 | 1.047 |

These are full forced-tree/mapping timings, with the same managed runtime and
compiled grammar. Original Nitra remains faster. Wide-family results separately
measure parsing and full typed-tree forcing without mappings/backend execution;
parallel dispatch costs more than serial filtering for those lightweight masks.
See `baseline/coreclr-verification/nitra-relational-results.json` for report links
and `nemerle/grammar/NITRA-CANDIDATE-SETS.md` for architecture and limits.

## Adaptive proportional pool checkpoint

Current installed provenance is `POOL-INTEGRATION-STATUS.json`; the previous
relational checkpoint is historical. The reusable bounded queue now holds range
records, with one completion object per parallel batch and none for inline work.
The pool keeps the hardware cap; parallel batches use min(candidate count, cap,
configured maximum) balanced ranges. Candidate count never expands that cap.

Offline dispatch calibration selected 16,384 candidates for the current cheap
membership filter. At that size and the following two doubling sizes parallel
execution was at least 10% faster. Smaller reductions stay inline. This is a
hardware-specific offline default; forced-parallel overrides remain available.
Three fresh processes measure actual Start/Wait calls independently of parsing.

All targeted checks pass, including 312 candidate-set checks and pool cap, mask,
completion, concurrency and failure/recovery checks. Forced-parallel corpus72/72;
expanded adaptive corpus81/82 retains the shared backend stack limit; both engines
execute chain-2048 with the existing CLI-sized stack. Wide-family tests compare
original Nitra, pre-pool compiler, new inline, forced-parallel and adaptive modes
at 134, 512 and 4096 candidates, with identical typed-tree hashes.

Final reports: `baseline/coreclr-verification/nitra-pool-results.json`,
`nitra-pool-crossover.json`, `nitra-pool-family-performance.json` and
`nitra-comparison-pool-performance.json`. Whole-operation timings and isolated
dispatch timings must not be presented as interchangeable. Original Nitra remains
faster; these tests do not prove complete Nitra equivalence.

## Flat recognition-node checkpoint

The installed experimental compiler now uses segmented node headers, arena-backed
collections, explicit consumer links and typed continuations. Node/link blocks
start at 64 records, arena blocks at 256, then grow through 1024-record segments
without copying records. Compact headers keep collection IDs, scalar updates address stored fields directly, and value enumerators avoid iterator objects. The pre-fix reports
preserve a measured short-input regression caused by oversized initial blocks.

All 94 new node checks and existing targeted checks pass. Forced-parallel corpus
72/72; expanded adaptive81/82 retains the shared backend stack limit; both engines
execute chain-2048 with the existing CLI-sized stack. Worker counters prove real
multi-range node dispatch in forced mode. Production node transitions remain
inline because fair calibration, including pooled allocation and consumption,
found no qualifying crossover through 65536 transitions. Candidate filtering keeps
its separate 16384 threshold. Symmetric-allocation calibration is exploratory only.

Warm whole-operation medians (ms), caller-thread allocation (decimal MB), from fresh sequential paired runs of the saved compiler, original Nitra and installed compiler using the same compiled grammar:

| Case | Previous | Flat nodes | Previous MB | Flat MB |
|---|---:|---:|---:|---:|
| chain-128 | 10.718 | 9.966 | 12.28 | 10.21 |
| list-2048 | 251.859 | 221.162 | 162.78 | 136.04 |
| sql-2048 | 320.564 | 286.311 | 193.83 | 162.56 |
| near-miss-2048 | 167.421 | 133.435 | 102.66 | 69.74 |
| nesting-64 | 5.289 | 5.080 | 6.80 | 5.50 |
| nesting-256 | 37.570 | 30.576 | 26.70 | 21.35 |

Structure selection is unchanged. Phase diagnostics include a cold iteration and
are distinct from these warm comparisons. Dedicated sequential latency runs use
three fresh processes and 100 one-operation samples each, reporting observed
median/p95/p99 rather than population guarantees. Wide-family tests compare the
saved compiler, original Nitra, new inline, forced-parallel and adaptive modes at
134/512/4096 alternatives with equal typed trees. No speed or stability advantage
over original Nitra is claimed.

Current provenance: `NODES-INTEGRATION-STATUS.json`. Architecture:
`nemerle/grammar/NITRA-NODES.md`. Aggregate verification and report links:
`baseline/coreclr-verification/nitra-nodes-results.json`.

## Worker-owned candidate checks

The coordinator now publishes source evidence and incoming candidate sets. Jobs
evaluate actual literal/lexical requirements and return immutable results; the
coordinator reduces the still-considered set and carries survivors forward. Jobs
within a range share a private lexical memo but publish separate snapshots.
Independent completed jobs commit without waiting for the entire reduction.
Cached spans and guard proofs prevent immediate node-request reevaluation.

The earlier Boolean-copy threshold is superseded. Actual-guard calibration after
private memo reuse found no qualifying crossover through 128 candidates; default
dispatch is inline, forced-pool execution is tested with real predicates.
14 ownership checks, existing targeted checks, forced 72/72 and expanded 81/82 pass
with the known shared backend stack failure; larger-stack control passes.
Separate structure selection is unchanged.

Fresh sequential paired warm medians, milliseconds per operation:

| Workload | Saved compiler | Corrected | Original Nitra |
|---|---:|---:|---:|
| chain-128 | 10.330 | 11.894 | 0.812 |
| list-2048 | 232.574 | 277.114 | 12.019 |
| sql-2048 | 293.151 | 327.028 | 7.705 |
| near-miss-2048 | 137.953 | 184.154 | 0.524 |
| nesting-64 | 5.380 | 6.996 | 0.238 |
| nesting-256 | 29.287 | 36.750 | 1.021 |

Wide alternatives, actual lexical-guard families, allocation counts and observed
latency are reported separately in `nitra-worker-checks-results.json`. Whole-operation
comparisons use the detailed inspection path; compact source compilation omits
diagnostic regions. No universal speed/stability advantage is claimed. Current
provenance: `WORKER-CHECKS-INTEGRATION-STATUS.json`; design: `NITRA-WORKER-CHECKS.md`.
