"""Cross-platform subprocess commands for the Neo-Nemerle test toolchain.

The Unix `ncc` and `nscript` files are shell scripts, not Windows programs.
On Windows `ncc.exe` and `nscript.exe` are managed assemblies run by dotnet.
"""
import os
from pathlib import Path

WINDOWS = os.name == 'nt'


def ncc_command(toolchain, managed_output=True):
    toolchain = Path(toolchain)
    if not WINDOWS:
        return [str(toolchain / 'ncc')]
    command = ['dotnet', str(toolchain / 'ncc.exe'),
               '-target-references:' + str(toolchain / 'references')]
    # Programs intended for `dotnet main.exe`, not an apphost `main.exe`.
    # Project commands must keep their ordinary launcher semantics.
    if managed_output:
        command.append('-launcher-')
    return command


def nscript_command(toolchain):
    toolchain = Path(toolchain)
    return (['dotnet', str(toolchain / 'nscript.exe')] if WINDOWS
            else [str(toolchain / 'nscript')])


def lsp_command(path):
    path = Path(path)
    return ['dotnet', str(path.with_suffix('.exe'))] if WINDOWS else [str(path)]
