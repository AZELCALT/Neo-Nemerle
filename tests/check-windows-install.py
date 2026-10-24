#!/usr/bin/env python3
"""Exercise PowerShell prerequisite policy and staged installation without touching real Windows packages/editors."""
import argparse
import os
import pathlib
import shutil
import subprocess
import tempfile

p = argparse.ArgumentParser()
p.add_argument('--pwsh', default=shutil.which('pwsh') or os.environ.get('PWSH') or (shutil.which('powershell') if os.name == 'nt' else None))
p.add_argument('--codedom-package', type=pathlib.Path, help='optional predownloaded official 10.0.0 package for repair checks')
a = p.parse_args()
if not a.pwsh:
    raise SystemExit('SKIP: PowerShell is unavailable; pass --pwsh to check Windows installer policy')
repo = pathlib.Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='nemerle windows install ') as directory:
    work = pathlib.Path(directory)
    command = [a.pwsh, '-NoProfile', '-File', str(repo / 'tests/WindowsInstallChecks.ps1'),
               '-Repository', str(repo), '-Work', str(work / 'policy')]
    if a.codedom_package:
        command += ['-CodeDomPackage', str(a.codedom_package.resolve())]
    subprocess.run(command, check=True, timeout=120)
    prefix = work / 'installed'
    try:
        result = subprocess.run([a.pwsh, '-NoProfile', '-File', str(repo / 'install/install.ps1'),
                                 '-Prefix', str(prefix), '-NoLsp', '-NoDebugger', '-Editor', 'none', '-NoDependencies'],
                                capture_output=True, text=True, timeout=120)
        assert result.returncode == 0, result.stdout + result.stderr
        assert 'compiler and scripting checks passed' in result.stdout, result.stdout
        assert not list(prefix.glob('.toolchain-*')), 'successful install left staging directories'

        # A corrupt incoming compiler must not destroy the previous toolchain or change its launchers.
        fake = work / 'broken checkout'
        (fake / 'install').mkdir(parents=True)
        for name in ('install.ps1', 'dependencies.ps1'):
            shutil.copy2(repo / 'install' / name, fake / 'install' / name)
        boot = fake / 'boot/coreclr'
        boot.mkdir(parents=True)
        for name in ('Nemerle.Compiler.dll', 'System.CodeDom.dll'):
            shutil.copy2(repo / 'boot/coreclr' / name, boot / name)
        (boot / 'ncc.exe').write_text('not a runnable compiler')
        old = (prefix / 'toolchain/ncc.exe').read_bytes()
        launchers = {path.name: path.read_bytes() for path in (prefix / 'bin').iterdir() if path.is_file()}
        result = subprocess.run([a.pwsh, '-NoProfile', '-File', str(fake / 'install/install.ps1'),
                                 '-Prefix', str(prefix), '-NoLsp', '-NoDebugger', '-Editor', 'none', '-NoDependencies'],
                                capture_output=True, text=True, timeout=120)
        assert result.returncode != 0, 'a corrupt toolchain was reported as installed'
        assert (prefix / 'toolchain/ncc.exe').read_bytes() == old, 'failed upgrade replaced the previous compiler'
        assert all((prefix / 'bin' / name).read_bytes() == data for name, data in launchers.items()), 'failed upgrade changed launchers'
        assert not list(prefix.glob('.toolchain-*')), 'failed install left staging directories'
    finally:
        if os.name == 'nt':
            # The real Windows installer writes user PATH. Remove only this scratch entry, preserving other edits.
            cleanup = work / 'cleanup-path.ps1'
            cleanup.write_text("param([string]$Bin)\n"
                               "$current = [Environment]::GetEnvironmentVariable('Path', 'User')\n"
                               "$parts = @($current -split ';' | Where-Object { $_ -and $_ -ne $Bin })\n"
                               "[Environment]::SetEnvironmentVariable('Path', ($parts -join ';'), 'User')\n")
            subprocess.run([a.pwsh, '-NoProfile', '-File', str(cleanup), str(prefix / 'bin')], check=True, timeout=30)
print('PASS: PowerShell install, paths with spaces, compiler/script smoke checks and preservation after a failed upgrade')
