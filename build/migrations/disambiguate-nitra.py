#!/usr/bin/env python3
"""After migrate-nitra.py: a merged module imports what any of its source files imported, so a short name one file
meant from its own imports can now also name a type of another import. For every chunk (marked
`// ---- <file> (<old namespace>) ----`), a short type name defined by several modules is qualified with the one
module the chunk's original file could see (its usings and enclosing namespaces, in the new layout).

    disambiguate-nitra.py PROJECT..."""
import importlib.util, json, pathlib, re, subprocess, sys
from collections import defaultdict

here = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('mn', here / 'migrate-nitra.py')
mn = importlib.util.module_from_spec(spec); spec.loader.exec_module(mn)
spec = importlib.util.spec_from_file_location('mfm', here / 'migrate-file-modules.py')
mfm = importlib.util.module_from_spec(spec); spec.loader.exec_module(mfm)
repo = here.parents[1]
DECL = re.compile(r'(?m)^[ \t]*(?:\[[^\n]*\][ \t]*)*(?:(?:public|internal|private|protected|sealed|abstract|static|new)[ \t]+)*'
                  r'(?:class|module|variant|interface|enum|struct|delegate)[ \t]+(\w+)')
NITRA_DECL = re.compile(r'(?m)^\s*(?:abstract\s+)?(?:ast|declaration|symbol)\s+(\w+)')


def module_paths(project):
    """{module path: file} of a project's file modules."""
    out = {}
    for path in (mn.root / project).rglob('*.n'):
        rel = path.relative_to(mn.root / project)
        if rel.parts[0] in ('Properties', 'obj'): continue
        out['.'.join(rel.with_suffix('').parts)] = path
    return out


def definitions(project):
    """short name -> {module (or module.mask) path} defined by the project's sources and grammars."""
    defs = defaultdict(set)
    for module, path in module_paths(project).items():
        text = path.read_text(encoding='utf-8')
        structural = list(mfm.scan(text))
        masks = [(m.start(), m.group(1), mfm.code_depth(structural, m.start())) for m in re.finditer(r'(?m)^[ \t]*(?:public |internal )?mask (\w+)', text)]
        for m in DECL.finditer(text):
            depth = mfm.code_depth(structural, m.start())
            chain = []
            for mp, name, md in masks:
                if mp < m.start() and md < depth: chain = chain[:md] + [name]
            if len(chain) == depth:
                defs[m.group(1)].add('.'.join([module] + chain))
    for grammar in (mn.root / project).rglob('*.nitra'):
        text = grammar.read_text(encoding='utf-8-sig', errors='replace')
        ns = re.search(r'(?m)^\s*namespace\s+([\w.]+)', text)
        if not ns: continue
        for m in NITRA_DECL.finditer(text):
            defs[m.group(1)].add(ns.group(1))
            if 'declaration' in m.group(0): defs[m.group(1) + 'Symbol'].add(ns.group(1))
    return defs


def compiler_definitions():
    defs = defaultdict(set)
    for name, modules in json.loads((repo / 'ncc/Nemerle/Compiler/SYMBOLS.json').read_text()).items():
        for m in modules: defs[name].add('Nemerle.Compiler.' + m)
    return defs


def visible(project, old_usings, old_namespaces):
    """The new module paths an original file saw."""
    seen = set()
    projects = [project] + mn.DEPENDS[project]
    names = set(old_usings)
    for ns in old_namespaces:
        parts = ns.split('.')
        names.update('.'.join(parts[:i]) for i in range(1, len(parts) + 1))
    for ns in names:
        seen.add(ns)
        for p in projects:
            try: target, mask = mn.layout(p, ns)
            except SystemExit: continue
            seen.add(mn.module_of(target, mask))
        for old, owner, new in mn.MOVES:
            if old == ns and owner in projects: seen.add(new)
    return seen


def main():
    cdefs = compiler_definitions()
    for project in sys.argv[1:]:
        defs = defaultdict(set)
        for p in [project] + mn.DEPENDS[project]:
            for k, v in definitions(p).items(): defs[k] |= v
        for k, v in cdefs.items(): defs[k] |= v
        clashing = {k: v for k, v in defs.items() if len(v) > 1}
        for module, path in module_paths(project).items():
            text = path.read_text(encoding='utf-8')
            merged = set(re.findall(r'(?m)^using\s+([\w.]+)\s*;', text)) | {module}
            pieces = re.split(r'(?m)^([ \t]*// ---- (\S+) \(([^)]*)\) ----\n)', text)
            out, changed = pieces[0], 0
            for i in range(1, len(pieces), 4):
                marker, src, ns, body = pieces[i], pieces[i + 1], pieces[i + 2], pieces[i + 3]
                r = subprocess.run(['git', 'show', 'HEAD:native-nitra/upstream/Nitra/%s/%s' % (project, src)],
                                   cwd=repo, capture_output=True, text=True)
                if r.returncode:
                    r = subprocess.run(['git', 'show', 'HEAD:native-nitra/integration/' + pathlib.Path(src).name],
                                       cwd=repo, capture_output=True, text=True)
                saw = visible(project, re.findall(r'using\s+([\w.]+)\s*;', r.stdout), [ns])
                def fix(m):
                    nonlocal changed
                    if m.group(1) is None: return m.group(0)
                    name = m.group(1)
                    before = m.string[max(0, m.start() - 40):m.start()]
                    if re.search(r'\b(public|private|protected|internal|override|virtual|static|abstract|new|mutable|sealed|extern|macro|event|struct|enum|type)\s+$|\|\s*$|^\s*$', before):
                        return m.group(0)        # a declaration, or a variant option / match case
                    after = m.string[m.end():m.end() + 3]
                    if not (re.search(r'(:>?|\[|\bis|\btypeof\(|\bnew)\s*$', before) or re.match(r'\s*(\(|\[|\.\[)', after)):
                        return m.group(0)        # only type positions and constructor calls; elsewhere it is a value
                    if re.match(r'\s*\.', m.string[m.end():m.end() + 3]):
                        return m.group(0)        # X.Member: X may be a property, not the type
                    owners = clashing.get(name)
                    if not owners: return m.group(0)
                    mine = [o for o in owners if o in saw]
                    now = [o for o in owners if o in merged or o in saw]
                    if len(mine) == 1 and len(now) > 1:
                        changed += 1
                        return mine[0] + '.' + name
                    return m.group(0)
                body = re.sub(r'//[^\n]*|/\*.*?\*/|"(?:[^"\\\n]|\\.)*"|\'(?:\\.|[^\\\'\n])\''
                              r'|(?<![\w.$@])(?<!\bdef )(?<!\bclass )(?<!\binterface )(?<!\bvariant )(?<!\bmodule )([A-Z]\w*)(?![\w])(?!\s*=[^=>])',
                              fix, body, flags=re.S)
                out += marker + body
            if changed:
                path.write_text(out, encoding='utf-8')
                print(project, module, changed, 'names qualified')


if __name__ == '__main__':
    main()
