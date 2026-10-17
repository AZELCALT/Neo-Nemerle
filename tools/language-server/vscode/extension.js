// Starts nemerle-lsp (stdio) for .n files. The extension carries the server (server/nemerle-lsp.exe), which runs on
// the .NET 10 runtime; a configured or installed nemerle-lsp is used instead when set.
const vscode = require('vscode');
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');
const { LanguageClient } = require('vscode-languageclient/node');

let client;

function serverCommand(context, config) {
  const dotnet = vscode.workspace.getConfiguration('nemerle.dotnet').get('path') || 'dotnet';
  const configured = config.get('path') || process.env.NEMERLE_LSP;
  const bundled = path.join(context.extensionPath, 'server', 'nemerle-lsp.exe');
  // a .exe (a .NET assembly) runs on dotnet; anything else is a launcher
  const run = (file) => file.toLowerCase().endsWith('.exe') ? { command: dotnet, prefix: [file] } : { command: file, prefix: [] };
  if (configured) return run(configured);
  if (fs.existsSync(bundled)) return { command: dotnet, prefix: [bundled] };
  return run('nemerle-lsp');
}

function hasDotnet10(dotnet) {
  try { return /^Microsoft\.NETCore\.App 10\./m.test(execFileSync(dotnet, ['--list-runtimes'], { encoding: 'utf8' })); }
  catch { return false; }
}

function activate(context) {
  const config = vscode.workspace.getConfiguration('nemerle.languageServer');
  const { command, prefix } = serverCommand(context, config);
  if (prefix.length > 0 && !hasDotnet10(command)) {
    vscode.window.showErrorMessage('Nemerle needs the .NET 10 runtime to run its language server.', 'Get .NET 10')
      .then(choice => { if (choice) vscode.env.openExternal(vscode.Uri.parse('https://dotnet.microsoft.com/download/dotnet/10.0')); });
    return;
  }
  const args = [...prefix];
  if (config.get('references')) args.push('--references', config.get('references'));
  if (config.get('log')) args.push('--log', config.get('log'));
  if (config.get('sourceRoot')) args.push('--source-root', config.get('sourceRoot'));
  if (config.get('fileNameNamespaces')) args.push('--file-name-namespaces');
  if (config.get('typecheck') === false) args.push('--no-typecheck');
  for (const library of config.get('libraries') || []) args.push('--library', library);
  // a launcher on Windows (nemerle-lsp.cmd) only starts through a shell; dotnet does not need one
  const shell = process.platform === 'win32' && prefix.length === 0;
  const server = { command, args, transport: 0 /* stdio */, options: shell ? { shell: true } : undefined };
  client = new LanguageClient('nemerle', 'Nemerle', { run: server, debug: server },
    { documentSelector: [{ scheme: 'file', language: 'nemerle' }, { scheme: 'untitled', language: 'nemerle' }] });
  client.start();
  context.subscriptions.push({ dispose: () => client && client.stop() });
}

function deactivate() { return client ? client.stop() : undefined; }

module.exports = { activate, deactivate, _test: { serverCommand, hasDotnet10 } };
