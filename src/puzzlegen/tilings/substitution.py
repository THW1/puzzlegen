# === CONTEXT ===
# Purpose:     Hat and Spectre tilings over the region (DESIGN 4.3): place a substitution
#              patch from tilings/_kaplan.py so it covers the region at the size that
#              gives the target count, clip (or keep whole) cells, and tag each cell with
#              its supertile for hierarchy / metatile grouping.
# Decisions:   Tile size from the target: s = sqrt(region area / (cells * unit tile
#              area)); for grouped strategies cells = pieces x mean group size measured on
#              the generated patch. The level grows until the rotated, scaled region fits
#              inside the patch shrunk by two tile diameters. Kaplan's systems inflate a
#              fixed seed, so the patch is not centred on anything useful: the region is
#              placed at the patch's pole of inaccessibility (deepest interior point).
#              Random rotation (seeded) varies the tiling between seeds.
#              Tag of a cell = its tree path cut to the supertile `height` levels above the
#              tiles (metatile = height 1 for hats). Spectre tiles inside a Mystic are
#              one tree level deeper; cutting by absolute prefix length keeps both halves
#              of a Mystic in the same supertile.
#              Only the standard hat (Tile(1, sqrt 3)) and the straight-edged Spectre are
#              supported; other Tile(a, b) members and curved Spectre edges need their own
#              geometry and are rejected by config.check_implemented.
# Invariants:  Returned cells partition the region they are given (for natural borders
#              pipeline.py passes an enlarged region and selects whole pieces later).
# Related:     tilings/_kaplan.py, grouping.py (hierarchy/metatile use face_tag),
#              config.py:tiling.hat.*, tiling.spectre.*, grouping.level.
# Tests:       tests/test_hat_spectre.py
# === END CONTEXT ===
from __future__ import annotations

import math
from collections import Counter

import numpy as np
from shapely import affinity
from shapely.geometry import Polygon
from shapely.ops import polylabel, unary_union

from ..config import Config
from ..planar_map import PlanarMap
from . import _kaplan

MAX_LEVEL = {"hat": 5, "spectre": 5}
HIER_HEIGHT = 2            # default supertile height for grouping.strategy = "hierarchy"


def _height(cfg: Config) -> int:
    s = cfg["grouping.strategy"]
    if s == "metatile":
        return 1
    if s == "hierarchy":
        return HIER_HEIGHT if cfg["grouping.level"] == "auto" else cfg["grouping.level"]
    return 0


def generate_hat(region: Polygon, n: int, rng: np.random.Generator, cfg: Config) -> PlanarMap:
    return _generate("hat", region, n, rng, cfg)


def generate_spectre(region: Polygon, n: int, rng: np.random.Generator, cfg: Config) -> PlanarMap:
    return _generate("spectre", region, n, rng, cfg)


def _patch(kind: str, level: int):
    return _kaplan.hat_patch(level) if kind == "hat" else _kaplan.spectre_patch(level)


def _keys(tiles, kind: str, level: int, height: int) -> list:
    if height <= 0:
        return [None] * len(tiles)
    base = level + 1 if kind == "hat" else level
    cut = max(0, base - height)
    return [path[:cut] for _, path in tiles]


def _generate(kind: str, region: Polygon, n: int, rng: np.random.Generator, cfg: Config
              ) -> PlanarMap:
    height = _height(cfg)
    angle = rng.uniform(0, 360)
    cx, cy = region.centroid.coords[0]
    for level in range(1, MAX_LEVEL[kind] + 1):
        tiles = _patch(kind, level)
        keys = _keys(tiles, kind, level, height)
        group = np.mean(list(Counter(keys).values())) if height > 0 else 1.0
        unit_area = Polygon(tiles[0][0]).area
        s = math.sqrt(region.area / (n * group * unit_area))     # mm per patch unit
        diam = math.sqrt(unit_area) * 2.5
        union = unary_union([Polygon(p).buffer(1e-9) for p, _ in tiles])
        inner = union.buffer(-2 * diam)
        if inner.is_empty:
            continue
        if inner.geom_type == "MultiPolygon":
            inner = max(inner.geoms, key=lambda g: g.area)
        pole = polylabel(inner, tolerance=diam / 4)
        # Region expressed in patch units, centred on the pole.
        reg_u = affinity.translate(affinity.scale(affinity.rotate(
            affinity.translate(region, -cx, -cy), -angle, origin=(0, 0)),
            1 / s, 1 / s, origin=(0, 0)), pole.x, pole.y)
        if inner.contains(reg_u):
            break
    else:
        raise ValueError(f"{kind}: region too large for a level-{MAX_LEVEL[kind]} patch; "
                         "lower tiling.target_count")
    a = math.radians(angle)
    rot = np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]])
    polys, tags = [], []
    for (p, _), key in zip(tiles, keys):
        world = ((p - [pole.x, pole.y]) * s) @ rot.T + [cx, cy]
        cut = Polygon(world).intersection(region)
        for g in getattr(cut, "geoms", [cut]):
            if isinstance(g, Polygon) and g.area > 1e-6:
                polys.append(np.asarray(g.exterior.coords)[:-1])
                tags.append(key)
    return PlanarMap.from_polygons(polys, tags=tags)
