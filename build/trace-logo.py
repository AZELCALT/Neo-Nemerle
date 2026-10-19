#!/usr/bin/env python3
"""Trace the logo's source drawing into the responsive SVG (doc/assets/logo/nemerle.svg).

    build/trace-logo.py [--source doc/assets/logo/nemerle-source.png] [--output doc/assets/logo/nemerle.svg]

Needs OpenCV and Pillow (pip install opencv-python-headless pillow); run it again after a new drawing. The drawing's
shapes become straight-edged polygons, its disc a true circle, and its purple a gradient fitted to its pixels. Three
levels of detail go into the one SVG, which shows the one that fits the size it is drawn at (CSS media queries inside
it): full above 96 px; medium (the disc solid, the bottom-left notches closed) down to 41 px; small (the cuts closed
into one bold N, the disc a round hole) at 40 px and below. build/build-logo.py renders the PNGs from it.
"""
import argparse, pathlib
import cv2, numpy as np
from PIL import Image

repo = pathlib.Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
p.add_argument('--source', type=pathlib.Path, default=repo / 'doc/assets/logo/nemerle-source.png')
p.add_argument('--output', type=pathlib.Path, default=repo / 'doc/assets/logo/nemerle.svg')
a = p.parse_args()

rgba = np.array(Image.open(a.source).convert('RGBA'))
full = (rgba[:, :, 3] > 128).astype(np.uint8) * 255
ys, xs = np.nonzero(full)
x0, y0, x1, y1 = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
side = max(x1 - x0, y1 - y0); pad = side * 0.04
cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
viewbox = (cx - side / 2 - pad, cy - side / 2 - pad, side + 2 * pad)

def outline(c, eps=1.6):
    return 'M' + ' L'.join('%.1f,%.1f' % (q[0], q[1]) for q in cv2.approxPolyDP(c, eps, True)[:, 0, :]) + ' Z'

def paths(mask):
    """The mask's shapes as SVG path data: polygons (holes included), and a round shape as a true circle."""
    contours, hierarchy = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    result, disc = [], None
    for i, c in enumerate(contours):
        if hierarchy[0][i][3] != -1: continue
        holes = ''.join(' ' + outline(contours[j], 1.0) for j in range(len(contours)) if hierarchy[0][j][3] == i)
        area, perimeter = cv2.contourArea(c), cv2.arcLength(c, True)
        if 4 * np.pi * area / (perimeter * perimeter) > 0.85:
            (dx, dy), r = cv2.minEnclosingCircle(c)
            disc = (dx, dy, r)
            result.append('M%.1f,%.1f a%.1f,%.1f 0 1,0 %.1f,0 a%.1f,%.1f 0 1,0 %.1f,0 Z' % (dx - r, dy, r, r, 2 * r, r, r, -2 * r) + holes)
        else:
            result.append(outline(c) + holes)
    return result, disc

full_paths, disc = paths(full)
(dx, dy, dr) = disc
# medium: the disc solid (no plus), the bottom-left notches closed
medium = full.copy()
cv2.circle(medium, (int(round(dx)), int(round(dy))), int(dr), 255, -1)
corner = medium[int(y0 + 0.8 * (y1 - y0)):, :int(x0 + 0.25 * (x1 - x0))]
corner[:] = cv2.morphologyEx(corner, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 45)))
# small: the cuts closed into one silhouette (within the drawing's outline), the disc a round hole
small = cv2.morphologyEx(full, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (45, 45)))
small = cv2.bitwise_and(small, cv2.dilate(full, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (47, 47))))
cv2.circle(small, (int(round(dx)), int(round(dy))), int(dr * 0.62), 0, -1)
medium_paths, _ = paths(medium)
small_paths, _ = paths(small)

# the purple: a linear gradient fitted to the drawing's pixels, along the direction its brightness changes most
inside = full > 0
X = np.stack([np.ones(inside.sum()), xs, ys], 1)
coef = [np.linalg.lstsq(X, rgba[:, :, k][inside].astype(float), rcond=None)[0] for k in range(3)]
g = np.array([sum(c[1] for c in coef), sum(c[2] for c in coef)]); g /= np.linalg.norm(g)
projection = xs * g[0] + ys * g[1]
middle = np.array([cx, cy])
start = middle + (projection.min() - middle @ g) * g
end = middle + (projection.max() - middle @ g) * g
def colour(q): return '#%02x%02x%02x' % tuple(int(np.clip(c[0] + c[1] * q[0] + c[2] * q[1], 0, 255)) for c in coef)

group = lambda name, ps: f'  <g class="{name}" fill="url(#purple)" fill-rule="evenodd">\n' + ''.join(f'    <path d="{d}"/>\n' for d in ps) + '  </g>\n'
svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="{viewbox[0]:.1f} {viewbox[1]:.1f} {viewbox[2]:.1f} {viewbox[2]:.1f}">
  <title>Nemerle</title>
  <!-- One logo, three levels of detail: the SVG shows the one that fits the size it is drawn at.
       full above 96 px; medium (no plus, no notches) from 41 to 96 px; small (the bold N) at 40 px and below.
       Traced from nemerle-source.png by build/trace-logo.py; build/build-logo.py renders the PNGs. -->
  <style>
    .medium, .small {{ display: none }}
    @media (max-width: 96px) {{ .full {{ display: none }} .medium {{ display: inline }} }}
    @media (max-width: 40px) {{ .medium {{ display: none }} .small {{ display: inline }} }}
  </style>
  <defs>
    <linearGradient id="purple" gradientUnits="userSpaceOnUse" x1="{start[0]:.1f}" y1="{start[1]:.1f}" x2="{end[0]:.1f}" y2="{end[1]:.1f}">
      <stop offset="0" stop-color="{colour(start)}"/><stop offset="1" stop-color="{colour(end)}"/>
    </linearGradient>
  </defs>
''' + group('full', full_paths) + group('medium', medium_paths) + group('small', small_paths) + '</svg>\n'
a.output.write_text(svg)
print('logo: %s (%d bytes)' % (a.output, len(svg)))
