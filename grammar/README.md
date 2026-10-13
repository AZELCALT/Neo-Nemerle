# Grammar and space blocks

`grammar Name { ... }` declares Nitra syntax modules inside a Nemerle source file; `space Name { ... }`
(or `space (A, B) { ... }`, or a bare local `space { ... }`) writes input in that grammar, which the
compiler turns into Nemerle code. Both are part of the language: any compilation whose sources contain
them compiles them, with no option. The Nitra runtime dlls (`Integrated.*`) must sit next to
`Nemerle.Compiler.dll`.

- [NITRA-SYNTAX.md](NITRA-SYNTAX.md) - native Nitra declarations, `-nitra-syntax` inspection, host API.
- [NITRA-DIRECT-OUTPUT.md](NITRA-DIRECT-OUTPUT.md) - settled structures and direct Nemerle output.
- [NITRA-REGIONS.md](NITRA-REGIONS.md) - the structural-region recognizer, selection and the hybrid fast pass.
- [STRUCTURAL-PROJECTION.md](STRUCTURAL-PROJECTION.md) - the token-level structural projection API.
- [../native-nitra/README.md](../native-nitra/README.md) - how the native Nitra compiler is integrated.
- [../tools/language-server/README.md](../tools/language-server/README.md) - the language server (Nemerle parser + unmodified Nitra).
- [obsolete/](obsolete/) - the previous source-only grammar design (parked behind `OLD_GRAMMAR_DESIGN`).
