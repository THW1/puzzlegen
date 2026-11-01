# === CONTEXT ===
# Purpose:     The puzzle outline (DESIGN 3) as a Shapely polygon in mm, fitted into the
#              box [0, w] x [0, h] given by region.size.
# Decisions:   Only convex shapes so far (rect, ellipse, regular polygon, optionally with
#              rounded corners): Voronoi clipping and the frame then never produce
#              MultiPolygons. SVG outlines (possibly non-convex) arrive with M4.
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

from .config import Config

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


def _fit(poly: Polygon, w: float, h: float) -> Polygon:
    x0, y0, x1, y1 = poly.bounds
    p = affinity.scale(poly, w / (x1 - x0), h / (y1 - y0), origin=(x0, y0))
    return affinity.translate(p, -x0, -y0)
