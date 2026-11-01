# === CONTEXT ===
# Purpose:     The central data structure (DESIGN 2.1): a half-edge planar map whose
#              shared edges are stored once, so decorating an edge changes both
#              neighbouring faces consistently and pieces stay gap- and overlap-free.
# Decisions:   Topology (half-edges) is the source of truth; Shapely polygons are only
#              derived views (`face_polygon`). Rejected: independent polygons per piece,
#              because shared edges drift apart after decoration and adjacency then has
#              to be re-derived with tolerances.
#              Vertex merging in `from_polygons` clusters points within `snap` using a
#              KD-tree + union-find. Rejected: rounding coordinates to a grid, because two
#              nearly equal points can round to different cells.
#              Plain Python lists for half-edge fields: maps have at most a few thousand
#              edges, and clarity beats vectorisation here.
# Invariants:  Face 0 is the outside face. Every half-edge h: twin[twin[h]] == h,
#              prev[next[h]] == h, origin[twin[h]] == destination of h. Inner faces are
#              CCW, so a half-edge's face lies on its left.
#              A curve polyline runs from origin(curve_he) to origin(twin(curve_he));
#              reading it from the twin reverses it.
# Constraints: `from_polygons` needs the union of the polygons to be one simply connected
#              region whose boundary vertices each have exactly one outgoing boundary
#              edge (true for clipped Voronoi cells and grids of a rect region).
# Tests:       tests/test_planar_map.py, tests/test_partition.py
# Limitations: No regions with holes yet (outside face would need several cycles).
#              Joints are single edges; edge chains (DESIGN 2.0 "joint") come with
#              grouping in M3.
# === END CONTEXT ===
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.spatial import cKDTree
from shapely.geometry import LineString, Polygon

OUTSIDE = 0


@dataclass
class PlanarMap:
    verts: np.ndarray                       # (n, 2) float, mm
    origin: list[int] = field(default_factory=list)
    twin: list[int] = field(default_factory=list)
    next: list[int] = field(default_factory=list)
    prev: list[int] = field(default_factory=list)
    face: list[int] = field(default_factory=list)
    curve: list[int] = field(default_factory=list)       # half-edge -> curve id
    face_edge: list[int] = field(default_factory=list)   # face -> one half-edge
    face_kind: list[str] = field(default_factory=list)   # "outside" | "cell"
    curve_he: list[int] = field(default_factory=list)    # curve -> canonical half-edge
    curve_pts: list[np.ndarray] = field(default_factory=list)  # curve -> (m, 2) polyline
    curve_spec: list[object] = field(default_factory=list)     # curve -> connector spec

    # ------------------------------------------------------------ construction
    @classmethod
    def from_polygons(cls, polygons: list[np.ndarray], snap: float = 1e-6) -> "PlanarMap":
        """Build a map from cell polygons (each an (k, 2) array, open ring)."""
        pts = np.concatenate([np.asarray(p, float) for p in polygons])
        ids = _cluster(pts, snap)
        uniq, inv = np.unique(ids, return_inverse=True)
        verts = np.array([pts[ids == u].mean(axis=0) for u in uniq])

        rings: list[list[int]] = []
        k = 0
        for p in polygons:
            ring = [int(v) for v in inv[k:k + len(p)]]
            k += len(p)
            ring = [v for i, v in enumerate(ring) if v != ring[i - 1]]  # drop collapsed
            if len(ring) < 3:
                continue
            if _signed_area(verts[ring]) < 0:
                ring.reverse()
            rings.append(ring)

        m = cls(verts=verts)
        m.face_edge.append(-1)
        m.face_kind.append("outside")
        by_ends: dict[tuple[int, int], int] = {}
        for ring in rings:
            f = len(m.face_edge)
            m.face_kind.append("cell")
            first = len(m.origin)
            n = len(ring)
            for i, v in enumerate(ring):
                h = first + i
                if (v, ring[(i + 1) % n]) in by_ends:
                    raise ValueError("overlapping cells: directed edge used twice")
                by_ends[(v, ring[(i + 1) % n])] = h
                m._add_he(v, f)
                m.next[h] = first + (i + 1) % n
                m.prev[h] = first + (i - 1) % n
            m.face_edge.append(first)

        # twins; unmatched edges get an outside twin
        boundary_from: dict[int, int] = {}
        for (u, v), h in list(by_ends.items()):
            t = by_ends.get((v, u))
            if t is not None:
                m.twin[h] = t
            else:
                o = m._add_he(v, OUTSIDE)
                m.twin[h], m.twin[o] = o, h
                if v in boundary_from:
                    raise ValueError("boundary vertex with two outgoing boundary edges")
                boundary_from[v] = o
        for o in boundary_from.values():
            dest = m.origin[m.twin[o]]
            nxt = boundary_from[dest]
            m.next[o], m.prev[nxt] = nxt, o
        m.face_edge[OUTSIDE] = next(iter(boundary_from.values()))

        for h in range(len(m.origin)):
            if h < m.twin[h]:
                c = len(m.curve_he)
                m.curve_he.append(h)
                m.curve_pts.append(verts[[m.origin[h], m.origin[m.twin[h]]]].copy())
                m.curve_spec.append(None)
                m.curve[h] = m.curve[m.twin[h]] = c
        return m

    def _add_he(self, origin: int, face: int) -> int:
        self.origin.append(origin)
        for lst in (self.twin, self.next, self.prev, self.curve):
            lst.append(-1)
        self.face.append(face)
        return len(self.origin) - 1

    # ------------------------------------------------------------ queries
    @property
    def n_faces(self) -> int:
        return len(self.face_edge)

    def inner_faces(self) -> range:
        return range(1, self.n_faces)

    def face_halfedges(self, f: int) -> list[int]:
        start = self.face_edge[f]
        out, h = [start], self.next[start]
        while h != start:
            out.append(h)
            h = self.next[h]
            if len(out) > len(self.origin):
                raise RuntimeError(f"broken next-cycle at face {f}")
        return out

    def he_points(self, h: int) -> np.ndarray:
        """Polyline of half-edge h in its own direction."""
        pts = self.curve_pts[self.curve[h]]
        return pts if self.curve_he[self.curve[h]] == h else pts[::-1]

    def face_ring(self, f: int, skip_curve: int | None = None) -> np.ndarray:
        """Closed outline of face f as an open ring (concatenated curve polylines)."""
        parts = [self.he_points(h)[:-1] for h in self.face_halfedges(f)
                 if self.curve[h] != skip_curve]
        return np.concatenate(parts)

    def face_polygon(self, f: int) -> Polygon:
        return Polygon(self.face_ring(f))

    def face_boundary_except(self, f: int, c: int) -> LineString:
        """Boundary of face f without curve c, as one open polyline."""
        hs = self.face_halfedges(f)
        i = next(k for k, h in enumerate(hs) if self.curve[h] == c)
        order = hs[i + 1:] + hs[:i]
        pts = [self.he_points(h) for h in order]
        return LineString(np.concatenate([p[:-1] for p in pts[:-1]] + [pts[-1]]))

    def is_interior_curve(self, c: int) -> bool:
        h = self.curve_he[c]
        return self.face[h] != OUTSIDE and self.face[self.twin[h]] != OUTSIDE

    def check(self) -> None:
        """Assert the DCEL invariants (see header)."""
        n = len(self.origin)
        for h in range(n):
            assert self.twin[self.twin[h]] == h, f"twin {h}"
            assert self.prev[self.next[h]] == h, f"next/prev {h}"
            assert self.origin[self.twin[h]] == self.origin[self.next[h]], f"dest {h}"
            assert self.face[self.next[h]] == self.face[h], f"face cycle {h}"
            assert self.curve[h] == self.curve[self.twin[h]], f"curve {h}"
        seen = set()
        for f in range(self.n_faces):
            hs = self.face_halfedges(f)
            assert all(self.face[h] == f for h in hs)
            seen.update(hs)
        assert len(seen) == n, "half-edges not on any face cycle"
        v, e, fc = len(self.verts), n // 2, self.n_faces
        assert v - e + fc == 2, f"Euler: V-E+F = {v - e + fc}"


def _signed_area(p: np.ndarray) -> float:
    x, y = p[:, 0], p[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def _cluster(pts: np.ndarray, tol: float) -> np.ndarray:
    """Union-find over point pairs closer than tol; returns a root id per point."""
    parent = np.arange(len(pts))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, j in cKDTree(pts).query_pairs(tol):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[max(ri, rj)] = min(ri, rj)
    return np.array([find(i) for i in range(len(pts))])
