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
  const server = { command, args, transport: 0 /* stdio */ };
  client = new LanguageClient('nemerle', 'Nemerle', { run: server, debug: server },
    { documentSelector: [{ scheme: 'file', language: 'nemerle' }, { scheme: 'untitled', language: 'nemerle' }] });
  client.start();
  context.subscriptions.push({ dispose: () => client && client.stop() });
}

function deactivate() { return client ? client.stop() : undefined; }

module.exports = { activate, deactivate };
