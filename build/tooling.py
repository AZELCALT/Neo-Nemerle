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
    sn = shutil.which('sn')
    if not sn:
        raise RuntimeError('Strong-name verification needs sn; on Windows run install\\install.cmd -Build to install prerequisites.')
    command = [sn]
    if pathlib.Path(sn).suffix.lower() in ('.bat', '.cmd'):
        # Mono on Windows exposes sn.bat. Invoke its managed tool explicitly, without cmd.exe quoting rules.
        managed = pathlib.Path(sn).parent.parent / 'lib/mono/4.5/sn.exe'
        mono = shutil.which('mono')
        if not mono or not managed.is_file():
            raise RuntimeError(f'The Mono strong-name launcher is incomplete: {sn}')
        command = [mono, str(managed)]
    subprocess.run([*command, '-vf', str(assembly)], check=True, stdout=subprocess.DEVNULL)


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
