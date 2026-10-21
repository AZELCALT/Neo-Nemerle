#!/usr/bin/env python3
"""Debug a Nemerle program the way the VS Code / VSCodium extension does, and check what the debugger sees.

Usage: check-debugger.py --toolchain DIR [--netcoredbg PATH] [--extension DIR]

The extension's own launch configuration (from tools/language-server/vscode/extension.js, through a stub of the
`vscode` API) is sent to netcoredbg in its debug adapter mode (--interpreter=vscode), as the editor does. The checks:
a breakpoint in a function and one in top-level code are hit at their lines, the call stack names the source lines,
and parameters, locals and top-level state have their values. Without netcoredbg (on PATH, NETCOREDBG, or
--netcoredbg) the check is skipped."""
import argparse, json, os, pathlib, queue, shutil, subprocess, tempfile, threading, time

p = argparse.ArgumentParser()
p.add_argument('--toolchain', type=pathlib.Path, required=True)
p.add_argument('--netcoredbg', type=pathlib.Path)
p.add_argument('--extension', type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[1] / 'tools/language-server/vscode')
a = p.parse_args()
debugger = a.netcoredbg or (pathlib.Path(os.environ['NETCOREDBG']) if os.environ.get('NETCOREDBG') else None) or shutil.which('netcoredbg')
if not debugger:
    # fetched once into the cache the toolchain uses for reference packs
    import platform, urllib.request, tarfile, zipfile, io
    data = os.environ.get('LOCALAPPDATA') if os.name == 'nt' else (os.environ.get('XDG_DATA_HOME') or str(pathlib.Path.home() / '.local/share'))
    home = pathlib.Path(data) / 'Nemerle/tools/netcoredbg'
    exe = home / 'netcoredbg' / ('netcoredbg.exe' if os.name == 'nt' else 'netcoredbg')
    if not exe.exists():
        asset = {'Linux': 'netcoredbg-linux-amd64.tar.gz', 'Windows': 'netcoredbg-win64.zip', 'Darwin': 'netcoredbg-osx-amd64.tar.gz'}.get(platform.system())
        try:
            blob = urllib.request.urlopen('https://github.com/Samsung/netcoredbg/releases/latest/download/' + asset, timeout=120).read()
            home.mkdir(parents=True, exist_ok=True)
            if asset.endswith('.zip'): zipfile.ZipFile(io.BytesIO(blob)).extractall(home)
            else: tarfile.open(fileobj=io.BytesIO(blob)).extractall(home)
        except Exception as error:
            print('SKIP: no netcoredbg, and it cannot be fetched: %s' % error); raise SystemExit(0)
    debugger = exe
if not pathlib.Path(debugger).exists():
    print('SKIP: no netcoredbg at %s' % debugger); raise SystemExit(0)
tc = a.toolchain.resolve()
work = pathlib.Path(tempfile.mkdtemp(prefix='nemerle-debugger-'))
checks = 0

def check(ok, message):
    global checks
    if not ok: raise SystemExit('FAIL: ' + message)
    checks += 1

try:
    prog = work / 'prog'; prog.mkdir()
    (prog / 'prog.nproj').write_text('name = "prog"\n[compiler]\noptions = ["-debug+"]\n')
    source = ('Square(n : int) : int\n{\n  def result = n * n;\n  result\n}\n\n'
              'def xs = [1, 2, 3];\ndef total = xs.FoldLeft(0, (x, acc) => acc + Square(x));\nSystem.Console.WriteLine($"total $total");\n')
    (prog / 'main.n').write_text(source)
    # the extension's launch configuration for this folder (it would build first; here the build runs below)
    harness = work / 'harness.js'
    harness.write_text('''
const Module = require('module'); const original = Module._load;
Module._load = function (request, parent, isMain) {
  if (request === 'vscode-languageclient/node') return { LanguageClient: class { start() {} stop() {} } };
  if (request === 'vscode') return { workspace: { getConfiguration: () => ({ get: () => undefined }) }, window: {}, env: {}, Uri: {} };
  return original.apply(this, arguments);
};
const ext = require(process.argv[2]);
const config = ext._test.completeConfiguration(process.argv[3], {});
console.log(JSON.stringify({ config, adapter: ext._test.adapterConfiguration(config, 'dotnet') }));
''')
    both = json.loads(subprocess.run(['node', str(harness), str(a.extension / 'extension.js'), str(prog)],
                                     capture_output=True, text=True, check=True).stdout)
    config, adapter = both['config'], both['adapter']
    check(config['type'] == 'nemerle' and config['program'] == str(prog / 'out/prog.dll') and config['build'] is True,
          'the extension\'s launch configuration: %s' % config)
    r = subprocess.run([str(tc / 'ncc'), 'build', str(prog)], capture_output=True, text=True)
    check(r.returncode == 0 and (prog / 'out/prog.pdb').exists(), 'the build with debug information: ' + r.stdout + r.stderr)

    # the debug adapter session
    proc = subprocess.Popen([str(debugger), '--interpreter=vscode'], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    inbox = queue.Queue(); seq = [0]
    def reader(out, inbox):
        while True:
            length = None
            while True:
                line = out.readline()
                if not line: inbox.put(None); return
                line = line.strip()
                if not line: break
                if line.lower().startswith(b'content-length:'): length = int(line.split(b':')[1])
            inbox.put(json.loads(out.read(length)))
    threading.Thread(target=reader, args=(proc.stdout, inbox), daemon=True).start()
    def send(command, arguments=None):
        seq[0] += 1
        body = json.dumps({'seq': seq[0], 'type': 'request', 'command': command, 'arguments': arguments or {}}).encode()
        proc.stdin.write(b'Content-Length: %d\r\n\r\n' % len(body) + body); proc.stdin.flush()
        return seq[0]
    def wait(test, what, timeout=60):
        deadline = time.time() + timeout
        while time.time() < deadline:
            try: m = inbox.get(timeout=1)
            except queue.Empty: continue
            if m is None: raise SystemExit('FAIL: the debugger ended while waiting for ' + what)
            if test(m): return m
        raise SystemExit('FAIL: timed out waiting for ' + what)
    def request(command, arguments=None):
        n = send(command, arguments)
        m = wait(lambda m: m.get('type') == 'response' and m.get('request_seq') == n, command)
        check(m.get('success'), command + ' failed: %s' % m)
        return m.get('body') or {}
    request('initialize', {'adapterID': 'nemerle', 'linesStartAt1': True, 'columnsStartAt1': True, 'pathFormat': 'path'})
    # exactly what the extension hands the adapter (the program run through dotnet)
    check(adapter['program'] == 'dotnet' and adapter['args'][0] == config['program'], 'the adapter configuration: %s' % adapter)
    n = send('launch', adapter)
    wait(lambda m: m.get('event') == 'initialized' or (m.get('type') == 'response' and m.get('request_seq') == n), 'initialized')
    bps = request('setBreakpoints', {'source': {'path': str(prog / 'main.n')}, 'breakpoints': [{'line': 4}, {'line': 9}]})
    check(len(bps.get('breakpoints', [])) == 2, 'two breakpoints set: %s' % bps)
    request('configurationDone')
    stopped = wait(lambda m: m.get('event') == 'stopped', 'the first breakpoint')
    thread = stopped['body']['threadId']
    frames = request('stackTrace', {'threadId': thread})['stackFrames']
    check(frames[0]['line'] == 4 and frames[0]['source']['path'].endswith('main.n') and 'Square' in frames[0]['name'],
          'stopped in Square at main.n:4: %s' % frames[0])
    check(any(f.get('line') == 8 and 'Main' in f['name'] for f in frames), 'the call stack reaches the top-level code at line 8: %s' % [(f['name'], f.get('line')) for f in frames])
    def values(frame):
        found = {}
        for scope in request('scopes', {'frameId': frame['id']})['scopes']:
            for v in request('variables', {'variablesReference': scope['variablesReference']})['variables']: found[v['name']] = v['value']
        return found
    local = values(frames[0])
    check(local.get('n') == '1' and local.get('result') == '1', 'the parameter and the local: %s' % local)
    # a step past the function's last line stops at its closing brace (the result is kept out of the stack there)
    request('next', {'threadId': thread})
    stepped = wait(lambda m: m.get('event') == 'stopped', 'the step to the closing brace')
    frame = request('stackTrace', {'threadId': stepped['body']['threadId']})['stackFrames'][0]
    check(frame['line'] == 5 and 'Square' in frame['name'], 'a step past `result` lands on the closing brace (main.n:5): %s' % frame)
    print('PASS: a breakpoint in a function: its line, the call stack with lines, parameters and locals; stepping to its end')
    request('setBreakpoints', {'source': {'path': str(prog / 'main.n')}, 'breakpoints': [{'line': 9}]})
    request('continue', {'threadId': thread})
    stopped = wait(lambda m: m.get('event') == 'stopped', 'the top-level breakpoint')
    frames = request('stackTrace', {'threadId': stopped['body']['threadId']})['stackFrames']
    check(frames[0]['line'] == 9, 'stopped in the top-level code at main.n:9: %s' % frames[0])
    def evaluate(expression):
        return request('evaluate', {'expression': expression, 'frameId': frames[0]['id'], 'context': 'watch'})['result']
    check(evaluate('total') == '14', 'top-level state `total`')
    check('Cons' in evaluate('xs'), 'a top-level list `xs`: ' + evaluate('xs'))
    print('PASS: a breakpoint in top-level code: its line and the top-level state')
    request('continue', {'threadId': stopped['body']['threadId']})
    wait(lambda m: m.get('event') in ('exited', 'terminated'), 'the end')
    try: request('disconnect', {})
    except SystemExit: pass
    proc.kill()

    # an async function: a breakpoint after an `await' (the code resumed on another thread), its locals (the state
    # machine's fields, named as C#'s), and a step over the next `await' to the line after it
    aprog = work / 'asyncprog'; aprog.mkdir()
    (aprog / 'asyncprog.nproj').write_text('name = "asyncprog"\n[compiler]\noptions = ["-debug+"]\n')
    (aprog / 'main.n').write_text('using System.Threading.Tasks;\n\nasync Compute(n : int) : Task[int]\n{\n  def start = n * 2;\n'
                                  '  await Task.Delay(10);\n  def middle = start + 1;\n  await Task.Delay(10);\n  middle * 10\n}\n\n'
                                  'System.Console.WriteLine(await Compute(4));\n'
                                  'def scaled = async (k : int) =>\n{\n  def shifted = k + 1;\n  await Task.Delay(10);\n  shifted * 3\n};\n'
                                  'System.Console.WriteLine(await scaled(4));\n'
                                  'async Scaled(n : int) : Task[int]\n{\n  def factor = n + 1;\n  def scale = x => x * factor;\n'
                                  '  await Task.Delay(10);\n  def doubled = scale(2);\n  doubled\n}\n'
                                  'System.Console.WriteLine(await Scaled(4))\n')
    r = subprocess.run([str(tc / 'ncc'), 'build', str(aprog)], capture_output=True, text=True)
    check(r.returncode == 0, 'the async program\'s build: ' + r.stdout + r.stderr)
    proc = subprocess.Popen([str(debugger), '--interpreter=vscode'], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    inbox = queue.Queue()
    threading.Thread(target=reader, args=(proc.stdout, inbox), daemon=True).start()
    request('initialize', {'adapterID': 'nemerle', 'linesStartAt1': True, 'columnsStartAt1': True, 'pathFormat': 'path'})
    n = send('launch', {'program': 'dotnet', 'args': [str(aprog / 'out/asyncprog.dll')], 'cwd': str(aprog), 'justMyCode': True})
    wait(lambda m: m.get('event') == 'initialized' or (m.get('type') == 'response' and m.get('request_seq') == n), 'initialized')
    request('setBreakpoints', {'source': {'path': str(aprog / 'main.n')}, 'breakpoints': [{'line': 7}, {'line': 17}, {'line': 22}]})
    request('configurationDone')
    stopped = wait(lambda m: m.get('event') == 'stopped', 'the breakpoint after an await')
    thread = stopped['body']['threadId']
    frames = request('stackTrace', {'threadId': thread})['stackFrames']
    check(frames[0]['line'] == 7 and 'Compute' in frames[0]['name'], 'stopped in Compute after its await (main.n:7): %s' % frames[0])
    local = values(frames[0])
    check(local.get('start') == '8' and local.get('n') == '4' and not any(k.startswith('_N_') or k.startswith('<') for k in local),
          'the async function\'s parameter and local, and none of its state machine\'s own fields: %s' % local)
    request('next', {'threadId': thread})
    stepped = wait(lambda m: m.get('event') == 'stopped', 'the step to the await')
    request('next', {'threadId': stepped['body']['threadId']})
    stepped = wait(lambda m: m.get('event') == 'stopped', 'the step over the await')
    frame = request('stackTrace', {'threadId': stepped['body']['threadId']})['stackFrames'][0]
    check(frame['line'] == 9 and 'Compute' in frame['name'], 'a step over an await lands on the line after it (main.n:9): %s' % frame)
    check(values(frame).get('middle') == '9', 'the local set before the await')
    print('PASS: an async function: a breakpoint after an await, its locals, and a step over an await')
    # an async lambda (its state machine a struct, as C#'s): a breakpoint after its await, its parameter and local
    request('continue', {'threadId': stepped['body']['threadId']})
    stopped = wait(lambda m: m.get('event') == 'stopped', 'the breakpoint in the async lambda')
    frame = request('stackTrace', {'threadId': stopped['body']['threadId']})['stackFrames'][0]
    check(frame['line'] == 17, 'stopped in the async lambda after its await (main.n:17): %s' % frame)
    local = values(frame)
    check(local.get('shifted') == '5' and local.get('k') == '4', 'the async lambda\'s parameter and local: %s' % local)
    print('PASS: an async lambda: a breakpoint after an await, and its locals')
    # a function with a lambda in it: the local the lambda uses is its display class's (as C#'s); each statement is
    # a step, the lambda's making and its call too
    request('continue', {'threadId': stopped['body']['threadId']})
    stopped = wait(lambda m: m.get('event') == 'stopped', 'the breakpoint in the function with a lambda')
    frame = request('stackTrace', {'threadId': stopped['body']['threadId']})['stackFrames'][0]
    check(frame['line'] == 22, 'stopped in Scaled (main.n:22): %s' % frame)
    lines = []
    for _ in range(4):
        request('next', {'threadId': stopped['body']['threadId']})
        stopped = wait(lambda m: m.get('event') == 'stopped', 'a step in Scaled')
        frame = request('stackTrace', {'threadId': stopped['body']['threadId']})['stackFrames'][0]
        lines.append(frame['line'])
    check(lines == [23, 24, 25, 26], 'the steps through Scaled, its lambda\'s making and call included: %s' % lines)
    local = values(frame)
    check(local.get('factor') == '5' and local.get('doubled') == '10' and local.get('n') == '4',
          'Scaled\'s locals, the one in its display class too: %s' % local)
    print('PASS: a function with a lambda in it: its steps, and its locals (one in its display class)')
    request('continue', {'threadId': stopped['body']['threadId']})
    wait(lambda m: m.get('event') in ('exited', 'terminated'), 'the end of the async program')
    try: request('disconnect', {})
    except SystemExit: pass
    proc.kill()
    print('PASS: %d debugger checks (netcoredbg, the extension\'s launch configuration)' % checks)
finally:
    shutil.rmtree(work, ignore_errors=True)
