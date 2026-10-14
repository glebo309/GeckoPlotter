"""Draw the GeckoPlotter launcher icon (icon.svg): a top-down gecko walking along a chromatogram.

Run: python make_icon.py  -> icon.svg. Rasterise it to icon.png (1024 px) with any browser or Inkscape, then build
icon.ico (Windows) and icon.icns (macOS) with build_icons.sh.
"""
import math
from pathlib import Path

SIZE = 1024


def spine(n=160):
    """Head at upper right, body sweeping down-left, tail curling up at the end (built from a heading angle)."""
    pts, x, y, length = [], 760.0, 225.0, 800.0
    for i in range(n + 1):
        s = i / n
        heading = 2.05 + 0.45 * math.sin(4.2 * s - 0.6) + (9.0 * (s - 0.58) ** 1.3 if s > 0.58 else 0)
        if s < 0.03:
            r = 36 + s * 800
        elif s < 0.12:
            r = 60
        elif s < 0.18:
            r = 44 + (0.18 - s) * 250
        elif s < 0.58:
            r = 70 - abs(s - 0.38) * 60
        else:
            r = max(6, 58 * max(0.0, 1 - (s - 0.58) / 0.42) ** 0.9)
        pts.append((x, y, r))
        x += math.cos(heading) * length / n
        y += math.sin(heading) * length / n
    return pts


def outline(pts):
    left, right = [], []
    for i, (x, y, r) in enumerate(pts):
        x2, y2, _ = pts[min(i + 1, len(pts) - 1)]
        x1, y1, _ = pts[max(i - 1, 0)]
        dx, dy = x2 - x1, y2 - y1
        n = math.hypot(dx, dy) or 1
        nx, ny = -dy / n, dx / n
        left.append((x + nx * r, y + ny * r))
        right.append((x - nx * r, y - ny * r))
    head = pts[0]
    tip = ' '.join(f'{head[0] + math.cos(a) * head[2]:.1f},{head[1] + math.sin(a) * head[2]:.1f}'
                   for a in [math.atan2(left[0][1] - head[1], left[0][0] - head[0]) - k * math.pi / 12 for k in range(13)])
    return 'M ' + ' L '.join(f'{x:.1f},{y:.1f}' for x, y in left) + ' L ' + \
           ' L '.join(f'{x:.1f},{y:.1f}' for x, y in reversed(right)) + ' L ' + tip.replace(' ', ' L ') + ' Z'


def normal(pts, s):
    i = round(s * (len(pts) - 1))
    x2, y2, _ = pts[min(i + 1, len(pts) - 1)]
    x1, y1, _ = pts[max(i - 1, 0)]
    n = math.hypot(x2 - x1, y2 - y1)
    return pts[i], (-(y2 - y1) / n, (x2 - x1) / n), ((x2 - x1) / n, (y2 - y1) / n)


def leg(pts, s, side, front):
    (x, y, r), (nx, ny), (tx, ty) = normal(pts, s)
    sx, sy = x + nx * side * r * 0.6, y + ny * side * r * 0.6
    back = 1 if front else -1                      # along the body: +t goes toward the tail
    jx, jy = sx + nx * side * 95 + tx * back * 45, sy + ny * side * 95 + ty * back * 45
    fx, fy = jx + nx * side * 40 - tx * back * 85, jy + ny * side * 40 - ty * back * 85
    d = f'M {sx:.1f},{sy:.1f} Q {jx:.1f},{jy:.1f} {fx:.1f},{fy:.1f}'
    toes = []
    ux, uy = (fx - jx), (fy - jy)
    un = math.hypot(ux, uy)
    ux, uy = ux / un, uy / un
    for a in (-1.0, -0.5, 0, 0.5, 1.0):
        ex = fx + (ux * math.cos(a) - uy * math.sin(a)) * 52
        ey = fy + (ux * math.sin(a) + uy * math.cos(a)) * 52
        toes.append((fx, fy, ex, ey))
    return d, toes


def main():
    pts = spine()
    legs, toes = [], []
    for s, side, front in ((0.24, 1, True), (0.24, -1, True), (0.56, 1, False), (0.56, -1, False)):
        d, t = leg(pts, s, side, front)
        legs.append(d)
        toes += t
    (hx, hy, hr), (nx, ny), (tx, ty) = normal(pts, 0.06)
    eyes = [(hx + nx * k * 34 - tx * 6, hy + ny * k * 34 - ty * 6) for k in (1, -1)]
    # chromatogram: flat baseline with two peaks, running behind the gecko
    trace = []
    for i in range(201):
        u = i / 200
        x = 110 + 804 * u
        y = 860 - 330 * math.exp(-((u - 0.62) / 0.035) ** 2) - 170 * math.exp(-((u - 0.80) / 0.03) ** 2) \
            - 60 * math.exp(-((u - 0.34) / 0.05) ** 2)
        trace.append(f'{x:.1f},{y:.1f}')
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {SIZE} {SIZE}" width="{SIZE}" height="{SIZE}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#2a2c30"/><stop offset="1" stop-color="#151618"/></linearGradient>
    <linearGradient id="skin" gradientUnits="userSpaceOnUse" x1="760" y1="200" x2="200" y2="800"><stop offset="0" stop-color="#9be3b4"/><stop offset=".45" stop-color="#4f9a6d"/><stop offset="1" stop-color="#355f49"/></linearGradient>
    <linearGradient id="skinb" gradientUnits="userSpaceOnUse" x1="760" y1="200" x2="200" y2="800"><stop offset="0" stop-color="#9be3b4"/><stop offset=".45" stop-color="#4f9a6d"/><stop offset="1" stop-color="#355f49"/></linearGradient>
    <filter id="soft" x="-10%" y="-10%" width="120%" height="120%"><feDropShadow dx="0" dy="10" stdDeviation="14" flood-color="#000" flood-opacity=".45"/></filter>
  </defs>
  <rect x="40" y="40" width="944" height="944" rx="215" fill="url(#bg)"/>
  <rect x="40.5" y="40.5" width="943" height="943" rx="214.5" fill="none" stroke="#ffffff" stroke-opacity=".08" stroke-width="3"/>
  <line x1="110" y1="860" x2="914" y2="860" stroke="#ffffff" stroke-opacity=".10" stroke-width="6"/>
  <polyline points="{' '.join(trace)}" fill="none" stroke="#f0913a" stroke-width="16" stroke-linejoin="round" stroke-linecap="round"/>
  <g filter="url(#soft)">
    {''.join(f'<path d="{d}" fill="none" stroke="url(#skin)" stroke-width="30" stroke-linecap="round"/>' for d in legs)}
    {''.join(f'<line x1="{a:.1f}" y1="{b:.1f}" x2="{c:.1f}" y2="{e:.1f}" stroke="#4f9a6d" stroke-width="13" stroke-linecap="round"/><circle cx="{c:.1f}" cy="{e:.1f}" r="12" fill="#7cc79a"/>' for a, b, c, e in toes)}
    {''.join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="url(#skinb)"/>' for x, y, r in pts)}
  </g>
  {''.join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="15" fill="#f6f7f8"/><circle cx="{x + tx * -3:.1f}" cy="{y + ty * -3:.1f}" r="7" fill="#151618"/>' for x, y in eyes)}
</svg>
'''
    out = Path(__file__).with_name('icon.svg')
    out.write_text(svg)
    print('wrote', out)


if __name__ == '__main__':
    main()
