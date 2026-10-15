# Nitra performance investigation — 2026-10-11

This investigates the current retained-selection compiler, without changing production compiler behavior. Both paths run managed code on the same .NET 10 host, with tiering and server GC disabled. Original Nitra means the integrated upstream generated-parser machinery, not an independently validated historical binary or native C.

## What was checked

`Worker.Run` creates a new SourceSnapshot on every operation. Native `ParseSession.Parse(SourceSnapshot)` creates a new ParseResult; its constructor allocates fresh rawTree and memoize integer arrays. No old ParseResult is passed into this overload. Reusing a ParseSession therefore does not reuse the last input's recognition result. The harness forces typed fields, serializes them, maps and prints PExprs on both paths. Original correctness checks also mutate input to an invalid string, then parse the original again. The audit repeats tree/mapping equality and the recovery control; all six cases pass. Backend compilation/execution is outside these timings and was already checked in the comparison corpus.

`AuditWorker.cs` is a diagnostic derivative generated from Worker.cs. It splits the exact side Structure calls into Recognize and NitraStructureBuilder.Run, then retains typed-tree construction, forced snapshot, serialization, and mapping. Native recognition includes Parse; lazy typed fields are forced in snapshot traversal. Side splitting uses reflection, so small overhead is added. Each engine/case runs sequentially in a fresh process, with two warmups and five samples of three operations. Detailed phase records are the last operation of each sample; their medians need not sum to the median of the averaged full-operation samples. These diagnostics are not a replacement for the three-process paired benchmarks.

## Measured explanation

See `../coreclr-verification/nitra-performance-audit.json` for final phase measurements and per-phase allocated bytes. See `nitra-scheduler-audit.json` for scheduler/export split and sample/selection counts. The second probe has three iterations, the first cold; queue counting and reflective settlement add overhead. Its durations must not be mixed with warm competitive timings.

Final warm diagnostic medians (milliseconds; phase medians are separate):

| Case | Nitra recognition | Side recognition | Side selection | Nitra total allocation | Side total allocation |
| --- | ---: | ---: | ---: | ---: | ---: |
| chain-128 | 0.029 | 6.087 | 1.952 | 0.61 MB | 12.09 MB |
| list-2048 | 0.271 | 138.814 | 115.279 | 6.04 MB | 160.75 MB |
| sql-2048 | 0.299 | 173.405 | 156.042 | 4.21 MB | 183.30 MB |
| near-miss-2048 | 0.497 | 176.201 | 0.083 | 0.80 MB | 101.81 MB |
| nesting-256 | 0.040 | 38.353 | 13.744 | 0.73 MB | 33.28 MB |

Native rejection includes unwinding the strict-rejection callback. Side recognition includes detailed region export; the separate scheduler probe splits this export. Native lazy materialization cost remains in the forced snapshot phase, included in all full-operation totals.

The main gap is before typed-tree mapping. Nitra generates parser methods specialized for grammar rules, list loops, token checks and calls. Its ParseResult stores recognition records in integer arrays. The side recognizer interprets NitraOperation.Kind, creates per-input NitraSamples, subscribes callbacks, queues closure notifications and searches retained evidence during a separate selection pass. Caching fixed substantial repeated work, but a cached object still has allocation, hashing, lookup and traversal costs.

For the 2,048-item list, the scheduler census finds 24,590 samples, 65,574 executed queued actions, 45,076 exported regions, and 24,582 selected structural nodes. Each sample initializes seven HashSets and a subscriber List (collection objects are allocated even where backing storage remains empty). Its retained cursors contain 34,839 entries. Selection retains 20,487 endpoint views and 14,343 suffix-search entries, as well as other records. These counts describe this implementation; equivalent integer-array parser records are not interchangeable units.

For the rejected 2,048-term near-match: 28,683 samples, 92,187 actions, 51,224 exported regions, 43,018 cursor entries, and zero selected nodes. Thus rejection cost is in recognition and reporting, not AST lowering or backend compilation.

A concrete extra pass exists in NitraRecognizer.Run after acceptance is known: it creates a NitraRegion for every sample/view, copies and sorts endpoints, builds child lists and sorts them. This runs even for rejected input. Large list/SQL export costs about 15–16 MB and roughly 25–30 ms in the diagnostic; rejected near-match export costs about 12.5 MB and roughly 25 ms. Selection consumes Evidence; other APIs and diagnostics consume Regions. Separating these outputs could avoid work in the compilation path, provided existing diagnostic contracts remain available.

The generated native parser does not have an equivalent separate NitraStructureBuilder search. Its raw records already encode recognition choices used to materialize typed fields. The side builder must find connections and create generic structural wrappers before the generated selected-tree factories build native typed trees. This extra representation is useful for the current integration but measurably expensive: around 72 MB list selection allocation and 92 MB SQL selection allocation.

Final normalization is a small part of the gap on these workloads. JSON serialization can dominate Nitra's instrumented full-operation total while being nearly identical between engines. Therefore the earlier submillisecond *full* small-case timings are plausible; native recognition alone is considerably smaller still. These fixtures are small expression/list/SQL grammars, not a benchmark of full language tooling, IDE updates or upstream large-language projects.

## Source locations

- `Worker.cs`: Run, Snapshot, repeated equality/recovery controls.
- `../../nemerle/native-nitra/upstream/Nitra/Nitra.Runtime/Parsing/ParseSession.n`: fresh ParseResult overload.
- `../../nemerle/native-nitra/upstream/Nitra/Nitra.Runtime/Parsing/ParseResult.n`: fresh integer arrays, RuleParser.Parse and typed-tree factory.
- `../../nemerle/native-nitra/upstream/Nitra/Nitra.Compiler/Generation/Parser/ParseMethodEmitter/CompileListWithSeparator.n`: emitted position/counter loop.
- `../../nemerle/ncc/parsing/NitraRecognition.n`: NitraSample, Schedule, Subscribe, Cursor and Run export.
- `../../nemerle/ncc/parsing/NitraStructures.n`: endpoint/suffix/transition caches and structure task stack.

## Next optimization targets supported by this investigation

1. Separate lightweight retained evidence from optional detailed region export. Retain complete reporting on demand; avoid paying for it on every compile or failed parse.
2. Compact recognition storage: integer IDs and arenas/arrays, small or singleton endpoint representations, typed cursor keys, and tagged queue records instead of many closure objects. Keep filtering, shared samples, recursion settlement, identity and ambiguity semantics.
3. Reduce selection's generic wrapper/search allocation, reusing recognized connections directly where unambiguous. Keep resolver ordering and captures intact.
4. Consider specializing prepared operations into direct executable recognizers for common sequences, lists and lexical rules. Original Nitra already moves grammar interpretation to generated code. This is an implementation choice that can preserve the user's grammar/space model.

The investigation establishes phase costs, allocations, concrete object/work counts and source-level causes. It does not give sampled CPU stacks or percentages for individual HashSet/closure methods; a statistical CPU/allocation profiler would be needed for that precision. No statistical CPU profiler was used. No production optimizations were made during this investigation.

Reproduce from workspace root:

```sh
python3 baseline/audit-nitra-performance.py
python3 baseline/audit-nitra-scheduler.py \
  --comparison-report baseline/coreclr-verification/nitra-comparison-retention-performance.json \
  --output baseline/coreclr-verification/nitra-scheduler-audit.json
```

The saved comparison's temporary build directory must still exist. Run sequentially, not alongside other benchmarks.

## Architectural correction after user review

The counts above characterize the current implementation, not a faithful benchmark
of the intended grouped structural projection. The intended operation discovers a
plausible start family, shares one structural observation and retained candidate
pool, and narrows that pool as evidence advances. Current Request performs initial
filtering and canonical-interface memoization, but keys work by operation and source
position; Initialize still dispatches alternatives into subscriptions and per-sample
continuations. Existing filtering/prefix sharing therefore must not be presented as
proof of complete family-level discovery and reuse. Before choosing generated-code
specialization or only smaller objects, investigate why detailed operation states
are being activated and whether compatible start families can remain grouped.
Reusable logical worker/state pools differ from OS-thread parallelism; parallelism
alone does not remove duplicate search. Source-independent formation caches and
source-dependent observed-region evidence require distinct validity rules.
