#!/usr/bin/env python3
"""Rebuild upstream Nitra bootstrap sources with the modern Nemerle compiler.

The old Nitra parser is used ONLY to bootstrap its generated support sources.
This does not activate it in grammar/space hosting or install these assemblies.
"""
import argparse
import hashlib
import json
import pathlib
import shutil
import subprocess
from tooling import net10_csc, net10_runtime
import tempfile
import xml.etree.ElementTree as ET

def patch_reference(label, path):
    """The isolated-copy patches the pinned Boot2 reference snapshot still needs (the Nitra snapshot has them folded in)."""
    def overlay(name, text):
        patched = work / name; patched.write_text(text); return patched
    if label == 'compiler' and path.name == 'DefineMembers-ChemicalNode.n':
        addition = here / 'nitra-reference-chemical.n.inc'
        text = path.read_text(encoding='utf-8-sig')
        anchor = '      _nodeTb.DefineConditional(<[ decl:\n        [Nemerle.Diagnostics.CompileStatistic("ParseTree")]'
        if text.count(anchor) != 1: raise ValueError('Chemical constructor generator changed; review integration patch')
        path = overlay('DefineMembers-ChemicalNode.n', text.replace(anchor, addition.read_text() + anchor))
    if path.name == 'CompositeGrammar.n':
        text = path.read_text(encoding='utf-8-sig')
        old = 'Debug.Assert(content.Parent != null);'
        if old not in text: raise ValueError('Upstream CompositeGrammar assertion changed; review the port')
        path = overlay('CompositeGrammar.n', text.replace(old, 'Debug.Assert(content.Parent != null, "Missing content parent");'))
    if label == 'grammar' and path.name == 'AssemblyInfo.n':
        text = path.read_text(encoding='utf-8-sig')
        path = overlay('GrammarAssemblyInfo.n', '\n'.join(line for line in text.splitlines()
                       if '[assembly: Nemerle.Macro.Resource(' not in line and '[assembly: Nemerle.Macro.Settings(' not in line))
    return path


p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--bootstrap', type=pathlib.Path, required=True)
p.add_argument('--references', type=pathlib.Path, required=True)
p.add_argument('--nitra-source', type=pathlib.Path)
p.add_argument('--through', choices=['runtime', 'dotnet', 'grammar', 'compiler'], default='compiler')
p.add_argument('--snapshot', choices=['Boot2', 'Nitra'], default='Boot2')
p.add_argument('--target-runtime', type=pathlib.Path,
               help='Compile against this directory\'s Nemerle.dll and Nemerle.Compiler.dll instead of the host\'s '
                    '(bootstrapping onto a runtime whose types moved; the host still runs the previous Nitra macros)')
p.add_argument('--prebuilt-deps', type=pathlib.Path,
               help='Take Nitra.Runtime, DotNetLang and Nitra.Grammar from this directory (same prefix) and build only the '
                    'compiler stage: re-seeds the Nitra compiler after a change of the standard macros\' paths')
p.add_argument('--assembly-version',
               help='Version of the built Nitra assemblies (a bootstrap pass whose output must not be taken for the '
                    'previous build its macros run with)')
p.add_argument('--native-bootstrap', type=pathlib.Path,
               help='Previously source-built Nitra output; required for the current Nitra snapshot')
a = p.parse_args()
here = pathlib.Path(__file__).resolve().parent
repo = here.parent
# The pinned upstream Nitra reference (Boot2 builds only) is not part of this repository: --nitra-source DIR.
workspace = repo.parent
source = (a.nitra_source or (repo / 'native-nitra/upstream'
          if a.snapshot == 'Nitra' else workspace / 'nitra-reference')).resolve()
work = pathlib.Path(tempfile.mkdtemp(prefix='nemerle-nitra-core-'))
host = work / 'host'
host.mkdir()
output = work / 'output'
output.mkdir()
print('Nitra bootstrap build:', work, flush=True)
for path in a.bootstrap.resolve().iterdir():
    if path.is_file() and path.suffix in {'.dll', '.exe', '.json', '.config', '.pdb', '.nitrametadata'}:
        shutil.copy2(path, host / path.name)
if a.snapshot == 'Nitra' and a.native_bootstrap is None:
    p.error('--snapshot Nitra requires --native-bootstrap from a successful Boot2 build')
if a.native_bootstrap:
    # Only the Nitra assemblies: a full toolchain (boot/coreclr) also holds an older compiler and runtime.
    for path in a.native_bootstrap.resolve().iterdir():
        if path.is_file() and path.suffix in {'.dll', '.nitrametadata'} and path.name.startswith(('Integrated.', 'Nitra.', 'Boot.')):
            target = host / path.name
            if target.exists(): target.chmod(0o644)
            shutil.copy2(path, target)
else:
    for name in ['Boot.Nitra.Runtime.dll', 'Boot.DotNetLang.dll', 'Nitra.Grammar.dll', 'Nitra.Compiler.dll']:
        shutil.copy2(source / 'Boot1/Net-4.0' / name, host / name)
native_compiler = host / 'Nitra.Compiler.dll'
if not native_compiler.is_file():
    native_compiler = host / 'Integrated.Nitra.Compiler.dll'
if not native_compiler.is_file():
    raise FileNotFoundError('Native bootstrap is missing its Nitra compiler')
prefix = 'Integrated.' if a.snapshot == 'Nitra' else ''
runtime = net10_runtime()
references = ['System.Collections.Immutable', 'System.Xml.XDocument', 'System.Xml.ReaderWriter',
              'System.Xml.XmlDocument', 'System.Linq', 'System.Threading.Thread', 'System.Drawing.Primitives']
report = {'full_integration_complete': False, 'bootstrap_only': True, 'stages': [],
          'source_hashes': {}, 'work': str(work), 'snapshot': a.snapshot}
try:
    manifest = source / 'NITRA-UPSTREAM.json'
    report['upstream_commit'] = (json.loads(manifest.read_text())['commit'] if manifest.is_file()
        else subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip())
except subprocess.CalledProcessError:
    report['upstream_commit'] = None
stages = [('runtime', 'Nitra.Runtime', []), ('dotnet', 'DotNetLang', ['Nitra.Runtime']),
          ('grammar', 'Nitra.Grammar', ['Nitra.Runtime', 'DotNetLang']),
          ('compiler', 'Nitra.Compiler', ['Nitra.Runtime', 'DotNetLang', 'Nitra.Grammar'])]
for label, name, dependencies in stages:
    if a.prebuilt_deps and label != 'compiler':
        for path in a.prebuilt_deps.resolve().glob(prefix + name + '*'):
            shutil.copy2(path, output / path.name)
        print('PREBUILT:', label, flush=True)
        continue
    project = source / a.snapshot / name / (name + '.nproj')
    sources = []
    csharp = []
    for item in ET.parse(project).getroot().findall('.//{http://schemas.microsoft.com/developer/msbuild/2003}Compile'):
        include = item.attrib['Include'].replace('\\', '/').replace('$(CommonFilesPath)', '../../Common')
        path = (project.parent / include).resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        report['source_hashes'][str(path.relative_to(source))] = hashlib.sha256(path.read_bytes()).hexdigest()
        # The Nitra snapshot is file modules (one file per namespace) with our integration folded in
        # (build/migrations/migrate-nitra.py); only the pinned Boot2 reference snapshot is still patched here.
        if a.snapshot != 'Nitra':
            path = patch_reference(label, path)
        (csharp if path.suffix == '.cs' else sources).append(str(path))
    layout = ['-source-root:' + str(project.parent)] if a.snapshot == 'Nitra' else []
    command = ['dotnet', str(host / 'ncc.exe'), *layout, *sources, '-out:' + str(output / (prefix + name + '.dll')),
               '-target:library', '-define:BOOT', '-target-references:' + str(a.references.resolve()),
               '-no-color'] + (['-assembly-version:' + a.assembly_version] if a.assembly_version else [])
    if a.target_runtime:
        # Only these two, in a directory of their own: the host must keep loading its own standard macros.
        target = work / 'target-runtime'
        if not target.exists():
            target.mkdir()
            for n in ('Nemerle.dll', 'Nemerle.Compiler.dll'): shutil.copy2(a.target_runtime.resolve() / n, target / n)
        command += ['-no-stdlib', '-r:' + str(target / 'Nemerle.dll'), '-r:' + str(target / 'Nemerle.Compiler.dll')]
    else:
        command.append('-r:' + str(host / 'Nemerle.Compiler.dll'))
    if label != 'compiler':
        command.append('-macros:' + str(native_compiler))
    command += ['-r:' + str(runtime / (n + '.dll')) for n in references]
    command += ['-r:' + str(output / (prefix + n + '.dll')) for n in dependencies]
    if csharp:
        csc = net10_csc()
        support = output / (prefix + name + '.Support.dll')
        response = work / (label + '-support.rsp')
        options = ['-nologo', '-nostdlib+', '-target:library', '-out:"' + str(support) + '"']
        options += ['-r:"' + str(path) + '"' for path in sorted(a.references.resolve().glob('*.dll'))]
        options += ['"' + path + '"' for path in csharp]
        for item in ET.parse(project).getroot().findall('.//{http://schemas.microsoft.com/developer/msbuild/2003}EmbeddedResource'):
            resource = (project.parent / item.attrib['Include'].replace('\\', '/')).resolve()
            logical = name + '.' + item.attrib['Include'].replace('\\', '.')
            options.append('-resource:"' + str(resource) + '",' + logical)
        response.write_text('\n'.join(options))
        subprocess.run(['dotnet', str(csc), '@' + str(response)], check=True)
        command.append('-r:' + str(support))
    log = work / (label + '.log')
    print('Building upstream bootstrap:', label, flush=True)
    (work / (label + '-command.json')).write_text(json.dumps(command, indent=2))
    with log.open('w') as stream:
        result = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT)
    report['stages'].append({'name': label, 'exit_code': result.returncode, 'log': str(log)})
    (work / 'report.json').write_text(json.dumps(report, indent=2))
    if result.returncode:
        print(log.read_text()[-16000:], flush=True)
        raise SystemExit(result.returncode)
    print('PASS:', label, flush=True)
    if label == a.through:
        break
print('Bootstrap artifacts (not an integrated grammar toolchain):', output, flush=True)
