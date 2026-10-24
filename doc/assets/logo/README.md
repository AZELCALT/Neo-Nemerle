# The Nemerle logo

Designed by azelcalt for the revived Nemerle. It may be used, recoloured or resized, to refer to Nemerle, but not as
the logo or icon of another project ([LicenseRef-Nemerle-Logo](../../../LICENSES/LicenseRef-Nemerle-Logo.txt)).

| File | What it is |
|---|---|
| `nemerle.svg` | **the logo**, drawn as SVG |
| `nemerle-script.svg` | the script variant: the same drawing in yellow, the icon of `.ns` scripts |
| `nemerle-project.svg` | the silver project variant for `.nproj`, from `nemerle_logo_silver_cutout_asset.svg`, with a tighter viewport for small icons |
| `nemerle-512.png`, `nemerle-128.png`, `nemerle-script-128.png` | PNG renderings, for places that take no SVG (social images, NuGet) |
| `social-preview.png` (from `social-preview.svg`) | the GitHub social preview, 1280×640: Settings → General → Social preview |
| `legacy/` | the first logo, kept as the first version: its drawing, the SVG traced from it, and its renderings |

`build/build-logo.py` renders the PNGs, the social preview and the VS Code extension's marketplace icon
(`tools/language-server/vscode/images/icon.png`) from the SVGs, and copies the three variants as the extension's file
icons for `.n`, `.ns` and `.nproj`. It needs `rsvg-convert`.
