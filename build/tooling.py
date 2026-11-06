"""Small cross-platform helpers shared by source-build steps."""
import pathlib
import re
import shutil
import subprocess


def net10_runtime(output=None):
    """Use the target runtime's implementation assemblies, even when a newer SDK/runtime is also installed."""
    if output is None:
        output = subprocess.check_output(['dotnet', '--list-runtimes'], text=True)
    rows = [match.groups() for line in output.splitlines()
            if (match := re.fullmatch(r'Microsoft\.NETCore\.App (10\.\d+\.\d+) \[(.+)\]', line))]
    if not rows:
        raise RuntimeError('The .NET 10 runtime is required; on Windows run install\\install.cmd -Build.')
    version, folder = max(rows, key=lambda row: tuple(map(int, row[0].split('.'))))
    return pathlib.Path(folder) / version


def net10_csc(output=None):
    if output is None:
        output = subprocess.check_output(['dotnet', '--list-sdks'], text=True)
    rows = [match.groups() for line in output.splitlines()
            if (match := re.fullmatch(r'(10\.\d+\.\d+) \[(.+)\]', line))]
    if not rows:
        raise RuntimeError('The .NET 10 SDK is required; on Windows run install\\install.cmd -Build.')
    version, folder = max(rows, key=lambda row: tuple(map(int, row[0].split('.'))))
    return pathlib.Path(folder) / version / 'Roslyn/bincore/csc.dll'


def verify_strong_name(assembly):
    # The adjacent verifier reads the assembly's own public key and checks its RSA
    # strong-name signature. No Mono, Windows SDK, or external executable needed.
    from strong_name import verify_strong_name as verify
    verify(assembly)


def tune_compiler_runtime(folder):
    """Give the compiler's runtimeconfig the runtime settings that suit it: a short run that allocates a lot, through
    much branchy code. Without tiered PGO and with server GC on two heaps, compiling Nemerle.Compiler.dll takes 20 s,
    not 26 s (peak 1.06 GB, not 0.83 GB). ncc.runtimeconfig.json is the generic one the compiler writes for a program."""
    import json
    config = pathlib.Path(folder) / 'ncc.runtimeconfig.json'
    data = json.loads(config.read_text())
    data['runtimeOptions']['configProperties'] = {
        'System.Runtime.TieredPGO': False, 'System.GC.Server': True, 'System.GC.HeapCount': 2}
    config.write_text(json.dumps(data))


def cleanup_generated_items(folder):
    """Remove compiler-generated _N_* files and directories, not other outputs."""
    for item in pathlib.Path(folder).glob('_N_*'):
        if item.is_dir() and not item.is_symlink():
            shutil.rmtree(item)
        else:
            item.unlink()


_parallel = {}
def parallel_flag(ncc_exe):
    """['-parallel'] when the compiler at ncc_exe types method bodies in parallel (any built from this tree; the pinned
    boot compiler may predate it), else []. Its output is the same as without it, its made-up names aside."""
    key = str(pathlib.Path(ncc_exe).resolve())
    if key not in _parallel:
        shown = subprocess.run(['dotnet', key, '-help'], capture_output=True, text=True).stdout
        _parallel[key] = ['-parallel'] if '-parallel' in shown else []
    return _parallel[key]


def artifact_path(log, marker):
    """Read an explicit build marker, preserving spaces and Windows drive letters/separators."""
    paths = [line[len(marker):].strip() for line in log.splitlines() if line.startswith(marker)]
    if not paths:
        raise RuntimeError(f'The build did not report {marker.strip()}')
    return pathlib.Path(paths[-1])


def _retry_readonly_removal(function, path, error):
    """Retry only when a read-only file caused the removal failure."""
    import os
    import stat
    if not isinstance(error, PermissionError) or os.path.islink(path):
        raise error
    mode = os.stat(path).st_mode
    if mode & stat.S_IWRITE:
        raise error   # ACL denial or open handle: not a read-only attribute
    os.chmod(path, mode | stat.S_IWRITE)
    function(path)


def remove_readonly_tree(folder):
    """Remove a disposable build tree, including read-only generated source."""
    import sys
    if sys.version_info >= (3, 12):
        shutil.rmtree(folder, onexc=_retry_readonly_removal)
    else:
        shutil.rmtree(folder, onerror=lambda fn, name, info:
                      _retry_readonly_removal(fn, name, info[1]))


def cleanup_generated_items_readonly(folder):
    """Best-effort remove only compiler-generated _N_* artifacts.

    These are disposable generated sources, not compiler or build outputs.
    Windows ReadOnly metadata and an open file handle can prevent unlinking.
    A failure to remove a disposable artifact must not fail a successful
    .NET Standard build. Do not apply this policy to removing build trees.
    """
    # NEMERLE-GENERATED-CLEANUP: v2
    import os
    import stat
    for item in pathlib.Path(folder).glob('_N_*'):
        try:
            if item.is_dir() and not item.is_symlink():
                remove_readonly_tree(item)
                continue
            if not item.is_symlink():
                # Windows os.chmod clears FILE_ATTRIBUTE_READONLY; don't infer
                # that the file is writable from st_mode alone.
                try:
                    item.chmod(item.stat().st_mode | stat.S_IWRITE)
                except PermissionError:
                    # Unlink may still work even if changing attributes failed.
                    pass
            item.unlink()
        except FileNotFoundError:
            # Parallel generator/cleanup or a previous run removed it.
            pass
        except PermissionError as exc:
            # Deleting _N_* is only housekeeping. Do not weaken build failure
            # handling or silently pretend the file was removed.
            code = getattr(exc, 'winerror', None) or exc.errno
            print('WARNING: generated artifact could not be removed '
                  '(permission/sharing conflict; not needed for build): '
                  f'{item} [error {code}]. Keeping it.', flush=True)
