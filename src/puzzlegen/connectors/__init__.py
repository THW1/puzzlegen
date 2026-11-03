# === CONTEXT ===
# Purpose:     Assign connectors (tabs, swirls) to interior joints and decorate the planar
#              map (DESIGN 5), choosing shapes that keep connectors distinguishable
#              (DESIGN 7.4).
# Decisions:   Feasibility is checked against the faces' *current* boundaries (curves
#              decorated earlier), so earlier connectors are respected automatically.
#              Greedy distinctness instead of a quantised alphabet: for each joint K
#              random candidates are drawn and ordered by distance to the most similar
#              connector already placed (capped at tau) - first among connectors whose
#              joints would also end at the same points (the joint-level criterion that
#              verify() fails on; added after grids with equal joint lengths kept
#              joint-level ambiguities), then among all. The first feasible one is
#              taken. Joints are processed shortest first,
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
#              part of that face's boundary, and the giving face stays robust (_robust);
#              a swirl keeps min_wall to both faces' other boundaries and both faces stay
#              robust (tests/test_connectors.py).
# Related:     connectors/tab.py, connectors/swirl.py, uniqueness.py (profiles, verify),
#              pipeline.run (repair loop calls `redo`), config.py:connectors.*.
# Tests:       tests/test_connectors.py, tests/test_partition.py
# === END CONTEXT ===
from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, replace

import numpy as np
from shapely.geometry import LineString, MultiPolygon, Polygon

from ..config import Config
from ..frame import exterior_of
from ..planar_map import OUTSIDE, PlanarMap
from ..interlock import is_locking
from ..uniqueness import Alphabet, side_profiles
from . import swirl as sw
from .tab import MAX_TILT, TabSpec, keyhole, local_polyline, to_world

SHRINK = 0.85        # head radius / swirl window factor per retry round
RESCUE_ROUNDS = 9    # shrink rounds for pieces without any lock (0.85^8 = 0.27 x size)
CANDIDATES = 8       # candidates per round when uniqueness is enabled
LOCKING = ("tab", "swirl")
SWIRL_THETA = (math.radians(90), math.radians(125))   # per third; sum checked
LOBE_EPS = 1.0       # mm^2 of material an opening may remove along a swirl
MAX_SOCKET_SHARE = 0.25   # a socket may take at most this share of the receiving piece


@dataclass(frozen=True)
class ShapeSpec:
    """A bent (chain) joint without connector: its whole outline is the profile used by
    the uniqueness check (DESIGN 6.2: shape-locked joints)."""
    kind = "shape"

    def profile_range(self, n_pts: int) -> tuple[int, int]:
        return 0, n_pts


def mark_shapes(m: PlanarMap) -> int:
    n = 0
    for c in range(len(m.curve_he)):
        if m.is_interior_curve(c) and m.curve_spec[c] is None and len(m.curve_pts[c]) > 2:
            m.curve_spec[c] = ShapeSpec()
            n += 1
    return n


def assign(m: PlanarMap, cfg: Config, rng: np.random.Generator, region=None,
           frame_connectors: bool = False) -> tuple[Counter, Alphabet]:
    """Decorate interior joints (and, with frame connectors, the joints between edge
    pieces and the frame) in place; returns counts and the alphabet of profiles."""
    stats: Counter = Counter()
    tau = cfg["uniqueness.tolerance_k"] * cfg["fabrication.clearance"]
    alpha = Alphabet(tau, cfg["uniqueness.flippable"])
    curves = [c for c in range(len(m.curve_he)) if m.is_interior_curve(c)]
    m.frame_exterior = None
    if frame_connectors:
        # Joints between edge pieces and the frame (DESIGN 3): the frame acts as a fixed
        # piece; heads into the frame must stay inside its wall.
        m.frame_exterior = exterior_of(region.buffer(cfg["fabrication.clearance"] / 2,
                                                     join_style="mitre"), cfg)
        curves += [c for c in range(len(m.curve_he)) if not m.is_interior_curve(c)]
    kinds = [k for k in cfg["connectors.kinds"] if k in LOCKING]
    if not kinds:
        stats["none"] = len(curves)
        return stats, alpha
    order = sorted(curves, key=lambda c: _length(m, c)) if cfg["uniqueness.enabled"] \
        else list(rng.permutation(curves))
    for c in order:
        stats[_place(m, int(c), cfg, rng, alpha, kinds)] += 1
    stats["rescued"] = _rescue_loose(m, cfg, rng, alpha, kinds)
    return stats, alpha


def _rescue_loose(m: PlanarMap, cfg: Config, rng: np.random.Generator, alpha: Alphabet,
                  kinds: list[str]) -> int:
    """Pieces left without any locking joint get more attempts with smaller heads
    (down to the size min_neck allows) on their undecorated joints. Added in M3 for
    small corner pieces of Penrose puzzles with a single interior joint."""
    from ..interlock import joint_report
    rescued = 0
    for f in joint_report(m, cfg["connectors.lock_margin"])["loose_pieces"]:
        for hh in m.face_halfedges(f):
            c = m.curve[hh]
            if not m.is_interior_curve(c) or m.curve_spec[c] is not None:
                continue
            if _place(m, c, cfg, rng, alpha, kinds, rounds=RESCUE_ROUNDS) in LOCKING:
                rescued += 1
                break
    return rescued


def redo(m: PlanarMap, c: int, cfg: Config, rng: np.random.Generator, alpha: Alphabet) -> str:
    """Replace the connector of curve c by a new one (repair loop). If no new one fits,
    the old connector is restored: losing a lock is worse than an ambiguity (seen in
    M3 on Penrose rhombi, where re-draws often found no feasible shape)."""
    old_pts, old_spec, old_alpha = m.curve_pts[c], m.curve_spec[c], alpha.items.get(c)
    alpha.remove(c)
    m.curve_pts[c] = strip(old_pts, old_spec)
    m.curve_spec[c] = None
    kinds = [k for k in cfg["connectors.kinds"] if k in LOCKING]
    kind = _place(m, c, cfg, rng, alpha, kinds)
    if kind == "skipped_infeasible" and old_spec is not None:
        m.curve_pts[c], m.curve_spec[c] = old_pts, old_spec
        alpha.items[c] = old_alpha
        alpha._cache = None
        return "kept_old"
    return kind


def _length(m: PlanarMap, c: int) -> float:
    h = m.curve_he[c]
    return float(np.linalg.norm(m.verts[m.origin[h]] - m.verts[m.origin[m.twin[h]]]))


def strip(pts: np.ndarray, spec) -> np.ndarray:
    """The undecorated joint polyline: curve points without the connector."""
    i0, i1 = spec.profile_range(len(pts))
    return np.vstack([pts[:i0], pts[i1:]])


def _place(m: PlanarMap, c: int, cfg: Config, rng: np.random.Generator, alpha: Alphabet,
           kinds: list[str], rounds: int = 4, force_chord: bool = False) -> str:
    base = m.curve_pts[c]
    margin = cfg["connectors.lock_margin"]
    if cfg["connectors.placement"] == "unlocked" and is_locking(base, margin):
        return "shape_locked"
    if len(base) == 2:
        return _try(m, c, base, 0, kinds, cfg, rng, alpha, rounds) or "skipped_infeasible" \
            if np.linalg.norm(base[1] - base[0]) >= cfg["connectors.min_edge"] else "skipped_short"
    # Chain joint (bent). 1) a tab on one of its straight segments, longest first (M3:
    # trying only the longest missed feasible neighbours 0.1 mm shorter);
    seglen = np.linalg.norm(np.diff(base, axis=0), axis=1)
    if "tab" in kinds:
        for seg in np.argsort(-seglen):
            if seglen[seg] < cfg["connectors.min_edge"]:
                break
            kind = _try(m, c, base, int(seg), ["tab"], cfg, rng, alpha, rounds)
            if kind:
                return kind
    # 2) if the chain does not lock by itself, replace it by its straight chord and put
    # any connector there (M3: chains between small grouped cells have ~6 mm segments,
    # too short for tabs; a chain that does not lock loses nothing by straightening).
    if is_locking(base, margin) and not force_chord:
        return "skipped_chain"
    return _on_chord(m, c, base, kinds, cfg, rng, alpha, rounds)


def convert_shape(m: PlanarMap, c: int, cfg: Config, rng: np.random.Generator,
                  alpha: Alphabet) -> str:
    """Replace an ambiguous shape joint (chain without connector) by chord + connector
    (repair loop, M3: Penrose supertile outlines repeat, so shape joints collide)."""
    base, spec = m.curve_pts[c], m.curve_spec[c]
    m.curve_spec[c] = None
    kinds = [k for k in cfg["connectors.kinds"] if k in LOCKING] or ["tab"]
    kind = _on_chord(m, c, base, kinds, cfg, rng, alpha, 4)
    if kind == "skipped_infeasible":
        m.curve_spec[c] = spec
    return kind


def _on_chord(m, c, base, kinds, cfg, rng, alpha, rounds) -> str:
    chord = base[[0, -1]].copy()
    if np.linalg.norm(chord[1] - chord[0]) < cfg["connectors.min_edge"]:
        return "skipped_chain"
    h = m.curve_he[c]
    r = 0.99 * (cfg["fabrication.min_neck"] + cfg["fabrication.clearance"]) / 2
    # Middle of the chord only: its ends always form acute corners with the zigzag's
    # neighbours, which an opening trims a little (that is not a neck problem).
    zone = LineString([chord[0] + 0.2 * (chord[1] - chord[0]),
                       chord[0] + 0.8 * (chord[1] - chord[0])]).buffer(2 * r)
    if all(_robust(m, c, chord, f, zone, cfg, r)
           for f in (m.face[h], m.face[m.twin[h]]) if f != OUTSIDE):
        m.curve_pts[c] = chord
        kind = _try(m, c, chord, 0, kinds, cfg, rng, alpha, rounds)
        if kind:
            return kind
    m.curve_pts[c] = base
    return "skipped_infeasible"


def _try(m: PlanarMap, c: int, base: np.ndarray, seg: int, kinds: list[str], cfg: Config,
         rng: np.random.Generator, alpha: Alphabet, rounds: int) -> str | None:
    """Place a connector on segment `seg` of the polyline `base`; None if nothing fits."""
    h = m.curve_he[c]
    va, vb = m.verts[m.origin[h]], m.verts[m.origin[m.twin[h]]]
    a, b = base[seg], base[seg + 1]
    length = float(np.linalg.norm(b - a))
    if len(base) > 2:
        kinds = [k for k in kinds if k == "tab"]   # swirls need the whole joint straight
    if not kinds:
        return None
    k = CANDIDATES if cfg["uniqueness.enabled"] else 1
    scale = 1.0
    for _ in range(rounds):
        cands = []
        for _ in range(k):
            kind = kinds[int(rng.integers(len(kinds)))]
            spec = _sample_tab(cfg, rng, length, scale) if kind == "tab" \
                else _sample_swirl(cfg, rng, length, scale)
            if spec is None:
                continue
            if spec.kind == "tab":
                spec = replace(spec, offset=seg)
            world = to_world(_local(spec, length), a, b, spec.side)
            pts = np.vstack([base[:seg + 1], world[1:-1], base[seg + 1:]])
            sj, ss = alpha.score(c, side_profiles(pts, spec, va, vb)) if k > 1 else (0.0, 0.0)
            cands.append((-sj, -ss, len(cands), spec, pts))
        for *_, spec, pts in sorted(cands, key=lambda x: x[:3]):
            if _feasible(m, c, spec, pts, cfg):
                m.curve_pts[c] = pts
                m.curve_spec[c] = spec
                alpha.add(c, side_profiles(pts, spec, va, vb))
                return spec.kind
        scale *= SHRINK
    return None


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
        i0, i1 = spec.profile_range(len(pts))
        head = Polygon(pts[i0:i1])          # neck base to neck base, closed along the chord
        if not head.is_valid or head.area <= 0:
            return False
        giver = m.face[m.twin[h]] if spec.side > 0 else m.face[h]
        if recv == OUTSIDE:
            return _fits_frame(m, c, head, giver, min_wall)
        recv_poly = m.face_polygon(recv)
        if not recv_poly.buffer(1e-9).contains(head):
            return False
        if head.distance(m.face_boundary_except(recv, c)) < min_wall:
            return False
        # Other segments of a chain joint: min_wall, like any other edge of the piece.
        # (M3 relaxed this to end_margin; M4 showed that leaves walls of 3 mm, i.e.
        # 2.75 mm after the clearance offset, below min_neck - pieces split.)
        # The full neighbouring polylines, shared vertex included - exactly the rule a
        # straight joint already obeys against its adjacent joints. (Until M4 the
        # shared vertex was dropped and 2-point rests skipped, so the neighbouring
        # segment of a 2-segment chain was never checked.)
        for rest in (pts[:i0], pts[i1:]):
            if len(rest) >= 2 and head.distance(LineString(rest)) < min_wall:
                return False
        # Sockets must not hollow out small pieces (M3: clipped Penrose cells shrank to a
        # fifth of their area under neighbours' sockets and could not carry own tabs).
        if head.area > MAX_SOCKET_SHARE * recv_poly.area:
            return False
        r = 0.99 * (cfg["fabrication.min_neck"] + cfg["fabrication.clearance"]) / 2
        # The giving piece must carry the head: no thin body behind the neck (found in
        # M3: a head on a 2 mm corner wedge of a clipped Penrose cell).
        # Radius 0.99 x the limit (as in fabricate.py), so the tab's own neck - exactly
        # min_neck + clearance wide - survives; the zone excludes the head itself.
        if giver == OUTSIDE:
            return True                      # the frame wall carries the head
        zone = LineString(pts[[i0, i1 - 1]]).buffer(2 * r + head.length / 8).difference(head)
        return _robust(m, c, pts, giver, zone, cfg, r)

    # swirl: curve stays clear of both faces' other boundaries, faces stay thick enough
    curve = LineString(pts[1:-1])
    if not curve.is_simple:
        return False
    win = pts[1:-1]
    k = max(1, len(win) // 10)
    middle = LineString(win[k:-k]).buffer(2 * _neck_radius(cfg))   # without end kinks
    for f in (m.face[h], m.face[m.twin[h]]):
        old_pts = m.curve_pts[c]
        m.curve_pts[c] = pts
        try:
            if curve.distance(m.face_boundary_except(f, c)) < min_wall:
                return False
        finally:
            m.curve_pts[c] = old_pts
        if not _robust(m, c, pts, f, middle, cfg):
            return False
    return True


def _fits_frame(m: PlanarMap, c: int, head: Polygon, giver: int, min_wall: float) -> bool:
    """A head reaching into the frame: inside the frame wall with min_wall to its outer
    edge, and min_wall away from every other piece (including heads they already push
    into the frame) and from the giving piece's other edges."""
    ext = getattr(m, "frame_exterior", None)
    if ext is None or not ext.buffer(-min_wall).contains(head):
        return False
    if head.distance(m.face_boundary_except(giver, c)) < min_wall:
        return False
    zone = head.buffer(min_wall)
    for f in m.inner_faces():
        if f != giver and m.face_polygon(f).intersects(zone):
            return False
    return True


def _neck_radius(cfg: Config) -> float:
    # 3 % above the limit: the later fabrication check (offset + corner rounding +
    # erosion) must not land on the knife edge (seen in M2: throat exactly at min_neck).
    return 1.03 * (cfg["fabrication.min_neck"] + cfg["fabrication.clearance"]) / 2


def _robust(m: PlanarMap, c: int, pts: np.ndarray, f: int, zone, cfg: Config,
            r: float | None = None) -> bool:
    """With curve c set to pts, face f has no neck below min_neck (erosion does not
    split it) and loses no material inside `zone` under an opening (a part attached by
    a thin throat vanishes under erosion instead of splitting)."""
    r = _neck_radius(cfg) if r is None else r
    old_pts = m.curve_pts[c]
    m.curve_pts[c] = pts
    try:
        poly = m.face_polygon(f)
    finally:
        m.curve_pts[c] = old_pts
    if not poly.is_valid:
        return False
    core = poly.buffer(-r)
    if core.is_empty or (isinstance(core, MultiPolygon) and len(core.geoms) > 1):
        return False
    lost = poly.difference(core.buffer(r)).intersection(zone)
    return not any(g.area > LOBE_EPS for g in getattr(lost, "geoms", [lost]))
