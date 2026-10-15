#!/usr/bin/env python3
"""Move the compiler (nemerle/ncc) from `namespace Nemerle.Compiler` to flat file modules ncc/Nemerle/Compiler/<Module>.n.

    migrate-compiler.py [--dry-run]

1. Every source becomes Nemerle/Compiler/<Module>.n (module = file name; a few renames below). Brace files use
   migrate-file-modules.py (namespace body unwrapped, usings hoisted, `internal` kept as the classic default); indentation
   syntax files lose their `namespace` line and are dedented.
2. A symbol table maps every top-level name to its module.
3. Each module imports (`using Nemerle.Compiler.<Module>;`) the modules whose names it uses.
4. Qualified references `Nemerle.Compiler.<Name>` / `NC.<Name>` become `Nemerle.Compiler.<Module>.<Name>`.
The symbol table is written to ncc/Nemerle/Compiler/SYMBOLS.json for migrating the compiler's consumers
(rename-compiler-references.py)."""
import importlib.util, json, pathlib, re, sys

here = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('mfm', here / 'migrate-file-modules.py')
mfm = importlib.util.module_from_spec(spec); spec.loader.exec_module(mfm)

repo = here.parents[1]
ncc = repo / 'ncc'
out_dir = ncc / 'Nemerle' / 'Compiler'
RENAMES = {'passes': 'ManagerClass', 'ParseTree': 'Parsetree', 'TypedTree': 'Typedtree',
           'Typer-PatternTyper': 'ExtensionPattern', 'MainParser-Extensions': 'SyntaxDefinition'}
SKIP = {'main.n'}   # the command-line compiler is a separate program
DECL = re.compile(r'^[ \t]*(?:\[[^\]\n]*\][ \t]*)*(?:(?:public|internal|private|protected|sealed|abstract|static|new)[ \t]+)*'
                  r'(?:class|module|variant|interface|enum|struct|delegate|type|macro)[ \t]+@?([A-Za-z_]\w*)', re.M)


def read(p): return p.read_text(encoding='utf-8', errors='surrogateescape').lstrip('﻿')


def module_of(path):
    return RENAMES.get(path.stem, path.stem)


def convert_brace(path):
    text = read(path)
    header, rest = mfm.split_header(text)
    namespaces, outside = mfm.pieces(rest)
    usings, outside = mfm.extract_usings(outside, True)
    bodies = []
    for ns, s, e in namespaces:
        inner_usings, body = mfm.extract_usings(rest[s:e], True)
        for u in inner_usings:
            if u not in usings: usings.append(u)
        bodies.append(mfm.dedent(mfm.add_internal(body)))
    if re.sub(r'//[^\n]*|/\*.*?\*/', '', outside, flags=re.S).strip():
        bodies.insert(0, mfm.add_internal(outside).strip('\n'))
    return (header.rstrip() + '\n\n' if header.strip() else '') + '\n'.join(usings) + '\n\n' + '\n\n'.join(bodies) + '\n'


def convert_indent(path):
    text = read(path)
    lines = text.split('\n')
    for i, l in enumerate(lines):
        if re.match(r'^namespace\s+[\w.]+\s*\r?$', l):
            body = [x[2:] if x.startswith('  ') else x for x in lines[i + 1:]]
            # classic default for top-level declarations without access modifier
            body = [re.sub(r'^((?:\[[^\]]*\]\s*)*)(class|module|variant|interface|enum|struct) ', r'\1internal \2 ', x) for x in body]
            return '\n'.join(lines[:i] + body)
    return text


def main():
    dry = '--dry-run' in sys.argv
    sources = sorted(p for p in ncc.rglob('*.n') if out_dir not in p.parents and p.name not in SKIP)
    modules = {}
    for path in sources:
        mod = module_of(path)
        if mod in modules: raise SystemExit('duplicate module %s: %s and %s' % (mod, modules[mod], path))
        modules[mod] = path
    converted = {}
    for mod, path in modules.items():
        text = read(path)
        converted[mod] = convert_indent(path) if '#pragma indent' in text else convert_brace(path)
    # symbol table: top-level names per module (column 0 after conversion)
    symbols = {}
    for mod, text in converted.items():
        if '#pragma indent' in text:
            found = [m for m in DECL.finditer(text) if not text[m.start():m.start() + 1].isspace()]
        else:
            structural = list(mfm.scan(text))
            found = [m for m in DECL.finditer(text) if mfm.code_depth(structural, m.start()) == 0]
        for m in found:
            symbols.setdefault(m.group(1), set()).add(mod)
    ambiguous = {n: sorted(ms) for n, ms in symbols.items() if len(ms) > 1}
    if ambiguous: print('names defined in several modules:', ambiguous)
    owner = {n: sorted(ms)[0] for n, ms in symbols.items()}
    words = re.compile(r'(?<![\w.$])([A-Z_][\w]*)')
    for mod, text in converted.items():
        indent = '#pragma indent' in text
        code = re.sub(r'//[^\n]*|/\*.*?\*/|"(?:[^"\\]|\\.)*"', '', text, flags=re.S)
        used = {owner[w] for w in words.findall(code) if w in owner and owner[w] != mod}
        # qualified references -> module-qualified
        def requalify(m):
            prefix, name = m.group(1), m.group(2)
            return '%s%s.%s' % (prefix, owner[name], name) if name in owner and owner[name] != name or (name in owner and name in symbols and name in modules) else m.group(0)
        text = re.sub(r'(?<![\w.])(Nemerle\.Compiler\.|NC\.)([A-Z_]\w*)\b(?!\s*=)',
                      lambda m: ('%s%s.%s' % (m.group(1), owner[m.group(2)], m.group(2))) if m.group(2) in owner else m.group(0), text)
        imports = ['using Nemerle.Compiler.%s%s' % (u, '' if indent else ';') for u in sorted(used)]
        if imports:
            us = list(re.finditer(r'(?m)^using[ \t]+[^\r\n]+$', text))
            at = us[-1].end() if us else 0
            text = text[:at] + ('\n' if at else '') + '\n'.join(imports) + ('' if at else '\n') + text[at:]
        converted[mod] = text
    # the command-line compiler (ncc/main.n) is its own program: Nemerle/CommandlineCompiler.n
    main_path = ncc / 'main.n'
    main_text = convert_brace(main_path) if main_path.exists() else None
    if main_text:
        code = re.sub(r'//[^\n]*|/\*.*?\*/|"(?:[^"\\]|\\.)*"', '', main_text, flags=re.S)
        used = sorted({owner[w] for w in words.findall(code) if w in owner})
        us = list(re.finditer(r'(?m)^using[ \t]+[^\r\n]+$', main_text))
        main_text = main_text[:us[-1].end()] + '\n' + '\n'.join('using Nemerle.Compiler.%s;' % u for u in used) + main_text[us[-1].end():]
    if dry:
        print(len(converted), 'modules;', sum(len(v) for v in symbols.values()), 'symbols')
        return
    out_dir.mkdir(parents=True, exist_ok=True)
    for mod, text in converted.items():
        (out_dir / (mod + '.n')).write_text(text, encoding='utf-8', errors='surrogateescape')
    for path in modules.values(): path.unlink()
    if main_text:
        (out_dir.parent / 'CommandlineCompiler.n').write_text(main_text, encoding='utf-8', errors='surrogateescape')
        main_path.unlink()
    (out_dir / 'SYMBOLS.json').write_text(json.dumps({n: sorted(ms) for n, ms in symbols.items()}, indent=1, sort_keys=True))
    print('wrote', len(converted), 'modules to', out_dir)


if __name__ == '__main__':
    main()
