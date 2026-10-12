#!/usr/bin/env python3
"""Run against installed Mono and CoreCLR without package restore or network access."""
import json
import pathlib
import subprocess
import tempfile

here = pathlib.Path(__file__).resolve().parent
sources = [here.parent / 'ClrCompilerSection.cs', here.parent / 'ClrResXReader.cs', here.parent / 'ClrAssemblyLoader.cs', here.parent / 'ClrAssemblySession.cs', here.parent / 'ClrSigning.cs', here.parent / 'ClrTargetReferences.cs', here.parent / 'ClrEmission.cs', here.parent / 'ClrMetadata.cs', here.parent / 'ClrAttributes.cs', here / 'EmissionChecks.cs']

def run(*args):
    print("Running:", args[0], flush=True)
    subprocess.run([str(arg) for arg in args], check=True, timeout=60)

with tempfile.TemporaryDirectory(prefix='nemerle-emission-') as folder:
    output = pathlib.Path(folder)
    cecil = sorted(pathlib.Path('/usr/lib/mono/gac/Mono.Cecil').glob('0.11*__*/Mono.Cecil.dll'))[-1]
    sdk_lines = subprocess.check_output(['dotnet', '--list-sdks'], text=True).splitlines()
    sdk_version, sdk_root = sdk_lines[-1].split(' ', 1)
    compiler = pathlib.Path(sdk_root.strip('[]')) / sdk_version / 'Roslyn/bincore/csc.dll'
    dotnet_root = pathlib.Path(sdk_root.strip('[]')).parent
    ref_versions = list((dotnet_root / 'packs/Microsoft.NETCore.App.Ref').iterdir())
    references = sorted(ref_versions, key=lambda p: tuple(int(x) for x in p.name.split('.')[:3]))[-1]
    tfm = 'net' + references.name.split('.')[0] + '.0'
    for driver in ('EmissionChecks', 'AttributeChecks', 'AssemblySessionChecks'):
        test_sources = sources[:-1] + [here.parent / 'MonoPersistence.cs', here.parent / 'ClrConstructorFactories.cs', here / (driver + '.cs')]
        mono = output / (driver + '.exe')
        run('mcs', '-r:' + str(cecil), '-out:' + str(mono), *test_sources)
        run('mono', mono, output, here.parent.parent / 'misc/keys/Nemerle.Compiler.snk')
        import shutil
        shutil.copy2(cecil, output / 'Mono.Cecil.dll')
        modern = output / (driver + '.dll')
        response = output / (driver + '.rsp')
        response.write_text('\n'.join(['-nologo', '-nostdlib+', '-define:MODERN_CLR', '-target:exe',
            '-out:"' + str(modern) + '"', '-r:"' + str(cecil) + '"'] +
            ['-r:"' + str(path) + '"' for path in sorted((references / 'ref' / tfm).glob('*.dll'))] +
            ['"' + str(path) + '"' for path in test_sources]))
        modern.with_suffix('.runtimeconfig.json').write_text(json.dumps({'runtimeOptions': {
            'tfm': tfm, 'framework': {'name': 'Microsoft.NETCore.App', 'version': references.name}}}))
        run('dotnet', compiler, '@' + str(response))
        run('dotnet', modern, output, here.parent.parent / 'misc/keys/Nemerle.Compiler.snk')
        if driver == 'AssemblySessionChecks': run('sn', '-vf', output / 'SignedSession.dll')
