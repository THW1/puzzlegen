# === CONTEXT ===
# Purpose:     SVG preview of the assembled puzzle (DESIGN 9.1, USAGE 4: <name>_preview.svg):
#              exact piece outlines on top of the frame segments (grey).
# Decisions:   Hand-written SVG strings, no svgwrite dependency: the output is a handful
#              of <path>/<text> elements. Coordinates are written with 3 decimals and the
#              y axis flipped (SVG y points down), so files are stable across runs (G6).
#              Colours: golden-angle hue steps, so neighbouring IDs get distinct hues.
# Related:     pipeline.Result; cli.py decides the file name.
# === END CONTEXT ===
from __future__ import annotations

from shapely.geometry import Polygon

from .pipeline import Result

PAD = 5.0  # mm around the region


def _ring(coords, height: float) -> str:
    d = " L".join(f"{x:.3f},{height - y:.3f}" for x, y in coords[:-1])
    return f"M{d} Z"


def _path(poly: Polygon, height: float) -> str:
    return " ".join([_ring(poly.exterior.coords, height)]
                    + [_ring(r.coords, height) for r in poly.interiors])


def _polys(g) -> list[Polygon]:
    return [] if g is None else list(getattr(g, "geoms", [g]))


def preview_svg(res: Result) -> str:
    x0, y0, x1, y1 = (res.frame.exterior if res.frame else res.region).bounds
    w, h = x1 - x0 + 2 * PAD, y1 - y0 + 2 * PAD
    top = y1 + PAD
    font = max(2.0, min(8.0, (res.region.area / max(1, len(res.pieces))) ** 0.5 / 5))
    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.3f}mm" height="{h:.3f}mm" '
        f'viewBox="{x0 - PAD:.3f} 0 {w:.3f} {h:.3f}">',
        f'<rect x="{x0 - PAD:.3f}" y="0" width="{w:.3f}" height="{h:.3f}" fill="white"/>',
    ]
    if res.frame is not None:
        out.append('<g id="frame" fill="#bbb" stroke="#555" stroke-width="0.3">')
        for k, seg in enumerate(res.frame.segments):
            for g in _polys(seg.floor if seg.floor is not None else seg.wall):
                out.append(f'<path id="f{k + 1}" d="{_path(g, top)}" fill-rule="evenodd"/>')
        out.append('</g>')
    out.append('<g id="pieces" stroke="#222" stroke-width="0.3" stroke-linejoin="round">')
    for i, p in enumerate(res.pieces):
        hue = (i * 137.508) % 360
        out.append(f'<path id="p{i + 1}" d="{_path(p, top)}" '
                   f'fill="hsl({hue:.1f},55%,78%)"/>')
    out.append('</g>')
    out.append(f'<g id="ids" font-family="sans-serif" font-size="{font:.2f}" '
               f'text-anchor="middle" dominant-baseline="central" fill="#222">')
    for i, p in enumerate(res.pieces):
        c = p.representative_point()   # inside the piece even if it is non-convex
        out.append(f'<text x="{c.x:.3f}" y="{top - c.y:.3f}">{i + 1}</text>')
    out.append('</g>')
    out.append('</svg>')
    return "\n".join(out) + "\n"
