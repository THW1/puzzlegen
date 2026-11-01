# === CONTEXT ===
# Purpose:     Run the stages of DESIGN 2 in order and collect the report data.
#              region -> tiling -> cleanup -> (identity grouping) -> connectors -> pieces
#              -> uniqueness verification + repair -> checks
#              -> fabrication outlines -> frame. 3D export happens in cli.py (it writes files).
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

from . import checks, connectors, interlock, uniqueness
from .cleanup import cleanup
from .config import Config, check_implemented, piece_target
from .fabricate import Fabricated, fabricate
from .frame import Frame, make_frame
from .planar_map import PlanarMap
from .region import make_region
from .tilings import REGISTRY


@dataclass
class Result:
    cfg: Config
    region: Polygon
    pmap: PlanarMap
    pieces: list[Polygon]          # exact outlines; index i = face i + 1
    connector_stats: Counter
    partition: dict
    interlock: dict
    cleanup: dict
    fab: Fabricated                # clearance-offset outlines + printability issues
    frame: Frame | None
    uniqueness: dict


def run(cfg: Config) -> Result:
    check_implemented(cfg)
    rng = np.random.default_rng(cfg["seed"])
    region = make_region(cfg)
    pmap = REGISTRY[cfg["tiling.kind"]](region, piece_target(cfg), rng, cfg)
    pmap.check()
    pmap, cleanup_stats = cleanup(pmap, cfg)
    pmap.check()
    stats, alpha = connectors.assign(pmap, cfg, rng)
    ver = _verify_and_repair(pmap, region, cfg, rng, alpha, stats)
    pieces = [pmap.face_polygon(f) for f in pmap.inner_faces()]
    return Result(cfg, region, pmap, pieces, stats, checks.partition(pieces, region),
                  interlock.joint_report(pmap, cfg["connectors.lock_margin"]), cleanup_stats,
                  fabricate(pieces, cfg), make_frame(region, cfg), ver)


REPAIR_ROUNDS = 10   # verification passes in the repair loop (each costs a full verify)


def _verify_and_repair(pmap: PlanarMap, region: Polygon, cfg: Config,
                       rng: np.random.Generator, alpha, stats: Counter) -> dict:
    """Re-draw one connector of every joint-level ambiguous pair until none is left or
    uniqueness.max_iter re-draws are used up, then verify (DESIGN 7.4).
    Strict (shape-only) pairs are not chased: placement already maximises shape
    distinctness, and beyond the shape alphabet's capacity (about 60 tabs at the
    default head sizes) re-drawing cannot remove them (measured in M2: 85 pairs left
    after 2000 re-draws on 75 joints, 70 s)."""
    if not cfg["uniqueness.enabled"]:
        return {"ok": True, "skipped": True}
    tau = cfg["uniqueness.tolerance_k"] * cfg["fabrication.clearance"]
    flip = cfg["uniqueness.flippable"]
    budget = cfg["uniqueness.max_iter"]
    redraws = rounds = 0
    while True:
        pieces = [pmap.face_polygon(f) for f in pmap.inner_faces()]
        v = uniqueness.verify(pmap, pieces, region, tau, flip)
        if not v.joint or redraws >= budget or rounds >= REPAIR_ROUNDS:
            break
        rounds += 1
        for c_a, c_b, _ in v.joint:
            if redraws >= budget:
                break
            c = c_b if rng.random() < 0.5 else c_a
            if pmap.curve_spec[c] is None:
                continue
            kind = connectors.redo(pmap, c, cfg, rng, alpha)
            stats["redrawn"] += 1
            if kind == "skipped_infeasible":
                stats["lost_in_redraw"] += 1
            redraws += 1
    pieces = [pmap.face_polygon(f) for f in pmap.inner_faces()]
    v = uniqueness.verify(pmap, pieces, region, tau, flip, cfg["uniqueness.exact_solver"])
    return {**v.report(), "redraws": redraws}
