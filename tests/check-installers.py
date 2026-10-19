#!/usr/bin/env python3
"""Run the installers into scratch folders and check what they leave: the commands, and the editor extension.

Usage: check-installers.py

install/install.sh (and install/install.ps1 when PowerShell 7 is on PATH) install the pinned toolchain into a temporary
prefix with --editor none, and the .vsix each writes next to itself must pass tests/check-vscode-extension.py. The
editor step runs against a stand-in editor command that records how it is called (no real editor is touched)."""
import os, pathlib, shutil, subprocess, sys, tempfile, zipfile

repo = pathlib.Path(__file__).resolve().parents[1]
work = pathlib.Path(tempfile.mkdtemp(prefix='nemerle-installers-'))
vsix = repo / 'install/nemerle-0.2.0.vsix'
checks = 0

def check(ok, message):
    global checks
    if not ok: raise SystemExit('FAIL: ' + message)
    checks += 1

def installed(prefix, launcher):
    hello = work / 'hello.n'; hello.write_text('System.Console.WriteLine("hello from the installed nscript")\n')
    r = subprocess.run([str(prefix / 'bin' / launcher), 'run', str(hello), '--no-cache'], capture_output=True, text=True)
    return 'hello from the installed nscript' in r.stdout

def extension_check():
    r = subprocess.run([sys.executable, str(repo / 'tests/check-vscode-extension.py'), '--vsix', str(vsix)], capture_output=True, text=True)
    return r.returncode == 0, r.stdout + r.stderr

try:
    # install.sh
    prefix = work / 'unix'
    vsix.unlink(missing_ok=True)
    # the extension's dependencies come from the registry without npm: an npm on PATH that only records being called
    nonpm = work / 'nonpm'; nonpm.mkdir()
    (nonpm / 'npm').write_text('#!/bin/sh\necho called >> "%s/npm-called"\nexit 1\n' % work); (nonpm / 'npm').chmod(0o755)
    r = subprocess.run(['sh', str(repo / 'install/install.sh'), '--prefix', str(prefix), '--bin', str(prefix / 'bin'), '--editor', 'none'],
                       capture_output=True, text=True, env=dict(os.environ, PATH=str(nonpm) + os.pathsep + os.environ['PATH']))
    check(r.returncode == 0, 'install.sh: ' + r.stdout + r.stderr)
    offline = 'could not be fetched' in r.stdout + r.stderr
    if offline: print('SKIP: the npm-free dependencies (the registry cannot be reached)', flush=True)
    else:
        check(not (work / 'npm-called').exists(), 'install.sh fetches the extension\'s dependencies without npm: ' + r.stderr)
        with zipfile.ZipFile(vsix) as z:
            names = z.namelist()
        check('extension/node_modules/vscode-languageclient/node.js' in names and 'extension/node_modules/semver/package.json' in names,
              'the .vsix carries the dependencies the lock file pins')
    summary = r.stdout[r.stdout.find('Summary:'):]
    check('Summary:' in r.stdout and 'installed  the toolchain' in summary and 'skipped    installing the extension in an editor: --editor none' in summary,
          'install.sh ends with what it installed and skipped: ' + summary)
    check(installed(prefix, 'nscript'), 'the commands install.sh installed run')
    check(vsix.exists(), 'install.sh writes ' + str(vsix))
    # the debugger it fetched (skipped, and said so, without the network)
    netcoredbg = prefix / 'tools/netcoredbg/netcoredbg/netcoredbg'
    if 'Skipping the debugger' in r.stdout:
        print('SKIP: the debugger download (%s)' % [l for l in r.stdout.splitlines() if 'Skipping the debugger' in l][0], flush=True)
    else:
        v = subprocess.run([str(netcoredbg), '--version'], capture_output=True, text=True)
        check('NET Core debugger' in v.stdout, 'the fetched netcoredbg runs: ' + v.stdout + v.stderr)
    # the extension finds a debugger where the installers put it (their default prefix)
    xdg = work / 'xdg'; found = xdg / 'nemerle/tools/netcoredbg/netcoredbg/netcoredbg'
    found.parent.mkdir(parents=True); found.write_text('#!/bin/sh\n'); found.chmod(0o755)
    harness = work / 'find.js'
    harness.write_text('''
const Module = require('module'); const original = Module._load;
Module._load = function (request) {
  if (request === 'vscode-languageclient/node') return { LanguageClient: class {} };
  if (request === 'vscode') return { workspace: { getConfiguration: () => ({ get: () => undefined }) }, window: {}, env: {}, Uri: {} };
  return original.apply(this, arguments);
};
console.log(require(process.argv[2])._test.debuggerPath({ get: () => undefined }) || '');
''')
    out = subprocess.run(['node', str(harness), str(repo / 'tools/language-server/vscode/extension.js')], capture_output=True, text=True,
                         env=dict(os.environ, XDG_DATA_HOME=str(xdg), PATH='/usr/bin:/bin')).stdout.strip()
    check(out == str(found), 'the extension finds the installed debugger: %r' % out)
    ok, out = extension_check()
    check(ok, 'the .vsix of install.sh: ' + out)
    # the editor step: the editor's own --install-extension, after the old copied-in folder is removed
    fake = work / 'editor'; (fake / 'bin').mkdir(parents=True)
    old = fake / 'home/.vscode-oss/extensions/neo-nemerle.nemerle-0.2.0'; old.mkdir(parents=True)
    (fake / 'bin/codium').write_text('#!/bin/sh\necho "$@" > "%s/called.txt"\n' % fake); (fake / 'bin/codium').chmod(0o755)
    env = dict(os.environ, HOME=str(fake / 'home'), PATH=str(fake / 'bin') + os.pathsep + os.environ['PATH'])
    r = subprocess.run(['sh', str(repo / 'install/install.sh'), '--prefix', str(prefix), '--bin', str(prefix / 'bin'), '--editor', 'codium'],
                       capture_output=True, text=True, env=env)
    called = (fake / 'called.txt').read_text().split() if (fake / 'called.txt').exists() else []
    check(r.returncode == 0 and called[:1] == ['--install-extension'] and called[-1] == '--force' and not old.exists(),
          'install.sh installs the .vsix through the editor: %s %s' % (called, r.stdout[-500:]))
    print('PASS: install.sh installs the commands and writes a working .vsix, which the editor\'s own command installs', flush=True)
    # install.ps1, under PowerShell 7 where it is available
    pwsh = shutil.which('pwsh') or os.environ.get('PWSH')
    if pwsh:
        prefix = work / 'ps'
        vsix.unlink(missing_ok=True)
        (work / 'npm-called').unlink(missing_ok=True)
        r = subprocess.run([pwsh, '-NoProfile', '-File', str(repo / 'install/install.ps1'), '-Prefix', str(prefix), '-Editor', 'none'],
                           capture_output=True, text=True, env=dict(os.environ, PATH=str(nonpm) + os.pathsep + os.environ['PATH']))
        check(r.returncode == 0, 'install.ps1: ' + r.stdout + r.stderr)
        if 'could not be fetched' not in r.stdout:
            check(not (work / 'npm-called').exists(), 'install.ps1 fetches the extension\'s dependencies without npm: ' + r.stdout)
            with zipfile.ZipFile(vsix) as z:
                check('extension/node_modules/vscode-languageclient/node.js' in z.namelist(), 'the .vsix of install.ps1 carries the dependencies')
        summary = r.stdout[r.stdout.find('Summary:'):]
        check('installed  the toolchain' in summary and 'skipped    installing the extension in an editor: -Editor none' in summary,
              'install.ps1 ends with what it installed and skipped: ' + summary)
        check(installed(prefix, 'nscript'), 'the commands install.ps1 installed run')
        if 'Skipping the debugger' not in r.stdout:
            v = subprocess.run([str(prefix / 'tools/netcoredbg/netcoredbg/netcoredbg'), '--version'], capture_output=True, text=True)
            check('NET Core debugger' in v.stdout, 'the netcoredbg install.ps1 fetched runs: ' + v.stdout + v.stderr)
        ok, out = extension_check()
        check(ok, 'the .vsix of install.ps1: ' + out)
        print('PASS: install.ps1 (PowerShell 7) installs the commands and writes a working .vsix', flush=True)
    else:
        print('SKIP: install.ps1 (no pwsh on PATH; set PWSH to run it)', flush=True)
    print('PASS: %d installer checks' % checks)
finally:
    shutil.rmtree(work, ignore_errors=True)
