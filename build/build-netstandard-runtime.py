#!/usr/bin/env python3
"""Build the runtime library (lib/Nemerle) for .NET Standard 2.0 into <toolchain>/netstandard2.0/Nemerle.dll.

    build/build-netstandard-runtime.py --toolchain DIR [--offline]

Programs and libraries for a target other than the compiler's own .NET (net8.0, netstandard2.x, net48, Mono, Unity)
run with this build of Nemerle.dll, which every target can load. Its identity (name, version, key) is the toolchain
Nemerle.dll's, so code compiled against one runs with the other. The .NET Standard reference assemblies come from
nuget.org (NETStandard.Library 2.0.3), downloaded once into the same cache `ncc build` uses. Without the network and
without the cache, the step is skipped: the toolchain then builds for its own .NET only, and says so.
"""
import argparse, io, os, pathlib, re, shutil, subprocess, sys, urllib.request, zipfile

p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
p.add_argument('--toolchain', type=pathlib.Path, required=True)
p.add_argument('--offline', action='store_true')
a = p.parse_args()
repo = pathlib.Path(__file__).resolve().parents[1]
tc = a.toolchain.resolve()

# the cache `ncc build` uses (Environment.SpecialFolder.LocalApplicationData)
data = os.environ.get('LOCALAPPDATA') if os.name == 'nt' else (os.environ.get('XDG_DATA_HOME') or str(pathlib.Path.home() / '.local/share'))
cache = pathlib.Path(data) / 'Nemerle/references/netstandard.library/2.0.3'
refs = cache / 'build/netstandard2.0/ref'
if not refs.is_dir():
    if a.offline:
        print('SKIP: no .NET Standard 2.0 reference assemblies in %s (offline)' % cache); sys.exit(0)
    feed = os.environ.get('NEMERLE_REFERENCE_FEED', 'https://api.nuget.org/v3-flatcontainer/').rstrip('/')
    url = feed + '/netstandard.library/2.0.3/netstandard.library.2.0.3.nupkg'
    try:
        data_bytes = pathlib.Path(url).read_bytes() if pathlib.Path(url).is_file() else urllib.request.urlopen(url, timeout=60).read()
    except Exception as error:
        print('SKIP: could not fetch the .NET Standard 2.0 reference assemblies (%s): %s' % (url, error)); sys.exit(0)
    pending = cache.with_name(cache.name + '.partial')
    shutil.rmtree(pending, ignore_errors=True)
    with zipfile.ZipFile(io.BytesIO(data_bytes)) as z: z.extractall(pending)
    shutil.rmtree(cache, ignore_errors=True)
    pending.rename(cache)

# the toolchain Nemerle.dll's version, so the two builds are one identity
version = subprocess.run(['dotnet', str(tc / 'ncc.exe'), '-version'],
                         capture_output=True, text=True).stderr
match = re.search(r'version (\d+\.\d+\.\d+\.\d+)', version)
if not match: sys.exit('cannot read the toolchain version: ' + version)
rows = [line.split() for line in subprocess.check_output(['dotnet', '--list-runtimes'], text=True).splitlines() if line.startswith('Microsoft.NETCore.App ')]
row = max(rows, key=lambda r: tuple(int(v) for v in r[1].split('.')))
runtime = pathlib.Path(row[2].strip('[]')) / row[1]
out = tc / 'netstandard2.0'
out.mkdir(exist_ok=True)
command = ['dotnet', str(tc / 'ncc.exe'), *map(str, sorted((repo / 'lib/Nemerle').rglob('*.n'))),
           '-out:' + str(out / 'Nemerle.dll'), '-define:NET_4_0', '-define:MODERN_CLR', '-define:NETSTANDARD2_0',
           '-target-references:' + str(refs), '-target-framework:netstandard2.0',
           '-keyfile:' + str(repo / 'misc/keys/Nemerle.snk'), '-no-color', '-target:library', '-no-stdlib',
           '-source-root:' + str(repo / 'lib'), '-assembly-version:' + match.group(1),
           '-no-stdmacros', '-macros:' + str(tc / 'Nemerle.Macros.dll'), '-nowarn:618',
           *['-r:' + str(runtime / n) for n in ('System.Xml.ReaderWriter.dll', 'System.Xml.XmlDocument.dll', 'System.Console.dll')]]
result = subprocess.run(command, capture_output=True, text=True)
if result.returncode: sys.exit(result.stdout + result.stderr)
for leftover in out.glob('_N_*'): leftover.unlink()
print('PASS: Nemerle.dll for .NET Standard 2.0 (%s), version %s' % (out / 'Nemerle.dll', match.group(1)))
