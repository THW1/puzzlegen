# === CONTEXT ===
# Purpose:     Edge cleanup (DESIGN 6.3) between tiling and connectors: merge slivers,
#              straighten degree-2 vertices inside joints, and contract joints too short
#              to carry a connector. Rule U1 (every joint locks) depends on it.
# Decisions:   Works on (vertex positions, vertex-index rings) and rebuilds the
#              PlanarMap afterwards (PlanarMap.from_rings). Rejected: in-place half-edge
#              surgery - merging faces and contracting edges in a DCEL is error-prone,
#              and cleanup runs once, before any edge is decorated.
#              Rejected: Shapely unions for merging - they may drop vertices that a third
#              face still uses, which creates T-junctions. Ring merging keeps every
#              shared vertex.
#              A short joint is removed by contracting its edge to one point. The two
#              pieces then touch only at a vertex (where four pieces meet), which is how
#              classic jigsaw grids look. Rejected for now: moving vertices to lengthen
#              the joint (needs an optimiser).
#              Contraction threshold: connectors.min_edge if a connector kind is in use,
#              else cleanup.collapse_edge (shape-locked modes need no connector room).
#              Every operation is checked (rings stay simple, CCW, no pinch); an
#              operation that would break a face is skipped and the case is counted.
# Invariants:  Operations move or remove vertices in ALL rings that use them, so the
#              rings keep partitioning the region (tests/test_cleanup.py).
#              Boundary vertices never move off the region outline: a contraction with
#              one boundary end keeps that end's position; with two boundary ends it is
#              skipped.
# Related:     pipeline.run calls cleanup() after the tiling; config.py:cleanup.*,
#              connectors.min_edge.
# Tests:       tests/test_cleanup.py
# === END CONTEXT ===
from __future__ import annotations

from collections import Counter, defaultdict

import numpy as np
from shapely.geometry import Polygon

from .config import Config
from .planar_map import PlanarMap

LOCKING_KINDS = {"tab", "dovetail", "tee", "double", "swirl"}


class _Rings:
    def __init__(self, verts: np.ndarray, rings: list[list[int]]):
        self.verts = np.array(verts, float)
        self.rings = [list(r) for r in rings]

    def edge_owner(self) -> dict[tuple[int, int], int]:
        out = {}
        for i, r in enumerate(self.rings):
            for k, u in enumerate(r):
                out[(u, r[(k + 1) % len(r)])] = i
        return out

    def poly(self, ring: list[int]) -> Polygon:
        return Polygon(self.verts[ring])

    def ok(self, ring: list[int]) -> bool:
        if len(ring) < 3 or len(set(ring)) != len(ring):
            return False
        p = self.poly(ring)
        return p.is_valid and p.exterior.is_ccw and p.area > 1e-9

    def boundary_vertices(self, owner) -> set[int]:
        return {u for (u, v) in owner if (v, u) not in owner}


def cleanup(m: PlanarMap, cfg: Config) -> tuple[PlanarMap, dict]:
    R = _Rings(m.verts, m.rings())
    stats: Counter = Counter()
    min_feat = cfg["fabrication.min_feature"] + cfg["fabrication.clearance"]
    _merge_slivers(R, cfg["cleanup.min_area_ratio"], min_feat, stats)
    _straighten(R, stats)
    uses_connectors = bool(set(cfg["connectors.kinds"]) & LOCKING_KINDS)
    threshold = cfg["connectors.min_edge"] if uses_connectors else cfg["cleanup.collapse_edge"]
    _contract_short(R, threshold, stats)
    _merge_slivers(R, cfg["cleanup.min_area_ratio"], min_feat, stats)
    _straighten(R, stats)
    return PlanarMap.from_rings(R.verts, R.rings), dict(sorted(stats.items()))


# ---------------------------------------------------------------- slivers
def _merge_slivers(R: _Rings, ratio: float, min_width: float, stats: Counter) -> None:
    """Merge pieces that are too small or too thin into the neighbour sharing the
    longest boundary, smallest first, until none is left (or none can be merged)."""
    while True:
        areas = np.array([R.poly(r).area for r in R.rings])
        med = float(np.median(areas))
        cand = [int(i) for i in np.argsort(areas)
                if areas[i] < ratio * med
                or R.poly(R.rings[i]).buffer(-min_width / 2).is_empty]
        owner = R.edge_owner()
        done = False
        for i in cand:
            for j in _neighbours_by_shared_length(R, i, owner):
                new = _merge_rings(R.rings[i], R.rings[j])
                if new is not None and R.ok(new):
                    R.rings[j] = new
                    del R.rings[i]
                    stats["slivers_merged"] += 1
                    done = True
                    break
            if done:
                break
        if not done:
            stats["slivers_unmergeable"] = len(cand)
            return


def _neighbours_by_shared_length(R: _Rings, i: int, owner) -> list[int]:
    shared: dict[int, float] = defaultdict(float)
    r = R.rings[i]
    for k, u in enumerate(r):
        v = r[(k + 1) % len(r)]
        j = owner.get((v, u))
        if j is not None:
            shared[j] += float(np.linalg.norm(R.verts[u] - R.verts[v]))
    return sorted(shared, key=lambda j: -shared[j])


def _merge_rings(a: list[int], b: list[int]) -> list[int] | None:
    """Union of two rings sharing one contiguous chain of edges, or None."""
    eb = {(b[k], b[(k + 1) % len(b)]) for k in range(len(b))}
    n = len(a)
    shared = [(a[k], a[(k + 1) % n]) in {(v, u) for (u, v) in eb} for k in range(n)]
    if all(shared) or not any(shared):
        return None
    # Rotate a so that the shared chain is a single run at the end.
    k0 = next(k for k in range(n) if shared[k] and not shared[k - 1])   # chain start
    runs = sum(1 for k in range(n) if shared[k] and not shared[k - 1])
    if runs != 1:
        return None                        # two separate contacts would leave a hole
    length = 0
    while shared[(k0 + length) % n]:
        length += 1
    s, e = a[k0], a[(k0 + length) % n]     # chain from s to e along a
    a_path = [a[(k0 + length + t) % n] for t in range(n - length + 1)]   # e ... s
    ib = b.index(s)
    b_path = []
    t = 1
    while b[(ib + t) % len(b)] != e:
        b_path.append(b[(ib + t) % len(b)])
        t += 1
        if t > len(b):
            return None
    return a_path + b_path


# ---------------------------------------------------------------- degree-2 vertices
def _straighten(R: _Rings, stats: Counter) -> None:
    owner = R.edge_owner()
    boundary = R.boundary_vertices(owner)
    uses: dict[int, list[int]] = defaultdict(list)
    for i, r in enumerate(R.rings):
        for v in r:
            uses[v].append(i)
    for v, rs in uses.items():
        if v in boundary or len(rs) != 2:
            continue
        new = {i: [x for x in R.rings[i] if x != v] for i in rs}
        if all(R.ok(r) for r in new.values()):
            for i, r in new.items():
                R.rings[i] = r
            stats["vertices_straightened"] += 1


# ---------------------------------------------------------------- short joints
def _contract_short(R: _Rings, threshold: float, stats: Counter) -> None:
    skipped: set[tuple[int, int]] = set()
    while True:
        owner = R.edge_owner()
        boundary = R.boundary_vertices(owner)
        edges = [(float(np.linalg.norm(R.verts[u] - R.verts[v])), u, v)
                 for (u, v) in owner if u < v and (v, u) in owner]
        edges = sorted(e for e in edges if e[0] < threshold and (e[1], e[2]) not in skipped)
        if not edges:
            stats["short_joints_left"] = len(skipped)
            return
        _, u, v = edges[0]
        if not _contract(R, u, v, boundary):
            skipped.add((u, v))
            continue
        stats["joints_contracted"] += 1


def _contract(R: _Rings, u: int, v: int, boundary: set[int]) -> bool:
    bu, bv = u in boundary, v in boundary
    if bu and bv:
        return False
    if bv:
        u, v = v, u                        # keep the boundary vertex u in place
    target = R.verts[u] if (bu or bv) else (R.verts[u] + R.verts[v]) / 2
    old_u = R.verts[u].copy()
    R.verts[u] = target
    new_rings = {}
    for i, r in enumerate(R.rings):
        if u in r or v in r:
            nr = [u if x == v else x for x in r]
            nr = [x for k, x in enumerate(nr) if x != nr[k - 1]]
            if not R.ok(nr):
                R.verts[u] = old_u
                return False
            new_rings[i] = nr
    for i, nr in new_rings.items():
        R.rings[i] = nr
    return True
