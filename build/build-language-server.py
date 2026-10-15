#!/usr/bin/env python3
"""Build the Nemerle language server (nemerle/tools/language-server) into a self-contained directory.

The directory holds the toolchain (compiler + Integrated.* Nitra dlls, needed at run time to index grammar/space
blocks and to compile their grammars) and nemerle-lsp.exe; start it with `<out>/nemerle-lsp` (stdio LSP)."""
import argparse, pathlib, shutil, subprocess, sys

p = argparse.ArgumentParser()
p.add_argument('--toolchain', type=pathlib.Path, required=True, help='stage dir with ncc.exe, Nemerle.Compiler.dll and Integrated.* dlls')
p.add_argument('--references', type=pathlib.Path, required=True, help='.NET reference assemblies (packs/Microsoft.NETCore.App.Ref/<v>/ref/net10.0)')
p.add_argument('--nitra-compiler', type=pathlib.Path, help='Integrated.Nitra.Compiler.dll to use instead of the toolchain copy (needs NativeSourceHost.GrammarAssembly)')
p.add_argument('--output', type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[1] / 'out' / 'language-server')
a = p.parse_args()

repo = pathlib.Path(__file__).resolve().parents[1]
sources = sorted((repo / 'tools/language-server').glob('*.n'))
out = a.output.resolve()
if out.exists(): shutil.rmtree(out)
out.mkdir(parents=True)
for f in a.toolchain.iterdir():
    if f.is_file() and f.suffix in {'.dll', '.exe', '.json', '.nitrametadata', '.nitrametadata2'}:
        shutil.copy2(f, out / f.name)
if a.nitra_compiler: shutil.copy2(a.nitra_compiler, out / 'Integrated.Nitra.Compiler.dll')
refs = ['Nemerle.Compiler.dll', 'Integrated.Nitra.Runtime.dll', 'Integrated.Nitra.Grammar.dll', 'Integrated.Nitra.Compiler.dll', 'Integrated.DotNetLang.dll']
# The server is written as file modules (server.n is module server) rooted at its directory.
command = ['dotnet', str(out / 'ncc.exe'), '-source-root:' + str(repo / 'tools/language-server'), *map(str, sources), '-target:exe', '-out:' + str(out / 'nemerle-lsp.exe'),
           '-target-references:' + str(a.references.resolve()), '-no-color'] + ['-r:' + str(out / r) for r in refs]
result = subprocess.run(command, capture_output=True, text=True)
sys.stdout.write(result.stdout + result.stderr)
if result.returncode: raise SystemExit(result.returncode)
shutil.copy2(out / 'ncc.runtimeconfig.json', out / 'nemerle-lsp.runtimeconfig.json')
launcher = out / 'nemerle-lsp'
launcher.write_text('#!/bin/sh\nexec dotnet "$(dirname "$0")/nemerle-lsp.exe" "$@"\n')
launcher.chmod(0o755)
print('Language server:', launcher)
