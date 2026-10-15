#!/usr/bin/env python3
"""Exercise native map generation and direct PExpr output, outside source hosting.

The upstream recognizer bootstraps the fixture definition only. Its runtime
input is supplied through selected-tree factories and must not be reparsed.
"""
import argparse
import pathlib
import shutil
import subprocess
import tempfile

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--toolchain', type=pathlib.Path, required=True)
p.add_argument('--native-core', type=pathlib.Path, required=True)
p.add_argument('--references', type=pathlib.Path, required=True)
a = p.parse_args()
w = pathlib.Path(tempfile.mkdtemp(prefix='nemerle-native-output-'))
print('Native output checks:', w, flush=True)
for root in (a.toolchain, a.native_core):
    for f in root.iterdir():
        if f.is_file() and f.suffix in {'.dll', '.exe', '.json', '.nitrametadata'}:
            shutil.copy2(f, w / f.name)
here = pathlib.Path(__file__).resolve().parent
common = ['dotnet', str(w / 'ncc.exe'), '-no-color', '-source-root:' + str(here), '-target-references:' + str(a.references.resolve())]
references = ['-r:' + str(w / name) for name in (
    'Nemerle.Compiler.dll', 'Integrated.Nitra.Runtime.dll',
    'Integrated.DotNetLang.dll', 'Integrated.Nitra.Grammar.dll')]
rows = [line.split() for line in subprocess.check_output(
    ['dotnet', '--list-runtimes'], text=True).splitlines()
    if line.startswith('Microsoft.NETCore.App ')]
row = max(rows, key=lambda x: tuple(map(int, x[1].split('.'))))
runtime = pathlib.Path(row[2].strip('[]')) / row[1]
references += ['-r:' + str(runtime / (name + '.dll')) for name in (
    'System.Collections.Immutable', 'System.Linq', 'System.Xml.XDocument',
    'System.Xml.ReaderWriter', 'System.Xml.XmlDocument')]
subprocess.run(common + references + [
    str(here / 'NativeNemerleMapping.nitra'), str(here / 'DirectOutput.n'),
    '-macros:' + str(w / 'Integrated.Nitra.Compiler.dll'), '-target:library',
    '-out:' + str(w / 'NativeMapping.dll')], check=True, cwd=w, timeout=180)
subprocess.run(common + references + [str(here / 'NativeNemerleMappingConsumer.n'),
    '-macros:' + str(w / 'NativeMapping.dll'), '-out:' + str(w / 'Consumer.exe')],
    check=True, cwd=w, timeout=120)
shutil.copy2(w / 'ncc.runtimeconfig.json', w / 'Consumer.runtimeconfig.json')
subprocess.run(['dotnet', str(w / 'Consumer.exe')], check=True, cwd=w, timeout=30)
