#!/usr/bin/env python3
"""Regression checks for Windows paths, mixed installed .NET versions and Mono batch launchers."""
import importlib.util
import pathlib
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('tooling', pathlib.Path(__file__).resolve().parents[1] / 'build/tooling.py')
tooling = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tooling)


class BuildToolingChecks(unittest.TestCase):
    def test_runtime_ignores_newer_major_and_keeps_spaces(self):
        output = ('Microsoft.NETCore.App 11.0.0 [C:\\Program Files\\dotnet\\shared\\Microsoft.NETCore.App]\n'
                  'Microsoft.NETCore.App 10.0.9 [C:\\Program Files\\dotnet\\shared\\Microsoft.NETCore.App]\n'
                  'Microsoft.NETCore.App 10.0.10 [C:\\Program Files\\dotnet\\shared\\Microsoft.NETCore.App]\n')
        result = tooling.net10_runtime(output)
        self.assertEqual(result.name, '10.0.10')
        self.assertIn('Program Files', str(result))
        self.assertIn('Microsoft.NETCore.App', str(result))

    def test_sdk_uses_net10_not_net11(self):
        result = tooling.net10_csc('11.0.100 [C:\\Program Files\\dotnet\\sdk]\n10.0.113 [C:\\Program Files\\dotnet\\sdk]\n')
        self.assertIn('10.0.113', str(result))
        self.assertIn('Program Files', str(result))
        self.assertEqual(result.name, 'csc.dll')
        with self.assertRaisesRegex(RuntimeError, '.NET 10 SDK'):
            tooling.net10_csc('11.0.100 [/dotnet/sdk]\n')

    def test_artifact_markers_keep_whole_path(self):
        marker = 'Verified CoreCLR source toolchain: '
        path = r'C:\Users\A Developer\AppData\Local\Temp\nemerle-core\stage2\ncc.exe'
        self.assertEqual(str(tooling.artifact_path(marker + path + '\n', marker)), path)
        self.assertEqual(str(tooling.artifact_path('result: /tmp/a folder/output\n', 'result: ')), '/tmp/a folder/output')
        with self.assertRaisesRegex(RuntimeError, 'did not report'):
            tooling.artifact_path('failed', marker)

    def test_mono_batch_uses_managed_executable_without_shell(self):
        with tempfile.TemporaryDirectory(prefix='nemerle mono tools ') as folder:
            base = pathlib.Path(folder)
            sn = base / 'bin/sn.bat'
            managed = base / 'lib/mono/4.5/sn.exe'
            managed.parent.mkdir(parents=True)
            managed.write_bytes(b'tool')
            assembly = base / 'an assembly.dll'
            with patch.object(tooling.shutil, 'which', side_effect=lambda n: str(sn) if n == 'sn' else 'mono.exe'):
                with patch.object(tooling.subprocess, 'run') as run:
                    tooling.verify_strong_name(assembly)
                    self.assertEqual(run.call_args.args[0], ['mono.exe', str(managed), '-vf', str(assembly)])
                    self.assertNotIn('shell', run.call_args.kwargs)


if __name__ == '__main__':
    unittest.main()
