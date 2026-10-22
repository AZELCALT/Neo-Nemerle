#!/usr/bin/env python3
"""Drive the Nemerle language server over stdio like an editor and check its answers.

Usage: check-language-server.py --server <out>/nemerle-lsp [--log FILE]
Build the server first with build-language-server.py."""
import argparse, json, os, pathlib, shutil, subprocess, tempfile, threading, queue, time, sys

p = argparse.ArgumentParser()
p.add_argument('--server', type=pathlib.Path, required=True)
p.add_argument('--log', type=pathlib.Path)
p.add_argument('--timeout', type=float, default=120)
a = p.parse_args()
here = pathlib.Path(__file__).resolve().parent
checks = 0

def check(ok, message):
    global checks
    if not ok: raise SystemExit('FAIL: ' + message)
    checks += 1

# the servers keep their symbol index in a data folder of the test's own, not the user's
testdata = tempfile.mkdtemp(prefix='nemerle-lsp-data-')
class Client:
    def __init__(self, log=None, env=None):
        log = log or a.log
        args = [str(a.server)] + (['--log', str(log)] if log else [])
        env = env or dict(os.environ, XDG_DATA_HOME=testdata, LOCALAPPDATA=testdata)
        self.proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=env)
        self.next_id = 0; self.inbox = queue.Queue(); self.diagnostics = {}
        threading.Thread(target=self.reader, daemon=True).start()
    def reader(self):
        out = self.proc.stdout
        while True:
            length = None
            while True:
                line = out.readline()
                if not line: self.inbox.put(None); return
                line = line.strip()
                if not line: break
                if line.lower().startswith(b'content-length:'): length = int(line.split(b':')[1])
            self.inbox.put(json.loads(out.read(length)))
    def send(self, message):
        body = json.dumps(message).encode()
        self.proc.stdin.write(b'Content-Length: %d\r\n\r\n' % len(body) + body); self.proc.stdin.flush()
    def notify(self, method, params): self.send({'jsonrpc': '2.0', 'method': method, 'params': params})
    def pump(self, until, what):
        deadline = time.time() + a.timeout
        while time.time() < deadline:
            try: m = self.inbox.get(timeout=1)
            except queue.Empty: continue
            if m is None: raise SystemExit('FAIL: server closed the stream while waiting for ' + what)
            if m.get('method') == 'textDocument/publishDiagnostics':
                self.diagnostics[m['params']['uri']] = m['params']
            r = until(m)
            if r is not None: return r
        raise SystemExit('FAIL: timed out waiting for ' + what)
    def request(self, method, params):
        self.next_id += 1; rid = self.next_id
        self.send({'jsonrpc': '2.0', 'id': rid, 'method': method, 'params': params})
        m = self.pump(lambda m: m if m.get('id') == rid and 'method' not in m else None, method)
        if 'error' in m: raise SystemExit('FAIL: %s returned %s' % (method, m['error']))
        return m['result']
    def wait_diagnostics(self, uri, version):
        return self.pump(lambda m: m['params'] if m.get('method') == 'textDocument/publishDiagnostics'
                         and m['params']['uri'] == uri and m['params'].get('version') == version else None, 'diagnostics of %s v%d' % (uri, version))

def decode(tokens, legend):
    out = []; line = 0; char = 0; d = tokens['data']
    for i in range(0, len(d), 5):
        dl, dc, length, kind, _ = d[i:i + 5]
        line += dl; char = dc if dl else char + dc
        out.append((line, char, length, legend[kind]))
    return out

def offset_of(text, needle, nth=0):
    pos = -1
    for _ in range(nth + 1): pos = text.index(needle, pos + 1)
    return pos

def position(text, offset):
    line = text.count('\n', 0, offset); return line, offset - (text.rfind('\n', 0, offset) + 1)

def covered(tokens, text, offset):
    l, c = position(text, offset)
    return [t for t in tokens if t[0] == l and t[1] <= c < t[1] + t[2]]

c = Client()
init = c.request('initialize', {'processId': None, 'rootUri': None, 'capabilities': {}})
caps = init['capabilities']; legend = caps['semanticTokensProvider']['legend']['tokenTypes']
sync = caps['textDocumentSync']
check(sync['change'] == 2 and sync['openClose'] and 'save' in sync and caps['foldingRangeProvider'] and caps['documentSymbolProvider'],
      'capabilities (changed ranges, and saves for the index): %s' % sync)
check(caps.get('documentFormattingProvider') and caps.get('documentRangeFormattingProvider'), 'formatting capabilities: %s' % caps)
check(caps['hoverProvider'] and caps['definitionProvider'], 'hover and definition capabilities')
c.notify('initialized', {})

def open_doc(name, text, version=1):
    uri = 'file:///lsp-check/' + name
    c.notify('textDocument/didOpen', {'textDocument': {'uri': uri, 'languageId': 'nemerle', 'version': version, 'text': text}})
    return uri

def analyze(uri, text, version):
    diags = c.wait_diagnostics(uri, version)['diagnostics']
    tokens = decode(c.request('textDocument/semanticTokens/full', {'textDocument': {'uri': uri}}), legend)
    folds = c.request('textDocument/foldingRange', {'textDocument': {'uri': uri}})
    symbols = c.request('textDocument/documentSymbol', {'textDocument': {'uri': uri}})
    return diags, tokens, folds, symbols

def names(symbols):
    for s in symbols:
        yield s['name']; yield from names(s.get('children', []))

# 1. plain Nemerle
plain = 'using System;\n// greeting\nmodule Program\n{\n  Main() : void\n  {\n    Console.WriteLine("hello");\n  }\n}\n'
uri = open_doc('plain.n', plain)
diags, tokens, folds, symbols = analyze(uri, plain, 1)
check([d for d in diags if d['severity'] == 1] == [], 'plain file has no errors: %s' % diags)
check(any(t[3] == 'keyword' for t in covered(tokens, plain, offset_of(plain, 'module'))), 'keyword token for module')
check(any(t[3] == 'string' for t in covered(tokens, plain, offset_of(plain, '"hello"'))), 'string token')
check(any(t[3] == 'comment' for t in covered(tokens, plain, offset_of(plain, '// greeting'))), 'comment token')
check({'Program', 'Main'} <= set(names(symbols)), 'symbols Program/Main: %s' % list(names(symbols)))
check(any(f['startLine'] == 2 and f['endLine'] == 8 for f in folds), 'fold for module Program: %s' % folds)
print('PASS: plain Nemerle file (main parser tokens, symbols, folding)')

# 2. grammar + space, from the compiler's native example
example = (here / 'NativeDialectScopeExample.n').read_text()
uri = open_doc('example.n', example)
diags, tokens, folds, symbols = analyze(uri, example, 1)
check([d for d in diags if d['severity'] == 1] == [], 'example has no errors: %s' % diags)
check(any(t[3] == 'keyword' for t in covered(tokens, example, offset_of(example, 'syntax module'))), 'Nitra keyword inside grammar block')
check(covered(tokens, example, offset_of(example, '"answer"', 0)) != [], 'Nitra literal token inside grammar block')
check(covered(tokens, example, offset_of(example, 'answer }')) != [], 'token inside the space body (Nitra parse of the compiled grammar)')
check(any(t[3] == 'keyword' for t in covered(tokens, example, offset_of(example, 'def doubled'))), 'Nemerle keyword after the grammar block')
glines = position(example, offset_of(example, 'grammar Demo'))[0]
check(any(f['startLine'] == glines for f in folds), 'fold for the grammar block')
syms = set(names(symbols))
check('grammar Demo' in syms and any(n.startswith('space') for n in syms), 'symbols: %s' % syms)
print('PASS: grammar/space file (unmodified Nitra highlighting of grammar and space, Nemerle around them)')

# 3. broken space body and broken grammar rule: recovery keeps a tree
broken = example.replace('space Demo [A] { answer }', 'space Demo [A] { answr }')
c.notify('textDocument/didChange', {'textDocument': {'uri': uri, 'version': 2}, 'contentChanges': [{'text': broken}]})
diags, tokens, folds, symbols = analyze(uri, broken, 2)
body = offset_of(broken, 'answr')
space_errors = [d for d in diags if d['severity'] == 1 and d.get('source') == 'space']
check(space_errors and all(d['range']['start']['line'] == position(broken, body)[0] for d in space_errors), 'space error on the space line: %s' % diags)
check(any(t[3] == 'keyword' for t in covered(tokens, broken, offset_of(broken, 'def doubled'))), 'Nemerle tokens still present')
broken2 = example.replace('[StartRule] syntax Input = "answer"', '[StartRule] syntax Input = = "answer"')
c.notify('textDocument/didChange', {'textDocument': {'uri': uri, 'version': 3}, 'contentChanges': [{'text': broken2}]})
diags, tokens, folds, symbols = analyze(uri, broken2, 3)
grammar_errors = [d for d in diags if d['severity'] == 1 and d.get('source') in ('nitra', 'grammar')]
check(grammar_errors != [], 'broken grammar reported: %s' % diags)
check(any(t[3] == 'keyword' for t in covered(tokens, broken2, offset_of(broken2, 'syntax module'))), 'grammar block still highlighted after the error (recovery)')
print('PASS: broken space body and broken grammar rule (diagnostics located, recovery keeps highlighting)')

# 4. repair: diagnostics clear again
c.notify('textDocument/didChange', {'textDocument': {'uri': uri, 'version': 4}, 'contentChanges': [{'text': example}]})
diags = c.wait_diagnostics(uri, 4)['diagnostics']
check([d for d in diags if d['severity'] == 1] == [], 'repaired file has no errors: %s' % diags)
c.notify('textDocument/didClose', {'textDocument': {'uri': uri}})

# 5. file modules are the default: top-level functions, mask, `using path.to.file`; namespace blocks are rejected
fm = 'using util.text;\npublic Main() : void\n{\n  System.Console.WriteLine(Shout("x"));\n}\nmask helpers\n{\n  public Two() : int { 2 }\n}\n'
uri = open_doc('app/main.n', fm)
diags, tokens, folds, symbols = analyze(uri, fm, 1)
check([d for d in diags if d['severity'] == 1] == [], 'file module has no errors: %s' % diags)
check({'Main', 'helpers', 'Two'} <= set(names(symbols)), 'file module symbols at top level: %s' % list(names(symbols)))
check(any(t[3] == 'keyword' for t in covered(tokens, fm, offset_of(fm, 'mask'))), 'mask is a keyword in a file module')
ns = 'namespace Foo\n{\n  public module M { }\n}\n'
uri = open_doc('app/ns.n', ns)
diags = c.wait_diagnostics(uri, 1)['diagnostics']
check(any('namespace declarations are not allowed' in d['message'] for d in diags), 'namespace block rejected: %s' % diags)
print('PASS: file modules by default (top-level functions, mask, using a file; namespace rejected)')
c.request('shutdown', None); c.notify('exit', None)
check(c.proc.wait(timeout=30) == 0, 'clean exit')

# 6. a workspace: typed diagnostics across files (`using`, an exported type), hover and go-to-definition
work = pathlib.Path(tempfile.mkdtemp(prefix='nemerle-lsp-ws-'))
try:
    (work / 'app').mkdir()
    pen = 'export class Pen\n{\n  public Width : int = 3;\n}\n'
    (work / 'app/pen.n').write_text(pen)
    main = 'using app.pen;\n\ndef p = Pen();\nSystem.Console.WriteLine(p.Width);\ndef n : int = "oops";\n'
    (work / 'main.n').write_text(main)
    c = Client()
    c.request('initialize', {'processId': None, 'rootUri': work.as_uri(), 'capabilities': {}})
    c.notify('initialized', {})
    uri = (work / 'main.n').as_uri()
    c.notify('textDocument/didOpen', {'textDocument': {'uri': uri, 'languageId': 'nemerle', 'version': 1, 'text': main}})
    typed = c.pump(lambda m: m['params']['diagnostics'] if m.get('method') == 'textDocument/publishDiagnostics'
                   and m['params']['uri'] == uri and any(d.get('source') == 'nemerle' for d in m['params']['diagnostics']) else None,
                   'typed diagnostics')
    error = [d for d in typed if d.get('source') == 'nemerle' and d['severity'] == 1]
    check(len(error) == 1 and error[0]['range']['start']['line'] == 4 and 'string' in error[0]['message'], 'type error located: %s' % typed)
    # repair it: the typed error clears, and the facts come back for the new text
    fixed = main.replace('"oops"', '4')
    c.notify('textDocument/didChange', {'textDocument': {'uri': uri, 'version': 2}, 'contentChanges': [{'text': fixed}]})
    deadline = time.time() + a.timeout; hover = None
    while time.time() < deadline:
        l, ch = position(fixed, offset_of(fixed, 'Width'))
        hover = c.request('textDocument/hover', {'textDocument': {'uri': uri}, 'position': {'line': l, 'character': ch}})
        if hover and 'Pen.Width : int' in hover['contents']['value']: break
        time.sleep(0.5)
    check(hover and 'Pen.Width : int' in hover['contents']['value'], 'hover on p.Width: %s' % hover)
    check(not any(d['severity'] == 1 for d in c.diagnostics[uri]['diagnostics']), 'repaired workspace has no errors: %s' % c.diagnostics[uri])
    l, ch = position(fixed, offset_of(fixed, 'Pen()'))
    target = c.request('textDocument/definition', {'textDocument': {'uri': uri}, 'position': {'line': l, 'character': ch}})
    check(target and target['uri'].endswith('/app/pen.n') and target['range']['start']['line'] == 0, 'definition of Pen() is in app/pen.n: %s' % target)
    l, ch = position(fixed, offset_of(fixed, 'p.Width'))
    target = c.request('textDocument/definition', {'textDocument': {'uri': uri}, 'position': {'line': l, 'character': ch}})
    check(target and target['uri'] == uri and target['range']['start']['line'] == 2, 'definition of p is its binding: %s' % target)
    print('PASS: workspace (typed diagnostics through using/export, hover, go-to-definition)')
    # completion: members after a dot, names in scope
    v = 3
    def edit(text):
        global v
        v += 1
        c.notify('textDocument/didChange', {'textDocument': {'uri': uri, 'version': v}, 'contentChanges': [{'text': text}]})
        return text
    typing = edit(fixed + 'def w = p.\n')
    l, ch = position(typing, len(typing) - 1)
    items = [i['label'] for i in c.request('textDocument/completion', {'textDocument': {'uri': uri}, 'position': {'line': l, 'character': ch}})['items']]
    check('Width' in items and 'ReferenceEquals' not in items, 'completion after `p.`: %s' % items)
    typing = edit(fixed + 'def w = pe\n')
    l, ch = position(typing, len(typing) - 1)
    items = [i['label'] for i in c.request('textDocument/completion', {'textDocument': {'uri': uri}, 'position': {'line': l, 'character': ch}})['items']]
    check(items == [] or all(i.lower().startswith('pe') or 'pe' in i.lower() for i in items), 'completion of `pe`: %s' % items)
    typing = edit(fixed + 'def w = Pe\n')
    l, ch = position(typing, len(typing) - 1)
    items = [i['label'] for i in c.request('textDocument/completion', {'textDocument': {'uri': uri}, 'position': {'line': l, 'character': ch}})['items']]
    check('Pen' in items, 'completion of `Pe` offers the exported type: %s' % items)
    # another unfinished line in the file: the typed completion still gets to the cursor
    typing = edit(fixed + 'def broken = (1 + ;\ndef w = p.\n')
    l, ch = position(typing, len(typing) - 1)
    items = [i['label'] for i in c.request('textDocument/completion', {'textDocument': {'uri': uri}, 'position': {'line': l, 'character': ch}})['items']]
    check('Width' in items, 'completion after `p.` with another broken line: %s' % items)
    # keywords and syntax forms, with or without a compile
    typing = edit(fixed + 'ma\n')
    l, ch = position(typing, len(typing) - 1)
    result = c.request('textDocument/completion', {'textDocument': {'uri': uri}, 'position': {'line': l, 'character': ch}})['items']
    match = [i for i in result if i['label'] == 'match' and i.get('insertTextFormat') == 2]
    check(match and '| ${2:pattern}' in match[0]['insertText'], 'the match form as a snippet: %s' % result)
    check(any(i['label'] == 'mask' and i['kind'] == 14 for i in result), 'keywords for the prefix: %s' % [i['label'] for i in result])
    typing = edit(fixed + 'def x = Pen().\n')
    l, ch = position(typing, len(typing) - 1)
    result = c.request('textDocument/completion', {'textDocument': {'uri': uri}, 'position': {'line': l, 'character': ch}})['items']
    check(not any(i['kind'] in (14, 15) for i in result), 'no keywords after a dot: %s' % [i['label'] for i in result])
    typing = edit(fixed + 'asy\n')
    l, ch = position(typing, len(typing) - 1)
    result = c.request('textDocument/completion', {'textDocument': {'uri': uri}, 'position': {'line': l, 'character': ch}})['items']
    check(any(i['label'] == 'async' and i.get('insertTextFormat') == 2 and 'Task[' in i['insertText'] for i in result),
          'the async function form: %s' % [i['label'] for i in result])
    # an async function: no errors, and hover where its locals are declared and used
    typing = edit(fixed + 'async Twice(n : int) : System.Threading.Tasks.Task[int]\n{\n  def got = await System.Threading.Tasks.Task.FromResult(n);\n  got * 2\n}\n')
    deadline = time.time() + a.timeout; hover = None
    while time.time() < deadline:
        l, ch = position(typing, offset_of(typing, 'got =') + 1)
        hover = c.request('textDocument/hover', {'textDocument': {'uri': uri}, 'position': {'line': l, 'character': ch}})
        if hover and 'got : int' in hover['contents']['value']: break
        time.sleep(0.5)
    check(hover and 'got : int' in hover['contents']['value'], 'hover where a local of an async function is declared: %s' % hover)
    l, ch = position(typing, offset_of(typing, 'got * 2') + 1)
    hover = c.request('textDocument/hover', {'textDocument': {'uri': uri}, 'position': {'line': l, 'character': ch}})
    check(hover and 'got : int' in hover['contents']['value'], 'hover where it is used: %s' % hover)
    check(not any(d['severity'] == 1 for d in c.diagnostics[uri]['diagnostics']), 'an async function has no errors: %s' % c.diagnostics[uri])
    l, ch = position(typing, offset_of(typing, 'got * 2') + 1)
    renamed = c.request('textDocument/rename', {'textDocument': {'uri': uri}, 'position': {'line': l, 'character': ch}, 'newName': 'value'})
    lines = sorted(e['range']['start']['line'] for e in renamed['changes'][uri])
    check(len(lines) == 2 and len(set(lines)) == 2, 'renaming a local edits its declaration and its use, once each: %s' % renamed)
    edit(fixed)
    print('PASS: completion (members after a dot, names in scope, despite another broken line; keywords and forms)')
    # find-references and rename, over the whole workspace
    l, ch = position(fixed, offset_of(fixed, 'p.Width'))
    refs = c.request('textDocument/references', {'textDocument': {'uri': uri}, 'position': {'line': l, 'character': ch}, 'context': {'includeDeclaration': True}})
    lines = sorted(r['range']['start']['line'] for r in refs)
    check(lines == [2, 3], 'references of p (its declaration and its use): %s' % refs)
    l, ch = position(fixed, offset_of(fixed, 'Width'))
    refs = c.request('textDocument/references', {'textDocument': {'uri': uri}, 'position': {'line': l, 'character': ch}, 'context': {'includeDeclaration': True}})
    check(any(r['uri'].endswith('/app/pen.n') for r in refs) and any(r['uri'] == uri for r in refs), 'references of Width reach app/pen.n: %s' % refs)
    l, ch = position(fixed, offset_of(fixed, 'p.Width'))
    prepared = c.request('textDocument/prepareRename', {'textDocument': {'uri': uri}, 'position': {'line': l, 'character': ch}})
    check(prepared and prepared['placeholder'] == 'p', 'prepareRename on p: %s' % prepared)
    renamed = c.request('textDocument/rename', {'textDocument': {'uri': uri}, 'position': {'line': l, 'character': ch}, 'newName': 'pen'})
    edits = renamed['changes'][uri]
    check(len(edits) == 2 and all(e['newText'] == 'pen' and e['range']['end']['character'] - e['range']['start']['character'] == 1 for e in edits),
          'rename p -> pen edits the two names: %s' % renamed)
    l, ch = position(fixed, offset_of(fixed, 'Width'))
    renamed = c.request('textDocument/rename', {'textDocument': {'uri': uri}, 'position': {'line': l, 'character': ch}, 'newName': 'Thickness'})
    check(set(renamed['changes']) == {uri, (work / 'app/pen.n').as_uri()}, 'rename Width edits both files: %s' % renamed)
    # a type: its declaration, constructor calls and annotations, in every file (not inside strings)
    typed_text = edit(fixed.replace('def p = Pen();', 'def p : Pen = Pen(); // a Pen\ndef label = "Pen";'))
    l, ch = position(typed_text, offset_of(typed_text, 'Pen()'))
    prepared = c.request('textDocument/prepareRename', {'textDocument': {'uri': uri}, 'position': {'line': l, 'character': ch}})
    check(prepared and prepared['placeholder'] == 'Pen', 'prepareRename on a type: %s' % prepared)
    renamed = c.request('textDocument/rename', {'textDocument': {'uri': uri}, 'position': {'line': l, 'character': ch}, 'newName': 'Marker'})
    here = renamed['changes'][uri]; there = renamed['changes'][(work / 'app/pen.n').as_uri()]
    check(len(here) == 2 and len(there) == 1, 'rename Pen -> Marker: the annotation and the call here, the declaration there (not the comment or string): %s' % renamed)
    edit(fixed)
    print('PASS: find-references and rename across files')
    # a script (.ns) in the workspace: the scripting host checks it as nscript compiles it, at its own lines; it is
    # not one of the workspace's modules, so its top-level names do not reach main.n and its errors are its own
    script = 'def greeting = "hi";\nSystem.Console.WriteLine(greeting);\ndef n : int = "two";\n'
    (work / 'tool.ns').write_text(script)
    suri = (work / 'tool.ns').as_uri()
    c.notify('textDocument/didOpen', {'textDocument': {'uri': suri, 'languageId': 'nemerle-script', 'version': 1, 'text': script}})
    found = c.pump(lambda m: m['params']['diagnostics'] if m.get('method') == 'textDocument/publishDiagnostics'
                   and m['params']['uri'] == suri and any(d.get('source') == 'nemerle' for d in m['params']['diagnostics']) else None,
                   'script diagnostics')
    error = [d for d in found if d.get('source') == 'nemerle' and d['severity'] == 1]
    check(len(error) == 1 and error[0]['range']['start']['line'] == 2, 'a .ns script\'s type error, at its line: %s' % found)
    check(not any(d['severity'] == 1 for d in c.diagnostics[uri]['diagnostics']), 'the script does not affect main.n: %s' % c.diagnostics[uri])
    clean = script.replace('"two"', '2')
    c.notify('textDocument/didChange', {'textDocument': {'uri': suri, 'version': 2}, 'contentChanges': [{'text': clean}]})
    deadline = time.time() + a.timeout
    while time.time() < deadline and any(d['severity'] == 1 for d in c.diagnostics.get(suri, {}).get('diagnostics', [{'severity': 1}])):
        c.pump(lambda m: True if m.get('method') == 'textDocument/publishDiagnostics' and m['params']['uri'] == suri else None, 'script recheck')
    check(not any(d['severity'] == 1 for d in c.diagnostics[suri]['diagnostics']), 'the repaired script has no errors: %s' % c.diagnostics[suri])
    # hover, go-to-definition and typed completion in the script, from the scripting host's compilation
    deadline = time.time() + a.timeout; hover = None
    l, ch = position(clean, offset_of(clean, 'greeting', 1))
    while time.time() < deadline:
        hover = c.request('textDocument/hover', {'textDocument': {'uri': suri}, 'position': {'line': l, 'character': ch}})
        if hover and 'greeting' in hover['contents']['value'] and 'string' in hover['contents']['value']: break
        time.sleep(0.5)
    check(hover and 'string' in hover['contents']['value'], 'hover on a script value: %s' % hover)
    target = c.request('textDocument/definition', {'textDocument': {'uri': suri}, 'position': {'line': l, 'character': ch}})
    check(target and target['uri'] == suri and target['range']['start']['line'] == 0, 'definition of a script value is its binding: %s' % target)
    typing = clean + 'def size = greeting.\n'
    c.notify('textDocument/didChange', {'textDocument': {'uri': suri, 'version': 3}, 'contentChanges': [{'text': typing}]})
    l, ch = position(typing, len(typing) - 1)
    items = [i['label'] for i in c.request('textDocument/completion', {'textDocument': {'uri': suri}, 'position': {'line': l, 'character': ch}})['items']]
    check('Length' in items and 'Substring' in items, 'typed completion after `greeting.` in a script: %s' % items[:20])
    typing = clean + 'def other = gree\n'
    c.notify('textDocument/didChange', {'textDocument': {'uri': suri, 'version': 4}, 'contentChanges': [{'text': typing}]})
    l, ch = position(typing, len(typing) - 1)
    items = [i['label'] for i in c.request('textDocument/completion', {'textDocument': {'uri': suri}, 'position': {'line': l, 'character': ch}})['items']]
    check('greeting' in items, 'a script\'s own names are completed: %s' % items[:20])
    print('PASS: a .ns script is checked by the scripting host (its errors at its lines, apart from the workspace; hover, '
          'definition and typed completion)')
    # the symbol index: kept on disk, so a new server answers find-references without checking the workspace again;
    # a saved change checks again only the file and the files that import it, and the uses follow it
    c.request('shutdown', None); c.notify('exit', None); c.proc.wait(timeout=30)
    (work / 'tool.ns').unlink()
    (work / 'main.n').write_text(fixed)   # the repaired text, saved (the index follows the files on disk)
    data = work / 'data'; indexenv = dict(os.environ, XDG_DATA_HOME=str(data), LOCALAPPDATA=str(data))
    def session(logname):
        log = work / logname
        s = Client(log=log, env=indexenv)
        s.request('initialize', {'processId': None, 'rootUri': work.as_uri(), 'capabilities': {}})
        s.notify('initialized', {})
        s.notify('textDocument/didOpen', {'textDocument': {'uri': uri, 'languageId': 'nemerle', 'version': 1, 'text': fixed}})
        return s, log
    def wait_log(log, text):
        deadline = time.time() + a.timeout
        while time.time() < deadline:
            if log.exists() and text in log.read_text(): return True
            time.sleep(0.3)
        return False
    def references_to_width(s, want):
        l, ch = position(fixed, offset_of(fixed, 'p.Width') + 2)
        deadline = time.time() + a.timeout; refs = []
        while time.time() < deadline:
            refs = s.request('textDocument/references', {'textDocument': {'uri': uri}, 'position': {'line': l, 'character': ch}, 'context': {'includeDeclaration': True}})
            if want(refs): break
            time.sleep(0.5)
        return refs
    pen_uri = (work / 'app/pen.n').as_uri()
    both = lambda refs: {r['uri'] for r in refs} == {uri, pen_uri}
    s, log = session('lsp1.log')
    check(wait_log(log, 'index: '), 'the first server builds the index: %s' % (log.read_text() if log.exists() else ''))
    stores = list((data / 'Nemerle/lsp-index').glob('*.json'))
    check(len(stores) == 1 and ':Pen::Width' in stores[0].read_text(), 'the index is kept on disk with symbol ids: %s\n%s\n%s' % (stores, log.read_text(), sorted(str(x) for x in work.rglob('*.json'))))
    refs = references_to_width(s, both)
    check(both(refs), 'references from the index: %s' % refs)
    s.request('shutdown', None); s.notify('exit', None); s.proc.wait(timeout=30)
    s, log = session('lsp2.log')
    refs = references_to_width(s, both)
    check(both(refs), 'a new server answers from the index on disk: %s' % refs)
    check('index: ' not in log.read_text(), 'nothing is checked again when nothing changed: %s' % log.read_text())
    # a change on disk, then a save: pen.n moves down two lines; it and main.n (which imports it) are checked again
    (work / 'app/pen.n').write_text('\n\n' + pen)
    s.notify('textDocument/didSave', {'textDocument': {'uri': pen_uri}})
    check(wait_log(log, 'index: 2 file(s) checked again'), 'a save checks again the file and its importer only: %s' % log.read_text())
    moved = lambda refs: any(r['uri'] == pen_uri and r['range']['start']['line'] == 4 for r in refs)
    refs = references_to_width(s, moved)
    check(moved(refs), 'the uses follow the change: %s' % refs)
    s.request('shutdown', None); s.notify('exit', None); s.proc.wait(timeout=30)
    (work / 'app/pen.n').write_text(pen)
    print('PASS: the symbol index (kept on disk, reused by a new server, checked again only where files changed)')
    c = Client()
    c.request('initialize', {'processId': None, 'rootUri': work.as_uri(), 'capabilities': {}})
    c.notify('initialized', {})
    c.request('shutdown', None); c.notify('exit', None)
    check(c.proc.wait(timeout=30) == 0, 'clean exit')
finally:
    shutil.rmtree(work, ignore_errors=True)
# 8. async code, declarations, $ strings and type renames: hover where a function is declared; completion after a dot
# in an async function (top-level code with an async lambda, which completion types too); the names in a $ string
# that waits at their own places; completion of a name written after a broken line; renaming one of two types of
# the same name (each name means the type its file sees)
lang = pathlib.Path(tempfile.mkdtemp(prefix='nemerle-lsp-lang-'))
try:
    (lang / 'app').mkdir()
    (lang / 'app/pen.n').write_text('public class Pen\n{\n  public Width : int = 3;\n}\n')
    (lang / 'app/ink.n').write_text('// a Pen of its own\npublic class Pen { public Ink : int = 1; }\npublic Make() : int { def p = Pen(); p.Ink }\n')
    code = ('using System;\nusing System.Threading.Tasks;\nusing app.pen;\n\n'
            'async Compute(n : int) : Task[int]\n{\n  def start = n * 2;\n  def scale = x => x * start;\n  await Task.Delay(1);\n  scale(3)\n}\n\n'
            'def lambda = async (k : int) => { await Task.Yield(); k + 1 };\nmutable total = 0;\ndef p : Pen = Pen();\n'
            'Console.WriteLine($"$total $(await Compute(4)) $(await lambda(2)) $(p.Width)")\n')
    (lang / 'main.n').write_text(code)
    c = Client()
    c.request('initialize', {'processId': None, 'rootUri': lang.as_uri(), 'capabilities': {}})
    c.notify('initialized', {})
    luri = (lang / 'main.n').as_uri()
    c.notify('textDocument/didOpen', {'textDocument': {'uri': luri, 'languageId': 'nemerle', 'version': 1, 'text': code}})
    def at(text, needle, nth=0, delta=0):
        l, ch = position(text, offset_of(text, needle, nth) + delta)
        return {'textDocument': {'uri': luri}, 'position': {'line': l, 'character': ch}}
    def hover_text(text, needle, nth=0):
        r = c.request('textDocument/hover', at(text, needle, nth))
        return r['contents']['value'] if r else ''
    deadline = time.time() + a.timeout
    while time.time() < deadline and 'n : int' not in hover_text(code, 'n * 2'): time.sleep(0.5)
    check('main.Compute : int -> System.Threading.Tasks.Task[int]' in hover_text(code, 'Compute'), 'hover where a function is declared: %s' % hover_text(code, 'Compute'))
    check('main.Compute' in hover_text(code, 'Compute(4)') and 'main.lambda' in hover_text(code, 'lambda(2)')
          # (a top-level `mutable' is the top-level code's local there, the module's value elsewhere)
          and ('main.total' in hover_text(code, 'total ', 1) or 'total : int' in hover_text(code, 'total ', 1))
          and 'Pen.Width' in hover_text(code, 'Width)'),
          'the names in a $ string that waits, at their places: %s / %s / %s' % (hover_text(code, 'Compute(4)'), hover_text(code, 'lambda(2)'), hover_text(code, 'total ', 1)))
    def complete_at(text, version, marker):
        c.notify('textDocument/didChange', {'textDocument': {'uri': luri, 'version': version}, 'contentChanges': [{'text': text}]})
        l, ch = position(text, text.index(marker) + len(marker))
        r = c.request('textDocument/completion', {'textDocument': {'uri': luri}, 'position': {'line': l, 'character': ch}})
        return [i['label'] for i in r['items']]
    dotted = code.replace('  scale(3)\n', '  start.\n')
    items = complete_at(dotted, 2, '  start.')
    check('CompareTo' in items and 'ToString' in items, 'completion after a dot in an async function: %s' % items)
    broken = code.replace('mutable total = 0;', 'mutable total = 0;\ndef oops = (;').replace('  scale(3)\n', '  def freshly = 2;\n  fre\n')
    items = complete_at(broken, 3, '  fre')
    check('freshly' in items, 'completion of a name written since, with a broken line elsewhere: %s' % items)
    c.notify('textDocument/didChange', {'textDocument': {'uri': luri, 'version': 4}, 'contentChanges': [{'text': code}]})
    renamed = c.request('textDocument/rename', dict(at(code, 'Pen()'), newName='Marker'))['changes']
    places = {u.rsplit('/', 1)[-1]: sorted((e['range']['start']['line'], e['range']['start']['character']) for e in v) for u, v in renamed.items()}
    check(places.get('main.n') == [(14, 8), (14, 14)] and places.get('pen.n') == [(0, 13)] and 'ink.n' not in places,
          'renaming app.pen.Pen (app.ink.Pen has its name too): its uses and declaration only: %s' % places)
    c.request('shutdown', None); c.notify('exit', None)
    print('PASS: async code, declarations, $ strings that wait, completion after a broken line, and one of two types of a name renamed')
finally:
    shutil.rmtree(lang, ignore_errors=True)
# 9. signature help, document highlight, workspace symbols, inlay hints and meaning-based tokens: for Nemerle code
# from the typed check, for a grammar block from its rules (Nitra's declarations)
more = pathlib.Path(tempfile.mkdtemp(prefix='nemerle-lsp-more-'))
try:
    (more / 'app').mkdir()
    (more / 'app/pen.n').write_text('public class Pen\n{\n  public Width : int = 3;\n'
                                    '  public Scale(by : int, extra : string) : int { Width * by + extra.Length }\n'
                                    '  public Scale(by : int) : int { Width * by }\n}\n')
    code = ('using System;\nusing System.Threading.Tasks;\nusing app.pen;\n\n'
            'async Compute(n : int, label : string) : Task[int]\n{\n  def start = n * 2;\n  def scale = x => x * start;\n'
            '  await Task.Delay(1);\n  scale(3) + label.Length\n}\n\n'
            'def p : Pen = Pen();\nmutable total = 0;\ndef ratio = p.Scale(2) * 1.5;\ntotal += p.Width;\ndef name = "x";\n'
            'Console.WriteLine($"$total $(await Compute(4, name)) $ratio")\n')
    (more / 'main.n').write_text(code)
    gram = ('grammar Calc\n{\n  syntax module Arith\n  {\n    using Nitra.Core;\n    [StartRule] syntax Start = Expr;\n'
            '    syntax Expr = Term "+" Expr;\n    syntax Term = Number;\n    regex Number = [\'0\'..\'9\']+;\n  }\n}\n')
    (more / 'calc.n').write_text(gram)
    c = Client()
    caps = c.request('initialize', {'processId': None, 'rootUri': more.as_uri(), 'capabilities': {}})['capabilities']
    check(caps.get('documentHighlightProvider') and caps.get('workspaceSymbolProvider') and caps.get('inlayHintProvider')
          and '(' in caps['signatureHelpProvider']['triggerCharacters'], 'the capabilities: %s' % caps)
    legend = caps['semanticTokensProvider']['legend']['tokenTypes']
    c.notify('initialized', {})
    muri = (more / 'main.n').as_uri(); guri = (more / 'calc.n').as_uri()
    c.notify('textDocument/didOpen', {'textDocument': {'uri': muri, 'languageId': 'nemerle', 'version': 1, 'text': code}})
    c.notify('textDocument/didOpen', {'textDocument': {'uri': guri, 'languageId': 'nemerle', 'version': 1, 'text': gram}})
    def spot(u, text, needle, nth=0, delta=0):
        l, ch = position(text, offset_of(text, needle, nth) + delta)
        return {'textDocument': {'uri': u}, 'position': {'line': l, 'character': ch}}
    deadline = time.time() + a.timeout
    while time.time() < deadline and not c.request('textDocument/hover', spot(muri, code, 'n * 2')): time.sleep(0.5)
    # signature help: the overloads, the argument the position is at
    sig = c.request('textDocument/signatureHelp', spot(muri, code, 'Compute(4, name', delta=len('Compute(4, ')))
    check(sig and sig['signatures'][0]['label'] == 'Compute(n : int, label : string) : System.Threading.Tasks.Task[int]' and sig['activeParameter'] == 1,
          'signature help in a call, at its second argument: %s' % sig)
    sig = c.request('textDocument/signatureHelp', spot(muri, code, 'Scale(2', delta=len('Scale(')))
    labels = [x['label'] for x in sig['signatures']] if sig else []
    check('Scale(by : int) : int' in labels and 'Scale(by : int, extra : string) : int' in labels, 'a method\'s overloads: %s' % labels)
    # document highlight: a local's uses; a rule's uses in its grammar block
    lit = c.request('textDocument/documentHighlight', spot(muri, code, 'total', 1))
    check(sorted((x['range']['start']['line'], x['range']['start']['character']) for x in lit) == [(13, 8), (15, 0), (17, 21)],
          'the uses of a top-level value highlighted: %s' % lit)
    lit = c.request('textDocument/documentHighlight', spot(guri, gram, 'Expr', 1))
    check(sorted((x['range']['start']['line'], x['range']['start']['character']) for x in lit) == [(5, 31), (6, 11), (6, 27)],
          'a rule\'s declaration and uses highlighted in its grammar: %s' % lit)
    # workspace symbols: a function, a method's overloads, a rule, a syntax module
    found = lambda q: [(x['name'], x['location']['uri'].rsplit('/', 1)[-1]) for x in c.request('workspace/symbol', {'query': q})]
    check(('Compute', 'main.n') in found('Comp') and found('Scale').count(('Scale', 'pen.n')) == 2
          and ('Expr', 'calc.n') in found('Expr') and ('Arith', 'calc.n') in found('Arith'),
          'workspace symbols: %s %s %s %s' % (found('Comp'), found('Scale'), found('Expr'), found('Arith')))
    # inlay hints: the types inferred where none is written
    hints = {(x['position']['line'], x['label']) for x in c.request('textDocument/inlayHint', {'textDocument': {'uri': muri},
             'range': {'start': {'line': 0, 'character': 0}, 'end': {'line': 40, 'character': 0}}})}
    check({(6, ': int'), (13, ': int'), (14, ': double'), (16, ': string')} <= hints and not any(l == 12 for l, _ in hints),
          'inlay hints of inferred types (none where a type is written): %s' % hints)
    # tokens by meaning
    def kinds(u, text, needle, nth=0):
        return [t[3] for t in covered(decode(c.request('textDocument/semanticTokens/full', {'textDocument': {'uri': u}}), legend), text, offset_of(text, needle, nth))]
    check(kinds(muri, code, 'start') == ['variable'] and kinds(muri, code, 'n * 2') == ['parameter'] and kinds(muri, code, 'Compute(4') == ['method']
          and kinds(muri, code, 'Width;') == ['property'] and kinds(muri, code, 'Pen()') == ['type'],
          'tokens by what the names are: %s %s %s %s %s' % (kinds(muri, code, 'start'), kinds(muri, code, 'n * 2'), kinds(muri, code, 'Compute(4'),
                                                            kinds(muri, code, 'Width;'), kinds(muri, code, 'Pen()')))
    check(kinds(guri, gram, 'Expr;') == ['type'] and kinds(guri, gram, 'Arith') == ['type'], 'a grammar\'s rule and module names: %s %s' % (kinds(guri, gram, 'Expr;'), kinds(guri, gram, 'Arith')))
    c.request('shutdown', None); c.notify('exit', None)
    print('PASS: signature help, document highlight, workspace symbols, inlay hints and tokens by meaning (Nemerle and Nitra)')
finally:
    shutil.rmtree(more, ignore_errors=True)
# 10. changes by range, and formatting: lines indented by their braces, their own way of lining up kept; strings and
# comments as they are; nothing changed where the brackets do not balance or the indentation is the code's
def edited(text, edits):
    lines = text.split('\n')
    for e in sorted(edits, key=lambda e: e['range']['start']['line'], reverse=True):
        assert e['range']['start']['line'] == e['range']['end']['line']
        l = e['range']['start']['line']; line = lines[l]
        lines[l] = line[:e['range']['start']['character']] + e['newText'] + line[e['range']['end']['character']:]
    return '\n'.join(lines)
c = Client()
c.request('initialize', {'processId': None, 'rootUri': None, 'capabilities': {}})
c.notify('initialized', {})
uri = open_doc('sync.n', 'A() : int { 1 }\n')
# (two changes in one message: the second's range is of the text after the first)
c.notify('textDocument/didChange', {'textDocument': {'uri': uri, 'version': 2}, 'contentChanges': [
    {'range': {'start': {'line': 0, 'character': 0}, 'end': {'line': 0, 'character': 1}}, 'text': 'Alpha'},
    {'range': {'start': {'line': 1, 'character': 0}, 'end': {'line': 1, 'character': 0}}, 'text': 'Beta() : string { "\u00e9t\u00e9" }\nGamma() : int { 3 }\n'},
    {'range': {'start': {'line': 1, 'character': 20}, 'end': {'line': 1, 'character': 21}}, 'text': 'E'}]})
c.wait_diagnostics(uri, 2)
symbols = c.request('textDocument/documentSymbol', {'textDocument': {'uri': uri}})
check(sorted(names(symbols)) == ['Alpha', 'Beta', 'Gamma'], 'changes by range applied in order: %s' % list(names(symbols)))
spaces = {'tabSize': 2, 'insertSpaces': True}
messy = ('Run(x : int) : string\n{\n      def s = "a { string";   \n      def c = \'{\';\n      def m = <#multi {\n   line#>;\n'
         '      when (x > 1)\n        System.Console.WriteLine(s +\n                                 c.ToString());\n'
         '    match (x)\n  {\n| 1 => "one"\n| _ =>\n  /* block { */ m\n}\n}\n')
neat = ('Run(x : int) : string\n{\n  def s = "a { string";\n  def c = \'{\';\n  def m = <#multi {\n   line#>;\n'
        '  when (x > 1)\n    System.Console.WriteLine(s +\n                             c.ToString());\n'
        '  match (x)\n  {\n    | 1 => "one"\n    | _ =>\n      /* block { */ m\n  }\n}\n')
uri = open_doc('messy.n', messy)
formatted = edited(messy, c.request('textDocument/formatting', {'textDocument': {'uri': uri}, 'options': spaces}))
check(formatted == neat, 'a file formatted:\n%s' % formatted)
c.notify('textDocument/didChange', {'textDocument': {'uri': uri, 'version': 2}, 'contentChanges': [{'text': neat}]})
check(c.request('textDocument/formatting', {'textDocument': {'uri': uri}, 'options': spaces}) == [], 'a formatted file stays as it is')
# a range: only its lines; four columns
edits = c.request('textDocument/rangeFormatting', {'textDocument': {'uri': uri}, 'options': {'tabSize': 4, 'insertSpaces': True},
                                                   'range': {'start': {'line': 2, 'character': 0}, 'end': {'line': 3, 'character': 0}}})
check(sorted((e['range']['start']['line'], e['newText']) for e in edits) == [(2, '    def s = "a { string";'), (3, "    def c = '{';")],
      'a range formatted, four columns: %s' % edits)
# the styles kept: cases as far in as their `match', a block given to a call as far in as the call, a variant's
# members beside its cases, a `|' that goes on with a line
kept = ('F(x : int) : int\n{\n  match (x) {\n  | 1 => 1\n  | _ => 2\n  }\n}\n'
        'G() : void\n{\n  locate (loc, {\n  def y = 1;\n  _ = y\n  })\n}\n'
        'variant V\n{\n  | A\n  | B\n  public N : int { get { 0 } }\n}\n'
        'H() : int\n{\n  def flags = 1\n             | 2;\n  flags\n}\n')
uri = open_doc('kept.n', kept)
check(c.request('textDocument/formatting', {'textDocument': {'uri': uri}, 'options': spaces}) == [], 'the styles kept')
for name, text in (('unbalanced.n', 'F() : void\n{\n      def x = (1;\n}\n'), ('indent.n', '#pragma indent\nF() : void\n      def x = 1\n'),
                   ('script.ns', 'def x = 1;\nwhen (x > 0)\n{\n      System.Console.WriteLine(x)\n}\n')):
    uri = open_doc(name, text)
    edits = c.request('textDocument/formatting', {'textDocument': {'uri': uri}, 'options': spaces})
    if name == 'script.ns': check([e['newText'] for e in edits] == ['  System.Console.WriteLine(x)'], 'a script formatted: %s' % edits)
    else: check(edits == [], '%s is not changed: %s' % (name, edits))
c.request('shutdown', None); c.notify('exit', None)
check(c.proc.wait(timeout=30) == 0, 'clean exit')
print('PASS: changes by range; formatting (braces, alignment and styles kept, strings and comments untouched, a range, '
      'nothing where brackets do not balance or with #pragma indent)')

# 11. quick fixes: a name the compiler could not find gets a `using' of each namespace or module that has it (or the
# name written with it); an unused value its name prefixed with `_'
fixes = pathlib.Path(tempfile.mkdtemp(prefix='nemerle-lsp-fixes-'))
try:
    (fixes / 'shapes.n').write_text('public class Circle { public R : int = 2; }\npublic Area(c : Circle) : int { 3 * c.R * c.R }\n')
    code = '// a header\nusing System;\n\ndef sb = StringBuilder();\n_ = sb.Append(Area(Circle()));\nConsole.WriteLine(sb);\nF() : void { def unused = 1; }\nF()\n'
    (fixes / 'main.n').write_text(code)
    c = Client()
    caps = c.request('initialize', {'processId': None, 'rootUri': fixes.as_uri(), 'capabilities': {}})['capabilities']
    check(caps.get('codeActionProvider'), 'the code action capability: %s' % caps)
    c.notify('initialized', {})
    uri = (fixes / 'main.n').as_uri()
    c.notify('textDocument/didOpen', {'textDocument': {'uri': uri, 'languageId': 'nemerle', 'version': 1, 'text': code}})
    c.pump(lambda m: True if m.get('method') == 'textDocument/publishDiagnostics' and m['params']['uri'] == uri
           and any('StringBuilder' in d['message'] for d in m['params']['diagnostics']) else None, 'typed diagnostics')
    def actions(line):
        found = c.request('textDocument/codeAction', {'textDocument': {'uri': uri}, 'range': {'start': {'line': line, 'character': 0},
                          'end': {'line': line, 'character': 80}}, 'context': {'diagnostics': []}})
        return {x['title']: x for x in found}
    on = actions(3)
    check('Add `using System.Text;\'' in on and 'Write `System.Text.StringBuilder\'' in on, 'a .NET type\'s namespace: %s' % list(on))
    add = on['Add `using System.Text;\'']
    check(add.get('isPreferred') and add['diagnostics'][0]['message'].startswith('unbound name'), 'the fix of its diagnostic: %s' % add)
    check(edited(code, add['edit']['changes'][uri]) == code.replace('using System;\n', 'using System;\nusing System.Text;\n'),
          'the using goes after the others: %s' % add['edit'])
    on = actions(4)
    check('Add `using shapes;\'' in on and 'Write `shapes.Area\'' in on and 'Write `shapes.Circle\'' in on,
          'a workspace module\'s function and type: %s' % list(on))
    on = actions(6)
    check(list(on) == ['Prefix `unused\' with `_\''] and edited(code, on['Prefix `unused\' with `_\'']['edit']['changes'][uri]).count('def _unused = 1') == 1,
          'an unused value: %s' % list(on))
    c.request('shutdown', None); c.notify('exit', None)
    print('PASS: quick fixes (a using of the namespace or module that has the name, the name written with it; an unused value)')
finally:
    shutil.rmtree(fixes, ignore_errors=True)
shutil.rmtree(testdata, ignore_errors=True)
print('PASS: %d language server checks' % checks)
