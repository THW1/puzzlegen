# === CONTEXT ===
# Purpose:     The puzzle outline (DESIGN 3) as a Shapely polygon in mm, origin at the
#              lower-left corner of the bounding box.
# Decisions:   M0 implements only the rectangle; other shapes are rejected earlier by
#              config.check_implemented, so this module stays trivial until M1.
# Related:     config.py:region.*; used by tilings/* for clipping and seed sampling.
# === END CONTEXT ===
from __future__ import annotations

from shapely.geometry import Polygon, box

from .config import Config


def make_region(cfg: Config) -> Polygon:
    w, h = cfg["region.size"]
    if cfg["region.shape"] != "rect":
        raise NotImplementedError(cfg["region.shape"])
    return box(0.0, 0.0, w, h)
