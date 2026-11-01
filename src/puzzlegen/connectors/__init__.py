# === CONTEXT ===
# Purpose:     Assign connectors to interior edges and decorate the planar map
#              (DESIGN 5). M0: random tab parameters with a geometric feasibility check;
#              the uniqueness optimiser (DESIGN 7.4) replaces the random choice in M2.
# Decisions:   Feasibility is checked against the receiving face's *current* boundary
#              (other curves already decorated), so tabs placed earlier are respected
#              automatically and no separate tab-vs-tab collision test is needed.
#              On failure: shrink the head in steps, then try the other side, then leave
#              the edge straight and count it in the report (never fail the run).
#              The neck is widened to at least fabrication.min_neck + clearance, so the
#              neck still meets min_neck after the clearance offset (DESIGN 5.3, 8).
# Invariants:  The head of an edge's tab lies inside the receiving face with at least
#              connectors.min_wall to every other part of that face's boundary
#              (tests/test_connectors.py).
# Related:     planar_map.PlanarMap (curve_pts/curve_spec are rewritten here);
#              config.py:connectors.*, fabrication.min_neck, fabrication.clearance.
# Tests:       tests/test_connectors.py, tests/test_partition.py
# === END CONTEXT ===
from __future__ import annotations

from collections import Counter

import numpy as np
from shapely.geometry import Polygon

from ..config import Config
from ..planar_map import PlanarMap
from .tab import TabSpec, local_polyline, to_world

SHRINK = 0.85        # head radius factor per retry
MIN_HEAD_FRAC = 0.6  # retries stop below this fraction of the minimum head size


def assign(m: PlanarMap, cfg: Config, rng: np.random.Generator) -> Counter:
    """Decorate interior edges in place; returns counts for the report."""
    stats: Counter = Counter()
    if cfg["connectors.kinds"] == ["none"]:
        stats["none"] = sum(m.is_interior_curve(c) for c in range(len(m.curve_he)))
        return stats
    curves = [c for c in range(len(m.curve_he)) if m.is_interior_curve(c)]
    for c in rng.permutation(curves):
        stats[_place(m, int(c), cfg, rng)] += 1
    return stats


def _place(m: PlanarMap, c: int, cfg: Config, rng: np.random.Generator) -> str:
    h = m.curve_he[c]
    a, b = m.verts[m.origin[h]], m.verts[m.origin[m.twin[h]]]
    length = float(np.linalg.norm(b - a))
    if length < cfg["connectors.min_edge"]:
        return "skipped_short"

    hmin, hmax = cfg["connectors.head_size"]
    rmin, rmax = hmin / 2, hmax / 2
    nmin_ratio, nmax_ratio = cfg["connectors.neck_ratio"]
    min_half_neck = (cfg["fabrication.min_neck"] + cfg["fabrication.clearance"]) / 2
    margin = cfg["connectors.end_margin"]
    side0 = int(rng.choice([-1, 1]))
    r = rng.uniform(rmin, rmax)
    ratio = rng.uniform(nmin_ratio, nmax_ratio)
    skew = rng.uniform(-0.3, 0.3)

    for side in (side0, -side0):
        rr = r
        while rr >= rmin * MIN_HEAD_FRAC:
            neck = max(ratio * rr, min_half_neck)
            if neck < 0.9 * rr:
                half = rr * (1 + abs(skew)) + margin   # head extent from its centre
                if length > 2 * half:
                    t = rng.uniform(half / length, 1 - half / length)
                    spec = TabSpec(side, t, rr, neck, max(0.5, 0.3 * rr), skew)
                    pts = to_world(local_polyline(spec, length), a, b, side)
                    if _feasible(m, c, side, pts, cfg["connectors.min_wall"]):
                        m.curve_pts[c] = pts
                        m.curve_spec[c] = spec
                        return "tab"
            rr *= SHRINK
    return "skipped_infeasible"


def _feasible(m: PlanarMap, c: int, side: int, pts: np.ndarray, min_wall: float) -> bool:
    h = m.curve_he[c]
    recv = m.face[h] if side > 0 else m.face[m.twin[h]]
    head = Polygon(pts[1:-1])               # neck base to neck base, closed along the chord
    if not head.is_valid or head.area <= 0:
        return False
    if not m.face_polygon(recv).buffer(1e-9).contains(head):
        return False
    return head.distance(m.face_boundary_except(recv, c)) >= min_wall
