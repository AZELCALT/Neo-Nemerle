#!/usr/bin/env python3
"""Run every example of the book (doc/book/src/*.md), like Rust's doctests.

    check-book.py --toolchain DIR --references REFS [--chapter NAME]

A fenced block tagged `nemerle` is compiled as a program and run; when the next block is tagged `text`, the output
must equal it. Tags after a comma change that:
    nemerle,ignore      not tested
    nemerle,fail        must not compile; the following `text` block is a substring of the diagnostics
    nemerle,script      run with `nscript run`
    nemerle,lib=NAME    compiled as library NAME.dll; later blocks of the same chapter may reference it
    nemerle,app         an application that embeds the compiler: it runs with the toolchain next to it
                        (and `references/`)
Inside a block, `// file: path.n` starts another file, and a line `// ncc: ARGS` adds compiler arguments, where
{toolchain} is replaced by the toolchain directory. A file that does not end in `.n` is data the program reads, not
compiled. Each chapter runs in a folder of its own."""
import argparse, pathlib, re, shutil, subprocess, sys, tempfile

p = argparse.ArgumentParser()
p.add_argument('--toolchain', type=pathlib.Path, required=True)
p.add_argument('--references', type=pathlib.Path, required=True)
p.add_argument('--chapter', help='only chapters whose file name contains this')
a = p.parse_args()
T = a.toolchain.resolve()
book = pathlib.Path(__file__).resolve().parents[1] / 'doc/book/src'
w = pathlib.Path(tempfile.mkdtemp(prefix='nemerle-book-'))
FENCE = re.compile(r'^```([^\n]*)\n(.*?)^```\s*$', re.S | re.M)
failures, count = [], 0


def files_of(code, first='main.n'):
    """[(relative path, text)] of a block; files split at `// file: path` lines."""
    parts, name, lines = [], first, []
    def real(lines):   # a part holding only blank and comment lines (e.g. an `// ncc:` line) is not a file
        return any(l.strip() and not l.strip().startswith('//') for l in lines)
    for line in code.splitlines(keepends=True):
        m = re.match(r'\s*// file: (\S+)\s*$', line)
        if m:
            if real(lines): parts.append((name, ''.join(lines)))
            name, lines = m.group(1), []
        else:
            lines.append(line)
    if real(lines): parts.append((name, ''.join(lines)))
    return parts


def check(chapter, line, tags, code, expected, folder):
    kind = tags[0] if tags else ''
    root = folder / ('example%d' % line)
    root.mkdir()
    paths = []
    for name, text in files_of(code, 'main.ns' if kind == 'script' else 'main.n'):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        paths.append(path)
    extra = []
    for m in re.finditer(r'^\s*// ncc: (.*)$', code, re.M):
        extra += [arg.replace('{toolchain}', str(T)).replace('{chapter}', str(folder)) for arg in m.group(1).split()]
    if kind == 'script':
        for dll in folder.glob('*.dll'): shutil.copy2(dll, root / dll.name)   # libraries and script kinds of the chapter
        r = subprocess.run([str(T / 'nscript'), 'run', str(paths[0]), '--no-cache'], cwd=root, capture_output=True, text=True)
        return r.returncode == 0 and (expected is None or r.stdout.strip() == expected.strip()), r.stdout + r.stderr
    library = kind.startswith('lib=')
    output = folder / (kind[4:] + '.dll') if library else root / 'main.exe'
    sources = [p for p in paths if p.suffix == '.n']
    command = [str(T / 'ncc'), *map(str, sources), '-source-root:' + str(root), '-out:' + str(output), '-no-color', *extra]
    if library: command.insert(-len(extra) if extra else len(command), '-target:library')
    r = subprocess.run(command, cwd=root, capture_output=True, text=True)
    diagnostics = r.stdout + r.stderr
    if kind == 'fail':
        return r.returncode != 0 and (expected is None or expected.strip() in diagnostics), diagnostics
    if r.returncode != 0:
        return False, diagnostics
    if library:
        return True, ''
    for dll in list(T.glob('Nemerle.dll')) + list(folder.glob('*.dll')):
        shutil.copy2(dll, root / dll.name)
    if kind == 'app':
        for f in T.iterdir():
            if f.is_file() and f.suffix in {'.dll', '.json', '.nitrametadata'} and not (root / f.name).exists():
                shutil.copy2(f, root / f.name)
        (root / 'references').symlink_to(T / 'references', target_is_directory=True)
    shutil.copy2(T / 'ncc.runtimeconfig.json', root / 'main.runtimeconfig.json')
    r = subprocess.run(['dotnet', str(output)], cwd=root, capture_output=True, text=True, timeout=60)
    ok = r.returncode == 0 and (expected is None or r.stdout.rstrip() == expected.rstrip())
    return ok, r.stdout + r.stderr


for md in sorted(book.glob('*.md')):
    if a.chapter and a.chapter not in md.name: continue
    text = md.read_text()
    blocks = [(m.group(1).strip(), m.group(2), text.count('\n', 0, m.start()) + 1, m.end()) for m in FENCE.finditer(text)]
    folder = w / md.stem
    folder.mkdir()
    for i, (info, code, line, end) in enumerate(blocks):
        tags = info.split(',')
        if tags[0] != 'nemerle' or 'ignore' in tags[1:]: continue
        expected = None
        if i + 1 < len(blocks) and blocks[i + 1][0] == 'text' and text[end:text.find('```', end)].strip() == '':
            expected = blocks[i + 1][1]
        count += 1
        ok, log = check(md.name, line, tags[1:], code, expected, folder)
        if not ok:
            failures.append('%s:%d\n%s\nexpected:\n%s' % (md.name, line, log.strip()[-1500:], expected))
            print('FAIL: %s:%d' % (md.name, line), flush=True)
if failures:
    print('\n\n'.join(failures))
    sys.exit(1)
shutil.rmtree(w, ignore_errors=True)
print('PASS: %d book examples compile and print what the book says' % count)
