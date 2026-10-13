# Experimental block archives

This is placeholder infrastructure for later compiler-building work. It retains
source-defined components without assigning compile-time or runtime semantics.
It does not provide full Nitra syntax modules or execute foreign syntax.

## Try it

From the workspace root, use the isolated archive prototype:

```sh
dotnet toolchain/grammar-archive-prototype/ncc.exe \
  -experimental-grammar-ir -out:Draft.dll \
  nemerle/grammar/examples/placeholders.n
```

The output is a metadata-only CLR DLL with a custom `.nemir` PE section. It contains
no compiled source types, methods, or entry point. Surrounding ordinary source is
not compiled in this mode. The completion message explicitly reports inactive
source behavior. Normal compilation still diagnoses unimplemented constructs.
The separate `-parse-grammar-spaces` mode continues to exercise phase-1 recognition;
it cannot be combined with archive mode. Neither installed toolchain is replaced.

## Placeholder forms

Each of `runtime`, `compile`, `grammar`, and `space` accepts:

```text
kind { opaque body }
kind name { opaque body }
kind (GrammarA, Other.GrammarB) { opaque body }
```

Named headers and explicit grammar lists are distinct records. Lists retain order
and duplicates. References are not resolved, and their interaction is not designed
by this implementation. In particular, `grammar (...)` is reserved interaction
structure, not an implementation of grammar composition behavior.

Bodies preserve exact source text between the braces, including whitespace and
comments. Unknown future syntax is accepted within the supported envelope. Text
that resembles another block inside a body stays opaque; it is not independently
indexed. This preserves room for a later grammar-aware interpretation.

The envelope scanner understands nested braces, ordinary single/double quoted
strings with backslash escapes, C comments, and SQL `--` comments. Arbitrary raw
strings, interpolation rules, other quoting conventions, and decrement-like `--`
text are not universally supported. Those require later lexical design. These are
scanner limitations, not restrictions on the planned languages.

## Compiler API and experimental format

Public types live in `Nemerle.Compiler.dll`:

- `ExperimentalGrammarBlock`: kind, header form, optional name, grammar list, file,
  file-module owner, nearest enclosing source-brace offset, block/body spans, body.
- `ExperimentalGrammarArchive`: blocks, diagnostics, success, `ToJson()`.
- `GrammarArchives.Collect(sources, sourceRoot)`: source-only collection; no compiler
  manager initialization, binding, assembly loading, or execution.
- `GrammarArchives.Serialize` / `Deserialize`: versioned archive transport.
- `GrammarArchives.WriteDll(archive, path, keyFile, debug)`: explicit persisted archive.
- `GrammarArchives.ReadDll(path)`: inspect without loading or executing the assembly.

Spans are half-open UTF-16 offsets. `EnclosingStart` is the nearest ordinary opening
brace, or -1 at top level; it is lexical context, not a resolved compiler scope.
`Owner` follows source-root/file-module naming. Source paths are retained as supplied
by the compiler source registry. Bodies are exact text, not raw source-file bytes.

The `.nemir` section contains UTF-8 JSON with format identifier
`Nemerle.Experimental.GrammarIR`, version 1, and a `blocks` array. It is readable,
non-executable initialized data. Its virtual size delimits the JSON; PE file
alignment padding is not part of the payload. The CLR does not interpret it.
The platform adapter transports the section and signs the completed PE directly,
so signing does not rewrite away compiler data.

An absent section returns null. Malformed PE, UTF-8, JSON, or records raise
`InvalidDataException`; unsupported archive versions raise `NotSupportedException`.
Collection failures return diagnostics and prevent archive serialization/emission.
The reader does not activate imported grammars. No live AST or compiler scope is
serialized. No compatibility promise extends beyond this experimental version.

## Verify

```sh
python baseline/check-grammar-archives.py \
  --toolchain toolchain/grammar-archive-prototype --references /path/to/net10.0/refs
python baseline/check-grammar-archive-api.py \
  --toolchain toolchain/grammar-archive-prototype --references /path/to/net10.0/refs
```

See [the four-phase roadmap](PART2.md). All phases remain experimental and require
usage feedback before stabilization. This archive gives later work a place to
populate compiler/runtime details without specifying them now.
