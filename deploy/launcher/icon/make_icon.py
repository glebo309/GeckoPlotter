"""Draw the GeckoPlotter icon (icon.svg): a gecko-green tile with one white line, a chromatogram that ends in a
curled lizard tail. Flat and bold like instrument-software icons, readable at 16 px.

Run: python make_icon.py  -> icon.svg. Rasterise it to icon.png (1024 px) with any browser, then build icon.ico
(Pillow) and icon.icns (macOS iconutil); see the launcher README.
"""
import math
from pathlib import Path

SIZE = 1024


def trace():
    """Baseline from the left, a small and a tall peak, then the line runs on and rolls up into a spiral."""
    pts = []
    for i in range(240):                                       # chromatogram part
        u = i / 239
        x = 140 + 420 * u
        y = 700 - 120 * math.exp(-((u - 0.25) / 0.06) ** 2) - 430 * math.exp(-((u - 0.64) / 0.065) ** 2)
        pts.append((x, y))
    cx, cy, turns = 710, 545, 1.3                              # tail spiral, entered from its bottom
    for i in range(1, 200):
        k = i / 199
        angle = math.pi / 2 - k * turns * 2 * math.pi           # start at the bottom, curl counter-clockwise upward
        radius = 155 * (1 - 0.62 * k)
        pts.append((cx + radius * math.cos(angle) + (1 - k) * 0, cy + radius * math.sin(angle)))
    return pts


def main():
    pts = trace()
    path = 'M ' + ' L '.join(f'{x:.1f},{y:.1f}' for x, y in pts)
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {SIZE} {SIZE}" width="{SIZE}" height="{SIZE}">
  <defs>
    <linearGradient id="tile" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#5aa877"/><stop offset="1" stop-color="#2c5240"/></linearGradient>
    <filter id="lift" x="-10%" y="-10%" width="120%" height="120%"><feDropShadow dx="0" dy="8" stdDeviation="10" flood-color="#0b1a12" flood-opacity=".35"/></filter>
  </defs>
  <rect x="40" y="40" width="944" height="944" rx="215" fill="url(#tile)"/>
  <rect x="41.5" y="41.5" width="941" height="941" rx="213.5" fill="none" stroke="#ffffff" stroke-opacity=".14" stroke-width="3"/>
  <path d="{path}" fill="none" stroke="#ffffff" stroke-width="46" stroke-linecap="round" stroke-linejoin="round" filter="url(#lift)"/>
</svg>
'''
    out = Path(__file__).with_name('icon.svg')
    out.write_text(svg)
    print('wrote', out)


if __name__ == '__main__':
    main()
