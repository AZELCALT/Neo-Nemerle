#!/usr/bin/env python3
"""Build the whole toolchain from the pinned compiler in boot/coreclr and verify it.

    build/bootstrap.py [--quick] [--no-comparison] [--update-boot] [--output DIR] [--boot DIR] [--references DIR]

Steps (each logs to <output>/logs/<step>.log):
  1. platform: the C# platform adapter (platform/) from source, into a copy of boot
  2. compiler: that copy -> stage 1 -> stage 2 (runtime, compiler, macros, ncc), stage 2 checked by rebuilding itself
  3. nitra:    Nitra runtime/grammar/compiler built by the new compiler, native bootstrap = boot/coreclr
  4. tools:    scripting (nscript) and the language server
  5. tests:    every suite under tests/ (--quick: the fast ones only; --no-comparison: skip the 72-case differential)
With --update-boot, boot/coreclr is replaced by the result, but only when every step passed.
"""
import argparse, os, pathlib, re, shutil, subprocess, sys, time
from tooling import artifact_path

repo = pathlib.Path(__file__).resolve().parents[1]
build, tests = repo / 'build', repo / 'tests'


def default_references():
    """The newest Microsoft.NETCore.App.Ref pack next to the dotnet on PATH (falls back to boot/coreclr/references)."""
    dotnet = shutil.which('dotnet')
    if dotnet:
        packs = pathlib.Path(dotnet).resolve().parent / 'packs/Microsoft.NETCore.App.Ref'
        versions = sorted(packs.glob('10.*/ref/net10.0'), key=lambda p: [int(x) for x in re.findall(r'\d+', p.parent.parent.name)])
        if versions: return versions[-1]
    return repo / 'boot/coreclr/references'


p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
p.add_argument('--boot', type=pathlib.Path, default=repo / 'boot/coreclr', help='pinned toolchain to start from')
p.add_argument('--references', type=pathlib.Path, help='.NET 10 reference assemblies (default: the installed ref pack)')
p.add_argument('--output', type=pathlib.Path, default=repo / 'out/bootstrap', help='where the new toolchain goes')
p.add_argument('--quick', action='store_true', help='fast suites only (no Nitra suites, no differential)')
p.add_argument('--no-comparison', action='store_true', help='skip the Nitra differential (the slowest suite)')
p.add_argument('--update-boot', action='store_true', help='replace boot/coreclr with the result when everything passed')
p.add_argument('--build-only', action='store_true', help='build the toolchain and tools without running the test suites (installer performs smoke checks)')
a = p.parse_args()
if a.build_only and a.update_boot:
    p.error('--build-only cannot be combined with --update-boot; replacing the bootstrap requires the test suites')
boot = a.boot.resolve()
refs = (a.references or default_references()).resolve()
out = a.output.resolve()
toolchain, logs = out / 'toolchain', out / 'logs'
if out.exists(): shutil.rmtree(out)
logs.mkdir(parents=True)
print('boot:', boot, '\nreferences:', refs, '\noutput:', out, flush=True)
failures, scratch = [], []


def step(name, command, env=None, required=True):
    """Run one script; its log goes to logs/<name>.log. Returns the log text."""
    started = time.time()
    log = logs / (name + '.log')
    with open(log, 'w') as f:
        rc = subprocess.run([str(c) for c in command], cwd=repo, stdout=f, stderr=subprocess.STDOUT,
                            env=dict(os.environ, **(env or {}))).returncode
    text = log.read_text(errors='replace')
    scratch.extend(re.findall(r'/tmp/nemerle-[\w.-]+', text))
    passes = [l for l in text.splitlines() if l.startswith('PASS')]
    status = 'ok' if rc == 0 else 'FAILED'
    print('%-22s %-6s %5.0fs  %s' % (name, status, time.time() - started, (passes[-1][:90] if passes else '')), flush=True)
    if rc != 0:
        failures.append(name)
        print('   see', log, flush=True)
        if required: finish()
    return text


def finish():
    for path in set(scratch):
        path = pathlib.Path(path)
        while path.parent != pathlib.Path('/tmp'): path = path.parent
        shutil.rmtree(path, ignore_errors=True)
    if failures:
        print('\nFAILED:', ', '.join(failures)); sys.exit(1)
    if a.update_boot:
        target = repo / 'boot/coreclr'
        keep = [f for f in toolchain.iterdir()
                if f.name in ('references', 'netstandard2.0') or f.suffix in ('.dll', '.nitrametadata', '.nitrametadata2', '.exe', '.json', '.txt', '.rtf', '.png')
                or f.name in ('ncc', 'nscript')]
        keep = [f for f in keep if not f.name.endswith('-STATUS.json') and not f.name.startswith('_N_')]
        shutil.rmtree(target); target.mkdir()
        for f in keep:
            (shutil.copytree if f.is_dir() else shutil.copy2)(f, target / f.name)
        print('\nboot/coreclr updated from', toolchain)
    print('\n' + ('Build completed (test suites skipped). Toolchain:' if a.build_only else 'All steps passed. Toolchain:'), toolchain)
    sys.exit(0)


py = sys.executable
# 1. The CLR platform adapter (platform/*.cs, C#, independent of Nemerle) is built first into a copy of boot, so the
#    compiler stages compile against the platform API of this source tree.
seed = out / 'seed'
shutil.copytree(boot, seed)
step('platform', [py, build / 'build-coreclr-platform.py', '--toolchain', seed, '--references', refs])
# 2. compiler, two stages from the seed
text = step('compiler', [py, build / 'build-coreclr-toolchain.py', '--bootstrap', seed, '--references', refs])
stage2 = artifact_path(text, 'Verified CoreCLR source toolchain: ').parent
shutil.copytree(stage2, toolchain)
if not (toolchain / 'references').exists(): shutil.copytree(boot / 'references', toolchain / 'references')
# 3. Nitra, built by the new compiler; the previous Nitra compiler (boot) generates its grammars
text = step('nitra', [py, build / 'build-nitra-core.py', '--snapshot', 'Nitra', '--bootstrap', toolchain,
                      '--native-bootstrap', boot, '--references', refs])
nitra = artifact_path(text, 'Bootstrap artifacts (not an integrated grammar toolchain): ')
for f in nitra.glob('Integrated.*'): shutil.copy2(f, toolchain / f.name)
# 4. tools
shutil.copy2(repo / 'doc/assets/logo/nemerle-128.png', toolchain / 'nemerle-icon.png')  # the runtime package's icon
step('runtime-netstandard', [py, build / 'build-netstandard-runtime.py', '--toolchain', toolchain])
step('scripting-build', [py, build / 'build-scripting.py', '--toolchain', toolchain, '--references', toolchain / 'references'])
step('lsp-build', [py, build / 'build-language-server.py', '--toolchain', toolchain, '--references', refs, '--output', out / 'lsp'])
step('vscode-build', [py, build / 'build-vscode-extension.py', '--server', out / 'lsp', '--references', toolchain / 'references',
                      '--output', out])
# 5. tests (a failing suite is reported, the others still run)
T, R = toolchain, refs
suites = [
    ('file-modules', ['check-file-modules.py', T / 'ncc.exe', '--runtime', 'dotnet', '--target-references', R]),
    ('source-resolution', ['check-source-resolution.py', '--toolchain', T, '--references', R]),
    ('logical-modules', ['check-logical-modules.py', '--toolchain', T, '--references', R]),
    ('projects', ['check-projects.py', '--toolchain', T]),
    ('targets', ['check-targets.py', '--toolchain', T]),
    ('debugger', ['check-debugger.py', '--toolchain', T]),
    ('installers', ['check-installers.py']),
    ('build-tooling', ['check-build-tooling.py']),
    ('windows-install-policy', ['check-windows-install.py']),
    ('file-icons', ['check-file-icons.py']),
    ('runtime-only', ['check-runtime-only.py', '--compiler', T / 'ncc.exe', '--references', T / 'references']),
    ('grammar-regressions', ['check-grammar-regressions.py', '--toolchain', T, '--references', R]),
    ('indentation', ['check-indentation.py', '--toolchain', T, '--references', R]),
    ('scripting', ['check-scripting.py', '--toolchain', T, '--references', T / 'references']),
    ('script-imports', ['check-script-imports.py', '--toolchain', T, '--server', out / 'lsp/nemerle-lsp']),
    ('type-flow', ['check-type-flow.py', '--toolchain', T]),
    ('extend', ['check-extend.py', '--toolchain', T]),
    ('extensions', ['check-extensions.py', '--toolchain', T]),
    ('dynamic', ['check-dynamic.py', '--toolchain', T, '--references', R]),
    ('csharp-interop', ['check-csharp-interop.py', '--toolchain', T, '--references', R]),
    ('folder-modules', ['check-folder-modules.py', '--toolchain', T, '--references', R]),
    ('runtime-compilation', ['check-runtime-compilation.py', '--toolchain', T, '--references', T / 'references']),
    ('codedom', ['check-codedom.py', '--toolchain', T, '--references', R]),
    ('captured-delegate', ['check-captured-delegate.py', '--toolchain', T, '--references', R]),
    ('debug-resources', ['check-coreclr-debug-resources.py', '--toolchain', T, '--references', R]),
    ('coreclr-probe', ['probe-coreclr.py', '--compiler', T, '--support', T]),
    ('language-server', ['check-language-server.py', '--server', out / 'lsp/nemerle-lsp']),
    ('vscode-extension', ['check-vscode-extension.py', '--vsix', out / 'nemerle-0.2.0.vsix']),
]
if not a.quick:
    suites += [
        ('nitra-syntax', ['check-nitra-syntax.py', '--toolchain', T, '--references', R]),
        ('nitra-structures', ['check-nitra-structures.py', '--toolchain', T, '--references', R]),
        ('nitra-core', ['check-nitra-core.py', '--toolchain', T, '--references', R, '--native-core', T]),
        ('native-source', ['check-native-source.py', '--toolchain', T, '--references', R, '--native-core', T]),
        ('native-dialect', ['check-native-source.py', '--toolchain', T, '--references', R, '--native-core', T,
                            '--checks', 'NitraDialectChecks.cs']),
        ('native-output', ['check-native-output.py', '--toolchain', T, '--references', R, '--native-core', T]),
        ('scripting-nuget', ['check-scripting-nuget.py', '--toolchain', T, '--references', T / 'references']),
        ('script-kinds', ['check-script-kinds.py', '--toolchain', T, '--references', R]),
        ('continuation', ['check-continuation.py', '--toolchain', T, '--references', R]),
        ('book', ['check-book.py', '--toolchain', T, '--references', R]),
        ('script-book-usage', ['check-script-book-usage.py', '--toolchain', T]),
    ]
    if not a.no_comparison:
        suites.append(('nitra-comparison', ['check-nitra-comparison.py', '--toolchain', T, '--references', R,
                                            '--no-benchmarks', '--output', out / 'comparison.json']))
for name, command in ([] if a.build_only else suites):
    step(name, [py, tests / command[0], *command[1:]], env={'NITRA_VERIFY': '1'} if name == 'nitra-comparison' else None,
         required=False)
finish()
