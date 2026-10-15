#!/usr/bin/env python3
"""Merge classic `namespace X { ... }` sources into file modules (one file per target module).

    migrate-file-modules.py PLAN.json

PLAN: {"root": "<dir the targets are relative to>",
       "targets": {"Nemerle/Core.n": [["core.n", "Nemerle.Core"], ["AssemblyInfo.n", ""], ...], ...},
       "drop": [["internal.n", "Nemerle.Compiler"]]}
Each [file, namespace] piece is the body of that namespace in that file ("" = text outside any namespace).
For each target: the license header of its first source, the union of `using` directives (hoisted from file level and
from namespace bodies, without self-imports), then each piece with its declarations. Declarations without an access
modifier get `internal`, which keeps the classic default (file modules default to public). Every piece of every source
must be assigned or dropped; the sources are not deleted (do that with git rm)."""
import json, pathlib, re, sys

ACCESS = {'public', 'internal', 'private', 'protected'}
DECL = {'class', 'module', 'variant', 'interface', 'enum', 'struct', 'type', 'delegate'}


def scan(text):
    """Yield (index, char, depth) for structural characters outside strings/comments; depth counts { } only."""
    i, n, depth = 0, len(text), 0
    while i < n:
        c = text[i]
        if text.startswith('//', i):
            j = text.find('\n', i); i = n if j < 0 else j; continue
        if text.startswith('/*', i):
            j = text.find('*/', i + 2); i = n if j < 0 else j + 2; continue
        if text.startswith('<#', i):
            level, i = 1, i + 2
            while i < n and level:
                if text.startswith('<#', i): level += 1; i += 2
                elif text.startswith('#>', i): level -= 1; i += 2
                else: i += 1
            continue
        if c == '@' and i + 1 < n and text[i + 1] == '"':
            i += 2
            while i < n:
                if text[i] == '"':
                    if i + 1 < n and text[i + 1] == '"': i += 2; continue
                    break
                i += 1
            i += 1; continue
        if c == '"':
            i += 1
            while i < n and text[i] != '"':
                i += 2 if text[i] == '\\' else 1
            i += 1; continue
        if c == "'":
            m = re.match(r"'(\\u[0-9a-fA-F]{4}|\\.|[^\\'\n])'", text[i:])
            if m: i += len(m.group(0)); continue
        if c == '{': depth += 1; yield i, c, depth; i += 1; continue
        if c == '}': yield i, c, depth; depth -= 1; i += 1; continue
        if c == ';': yield i, c, depth
        i += 1


def pieces(text):
    """Split a classic source into (header, file_usings, [(namespace, body)], outside_text)."""
    structural = list(scan(text))
    namespaces, outside, cursor = [], [], 0
    for m in re.finditer(r'(?m)^[ \t]*namespace[ \t]+([A-Za-z_][\w.]*)\s*\{', text):
        start = m.start()
        if any(s <= start < e for _, s, e in namespaces): continue
        if code_depth(structural, start) != 0: continue
        open_index = m.end() - 1
        close = next(i for i, c, d in structural if i > open_index and c == '}' and d == 1)
        namespaces.append((m.group(1), m.end(), close))
        outside.append(text[cursor:start]); cursor = close + 1
    outside.append(text[cursor:])
    return namespaces, ''.join(outside)


def code_depth(structural, position):
    depth = 0
    for i, c, d in structural:
        if i >= position: break
        depth = d if c == '{' else d - 1 if c == '}' else depth
    return depth


def split_header(text):
    """Leading comments (license) and the rest."""
    m = re.match(r'(\s*(//[^\n]*\n|/\*.*?\*/\s*)*)', text, re.S)
    return m.group(1), text[m.end():]


def extract_usings(text, top_level_only):
    """Remove `using ...;` statements at brace depth 0 of `text`; return (usings, remaining text)."""
    structural = list(scan(text))
    usings, out, cursor = [], [], 0
    for m in re.finditer(r'(?m)^[ \t]*using[ \t]+[^;{}()]+;[ \t]*\n?', text):
        if code_depth(structural, m.start()) != 0: continue
        usings.append(re.sub(r'\s+', ' ', m.group(0).strip()))
        out.append(text[cursor:m.start()]); cursor = m.end()
    out.append(text[cursor:])
    return usings, ''.join(out)


def add_internal(body):
    """Insert `internal` before depth-0 declarations that have no access modifier."""
    structural = [(i, c, d) for i, c, d in scan(body)]
    starts = [0] + [i + 1 for i, c, d in structural if (c == '}' and d == 1) or (c == ';' and d == 0)]
    inserts = []
    for s in starts:
        j = s
        while True:
            m = re.match(r'\s+|//[^\n]*|/\*.*?\*/|#[^\n]*', body[j:], re.S)
            if m and m.end(): j += m.end(); continue
            if body.startswith('[', j):
                level = 0
                for k in range(j, len(body)):
                    if body[k] == '[': level += 1
                    elif body[k] == ']':
                        level -= 1
                        if level == 0: j = k + 1; break
                continue
            break
        words = re.match(r'((?:[A-Za-z_]\w*\s+)*?)(class|module|variant|interface|enum|struct|type|delegate)\b', body[j:])
        if not words: continue
        mods = set(words.group(1).split())
        if mods & ACCESS: continue
        inserts.append(j)
    for j in sorted(inserts, reverse=True):
        body = body[:j] + 'internal ' + body[j:]
    return body


def dedent(body):
    lines = body.split('\n')
    indented = [l for l in lines if l.strip()]
    if indented and all(l.startswith('  ') for l in indented):
        lines = [l[2:] if l.startswith('  ') else l for l in lines]
    return '\n'.join(lines).strip('\n')


def main():
    plan = json.loads(pathlib.Path(sys.argv[1]).read_text())
    root = pathlib.Path(plan['root'])
    assigned = {}
    for target, parts in plan['targets'].items():
        for part in parts: assigned.setdefault(part[0], set()).add(part[1])
    for f, ns in plan.get('drop', []): assigned.setdefault(f, set()).add(ns)
    parsed = {}
    for f in assigned:
        text = (root / f).read_text().lstrip('\ufeff')
        header, rest = split_header(text)
        namespaces, outside = pieces(rest)
        file_usings, outside = extract_usings(outside, True)
        bodies = {}
        for ns, s, e in namespaces: bodies[ns] = bodies.get(ns, '') + '\n' + rest[s:e]
        if re.sub(r'//[^\n]*|/\*.*?\*/', '', outside, flags=re.S).strip(): bodies[''] = outside
        missing = set(bodies) - assigned[f]
        if missing: raise SystemExit('unassigned pieces in %s: %s' % (f, sorted(missing)))
        unknown = assigned[f] - set(bodies) - {''}
        if unknown: raise SystemExit('no namespace %s in %s' % (sorted(unknown), f))
        parsed[f] = (header, file_usings, bodies)
    for target, parts in plan['targets'].items():
        module = target[:-2].replace('/', '.')
        usings, chunks, header = [], [], None
        for part in parts:
            f, ns = part[0], part[1]
            mask = part[2] if len(part) > 2 else None
            h, file_usings, bodies = parsed[f]
            if header is None and h.strip(): header = h
            inner_usings, body = extract_usings(bodies.get(ns, ''), True)
            for u in file_usings + inner_usings:
                name = re.match(r'using\s+([\w.]+)\s*;', u)
                if name and name.group(1) == module: continue
                if u not in usings: usings.append(u)
            # a namespace nested in a namespace body becomes a nested module of the file
            body = re.sub(r'(?m)^([ \t]*)namespace[ \t]+([A-Za-z_]\w*)[ \t]*$', r'\1public module \2', body)
            body = dedent(add_internal(body))
            if mask:
                body = 'public mask %s\n{\n%s\n}' % (mask, '\n'.join('  ' + l if l.strip() else l for l in body.split('\n')))
            if body.strip(): chunks.append('// ---- %s%s ----\n%s' % (f, ' (' + ns + ')' if ns else '', body))
        text = (header or '').rstrip() + '\n\n' + '\n'.join(usings) + '\n\n' + '\n\n'.join(chunks) + '\n'
        out = root / target
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text.lstrip('\n'))
        print('wrote', out, len(text.splitlines()), 'lines')


if __name__ == '__main__':
    main()
