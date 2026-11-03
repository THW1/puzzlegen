# === CONTEXT ===
# Purpose:     Registry of tiling generators (DESIGN 4). Each generator returns a
#              PlanarMap of cells that exactly partitions the region.
# Decisions:   A plain dict registry, no plugin framework (DESIGN 4). Generators share
#              one signature: (region, target_count, rng, cfg) -> PlanarMap.
# Invariants:  Generator output must partition the region (tests/test_partition.py).
# === END CONTEXT ===
from __future__ import annotations

from typing import Callable

import numpy as np
from shapely.geometry import Polygon

from ..config import Config
from ..planar_map import PlanarMap
from . import grid, penrose, substitution, voronoi

Generator = Callable[[Polygon, int, np.random.Generator, Config], PlanarMap]

REGISTRY: dict[str, Generator] = {
    "voronoi": voronoi.generate,
    "grid": grid.generate,
    "penrose": penrose.generate,
    "hat": substitution.generate_hat,
    "spectre": substitution.generate_spectre,
}
