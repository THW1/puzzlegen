# === CONTEXT ===
# Purpose:     Voronoi cells clipped to the region (DESIGN 4.1), with blue-noise or
#              uniform seeds and optional Lloyd relaxation.
# Decisions:   "poisson" seeds use Mitchell's best-candidate sampling, not Bridson: it
#              yields exactly N points, so target_count is met without a radius search
#              (G7). Bridson only fixes a radius and the count then varies.
#              Four far-away ghost seeds make every real Voronoi cell finite, so no
#              infinite-ridge handling is needed; cells are then clipped with Shapely.
# Constraints: Region must be convex for the clip to give one polygon per seed (true for
#              the M0 rectangle). Non-convex regions arrive in M1 and need MultiPolygon
#              handling here.
# Related:     planar_map.PlanarMap.from_polygons snaps the independently computed
#              boundary intersection points of neighbouring cells together.
# Tests:       tests/test_partition.py
# === END CONTEXT ===
from __future__ import annotations

import numpy as np
from scipy.spatial import Voronoi
from shapely.geometry import Point, Polygon

from ..config import Config
from ..planar_map import PlanarMap

CANDIDATES = 12   # best-candidate sampling: more = more even spacing, slower


def generate(region: Polygon, n: int, rng: np.random.Generator, cfg: Config) -> PlanarMap:
    if cfg["tiling.voronoi.seeds"] == "poisson":
        seeds = best_candidate(region, n, rng)
    else:
        seeds = uniform(region, n, rng)
    cells = clipped_cells(region, seeds)
    for _ in range(cfg["tiling.voronoi.lloyd"]):
        seeds = np.array([c.centroid.coords[0] for c in cells])
        cells = clipped_cells(region, seeds)
    return PlanarMap.from_polygons([np.asarray(c.exterior.coords)[:-1] for c in cells])


def uniform(region: Polygon, n: int, rng: np.random.Generator) -> np.ndarray:
    x0, y0, x1, y1 = region.bounds
    out: list[np.ndarray] = []
    while len(out) < n:
        p = rng.uniform((x0, y0), (x1, y1))
        if region.contains(Point(p)):
            out.append(p)
    return np.array(out)


def best_candidate(region: Polygon, n: int, rng: np.random.Generator) -> np.ndarray:
    """Mitchell's best-candidate: each new point is the candidate farthest from all
    previous points. Cost O(n^2 * CANDIDATES); fine for n up to a few thousand."""
    pts = uniform(region, 1, rng)
    for _ in range(n - 1):
        cand = uniform(region, CANDIDATES, rng)
        d = np.min(np.linalg.norm(cand[:, None, :] - pts[None, :, :], axis=2), axis=1)
        pts = np.vstack([pts, cand[np.argmax(d)]])
    return pts


def clipped_cells(region: Polygon, seeds: np.ndarray) -> list[Polygon]:
    x0, y0, x1, y1 = region.bounds
    span = 10.0 * max(x1 - x0, y1 - y0)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    ghosts = np.array([[cx - span, cy - span], [cx + span, cy - span],
                       [cx + span, cy + span], [cx - span, cy + span]])
    vor = Voronoi(np.vstack([seeds, ghosts]))
    cells = []
    for i in range(len(seeds)):
        reg = vor.regions[vor.point_region[i]]
        assert reg and -1 not in reg, "ghost seeds must bound all real cells"
        cell = Polygon(vor.vertices[reg]).intersection(region)
        if not isinstance(cell, Polygon) or cell.is_empty:
            raise ValueError("clipped Voronoi cell is not a single polygon")
        cells.append(cell)
    return cells
