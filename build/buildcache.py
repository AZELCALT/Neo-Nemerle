"""Reuse a compile whose inputs did not change.

A compile (one `dotnet .../ncc.exe ...' command) is keyed by the hash of everything it reads: the compiler folder it
runs from, every file named on its command line (sources, -r:, -macros:, -keyfile:), every .n file under its
-source-root (a file module can pull in its neighbours), the reference pack, the .NET runtime and the other
arguments. Paths are keyed by content, not by name, so a build in a fresh temporary folder still finds its earlier
result. On a hit the files the compile wrote next to its -out: are restored and its log is replayed.

The compiler does not write the same bytes twice (a module's id is new each time), so a file a cached compile wrote
is keyed by the key that wrote it, not by its bytes: a compile reading it is then reused whenever what made it was.

NEMERLE_BUILD_CACHE=off disables it; NEMERLE_BUILD_CACHE=DIR moves it (default ~/.cache/nemerle/build).
"""
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import time

LIMIT = 4 << 30   # bytes kept; the oldest entries go first
_file_hashes = {}
_env_key = None


def root():
    setting = os.environ.get('NEMERLE_BUILD_CACHE', '')
    if setting.lower() in ('off', '0', 'no'): return None
    return pathlib.Path(setting) if setting else pathlib.Path.home() / '.cache/nemerle/build'


def produced(cache, digest):
    """The key and name a cached compile wrote this content under, or None."""
    mark = cache / 'produced' / digest
    return mark.read_text() if mark.is_file() else None


def ident(path):
    """What a file stands for in a key: the compile that wrote it, else its content."""
    digest = file_hash(path)
    cache = root()
    return (cache and produced(cache, digest)) or digest


def file_hash(path):
    stat = path.stat()
    known = _file_hashes.get(path)
    if known and known[0] == (stat.st_mtime_ns, stat.st_size): return known[1]
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    _file_hashes[path] = ((stat.st_mtime_ns, stat.st_size), digest)
    return digest


def folder_hash(folder, pattern, skip=()):
    h = hashlib.sha256()
    for path in sorted(folder.rglob(pattern)):
        if path.is_file() and path.resolve() not in skip: h.update(str(path.relative_to(folder)).encode() + b'\0' + ident(path).encode() + b'\n')
    return h.hexdigest()


def environment():
    global _env_key
    if _env_key is None:
        _env_key = subprocess.run(['dotnet', '--list-runtimes'], capture_output=True, text=True).stdout
    return _env_key


def key(command):
    h = hashlib.sha256(environment().encode())
    # (a compile writing into its compiler's own folder: what it writes is not one of its inputs)
    out = [pathlib.Path(arg[5:]).resolve() for arg in command if arg.startswith('-out:')]
    parts = []
    for arg in command:
        prefix, value = '', arg
        if arg.startswith('-') and ':' in arg: prefix, value = arg.split(':', 1); prefix += ':'
        path = pathlib.Path(value)
        if prefix == '-out:':
            part = prefix + path.name
        elif path.is_file():
            part = prefix + 'file ' + ident(path)
            # the compiler: everything beside ncc.exe is loaded with it (runtime, compiler, macros, platform)
            if path.name == 'ncc.exe':
                part += ' ' + folder_hash(path.parent, '*.dll', out) + folder_hash(path.parent, '*.json', out)
        elif path.is_dir():
            part = prefix + 'dir ' + (folder_hash(path, '*.n') if prefix == '-source-root:' else folder_hash(path, '*.dll'))
        else:
            part = arg
        h.update(part.encode() + b'\n')
        parts.append(part)
    digest = h.hexdigest()
    debug = os.environ.get('NEMERLE_BUILD_CACHE_DEBUG')   # (a file to append each key's parts to)
    if debug:
        with open(debug, 'a') as stream: stream.write(json.dumps({'key': digest, 'parts': parts}) + '\n')
    return digest


def output_folder(command):
    for arg in command:
        if arg.startswith('-out:'): return pathlib.Path(arg[5:]).parent
    return None


def snapshot(folder):
    if folder is None or not folder.is_dir(): return {}
    return {p.name: (p.stat().st_mtime_ns, p.stat().st_size) for p in folder.iterdir() if p.is_file()}


def run(command, log, cwd=None):
    """Run a compile, or replay it; returns the exit code. The log is written either way."""
    cache = root()
    folder = output_folder(command)
    if cache is None or folder is None:
        with log.open('w') as stream:
            return subprocess.run(command, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT).returncode
    entry = cache / key(command)
    manifest = entry / 'manifest.json'
    if manifest.is_file():
        files = json.loads(manifest.read_text())['files']
        folder.mkdir(parents=True, exist_ok=True)
        for name in files:
            target = folder / name
            if target.exists(): target.chmod(0o644)
            shutil.copy2(entry / 'files' / name, target)
        shutil.copy2(entry / 'log', log)
        with log.open('a') as stream: stream.write('\n(build cache: reused ' + entry.name[:12] + ')\n')
        os.utime(entry)
        return 0
    before = snapshot(folder)
    with log.open('w') as stream:
        code = subprocess.run(command, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT).returncode
    if code == 0:
        written = [name for name, state in snapshot(folder).items() if before.get(name) != state]
        staging = cache / (entry.name + '.tmp' + str(os.getpid()))
        shutil.rmtree(staging, ignore_errors=True)
        (staging / 'files').mkdir(parents=True)
        for name in written: shutil.copy2(folder / name, staging / 'files' / name)
        shutil.copy2(log, staging / 'log')
        (staging / 'manifest.json').write_text(json.dumps({'files': written, 'made': time.time()}))
        marks = cache / 'produced'; marks.mkdir(parents=True, exist_ok=True)
        # (only the binaries it emits, whose bytes differ run to run; a text file it writes may equal an input's)
        for name in written:
            mark = marks / file_hash(folder / name)
            if pathlib.Path(name).suffix in ('.dll', '.exe', '.pdb') and not mark.exists():
                mark.write_text(entry.name + '/' + name)
        try: staging.rename(entry)
        except OSError: shutil.rmtree(staging, ignore_errors=True)   # (another build stored it first)
        prune(cache)
    return code


def prune(cache):
    entries = [e for e in cache.iterdir() if e.is_dir() and (e / 'manifest.json').is_file()]
    sized = [(e.stat().st_mtime, sum(f.stat().st_size for f in e.rglob('*') if f.is_file()), e) for e in entries]
    total = sum(size for _, size, _ in sized)
    for _, size, e in sorted(sized):
        if total <= LIMIT: break
        shutil.rmtree(e, ignore_errors=True); total -= size
