#!/usr/bin/env python3
"""Regression checks for Windows paths, mixed installed .NET versions and Mono batch launchers."""
import importlib.util
import pathlib
import tempfile
import unittest

import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'build'))

# A small independently signed managed PE fixture; contains a test-only public key.
_SIGNED_FIXTURE = (
    'c-r%gVjvqdFi;KxTp1XA7#UH-9x(7Jax*f}3<xj`08n6H@Id0~m84dbfEa8LIWWyce`k4stz~6M0J=dC80MVl3REbIXQyB<Cq@QHWO4&>nTei(p0R<kp(O*@W*Z=B1jNd93=DZddNGLYl#`zX)ej63ux8}s0AjN=po@Wd4GTaH21!l<g((xn13|%#h72qaMa8#Ojvv~6R>|7`Gk3N7l`pJqyy;nC>&~tXXqgu|akby_Nr%HXXSx1<alYK_0oxi^nX0lKvyc1>5Zx&6e)`&Jz3Yj0lU()(m@KiJyX?v9t1TfOtNyBQ?4Evk*^>3=Yqy>d-o{bbJ3&Bizd%Z?ivDkVxq#K%U);67Byil;rD5i*j|`(=6bv4)Yt1sbUl9deH3@s4>y>5Ma=o|TR`qT=r)kKX_WUQek}o_FT4z0RiGQ8*ALC1^vQB-8zjWQA56w8KZgF4a-rGwHYmS!Q<UF;yipPy_S*L%FbeZimnV49kCCNG&j!R}Pu?XLB<Ct6If<>==ql5Wh>J^;a6R<-^r|I`}R<X7aj<usPFt7jsI+K!P'
)

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
        self.assertEqual(tooling.artifact_path('result: /tmp/a folder/output\n', 'result: '), pathlib.Path('/tmp/a folder/output'))
        with self.assertRaisesRegex(RuntimeError, 'did not report'):
            tooling.artifact_path('failed', marker)

    def test_signed_assembly_is_verified_without_external_tools(self):
        import base64
        import zlib
        from strong_name import StrongNameError

        signed = zlib.decompress(base64.b85decode(_SIGNED_FIXTURE))
        with tempfile.TemporaryDirectory(prefix='nemerle strong name ') as folder:
            assembly = pathlib.Path(folder) / 'signed.dll'
            assembly.write_bytes(signed)
            tooling.verify_strong_name(assembly)
            for offset in (0x600, 0x5f0, 0x260):
                tampered = bytearray(signed)
                tampered[offset] ^= 1
                assembly.write_bytes(tampered)
                with self.subTest(offset=offset), self.assertRaises(StrongNameError):
                    tooling.verify_strong_name(assembly)
            assembly.write_bytes(bytes(len(signed)))
            with self.assertRaises(StrongNameError):
                tooling.verify_strong_name(assembly)


    def test_windows_codedom_portability_gate(self):
        import importlib.util
        import struct
        file = pathlib.Path(__file__).resolve().parents[1] / 'build/windows_codedom.py'
        spec = importlib.util.spec_from_file_location('windows_codedom', file)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        pe = bytearray(1024)
        pe[:2] = b'MZ'
        struct.pack_into('<I', pe, 0x3c, 0x80)
        pe[0x80:0x84] = b'PE\0\0'
        struct.pack_into('<H', pe, 0x84, 0x14c)
        struct.pack_into('<H', pe, 0x86, 1)
        struct.pack_into('<H', pe, 0x94, 0xe0)
        struct.pack_into('<H', pe, 0x98, 0x10b)
        struct.pack_into('<I', pe, 0x98 + 96 + 8 * 14, 0x2000)
        section = 0x178
        struct.pack_into('<I', pe, section + 12, 0x2000)
        struct.pack_into('<I', pe, section + 16, 0x200)
        struct.pack_into('<I', pe, section + 20, 0x200)
        struct.pack_into('<I', pe, 0x200 + 16, 1)
        self.assertTrue(module._portable_il(pe))
        struct.pack_into('<H', pe, 0x84, 0xfd1d)
        self.assertFalse(module._portable_il(pe))
        struct.pack_into('<H', pe, 0x84, 0x14c)
        struct.pack_into('<I', pe, 0x200 + 64, 0x2200)
        self.assertFalse(module._portable_il(pe))

    def test_cli_toolchain_builds_managed_exe_not_windows_apphost(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        bootstrap = (root / 'build/build-coreclr-toolchain.py').read_text()
        dev = (root / 'build/dev.py').read_text()
        # The bootstrap invokes `dotnet ncc.exe` and verifies its strong name:
        # a Windows native apphost cannot be used for either operation.
        self.assertIn("['-source-root:' + str(repo / 'ncc'), '-launcher-', *new_macros])", bootstrap)
        self.assertIn("['-source-root:' + str(repo / 'ncc'), '-launcher-', *new_runtime, *new_macros])", bootstrap)
        self.assertIn("cli_refs, ['-no-stdlib', '-r:' + str(base / 'Nemerle.dll'), '-source-root:' + str(repo / 'ncc'), '-launcher-'])", dev)

    def test_cleanup_generated_items_accepts_directories_on_windows(self):
        with tempfile.TemporaryDirectory(prefix='nemerle-generated-') as directory:
            root = pathlib.Path(directory)
            generated_file = root / '_N_Temporary.n'
            generated_file.write_text('temporary')
            generated_dir = root / '_N_GeneratedSource_Nemerle.n'
            generated_dir.mkdir()
            (generated_dir / 'nested.n').write_text('generated')
            keep = root / 'Nemerle.dll'
            keep.write_text('keep')
            tooling.cleanup_generated_items(root)
            self.assertFalse(generated_file.exists())
            self.assertFalse(generated_dir.exists())
            self.assertEqual(keep.read_text(), 'keep')
            tooling.cleanup_generated_items(root)  # idempotent


    def test_readonly_generated_and_bootstrap_cleanup(self):
        import stat
        with tempfile.TemporaryDirectory(prefix='nemerle readonly build ') as folder:
            root = pathlib.Path(folder)
            output = root / 'netstandard2.0'
            output.mkdir()
            generated = output / '_N_GeneratedSource_Nemerle.n'
            generated.write_text('generated')
            generated.chmod(stat.S_IREAD)
            nested = output / '_N_folder'
            nested.mkdir()
            (nested / 'item.n').write_text('generated')
            keep = output / 'Nemerle.dll'
            keep.write_bytes(b'keep')
            tooling.cleanup_generated_items_readonly(output)
            self.assertFalse(generated.exists())
            self.assertFalse(nested.exists())
            self.assertTrue(keep.exists())
            # Reproduce the second-run bootstrap cleanup on a new read-only file.
            generated.write_text('generated again')
            generated.chmod(stat.S_IREAD)
            tooling.remove_readonly_tree(output)
            self.assertFalse(output.exists())

    def test_readonly_removal_retry_only_for_readonly(self):
        import os
        import stat
        with tempfile.TemporaryDirectory() as folder:
            file = pathlib.Path(folder) / 'generated.n'
            file.write_text('generated')
            file.chmod(stat.S_IREAD)
            tooling._retry_readonly_removal(os.unlink, str(file), PermissionError('read-only'))
            self.assertFalse(file.exists())
            file.write_text('another')
            with self.assertRaises(PermissionError):
                tooling._retry_readonly_removal(os.unlink, str(file), PermissionError('ACL'))

    def test_cross_platform_cli_wrappers(self):
        import windows_commands
        from unittest.mock import patch
        with patch.object(windows_commands, 'WINDOWS', True):
            root = pathlib.Path('test-toolchain')
            c = windows_commands.ncc_command(root)
            self.assertEqual(c[:2], ['dotnet', str(root / 'ncc.exe')])
            self.assertIn('-target-references:' + str(root / 'references'), c)
            self.assertIn('-launcher-', c)
            self.assertNotIn('-launcher-', windows_commands.ncc_command(root, managed_output=False))
            self.assertEqual(windows_commands.nscript_command(root), ['dotnet', str(root / 'nscript.exe')])
            self.assertEqual(windows_commands.lsp_command(root / 'nemerle-lsp'),
                             ['dotnet', str(root / 'nemerle-lsp.exe')])
        with patch.object(windows_commands, 'WINDOWS', False):
            self.assertEqual(windows_commands.ncc_command('test-toolchain'), [str(root / 'ncc')])
            self.assertEqual(windows_commands.nscript_command('test-toolchain'), [str(root / 'nscript')])

    def test_generated_cleanup_permission_failure_is_nonfatal(self):
        """A locked generated file is reported but must not fail a built DLL."""
        from unittest.mock import patch
        with tempfile.TemporaryDirectory(prefix='nemerle generated cleanup ') as d:
            folder = pathlib.Path(d)
            keep = folder / 'Nemerle.dll'
            keep.write_bytes(b'compiled runtime')
            generated = folder / '_N_GeneratedSource_Nemerle.n'
            generated.write_text('generated source')
            real_unlink = pathlib.Path.unlink
            def simulate_sharing_violation(path, *args, **kwargs):
                if path == generated:
                    raise PermissionError(13, 'simulated file sharing violation', str(path))
                return real_unlink(path, *args, **kwargs)
            with patch.object(pathlib.Path, 'unlink', simulate_sharing_violation):
                with patch('builtins.print') as message:
                    tooling.cleanup_generated_items_readonly(folder)
            self.assertTrue(generated.exists())
            self.assertEqual(keep.read_bytes(), b'compiled runtime')
            text = ' '.join(str(x) for call in message.call_args_list for x in call.args)
            self.assertIn('WARNING: generated artifact could not be removed', text)
            self.assertIn(str(generated), text)
            # Subsequent cleanup succeeds when the simulated lock is released.
            tooling.cleanup_generated_items_readonly(folder)
            self.assertFalse(generated.exists())
            self.assertTrue(keep.exists())

if __name__ == '__main__':
    unittest.main()
