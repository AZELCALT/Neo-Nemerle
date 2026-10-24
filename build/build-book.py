#!/usr/bin/env python3
"""Build the book using a pinned prebuilt mdBook; Python 3 is the only build prerequisite."""
import argparse
import hashlib
import io
import os
import pathlib
import platform
import subprocess
import tarfile
import tempfile
import urllib.error
import urllib.request
import zipfile

REPO = pathlib.Path(__file__).resolve().parents[1]
VERSION = '0.5.4'
RELEASE = f'https://github.com/rust-lang/mdBook/releases/download/v{VERSION}'
# SHA-256 digests published on the official v0.5.4 release assets.
ASSETS = {
    'aarch64-apple-darwin': '03e8a6d8b13a2971e0b3280affd03b388373c1485e26f73407c3a76b0b1838df',
    'aarch64-unknown-linux-musl': '753e5c5c363ee8a56972344dcf91466f005a51db84a7aeffe427ae3ef83d6d44',
    'x86_64-apple-darwin': 'a47d7bf0d5d670cff9ee6cce95537cbeb62dc10704d9e7131ffbd13e2b59a5de',
    'x86_64-pc-windows-msvc': '8a6b2421aa522de06d746871d2b8fff9c8d71773467e310a4516d2566e7f2de4',
    'x86_64-unknown-linux-musl': '5222beabd3e37dc5be0d18ff99b79058469354db5c220153a1b92db5ba12be89',
}


def target_for(system, machine):
    arch = {'amd64': 'x86_64', 'x86_64': 'x86_64', 'arm64': 'aarch64', 'aarch64': 'aarch64'}.get(machine.lower())
    suffix = {'Windows': 'pc-windows-msvc', 'Linux': 'unknown-linux-musl', 'Darwin': 'apple-darwin'}.get(system)
    target = f'{arch}-{suffix}'
    if target not in ASSETS:
        raise RuntimeError(f'No pinned mdBook binary for {system}/{machine}; provide one with --mdbook PATH.')
    return target


def executable_bytes(data, target):
    """Read just the expected executable; never extract arbitrary archive paths."""
    if 'windows' in target:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            return archive.read('mdbook.exe')
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
        entry = archive.getmember('mdbook')
        if not entry.isfile():
            raise RuntimeError('The mdBook archive does not contain a regular mdbook executable.')
        return archive.extractfile(entry).read()


def install_mdbook(tool_dir, target, offline=False):
    folder = pathlib.Path(tool_dir) / VERSION / target
    binary = folder / ('mdbook.exe' if 'windows' in target else 'mdbook')
    extension = '.zip' if 'windows' in target else '.tar.gz'
    asset = f'mdbook-v{VERSION}-{target}{extension}'
    archive = folder / asset
    if archive.is_file():
        data = archive.read_bytes()
    else:
        if offline:
            raise RuntimeError(f'mdBook is not cached at {folder}; run once online or provide --mdbook PATH.')
        print(f'Downloading mdBook {VERSION} for {target}', flush=True)
        request = urllib.request.Request(f'{RELEASE}/{asset}', headers={'User-Agent': 'Nemerle-book-build'})
        with urllib.request.urlopen(request, timeout=30) as response:
            data = response.read()
    if hashlib.sha256(data).hexdigest() != ASSETS[target]:
        raise RuntimeError(f'{asset} failed SHA-256 verification; remove {archive} and download it again.')
    content = executable_bytes(data, target)
    folder.mkdir(parents=True, exist_ok=True)
    # Replace complete files atomically; an interrupted download never becomes a usable cache entry.
    for path, payload in ((archive, data), (binary, content)):
        if path.is_file() and path.read_bytes() == payload:
            continue
        with tempfile.NamedTemporaryFile(dir=folder, delete=False) as stream:
            temporary = pathlib.Path(stream.name)
            stream.write(payload)
        try:
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
    if os.name != 'nt':
        binary.chmod(0o755)
    return binary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mdbook', type=pathlib.Path, help='use an existing mdbook executable instead of downloading')
    parser.add_argument('--offline', action='store_true', help='use cached tools without network access')
    parser.add_argument('--tool-dir', type=pathlib.Path, default=REPO / 'out/book-tools', help='prebuilt tool cache')
    parser.add_argument('--dest-dir', type=pathlib.Path, default=REPO / 'doc/book/book', help='HTML output directory')
    args = parser.parse_args()
    try:
        binary = args.mdbook.resolve() if args.mdbook else install_mdbook(
            args.tool_dir.resolve(), target_for(platform.system(), platform.machine()), args.offline)
        destination = args.dest_dir.resolve()
        subprocess.run([str(binary), 'build', str(REPO / 'doc/book'), '--dest-dir', str(destination)], check=True)
    except (OSError, RuntimeError, urllib.error.URLError, subprocess.CalledProcessError,
            KeyError, ValueError, tarfile.TarError, zipfile.BadZipFile) as error:
        parser.exit(1, f'Book build failed: {error}\n')
    print(f'Book: {destination / "index.html"}')


if __name__ == '__main__':
    main()
