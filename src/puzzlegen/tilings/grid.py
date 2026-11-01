# === CONTEXT ===
# Purpose:     Jittered square or hex grid (DESIGN 4.4): the classic jigsaw baseline and
#              a simple, predictable test tiling.
# Decisions:   Square: the grid is fitted to the rectangle (nx*ny ~ N, near-square cells)
#              and only interior vertices are jittered, so the cells partition the
#              rectangle exactly without clipping.
#              Hex: Voronoi cells of a triangular lattice, reusing voronoi.clipped_cells,
#              because clipping hexagons to the rectangle is exactly that problem. Jitter
#              moves the lattice seeds.
#              Non-rectangular regions: the square grid is laid over the bounding box
#              (with the count scaled by bbox/region area) and clipped to the region.
# Tests:       tests/test_partition.py
# === END CONTEXT ===
from __future__ import annotations

import math

import numpy as np
import shapely
from shapely.geometry import Polygon

from ..config import Config
from ..planar_map import PlanarMap
from .voronoi import clipped_cells


def generate(region: Polygon, n: int, rng: np.random.Generator, cfg: Config) -> PlanarMap:
    jitter = cfg["tiling.grid.jitter"]
    if cfg["tiling.grid.cell"] == "square":
        return square(region, n, jitter, rng)
    return hexagonal(region, n, jitter, rng)


def square(region: Polygon, n: int, jitter: float, rng: np.random.Generator) -> PlanarMap:
    x0, y0, x1, y1 = region.bounds
    w, h = x1 - x0, y1 - y0
    is_rect = abs(region.area - w * h) < 1e-9 * w * h
    if not is_rect:
        n = round(n * w * h / region.area)
    nx = max(1, round(math.sqrt(n * w / h)))
    ny = max(1, round(n / nx))
    xs, ys = np.linspace(x0, x1, nx + 1), np.linspace(y0, y1, ny + 1)
    gx, gy = np.meshgrid(xs, ys, indexing="ij")
    cell = min(w / nx, h / ny)
    inner = (slice(1, nx), slice(1, ny))
    gx[inner] += rng.uniform(-jitter, jitter, gx[inner].shape) * cell
    gy[inner] += rng.uniform(-jitter, jitter, gy[inner].shape) * cell
    polys = []
    for i in range(nx):
        for j in range(ny):
            idx = [(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)]
            polys.append(np.array([[gx[a], gy[a]] for a in idx]))
    if not is_rect:
        clipped = [Polygon(p).intersection(region) for p in polys]
        polys = [np.asarray(c.exterior.coords)[:-1] for c in clipped
                 if isinstance(c, Polygon) and c.area > 1e-9]
    return PlanarMap.from_polygons(polys)


def hexagonal(region: Polygon, n: int, jitter: float, rng: np.random.Generator) -> PlanarMap:
    x0, y0, x1, y1 = region.bounds
    area = region.area
    # Hexagon of lattice spacing s has area s^2 * sqrt(3) / 2.
    s = math.sqrt(area / n / (math.sqrt(3) / 2))
    row_h = s * math.sqrt(3) / 2
    seeds = []
    for r in range(int((y1 - y0) / row_h) + 2):
        off = (r % 2) * s / 2
        for c in range(int((x1 - x0) / s) + 2):
            seeds.append((x0 + off + c * s, y0 + r * row_h))
    seeds = np.array(seeds) + rng.uniform(-jitter, jitter, (len(seeds), 2)) * s
    inside = shapely.contains_xy(region, seeds[:, 0], seeds[:, 1])
    cells = clipped_cells(region, seeds[inside])
    return PlanarMap.from_polygons([np.asarray(c.exterior.coords)[:-1] for c in cells])
