#!/usr/bin/env python3
"""Render the logo's PNGs from the responsive SVG (doc/assets/logo/nemerle.svg).

    build/build-logo.py

Where an SVG cannot be used (a VS Code extension's marketplace icon, a NuGet package's icon), a PNG is. The SVG picks
its level of detail by CSS media queries, which browsers and VS Code honour but rsvg-convert (which renders here) does
not, so each PNG is rendered with the level its size calls for. The PNGs are committed: building does not need this.
"""
import pathlib, re, subprocess, tempfile

repo = pathlib.Path(__file__).resolve().parents[1]
logo = repo / 'doc/assets/logo'
svg = (logo / 'nemerle.svg').read_text()

def level(size):
    return 'small' if size <= 40 else 'medium' if size <= 96 else 'full'

def only(name):
    """The SVG with only one level: the others and the media queries removed."""
    text = re.sub(r'<style>.*?</style>\s*', '', svg, flags=re.S)
    for other in ('full', 'medium', 'small'):
        if other != name: text = re.sub(r'  <g class="%s".*?</g>\n' % other, '', text, flags=re.S)
    return text

outputs = {
    logo / 'nemerle-512.png': 512,                                       # README fallback, social images
    logo / 'nemerle-128.png': 128,                                       # NuGet package icon
    repo / 'tools/language-server/vscode/images/icon.png': 128,          # the extension's marketplace icon
}
# the extension's file icon is the SVG itself (it picks its level in VS Code)
(repo / 'tools/language-server/vscode/images').mkdir(parents=True, exist_ok=True)
(repo / 'tools/language-server/vscode/images/nemerle.svg').write_text(svg)
for path, size in outputs.items():
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', suffix='.svg', delete=False) as f: f.write(only(level(size)))
    subprocess.run(['rsvg-convert', '-w', str(size), '-h', str(size), '-o', str(path), f.name], check=True)
    pathlib.Path(f.name).unlink()
    print('%s (%d px, %s detail)' % (path.relative_to(repo), size, level(size)))
