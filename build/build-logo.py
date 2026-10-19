#!/usr/bin/env python3
"""Render the logo's PNGs from the responsive SVG (doc/assets/logo/nemerle.svg), and its script variant.

    build/build-logo.py

Where an SVG cannot be used (a VS Code extension's marketplace icon, a NuGet package's icon), a PNG is. The SVG picks
its level of detail by CSS media queries, which browsers and VS Code honour but rsvg-convert (which renders here) does
not, so each PNG is rendered with the level its size calls for. The PNGs are committed: building does not need this.

The script variant (nemerle-script.svg, the icon of .ns files) is the same drawing in yellow: each gradient stop keeps
its lightness and saturation and the distance in hue between the stops, turned from purple to yellow.
"""
import colorsys, pathlib, re, subprocess, tempfile

repo = pathlib.Path(__file__).resolve().parents[1]
logo = repo / 'doc/assets/logo'
svg = (logo / 'nemerle.svg').read_text()

def yellow(text):
    """The script variant: the purple gradient's stops turned to yellow (the first stop's hue to 44.5 degrees, the
    others as far from it as they were), lightness and saturation kept."""
    stops = re.findall(r'stop-color="#([0-9a-fA-F]{6})"', text)
    hls = [colorsys.rgb_to_hls(*(int(s[i:i + 2], 16) / 255 for i in (0, 2, 4))) for s in stops]
    turn = 44.5 / 360 - hls[0][0]
    for s, (h, l, s_) in zip(stops, hls):
        rgb = colorsys.hls_to_rgb((h + turn) % 1, l, s_)
        text = text.replace('stop-color="#%s"' % s, 'stop-color="#%02x%02x%02x"' % tuple(round(c * 255) for c in rgb), 1)
    return text.replace('<title>Nemerle</title>', '<title>Nemerle script</title>').replace('id="purple"', 'id="yellow"').replace('url(#purple)', 'url(#yellow)')

script = yellow(svg)

def level(size):
    return 'small' if size <= 40 else 'medium' if size <= 96 else 'full'

def only(name, source=svg):
    """The SVG with only one level: the others and the media queries removed."""
    text = re.sub(r'<style>.*?</style>\s*', '', source, flags=re.S)
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
# and the script variant: the icon of .ns files
(logo / 'nemerle-script.svg').write_text(script)
(repo / 'tools/language-server/vscode/images/nemerle-script.svg').write_text(script)
outputs[logo / 'nemerle-script-128.png'] = 128
for path, size in outputs.items():
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', suffix='.svg', delete=False) as f: f.write(only(level(size), script if 'script' in path.name else svg))
    subprocess.run(['rsvg-convert', '-w', str(size), '-h', str(size), '-o', str(path), f.name], check=True)
    pathlib.Path(f.name).unlink()
    print('%s (%d px, %s detail)' % (path.relative_to(repo), size, level(size)))
