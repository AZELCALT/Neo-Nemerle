# Nitra-inspired compatibility inventory

This is a working source-grammar subset, not full Nitra compatibility. Declaration
spelling stays close where useful; all declarations are inside `grammar Name`.
No Nitra source implementation or binaries are incorporated.

| Facility | Prototype status |
| --- | --- |
| `syntax module`, simple rules, named alternatives | Implemented |
| `regex`, `token`, `void` character-level rules | Implemented |
| Literals, character ranges, grouping, alternatives | Implemented |
| Named captures, `?`, `*`, `+`, separated lists, trailing separators | Implemented; repetition is greedy |
| Positive/negative lookahead | Implemented |
| Module imports and aliases | Implemented for visible source definitions |
| `extend syntax`, token extensions | Implemented for selected compositions |
| Named precedence, relative order, associativity, qualified references | Implemented for precedence-style expression rules |
| `[StartRule]` | Retained on rule metadata; statement forms select zone roots |
| `[ExplicitSpaces]` | Disables automatic spacing in the annotated rule |
| `Nitra.Core` / `Core` import | Recognized built-in module names |
| `Any`, `s`, `S`, `sm`, `nl`, `inl`, `d` | Available; spacing markers consume optional whitespace, without pretty printing or keyword-regex behavior |
| `IgnoreToken` | Lexical alternatives provide grammar-declared comments/trivia |
| Statement forms and semantic kinds | Prototype additions |
| Source actions | Ordinary Nemerle blocks parsed/retained; no execution |
| Nitra method bodies such as `override Value`, `missing`, `[Cached]` | Not implemented; not silently executed or discarded |
| Nitra `map syntax`, `ast`, declarations/symbols and dependent properties | Not implemented; future lowering targets existing Nemerle AST |
| `language` declarations, generated grammar assemblies | Not implemented |
| Keyword-regex declarations, Unicode category classes, literal/marker/alias declarations | Not implemented |
| Other Nitra attributes and standard library modules | Explicit unsupported/unknown diagnostics |
| General left-recursive grammars beyond precedence expressions | Explicit unsupported-recursion diagnostics |
| Arbitrary custom lexical envelopes | Not yet implemented |
| Grammar changes through arbitrary user callbacks | Part 2; explicit space composition works now |
| IDE generation, recovery/completion, pretty printing | Not part of this prototype |

## Envelope limit

Foreign bodies are not fed through Nemerle's lexer/preparser. Grammar matching
recognizes their contents within the indexed envelope and cannot cross its
closing point. The preliminary declaration-index
scan still needs to skip space envelopes to discover later definitions. It
currently understands balanced braces, ordinary single/double quoted strings,
backslash escapes, and C-style/SQL line comments. This is sufficient for the checked
examples, including SQL doubled quotes and braces inside strings/comments. A
language with a different quotation/comment convention may need additional
indexing support even if its grammar rules themselves are valid. This restriction
is explicit; it is not a claim that every language is supported already.

## Reference material

The design was researched against the archived JetBrains Nitra source:

- [Calculator declarations and extensions](https://github.com/JetBrains/Nitra/blob/master/Grammars/Samples/Calculator/Sample.Calc/CalcGrammar.nitra)
- [Syntax mapping sample](https://github.com/JetBrains/Nitra/blob/master/Grammars/NitraMappingSample/Sample-Mapping.nitra)
- [Grammar composition](https://github.com/JetBrains/Nitra/blob/master/Nitra/Nitra.Runtime/CompositeGrammar.n)
- [Scoped dynamic-list parsing](https://github.com/JetBrains/Nitra/blob/master/Nitra/Nitra.Compiler/Generation/Parser/ParseMethodEmitter/CompileList.n)

These references establish mechanisms, not a measured explanation of Nitra's
performance or project history. No performance comparison with Nitra has been made.
