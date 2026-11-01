# === CONTEXT ===
# Purpose:     2D frame geometry (DESIGN 3): cavity, wall and floor outlines, thumb notch,
#              and the split into bed-sized segments joined by dovetails.
# Decisions:   Everything is 2D here; export3d.py extrudes the floor outline to
#              frame.floor and the wall outline from the floor up by frame.height.
#              Cavity = region grown by clearance/2 with mitre joins: pieces shrink by
#              clearance/2 (fabricate.py), so the gap to the frame equals the gap between
#              pieces and the region's sharp corners stay sharp.
#              Splitting uses straight vertical/horizontal cut lines carrying dovetail
#              teeth. Band polygons are shrunk/grown by clearance/2 on each side of a cut
#              so mating segments get the same clearance as the pieces.
#              Tooth placement: for `ring` (no floor) one tooth centred on every place
#              where the cut crosses the wall, because the teeth are the only joint; for
#              `tray` teeth are spread along the floor crossing every TOOTH_PITCH mm.
#              Teeth closer than TOOTH_KEEPOUT to another cut line are dropped, so teeth
#              of crossing cuts never collide. The thumb notch sits in the middle of the
#              first segment's bottom side, away from cut lines.
# Constraints: Region must be convex (true until M4), so every cut crosses the cavity
#              once and the wall twice.
# Related:     fabricate.py (clearance split), export3d.py (extrusion), config.py:frame.*
# Tests:       tests/test_frame.py
# === END CONTEXT ===
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box
from shapely.ops import unary_union

from .config import Config

TOOTH_BASE = 5.0      # dovetail width at the cut line, mm
TOOTH_TOP = 7.0       # dovetail width at full depth, mm (wider: that is what locks)
TOOTH_DEPTH = 4.0     # mm
TOOTH_PITCH = 30.0    # mm between floor teeth (tray)
TOOTH_KEEPOUT = 10.0  # mm from other cut lines
NOTCH_RADIUS = 10.0   # thumb notch radius, mm
NOTCH_KEEP = 2.0      # wall material kept behind the notch, mm (at least min_feature)


@dataclass
class FrameSegment:
    floor: Polygon | None      # extruded 0..floor (tray only)
    wall: Polygon | MultiPolygon | None   # extruded floor..floor+height


@dataclass
class Frame:
    cavity: Polygon
    exterior: Polygon
    floor_h: float             # 0 for ring
    wall_h: float              # wall height above the floor
    segments: list[FrameSegment]
    cuts: dict


def make_frame(region: Polygon, cfg: Config) -> Frame | None:
    style = cfg["frame.style"]
    if style == "none":
        return None
    c = cfg["fabrication.clearance"]
    wall = cfg["frame.wall"]
    cavity = region.buffer(c / 2, join_style="mitre")
    if cfg["frame.exterior"] == "offset":
        exterior = cavity.buffer(wall, quad_segs=16)
    else:
        x0, y0, x1, y1 = cavity.bounds
        rr = min(wall, 5.0)   # outer corner radius
        exterior = box(x0 - wall, y0 - wall, x1 + wall, y1 + wall).buffer(
            -rr, join_style="mitre").buffer(rr, quad_segs=8)
    wall2d = exterior.difference(cavity)
    xs, ys = _cut_positions(exterior, cfg["frame.max_segment"])
    if cfg["frame.thumb_notch"]:
        wall2d = wall2d.difference(_notch(cavity, wall, cfg["fabrication.min_feature"], xs))
    floor2d = exterior if style == "tray" else None
    height = cfg["fabrication.thickness"] if cfg["frame.height"] == "auto" else cfg["frame.height"]
    floor_h = cfg["frame.floor"] if style == "tray" else 0.0

    solid = floor2d if floor2d is not None else wall2d
    xbands = _bands(solid, xs, ys, vertical=True, ring=floor2d is None, c=c)
    ybands = _bands(solid, ys, xs, vertical=False, ring=floor2d is None, c=c)
    segments = []
    for xb in xbands:
        for yb in ybands:
            cell = xb.intersection(yb)
            fl = floor2d.intersection(cell) if floor2d is not None else None
            wl = wall2d.intersection(cell)
            for part in _parts(fl if fl is not None else wl):
                f = part if fl is not None else None
                w = wl.intersection(part) if fl is not None else part
                segments.append(FrameSegment(f, w if not w.is_empty else None))
    return Frame(cavity, exterior, floor_h, height, segments, {"x": xs, "y": ys})


def _notch(cavity: Polygon, wall: float, min_feature: float, xcuts: list[float]) -> Polygon:
    """Half-disc into the wall on the cavity's bottom side, in the middle of the first
    frame segment (so it never coincides with a cut line)."""
    x0, y0, x1, _ = cavity.bounds
    xm = (x0 + (xcuts[0] if xcuts else x1)) / 2
    line = LineString([(xm, y0 - 1), (xm, (y0 + cavity.bounds[3]) / 2)])
    hit = line.intersection(cavity.exterior)
    p = min(getattr(hit, "geoms", [hit]), key=lambda g: g.y)
    keep = max(NOTCH_KEEP, min_feature)
    return Point(p.x, p.y).buffer(NOTCH_RADIUS, quad_segs=16).intersection(
        cavity.buffer(wall - keep))


def _cut_positions(exterior: Polygon, max_segment: float) -> tuple[list[float], list[float]]:
    x0, y0, x1, y1 = exterior.bounds

    def cuts(lo: float, hi: float) -> list[float]:
        n = math.ceil((hi - lo) / max_segment)
        return [lo + (hi - lo) * k / n for k in range(1, n)]
    return cuts(x0, x1), cuts(y0, y1)


def _bands(solid, cuts: list[float], other: list[float], vertical: bool, ring: bool,
           c: float) -> list[Polygon]:
    """Polygons between consecutive cut lines (with dovetails), clearance applied."""
    x0, y0, x1, y1 = solid.bounds
    big = box(x0 - 50, y0 - 50, x1 + 50, y1 + 50)
    if not cuts:
        return [big]
    lows = [_low_side(solid, pos, other, vertical, ring, big) for pos in cuts]
    bands = []
    for k in range(len(cuts) + 1):
        b = big
        if k < len(cuts):
            b = b.intersection(lows[k].buffer(-c / 2, join_style="mitre"))
        if k > 0:
            b = b.difference(lows[k - 1].buffer(c / 2, join_style="mitre"))
        bands.append(b)
    return bands


def _low_side(solid, pos: float, other: list[float], vertical: bool, ring: bool,
              big: Polygon) -> Polygon:
    """Half-plane below/left of the cut at `pos`, plus teeth protruding across it."""
    bx0, by0, bx1, by1 = big.bounds
    if vertical:
        half = box(bx0, by0, pos, by1)
        line = LineString([(pos, by0), (pos, by1)])
    else:
        half = box(bx0, by0, bx1, pos)
        line = LineString([(bx0, pos), (bx1, pos)])
    teeth = []
    for t in _tooth_centres(solid.intersection(line), vertical, ring):
        if any(abs(t - o) < TOOTH_KEEPOUT for o in other):
            continue
        tb, tt, d = TOOTH_BASE / 2, TOOTH_TOP / 2, TOOTH_DEPTH
        pts = [(0, -tb), (d, -tt), (d, tt), (0, tb)] if vertical else \
              [(-tb, 0), (-tt, d), (tt, d), (tb, 0)]
        off = (pos, t) if vertical else (t, pos)
        teeth.append(Polygon([(off[0] + u, off[1] + v) for u, v in pts]).buffer(0.01))
    return unary_union([half, *teeth])


def _tooth_centres(crossing, vertical: bool, ring: bool) -> list[float]:
    out = []
    for seg in getattr(crossing, "geoms", [crossing]):
        if seg.is_empty or seg.length < TOOTH_TOP + 2:
            continue
        coords = np.asarray(seg.coords)
        a, b = sorted(coords[:, 1] if vertical else coords[:, 0])[::len(coords) - 1]
        if ring:
            out.append((a + b) / 2)
        else:
            k = max(1, int((b - a) // TOOTH_PITCH))
            out.extend(a + (b - a) * (i + 0.5) / k for i in range(k))
    return out


def _parts(g) -> list[Polygon]:
    if g is None or g.is_empty:
        return []
    return [p for p in getattr(g, "geoms", [g]) if isinstance(p, Polygon) and p.area > 1e-6]
