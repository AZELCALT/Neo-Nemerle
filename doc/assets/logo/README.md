# The Nemerle logo

Designed by azelcalt for the revived Nemerle. It may be used, recoloured or resized, to refer to Nemerle, but not as
the logo or icon of another project ([LicenseRef-Nemerle-Logo](../../../LICENSES/LicenseRef-Nemerle-Logo.txt)).

| File | What it is |
|---|---|
| `nemerle-source.png` | the drawing, with a transparent background: the source of everything else |
| `nemerle.svg` | **the logo**: one vector file with three levels of detail, which picks the one that fits the size it is drawn at |
| `nemerle-512.png`, `nemerle-128.png` | PNG renderings, for places that take no SVG (social images, NuGet) |
| `nemerle-script.svg`, `nemerle-script-128.png` | the script variant: the same drawing and shading in yellow, the icon of `.ns` scripts |
| `social-preview.png` (from `social-preview.svg`) | the GitHub social preview, 1280×640: Settings → General → Social preview |

The SVG holds three levels and switches with CSS media queries inside it, so browsers, GitHub and VS Code show:

- **full** (above 96 px): the drawing as it is;
- **medium** (41 to 96 px): the disc solid (no plus) and the small notches at the bottom left closed;
- **small** (40 px and below): the cuts closed into one bold N, the disc a round hole.

`build/trace-logo.py` traces `nemerle-source.png` into `nemerle.svg` again after a new drawing (it needs OpenCV:
`pip install opencv-python-headless pillow`). `build/build-logo.py` renders the PNGs, and the VS Code extension's
icon (`tools/language-server/vscode/images/icon.png`), with the level each size calls for: `rsvg-convert` ignores the
media queries, so the script picks the level itself. The extension's file icon for `.n` files is the SVG itself
(`tools/language-server/vscode/images/nemerle.svg`, a copy).
The yellow of the script variant is derived, not drawn: `build/build-logo.py` turns each purple gradient stop to yellow
keeping its lightness, saturation and the hue distance between the stops (`#2e00b2`→`#b28400`, `#670cf2`→`#f2d60c`), and
writes `nemerle-script.svg` and the extension's `.ns` icon (`images/nemerle-script.svg`).
