#!/usr/bin/env python3
"""The VS Code / VSCodium extension, as installed from its .vsix.

    check-vscode-extension.py --vsix FILE

The .vsix is unpacked as an editor installs it. Its extension.js is loaded under node with a minimal stand-in for
the `vscode` API: it must choose the server it carries (server/nemerle-lsp.exe on dotnet), and that server must
answer the language server protocol's initialize request with its capabilities. When a VSCodium or VS Code command
line is found, the .vsix is also installed into a scratch profile."""
import argparse, json, pathlib, shutil, subprocess, tempfile, zipfile
p = argparse.ArgumentParser()
p.add_argument('--vsix', type=pathlib.Path, required=True)
a = p.parse_args()
w = pathlib.Path(tempfile.mkdtemp(prefix='nemerle-vscode-'))
print('VS Code extension checks:', w, flush=True)
with zipfile.ZipFile(a.vsix) as z:
    names = z.namelist()
    for required in ('extension.vsixmanifest', '[Content_Types].xml', 'extension/package.json', 'extension/extension.js',
                     'extension/syntaxes/nemerle.tmLanguage.json', 'extension/server/nemerle-lsp.exe',
                     'extension/node_modules/vscode-languageclient/package.json', 'extension/images/icon.png',
                     'extension/images/nemerle.svg', 'extension/images/nemerle-script.svg',
                     'extension/syntaxes/nemerle-script.tmLanguage.json'):
        if required not in names:
            raise SystemExit('FAILED: the .vsix has no ' + required)
    if not any(n.startswith('extension/server/references/') for n in names):
        raise SystemExit('FAILED: the .vsix carries no reference assemblies')
    z.extractall(w / 'unpacked')
ext = w / 'unpacked/extension'
manifest = json.loads((ext / 'package.json').read_text())
assert manifest['contributes']['grammars'][0]['language'] == 'nemerle'
json.loads((ext / 'syntaxes/nemerle.tmLanguage.json').read_text())
# the icons: the marketplace one is a PNG the manifest names, the file icon the responsive SVG
assert manifest['icon'] == 'images/icon.png' and (ext / manifest['icon']).read_bytes()[:8] == b'\x89PNG\r\n\x1a\n'
assert manifest['contributes']['languages'][0]['icon']['dark'] == './images/nemerle.svg'
# scripts (.ns) are their own language, with the yellow icon, highlighted as Nemerle
script = manifest['contributes']['languages'][1]
assert script['id'] == 'nemerle-script' and script['extensions'] == ['.ns'] and script['icon']['dark'] == './images/nemerle-script.svg'
assert 'stop-color="#f2d60c"' in (ext / 'images/nemerle-script.svg').read_text()
assert any(g['language'] == 'nemerle-script' and g['scopeName'] == 'source.nemerle.script' for g in manifest['contributes']['grammars'])
assert '<Icon>extension/images/icon.png</Icon>' in (w / 'unpacked/extension.vsixmanifest').read_text()
print('PASS: the .vsix holds the extension, its grammar, its icons, the client library, the server and reference assemblies', flush=True)

harness = w / 'harness.js'
harness.write_text(r'''
const Module = require('module');
const original = Module._load;
const settings = {};
Module._load = function (request, parent, isMain) {
  if (request === 'vscode-languageclient/node') return { LanguageClient: class { start() {} stop() {} } };
  if (request === 'vscode')
    return { workspace: { getConfiguration: () => ({ get: key => settings[key] }) },
             window: { showErrorMessage: () => Promise.resolve() }, env: {}, Uri: {} };
  return original.apply(this, arguments);
};
const ext = require(process.argv[2]);
const context = { extensionPath: process.argv[3], subscriptions: [] };
const { command, prefix } = ext._test.serverCommand(context, { get: key => settings[key] });
if (!prefix[0] || !prefix[0].endsWith('nemerle-lsp.exe')) { console.log('FAILED: not the bundled server: ' + command + ' ' + prefix); process.exit(1); }
if (!ext._test.hasDotnet10(command)) { console.log('FAILED: no .NET 10 runtime found through ' + command); process.exit(1); }
// start it as the extension does and ask for its capabilities
const child = require('child_process').spawn(command, prefix);
const body = JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'initialize', params: { processId: process.pid, rootUri: null, capabilities: {} } });
child.stdin.write('Content-Length: ' + Buffer.byteLength(body) + '\r\n\r\n' + body);
let out = '';
const timer = setTimeout(() => { console.log('FAILED: no initialize response'); child.kill(); process.exit(1); }, 60000);
child.stdout.on('data', d => {
  out += d;
  const at = out.indexOf('\r\n\r\n');
  if (at < 0) return;
  const length = parseInt(/Content-Length: (\d+)/.exec(out)[1]);
  if (out.length < at + 4 + length) return;
  const response = JSON.parse(out.substr(at + 4, length));
  clearTimeout(timer); child.kill();
  const caps = response.result.capabilities;
  console.log(JSON.stringify({ semanticTokens: !!caps.semanticTokensProvider, folding: !!caps.foldingRangeProvider, symbols: !!caps.documentSymbolProvider }));
  process.exit(0);
});
''')
r = subprocess.run(['node', harness, ext / 'extension.js', ext], capture_output=True, text=True, timeout=120)
if r.returncode != 0 or '"semanticTokens":true' not in r.stdout:
    raise SystemExit('FAILED: the extension does not start its server\n' + r.stdout + r.stderr)
print('PASS: the extension starts the server it carries, which answers initialize with ' + r.stdout.strip(), flush=True)

for cli in (pathlib.Path.home() / '.local/opt/bin/codium', shutil.which('codium'), shutil.which('code')):
    if cli and pathlib.Path(cli).exists() and pathlib.Path(cli).read_bytes()[:2] == b'#!':
        profile = w / 'profile'
        r = subprocess.run([str(cli), '--user-data-dir', str(profile / 'data'), '--extensions-dir', str(profile / 'extensions'),
                            '--install-extension', str(a.vsix)], capture_output=True, text=True, timeout=180)
        if 'successfully installed' not in r.stdout:
            raise SystemExit('FAILED: %s does not install the .vsix\n%s%s' % (cli, r.stdout, r.stderr))
        print('PASS: %s installs the .vsix' % pathlib.Path(cli).name, flush=True)
        break
shutil.rmtree(w, ignore_errors=True)
