# === CONTEXT ===
# Purpose:     The central data structure (DESIGN 2.1): a half-edge planar map whose
#              shared edges are stored once, so decorating an edge changes both
#              neighbouring faces consistently and pieces stay gap- and overlap-free.
# Decisions:   Topology (half-edges) is the source of truth; Shapely polygons are only
#              derived views (`face_polygon`). Rejected: independent polygons per piece,
#              because shared edges drift apart after decoration and adjacency then has
#              to be re-derived with tolerances.
#              Vertex merging in `from_polygons` clusters points within `snap` using a
#              KD-tree + union-find; vertices lying on another polygon's edge are inserted
#              into that edge (T-junctions, e.g. the hat's length-2 edge). Rejected: rounding coordinates to a grid, because two
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
#              After grouping, a joint can be a chain: one curve whose polyline runs
#              through the former cell vertices (from_rings `paths`).
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
    face_tag: list[object] = field(default_factory=list)       # face -> tiling data or None

    # ------------------------------------------------------------ construction
    @classmethod
    def from_polygons(cls, polygons: list[np.ndarray], snap: float = 1e-6,
                      tags: list | None = None, chained: bool = False) -> "PlanarMap":
        """Build a map from cell polygons (each an (k, 2) array, open ring). `tags`
        (one per polygon, e.g. Penrose ancestry) end up in face_tag."""
        pts = np.concatenate([np.asarray(p, float) for p in polygons])
        ids = _cluster(pts, snap)
        uniq, inv = np.unique(ids, return_inverse=True)
        verts = np.array([pts[ids == u].mean(axis=0) for u in uniq])
        rings: list[list[int]] = []
        k = 0
        for p in polygons:
            rings.append([int(v) for v in inv[k:k + len(p)]])
            k += len(p)
        rings = _split_t_junctions(verts, rings, snap)
        return (cls.from_rings_chained if chained else cls.from_rings)(verts, rings, tags)

    @classmethod
    def from_rings(cls, verts: np.ndarray, rings: list[list[int]], tags: list | None = None,
                   paths: dict[tuple[int, int], np.ndarray] | None = None) -> "PlanarMap":
        """Build a map from vertex positions and cell rings (vertex indices). Unused
        vertices are dropped, collapsed vertices removed, rings oriented CCW.
        `paths` maps a directed vertex pair (u, v) of a ring to the polyline of that
        edge (chain curves after grouping); missing pairs get a straight curve."""
        clean: list[list[int]] = []
        clean_tags: list = []
        for i, ring in enumerate(rings):
            ring = [v for k, v in enumerate(ring) if v != ring[k - 1]]  # drop collapsed
            if len(ring) < 3:
                continue
            if _signed_area(verts[ring]) < 0:
                ring = ring[::-1]
            clean.append(ring)
            clean_tags.append(tags[i] if tags is not None else None)
        used = sorted({v for r in clean for v in r})
        new_id = {v: i for i, v in enumerate(used)}
        verts = np.asarray(verts, float)[used]
        rings = [[new_id[v] for v in r] for r in clean]

        m = cls(verts=verts)
        m.face_edge.append(-1)
        m.face_kind.append("outside")
        m.face_tag = [None] + clean_tags
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

        inv_id = {i: v for v, i in new_id.items()}
        for h in range(len(m.origin)):
            if h < m.twin[h]:
                c = len(m.curve_he)
                m.curve_he.append(h)
                u, v = m.origin[h], m.origin[m.twin[h]]
                path = None
                if paths:
                    path = paths.get((inv_id[u], inv_id[v]))
                    if path is None and (inv_id[v], inv_id[u]) in paths:
                        path = paths[(inv_id[v], inv_id[u])][::-1]
                m.curve_pts.append(np.array(path, float) if path is not None
                                   else verts[[u, v]].copy())
                m.curve_spec.append(None)
                m.curve[h] = m.curve[m.twin[h]] = c
        return m

    @classmethod
    def from_rings_chained(cls, verts: np.ndarray, rings: list[list[int]],
                           tags: list | None = None) -> "PlanarMap":
        """Like from_rings, but interior vertices shared by exactly two rings (bends
        inside a joint) are not map vertices: the joint becomes one chain curve whose
        polyline runs through them. Every ring keeps at least 3 junctions (vertices
        are promoted if needed, e.g. for a piece enclosed by a single neighbour)."""
        verts = np.asarray(verts, float)
        users: dict[int, int] = {}
        owner: set[tuple[int, int]] = set()
        for r in rings:
            for k, v in enumerate(r):
                users[v] = users.get(v, 0) + 1
                owner.add((v, r[(k + 1) % len(r)]))
        boundary = {u for (u, v) in owner if (v, u) not in owner}
        # Junctions: where 3+ pieces meet, or where two pieces meet the outline. A bend
        # shared by two pieces, and an outline bend touched by one piece, are chain
        # vertices (M4: natural borders are made of many short tile edges, which would
        # otherwise be separate joints too short for frame connectors).
        junction = {v for v, n in users.items() if n >= 3 or (n == 2 and v in boundary)}
        changed = True
        while changed:
            changed = False
            for r in rings:
                js = [v for v in r if v in junction]
                if len(js) < 3:
                    step = max(1, len(r) // 3)
                    junction.update(r[::step][:3])
                    changed = True
        new_rings, paths = [], {}
        for r in rings:
            n = len(r)
            start = next(k for k, v in enumerate(r) if v in junction)
            seq = [r[(start + k) % n] for k in range(n)] + [r[start]]
            ring, path = [], [seq[0]]
            for v in seq[1:]:
                path.append(v)
                if v in junction:
                    ring.append(path[0])
                    if len(path) > 2:
                        paths[(path[0], path[-1])] = verts[path]
                    path = [v]
            new_rings.append(ring)
        return cls.from_rings(verts, new_rings, tags, paths)

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

    def rings(self) -> list[list[int]]:
        """Vertex rings of the inner faces (inverse of from_rings)."""
        return [[self.origin[h] for h in self.face_halfedges(f)] for f in self.inner_faces()]

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


def _split_t_junctions(verts: np.ndarray, rings: list[list[int]], tol: float
                       ) -> list[list[int]]:
    """Insert into each ring edge the vertices of other polygons that lie on it.
    Needed for the hat: its 13-gon outline has one edge of length 2, and a neighbour's
    vertex can sit at that edge's midpoint (T-junction), so shared edges would not match
    end to end."""
    tree = cKDTree(verts)
    out = []
    for r in rings:
        new = []
        for i, u in enumerate(r):
            v = r[(i + 1) % len(r)]
            new.append(u)
            a, b = verts[u], verts[v]
            d = b - a
            L2 = float(d @ d)
            if L2 <= tol * tol:
                continue
            cand = tree.query_ball_point((a + b) / 2, np.sqrt(L2) / 2 + tol)
            on = []
            for w in cand:
                if w in (u, v):
                    continue
                t = float((verts[w] - a) @ d) / L2
                if 0 < t < 1 and np.linalg.norm(a + t * d - verts[w]) <= tol:
                    on.append((t, w))
            new.extend(w for _, w in sorted(on))
        out.append(new)
    return out


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
