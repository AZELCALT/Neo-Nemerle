# nemerle-lsp

A language server for Nemerle source files, including `grammar` and `space` blocks.

- **Nemerle code** goes through the compiler's own lexer and `MainParser`. That gives tokens, declarations
  (document symbols and folding) and parse errors.
- **Grammar and space blocks** are found by the compiler's own source index (`NitraEditorIndex`, the same
  scan compilation uses). They are then parsed by the **unmodified Nitra runtime**: `ParseSession` with its
  default error recovery, the highlighting walker (`GetSpans`), the outlining walker (`GetOutlining`) and its
  messages.
  - Grammar blocks are parsed with Nitra's own `NitraSyntax` grammar.
  - Space bodies are parsed with the grammar Nitra's compiler generates from the file's grammar blocks.

  None of Nitra's IDE ecosystem (its client/server, project system or Visual Studio parts) is used, and the
  code a space expands to is not generated. The compiler itself keeps using its own engine (`NitraSyntax.Structure`).

Supported requests: `textDocument/didOpen`, `didChange` (full sync), `didClose`, `publishDiagnostics`,
`semanticTokens/full`, `foldingRange` and `documentSymbol`.

## Build and check

```sh
python3 build/build-language-server.py --toolchain <stage with Integrated.* dlls> \
  --references <dotnet>/packs/Microsoft.NETCore.App.Ref/<v>/ref/net10.0 \
  [--nitra-compiler <Integrated.Nitra.Compiler.dll with NativeSourceHost.GrammarAssembly>] [--output out/language-server]
python3 tests/check-language-server.py --server out/language-server/nemerle-lsp
```

The server needs the toolchain next to it: it compiles each file's grammars in-process with Nitra's compiler.
It also needs reference assemblies. It uses `--references DIR` if given, then `<exe dir>/references`, then the
newest `Microsoft.NETCore.App.Ref` pack of the running dotnet. Use `--log FILE` to log timings and errors.

## Editor

`vscode/` holds a minimal VS Code / VSCodium extension. Set it up with `npm install` in that folder, then either:

- run `codium --extensionDevelopmentPath=nemerle/tools/language-server/vscode`, or
- package it with `npx @vscode/vsce package`.

Point the `nemerle.languageServer.path` setting (or the `NEMERLE_LSP` environment variable) at the
`nemerle-lsp` launcher.

## Timing

Measured on this machine:

| Situation | Time |
|---|---|
| Plain file | about 40–60 ms |
| First analysis of a file with grammars (Nitra compiles them) | about 2.5 s |
| Later edits that leave the grammar text unchanged (compiled grammar cached by its text) | about 30–60 ms |
| Edit to a grammar block | the grammar is recompiled before the next answer |

## Limits

No completion, hover, go-to-definition or references yet; those need typing.
