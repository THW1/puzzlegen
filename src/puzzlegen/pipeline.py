# === CONTEXT ===
# Purpose:     Run the stages of DESIGN 2 in order and collect the report data.
#              M0: region -> tiling -> (identity grouping) -> connectors -> pieces -> checks.
# Decisions:   One numpy Generator seeded from cfg.seed drives every random choice, in a
#              fixed stage order, so the same config + seed gives the same output (G6).
#              Identity grouping (1 cell = 1 piece) is implicit until M3 adds grouping.py.
# Related:     cli.py calls run(); export2d.py and report.py consume the Result.
# Tests:       tests/test_partition.py, tests/test_cli.py
# === END CONTEXT ===
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

import numpy as np
from shapely.geometry import Polygon

from . import checks, connectors
from .config import Config, check_implemented, piece_target
from .planar_map import PlanarMap
from .region import make_region
from .tilings import REGISTRY


@dataclass
class Result:
    cfg: Config
    region: Polygon
    pmap: PlanarMap
    pieces: list[Polygon]          # index i = face i + 1
    connector_stats: Counter
    partition: dict


def run(cfg: Config) -> Result:
    check_implemented(cfg)
    rng = np.random.default_rng(cfg["seed"])
    region = make_region(cfg)
    pmap = REGISTRY[cfg["tiling.kind"]](region, piece_target(cfg), rng, cfg)
    pmap.check()
    stats = connectors.assign(pmap, cfg, rng)
    pieces = [pmap.face_polygon(f) for f in pmap.inner_faces()]
    return Result(cfg, region, pmap, pieces, stats, checks.partition(pieces, region))
