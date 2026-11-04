#!/usr/bin/env python3
"""Run the book's examples (doc/book/src/*.md) in other ways than the book does, to find where one way differs.

    check-book-variants.py --toolchain DIR --references REFS [--chapter NAME] [--variants script,parallel,incremental]

check-book.py runs each example as written. Here every plain example (a `nemerle` block of one file, with no other tag,
no `// ncc:` arguments and a `text` block with its output) is also run as
    script       the same code as a `.ns` script under nscript (a file's top level and a script's should agree)
    parallel     compiled with -parallel (method bodies typed on worker threads must give the same program)
    incremental  compiled twice with one -incremental folder, the second build reusing the first
and each must print what the book says. Known, intended differences are listed in KNOWN with the reason. Use a stage-2
toolchain (./bootstrap's): -parallel types in order with a compiler that has no thread-safe colors (./dev's)."""
import argparse, pathlib, re, shutil, subprocess, sys, tempfile

p = argparse.ArgumentParser()
p.add_argument('--toolchain', type=pathlib.Path, required=True)
p.add_argument('--references', type=pathlib.Path, required=True)
p.add_argument('--chapter', help='only chapters whose file name contains this')
p.add_argument('--variants', default='script,parallel,incremental')
a = p.parse_args()
T = a.toolchain.resolve()
R = a.references.resolve()
variants = a.variants.split(',')
book = pathlib.Path(__file__).resolve().parents[1] / 'doc/book/src'
w = pathlib.Path(tempfile.mkdtemp(prefix='nemerle-book-variants-'))
FENCE = re.compile(r'^```([^\n]*)\n(.*?)^```\s*$', re.S | re.M)

# (chapter, line, variant) -> why that way of running the example differs. Each is an OPEN bug, listed so the suite can
# run in ./bootstrap meanwhile; the summary line counts them, and an entry goes once its bug is fixed.
KNOWN = {
    ('05-functions.md', 104, 'script'): 'a script function with a `this` parameter is an instance member, not an extension',
    ('07-files-and-modules.md', 279, 'script'): '`top name` (the file\'s own top-level name) does not parse in a script',
}


def plain(tags, code):
    """An example this check can run another way: one file, no tag, no compiler arguments."""
    return not tags[1:] and not re.search(r'^\s*// (file|ncc): ', code, re.M)


def run_program(root, exe):
    shutil.copy2(T / 'Nemerle.dll', root / 'Nemerle.dll')
    shutil.copy2(T / 'ncc.runtimeconfig.json', root / (exe.stem + '.runtimeconfig.json'))
    return subprocess.run(['dotnet', str(exe)], cwd=root, capture_output=True, text=True, timeout=60)


def compile_n(root, source, out, *extra):
    return subprocess.run(['dotnet', str(T / 'ncc.exe'), '-target-references:' + str(R), str(source),
                           '-source-root:' + str(root), '-out:' + str(out), '-no-color', *extra],
                          cwd=root, capture_output=True, text=True)


def variant(kind, root, code):
    """(output, diagnostics) of running the example `kind`'s way, or (None, diagnostics) when it did not build."""
    root.mkdir(parents=True)
    if kind == 'script':
        (root / 'main.ns').write_text(code)
        r = subprocess.run(['dotnet', str(T / 'nscript.exe'), 'run', 'main.ns', '--no-cache'], cwd=root,
                           capture_output=True, text=True, timeout=120)
        return (r.stdout if r.returncode == 0 else None), r.stderr
    (root / 'main.n').write_text(code)
    if kind == 'parallel':
        r = compile_n(root, root / 'main.n', root / 'main.exe', '-parallel')
        if r.returncode != 0: return None, r.stdout + r.stderr
    elif kind == 'incremental':
        cache = root / 'incremental'
        for attempt in (1, 2):   # the second build reuses the first one's code
            r = compile_n(root, root / 'main.n', root / 'main.exe', '-incremental:' + str(cache))
            if r.returncode != 0: return None, 'build %d: %s' % (attempt, r.stdout + r.stderr)
    else:
        raise SystemExit('unknown variant ' + kind)
    r = run_program(root, root / 'main.exe')
    return (r.stdout if r.returncode == 0 else None), r.stderr


failures, count, known = [], 0, 0
for md in sorted(book.glob('*.md')):
    if a.chapter and a.chapter not in md.name: continue
    text = md.read_text()
    blocks = [(m.group(1).strip(), m.group(2), text.count('\n', 0, m.start()) + 1, m.end()) for m in FENCE.finditer(text)]
    for i, (info, code, line, end) in enumerate(blocks):
        tags = info.split(',')
        if tags[0] != 'nemerle' or not plain(tags, code): continue
        if not (i + 1 < len(blocks) and blocks[i + 1][0] == 'text' and text[end:text.find('```', end)].strip() == ''):
            continue
        expected = blocks[i + 1][1]
        for kind in variants:
            count += 1
            output, diagnostics = variant(kind, w / md.stem / ('example%d' % line) / kind, code)
            if output is not None and output.rstrip() == expected.rstrip(): continue
            if (md.name, line, kind) in KNOWN:
                known += 1; continue
            failures.append('%s:%d [%s]\n%s\nexpected:\n%s' % (md.name, line, kind,
                            (diagnostics if output is None else 'printed:\n' + output).strip()[-1500:], expected.rstrip()))
            print('FAIL: %s:%d [%s]' % (md.name, line, kind), flush=True)
if failures:
    print('\n\n'.join(failures))
    sys.exit(1)
shutil.rmtree(w, ignore_errors=True)
print('PASS: %d runs of the book\'s examples (%s) print what the book says%s'
      % (count, ', '.join(variants), ' (%d known differences)' % known if known else ''))
