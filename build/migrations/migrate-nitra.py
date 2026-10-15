#!/usr/bin/env python3
"""Move Nitra (native-nitra/upstream/Nitra) to file modules: one file per (dll, namespace).

    migrate-nitra.py [--dry-run]

1. Fold the build-time patches (nitra_output_patches.py and the anchors build-nitra-core.py used to apply) and the
   integration sources (native-nitra/integration/*.n) into the sources, permanently.
2. Merge `partial` parts of each type into one declaration (merge-partials.py); `partial` is dropped.
3. Write one module per (project, namespace) following LAYOUT below; small sub-namespaces of a namespace that
   also has types become masks of its file. Old files are deleted, each .nproj Compile list is rewritten.
4. Write native-nitra/NITRA-SYMBOLS.json: {old full name: new full name} for the types and macros whose path moved
   (consumers are rewritten with rename-nitra-references.py).
Each module imports the modules its pieces' old namespaces opened implicitly (their enclosing namespaces).
A one-off: after it ran (2026-10-14), rename-nitra-references.py and disambiguate-nitra.py rewrote the references and a
few dozen sites were fixed by hand while bootstrapping (see the commit); the tree is the source of truth now."""
import importlib.util, json, pathlib, re, subprocess, sys
import xml.etree.ElementTree as ET

here = pathlib.Path(__file__).resolve().parent
repo = here.parents[1]
nitra = repo / 'native-nitra'
root = nitra / 'upstream/Nitra'
integration = nitra / 'integration'


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, here / file)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module


mfm = load('mfm', 'migrate-file-modules.py')
patches = load('nop', '../nitra_output_patches.py')
PROJECTS = ['Nitra.Runtime', 'DotNetLang', 'Nitra.Grammar', 'Nitra.Compiler']
MSB = '{http://schemas.microsoft.com/developer/msbuild/2003}'
INTEGRATION = {'Nitra.Runtime': ['SelectedFields.n'],
               'Nitra.Compiler': ['RecognizedNemerleFile.n', 'RecognitionEmitter.n', 'NativeSourceHost.n']}


DEPENDS = {'Nitra.Runtime': [], 'DotNetLang': ['Nitra.Runtime'], 'Nitra.Grammar': ['Nitra.Runtime', 'DotNetLang'],
           'Nitra.Compiler': ['Nitra.Runtime', 'DotNetLang', 'Nitra.Grammar']}


def layout(project, ns, path=None):
    """(target file relative to the project, mask or None) for the pieces of namespace `ns` in `project`."""
    parts = ns.split('.')
    if project == 'Nitra.Runtime':
        if ns in ('Nitra', 'Nitra.Runtime'): return 'Nitra/Runtime.n', None
        if ns == 'Nitra.Typing': return 'Nitra/Runtime.n', 'Typing'
        if parts[:2] == ['Nitra', 'Runtime']: return 'Nitra/Runtime.n', '.'.join(parts[2:])
        if ns == 'Nitra.Internal.Recovery': return 'Nitra/Internal.n', 'Recovery'
    if project == 'Nitra.Grammar':
        if ns in ('Nitra', 'Nitra.Internal', 'Nitra.ProjectSystem', 'Nitra.Grammar'): return 'Nitra/Grammar.n', None
        if ns == 'Nitra.Typing.RuleMethod': return 'Nitra/Typing.n', 'RuleMethod'
        if ns == 'DotNet': return 'Nitra/Ast.n', None
    if project == 'Nitra.Compiler':
        # macros under a path another dll owns get the ...Macros suffix (as the standard macros did: NemerleMacros)
        if ns == 'Nitra' and path is not None and path.parent.name == 'Macros': return 'NitraMacros.n', None
        if ns == 'Nitra.Internal': return 'Nitra/InternalMacros.n', None
        if ns == 'Nitra.Serialization2': return 'Nitra/Serialization2Macros.n', None
        if ns in ('Nitra', 'Nitra.Compiler'): return 'Nitra/Compiler.n', None
        if ns == 'Nitra.Serialization': return 'Nitra/Compiler.n', 'Serialization'
        if parts[:2] == ['Nitra', 'Compiler']: return 'Nitra/Compiler.n', '.'.join(parts[2:])
    if project == 'DotNetLang' and ns == 'DotNet': return 'DotNet.n', None
    if len(parts) > 3 or (len(parts) == 3 and project != 'Nitra.Runtime'):
        raise SystemExit('no layout for %s %s' % (project, ns))
    return '/'.join(parts) + '.n', None


def module_of(target, mask):
    path = target[:-2].replace('/', '.')
    return path + ('.' + mask if mask else '')


def compile_items(project):
    proj = root / project / (project + '.nproj')
    tree = ET.parse(proj)
    return proj, tree, [item for item in tree.getroot().iter(MSB + 'Compile')]


def read(path): return path.read_text(encoding='utf-8-sig', errors='surrogateescape')
def write(path, text): path.write_text(text, encoding='utf-8', errors='surrogateescape')


def fold_patches():
    """The patches build-nitra-core applied to its isolated copies, applied to the sources once."""
    chemical = (integration / 'ChemicalConstruction.n.inc').read_text()
    for project in PROJECTS:
        _, _, items = compile_items(project)
        for item in items:
            if '$(' in item.attrib['Include']: continue          # the shared Common file: handled by restructure
            path = (root / project / item.attrib['Include'].replace('\\', '/')).resolve()
            if path.suffix != '.n': continue
            text = read(path); original = text
            patched = patches.patch(path, text)
            if patched is not None: text = patched
            if path.name == 'DefineMembers-ChemicalNode.n':
                anchor = '      _nodeTb.DefineConditional(<[ decl:\n        [Nemerle.Diagnostics.CompileStatistic("ParseTree")]'
                assert text.count(anchor) == 1, path
                text = text.replace(anchor, chemical + '      DefineSelectedFactory(fields, _chemicalTb, _nodeTb);\n' + anchor)
            if path.name == 'SyntaxModuleEmitter.n':
                anchor = '      def allRuleSymbols = SyntaxModule.GetAllRuleSymbols();'
                assert text.count(anchor) == 1, path
                text = text.replace(anchor, '      RecognitionEmitter.Define(SyntaxModule, GrammarTB);\n' + anchor)
            if project == 'Nitra.Compiler' and path.name == 'Macros.n':
                anchor = '    manager.MacroColors.InGlobalColor(CompilingNitraProject.Instance(manager).BeforeInheritance);'
                if anchor in text: text = text.replace(anchor, '    NativeSourceHost.Populate(manager);\n' + anchor)
            if path.name == 'CompositeGrammar.n':
                text = text.replace('Debug.Assert(content.Parent != null);', 'Debug.Assert(content.Parent != null, "Missing content parent");')
            if path.name == 'ListParseTree.n':
                anchor = '        _items = lst.GetUnderlyingArray();'
                if text.count(anchor) == 1 and '_index = 0;' not in text:
                    text = text.replace(anchor, anchor + '\n        _index = 0;\n        _current = default(T);')
            if path.name == 'SequenceParseTreeGenerator.n':
                # generated root types live with the rest of them in Nitra.Runtime
                text = text.replace('EnterIntoNamespace(["Nitra"])', 'EnterIntoNamespace(["Nitra", "Runtime"])')
            if project == 'Nitra.Grammar' and path.name == 'AssemblyInfo.n':
                text = '\n'.join(l for l in text.splitlines() if '[assembly: Nemerle.Macro.Resource(' not in l
                                 and '[assembly: Nemerle.Macro.Settings(' not in l) + '\n'
            if text != original: write(path, text); print('patched', path.relative_to(root))
    for project, names in INTEGRATION.items():
        proj, tree, items = compile_items(project)
        group = items[0].getparent() if hasattr(items[0], 'getparent') else None
        for name in names:
            target = root / project / 'Integration' / name
            target.parent.mkdir(exist_ok=True)
            write(target, read(integration / name))
            print('integrated', target.relative_to(root))


def project_sources(project):
    files = sorted(p for p in (root / project).rglob('*.n') if 'obj' not in p.parts)
    return files


def merge_partials():
    decl = re.compile(r'(?m)^[ \t]*(?:\[[^\]\n]*\][ \t]*)*((?:(?:public|internal|private|protected|sealed|abstract|static|partial|new)[ \t]+)*)'
                      r'(?:class|module|variant|interface|struct)[ \t]+(\w+)')
    for project in PROJECTS:
        parts = {}
        for path in project_sources(project):
            text = read(path)
            for m in decl.finditer(text):
                if 'partial' in m.group(1).split():
                    body = len(text)  # owner: the largest file holding a part
                    parts.setdefault(m.group(2), []).append((body, str(path.relative_to(root / project))))
        owners = {name: max(ps)[1] for name, ps in parts.items()}
        plan = root.parent / ('partials-%s.json' % project)
        plan.write_text(json.dumps({'root': str(root / project), 'owners': owners}))
        subprocess.run([sys.executable, str(here / 'merge-partials.py'), str(plan)], check=True)
        plan.unlink()
        # a lone partial part (completed by generated code) just loses the keyword
        for path in project_sources(project):
            text = read(path)
            new = re.sub(r'(?m)^([ \t]*(?:\[[^\]\n]*\][ \t]*)*(?:(?:public|internal|private|protected|sealed|abstract|static|new)[ \t]+)*)partial[ \t]+',
                         r'\1', text)
            if new != text: write(path, new)


PRIMARY = {'Nitra.Runtime': 'Nitra/Runtime.n', 'DotNetLang': 'DotNet.n', 'Nitra.Grammar': 'Nitra/Grammar.n',
           'Nitra.Compiler': 'Nitra/Compiler.n'}
SELF_IMPORTS = re.compile(r'using\s+([\w.]+)\s*;')

# (old namespace, project that owned that part) -> new module; a macro module is visible to every project
# (they all compile with the Nitra compiler's macros), a type module only to the project and its dependents.
MOVES = [('Nitra', 'Nitra.Runtime', 'Nitra.Runtime'), ('Nitra.Typing', 'Nitra.Runtime', 'Nitra.Runtime.Typing'),
         ('Nitra', 'Nitra.Grammar', 'Nitra.Grammar'), ('Nitra.Internal', 'Nitra.Grammar', 'Nitra.Grammar'),
         ('Nitra.ProjectSystem', 'Nitra.Grammar', 'Nitra.Grammar'), ('DotNet', 'Nitra.Grammar', 'Nitra.Ast'),
         ('Nitra', 'Nitra.Compiler', 'Nitra.Compiler'), ('Nitra.Serialization', 'Nitra.Compiler', 'Nitra.Compiler.Serialization')]
MACRO_MOVES = [('Nitra', 'NitraMacros'), ('Nitra.Internal', 'Nitra.InternalMacros'), ('Nitra.Serialization2', 'Nitra.Serialization2Macros')]
GONE = {'Nitra.Runtime': ['Nitra', 'Nitra.Typing']}   # namespaces with no module left in that project


def rewrite_usings(project, usings, opens):
    """The usings of a module: old namespace imports get their moved parts added; namespaces this project no longer
    has are dropped; `opens` are the namespaces its pieces saw implicitly (they import the same way)."""
    out = []
    def add(line):
        if line not in out: out.append(line)
    seen = [SELF_IMPORTS.match(u).group(1) for u in usings if SELF_IMPORTS.match(u)] + sorted(opens)
    for u in usings:
        m = SELF_IMPORTS.match(u)
        if m and m.group(1) in GONE.get(project, []): continue
        add(u)
    for ns in seen:
        for old, owner, new in MOVES:
            if old == ns and (owner == project or owner in DEPENDS[project]): add('using %s;' % new)
        for old, new in MACRO_MOVES:
            if old == ns: add('using %s;' % new)
    return out


def restructure():
    symbols = {}
    for project in PROJECTS:
        proj, tree, items = compile_items(project)
        targets = {}          # target -> {'header', 'usings': [], 'chunks': [], 'masks': {mask: [chunks]}, 'opens': set()}
        consumed = []
        for path in project_sources(project):
            text = read(path)
            header, rest = mfm.split_header(text)
            namespaces, outside = mfm.pieces(rest)
            if not namespaces:
                consumed.append(path)
                if re.sub(r'//[^\n]*|/\*.*?\*/|\s', '', outside, flags=re.S) == '': continue   # comment-only file
                # assembly attributes (Properties/AssemblyInfo.n): into the project's primary module
                file_usings, outside = mfm.extract_usings(outside, True)
                entry = targets.setdefault(PRIMARY[project], {'header': None, 'usings': [], 'chunks': [], 'masks': {}, 'opens': set()})
                entry['usings'] += [u for u in file_usings if u not in entry['usings']]
                entry['chunks'].insert(0, outside.strip('\n'))
                continue
            file_usings, outside = mfm.extract_usings(outside, True)
            consumed.append(path)
            first_target = None
            for ns, s, e in namespaces:
                target, mask = layout(project, ns, path)
                first_target = first_target or target
                entry = targets.setdefault(target, {'header': None, 'usings': [], 'chunks': [], 'masks': {}, 'opens': set()})
                if entry['header'] is None and header.strip(): entry['header'] = header
                inner_usings, body = mfm.extract_usings(rest[s:e], True)
                for u in file_usings + inner_usings:
                    if u not in entry['usings']: entry['usings'].append(u)
                body = mfm.dedent(mfm.add_internal(body))
                # the namespaces this piece saw implicitly: every enclosing namespace of `ns`
                pieces = ns.split('.')
                for i in range(1, len(pieces) + 1): entry['opens'].add('.'.join(pieces[:i]))
                chunk = '// ---- %s (%s) ----\n%s' % (path.relative_to(root / project), ns, body)
                (entry['masks'].setdefault(mask, []) if mask else entry['chunks']).append(chunk)
                # moved names: top-level types and macros of this piece
                for m in re.finditer(r'(?m)^(?:\[[^\]\n]*\][ \t]*)*(?:(?:public|internal|private|protected|sealed|abstract|static|new)[ \t]+)*'
                                     r'(?:class|module|variant|interface|enum|struct|macro|delegate)[ \t]+(\w+)', body):
                    new = module_of(target, mask) + '.' + m.group(1)
                    old = ns + '.' + m.group(1)
                    if old != new: symbols[old] = new
            if re.sub(r'//[^\n]*|/\*.*?\*/|\s', '', outside, flags=re.S):
                targets[first_target]['chunks'].insert(0, mfm.add_internal(outside).strip('\n'))
        # the Common file every dll compiled (assembly version, AssemblyConstants): one internal mask per dll
        common = read(root.parent / 'Common/AssemblyConstants.Common.n')
        common_usings, common_rest = mfm.extract_usings(common, True)
        entry = targets[PRIMARY[project]]
        entry['usings'] += [u for u in common_usings if u not in entry['usings']]
        entry['chunks'].insert(0, re.sub(r'(?m)^module AssemblyConstants', 'internal mask AssemblyConstants', common_rest.strip('\n')))
        written = []
        for target, entry in sorted(targets.items()):
            module = target[:-2].replace('/', '.')
            usings = [u for u in rewrite_usings(project, entry['usings'], entry['opens'])
                      if not (SELF_IMPORTS.match(u) and SELF_IMPORTS.match(u).group(1) == module)]   # own masks stay imported
            opens = []
            body = '\n\n'.join(entry['chunks'])
            for mask, chunks in sorted(entry['masks'].items()):
                inner = '\n\n'.join(chunks)
                for level in reversed(mask.split('.')):
                    inner = 'public mask %s\n{\n%s\n}' % (level, '\n'.join('  ' + l if l.strip() else l for l in inner.split('\n')))
                body += '\n\n' + inner
            text = (entry['header'] or '').rstrip() + '\n\n' + '\n'.join(usings + opens) + '\n\n' + body + '\n'
            out = root / project / target
            out.parent.mkdir(parents=True, exist_ok=True)
            written.append((out, text.lstrip('\n')))
        if '--dry-run' in sys.argv:
            print(project, len(consumed), 'files ->', sorted(t for t in targets)); continue
        for path in consumed: path.unlink()
        for out, text in written: write(out, text)
        # Compile list: drop the consumed .n files, add the modules
        names = {str(p.relative_to(root / project)).replace('/', '\\') for p in consumed} | {'$(CommonFilesPath)\\AssemblyConstants.Common.n'}
        group = None
        doomed = [(parent, item) for parent in tree.getroot().iter() for item in list(parent)
                  if item.tag == MSB + 'Compile' and item.attrib['Include'] in names]
        for parent, item in doomed:
            group = parent; parent.remove(item)
        for out, _ in written:
            el = ET.SubElement(group, MSB + 'Compile'); el.set('Include', str(out.relative_to(root / project)).replace('/', '\\'))
        ET.register_namespace('', MSB[1:-1])
        tree.write(proj, encoding='utf-8', xml_declaration=True)
        print(project, len(consumed), 'files ->', len(written), 'modules')
    if '--dry-run' not in sys.argv:
        # Runtime's `language Language` completes the hand-written Language, which moved to Nitra.Runtime
        language = root / 'Nitra.Runtime/Language.nitra'
        raw = open(language, encoding='utf-8', newline='').read()   # keep the BOM and CRLF
        open(language, 'w', encoding='utf-8', newline='').write(re.sub(r'(?m)^(\ufeff?)namespace Nitra(\r?)$', r'\1namespace Nitra.Runtime\2', raw, count=1))
        for generated in ('SequenceParseTree', 'ConcreteSequenceParseTree', 'AmbiguousSequenceParseTree'):
            symbols['Nitra.' + generated] = 'Nitra.Runtime.' + generated
        # Grammar's DotNet.CompilationUnit (generated + hand-written) belongs to Nitra.Ast now
        for g in (root / 'Nitra.Grammar').rglob('*.nitra'):
            text = open(g, encoding='utf-8', newline='').read()
            new = re.sub(r'(?m)^(\ufeff?)namespace DotNet\b', r'\1namespace Nitra.Ast', text)
            if new != text: open(g, 'w', encoding='utf-8', newline='').write(new); print('namespace moved', g.relative_to(root))
        (nitra / 'NITRA-SYMBOLS.json').write_text(json.dumps(symbols, indent=1, sort_keys=True))
        print(len(symbols), 'moved names')


SYNTAX_USINGS = {'Nemerle.Imperative.GoTo': ['label', 'goto']}


def escape_syntax_keywords(text, original_usings):
    """A file module imports once for the whole file, so a syntax extension one source file opened (GoTo: the
    keywords `label` and `goto`) now covers code from files that used those words as names: escape them there.
    `original_usings(source)` gives the usings of a chunk's original file."""
    keywords = [k for u, ks in SYNTAX_USINGS.items() if re.search(r'(?m)^using %s;' % re.escape(u), text) for k in ks]
    if not keywords: return text
    pieces = re.split(r'(?m)^([ \t]*// ---- (\S+) \([^)]*\) ----\n)', text)
    out = pieces[0]
    for i in range(1, len(pieces), 3):
        marker, source, body = pieces[i], pieces[i + 1], pieces[i + 2]
        if not any(u in original_usings(source) for u in SYNTAX_USINGS):
            body = re.sub(r'//[^\n]*|"(?:[^"\\\n]|\\.)*"|(?<![\w@$.])(%s)\b' % '|'.join(keywords),
                          lambda m: '@' + m.group(1) if m.group(1) else m.group(0), body)
        out += marker + body
    return out


_owned = {}
def owned_by(project):
    """Namespaces present in `project` (so an import of their module names something that project builds)."""
    if project not in _owned:
        found = set()
        for path in project_sources(project):
            found.update(re.findall(r'(?m)^[ \t]*namespace[ \t]+([\w.]+)', read(path)))
        _owned[project] = found
    return _owned[project]


if __name__ == '__main__':
    if '--dry-run' not in sys.argv:
        fold_patches()
        merge_partials()
    for project in PROJECTS: owned_by(project)
    restructure()
