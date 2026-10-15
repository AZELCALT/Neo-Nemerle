#!/usr/bin/env python3
"""Point Nemerle sources at the compiler's file modules (Nemerle.Compiler.Typer -> Nemerle.Compiler.Typer.Typer, ...).

    rename-compiler-references.py [--quotations-only] FILE...

The symbol table nemerle/ncc/Nemerle/Compiler/SYMBOLS.json maps each top-level compiler name to its module.
- Qualified `Nemerle.Compiler.<Name>` (and `<Alias>.<Name>` for `using Alias = Nemerle.Compiler;`) becomes
  `Nemerle.Compiler.<Module>.<Name>`.
- In a file that opens Nemerle.Compiler, the module qualifiers `Parsetree.`, `Typedtree.` and those of the compiler
  macro modules (UtilMacros, MessageMacros, SolverMacros) become fully qualified, and `using Nemerle.Compiler;` is
  replaced by `using Nemerle.Compiler.<Module>;` for each module whose names the file uses: a directory is never
  imported, and short names then mean the class, not the module of the same name.
- `Macros.<macro>` naming a standard macro of Nemerle.Macros (Manager, ImplicitCTX...) becomes `Nemerle.Macros.<macro>`.
- Inside quotations (<[ ... ]>, code generated into other files) short compiler names become fully qualified, so they
  resolve wherever the code is expanded; so do type paths in strings ("Nemerle.Compiler.Location", for Lookup).
--no-strings: leave strings alone (a compiler of the previous layout reflects on its own types with them).
--keep-quoted-short: short names in quotations stay short (they resolve through the file's imports, which this adds);
  for sources whose own types share names with the compiler's (Nitra: ParseResult, Location...), where the
  enclosing namespace decides.
--assume-open: treat every file as opening the compiler (its own sources, whose modules import each other).
--quotations-only: only the quotations change.
C# sources (*.cs) import modules with `using static Nemerle.Compiler.<Module>;` (a module is a static class). Bridge macros built by a compiler of the previous layout generate
code for the new one (their own code still uses the previous API)."""
import json, pathlib, re, sys

here = pathlib.Path(__file__).resolve().parent
compiler_dir = here.parents[1] / 'ncc' / 'Nemerle' / 'Compiler'
symbols = json.loads((compiler_dir / 'SYMBOLS.json').read_text())
owner = {name: modules[0] for name, modules in symbols.items()}
modules = {p.stem for p in compiler_dir.glob('*.n')}
# Macros.Manager () and friends are the standard macros of Nemerle.Macros, not members of the compiler's class Macros
nemerle_macros = set(re.findall(r'(?m)^macro\s+(\w+)', (here.parents[1] / 'macros' / 'Nemerle' / 'Macros.n').read_text()))


def migrated(rest):
    """Nemerle.Compiler.<rest> already names a module member (Nemerle.Compiler.Typer.Typer): left alone."""
    return len(rest) > 1 and rest[0] in modules and owner.get(rest[1]) == rest[0]
MODULE_QUALIFIERS = {'Parsetree', 'Typedtree', 'UtilMacros', 'MessageMacros', 'SolverMacros'}
quotations_only = '--quotations-only' in sys.argv
no_strings = '--no-strings' in sys.argv
keep_quoted_short = '--keep-quoted-short' in sys.argv
assume_open = '--assume-open' in sys.argv   # the compiler's own sources: every compiler name is reachable
files = [a for a in sys.argv[1:] if not a.startswith('--')]

TOKEN = re.compile(r'//[^\n]*|/\*.*?\*/|<#.*?#>|@"(?:[^"]|"")*"|"(?:[^"\\\n]|\\.)*"|\'(?:\\.|[^\\\'\n])\'|<\[|\]>|\$\(|[()]|[A-Za-z_][\w.]*', re.S)


USING_DIRECTIVE = re.compile(r'[ \t\ufeff]*using[ \t]+(?:static[ \t]+)?(?:\w+[ \t]*=[ \t]*)?[\w.]+[ \t]*;?[ \t]*\r?$')
DECLARES = re.compile(r'\b(?:public|private|protected|internal|static|override|virtual|abstract|new|mutable|def|class|module|'
                      r'variant|interface|struct|enum|type|macro|namespace|event|this|extern)\s+$'
                      r'|\.\.\$\((?:[^()]|\([^()]*\))*\)\s+$')   # ..$(modifiers) Name : type


def tokens(text, csharp=False):
    """(start, end, word, in_quotation) for identifier paths outside strings and comments. A splice $( ... ) inside a
    quotation is macro-side code again."""
    stack = []   # 'q' quotation, 'p' pattern quotation, 's' splice, '(' parenthesis
    for m in TOKEN.finditer(text):
        s = m.group(0)
        if s == '<[':
            # a pattern quotation (| <[ PExpr ]> =>) matches source text by name: never rewritten
            before = text[:m.start()].rstrip()
            stack.append('p' if before.endswith('|') or 'p' in stack else 'q')
        elif s == ']>':
            while stack and stack[-1] == '(': stack.pop()
            if stack and stack[-1] in 'qp': stack.pop()
        elif s == '$(': stack.append('s' if 'q' in stack or 'p' in stack else '(')
        elif s == '(': stack.append('(')
        elif s == ')':
            if stack and stack[-1] in '(s': stack.pop()
        elif s[0].isalpha() or s[0] == '_':
            if m.start() and text[m.start() - 1] in '$@.': continue   # $name splices, @keyword escapes, members
            before = text[max(0, m.start() - 40):m.start()]
            if DECLARES.search(before) and not (csharp and re.search(r'\bnew\s+$', before)): continue   # the name being declared
            context = next((c for c in reversed(stack) if c != '('), None)
            yield m.start(), m.end(), s, context == 'q'


def rewrite(text, csharp=False):
    aliases = re.findall(r'(?m)^[ \t\ufeff]*using[ \t]+(\w+)[ \t]*=[ \t]*Nemerle\.Compiler[ \t]*;', text)
    opens = assume_open or bool(re.search(r'(?m)^[ \t\ufeff]*using[ \t]+Nemerle\.Compiler[ \t]*;?[ \t]*\r?$', text)) \
            or bool(re.search(r'(?m)^[ \t]*namespace[ \t]+Nemerle\.Compiler\b', text))
    # Compiler.Location written relative to an opened (or enclosing) Nemerle namespace
    opens_nemerle = bool(re.search(r'(?m)^[ \t\ufeff]*using[ \t]+Nemerle[ \t]*;?[ \t]*\r?$', text)) \
                    or bool(re.search(r'(?m)^[ \t]*namespace[ \t]+Nemerle\b', text))
    edits, used = [], set()
    for start, end, word, quoted in tokens(text, csharp):
        if quotations_only and not quoted: continue
        line_start = text.rfind('\n', 0, start) + 1
        line_end = text.find('\n', start); line_end = len(text) if line_end < 0 else line_end
        in_using = USING_DIRECTIVE.match(text[line_start:line_end]) is not None
        parts = word.split('.')
        head = None
        if parts[:2] == ['Nemerle', 'Compiler'] and len(parts) > 2: head, rest = 2, parts[2:]
        elif parts[0] in aliases and len(parts) > 1: head, rest = 1, parts[1:]
        elif parts[0] == 'Compiler' and len(parts) > 1 and parts[1] in owner and opens_nemerle: head, rest = 1, parts[1:]
        if head is not None:
            # `using Nemerle.Compiler.Typer;` now imports the module; an alias (`using T = Nemerle.Compiler.Typer;`) named the class
            alias_using = in_using and '=' in text[line_start:start]
            if rest[0] in owner and not migrated(rest) and not (in_using and not alias_using and len(rest) == 1 and (rest[0] in modules or rest[0] in MODULE_QUALIFIERS)):
                new = 'Nemerle.Compiler.%s.%s' % (owner[rest[0]], '.'.join(rest))
                edits.append((start, end, new))
            elif head == 1:
                edits.append((start, end, 'Nemerle.Compiler.' + '.'.join(rest)))
            continue
        if parts[0] == 'Macros' and len(parts) == 2 and parts[1] in nemerle_macros:
            edits.append((start, end, 'Nemerle.Macros.' + parts[1])); continue
        if not opens or in_using: continue
        if parts[0] in MODULE_QUALIFIERS and len(parts) > 1:
            edits.append((start, end, 'Nemerle.Compiler.' + word)); continue
        if parts[0] in owner:
            if quoted and not keep_quoted_short: edits.append((start, end, 'Nemerle.Compiler.%s.%s' % (owner[parts[0]], word)))
            else: used.add(owner[parts[0]])
    # type paths in strings (Manager.Lookup ("Nemerle.Compiler.Location")) name types of the compilation target
    for m in ([] if no_strings else re.finditer(r'"Nemerle\.Compiler\.([A-Za-z_]\w*)((?:\.[A-Za-z_]\w*)*)"', text)):
        if m.group(1) in owner and not migrated([m.group(1)] + m.group(2).split('.')[1:]) and not any(s <= m.start() < e for s, e, _ in edits):
            edits.append((m.start(), m.end(), '"Nemerle.Compiler.%s.%s%s"' % (owner[m.group(1)], m.group(1), m.group(2))))
    for s, e, r in sorted(edits, reverse=True): text = text[:s] + r + text[e:]
    if quotations_only or not opens: return text
    nl = '\r\n' if '\r\n' in text else '\n'
    if csharp:
        # a module is a static class: C# imports it with `using static`
        # only the directives heading the file (a `using` line inside a string literal is someone else's source)
        head = re.match(r'(?:[ \t\ufeff]*(?:using[^\n]*|//[^\n]*|)\r?\n)*', text).end()
        text = re.sub(r'(?m)^([ \t\ufeff]*)using[ \t]+Nemerle\.Compiler\.(\w+)[ \t]*;',
                      lambda m: '%susing static Nemerle.Compiler.%s;' % (m.group(1), m.group(2)) if m.group(2) in modules else m.group(0),
                      text[:head]) + text[head:]
    imports = [m for m in sorted(used)
               if not re.search(r'(?m)^[ \t\ufeff]*using[ \t]+(?:static[ \t]+)?Nemerle\.Compiler\.%s[ \t]*;?[ \t]*\r?$' % re.escape(m), text)]
    semicolon = '' if '#pragma indent' in text else ';'
    m = re.search(r'(?m)^([ \t\ufeff]*)using[ \t]+Nemerle\.Compiler[ \t]*;?[ \t]*\r?(?:\n|$)', text)
    if m:
        indent = m.group(1).lstrip('\ufeff')
        bom = '\ufeff' if m.group(1).startswith('\ufeff') else ''
        directive = 'using static' if csharp else 'using'
        text = text[:m.start()] + bom + ''.join('%s%s Nemerle.Compiler.%s%s%s' % (indent, directive, i, semicolon, nl) for i in imports) + text[m.end():]
    return text


for path in files:
    with open(path, encoding='utf-8', errors='surrogateescape', newline='') as f: original = f.read()
    text = rewrite(original, path.endswith('.cs'))
    if text != original:
        with open(path, 'w', encoding='utf-8', errors='surrogateescape', newline='') as f: f.write(text)
        print('updated', path)
