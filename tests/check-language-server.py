#!/usr/bin/env python3
"""Drive the Nemerle language server over stdio like an editor and check its answers.

Usage: check-language-server.py --server <out>/nemerle-lsp [--log FILE]
Build the server first with build-language-server.py."""
import argparse, json, pathlib, subprocess, threading, queue, time, sys

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
check(covered(tokens, example, offset_of(example, 'answer })')) != [], 'token inside the space body (Nitra parse of the compiled grammar)')
check(any(t[3] == 'keyword' for t in covered(tokens, example, offset_of(example, 'module Program'))), 'Nemerle keyword after the grammar block')
glines = position(example, offset_of(example, 'grammar Demo'))[0]
check(any(f['startLine'] == glines for f in folds), 'fold for the grammar block')
syms = set(names(symbols))
check('grammar Demo' in syms and 'Program' in syms and any(n.startswith('space') for n in syms), 'symbols: %s' % syms)
print('PASS: grammar/space file (unmodified Nitra highlighting of grammar and space, Nemerle around them)')

# 3. broken space body and broken grammar rule: recovery keeps a tree
broken = example.replace('space Demo [A] { answer }', 'space Demo [A] { answr }')
c.notify('textDocument/didChange', {'textDocument': {'uri': uri, 'version': 2}, 'contentChanges': [{'text': broken}]})
diags, tokens, folds, symbols = analyze(uri, broken, 2)
body = offset_of(broken, 'answr')
space_errors = [d for d in diags if d['severity'] == 1 and d.get('source') == 'space']
check(space_errors and all(d['range']['start']['line'] == position(broken, body)[0] for d in space_errors), 'space error on the space line: %s' % diags)
check(any(t[3] == 'keyword' for t in covered(tokens, broken, offset_of(broken, 'module Program'))), 'Nemerle tokens still present')
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
print('PASS: %d language server checks' % checks)
