#!/usr/bin/env python3
"""Rename the compiler modules that hold a type of their own name (Typer.n holding class Typer): a member may not
have the name of its file module (C# CS0542), so the file becomes snake_case (typer.n, type_builder.n) and the type
keeps its name: Nemerle.Compiler.Typer.Typer -> Nemerle.Compiler.typer.Typer.

    rename-compiler-modules.py --move              rename the files in ncc/Nemerle/Compiler and update SYMBOLS.json
    rename-compiler-modules.py [--quotations-only] [--no-strings] FILE...
                                                   rewrite module paths Nemerle.Compiler.<Old> -> Nemerle.Compiler.<new>

The map is computed from SYMBOLS.json before --move (modules whose file holds a top-level name equal to the module)
and kept in ncc/Nemerle/Compiler/RENAMED-MODULES.json afterwards.
--quotations-only: only paths inside quotations (and strings, unless --no-strings) change: bridges built by a compiler
of the previous layout generate code for the new one."""
import importlib.util, json, pathlib, re, subprocess, sys

here = pathlib.Path(__file__).resolve().parent
compiler_dir = here.parents[1] / 'ncc' / 'Nemerle' / 'Compiler'
symbols_path = compiler_dir / 'SYMBOLS.json'
renamed_path = compiler_dir / 'RENAMED-MODULES.json'


def snake(name):
    return re.sub(r'(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])', '_', name).lower()


def rename_map():
    if renamed_path.exists(): return json.loads(renamed_path.read_text())
    symbols = json.loads(symbols_path.read_text())
    return {p.stem: snake(p.stem) for p in sorted(compiler_dir.glob('*.n')) if symbols.get(p.stem) == [p.stem]}


def move():
    renames = rename_map()
    for old, new in renames.items():
        subprocess.run(['git', 'mv', str(compiler_dir / (old + '.n')), str(compiler_dir / (new + '.n'))], check=True)
    symbols = json.loads(symbols_path.read_text())
    symbols = {name: sorted(renames.get(m, m) for m in modules) for name, modules in symbols.items()}
    symbols_path.write_text(json.dumps(symbols, indent=1, sort_keys=True))
    renamed_path.write_text(json.dumps(renames, indent=1, sort_keys=True))
    print('renamed', len(renames), 'modules')


def rewrite_files(files, quotations_only, no_strings):
    renames = rename_map()
    path = re.compile(r'(?<![\w.])Nemerle\.Compiler\.(' + '|'.join(map(re.escape, sorted(renames, key=len, reverse=True))) + r')(?!\w)')
    spec = importlib.util.spec_from_file_location('rcr', here / 'rename-compiler-references.py')
    source = (here / 'rename-compiler-references.py').read_text()
    helpers = {'__file__': str(here / 'rename-compiler-references.py')}
    exec(source[:source.index('def rewrite(')].replace("files = [a for a in sys.argv[1:] if not a.startswith('--')]", 'files = []'), helpers)
    for file in files:
        with open(file, encoding='utf-8', errors='surrogateescape', newline='') as f: text = f.read()
        if quotations_only:
            spans = [(s, e) for s, e, _, quoted in helpers['tokens'](text, file.endswith('.cs')) if quoted]
            if not no_strings:
                spans += [(m.start(), m.end()) for m in re.finditer(r'"Nemerle\.Compiler\.[\w.]*"', text)]
            edits = [(m.start(), m.end(), 'Nemerle.Compiler.' + renames[m.group(1)]) for m in path.finditer(text)
                     if any(s <= m.start() < e for s, e in spans)]
            new = text
            for s, e, r in sorted(edits, reverse=True): new = new[:s] + r + new[e:]
        else:
            new = path.sub(lambda m: 'Nemerle.Compiler.' + renames[m.group(1)], text)
        if new != text:
            with open(file, 'w', encoding='utf-8', errors='surrogateescape', newline='') as f: f.write(new)
            print('updated', file)


if '--move' in sys.argv: move()
else: rewrite_files([a for a in sys.argv[1:] if not a.startswith('--')], '--quotations-only' in sys.argv, '--no-strings' in sys.argv)
