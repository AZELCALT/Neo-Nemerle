#!/usr/bin/env python3
"""Check prebuilt book tooling without downloading or executing foreign binaries."""
import hashlib
import importlib.util
import io
import pathlib
import tarfile
import tempfile
import unittest
import unittest.mock
import zipfile

spec = importlib.util.spec_from_file_location('book_build', pathlib.Path(__file__).resolve().parents[1] / 'build/build-book.py')
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


class BookBuildChecks(unittest.TestCase):
    def test_platforms(self):
        self.assertEqual(build.target_for('Windows', 'AMD64'), 'x86_64-pc-windows-msvc')
        self.assertEqual(build.target_for('Linux', 'aarch64'), 'aarch64-unknown-linux-musl')
        self.assertEqual(build.target_for('Darwin', 'arm64'), 'aarch64-apple-darwin')
        with self.assertRaisesRegex(RuntimeError, '--mdbook'):
            build.target_for('Windows', 'x86')

    def test_windows_zip_only_reads_executable(self):
        data = io.BytesIO()
        with zipfile.ZipFile(data, 'w') as archive:
            archive.writestr('mdbook.exe', b'MZ-test')
            archive.writestr('../outside.txt', b'not extracted')
        self.assertEqual(build.executable_bytes(data.getvalue(), 'x86_64-pc-windows-msvc'), b'MZ-test')

    def test_tar_rejects_executable_symlink(self):
        data = io.BytesIO()
        with tarfile.open(fileobj=data, mode='w:gz') as archive:
            entry = tarfile.TarInfo('mdbook')
            entry.type = tarfile.SYMTYPE
            entry.linkname = '../outside'
            archive.addfile(entry)
        with self.assertRaisesRegex(RuntimeError, 'regular'):
            build.executable_bytes(data.getvalue(), 'x86_64-unknown-linux-musl')

    def test_verified_offline_cache_and_tampering(self):
        target = 'x86_64-pc-windows-msvc'
        data = io.BytesIO()
        with zipfile.ZipFile(data, 'w') as archive:
            archive.writestr('mdbook.exe', b'MZ-test')
        payload = data.getvalue()
        with tempfile.TemporaryDirectory(prefix='nemerle book tools ') as folder:
            cache = pathlib.Path(folder) / build.VERSION / target
            cache.mkdir(parents=True)
            archive = cache / f'mdbook-v{build.VERSION}-{target}.zip'
            archive.write_bytes(payload)
            with unittest.mock.patch.dict(build.ASSETS, {target: hashlib.sha256(payload).hexdigest()}):
                with unittest.mock.patch.object(build.urllib.request, 'urlopen', side_effect=AssertionError('network used')):
                    binary = build.install_mdbook(folder, target, offline=True)
                    self.assertEqual(binary.read_bytes(), b'MZ-test')
                    binary.write_bytes(b'changed')
                    self.assertEqual(build.install_mdbook(folder, target, offline=True).read_bytes(), b'MZ-test')
                    archive.write_bytes(payload + b'changed')
                    with self.assertRaisesRegex(RuntimeError, 'SHA-256'):
                        build.install_mdbook(folder, target, offline=True)

    def test_offline_missing_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(RuntimeError, 'not cached'):
                build.install_mdbook(folder, 'x86_64-pc-windows-msvc', offline=True)


if __name__ == '__main__':
    unittest.main()
