#!/usr/bin/env python3
"""Check real compiler symbols and resources after metadata repair/signing."""
import argparse
import json
import pathlib
import shutil
import struct
import subprocess
import tempfile

parser = argparse.ArgumentParser()
parser.add_argument('--toolchain', type=pathlib.Path, required=True)
parser.add_argument('--references', type=pathlib.Path, required=True)
args = parser.parse_args()
repo = pathlib.Path(__file__).resolve().parents[1]
work = pathlib.Path(tempfile.mkdtemp(prefix='nemerle-debug-resources-'))
print('Debug/resource artifacts:', work, flush=True)
for path in args.toolchain.iterdir():
    if path.is_file(): shutil.copy2(path, work / path.name)
refs = args.references.resolve()
version, sdk_root = subprocess.check_output(['dotnet', '--list-sdks'], text=True).splitlines()[-1].split(' ', 1)
csc = pathlib.Path(sdk_root.strip('[]')) / version / 'Roslyn/bincore/csc.dll'

def run(command):
    result = subprocess.run(list(map(str, command)), cwd=work, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=120)
    print(result.stdout, end='', flush=True)
    if result.returncode: raise RuntimeError('Command failed: ' + str(command))
    return result.stdout

def cs(name, text, references=()):
    source = work / (name + '.cs'); source.write_text(text)
    response = work / (name + '.rsp')
    response.write_text('\n'.join(['-nologo', '-nostdlib+', '-target:exe', '-out:"' + str(work / (name + '.dll')) + '"'] +
        ['-r:"' + str(p) + '"' for p in refs.glob('*.dll')] + ['-r:"' + str(p) + '"' for p in references] + ['"' + str(source) + '"']))
    run(['dotnet', csc, '@' + str(response)])
    shutil.copy2(work / 'ncc.runtimeconfig.json', work / (name + '.runtimeconfig.json'))

cs('Generate', '''using System.IO; using System.Resources;
class Generate { static void Main() {
using (var writer = new ResourceWriter("Assets.resources")) {
writer.AddResource("Text", "café"); writer.AddResource("Number", 7);
writer.AddResource("Bytes", new byte[] {3,7,11}); writer.AddResource("Empty", (string)null); writer.Generate(); }
File.WriteAllText("encoded.txt", "café", System.Text.Encoding.Unicode);
} }''')
run(['dotnet', work / 'Generate.dll'])
(work / 'Assets.resx').write_text('''<root>
<data name="Text" type="System.Resources.ResXFileRef, System.Windows.Forms"><value>encoded.txt;System.String;utf-16</value></data>
<data name="Number" type="System.Int32"><value>7</value></data>
<data name="Bytes" type="System.Byte[]"><value>AwcL</value></data>
<data name="Empty" type="System.Resources.ResXNullRef, System.Windows.Forms"><value /></data>
</root>''')
source = work / 'debug.n'
source.write_text('''using System;
[assembly: Nemerle.Macro.Resource("Assets.resx")]
class ResourceProgram {
  public static Check() : int {
    if (Assets.Text == "café" && Assets.Number == 7 && Assets.Bytes[2] == 11 && Assets.Empty == null) 42 else 0
  }
  public static Fail() : void {
    def answer = 42;
    Console.WriteLine(answer);
    throw InvalidOperationException("debug");
  }
}
''')
# A standard numeric RCDATA resource with language 1033.
header = struct.pack('<IIHHHHIHHII', 3, 32, 0xffff, 10, 0xffff, 77, 0, 0, 1033, 0, 0)
(work / 'native.res').write_bytes(header + bytes([3,7,11,0]))
(work / 'external.bin').write_bytes(bytes([5,9,13]))
command = ['dotnet', work / 'ncc.exe', source, '-source-root:' + str(work), '-debug', '-target:library', '-out:' + str(work / 'DebugSample.dll'),
           '-target-references:' + str(refs), '-resource:' + str(work / 'Assets.resources') + ',Assets.resources',
           '-win32res:' + str(work / 'native.res'),
           '-keyfile:' + str(repo / 'misc/keys/Nemerle.Compiler.snk'), '-project-path:' + str(work / 'test.nproj'), '-no-color']
run(command)
run(['sn', '-vf', work / 'DebugSample.dll'])
cs('Inspect', '''using System; using System.IO; using System.Linq; using System.Reflection;
using System.Reflection.Metadata; using System.Reflection.PortableExecutable;
class Inspect {
static void Check(bool condition, string message) { if (!condition) throw new Exception(message); }
static void Main() {
var assembly = Assembly.LoadFrom("DebugSample.dll");
var program = assembly.GetType("debug+ResourceProgram");
Check((int)program.GetMethod("Check").Invoke(null,null) == 42, "Generated Resource macro properties must load values");
try { program.GetMethod("Fail").Invoke(null,null); throw new Exception("Expected user exception"); }
catch (TargetInvocationException e) { Check(e.InnerException.StackTrace.Contains("debug.n:line 10"), "Source stack trace missing: " + e.InnerException.StackTrace); }
using (var pdb = File.OpenRead("DebugSample.pdb"))
using (var provider = MetadataReaderProvider.FromPortablePdbStream(pdb)) {
var metadata = provider.GetMetadataReader();
Check(metadata.LocalVariables.Any(h => metadata.GetString(metadata.GetLocalVariable(h).Name) == "answer"), "Named compiler local missing");
Check(metadata.MethodDebugInformation.Any(h => metadata.GetMethodDebugInformation(h).GetSequencePoints().Any(p => p.StartLine == 10)), "Throw sequence point missing");
}
using (var stream = File.OpenRead("DebugSample.dll")) using (var pe = new PEReader(stream)) {
var entry = pe.ReadDebugDirectory().First(e => e.Type == DebugDirectoryEntryType.CodeView);
Check(Path.GetFileName(pe.ReadCodeViewDebugDirectoryData(entry).Path) == "DebugSample.pdb", "Wrong PDB path");
Check(pe.PEHeaders.PEHeader.ResourceTableDirectory.Size > 0, "Native resources missing after compiler repair/signing");

}
Console.WriteLine("PASS: compiler portable PDB, source stack trace, local names, Resource macro values, native resources, strong naming");
} }''')
run(['dotnet', work / 'Inspect.dll'])
# A release rebuild must not retain stale portable symbols.
release = [arg for arg in command if arg != '-debug']
run(release)
if (work / 'DebugSample.pdb').exists(): raise RuntimeError('Release rebuild retained a stale portable PDB')
print('PASS: release rebuild removes stale symbols', flush=True)
