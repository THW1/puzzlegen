# === CONTEXT ===
# Purpose:     Uniqueness verifier (DESIGN 7): can any connector be received by a socket
#              other than its true partner, and do the mates tie all pieces together?
#              Optionally a small exact solver.
# Decisions:   A "profile" is one side of a decorated joint, seen from that piece: the
#              connector curve in a frame with origin at the connector's base midpoint,
#              x along the piece's CCW direction and y along its outward normal (a head
#              has y > 0, a socket y < 0). Profiles a (piece A) and b (piece B) can mate
#              iff a ~ -b (rotation by 180°): Hausdorff distance < tau =
#              tolerance_k * clearance. The true partner gives exactly -a.
#              Two levels are reported (DESIGN 7.2):
#              - strict: no two connectors are shape-compatible. Sufficient for
#                uniqueness (with U1, U3 and a connected mate graph): every head must sit
#                in its true socket.
#              - joint-level: no shape-compatible pair whose joints also end at the same
#                two points when mated. A false mate that survives this needs the rest of
#                the joint to be bordered by other pieces meeting it mid-edge
#                (T-junctions); possible in principle, but it would have to continue
#                consistently through the whole puzzle.
#              `ok` requires no joint-level ambiguity and a connected mate graph;
#              `guarantee` says which level was reached.
#              Rejected: a pose test (place A in B's socket, check overlap with B and the
#              region). Convex pieces never overlap across a straight joint, and B
#              itself may move in an alternative assembly, so the test excluded nothing
#              valid (tried in M2, all pairs survived).
#              Exact solver: depth-first placement of pieces through shape-compatible
#              mates, counting overlap-free assemblies (inside the region) up to 2 with a
#              node budget. T-junction placements are included; the first piece is fixed
#              at its true pose.
# Invariants:  Profiles are built from the current curves (run after connectors and after
#              each repair). Frames: F = [[X Y o]] maps local to world coordinates.
# Limitations: U3 (no pocket made by two pieces) is assumed from end_margin, not checked.
#              The solver only explores assemblies whose pieces attach to the first piece
#              through mates.
# Related:     connectors/__init__.py (Alphabet scoring, redo), pipeline.run (repair
#              loop), config.py:uniqueness.*
# Tests:       tests/test_uniqueness.py
# === END CONTEXT ===
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import shapely
from scipy.spatial import cKDTree
from shapely import affinity
from shapely.geometry import LineString, Polygon

from .planar_map import PlanarMap

POSE_EPS = 0.5          # mm^2 of overlap that makes a solver placement invalid
SOLVER_BUDGET = 20000   # search nodes
R_MATE = np.diag([-1.0, -1.0, 1.0])     # a ~ -b
R_MIRROR = np.diag([1.0, -1.0, 1.0])    # mirrored a ~ -b (piece flipped over)


# ---------------------------------------------------------------- profiles
def side_profiles(pts: np.ndarray, spec, a: np.ndarray, b: np.ndarray) -> list[tuple]:
    """Both side profiles of a decorated joint a->b: [(local, F, x_lo, x_hi)] for the
    left face (travels a->b) and the right face (travels b->a)."""
    i0, i1 = spec.profile_range(len(pts))
    seg = pts[i0:i1]
    o = (seg[0] + seg[-1]) / 2
    ex = (b - a) / np.linalg.norm(b - a)
    out = []
    for xdir in (ex, -ex):
        nout = np.array([xdir[1], -xdir[0]])
        local = np.column_stack([(seg - o) @ xdir, (seg - o) @ nout])
        F = np.array([[xdir[0], nout[0], o[0]], [xdir[1], nout[1], o[1]], [0, 0, 1.0]])
        xs = sorted([float((a - o) @ xdir), float((b - o) @ xdir)])
        out.append((local, F, xs[0], xs[1]))
    return out


@dataclass
class Profile:
    curve: int
    face: int
    pts: np.ndarray
    F: np.ndarray
    x_lo: float            # joint end points along x (local frame)
    x_hi: float


def profiles(m: PlanarMap) -> list[Profile]:
    out = []
    for c, spec in enumerate(m.curve_spec):
        if spec is None or not m.is_interior_curve(c):
            continue
        h = m.curve_he[c]
        a, b = m.verts[m.origin[h]], m.verts[m.origin[m.twin[h]]]
        for face, (local, F, lo, hi) in zip((m.face[h], m.face[m.twin[h]]),
                                            side_profiles(m.curve_pts[c], spec, a, b)):
            out.append(Profile(c, face, local, F, lo, hi))
    return out


def _feat(p: np.ndarray) -> np.ndarray:
    return np.array([p[:, 0].min(), p[:, 0].max(), p[:, 1].min(), p[:, 1].max()])


def _hausdorff(p: np.ndarray, q: np.ndarray) -> float:
    return float(shapely.hausdorff_distance(LineString(p), LineString(q), densify=0.25))


class Alphabet:
    """Profiles of the connectors placed so far, for greedy distinctness scoring.
    Stores the negated profiles (what a matching candidate must look like) and their
    bounding-box features, so scoring is one vectorised prefilter plus a few Hausdorff
    distances."""

    def __init__(self, tau: float, flippable: bool):
        self.tau, self.flippable = tau, flippable
        self.items: dict[int, list[np.ndarray]] = {}     # curve -> negated profiles
        self._cache: tuple | None = None

    def add(self, c: int, sides: list[tuple]) -> None:
        self.items[c] = [-s[0] for s in sides]
        self._cache = None

    def remove(self, c: int) -> None:
        self.items.pop(c, None)
        self._cache = None

    def _index(self):
        if self._cache is None:
            owners, negs = [], []
            for c, qs in self.items.items():
                for q in qs:
                    owners.append(c)
                    negs.append(q)
            feats = np.array([_feat(q) for q in negs]) if negs else np.zeros((0, 4))
            self._cache = (np.array(owners), negs, feats)
        return self._cache

    def score(self, c: int, sides: list[tuple]) -> float:
        """Distance to the most similar placed connector, capped at tau."""
        owners, negs, feats = self._index()
        if not negs:
            return self.tau
        cand = [s[0] for s in sides]
        if self.flippable:
            cand += [p * np.array([-1.0, 1.0]) for p in cand]
        best = self.tau
        for p in cand:
            near = np.nonzero(np.all(np.abs(feats - _feat(p)) < best, axis=1)
                              & (owners != c))[0]
            for k in near:
                best = min(best, _hausdorff(p, negs[k]))
        return best


# ---------------------------------------------------------------- verification
@dataclass
class Verification:
    strict: list[tuple[int, int, float]] = field(default_factory=list)
    joint: list[tuple[int, int, float]] = field(default_factory=list)
    components: int = 1
    unmated_pieces: list[int] = field(default_factory=list)
    solver: dict | None = None

    @property
    def ok(self) -> bool:
        solver_ok = self.solver is None or self.solver["solutions_found"] <= 1
        return not self.joint and self.components == 1 and solver_ok

    def report(self) -> dict:
        return {"ok": self.ok,
                "guarantee": "strict" if not self.strict else "joint-level",
                "ambiguous_pairs": [list(x) for x in self.joint],
                "shape_compatible_pairs": [list(x) for x in self.strict],
                "mate_graph_components": self.components,
                "unmated_pieces": self.unmated_pieces, "exact_solver": self.solver}


def compatible_pairs(profs: list[Profile], tau: float, flippable: bool):
    """All (i, j, R, dist) with profile i ~ -j (or mirrored i ~ -j), different pieces."""
    if not profs:
        return []
    neg = [-p.pts for p in profs]
    tree = cKDTree(np.array([_feat(q) for q in neg]))
    variants = [(R_MATE, 1.0)] + ([(R_MIRROR, -1.0)] if flippable else [])
    out = []
    for R, sx in variants:
        for i, a in enumerate(profs):
            pa = a.pts * np.array([sx, 1.0])
            for j in tree.query_ball_point(_feat(pa), tau, p=np.inf):
                if profs[j].face == a.face:
                    continue
                d = _hausdorff(pa, neg[j])
                if d < tau:
                    out.append((i, j, R, d))
    return out


def verify(m: PlanarMap, pieces: list[Polygon], region: Polygon, tau: float,
           flippable: bool, solver: str = "never") -> Verification:
    profs = profiles(m)
    v = Verification()
    pairs = compatible_pairs(profs, tau, flippable)
    seen_s, seen_j = set(), set()
    for i, j, R, d in pairs:
        a, b = profs[i], profs[j]
        if a.curve == b.curve:
            continue                                   # the true partner
        key = (min(a.curve, b.curve), max(a.curve, b.curve))
        if key not in seen_s:
            seen_s.add(key)
            v.strict.append((key[0], key[1], round(d, 4)))
        lo, hi = (a.x_lo, a.x_hi) if R is R_MATE else (-a.x_hi, -a.x_lo)
        if abs(lo + b.x_hi) < tau and abs(hi + b.x_lo) < tau and key not in seen_j:
            seen_j.add(key)
            v.joint.append((key[0], key[1], round(d, 4)))
    v.components, v.unmated_pieces = _mate_graph(m)
    if solver == "always" or (solver == "auto" and m.n_faces - 1 <= 30):
        v.solver = exact_solve(m, profs, pairs, pieces, region, tau)
    return v


def _mate_graph(m: PlanarMap) -> tuple[int, list[int]]:
    parent = list(range(m.n_faces))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    mated = set()
    for c, spec in enumerate(m.curve_spec):
        if spec is None or not m.is_interior_curve(c):
            continue
        h = m.curve_he[c]
        f, g = m.face[h], m.face[m.twin[h]]
        mated.update((f, g))
        parent[find(f)] = find(g)
    roots = {find(f) for f in m.inner_faces()}
    return len(roots), sorted(set(m.inner_faces()) - mated)


# ---------------------------------------------------------------- exact solver
def _transform(g, T: np.ndarray):
    return affinity.affine_transform(g, [T[0, 0], T[0, 1], T[1, 0], T[1, 1], T[0, 2], T[1, 2]])


def exact_solve(m: PlanarMap, profs: list[Profile], pairs, pieces: list[Polygon],
                region: Polygon, tau: float) -> dict:
    """Count assemblies reachable through shape-compatible mates (up to 2)."""
    cand: dict[int, list[tuple[int, np.ndarray]]] = {i: [] for i in range(len(profs))}
    for i, j, R, _ in pairs:
        cand[i].append((j, R))
    by_face: dict[int, list[int]] = {}
    for i, p in enumerate(profs):
        by_face.setdefault(p.face, []).append(i)
    faces = list(m.inner_faces())
    shrunk = {f: pieces[f - 1].buffer(-tau) for f in faces}
    region_s = region.buffer(1e-6)
    state = {"nodes": 0, "solutions": 0}

    def fits(f, T, placed):
        g = _transform(shrunk[f], T)
        if g.difference(region_s).area > POSE_EPS:
            return False
        return all(g.intersection(_transform(shrunk[h], Th)).area <= POSE_EPS
                   for h, Th in placed.items())

    def dfs(placed: dict, resolved: frozenset):
        if state["solutions"] >= 2 or state["nodes"] >= SOLVER_BUDGET:
            return
        state["nodes"] += 1
        open_ = [i for f in placed for i in by_face.get(f, []) if i not in resolved]
        if not open_:
            if len(placed) == len(faces):
                state["solutions"] += 1
            return
        a = min(open_, key=lambda i: len(cand[i]))
        TA = placed[profs[a].face]
        for j, R in cand[a]:
            b = profs[j]
            TB = TA @ profs[a].F @ R @ np.linalg.inv(b.F)
            if b.face in placed:
                if np.allclose(placed[b.face], TB, atol=1e-3):
                    dfs(placed, resolved | {a, j})
            elif fits(b.face, TB, placed):
                dfs({**placed, b.face: TB}, resolved | {a, j})

    dfs({faces[0]: np.eye(3)}, frozenset())
    complete = state["nodes"] < SOLVER_BUDGET
    return {"solutions_found": state["solutions"], "nodes": state["nodes"],
            "complete": complete, "unique": state["solutions"] == 1 and complete}
