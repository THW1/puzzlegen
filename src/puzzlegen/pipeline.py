# === CONTEXT ===
# Purpose:     Run the stages of DESIGN 2 in order and collect the report data.
#              region -> tiling -> cleanup -> grouping -> connectors (+ shape joints)
#              -> pieces
#              -> uniqueness verification + repair -> checks
#              -> fabrication outlines -> frame. 3D export happens in cli.py (it writes files).
# Decisions:   One numpy Generator seeded from cfg.seed drives every random choice, in a
#              fixed stage order, so the same config + seed gives the same output (G6).
#              For `grow`, the tiling makes cells_per_piece x target cells and grouping.py
#              merges them into the target number of pieces.
# Related:     cli.py calls run(); export2d.py and report.py consume the Result.
# Tests:       tests/test_partition.py, tests/test_cli.py
# === END CONTEXT ===
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

import numpy as np
from shapely.geometry import Polygon

from . import checks, connectors, grouping, interlock, uniqueness
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
    color_set: list[int]           # colour set of each piece (output.color_sets)


def run(cfg: Config) -> Result:
    check_implemented(cfg)
    rng = np.random.default_rng(cfg["seed"])
    region = make_region(cfg)
    n = piece_target(cfg)
    n_cells = n
    if cfg["grouping.strategy"] == "grow":
        cpp = cfg["grouping.cells_per_piece"]
        n_cells = round(n * (grouping.CELLS_PER_PIECE if cpp == "auto" else cpp))
    pmap = REGISTRY[cfg["tiling.kind"]](region, n_cells, rng, cfg)
    pmap.check()
    pmap, cleanup_stats = cleanup(pmap, cfg)
    pmap.check()
    pmap, group_stats = grouping.group(pmap, cfg, rng, n)
    pmap.check()
    cleanup_stats = {**cleanup_stats, **({"grouping": group_stats} if group_stats else {})}
    stats, alpha = connectors.assign(pmap, cfg, rng)
    stats["shape_joints"] = connectors.mark_shapes(pmap)
    ver = _verify_and_repair(pmap, region, cfg, rng, alpha, stats)
    pieces = [pmap.face_polygon(f) for f in pmap.inner_faces()]
    return Result(cfg, region, pmap, pieces, stats, checks.partition(pieces, region),
                  interlock.joint_report(pmap, cfg["connectors.lock_margin"]), cleanup_stats,
                  fabricate(pieces, cfg), make_frame(region, cfg), ver,
                  color_sets(len(pieces), cfg["output.color_sets"], cfg["seed"]))


def color_sets(n: int, k: int, seed: int) -> list[int]:
    """Random, balanced split of n pieces into k sets (sizes differ by at most one).
    Uses its own random stream, so changing output.color_sets never changes the puzzle.
    Plain random split on purpose: neighbours may share a set (a map colouring with
    four colours was judged overkill)."""
    if k <= 1:
        return [0] * n
    rng = np.random.default_rng([seed, 0xC0105E7])
    sets = np.empty(n, dtype=int)
    sets[rng.permutation(n)] = np.arange(n) % k
    return sets.tolist()


REPAIR_ROUNDS = 10   # verification passes in the repair loop (each costs a full verify)


def _verify_and_repair(pmap: PlanarMap, region: Polygon, cfg: Config,
                       rng: np.random.Generator, alpha, stats: Counter) -> dict:
    """Re-draw one connector of every joint-level ambiguous pair until none is left or
    uniqueness.max_iter re-draws are used up; drop connectors of pairs that remain
    (see _drop_ambiguous); then verify (DESIGN 7.4).
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
            cs = [x for x in (c_a, c_b) if pmap.curve_spec[x] is not None
                  and pmap.curve_spec[x].kind in connectors.LOCKING]
            if not cs:
                # Two shape joints: replace one by chord + connector.
                for x in (c_a, c_b):
                    if pmap.curve_spec[x] is None or pmap.curve_spec[x].kind != "shape":
                        continue
                    k = connectors.convert_shape(pmap, x, cfg, rng, alpha)
                    redraws += 1
                    if k in connectors.LOCKING:
                        stats["shape_converted"] += 1
                        break
                    stats["shape_kept"] += 1
                continue
            c = cs[int(rng.integers(len(cs)))]
            kind = connectors.redo(pmap, c, cfg, rng, alpha)
            stats["redrawn"] += 1
            if kind == "kept_old":
                stats["redraw_kept_old"] += 1
            redraws += 1
    if v.joint:
        dropped = _drop_ambiguous(pmap, v.joint, cfg["connectors.lock_margin"], alpha)
        stats["dropped_ambiguous"] += dropped
    pieces = [pmap.face_polygon(f) for f in pmap.inner_faces()]
    v = uniqueness.verify(pmap, pieces, region, tau, flip, cfg["uniqueness.exact_solver"])
    return {**v.report(), "redraws": redraws}


def _drop_ambiguous(pmap: PlanarMap, pairs, margin: float, alpha) -> int:
    """Last resort after re-drawing: straighten one joint of each remaining joint-level
    ambiguous pair, if that adds no mate-graph component and leaves no piece without a
    locking joint that had one. A plain joint cannot be confused with another; the pieces stay held by
    their other joints. Added in M3: Penrose joints all have the same length, so the
    tab alphabet alone cannot separate them."""
    dropped = 0
    comps0, _ = uniqueness._mate_graph(pmap)
    loose0 = set(interlock.joint_report(pmap, margin)["loose_pieces"])
    for c_a, c_b, _ in pairs:
        for c in (c_b, c_a):
            spec, pts = pmap.curve_spec[c], pmap.curve_pts[c]
            if spec is None:
                break                            # pair already resolved
            if spec.kind not in connectors.LOCKING:
                continue                         # shape joints cannot be dropped
            h = pmap.curve_he[c]
            pmap.curve_spec[c] = None
            pmap.curve_pts[c] = connectors.strip(pts, spec)
            faces = (pmap.face[h], pmap.face[pmap.twin[h]])
            locked = interlock.joint_report(pmap, margin)
            comps, _ = uniqueness._mate_graph(pmap)
            # Must not make things worse: no new mate-graph component, no new loose piece.
            if comps <= comps0 and not (set(faces) & set(locked["loose_pieces"])) - loose0:
                alpha.remove(c)
                dropped += 1
                break
            pmap.curve_spec[c], pmap.curve_pts[c] = spec, pts   # undo
    return dropped
