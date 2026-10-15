#!/usr/bin/env python3
"""Point references at the standard macros' new file-module paths (Nemerle.IO.sprint -> Nemerle.IOMacros.sprint, ...).

    rename-macro-paths.py MOVES.json [--macro-sources] FILE...

MOVES.json: {"<old path>": {"new": "<new path>", "names": [macro and helper names defined there]}}.
- Qualified references `<old>.<name>` become `<new>.<name>`; `Util.locate/ice/cassert` and `Message.FatalError` (the
  compiler's macro shorthands) become `UtilMacros.*` / `MessageMacros.*`.
- A file that uses a short name of a moved module gets `using <new>;` next to its usings.
- --macro-sources: the files are the macro library itself, which is built by the previous macros once more. Outside
  quotations a qualified use becomes the short name with both `using <old>; using <new>;` (each resolves in one
  generation); inside quotations (generated code) the new qualified name is used."""
import json, re, sys

moves = json.load(open(sys.argv[1]))
macro_sources = '--macro-sources' in sys.argv
files = [a for a in sys.argv[2:] if not a.startswith('--')]
order = sorted(moves, key=len, reverse=True)
SHORTHAND = {'Util': ('Nemerle.Compiler.Util', 'UtilMacros', ['locate', 'ice', 'cassert']),
             'Message': ('Nemerle.Compiler.Message', 'MessageMacros', ['FatalError'])}


def quotation_mask(text):
    """True for characters inside <[ ... ]> (strings and comments are skipped when counting)."""
    mask, depth, i, n = [False] * len(text), 0, 0, len(text)
    while i < n:
        if text.startswith('//', i):
            j = text.find('\n', i); j = n if j < 0 else j
            for k in range(i, j): mask[k] = depth > 0
            i = j; continue
        if text.startswith('/*', i):
            j = text.find('*/', i + 2); j = n if j < 0 else j + 2
            for k in range(i, j): mask[k] = depth > 0
            i = j; continue
        if text[i] == '"':
            j = i + 1
            while j < n and text[j] != '"': j += 2 if text[j] == '\\' else 1
            for k in range(i, min(j + 1, n)): mask[k] = depth > 0
            i = j + 1; continue
        if text.startswith('<[', i): depth += 1
        mask[i] = depth > 0
        if text.startswith(']>', i) and depth > 0:
            mask[i + 1] = True; depth -= 1; i += 2; continue
        i += 1
    return mask


def add_using(text, line):
    if re.search(r'^\s*' + re.escape(line) + r'\s*$', text, re.M): return text
    usings = list(re.finditer(r'^[ \t]*using[ \t]+[^;\r\n]+;?[ \t]*\r?$', text, re.M))
    top = [u for u in usings if not u.group(0).startswith(' ')] or usings
    if top:
        at = top[-1].end() - (1 if top[-1].group(0).endswith('\r') else 0)
        indent = re.match(r'[ \t]*', top[-1].group(0)).group(0)
        semicolon = ';' if top[-1].group(0).rstrip().endswith(';') else ''
        nl = '\r\n' if '\r\n' in text else '\n'
        return text[:at] + nl + indent + line.rstrip(';') + semicolon + text[at:]
    bom = '\ufeff' if text.startswith('\ufeff') else ''
    return bom + line + ('\r\n' if '\r\n' in text else '\n') + text[len(bom):]


for path in files:
    text = open(path, encoding='utf-8', errors='surrogateescape', newline='').read()
    original = text
    needed = set()
    mask = quotation_mask(text) if macro_sources else None
    edits = []
    for old in order:
        new, names = moves[old]['new'], moves[old]['names']
        for m in re.finditer(r'(?<![\w.])' + re.escape(old) + r'\.(' + '|'.join(map(re.escape, names)) + r')\b', text):
            if macro_sources and not mask[m.start()]:
                edits.append((m.start(), m.end(), m.group(1))); needed.add(old)
            else:
                edits.append((m.start(), m.end(), new + '.' + m.group(1)))
    for short, (old, new_short, names) in SHORTHAND.items():
        for m in re.finditer(r'(?<![\w.])' + short + r'\.(' + '|'.join(names) + r')\b', text):
            if any(s <= m.start() < e for s, e, _ in edits): continue
            if macro_sources and not mask[m.start()]:
                edits.append((m.start(), m.end(), m.group(1))); needed.add(old)
            elif macro_sources:
                edits.append((m.start(), m.end(), moves[old]['new'] + '.' + m.group(1)))
            else:
                edits.append((m.start(), m.end(), new_short + '.' + m.group(1)))
    for s, e, r in sorted(edits, reverse=True): text = text[:s] + r + text[e:]
    # short uses of moved names need the new module imported (Nemerle.CoreMacros is opened by default)
    for old in order:
        if old == 'Nemerle.Core' or old in ('Nemerle.Compiler.Util', 'Nemerle.Compiler.Message'): continue
        new, names = moves[old]['new'], moves[old]['names']
        imports_old = re.search(r'^[\ufeff\s]*using\s+' + re.escape(old) + r'\s*;?\s*$', text, re.M)
        uses_name = re.search(r'(?<![\w.])(' + '|'.join(map(re.escape, names)) + r')\b', text)
        own_module = path.replace('\\', '/').endswith('/' + new.replace('.', '/') + '.n')
        if ((imports_old and uses_name) or old in needed) and not own_module:
            text = add_using(text, 'using %s;' % new)
            if macro_sources and old in needed and not imports_old: text = add_using(text, 'using %s;' % old)
    for old in needed:
        if old in ('Nemerle.Compiler.Util', 'Nemerle.Compiler.Message'):
            text = add_using(text, 'using %s;' % old); text = add_using(text, 'using %s;' % moves[old]['new'])
    if text != original:
        open(path, 'w', encoding='utf-8', errors='surrogateescape', newline='').write(text)
        print('updated', path)
