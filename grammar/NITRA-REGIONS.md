# Structural-region recognizer and selection (branch design/structural-recognizer)

Replaces the sample/queue/pool recognizer and the closure-driven structure builder.
Intent: `typed_recursive_syntax_chunks_for_codex.txt`. Everything here stays experimental;
the previous implementation is preserved on branch `wip/codex-pools-snapshot`.

## What it is

`NitraRegions.n` — recognizer. One region per (structural interface, source position),
stored in flat arrays (op, start, closed, pending/outstanding counters, ends, held ends,
subscriber/owned link chains). No per-region hash sets, closures or delegates.
Ends are all-ends relations: ambiguity is retained, never resolved during recognition.

* Delivery is push based: a new end of a region is queued once for every consumer link.
  The work stack is LIFO; a region closes when its pending work and its unclosed children
  reach zero (counters, not sets).
* Same-position cycles (left recursion, indirect cycles) settle when the work stack is
  empty: open regions at the greatest start depend only on each other (children never start
  before their owners), so Tarjan runs only on that group and closes leaf components.
  A negative/longest barrier inside a cycle is still the existing diagnostic.
* Kind-directed dispatch: first-character tables (`Possible` / `Begins`) eliminate a request
  before any region exists. Operations that always have a zero-width result and cannot start
  at the current character (`Sure` and not `Begins`, e.g. optional whitespace) deliver that end
  inline and open no region. Pure lexical operations are scanned, not opened.
* Sequence prefixes become interfaces only where several sequences share them (branching or
  shared ends). A sequence nobody shares is a single n-ary region.
* Evidence reads the recognizer's tables directly (`EvidenceAt`); nothing is exported or
  copied. Diagnostic `Regions` are built only when `detailed` is requested.

`NitraSelection.n` — structure selection over evidence. Explicit stacks, no CLR recursion.
* A feasibility machine (choice / greedy call / sequence / repetition frames) with long-keyed
  memo tables. It reproduces the native greedy-call rule (a call takes the longest feasible end).
* Sequences keep a derivation plan (edges per stage, and which lie on a path to the end);
  repetitions keep a state graph; choices keep the matching alternatives. Construction reads
  these plans; ambiguity is passed to the resolver in the same order as before.
* Pure pass-through wrappers (single-child rule/variant/capture/call, subtract) are skipped when
  asking feasibility; leaves are answered by the scanner.

## Deviations from the original brief, stated plainly

* The engine is a relational (all-ends) recognizer over characters, because the capability to be
  preserved is Nitra's grammar surface (lexical rules, precedence, ambiguity). The brief's
  "close a body on its boundary and eliminate the other termination family" is realised as
  first-character elimination of requests plus shared prefix interfaces; there is no separate
  boundary-mask object. The token-level boundary example is covered by `StructuralProjection.n`.
* (branches design/recorded-derivations, opt/ladder) Recognition records derivation edges per region
  (sequence stage, alternative index, subtract left end, repeat item / separator) in a flat arena.
  When a region closes its feasible ends are settled (the native "a call takes the longest feasible end"
  rule); the work is replayed in close order only after the input is accepted, so rejected input pays
  nothing. Selection reads those records: feasibility asks are answered from the settled region, and
  sequence, choice and repetition plans are built from the edges. Shared-prefix interface regions are
  flattened into the stages of the original sequence by a backward walk from the end (edges are
  indexed by end per region). Regions the records cannot express (invalid / nested greedy groups) fall
  back to the original search, which is kept. `NITRA_VERIFY=1` compares every recorded answer and plan
  with the search and throws on a difference; `NITRA_NOFAST=1` turns the recorded paths off.
* Regions are found by start position (head array plus chain), selection cells and entries likewise;
  same-position cycle settling uses shared scratch.

## Hybrid fast pass (branch opt/hybrid, `NitraFast.n`)

`NitraSyntax.Structure` first runs a fast pass that computes the same two relations the engine above settles:
R(op, p), the ends of an operation at a position, and F(op, p), its feasible ends (a greedy native call keeps
only the longest feasible end of its target). It works top-down with one memo entry per (operation, position),
the way Nitra's memo table does, and then builds the structure exactly as `NitraStructureBuilder` would.

* Pass-through wrappers share their child's entry; deterministic lexical subtrees are scanned without entries.
* Left-recursive groups (an entry read by its own descendants while still running) settle from a worklist of
  readers whose input grew; only unions and the first stage of a sequence may take part (both only add ends).
  A group whose ends did not grow after they were read needs no settling.
* Every feasible sequence end keeps the stage ends of the path that reached it, and every feasible union end the
  alternative that produced it. Construction reads these back; a second path or alternative for the same end is
  precisely an ambiguity.
* Rejected input is answered by the fast pass itself (same furthest offset and message as the full engine).
* Ambiguity is decided in the fast pass the way `NitraStructureBuilder.Pick` decides it: the same options, in the same
  order, at the same moments, handed to the same resolver (no resolver: the same diagnostic).
* It gives up and the full engine runs from scratch on: an accepted input that is not feasible,
  a cycle through any other operation, very deep nesting. So the result is always the full engine's result.
* `NITRA_VERIFY=1` runs the full engine first (recording the resolver's questions and answers), then the fast pass
  replaying those answers; questions, nodes and rejections (offset, message) must be identical;
  `NITRA_NOHYBRID=1` turns the fast pass off; `NITRA_HYBRID_WHY=1` prints why it gave up.

## Results (this machine, .NET 10.0.12, sequential, 3 fresh processes per engine)

See `baseline/coreclr-verification/nitra-regions-*.json`. Differential comparison against the
original Nitra machinery: 72/72 cases, backend execution correct, chain-2048 passes under the
CLI-sized backend stack. These are measurements of this corpus on this machine, not a proof of
general speed or full equivalence.

## Diagnostics

`NITRA_PHASES=1` prints warm per-phase medians at process exit (recognize, export, select,
feasibility and per-frame-kind time). `NITRA_DUMP=1` prints the region histogram by operation.
Both are read from the environment once and cost nothing when unset.
