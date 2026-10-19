#!/usr/bin/env python3
"""Drive the Nemerle language server over stdio like an editor and check its answers.

Usage: check-language-server.py --server <out>/nemerle-lsp [--log FILE]
Build the server first with build-language-server.py."""
import argparse, json, pathlib, shutil, subprocess, tempfile, threading, queue, time, sys

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

class Client:
    def __init__(self):
        args = [str(a.server)] + (['--log', str(a.log)] if a.log else [])
        self.proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
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
check(caps['textDocumentSync'] == 1 and caps['foldingRangeProvider'] and caps['documentSymbolProvider'], 'capabilities')
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
    print('PASS: a .ns script is checked by the scripting host (its errors at its lines, apart from the workspace)')
    c.request('shutdown', None); c.notify('exit', None)
    check(c.proc.wait(timeout=30) == 0, 'clean exit')
finally:
    shutil.rmtree(work, ignore_errors=True)
print('PASS: %d language server checks' % checks)
