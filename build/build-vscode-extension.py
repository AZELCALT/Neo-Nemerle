#!/usr/bin/env python3
"""Package the VS Code / VSCodium extension, with its language server, as a .vsix to install by hand.

    build/build-vscode-extension.py [--server out/bootstrap/lsp] [--references DIR] [--output out/vscode]

The server folder is the one build/build-language-server.py writes (nemerle-lsp.exe with the toolchain next to it);
the reference assemblies go into server/references, so the extension needs only the .NET 10 runtime. The .vsix is an
ordinary Open Packaging zip (extension.vsixmanifest, [Content_Types].xml, extension/...), written here directly, so no
vsce is needed. Install it with `code --install-extension FILE` or `codium --install-extension FILE`.
"""
import argparse, json, pathlib, shutil, subprocess, sys, tempfile, zipfile
from xml.sax.saxutils import escape

repo = pathlib.Path(__file__).resolve().parents[1]
source = repo / 'tools/language-server/vscode'
p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
p.add_argument('--server', type=pathlib.Path, default=repo / 'out/bootstrap/lsp', help='built language server folder')
p.add_argument('--references', type=pathlib.Path, default=repo / 'out/bootstrap/toolchain/references',
               help='.NET reference assemblies for the server (default: the toolchain\'s)')
p.add_argument('--output', type=pathlib.Path, default=repo / 'out/vscode')
a = p.parse_args()

manifest = json.loads((source / 'package.json').read_text())
name, version, publisher = manifest['name'], manifest['version'], manifest['publisher']
if not (a.server / 'nemerle-lsp.exe').exists():
    sys.exit('no nemerle-lsp.exe in %s (build it with build/build-language-server.py, or ./bootstrap)' % a.server)
if not a.references.is_dir():
    sys.exit('no reference assemblies in %s' % a.references)

work = pathlib.Path(tempfile.mkdtemp(prefix='nemerle-vsix-'))
ext = work / 'extension'
ext.mkdir()
for f in ('package.json', 'extension.js', 'language-configuration.json', 'README.md'):
    shutil.copy2(source / f, ext / f)
shutil.copytree(source / 'syntaxes', ext / 'syntaxes')
shutil.copytree(source / 'images', ext / 'images')   # the icon (marketplace) and the .n file icon (responsive SVG)
shutil.copy2(repo / 'LICENSES/GPL-2.0-or-later.txt', ext / 'LICENSE.txt')
# the client library: the extension's one production dependency
if not (source / 'node_modules/vscode-languageclient').is_dir():
    subprocess.run(['npm', 'install', '--omit=dev', '--no-audit', '--no-fund'], cwd=source, check=True)
shutil.copytree(source / 'node_modules', ext / 'node_modules')
# the server, its toolchain and reference assemblies
server = ext / 'server'
shutil.copytree(a.server, server, ignore=shutil.ignore_patterns('*.log', 'nemerle-lsp'))
shutil.copytree(a.references, server / 'references', dirs_exist_ok=True)

description = escape(manifest['description'])
(work / 'extension.vsixmanifest').write_text(f'''<?xml version="1.0" encoding="utf-8"?>
<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011" xmlns:d="http://schemas.microsoft.com/developer/vsx-schema-design/2011">
  <Metadata>
    <Identity Language="en-US" Id="{name}" Version="{version}" Publisher="{publisher}" />
    <DisplayName>{escape(manifest['displayName'])}</DisplayName>
    <Description xml:space="preserve">{description}</Description>
    <Tags>{','.join(manifest.get('keywords', []))}</Tags>
    <Categories>{','.join(manifest['categories'])}</Categories>
    <GalleryFlags>Public</GalleryFlags>
    <Icon>extension/images/icon.png</Icon>
    <Properties>
      <Property Id="Microsoft.VisualStudio.Code.Engine" Value="{manifest['engines']['vscode']}" />
      <Property Id="Microsoft.VisualStudio.Code.ExtensionDependencies" Value="" />
      <Property Id="Microsoft.VisualStudio.Code.ExtensionPack" Value="" />
      <Property Id="Microsoft.VisualStudio.Code.ExtensionKind" Value="workspace" />
      <Property Id="Microsoft.VisualStudio.Code.LocalizedLanguages" Value="" />
      <Property Id="Microsoft.VisualStudio.Services.Links.Source" Value="{manifest['repository']['url']}" />
    </Properties>
    <License>extension/LICENSE.txt</License>
  </Metadata>
  <Installation>
    <InstallationTarget Id="Microsoft.VisualStudio.Code" />
  </Installation>
  <Dependencies />
  <Assets>
    <Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" Addressable="true" />
    <Asset Type="Microsoft.VisualStudio.Services.Content.Details" Path="extension/README.md" Addressable="true" />
    <Asset Type="Microsoft.VisualStudio.Services.Content.License" Path="extension/LICENSE.txt" Addressable="true" />
    <Asset Type="Microsoft.VisualStudio.Services.Icons.Default" Path="extension/images/icon.png" Addressable="true" />
  </Assets>
</PackageManifest>
''')
files = sorted(f for f in work.rglob('*') if f.is_file())
kinds = {'.json': 'application/json', '.js': 'application/javascript', '.md': 'text/markdown', '.txt': 'text/plain',
         '.png': 'image/png', '.svg': 'image/svg+xml',
         '.vsixmanifest': 'text/xml', '.xml': 'text/xml'}
extensions = sorted({f.suffix.lower() for f in files if f.suffix})
types = ''.join('<Default Extension="%s" ContentType="%s" />' % (e, kinds.get(e, 'application/octet-stream')) for e in extensions)
(work / '[Content_Types].xml').write_text('<?xml version="1.0" encoding="utf-8"?>\n'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">%s</Types>\n' % types)

a.output.mkdir(parents=True, exist_ok=True)
vsix = a.output / ('%s-%s.vsix' % (name, version))
with zipfile.ZipFile(vsix, 'w', zipfile.ZIP_DEFLATED) as z:
    for f in sorted(f for f in work.rglob('*') if f.is_file()):
        z.write(f, f.relative_to(work).as_posix())
shutil.rmtree(work, ignore_errors=True)
print('VS Code extension: %s (%.1f MB)' % (vsix, vsix.stat().st_size / 1e6))
