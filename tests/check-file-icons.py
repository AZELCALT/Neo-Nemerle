#!/usr/bin/env python3
"""Check Linux file icons with an isolated MIME database, including removal."""
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

if not sys.platform.startswith('linux') or not shutil.which('update-mime-database'):
    print('SKIP: Linux with shared-mime-info is required')
    raise SystemExit(0)
repo = pathlib.Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='nemerle-file-icons-') as scratch:
    root = pathlib.Path(scratch)
    data = root / 'data'
    env = dict(os.environ, XDG_DATA_HOME=str(data))
    command = ['sh', str(repo / 'install/install-file-icons.sh'), '--data-dir', str(data)]
    for _ in range(2):
        subprocess.run(command, env=env, check=True, capture_output=True, text=True)
    for extension, mime, icon in [
        ('n', 'text/x-nemerle', 'text-x-nemerle'),
        ('ns', 'text/x-nemerle-script', 'text-x-nemerle-script'),
        ('nproj', 'application/x-nemerle-project', 'application-x-nemerle-project'),
    ]:
        sample = root / ('example.' + extension)
        sample.write_text('name = "example"\n')
        assert (data / 'icons/hicolor/scalable/mimetypes' / (icon + '.svg')).is_file()
        if shutil.which('gio'):
            result = subprocess.run(['gio', 'info', '-a', 'standard::content-type,standard::icon', str(sample)],
                                    env=env, check=True, capture_output=True, text=True)
            assert 'standard::content-type: ' + mime in result.stdout, result.stdout
            assert 'standard::icon: ' + icon in result.stdout, result.stdout
    untouched = data / 'icons/hicolor/scalable/mimetypes/unrelated.svg'
    untouched.write_text('keep this')
    for _ in range(2):
        subprocess.run(command + ['--uninstall'], env=env, check=True, capture_output=True, text=True)
    assert untouched.read_text() == 'keep this'
    assert not (data / 'mime/packages/neo-nemerle.xml').exists()
    assert sorted(p.name for p in untouched.parent.iterdir()) == ['unrelated.svg']
print('PASS: .n, .ns and .nproj MIME types and icons; repeat installation and removal preserve unrelated files')
