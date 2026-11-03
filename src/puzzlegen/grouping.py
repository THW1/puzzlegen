# === CONTEXT ===
# Purpose:     Cells -> pieces (DESIGN 6.2): `hierarchy` (Penrose supertiles) and `grow`
#              (region growing with a lock objective, DESIGN 5.4). The resulting
#              piece outlines are jagged; bent joints become chain curves.
# Decisions:   A group of cells is merged by edge cancellation on vertex rings: directed
#              edges whose reverse is in the same group cancel, the rest must form ONE
#              simple cycle (no pinch vertex, no hole). Rejected: Shapely unions - they
#              may drop vertices that neighbouring pieces still use.
#              grow: seeds by farthest-point sampling on cell centroids; the smallest
#              piece grows next; a candidate cell is scored by compactness (distance to
#              the piece centroid) blended with randomness (1 - compactness). A cell is
#              only added if the piece stays one simple polygon.
#              Lock objective as a local search afterwards, not during growth (the
#              neighbours are unknown while growing): for each pair of neighbouring
#              pieces whose joint does not lock (interlock.turning_sweep), single
#              boundary cells are moved across if that raises the joint's sweep, keeps
#              both pieces valid and within MIN/MAX_SIZE of the target, and does not
#              reduce the number of locked joints of the two pieces.
#              hierarchy: group key = face_tag (Penrose piece-level rhombus); a group
#              that is not one simple polygon (clipped by the region, pinched) is split
#              into connected parts, and parts that are still invalid into single cells.
# Invariants:  Output pieces partition the region (cells are only reassigned).
# Related:     tilings/penrose.py (tags), planar_map.PlanarMap.from_rings_chained,
#              interlock.py, pipeline.run, config.py:grouping.*
# Tests:       tests/test_grouping.py
# === END CONTEXT ===
from __future__ import annotations

from collections import Counter, defaultdict

import numpy as np
from shapely.geometry import Polygon

from .config import Config
from .interlock import is_locking, turning_sweep
from .planar_map import PlanarMap

CELLS_PER_PIECE = 12      # default for grow (cells_per_piece = "auto")
MIN_SIZE, MAX_SIZE = 0.5, 1.8   # piece size limits for lock moves, relative to target
LOCK_PASSES = 10


# ---------------------------------------------------------------- ring helpers
def boundary_cycle(rings: list[list[int]]) -> list[int] | None:
    """Outline of the union of rings as one vertex cycle, or None if it is not a
    single simple cycle (pinch vertex, hole, or several parts)."""
    edges = set()
    for r in rings:
        for k, u in enumerate(r):
            edges.add((u, r[(k + 1) % len(r)]))
    bd = [(u, v) for (u, v) in edges if (v, u) not in edges]
    nxt: dict[int, int] = {}
    for u, v in bd:
        if u in nxt:
            return None                       # pinch: two outgoing boundary edges
        nxt[u] = v
    if not bd:
        return None
    start = bd[0][0]
    cyc, u = [start], nxt[start]
    while u != start:
        cyc.append(u)
        u = nxt.get(u)
        if u is None or len(cyc) > len(bd):
            return None
    return cyc if len(cyc) == len(bd) else None


class _Cells:
    def __init__(self, m: PlanarMap, neck_r: float = 0.0):
        self.neck_r = neck_r
        self.verts = m.verts
        self.rings = m.rings()
        self.tags = m.face_tag[1:]
        edge_cell = {}
        for i, r in enumerate(self.rings):
            for k, u in enumerate(r):
                edge_cell[(u, r[(k + 1) % len(r)])] = i
        self.edge_cell = edge_cell
        self.adj: list[set[int]] = [set() for _ in self.rings]
        for (u, v), i in edge_cell.items():
            j = edge_cell.get((v, u))
            if j is not None:
                self.adj[i].add(j)
        polys = [Polygon(self.verts[r]) for r in self.rings]
        self.area = np.array([p.area for p in polys])
        self.cent = np.array([p.centroid.coords[0] for p in polys])

    def piece_ring(self, cells) -> list[int] | None:
        return boundary_cycle([self.rings[i] for i in cells])

    def ok_piece(self, cells) -> bool:
        """One simple polygon without a neck below min_neck (erosion keeps it whole).
        Cells joined only by a short shared edge would otherwise form thin necks (M3:
        grown Voronoi pieces failed the fabrication neck check)."""
        ring = self.piece_ring(cells)
        if ring is None:
            return False
        if self.neck_r <= 0:
            return True
        core = Polygon(self.verts[ring]).buffer(-self.neck_r)
        return not core.is_empty and core.geom_type == "Polygon"


def _result(C: _Cells, groups: list[list[int]], stats: Counter) -> tuple[PlanarMap, dict]:
    rings, tags = [], []
    for g in groups:
        ring = C.piece_ring(g)
        if ring is None:                      # should not happen; keep cells as pieces
            stats["invalid_groups_split"] += 1
            for i in g:
                rings.append(C.rings[i])
                tags.append(C.tags[i])
            continue
        rings.append(ring)
        tags.append(C.tags[g[0]])
    stats["pieces"] = len(rings)
    return PlanarMap.from_rings_chained(C.verts, rings, tags), dict(sorted(stats.items()))


def group(m: PlanarMap, cfg: Config, rng: np.random.Generator, n_pieces: int
          ) -> tuple[PlanarMap, dict]:
    strategy = cfg["grouping.strategy"]
    if strategy == "identity":
        return m, {}
    C = _Cells(m, 0.99 * (cfg["fabrication.min_neck"] + cfg["fabrication.clearance"]) / 2)
    stats: Counter = Counter()
    if strategy in ("hierarchy", "metatile"):        # both group by the tiling's tags
        groups = _hierarchy(C)
    elif strategy == "grow":
        groups = _grow(C, n_pieces, cfg["grouping.compactness"], rng, stats)
    else:
        raise NotImplementedError(strategy)
    _merge_small(C, groups, cfg["cleanup.min_area_ratio"], stats)
    if strategy == "grow":
        _lock_moves(C, groups, cfg["connectors.lock_margin"], stats)
    return _result(C, groups, stats)


def _merge_small(C: _Cells, groups: list[list[int]], ratio: float, stats: Counter) -> None:
    """Merge pieces smaller than ratio x median area (region-clipped supertiles,
    leftover cells) into the neighbour with the longest shared boundary."""
    while True:
        areas = np.array([C.area[g].sum() for g in groups])
        med = float(np.median(areas))
        owner = {i: k for k, g in enumerate(groups) for i in g}
        merged = False
        for k in np.argsort(areas):
            if areas[k] >= ratio * med:
                break
            shared: Counter = Counter()
            for i in groups[k]:
                r = C.rings[i]
                for t, u in enumerate(r):
                    v = r[(t + 1) % len(r)]
                    j = C.edge_cell.get((v, u))
                    if j is not None and owner[j] != k:
                        shared[owner[j]] += float(np.linalg.norm(C.verts[u] - C.verts[v]))
            for nb, _ in shared.most_common():
                if C.ok_piece(groups[nb] + groups[k]):
                    groups[nb] = groups[nb] + groups[k]
                    del groups[k]
                    stats["small_pieces_merged"] += 1
                    merged = True
                    break
            if merged:
                break
        if not merged:
            return


# ---------------------------------------------------------------- hierarchy
def _components(C: _Cells, cells: list[int]) -> list[list[int]]:
    left, out = set(cells), []
    while left:
        stack = [left.pop()]
        comp = []
        while stack:
            i = stack.pop()
            comp.append(i)
            for j in C.adj[i] & left:
                left.discard(j)
                stack.append(j)
        out.append(comp)
    return out


def _hierarchy(C: _Cells) -> list[list[int]]:
    by_tag: dict = defaultdict(list)
    for i, t in enumerate(C.tags):
        by_tag[t].append(i)
    groups = []
    for cells in by_tag.values():
        for comp in _components(C, cells):
            if C.piece_ring(comp) is not None:
                groups.append(comp)
            else:
                groups.extend([i] for i in comp)
    return groups


# ---------------------------------------------------------------- grow
def _seeds(C: _Cells, n: int, rng: np.random.Generator) -> list[int]:
    first = int(rng.integers(len(C.rings)))
    seeds = [first]
    d = np.linalg.norm(C.cent - C.cent[first], axis=1)
    for _ in range(n - 1):
        nxt = int(np.argmax(d))
        seeds.append(nxt)
        d = np.minimum(d, np.linalg.norm(C.cent - C.cent[nxt], axis=1))
    return seeds


def _grow(C: _Cells, n: int, compactness: float, rng: np.random.Generator,
          stats: Counter) -> list[list[int]]:
    n = max(1, min(n, len(C.rings)))
    owner = np.full(len(C.rings), -1)
    groups = [[s] for s in _seeds(C, n, rng)]
    for g, cells in enumerate(groups):
        owner[cells[0]] = g
    area = np.array([C.area[c[0]] for c in groups])
    scale = np.sqrt(C.area.sum() / n)
    stuck = set()
    while (owner < 0).any() and len(stuck) < n:
        g = min((k for k in range(n) if k not in stuck), key=lambda k: area[k])
        cand = {j for i in groups[g] for j in C.adj[i] if owner[j] < 0}
        if not cand:
            stuck.add(g)
            continue
        cen = np.average(C.cent[groups[g]], axis=0, weights=C.area[groups[g]])
        order = sorted(cand, key=lambda j: compactness * np.linalg.norm(C.cent[j] - cen) / scale
                       + (1 - compactness) * rng.random())
        for j in order:
            if C.ok_piece(groups[g] + [j]):
                groups[g].append(j)
                owner[j] = g
                area[g] += C.area[j]
                break
        else:
            stuck.add(g)
    # Leftover cells (enclosed or blocked): attach to any neighbour that stays valid,
    # otherwise they become pieces of their own.
    for i in np.nonzero(owner < 0)[0]:
        for j in C.adj[i]:
            g = owner[j]
            if g >= 0 and C.ok_piece(groups[g] + [int(i)]):
                groups[g].append(int(i))
                owner[i] = g
                break
        else:
            groups.append([int(i)])
            owner[i] = len(groups) - 1
            stats["leftover_cells"] += 1
    return groups


# ---------------------------------------------------------------- lock objective
def _joint_chains(C: _Cells, a: list[int], b_set: set[int]) -> list[np.ndarray]:
    """Shared boundary of piece a with the cells b_set, as ordered polylines (a's sense).
    Piece a is a simple polygon, so its boundary edges never branch."""
    nxt = {}
    for i in a:
        r = C.rings[i]
        for k, u in enumerate(r):
            v = r[(k + 1) % len(r)]
            if C.edge_cell.get((v, u)) in b_set:
                nxt[u] = v
    prv = {v: u for u, v in nxt.items()}
    chains, seen = [], set()
    for s in [u for u in nxt if u not in prv]:          # open chains
        path = [s]
        while path[-1] in nxt:
            path.append(nxt[path[-1]])
        seen.update(path)
        chains.append(C.verts[path])
    for u in nxt:                                       # closed loop (enclosed piece)
        if u not in seen:
            path = [u]
            while nxt[path[-1]] != u:
                path.append(nxt[path[-1]])
            seen.update(path)
            chains.append(C.verts[path + [u]])
    return chains


def _pair_sweep(C: _Cells, a: list[int], b: list[int]) -> float:
    chains = _joint_chains(C, a, set(b))
    return max((turning_sweep(ch) for ch in chains if len(ch) >= 2), default=0.0)


def _locked_count(C, groups, owner, g, margin) -> int:
    nb = {owner[j] for i in groups[g] for j in C.adj[i]} - {g}
    return sum(any(is_locking(ch, margin) for ch in _joint_chains(C, groups[g], set(groups[h])))
               for h in nb)


def _lock_moves(C: _Cells, groups: list[list[int]], margin: float, stats: Counter) -> None:
    owner = np.full(len(C.rings), -1)
    for g, cells in enumerate(groups):
        owner[cells] = g
    target = C.area.sum() / len(groups)
    limit = np.pi + np.radians(margin)
    for _ in range(LOCK_PASSES):
        moved = 0
        pairs = {(min(owner[i], owner[j]), max(owner[i], owner[j]))
                 for i in range(len(C.rings)) for j in C.adj[i] if owner[i] != owner[j]}
        # Pieces without any locking joint first: they decide require_lock.
        locked_any = {g: _locked_count(C, groups, owner, g, margin) > 0 for g in range(len(groups))}
        for ga, gb in sorted(pairs, key=lambda p: (locked_any[p[0]] and locked_any[p[1]], p)):
            sweep = _pair_sweep(C, groups[ga], groups[gb])
            if sweep >= limit:
                continue
            best = None
            for src, dst in ((ga, gb), (gb, ga)):
                border = [i for i in groups[src] if any(owner[j] == dst for j in C.adj[i])]
                for i in border:
                    if len(groups[src]) <= 1:
                        continue
                    new_src = [x for x in groups[src] if x != i]
                    new_dst = groups[dst] + [i]
                    a_src = C.area[new_src].sum()
                    a_dst = C.area[new_dst].sum()
                    if a_src < MIN_SIZE * target or a_dst > MAX_SIZE * target:
                        continue
                    if not C.ok_piece(new_src) or not C.ok_piece(new_dst):
                        continue
                    s = _pair_sweep(C, new_src if src == ga else new_dst,
                                    new_dst if src == ga else new_src)
                    if s > sweep + 1e-6 and (best is None or s > best[0]):
                        best = (s, i, src, dst, new_src, new_dst)
            if best is None:
                continue
            s, i, src, dst, new_src, new_dst = best
            before = _locked_count(C, groups, owner, src, margin) + \
                _locked_count(C, groups, owner, dst, margin)
            old_src, old_dst = groups[src], groups[dst]
            groups[src], groups[dst] = new_src, new_dst
            owner[i] = dst
            after = _locked_count(C, groups, owner, src, margin) + \
                _locked_count(C, groups, owner, dst, margin)
            if after < before:
                groups[src], groups[dst] = old_src, old_dst
                owner[i] = src
                continue
            moved += 1
        stats["lock_moves"] += moved
        if not moved:
            break
