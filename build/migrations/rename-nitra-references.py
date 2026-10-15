#!/usr/bin/env python3
"""Point sources at Nitra's file modules (after migrate-nitra.py): Nitra.Location -> Nitra.Runtime.Location, ...

    rename-nitra-references.py [--quotations-only] FILE...

- Qualified names listed in native-nitra/NITRA-SYMBOLS.json (types and macros whose path moved) are rewritten,
  in code, quotations, strings and symbol paths written as lists (["Nitra", "Language"]).
- `using N;` of a namespace that lost a part gets the part's new module imported next to it (MOVES of
  migrate-nitra.py); in C# a module is a static class, so `using N;` naming a Nitra module becomes `using static N;`.
--names-only: only the qualified names (Nitra's own modules, whose usings migrate-nitra.py wrote).
--quotations-only: only quotations and strings change (a bridge Nitra compiler of the previous layout generating code
for the new one)."""
import importlib.util, json, pathlib, re, sys

here = pathlib.Path(__file__).resolve().parent
nitra = here.parents[1] / 'native-nitra'
spec = importlib.util.spec_from_file_location('mn', here / 'migrate-nitra.py')
mn = importlib.util.module_from_spec(spec); spec.loader.exec_module(mn)
symbols = json.loads((nitra / 'NITRA-SYMBOLS.json').read_text())
quotations_only = '--quotations-only' in sys.argv
names_only = '--names-only' in sys.argv   # Nitra's own modules: migrate-nitra already wrote their usings
files = [a for a in sys.argv[1:] if not a.startswith('--')]
NAME = re.compile(r'(?<![\w.])(' + '|'.join(map(re.escape, sorted(symbols, key=len, reverse=True))) + r')(?!\w)')
# the module paths of the new layout (C# imports them with `using static`)
MODULES = set()
for project in mn.PROJECTS:
    for path in (mn.root / project).rglob('*.n'):
        rel = path.relative_to(mn.root / project)
        if rel.parts[0] in ('Properties', 'obj'): continue
        MODULES.add('.'.join(rel.with_suffix('').parts))
for _, _, new in mn.MOVES: MODULES.add(new)
for _, new in mn.MACRO_MOVES: MODULES.add(new)

rcr_source = (here / 'rename-compiler-references.py').read_text()
helpers = {'__file__': str(here / 'rename-compiler-references.py')}
exec(rcr_source[:rcr_source.index('def rewrite(')].replace("files = [a for a in sys.argv[1:] if not a.startswith('--')]", 'files = []'), helpers)


LIST_PATH = re.compile(r'(?<!")("(?:Nitra|DotNet)"(?:\s*,\s*"\w+")+)')   # ["Nitra", "Language"] or BindFullName(1, "Nitra", "X")


def rewrite_list_paths(text):
    """Symbol paths written as lists (BindWellKnownSymbol(["Nitra", "Language"]))."""
    def fix(m):
        parts = re.findall(r'"(\w+)"', m.group(1))
        for k in range(len(parts), 1, -1):          # the longest moved prefix
            old = '.'.join(parts[:k])
            if old in symbols:
                new = symbols[old].split('.') + parts[k:]
                return ', '.join('"%s"' % p for p in new)
        return m.group(0)
    return LIST_PATH.sub(fix, text)


def rewrite(text, csharp, project=None, grammar=False):
    text = rewrite_list_paths(text)
    if quotations_only:
        spans = [(s, e) for s, e, _, quoted in helpers['tokens'](text, csharp) if quoted]
        spans += [(m.start(), m.end()) for m in re.finditer(r'"Nitra\.[\w.]*"', text)]
        edits = [(m.start(), m.end(), symbols[m.group(1)]) for m in NAME.finditer(text) if any(s <= m.start() < e for s, e in spans)]
        for s, e, r in sorted(edits, reverse=True): text = text[:s] + r + text[e:]
        return text
    text = NAME.sub(lambda m: symbols[m.group(1)], text)
    if names_only: return text
    nl = '\r\n' if '\r\n' in text else '\n'
    def additions(ns):
        # a Nitra project sees its own parts and its dependencies'; anything else sees the runtime only
        visible = [project] + mn.DEPENDS[project] if project else ['Nitra.Runtime']
        return [new for old, owner, new in mn.MOVES if old == ns and owner in visible] + \
               [new for old, new in mn.MACRO_MOVES if old == ns and not csharp and not grammar and project]
    out, have = [], set(re.findall(r'(?m)^[ \t﻿]*using[ \t]+(?:static[ \t]+)?([\w.]+)[ \t]*;', text))
    for line in text.split('\n'):
        m = re.match(r'^([ \t﻿]*)using[ \t]+([\w.]+)[ \t]*;(\r?)$', line)
        if m and m.group(2) not in ('System',):
            indent, ns, cr = m.groups()
            if csharp and ns in MODULES and not ns.startswith('Nemerle'):
                line = '%susing static %s;%s' % (indent, ns, cr)
            out.append(line)
            for new in additions(ns):
                if new not in have:
                    have.add(new); out.append('%susing %s%s;%s' % (indent.lstrip('﻿'), 'static ' if csharp else '', new, cr))
        else:
            out.append(line)
    return '\n'.join(out)


for path in files:
    with open(path, encoding='utf-8', errors='surrogateescape', newline='') as f: original = f.read()
    parts = pathlib.Path(path).resolve().parts
    project = next((p for p in mn.PROJECTS if p in parts and 'upstream' in parts), None)
    text = rewrite(original, path.endswith('.cs'), project, path.endswith('.nitra'))
    if text != original:
        with open(path, 'w', encoding='utf-8', errors='surrogateescape', newline='') as f: f.write(text)
        print('updated', path)
