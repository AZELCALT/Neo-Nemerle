// Starts nemerle-lsp (stdio) for .n files.
const vscode = require('vscode');
const { LanguageClient } = require('vscode-languageclient/node');

let client;

function activate(context) {
  const config = vscode.workspace.getConfiguration('nemerle.languageServer');
  const command = config.get('path') || process.env.NEMERLE_LSP || 'nemerle-lsp';
  const args = [];
  if (config.get('references')) args.push('--references', config.get('references'));
  if (config.get('log')) args.push('--log', config.get('log'));
  if (config.get('sourceRoot')) args.push('--source-root', config.get('sourceRoot'));
  if (config.get('fileNameNamespaces')) args.push('--file-name-namespaces');
  // On Windows the launcher is nemerle-lsp.cmd, which Node only starts through a shell.
  const server = { command, args, transport: 0 /* stdio */, options: process.platform === 'win32' ? { shell: true } : undefined };
  client = new LanguageClient('nemerle', 'Nemerle', { run: server, debug: server },
    { documentSelector: [{ scheme: 'file', language: 'nemerle' }, { scheme: 'untitled', language: 'nemerle' }] });
  client.start();
  context.subscriptions.push({ dispose: () => client && client.stop() });
}

function deactivate() { return client ? client.stop() : undefined; }

module.exports = { activate, deactivate };
