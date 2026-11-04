#!/usr/bin/env python3
"""The fast loop while working on the toolchain: rebuild it once, with a base compiler, into out/dev/toolchain.

    ./dev [part ...] [--base DIR] [--output DIR]

Parts, in build order: runtime compiler macros cli nitra scripting lsp (default: all; a rebuilt compiler rebuilds the
macros, which are bound to it). Each is compiled once by the
base toolchain (out/bootstrap/toolchain when it is newer than boot/coreclr, else boot/coreclr), not in the two verified stages of
./bootstrap, and every compile goes through the build cache, so asking for all of them only costs the parts whose
inputs changed. The result runs as a toolchain (out/dev/toolchain/ncc, nscript; out/dev/lsp/nemerle-lsp). It is for
iterating, not a bootstrap: run ./bootstrap before committing a compiler change.
"""
import argparse, pathlib, re, shutil, subprocess, sys, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from tooling import artifact_path, net10_runtime, parallel_flag, tune_compiler_runtime, verify_strong_name
import buildcache

repo = pathlib.Path(__file__).resolve().parents[1]
PARTS = ['runtime', 'compiler', 'macros', 'cli', 'nitra', 'scripting', 'lsp']
p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
p.add_argument('parts', nargs='*', help='what to rebuild, from: ' + ' '.join(PARTS) + ' (default: all)')
p.add_argument('--base', type=pathlib.Path, help='toolchain that compiles (default: out/bootstrap/toolchain, else boot/coreclr)')
p.add_argument('--references', type=pathlib.Path, help='.NET reference assemblies (default: the base toolchain\'s)')
p.add_argument('--output', type=pathlib.Path, default=repo / 'out/dev')
a = p.parse_args()
parts = set(a.parts or PARTS)
if parts - set(PARTS): p.error('unknown part: ' + ' '.join(sorted(parts - set(PARTS))) + ' (parts: ' + ' '.join(PARTS) + ')')
def newest_base():
    # the last ./bootstrap result, unless boot/coreclr is newer (a stale out/bootstrap would build with an old compiler)
    built, boot = repo / 'out/bootstrap/toolchain', repo / 'boot/coreclr'
    if (built / 'ncc.exe').is_file() and (built / 'ncc.exe').stat().st_mtime >= (boot / 'ncc.exe').stat().st_mtime: return built
    return boot
base = (a.base or newest_base()).resolve()
refs = (a.references or base / 'references').resolve()
out = a.output.resolve()
runtime = net10_runtime()
T = out / 'toolchain'
logs = pathlib.Path(tempfile.mkdtemp(prefix='nemerle-dev-'))
# Afresh from the base each time: the cache makes the unchanged parts free, and nothing stale is left in T.
if T.exists(): shutil.rmtree(T)
shutil.copytree(base, T)
if not (T / 'references').exists(): shutil.copytree(refs, T / 'references')
print('base:', base, flush=True)

names = ['System.Linq', 'System.Collections.Specialized', 'System.ComponentModel.Primitives',
    'System.ComponentModel.TypeConverter', 'System.Diagnostics.Process', 'System.Diagnostics.TraceSource',
    'System.Xml.ReaderWriter', 'System.Xml.XmlDocument', 'System.Xml.XmlSerializer',
    'System.Security.Cryptography', 'System.Reflection.Emit', 'System.Reflection.Emit.ILGeneration',
    'System.Reflection.Primitives', 'System.Runtime.InteropServices']
def build(label, output, source_files, references, extra, keyname='Nemerle.Compiler.snk'):
    macros = ['-no-stdmacros', '-macros:' + str(base / 'Nemerle.Macros.dll')]
    cmd = ['dotnet', str(base / 'ncc.exe'), *map(str, source_files), '-out:' + str(output),
           '-define:NET_4_0', '-define:MODERN_CLR', '-target-references:' + str(refs),
           '-keyfile:' + str(repo / 'misc/keys' / keyname), '-no-color', *macros, *parallel_flag(base / 'ncc.exe'), *extra]
    cmd += ['-r:' + str(r) for r in references]
    log = logs / (label + '.log')
    code = buildcache.run(cmd, log, cwd=repo)
    if code:
        print(log.read_text(), flush=True); raise SystemExit(code)
    verify_strong_name(output)
    print('%-9s %s' % (label, 'reused' if 'build cache: reused' in log.read_text() else 'built'), flush=True)

def step(label, command):
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        print(result.stdout + result.stderr, flush=True); raise SystemExit(result.returncode)
    print('%-9s done' % label, flush=True)
    return result.stdout

if 'runtime' in parts:
    # the base runtime's version: the base compiler and front end, which stay, are bound to it
    reported = subprocess.run(['dotnet', str(base / 'ncc.exe'), '-version'], capture_output=True, text=True).stderr
    version = re.search(r'version (\d+\.\d+\.\d+\.\d+)', reported)
    if not version: raise SystemExit('cannot read the base toolchain version: ' + reported)
    build('runtime', T / 'Nemerle.dll', sorted((repo / 'lib/Nemerle').rglob('*.n')),
          [runtime / 'System.Xml.ReaderWriter.dll', runtime / 'System.Xml.XmlDocument.dll', runtime / 'System.Console.dll'],
          ['-target:library', '-no-stdlib', '-source-root:' + str(repo / 'lib'), '-assembly-version:' + version.group(1)],
          keyname='Nemerle.snk')
# (one stage: the compiler and its front end are built against the base runtime, which still runs them)
if 'compiler' in parts:
    build('compiler', T / 'Nemerle.Compiler.dll', sorted(repo.glob('ncc/Nemerle/Compiler/*.n')),
          [base / 'Nemerle.Platform.dll', base / 'System.CodeDom.dll'] + [runtime / (n + '.dll') for n in names],
          ['-target:library', '-no-stdlib', '-r:' + str(base / 'Nemerle.dll'), '-source-root:' + str(repo / 'ncc')])
# The standard macros run inside T's compiler, so they are built against it (after it): a macro library is bound to
# the compiler it was built against, and a rebuilt compiler needs its macros rebuilt.
if 'compiler' in parts: parts.add('macros')
if 'macros' in parts:
    build('macros', T / 'Nemerle.Macros.dll', sorted((repo / 'macros').rglob('*.n')),
          [T / 'Nemerle.Compiler.dll', T / 'Nemerle.Platform.dll',
           runtime / 'System.Data.Common.dll', runtime / 'System.Xml.ReaderWriter.dll',
           runtime / 'System.Xml.XmlSerializer.dll', runtime / 'System.Xml.XDocument.dll', runtime / 'System.Linq.dll'],
          ['-target:library', '-source-root:' + str(repo / 'macros')])
if 'cli' in parts:
    cli_refs = [T / 'Nemerle.Compiler.dll', T / 'Nemerle.Platform.dll', runtime / 'System.Console.dll',
        runtime / 'System.Linq.dll', runtime / 'System.Net.Http.dll', runtime / 'System.IO.Compression.dll',
        runtime / 'System.Text.Json.dll', runtime / 'System.Memory.dll', runtime / 'System.Reflection.Metadata.dll',
        runtime / 'System.Collections.Immutable.dll', runtime / 'System.IO.Compression.ZipFile.dll']
    build('cli', T / 'ncc.exe', [repo / 'ncc/Nemerle/CommandlineCompiler.n', repo / 'ncc/Nemerle/ProjectCommands.n'],
          cli_refs, ['-no-stdlib', '-r:' + str(base / 'Nemerle.dll'), '-source-root:' + str(repo / 'ncc')])
    tune_compiler_runtime(T)
py, b = sys.executable, repo / 'build'
if 'nitra' in parts:
    text = step('nitra', [py, b / 'build-nitra-core.py', '--snapshot', 'Nitra', '--bootstrap', T,
                          '--native-bootstrap', repo / 'boot/coreclr', '--references', refs])
    built = artifact_path(text, 'Bootstrap artifacts (not an integrated grammar toolchain): ')
    for f in built.glob('Integrated.*'): shutil.copy2(f, T / f.name)
    shutil.rmtree(built.parent, ignore_errors=True)
if 'scripting' in parts:
    step('scripting', [py, b / 'build-scripting.py', '--toolchain', T, '--references', T / 'references'])
if 'lsp' in parts:
    step('lsp', [py, b / 'build-language-server.py', '--toolchain', T, '--references', refs, '--output', out / 'lsp'])
shutil.rmtree(logs, ignore_errors=True)
print('Dev toolchain:', T, flush=True)
