#!/usr/bin/env python3
"""Render the logo's PNGs and the social preview from its SVGs (doc/assets/logo/nemerle.svg and nemerle-script.svg).

    build/build-logo.py

Where an SVG cannot be used (a VS Code extension's marketplace icon, a NuGet package's icon), a PNG is. The script
variant (nemerle-script.svg, the icon of .ns files) is the same drawing in yellow, drawn as its own file. The outputs
are committed: building does not need this. The first logo, and how it was traced, is in doc/assets/logo/legacy.
"""
import pathlib, re, subprocess, tempfile

repo = pathlib.Path(__file__).resolve().parents[1]
logo = repo / 'doc/assets/logo'
images = repo / 'tools/language-server/vscode/images'
svg = (logo / 'nemerle.svg').read_text()
script = (logo / 'nemerle-script.svg').read_text()

# the extension's file icons are the SVGs themselves
images.mkdir(parents=True, exist_ok=True)
(images / 'nemerle.svg').write_text(svg)
(images / 'nemerle-script.svg').write_text(script)

def render(source, path, width, height=None):
    with tempfile.NamedTemporaryFile('w', suffix='.svg', delete=False) as f: f.write(source)
    subprocess.run(['rsvg-convert', '-w', str(width), '-h', str(height or width), '-o', str(path), f.name], check=True)
    pathlib.Path(f.name).unlink()
    print('%s (%dx%d)' % (path.relative_to(repo), width, height or width))

render(svg, logo / 'nemerle-512.png', 512)             # README fallback, social images
render(svg, logo / 'nemerle-128.png', 128)             # NuGet package icon
render(svg, images / 'icon.png', 128)                  # the extension's marketplace icon
render(script, logo / 'nemerle-script-128.png', 128)

# the GitHub social preview (1280x640): the logo, then the name
viewbox = re.search(r'viewBox="([^"]*)"', svg).group(1)
inner = re.sub(r'^.*?<svg[^>]*>\s*(<title>.*?</title>\s*)?', '', svg, flags=re.S).rsplit('</svg>', 1)[0]
preview = '''<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="640" viewBox="0 0 1280 640">
  <rect width="1280" height="640" fill="#17151f"/>
  <svg x="110" y="140" width="360" height="360" viewBox="%s">
%s  </svg>
  <text x="540" y="330" font-family="Roboto" font-weight="500" font-size="132" fill="#ffffff">Nemerle</text>
  <text x="546" y="400" font-family="Roboto" font-weight="300" font-size="40" fill="#b8a6ff">The revived Nemerle, for .NET</text>
</svg>
''' % (viewbox, inner)
(logo / 'social-preview.svg').write_text(preview)
render(preview, logo / 'social-preview.png', 1280, 640)
