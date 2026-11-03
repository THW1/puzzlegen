# === CONTEXT ===
# Purpose:     The puzzle outline (DESIGN 3) as a Shapely polygon in mm, fitted into the
#              box [0, w] x [0, h] given by region.size.
# Decisions:   Shapes: rect, ellipse, regular polygon (optionally rounded), and the
#              largest closed outline of an SVG file (M4; may be non-convex, holes are
#              ignored), fitted into region.size keeping its aspect ratio. SVG parsing
#              uses svgelements (MIT), an optional dependency.
#              Corner rounding = inward then outward buffer, which rounds convex corners
#              only and keeps straight sides exact.
# Related:     config.py:region.*; tilings/* clip and sample against this polygon;
#              frame.py builds the cavity from it.
# === END CONTEXT ===
from __future__ import annotations

import math

import numpy as np
from shapely import affinity
from shapely.geometry import Point, Polygon, box
from shapely.geometry.polygon import orient

from .config import Config, ConfigError

CIRCLE_SEGMENTS = 128   # outline vertices of an ellipse; each becomes a boundary vertex


def make_region(cfg: Config) -> Polygon:
    w, h = cfg["region.size"]
    shape = cfg["region.shape"]
    if shape == "rect":
        poly = box(0.0, 0.0, w, h)
    elif shape == "circle":
        unit = Point(0, 0).buffer(1.0, quad_segs=CIRCLE_SEGMENTS // 4)
        poly = affinity.translate(affinity.scale(unit, w / 2, h / 2, origin=(0, 0)), w / 2, h / 2)
    elif shape == "polygon":
        poly = _fit(_regular(cfg["region.sides"]), w, h)
    elif shape == "svg":
        poly = _fit_keep_aspect(svg_outline(cfg["region.path"]), w, h)
    else:
        raise NotImplementedError(shape)
    r = cfg["region.corner_radius"]
    if r > 0 and shape != "circle":
        poly = poly.buffer(-r, join_style="mitre").buffer(r, quad_segs=8)
    return orient(Polygon(np.asarray(poly.exterior.coords)), 1.0)   # CCW, no holes


def _regular(n: int) -> Polygon:
    # One vertex at the top; for even n a flat bottom side reads better: rotate by half a step.
    start = math.pi / 2 + (math.pi / n if n % 2 == 0 else 0.0)
    return Polygon([(math.cos(start + 2 * math.pi * k / n),
                     math.sin(start + 2 * math.pi * k / n)) for k in range(n)])


def svg_outline(path: str, samples: int = 600) -> Polygon:
    """Largest closed outline in an SVG file as a polygon (y axis flipped to point
    up). Holes and further shapes are ignored (regions with holes are not supported)."""
    try:
        from svgelements import SVG, Path, Shape
    except ImportError:
        raise ConfigError('region.shape = "svg" needs the svgelements package '
                          '(pip install svgelements)') from None
    try:
        svg = SVG.parse(path)
    except (OSError, ValueError) as e:
        raise ConfigError(f"region.path: cannot read SVG {path!r}: {e}") from None
    best = None
    for el in svg.elements():
        if not isinstance(el, Shape):
            continue
        for sub in Path(el).as_subpaths():
            sub = Path(sub)
            if sub.length() <= 0:
                continue
            pts = np.asarray(sub.npoint(np.linspace(0, 1, samples)), float) * [1.0, -1.0]
            poly = Polygon(pts).buffer(0)
            if poly.is_empty:
                continue
            if poly.geom_type == "MultiPolygon":
                poly = max(poly.geoms, key=lambda g: g.area)
            if best is None or poly.area > best.area:
                best = poly
    if best is None:
        raise ConfigError(f"region.path: no closed outline found in {path!r}")
    return Polygon(best.exterior.coords).simplify(1e-3 * math.sqrt(best.area))


def _fit_keep_aspect(poly: Polygon, w: float, h: float) -> Polygon:
    x0, y0, x1, y1 = poly.bounds
    k = min(w / (x1 - x0), h / (y1 - y0))
    p = affinity.scale(poly, k, k, origin=(x0, y0))
    return affinity.translate(p, -x0, -y0)


def _fit(poly: Polygon, w: float, h: float) -> Polygon:
    x0, y0, x1, y1 = poly.bounds
    p = affinity.scale(poly, w / (x1 - x0), h / (y1 - y0), origin=(x0, y0))
    return affinity.translate(p, -x0, -y0)
