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

// ---- debugging: netcoredbg (MIT) as the debug adapter, for VS Code and VSCodium alike ----

function findOnPath(name, only) {
  const exts = only || (process.platform === 'win32' ? ['.exe', '.cmd', ''] : ['']);
  for (const dir of (process.env.PATH || '').split(path.delimiter))
    for (const ext of exts) { const file = path.join(dir, name + ext); if (dir && fs.existsSync(file)) return file; }
  return null;
}

/// Where the installers put netcoredbg (their default prefixes).
function installedDebugger() {
  const exe = process.platform === 'win32' ? 'netcoredbg.exe' : 'netcoredbg';
  const homes = process.platform === 'win32'
    ? [process.env.LOCALAPPDATA && path.join(process.env.LOCALAPPDATA, 'Nemerle')]
    : [path.join(process.env.XDG_DATA_HOME || path.join(require('os').homedir(), '.local', 'share'), 'nemerle')];
  for (const home of homes.filter(Boolean)) {
    const file = path.join(home, 'tools', 'netcoredbg', 'netcoredbg', exe);
    if (fs.existsSync(file)) return file;
  }
  return null;
}

/// The debugger: the nemerle.debugger.path setting, else netcoredbg on PATH, else the one the installer fetched;
/// null when there is none.
function debuggerPath(settings) {
  // a .exe on Windows: a .cmd wrapper cannot be started as a debug adapter
  const onPath = process.platform === 'win32' ? findOnPath('netcoredbg', ['.exe']) : findOnPath('netcoredbg');
  return settings.get('path') || onPath || installedDebugger();
}

/// The project in a folder: its .nproj file's name, output and target settings (the binary is out/<name>.dll, or
/// out/<name>.exe for a .NET Framework target).
function projectOf(folder) {
  try {
    const file = fs.readdirSync(folder).find(f => f.endsWith('.nproj'));
    if (!file) return null;
    const text = fs.readFileSync(path.join(folder, file), 'utf8');
    if (text.trimStart().startsWith('<')) {
      const m = /<AssemblyName>([^<]+)<\/AssemblyName>/.exec(text);
      const framework = /<TargetFrameworkVersion>/.test(text);
      return { file: path.join(folder, file), name: m ? m[1].trim() : path.basename(file, '.nproj'), output: 'out', framework };
    }
    const name = /^\s*name\s*=\s*"([^"]+)"/m.exec(text);
    const output = /^\s*output\s*=\s*"([^"]+)"/m.exec(text);
    const target = /^\s*target\s*=\s*"([^"]+)"/m.exec(text);
    const framework = !!target && /^net4\d+$/i.test(target[1]);
    return { file: path.join(folder, file), name: name ? name[1] : path.basename(file, '.nproj'), output: output ? output[1] : 'out', framework };
  } catch { return null; }
}

/// A launch configuration completed for the folder's project: program (out/<name>.dll), cwd, and a build first.
function completeConfiguration(folder, config) {
  const project = folder ? projectOf(folder) : null;
  const filled = Object.assign({}, config);
  if (!filled.type) filled.type = 'nemerle';
  if (!filled.request) filled.request = 'launch';
  if (!filled.name) filled.name = 'Nemerle: run the project';
  if (!filled.program && project) filled.program = path.join(folder, project.output, project.name + (project.framework ? '.exe' : '.dll'));
  if (!filled.cwd && folder) filled.cwd = folder;
  if (filled.build === undefined) filled.build = !!project;
  if (!filled.args) filled.args = [];
  return filled;
}

/// What the debug adapter gets: netcoredbg starts a .NET program through dotnet, so the program becomes its argument.
function adapterConfiguration(config, dotnet) {
  const managed = /\.(exe|dll)$/i.test(config.program);
  return Object.assign({}, config, managed ? { program: dotnet, args: [config.program].concat(config.args || []) } : {});
}

function registerDebugger(context) {
  const settings = () => vscode.workspace.getConfiguration('nemerle.debugger');
  context.subscriptions.push(vscode.debug.registerDebugConfigurationProvider('nemerle', {
    provideDebugConfigurations: folder => [completeConfiguration(folder && folder.uri.fsPath, {})],
    resolveDebugConfiguration: async (folder, config) => {
      const root = folder ? folder.uri.fsPath : (vscode.workspace.workspaceFolders || [])[0]?.uri.fsPath;
      const filled = completeConfiguration(root, config);
      if (!filled.program) {
        vscode.window.showErrorMessage('Nemerle: no project here to debug (a folder with a .nproj file), and no "program" in the launch configuration.');
        return undefined;
      }
      if (filled.build) {
        const ncc = vscode.workspace.getConfiguration('nemerle').get('ncc.path') || 'ncc';
        try { execFileSync(ncc, ['build', root], { cwd: root, encoding: 'utf8', shell: process.platform === 'win32' }); }
        catch (e) {
          vscode.window.showErrorMessage('Nemerle: the build failed. ' + String(e.stdout || e.message).trim().split('\n').slice(-3).join(' '));
          return undefined;
        }
      }
      return adapterConfiguration(filled, vscode.workspace.getConfiguration('nemerle.dotnet').get('path') || 'dotnet');
    }
  }));
  context.subscriptions.push(vscode.debug.registerDebugAdapterDescriptorFactory('nemerle', {
    createDebugAdapterDescriptor: () => {
      const debugger_ = debuggerPath(settings());
      if (!debugger_) {
        vscode.window.showErrorMessage('Nemerle debugging needs netcoredbg (on PATH, or set nemerle.debugger.path).', 'Get netcoredbg')
          .then(choice => { if (choice) vscode.env.openExternal(vscode.Uri.parse('https://github.com/Samsung/netcoredbg/releases')); });
        return undefined;
      }
      return new vscode.DebugAdapterExecutable(debugger_, ['--interpreter=vscode']);
    }
  }));
}

function activate(context) {
  if (vscode.debug) registerDebugger(context);
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

module.exports = { activate, deactivate, _test: { serverCommand, hasDotnet10, debuggerPath, installedDebugger, projectOf, completeConfiguration, adapterConfiguration } };
