# Structural-region recognizer (design draft, branch design/structural-recognizer)

Replaces the sample/queue/pool recognizer in `NitraRecognition.n`. Source of intent:
`typed_recursive_syntax_chunks_for_codex.txt`. Status: DESIGN ONLY, awaiting review.

## 1. Contract that must not change (parity target)

`NitraRecognizer.Run(root,name,retain,detailed)` must produce the same observable result as today:
- `Evidence.Ends[(opId,pos)]` = exact set of end positions, for every (operation,position) the
  old engine produced, including child operations of sequences (the selection builder reads them),
  lexical results, and canonical/identity "views" (capture/variant/call wrappers share the interface's set).
- `Accepted`, `Complete`, `Furthest`, `MatchedProductions`, `Diagnostics` (same messages for the
  same failures), safety limits (5,000,000 evaluations, 500,000 regions).
- Semantics of: `longest` and non-`AllEnds` repeat (keep only the greatest end), `not`/`and`
  (zero-width lookahead), `subtract`, `separated` incl. trailing, `Min/Max`, non-progressing-repeat
  error, nullable handling, left recursion and cycles (indirect too), cyclic negative/longest error.
- All-ends (relational) semantics: a (op,pos) yields a SET of ends; ambiguity is preserved.
  This is what lets selection report real ambiguity. It is a capability, so it stays.

## 2. What the design changes (and the counters that prove it)

| Brief | Today | New |
|---|---|---|
| Group shared requirements, one projection per family start | one sample per alternative per stage | ONE region per (family,pos); alternatives are bits of a production mask over the existing `NitraCandidateFamily` trie |
| Observe shared body once | `Request` keyed by (op,pos) but alternatives still subscribe separately | body/prefix interface requested once per (interface,pos); surviving productions reference it |
| Close on boundary, eliminate incompatible family | close by exhaustion only | boundary literal/trie transition closes the body region and clears mask bits whose tail differs; tail kept as an unresolved relation on the mask |
| Retain child regions, don't rescan | only (op,pos)->ends kept; selection re-searches | each region records child region refs per consumed stage in one int arena; selection reads them |
| No rewind/re-request | enforced by cursors, but via closures + hash sets | `BodyReparses` counter must be 0 by construction |

Counters added to `NitraRecognitionResult` (implementation-independent evidence for the final verdict):
`RegionCreations`, `AlternativeExpansions` (target 0 for grouped families), `BodyRerequests` (0),
`BoundaryCloses`, `MaskEliminations`, `TokenVisits`, `ChildRefs`, `SelectionResearchSteps` (builder, target ~0).

## 3. Engine

Storage: struct-of-arrays region table (`op, start, state, endsHead, mask, childHead, pending`) plus
append-only int arenas for ends and child refs. No per-region HashSet, List, closure or delegate.
`Ends` of a region = arena segment with a small-set/singleton fast path; dedup via a tiny open-addressed
per-region membership only when count > 8.

Evaluation is hybrid:
1. **Pull path (default, no queue).** `Ends(op,p)` is evaluated by an explicit-stack frame machine.
   A frame is (region, stage, cursor). A request for an already CLOSED region returns its ends
   immediately; a request for a lexical/fast op uses the existing `Lexical` scanner inline.
   Sequences iterate stages with a position set held in a reusable scratch buffer, appending child refs.
   Repeats are an int loop appending child refs. This is the hot path for lists, SQL-like statements and
   non-left-recursive structure, and handles nesting depth without CLR recursion.
2. **Incremental path (only for regions that re-enter themselves at the same start).** When a request hits
   an OPEN region on the stack with the same start position, the requester and everything between it and
   that head are marked members of a cycle component. Component members keep append-only ends and a per-consumer
   delivered cursor (semi-naive: only NEW ends are pushed through the continuation, never re-scanned).
   Components settle with the existing rule: when no unsettled work remains, leaf components close;
   a barrier (`not`/`subtract`/`longest`/non-AllEnds repeat) inside a cycle is the existing
   "cyclic negative or longest-match" error. The SCC bookkeeping (`NitraDependencyComponent`, `Depend`,
   `SettleUnindexed`) is ported but only runs for regions in a cycle, not for every sample.
   Rationale: left recursion with all-ends sets is O(n^2) if bodies are re-run to a fixpoint, so deltas are required.

Family start (`Initialize` for ops with `Family`): look at the first source char, intersect the root mask with
the family's first-char/literal table (existing `NitraLiteralFilter`, `FirstAscii`), and walk the family trie one
node per shared structural requirement. Where all remaining productions need the same next interface, request it once.
Where the next requirement is a literal terminator set, a trie step closes the body and drops incompatible bits.
A production splits into its own continuation only where the next required interface genuinely differs.
Productions that survive to a terminal node emit their ends; the mask retained on the region is the unresolved
production/tail relation.

Not carried over: evidence pools, flat node store, filter workers, candidate-set interner, guard batches,
timestamp/epoch/session commits. They scheduled per-sample work that no longer exists. Parallelism is out of scope
until the serial path beats Nitra on structure counters.

## 4. Selection (Step 3)

`NitraEvidence` gains `ChildRefs`: for each (op,start,end) the ordered child (op,start,end) chain recorded when the
end was produced. `NitraStructureBuilder` follows these instead of `Endpoints/RawSuffix/Suffix/AskRepeat`.
Where a region has several derivations (ambiguity), all chains are kept so the existing resolver sees the same choices.
Old search stays behind an internal flag until the comparison corpus is green.

## 5. Expectation check (read before approving)

Original Nitra's recognition is ~0.27 ms for the 2048-item list (~130 ns/item), i.e. close to the floor for
managed code. Its whole `Worker.Run` is 11.2 ms for the same case; most of that is typed-tree forcing and
serialization, which both engines share. So:
- Design goal reachable: recognition + selection from ~254 ms to a few ms, i.e. within a small factor of Nitra.
- Beating Nitra end to end requires the tree-build from retained child refs to be cheaper than Nitra's lazy
  materialization. That is plausible but not guaranteed; the structure counters, not wall time alone, decide
  "design vs implementation".

## 6. Risks / open decisions for review

1. Hybrid pull + incremental engine (above) vs pure incremental with flat storage. Hybrid is faster on the common
   path but has two code paths to keep equivalent; equivalence is tested by running both on the whole corpus
   (a debug flag forces everything through the incremental path).
2. Family grouping only applies to ops that already get a `Family` (seq/rule/alt/longest, non-Fast). Anything else
   stays a plain region. This is the same boundary as today.
3. Ambiguity chains in `ChildRefs` can be large for highly ambiguous grammars; bounded by the same safety limits.
