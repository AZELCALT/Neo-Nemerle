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

- **Typing** runs in a separate process, `nemerle-lsp --check` (`checker.n`), once edits have paused for 0.6 s; a newer
  edit kills a check still running. It compiles in memory, with the full compiler, the files the editor needs:
  - the open files (their unsaved text);
  - the files they import (`using a.b` is `<root>/a/b.n`), transitively;
  - every workspace file that exports a type (global types are reached without a `using`).

  When the workspace folder is a project (a `.nproj` file), the project says whether it is a program, where it
  starts, and what it references: the references its last `ncc build` resolved (`out/NAME.references`, packages and
  other projects included). Otherwise the workspace is a program when `<root>/main.n` is among them, a library
  otherwise. Its errors and warnings
  (type errors, `NotYet`, type changes, threads, export conflicts) are published for every file they are in, open
  or not, merged with the parse diagnostics. Each typed reference (a local, a member, a constructor) becomes a fact
  with its type and its declaration: hover and go-to-definition answer from the latest check. A compilation with
  errors stops before typing everything, so a file it typed nothing of keeps its earlier facts.

- **Completion** writes a marker identifier at the cursor and runs the checker in the compiler's completion mode:
  when the typer reaches the marker, it lists what fits there from its own view (the members of the object's type
  after a dot, the types, namespaces and static members of a path, else the locals in scope, the file's functions and
  state, what the `using`s open, and keywords).
- **Find-references and rename** run a check of the whole workspace and use its facts: every use of the declaration
  under the cursor (or of the one a use names). Rename edits the names alone, for locals, fields, properties,
  methods and events.

Supported requests: `textDocument/didOpen`, `didChange` (full sync), `didClose`, `publishDiagnostics`,
`semanticTokens/full`, `foldingRange`, `documentSymbol`, `hover`, `definition`, `completion`, `references`,
`prepareRename` and `rename`.

Options: `--references DIR`, `--source-root DIR`, `--file-name-namespaces`, `--library DLL` (repeatable, for the
typed check), `--no-typecheck`, `--log FILE`.

The installers in `install/` build and install it, together with the VS Code / VSCodium extension (see the
top-level README). To build it by hand:

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

`vscode/` holds the VS Code / VSCodium extension: the client, a TextMate grammar (highlighting before the server
answers), and the language configuration.

- **A .vsix to install by hand:** `build/build-vscode-extension.py` packages the extension with the server, its
  toolchain and reference assemblies (`out/vscode/nemerle-<version>.vsix`, about 10 MB), so it needs only the .NET 10
  runtime. `./bootstrap` builds it too and `tests/check-vscode-extension.py` checks it: its contents, that the
  extension starts the server it carries, and that VSCodium (or VS Code) installs it.
- **For development:** `npm install` in `vscode/`, then `codium --extensionDevelopmentPath=tools/language-server/vscode`.

The extension uses, in order: the `nemerle.languageServer.path` setting (or `NEMERLE_LSP`), the server it carries
(run on `nemerle.dotnet.path`, default `dotnet`), and `nemerle-lsp` on `PATH`.

## Timing

Measured on this machine:

| Situation | Time |
|---|---|
| Plain file | about 40–60 ms |
| First analysis of a file with grammars (Nitra compiles them) | about 2.5 s |
| Later edits that leave the grammar text unchanged (compiled grammar cached by its text) | about 30–60 ms |
| Edit to a grammar block | the grammar is recompiled before the next answer |
| Typed check of a small workspace (two files) | about 2 s after edits settle |

## Limits

- Completion types the file with the marker at the cursor: another unfinished line elsewhere in the file (a parse
  error) stops the compiler before it gets there, and nothing is offered.
- Types (and their constructors) are not renamed yet; type annotations are not facts, so a rename would miss them.
- Find-references and rename compile the whole workspace each time (a few seconds for a small one).
- Hover and go-to-definition come from the latest finished check: right after an edit they describe the previous text
  until the next check ends, and positions can be off by the edit in between.
- Scripts (files that name `DependsOn`) need the scripting host and are not typed. A workspace without a `main.n`
  is checked as a library.
- The typed check compiles everything it needs each time; a large workspace takes as long as a compile.
