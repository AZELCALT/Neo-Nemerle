# Nemerle for VS Code and VSCodium

Language support for [Nemerle](https://github.com/AZELCALT/Neo-Nemerle), the revived language for .NET 10:

- highlighting, including `grammar` and `space` blocks (parsed by Nitra with the file's own grammars);
- diagnostics from the compiler's parser and Nitra, as you type;
- typed diagnostics for the workspace (type errors, through `using` and exported types across files), hover with the
  type of a name, and go-to-definition, from a background compile once edits settle;
- outline (document symbols) and folding.

The extension carries its language server. It needs only the
[.NET 10 runtime](https://dotnet.microsoft.com/download/dotnet/10.0).

## Install by hand

```sh
code --install-extension nemerle-0.2.0.vsix      # VS Code
codium --install-extension nemerle-0.2.0.vsix    # VSCodium
```

Or in the editor: Extensions view, `...` menu, *Install from VSIX...*.

## Debugging

Run and Debug (F5) builds the folder's project with `ncc build` and debugs `out/<name>.exe`: breakpoints in `.n`
files, stepping, the call stack, parameters, locals and top-level state. The debugger is
[netcoredbg](https://github.com/Samsung/netcoredbg) (MIT), which works in VS Code and VSCodium alike: put it on `PATH`
or set `nemerle.debugger.path`. Build with `options = ["-debug+"]` in the project's `[compiler]` section.

## Settings

- `nemerle.dotnet.path`: the `dotnet` that runs the server (default: `dotnet` on `PATH`).
- `nemerle.languageServer.path`: another `nemerle-lsp` to use instead of the bundled one.
- `nemerle.languageServer.sourceRoot`: the root of file module paths (default: the workspace folder).
- `nemerle.languageServer.log`: a log file for the server.
- `nemerle.languageServer.typecheck`: the background typed check (default on).
- `nemerle.languageServer.libraries`: assemblies the workspace references, for the typed check.
- `nemerle.debugger.path`: netcoredbg (default: on `PATH`); `nemerle.ncc.path`: the `ncc` that builds before debugging.

The extension and its server are licensed under the GNU GPL, version 2 or later.
