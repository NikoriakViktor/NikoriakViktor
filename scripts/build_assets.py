"""Generate the profile SVGs from data/profile.json.

Usage:  pip install -r scripts/requirements.txt && python scripts/build_assets.py
Output: assets/*.svg

All text is converted to vector outlines (Manrope + IBM Plex Mono, the
GeoHydroAI site fonts), because GitHub shows SVGs as images and cannot
load web fonts inside them. Fonts live in scripts/fonts (SIL OFL).
"""

from __future__ import annotations

import base64
import json
import math
from functools import lru_cache
from pathlib import Path
from xml.sax.saxutils import escape

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "profile.json"
OUT = ROOT / "assets"
FONTS = Path(__file__).resolve().parent / "fonts"

# Palette from the GeoHydroAI frontend (geoai-frontend-v2).
C = {
    "deep": "#070D18",
    "bg": "#0A1322",
    "panel": "#0D182A",
    "border": "#1C2A40",
    "contour": "#22334D",
    "text": "#EAF2FF",
    "muted": "#9FB2D4",
    "faint": "#7E93B6",
    "accent": "#2DD4BF",
}


# ---------------------------------------------------------------- text → outlines

@lru_cache(maxsize=None)
def load_font(family: str, weight: int) -> TTFont:
    if family == "sans":
        font = TTFont(FONTS / "Manrope-VF.ttf")
        return instantiateVariableFont(font, {"wght": weight})
    name = "Medium" if weight >= 500 else "Regular"
    return TTFont(FONTS / f"IBMPlexMono-{name}.ttf")


def text_width(s: str, size: float, family: str = "sans", weight: int = 400, ls: float = 0) -> float:
    font = load_font(family, weight)
    cmap, hmtx = font.getBestCmap(), font["hmtx"]
    scale = size / font["head"].unitsPerEm
    adv = sum(hmtx[cmap.get(ord(ch), ".notdef")][0] for ch in s)
    return adv * scale + ls * max(len(s) - 1, 0)


def text(s: str, x: float, y: float, size: float, fill: str, family: str = "sans",
         weight: int = 400, anchor: str = "start", ls: float = 0) -> str:
    """Render a single line of text as one <path>. y is the baseline."""
    font = load_font(family, weight)
    cmap, hmtx, glyphs = font.getBestCmap(), font["hmtx"], font.getGlyphSet()
    scale = size / font["head"].unitsPerEm
    w = text_width(s, size, family, weight, ls)
    cx = x - (w if anchor == "end" else w / 2 if anchor == "middle" else 0)
    pen = SVGPathPen(glyphs, ntos=lambda v: f"{v:.1f}".rstrip("0").rstrip("."))
    for ch in s:
        name = cmap.get(ord(ch), ".notdef")
        glyphs[name].draw(TransformPen(pen, (scale, 0, 0, -scale, cx, y)))
        cx += hmtx[name][0] * scale + ls
    return f'<path fill="{fill}" d="{pen.getCommands()}"/>'


def mono(s, x, y, size, fill, weight=400, anchor="start", ls=0):
    return text(s, x, y, size, fill, "mono", weight, anchor, ls)


def check_fits(s: str, size: float, max_w: float, **kw) -> None:
    w = text_width(s, size, **kw)
    if w > max_w:
        raise SystemExit(f"Text too wide ({w:.0f}px > {max_w}px): {s!r} — shorten it in data/profile.json")


# ---------------------------------------------------------------- relief

def svg_doc(w: int, h: int, title: str, body: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" role="img" aria-label="{escape(title)}">\n'
        f"<title>{escape(title)}</title>\n{body}\n</svg>\n"
    )


def elevation(x: float, y: float) -> float:
    """Synthetic Carpathian-like relief: a few ridges plus gentle noise."""
    hills = [(930, 110, 170, 1.0), (1120, 290, 150, 0.8), (740, 330, 130, 0.6), (1180, 40, 110, 0.5)]
    z = sum(a * math.exp(-((x - cx) ** 2 + ((y - cy) * 1.4) ** 2) / (2 * r * r)) for cx, cy, r, a in hills)
    z += 0.05 * math.sin(x / 47 + y / 61) + 0.04 * math.sin(x / 23 - y / 37)
    return z


def isolines(w: int, h: int, levels: list[float], field=elevation, step: int = 6) -> list[str]:
    """Marching squares over field(); returns one path-d per contour level."""
    nx, ny = w // step + 2, h // step + 2
    grid = [[field(i * step, j * step) for i in range(nx)] for j in range(ny)]
    out = []
    for lv in levels:
        segs = []
        for j in range(ny - 1):
            for i in range(nx - 1):
                a, b = grid[j][i], grid[j][i + 1]
                c_, d = grid[j + 1][i + 1], grid[j + 1][i]
                x0, y0 = i * step, j * step

                def lerp(p, q):
                    return 0.5 if p == q else (lv - p) / (q - p)

                pts = []
                if (a > lv) != (b > lv):
                    pts.append((x0 + step * lerp(a, b), y0))
                if (b > lv) != (c_ > lv):
                    pts.append((x0 + step, y0 + step * lerp(b, c_)))
                if (d > lv) != (c_ > lv):
                    pts.append((x0 + step * lerp(d, c_), y0 + step))
                if (a > lv) != (d > lv):
                    pts.append((x0, y0 + step * lerp(a, d)))
                for k in range(0, len(pts) - 1, 2):
                    (x1, y1), (x2, y2) = pts[k], pts[k + 1]
                    segs.append(f"M{x1:.1f},{y1:.1f}L{x2:.1f},{y2:.1f}")
        out.append("".join(segs))
    return out


def relief_paths(ds: list[str]) -> str:
    return "\n".join(
        f'<path d="{d}" fill="none" stroke="{C["contour"]}" '
        f'stroke-width="{1.6 if n % 5 == 4 else 1.0}" stroke-linecap="round"/>'
        for n, d in enumerate(ds)
    )


def frame(w: int, h: int, fill: str, inner: str = "") -> str:
    return (
        f'<defs><clipPath id="clip"><rect width="{w}" height="{h}" rx="12"/></clipPath></defs>\n'
        f'<g clip-path="url(#clip)"><rect width="{w}" height="{h}" fill="{fill}"/>{inner}</g>\n'
        f'<rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="12" fill="none" stroke="{C["border"]}"/>'
    )


# ---------------------------------------------------------------- hero

def hero(p: dict) -> str:
    w, h = 1200, 340
    relief = relief_paths(isolines(w, h, [0.08 + 0.065 * i for i in range(15)]))
    rivers = [
        ("M1200,40 C1080,90 1010,170 960,210 S840,260 760,250 S640,280 560,340", 2.4),
        ("M1010,0 C1000,70 990,140 965,205", 1.4),
        ("M1200,180 C1120,190 1060,215 1000,212", 1.4),
        ("M850,340 C845,300 820,270 790,252", 1.2),
        ("M640,215 C680,235 700,262 690,292", 1.0),
    ]
    river_svg = "\n".join(
        f'<path d="{d}" fill="none" stroke="{C["accent"]}" stroke-width="{sw}" '
        f'stroke-linecap="round" opacity="0.85"/>'
        for d, sw in rivers
    )
    inner = f"""
<defs>
  <linearGradient id="fade" x1="0" x2="1" y1="0" y2="0">
    <stop offset="0.25" stop-color="#fff" stop-opacity="0"/>
    <stop offset="0.65" stop-color="#fff" stop-opacity="1"/>
  </linearGradient>
  <mask id="m"><rect width="{w}" height="{h}" fill="url(#fade)"/></mask>
</defs>
<g mask="url(#m)">{relief}{river_svg}</g>"""
    tags = "".join(mono(tag, 64 + i * 170, 292, 14, C["muted"], ls=1) for i, tag in enumerate(p["hero_tags"]))
    body = "\n".join([
        frame(w, h, C["bg"], inner),
        mono(p["kicker"], 64, 84, 13, C["accent"], weight=500, ls=3),
        text(p["name"], 62, 152, 58, C["text"], weight=800, ls=-0.5),
        text(p["role"], 64, 194, 24, C["text"], weight=600),
        text(p["focus"], 64, 226, 16, C["muted"]),
        f'<line x1="64" y1="258" x2="560" y2="258" stroke="{C["border"]}"/>',
        tags,
        text(p["hero_cta"], 1136, 292, 15, C["accent"], weight=700, anchor="end"),
    ])
    return svg_doc(w, h, f'{p["name"]} - {p["role"]}. {p["focus"]}', body)


# ---------------------------------------------------------------- philosophy

def philosophy_tile(step: dict, last: bool) -> str:
    """One step of TRUTH → TRUST → TOOL, its own image so it can carry its own link."""
    w, h = 400, 190
    cx = 185
    check_fits(step["note"], 12.5, 360)
    parts = [
        frame(w, h, C["bg"]),
        text(step["word"], cx, 76, 40, C["text"], weight=800, anchor="middle", ls=6),
        text(step["label"], cx, 106, 15, C["accent"], weight=500, anchor="middle"),
        text(step["note"], cx, 130, 12.5, C["faint"], anchor="middle"),
        text(step["cta"], cx, 166, 13, C["accent"], weight=700, anchor="middle"),
    ]
    if not last:
        a, b = 336, 384
        parts.append(
            f'<line x1="{a}" y1="62" x2="{b}" y2="62" stroke="{C["accent"]}" stroke-width="1.5"/>'
            f'<path d="M{b - 9},56 L{b},62 L{b - 9},68" fill="none" stroke="{C["accent"]}" '
            f'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>'
        )
    return svg_doc(w, h, f'{step["word"]} - {step["label"]}: {step["note"]}', "\n".join(parts))


# ---------------------------------------------------------------- cards

def corner_relief(seed: float) -> list[str]:
    """Small contour patch for the top-right corner of a card."""
    def field(x, y):
        dx, dy = (x - 560) / 120, (y - 20) / 90
        return math.exp(-(dx * dx + dy * dy)) + 0.04 * math.sin(x / 19 + seed) + 0.03 * math.sin(y / 13 - seed)
    return isolines(600, 230, [0.12 + 0.12 * i for i in range(7)], field, step=5)


def card(item: dict) -> str:
    w, h = 600, 230
    has_logo = bool(item.get("logo"))
    text_max = 380 if has_logo else 470
    for line in item["lines"]:
        check_fits(line, 16, text_max)
    check_fits(item["title"], 28, text_max, weight=700)

    if has_logo:
        png = base64.b64encode((ROOT / item["logo"]).read_bytes()).decode()
        motif = (f'<image x="428" y="18" width="150" height="150" '
                 f'href="data:image/png;base64,{png}"/>')
    else:
        motif = relief_paths(corner_relief(float(item["index"])))

    lines = [text(line, 36, 118 + i * 24, 16, C["muted"]) for i, line in enumerate(item["lines"])]
    body = "\n".join([
        frame(w, h, C["panel"], motif),
        mono(f'{item["index"]} / {item["kicker"]}', 36, 48, 12, C["accent"], weight=500, ls=2),
        text(item["title"], 36, 86, 28, C["text"], weight=700),
        *lines,
        mono(item["stack"], 36, 200, 12, C["faint"]),
        text(item["cta"], 564, 200, 14, C["accent"], weight=700, anchor="end"),
    ])
    return svg_doc(w, h, f'{item["index"]} / {item["title"]} - {" ".join(item["lines"])}', body)


# ---------------------------------------------------------------- main

def write(name: str, content: str) -> None:
    path = OUT / name
    path.write_text(content, encoding="utf-8", newline="\n")
    print(f"wrote {path.relative_to(ROOT)}  ({len(content.encode()) // 1024} KB)")


def main() -> None:
    profile = json.loads(DATA.read_text(encoding="utf-8"))
    OUT.mkdir(exist_ok=True)
    write("hero.svg", hero(profile))
    steps = profile["philosophy"]["steps"]
    for i, step in enumerate(steps):
        write(f"philosophy-{step['word'].lower()}.svg", philosophy_tile(step, i == len(steps) - 1))
    for item in profile["cards"]:
        write(f"card-{item['id']}.svg", card(item))


if __name__ == "__main__":
    main()
