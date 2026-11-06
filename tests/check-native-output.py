#!/usr/bin/env python3
"""Exercise native map generation and direct PExpr output, outside source hosting.

The upstream recognizer bootstraps the fixture definition only. Its runtime
input is supplied through selected-tree factories and must not be reparsed.
"""
import argparse
import pathlib
import shutil
import subprocess
import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'build'))
from tooling import net10_runtime
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
common = ['dotnet', str(w / 'ncc.exe'), '-launcher-', '-no-color', '-source-root:' + str(here), '-target-references:' + str(a.references.resolve())]
references = ['-r:' + str(w / name) for name in (
    'Nemerle.Compiler.dll', 'Integrated.Nitra.Runtime.dll',
    'Integrated.DotNetLang.dll', 'Integrated.Nitra.Grammar.dll')]
runtime = net10_runtime()
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
