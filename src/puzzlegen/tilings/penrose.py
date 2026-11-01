# === CONTEXT ===
# Purpose:     Penrose P3 (rhombus) tiling by Robinson-triangle subdivision (DESIGN 4.2),
#              with the ancestry each cell needs for hierarchical grouping.
# Decisions:   Subdivision rules as in Preshing's "Penrose Tiling Explained": red
#              (acute, 36° apex) A,B,C -> P = A + (B-A)/phi, children (red C,P,B),
#              (blue P,C,A); blue (obtuse) -> Q = B + (A-B)/phi, R = B + (C-B)/phi,
#              children (blue R,C,A), (blue Q,R,B), (red R,Q,A). Start: a "sun" of 10
#              red triangles. Two triangles sharing edge BC form a rhombus.
#              Verified geometrically, not taken on trust (tests/test_penrose.py): total
#              area is conserved, every BC pair is a thick (72/108°) or thin (36/144°)
#              rhombus with equal sides, and the thick:thin ratio approaches phi.
#              P2 (kite/dart) is deferred: a derived rule set produced kites and darts
#              locally but left pairing defects inside the patch, so it was not shipped.
#              Granularity: the level is the first one whose rhombi inside the region
#              reach the target count; then the whole patch is scaled UP by
#              sqrt(count/target), which keeps it covering the region and brings the
#              count to about the target (levels alone jump by phi^2 = 2.6x).
#              The sun's centre is shifted and rotated randomly (seeded), because the
#              sun is 5-fold symmetric and identical seeds would repeat whole patches.
#              Hierarchy: for grouping.strategy = "hierarchy" the target count applies to
#              the piece level, cells are `depth` levels finer, and each cell is tagged
#              with the id of its piece-level rhombus.
# Invariants:  Cells are rhombi (or unpaired triangles at the patch border, which lies
#              outside the region) clipped to the region; face_tag = piece-level rhombus
#              id for hierarchy, else None.
# Constraints: Region must be convex (clip gives single polygons), true until M4.
# Related:     grouping.py (hierarchy uses face_tag), config.py:tiling.penrose.*,
#              grouping.level (depth).
# Tests:       tests/test_penrose.py
# === END CONTEXT ===
from __future__ import annotations

import cmath
import math

import numpy as np
from shapely.geometry import Polygon

from ..config import Config
from ..planar_map import PlanarMap

PHI = (1 + 5 ** 0.5) / 2
HIER_DEPTH = 2          # default levels between a piece and its cells (about 7 rhombi);
                        # depth 3 gave outlines too fine for tabs and many loose pieces
MAX_LEVEL = 14


def sun(center: complex, radius: float, angle: float) -> list[tuple]:
    out = []
    for i in range(10):
        b = center + cmath.rect(radius, (2 * i - 1) * math.pi / 10 + angle)
        c = center + cmath.rect(radius, (2 * i + 1) * math.pi / 10 + angle)
        if i % 2 == 0:
            b, c = c, b
        out.append((0, center, b, c))
    return out


def subdivide(tris: list[tuple]) -> tuple[list[tuple], list[int]]:
    """One deflation step; returns children and the parent index of each child."""
    out, parent = [], []
    for k, (col, a, b, c) in enumerate(tris):
        if col == 0:
            p = a + (b - a) / PHI
            kids = [(0, c, p, b), (1, p, c, a)]
        else:
            q = b + (a - b) / PHI
            r = b + (c - b) / PHI
            kids = [(1, r, c, a), (1, q, r, b), (0, r, q, a)]
        out.extend(kids)
        parent.extend([k] * len(kids))
    return out, parent


def _key(z: complex) -> tuple[float, float]:
    return (round(z.real, 6), round(z.imag, 6))


def pair_rhombi(tris: list[tuple]) -> list[list[int]]:
    """Group triangle indices into rhombi (pairs sharing edge BC); singles stay alone."""
    groups: dict = {}
    for i, (col, a, b, c) in enumerate(tris):
        groups.setdefault((col, frozenset((_key(b), _key(c)))), []).append(i)
    return list(groups.values())


def rhombus_polygon(tris: list[tuple], idx: list[int]) -> np.ndarray:
    if len(idx) == 2:
        (_, a, b, c), (_, a2, _, _) = tris[idx[0]], tris[idx[1]]
        ring = [a, b, a2, c]
    else:
        _, a, b, c = tris[idx[0]]
        ring = [a, b, c]
    return np.array([[z.real, z.imag] for z in ring])


def _count_inside(region: Polygon, tris: list[tuple]) -> int:
    n = 0
    for idx in pair_rhombi(tris):
        if region.contains(Polygon(rhombus_polygon(tris, idx)).centroid):
            n += 1
    return n


def generate(region: Polygon, n: int, rng: np.random.Generator, cfg: Config) -> PlanarMap:
    hierarchical = cfg["grouping.strategy"] == "hierarchy"
    depth = 0
    if hierarchical:
        depth = HIER_DEPTH if cfg["grouping.level"] == "auto" else cfg["grouping.level"]
    cx, cy = region.centroid.coords[0]
    r_cover = max(math.hypot(x - cx, y - cy) for x, y in region.exterior.coords)
    shift = cmath.rect(rng.uniform(0, 0.3 * r_cover), rng.uniform(0, 2 * math.pi))
    center = complex(cx, cy) + shift
    angle = rng.uniform(0, 2 * math.pi)
    # The sun is a decagon: its inscribed radius is cos(18°) = 0.951 of its corner
    # radius, so that factor must be divided out (M3: a 5 % margin alone left a
    # 0.27 mm^2 gap at the region edge for one seed).
    r0 = (r_cover + abs(shift)) / math.cos(math.pi / 10) * 1.02

    # Piece level: first level whose rhombi inside the region reach the target.
    fixed = cfg["tiling.penrose.levels"]
    tris = sun(center, r0, angle)
    level, count = 0, _count_inside(region, tris)
    while (fixed == "auto" and count < n and level < MAX_LEVEL) or \
            (fixed != "auto" and level < fixed - depth):
        tris, _ = subdivide(tris)
        level += 1
        count = _count_inside(region, tris)
    scale = math.sqrt(count / n) if (fixed == "auto" and count > n) else 1.0

    # Final patch: scaled up about its centre (keeps covering), depth levels finer.
    tris = sun(center, r0 * scale, angle)
    for _ in range(level):
        tris, _ = subdivide(tris)
    piece_rhombus = {}
    for rid, idx in enumerate(pair_rhombi(tris)):
        for i in idx:
            piece_rhombus[i] = rid
    owner = list(range(len(tris)))                 # fine triangle -> piece-level triangle
    for _ in range(depth):
        tris, parent = subdivide(tris)
        owner = [owner[p] for p in parent]

    polys, tags = [], []
    for idx in pair_rhombi(tris):
        cell = Polygon(rhombus_polygon(tris, idx)).intersection(region)
        if cell.is_empty or cell.area < 1e-6:
            continue
        for g in getattr(cell, "geoms", [cell]):
            if isinstance(g, Polygon) and g.area > 1e-6:
                polys.append(np.asarray(g.exterior.coords)[:-1])
                tags.append(piece_rhombus[owner[idx[0]]] if hierarchical else None)
    return PlanarMap.from_polygons(polys, tags=tags)
