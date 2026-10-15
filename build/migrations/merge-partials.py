#!/usr/bin/env python3
"""Merge every `partial` type into one declaration in its owner file (file modules have no partial types).

    merge-partials.py PLAN.json

PLAN: {"root": dir, "owners": {"TypeName": "owner/file.n", ...}}. For each partial type, every `partial` part in another
file (found at namespace level, `[attrs] mods partial class|module Name [: bases] { ... }`) is removed from that file and its
body appended to the owner's declaration, whose base list gets the union of the parts' bases; `partial` is dropped from
the owner. The moved part's file-level `using` lines are added to the owner file. Files left with no declarations are
deleted (their path is printed)."""
import json, pathlib, re, sys, importlib.util

here = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('mfm', here / 'migrate-file-modules.py')
mfm = importlib.util.module_from_spec(spec); spec.loader.exec_module(mfm)

plan = json.loads(pathlib.Path(sys.argv[1]).read_text())
root = pathlib.Path(plan['root'])


def read(p): return (root / p).read_text(encoding='utf-8', errors='surrogateescape')
def write(p, t): (root / p).write_text(t, encoding='utf-8', errors='surrogateescape')


def find_decl(text, name, need_partial):
    """(start, header_end, open_brace, close_brace, header) of the declaration of `name` at brace depth 1 (inside a
    namespace) or 0."""
    structural = list(mfm.scan(text))
    pat = re.compile(r'(?m)^[ \t]*(?:\[[^\]\n]*\][ \t]*\r?\n?[ \t]*)*(?:(?:public|internal|private|protected|sealed|abstract|static|partial|new)[ \t]+)*'
                     r'(?:class|module|struct|interface|variant)[ \t]+' + re.escape(name) + r'\b[^{;]*\{')
    for m in pat.finditer(text):
        head = m.group(0)
        if need_partial and not re.search(r'\bpartial\b', head): continue
        depth = mfm.code_depth(structural, m.start())
        if depth > 1: continue
        open_brace = m.end() - 1
        close = next(i for i, c, d in structural if i > open_brace and c == '}' and d == depth + 1)
        return m.start(), open_brace, close, head
    return None


def bases_of(head):
    m = re.search(r'\b(?:class|module|struct|interface|variant)[ \t]+\w+\s*(?:\[[^\]]*\])?\s*:\s*([^{]*?)\s*(?:where\b[^{]*)?\{$', head.strip(), re.S)
    return [b.strip() for b in m.group(1).split(',')] if m else []


def file_usings(text):
    return [u.group(0).strip() for u in re.finditer(r'(?m)^[﻿]?using[ \t]+[^\r\n]+$', text)]


for name, owner in plan['owners'].items():
    parts = []
    for path in sorted(root.rglob('*.n')):
        rel = str(path.relative_to(root))
        if rel == owner: continue
        text = read(rel)
        while True:
            found = find_decl(text, name, True)
            if not found: break
            start, open_brace, close, head = found
            parts.append((rel, text[open_brace + 1:close], bases_of(head), file_usings(text)))
            end = close + 1
            text = text[:start] + text[end:]
        if parts and parts[-1][0] == rel: write(rel, text)
    if not parts: continue
    otext = read(owner)
    start, open_brace, close, head = find_decl(otext, name, False)
    bases = bases_of(head)
    extra = [b for _, _, bs, _ in parts for b in bs if b not in bases and b.split('.')[-1] not in [x.split('.')[-1] for x in bases]]
    new_head = re.sub(r'\bpartial[ \t]+', '', head)
    if extra:
        if bases: new_head = new_head[:-1].rstrip() + ', ' + ', '.join(dict.fromkeys(extra)) + '\n  {'
        else: new_head = new_head[:-1].rstrip() + ' : ' + ', '.join(dict.fromkeys(extra)) + '\n  {'
    moved = ''.join('\n    // ---- merged from %s ----%s' % (rel, body) for rel, body, _, _ in parts)
    otext = otext[:start] + new_head + otext[open_brace + 1:close] + moved + otext[close:]
    have = file_usings(otext)
    add = [u for _, _, _, us in parts for u in us if u.lstrip('﻿') not in [h.lstrip('﻿') for h in have]]
    if add:
        first = re.search(r'(?m)^[﻿]?(?:using|namespace)\b', otext)
        at = first.start() + (1 if otext[first.start()] == '﻿' else 0)
        otext = otext[:at] + '\n'.join(dict.fromkeys(a.lstrip('﻿') for a in add)) + '\n' + otext[at:]
    write(owner, otext)
    print('merged', name, 'into', owner, 'from', sorted(set(r for r, _, _, _ in parts)), 'bases+', extra)

for path in sorted(root.rglob('*.n')):
    text = read(str(path.relative_to(root)))
    code = re.sub(r'//[^\n]*|/\*.*?\*/', '', text, flags=re.S)
    code = re.sub(r'(?m)^\s*(using[^\n]*|namespace[^\n{]*|#[^\n]*)$', '', code)
    if not re.sub(r'[\s{}﻿]', '', code):
        path.unlink(); print('emptied', path.relative_to(root))
