# === CONTEXT ===
# Purpose:     Assign connectors (tabs, swirls) to interior joints and decorate the planar
#              map (DESIGN 5), choosing shapes that keep connectors distinguishable
#              (DESIGN 7.4).
# Decisions:   Feasibility is checked against the faces' *current* boundaries (curves
#              decorated earlier), so earlier connectors are respected automatically.
#              Greedy distinctness instead of a quantised alphabet: for each joint K
#              random candidates are drawn, ordered by their distance to the most similar
#              connector already placed (uniqueness.side_profiles, capped at tau), and
#              the first feasible one is taken. Joints are processed shortest first,
#              because short joints have the fewest feasible shapes.
#              Tab parameter space is wide on purpose (tilt up to +-25°, neck height
#              0.3-0.9 r): with the M1 ranges only about 10 tab shapes were
#              distinguishable at tau = 0.75 mm, with these about 60 (random packing,
#              head 5-8 mm). Wider connectors.head_size ranges add more.
#              If no candidate fits, the head (or swirl window) shrinks by SHRINK per
#              round; after that the joint stays straight and is counted.
#              Necks are widened to fabrication.min_neck + clearance, so they still meet
#              min_neck after the clearance offset (DESIGN 5.3, 8). Swirls are checked on
#              both changed faces by erosion (a thin neck splits the piece) AND by opening
#              (a lobe with a thin throat vanishes instead of splitting; found in M2 when
#              corner rounding cut such lobes off).
# Invariants:  A tab head lies inside the receiving face with >= min_wall to every other
#              part of that face's boundary; a swirl keeps min_wall to both faces' other
#              boundaries (tests/test_connectors.py).
# Related:     connectors/tab.py, connectors/swirl.py, uniqueness.py (profiles, verify),
#              pipeline.run (repair loop calls `redo`), config.py:connectors.*.
# Tests:       tests/test_connectors.py, tests/test_partition.py
# === END CONTEXT ===
from __future__ import annotations

import math
from collections import Counter
from dataclasses import replace

import numpy as np
from shapely.geometry import LineString, MultiPolygon, Polygon

from ..config import Config
from ..planar_map import PlanarMap
from ..uniqueness import Alphabet, side_profiles
from . import swirl as sw
from .tab import MAX_TILT, TabSpec, keyhole, local_polyline, to_world

SHRINK = 0.85        # head radius / swirl window factor per retry round
ROUNDS = 4           # shrink rounds before giving up
CANDIDATES = 8       # candidates per round when uniqueness is enabled
LOCKING = ("tab", "swirl")
SWIRL_THETA = (math.radians(90), math.radians(125))   # per third; sum checked
LOBE_EPS = 1.0       # mm^2 of material an opening may remove along a swirl


def assign(m: PlanarMap, cfg: Config, rng: np.random.Generator) -> tuple[Counter, Alphabet]:
    """Decorate interior joints in place; returns counts and the alphabet of profiles."""
    stats: Counter = Counter()
    tau = cfg["uniqueness.tolerance_k"] * cfg["fabrication.clearance"]
    alpha = Alphabet(tau, cfg["uniqueness.flippable"])
    curves = [c for c in range(len(m.curve_he)) if m.is_interior_curve(c)]
    kinds = [k for k in cfg["connectors.kinds"] if k in LOCKING]
    if not kinds:
        stats["none"] = len(curves)
        return stats, alpha
    order = sorted(curves, key=lambda c: _length(m, c)) if cfg["uniqueness.enabled"] \
        else list(rng.permutation(curves))
    for c in order:
        stats[_place(m, int(c), cfg, rng, alpha, kinds)] += 1
    return stats, alpha


def redo(m: PlanarMap, c: int, cfg: Config, rng: np.random.Generator, alpha: Alphabet) -> str:
    """Remove the connector of curve c and place a new one (repair loop)."""
    alpha.remove(c)
    h = m.curve_he[c]
    m.curve_pts[c] = m.verts[[m.origin[h], m.origin[m.twin[h]]]].copy()
    m.curve_spec[c] = None
    kinds = [k for k in cfg["connectors.kinds"] if k in LOCKING]
    return _place(m, c, cfg, rng, alpha, kinds)


def _length(m: PlanarMap, c: int) -> float:
    h = m.curve_he[c]
    return float(np.linalg.norm(m.verts[m.origin[h]] - m.verts[m.origin[m.twin[h]]]))


def _place(m: PlanarMap, c: int, cfg: Config, rng: np.random.Generator, alpha: Alphabet,
           kinds: list[str]) -> str:
    h = m.curve_he[c]
    a, b = m.verts[m.origin[h]], m.verts[m.origin[m.twin[h]]]
    length = float(np.linalg.norm(b - a))
    if length < cfg["connectors.min_edge"]:
        return "skipped_short"
    k = CANDIDATES if cfg["uniqueness.enabled"] else 1
    scale = 1.0
    for _ in range(ROUNDS):
        cands = []
        for _ in range(k):
            kind = kinds[int(rng.integers(len(kinds)))]
            spec = _sample_tab(cfg, rng, length, scale) if kind == "tab" \
                else _sample_swirl(cfg, rng, length, scale)
            if spec is None:
                continue
            pts = to_world(_local(spec, length), a, b, spec.side)
            score = alpha.score(c, side_profiles(pts, spec, a, b)) if k > 1 else 0.0
            cands.append((-score, len(cands), spec, pts))
        for _, _, spec, pts in sorted(cands, key=lambda x: x[:2]):
            if _feasible(m, c, spec, pts, cfg):
                m.curve_pts[c] = pts
                m.curve_spec[c] = spec
                alpha.add(c, side_profiles(pts, spec, a, b))
                return spec.kind
        scale *= SHRINK
    return "skipped_infeasible"


def _local(spec, length: float) -> np.ndarray:
    return local_polyline(spec, length) if spec.kind == "tab" else sw.local_polyline(spec, length)


def _sample_tab(cfg: Config, rng: np.random.Generator, length: float, scale: float):
    hmin, hmax = cfg["connectors.head_size"]
    r = rng.uniform(hmin / 2, hmax / 2) * scale
    nlo, nhi = cfg["connectors.neck_ratio"]
    neck = max(rng.uniform(nlo, nhi) * r,
               (cfg["fabrication.min_neck"] + cfg["fabrication.clearance"]) / 2)
    if neck >= 0.9 * r:
        return None
    skew = rng.uniform(-1.0, 1.0)
    # Neck base points must stay below the head when tilted (tab.py invariant).
    neck_h = max(rng.uniform(0.3, 0.9) * r, neck * math.tan(abs(skew) * MAX_TILT) + 0.3, 0.5)
    spec = TabSpec(int(rng.choice([-1, 1])), 0.0, r, neck, neck_h, skew)
    kx = keyhole(spec)[:, 0]
    margin = cfg["connectors.end_margin"]
    lo, hi = margin - kx.min(), length - margin - kx.max()
    if lo >= hi:
        return None
    return replace(spec, t=rng.uniform(lo, hi) / length)


def _sample_swirl(cfg: Config, rng: np.random.Generator, length: float, scale: float):
    """Swirl candidate. `scale` is ignored: a smaller window only narrows the lobe
    throats (throat width grows with the window; >= 16-20 mm keeps 3.25 mm throats)."""
    margin = cfg["connectors.end_margin"]
    lo = max(sw.MIN_WINDOW, 0.6 * length)
    hi = min(length - 2 * margin, sw.MAX_WINDOW)
    if hi < lo:
        return None
    w = rng.uniform(lo, hi)
    half = w / 2
    t = rng.uniform(margin + half, length - margin - half) / length
    th1, th2, th3 = rng.uniform(*SWIRL_THETA, size=3)
    need = math.pi + math.radians(cfg["connectors.lock_margin"] + 5)  # 5° above the limit
    if max(th1, th3) + th2 < need:
        return None
    return sw.SwirlSpec(int(rng.choice([-1, 1])), t, w, th1, th2, th3)


def _feasible(m: PlanarMap, c: int, spec, pts: np.ndarray, cfg: Config) -> bool:
    min_wall = cfg["connectors.min_wall"]
    h = m.curve_he[c]
    if spec.kind == "tab":
        recv = m.face[h] if spec.side > 0 else m.face[m.twin[h]]
        head = Polygon(pts[1:-1])           # neck base to neck base, closed along the chord
        if not head.is_valid or head.area <= 0:
            return False
        if not m.face_polygon(recv).buffer(1e-9).contains(head):
            return False
        return head.distance(m.face_boundary_except(recv, c)) >= min_wall
    # swirl: curve stays clear of both faces' other boundaries, faces stay thick enough
    curve = LineString(pts[1:-1])
    if not curve.is_simple:
        return False
    # 3 % above the limit: the later fabrication check (offset + corner rounding +
    # erosion) must not land on the knife edge (seen in M2: throat exactly at min_neck).
    r = 1.03 * (cfg["fabrication.min_neck"] + cfg["fabrication.clearance"]) / 2
    win = pts[1:-1]
    k = max(1, len(win) // 10)
    middle = LineString(win[k:-k]).buffer(2 * r)   # window without its end kinks
    old_pts = m.curve_pts[c]
    m.curve_pts[c] = pts
    try:
        for f in (m.face[h], m.face[m.twin[h]]):
            if curve.distance(m.face_boundary_except(f, c)) < min_wall:
                return False
            poly = m.face_polygon(f)
            if not poly.is_valid:
                return False
            core = poly.buffer(-r)
            if core.is_empty or (isinstance(core, MultiPolygon) and len(core.geoms) > 1):
                return False          # a neck narrower than min_neck splits the piece
            # A lobe with a too-thin throat does not split the piece under erosion, it
            # vanishes; the opening (erode + dilate) shows it as lost material.
            lost = poly.difference(core.buffer(r)).intersection(middle)
            if any(g.area > LOBE_EPS for g in getattr(lost, "geoms", [lost])):
                return False
        return True
    finally:
        m.curve_pts[c] = old_pts
