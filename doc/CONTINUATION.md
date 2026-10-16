# Continuation section

A Nemerle binary can carry a compiler-owned section, `.nemir`. It holds what a later, late-bound compilation needs to
continue from that binary: typically a script compiled by the embedded compiler inside a host application. It works
like Objective-C's `__objc_*` sections: the compiler writes its own metadata into every binary it produces. The section
is not a managed resource; the binary format is only the carrier.

It is on by default. Every output that defines grammars or macros carries the section, and every compilation
continues from the binaries it references that carry one. `tests/check-continuation.py` checks it as part of
`./bootstrap`.

## Using it

```sh
ncc host.n -target:library -out:host.dll ...   # host.dll carries the section (grammars, macros)
ncc use.n -r:host.dll ...                      # continues from it: its grammars, macros, and their helpers
ncc use.n -continue:host.exe ...               # continue from a binary without referencing it
ncc lib.n -no-continuation-section ...         # write no section
```

The compiler API has `CompilationOptions.ContinuationSection` and `CompilationOptions.ContinueFrom`.
`NEMERLE_CONTINUATION_DIFF=1` prints what a continued compilation did with each stored grammar: `diff`, `patch`, `reuse`,
`fallback` or `skipped`.

## Format

The payload of `.nemir` is a container (`ncc/Nemerle/Compiler/continuation.n`, `ContinuationStore`):

- **Header:** magic `NEMC`, format version, compiler version. Grammar images are bound to that exact compiler and Nitra
  build; images from another build are skipped.
- **String table:** UTF-8, deduplicated. All numbers are ECMA-335 compressed integers.
- **Subsections** (kind byte + length). Unknown kinds are skipped.
  1. **grammar:** the compiled Nitra grammar image (Deflate), plus a **mark** for every grammar declaration (syntax
     module, rule, alternative, `using`, map body). A mark holds:
     - kind, name and scope;
     - its source span and its parent;
     - a hash of its whole text and of its own text (children cut out).

     Both hashes collapse whitespace outside literals, so layout-only edits don't change them.
  2. **macro:** for every macro the binary defines, its name, its CLR class and the source span of its definition.
  3. **type:** for the *relevant set* only, meaning modules that define macros: the members that CLR visibility hides
     from a referencing compilation (internal ones). Everything else comes from ordinary .NET metadata.
  4. **scope:** the binary's shared scopes (`scope A;`), stored next to its grammars as their storage layout. For
     each slot: its name, its type token, and the Nemerle type it reads as (`object` when nothing gave one). The values
     are not stored: they live in the storage of the running program (`Nemerle.Scopes.Scope`, shared by the whole
     process). A slot holding a dial reference is not stored. With the scopes come the binary's spaces: for each, the
     grammars it uses, its path (`file`, `file.G` or `file.(A,B)`), its file, its `as` name, the scopes it attaches,
     and its body. Scopes are plain data, so they are read whatever compiler wrote them.
  5. **module:** every file module of the binary and its top-level code: whether it runs at a `using` (an
     initializer) or starts the program, the lines of its top-level code, a hash of it, the modules it imports, and
     the names of its top-level state. It is the fingerprint by which Nemerle binaries know each other's modules: a
     continuing compilation runs the top-level code of the binary's modules it imports, through modules without any,
     and keeps the binary's top-level state reachable only as `file.x`.

The section is appended to the finished image, after the Mono.Cecil metadata rewrite, which would drop it. The file is
then strong-name signed again (`platform/ClrCompilerSection.cs`). The PE header must have room for one more section
header. Cecil's output (`.text`, `.reloc`) has room. An image with a `.rsrc` section does not yet; it gets a warning and
no section.

## What a continued compilation does

| Situation | Result |
|---|---|
| A `space` uses a stored grammar that the source does not define | The stored image is loaded and no grammar is compiled. |
| The binary stores scopes | Their layouts are registered before the source's spaces are read, so `scope.A.x` and `space G [A]` work with no `scope` declaration, and reach the same storage when they run in the binary's process. |
| The binary stores spaces | Each is indexed as a space of its file there, with its attached scopes; a dial into it re-runs its mapping in this compilation (to register its resolver), and nothing of it is emitted. A space whose grammar image cannot be used here is left out. |
| A source has no space but uses `scope.` or a dial (`dial:.file.G::m`) | It takes the grammar path like a file with a space, so a plugin script reaches the host's scopes. |
| A plain `space { ... }` in a file without its own grammars | It selects every visible grammar, the stored ones included. |
| The source redefines a stored grammar, unchanged up to layout | `reuse`: the stored image is used as is. |
| Only alternatives of extensible rules changed, were added or removed | `patch`: just those alternatives are compiled, as `extend syntax` blocks of a patch module over the stored module, and the stale stored alternatives are dropped. |
| Anything else (a rule, a module, `using`s, a precedence group) | `fallback`: the grammar is compiled in full. |
| The binary defines macros | They are loaded without `-m`. |
| A host macro expands to an internal member of its module | The member is visible to the compiler, and the output carries `IgnoresAccessChecksTo(<host>)` so the .NET runtime allows the call. Internals of other modules stay hidden. |

## Measurements

Measured by `tests/check-continuation.py` on one machine; a plain compile with no grammar takes about 1.1 s.

| Case | Time |
|---|---|
| 10-rule grammar, fresh compile | 5.1–5.6 s |
| 10-rule grammar, continued (stored image) | 1.4–1.5 s |
| 120-rule grammar, fresh compile | 8.2–8.6 s |
| 120-rule grammar, continued | 1.5–1.7 s |
| 120 rules, one alternative's `map` edited (patch) | 3.6 s |
| 120 rules, alternative added / renamed (patch) | 3.8 s / 3.6 s |
| 120 rules, redefined unchanged (reuse) | 1.5 s |
| 120 rules, a new non-alternative rule (fallback) | 9.0 s |
| Script using a host library's grammar, macros and helper | 1.5–1.7 s |

The section for a 10-rule grammar is about 21 KB; its 64.5 KB image compresses to a third of that. Writing the section
adds no measurable time to a compile.

## Limits (open)

- **Patch cost:** a patch still pays the fixed cost of a nested Nitra compile (about 2 s). A warm compiler process
  would remove it.
- **Patched results aren't stored:** a patched compilation does not write a grammar subsection of its own.
- **Narrow patch scope:** changes inside precedence groups, to whole rules or to modules fall back to the full compile.
- **Carrier:** only PE images, with header room for one more section (otherwise a warning and no section).
- **Trust:** loading a stored grammar image runs code from that binary, the same trust as referencing it.

`NEMERLE_DUMP_GRAMMAR_IMAGE=<path>` writes the grammar image a compilation produces, for inspection.
