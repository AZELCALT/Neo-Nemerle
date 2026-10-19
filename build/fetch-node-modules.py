#!/usr/bin/env python3
"""Fetch the packages a package-lock.json pins into node_modules, without npm.

    build/fetch-node-modules.py LOCKFILE FOLDER

Each "node_modules/..." entry's tarball is downloaded from its "resolved" URL, checked against its "integrity" hash
(sha512), and unpacked (its top folder, "package/", removed) into FOLDER/node_modules/... . A download that does not
match its hash stops it. The editor extension's build and install/install.sh do the same.
"""
import base64, hashlib, io, json, pathlib, sys, tarfile, urllib.request

def fetch(lock, folder):
    packages = json.loads(pathlib.Path(lock).read_text())['packages']
    for path, entry in packages.items():
        if not path.startswith('node_modules/') or entry.get('dev') or entry.get('link'): continue
        url, integrity = entry['resolved'], entry.get('integrity', '')
        if not integrity.startswith('sha512-'): raise SystemExit('%s has no sha512 hash in %s' % (path, lock))
        data = urllib.request.urlopen(url, timeout=120).read()
        if base64.b64encode(hashlib.sha512(data).digest()).decode() != integrity[len('sha512-'):]:
            raise SystemExit('%s does not match its hash in %s' % (url, lock))
        target = pathlib.Path(folder) / path
        target.mkdir(parents=True, exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(data)) as tar:
            for member in tar.getmembers():
                name = member.name.split('/', 1)
                if len(name) < 2 or not (member.isfile() or member.isdir()): continue
                member.name = name[1]
                tar.extract(member, target, filter='data')

if __name__ == '__main__':
    if len(sys.argv) != 3: raise SystemExit(__doc__)
    fetch(sys.argv[1], sys.argv[2])
