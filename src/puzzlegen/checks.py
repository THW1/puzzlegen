# === CONTEXT ===
# Purpose:     Partition check (G4/M0 exit criterion): the pieces cover the region exactly,
#              without overlaps, and every outline is a valid simple polygon.
# Decisions:   Overlap is measured as the sum of pairwise intersection areas (STRtree
#              candidates), coverage as |sum(areas) - region area|. Both relative to the
#              region area, so the tolerance is scale-free.
#              Overlays use snap rounding (grid_size=GRID). Without it GEOS 3.14 returned
#              a whole neighbouring piece as the "intersection" of two pieces that share
#              an edge next to a tab (seed 51, hex grid, jitter 0.4), although the piece's
#              centroid was outside the other one. Snap rounding is the robust OverlayNG
#              mode, and 1e-7 mm is far below any printable feature.
# Related:     pipeline.run writes the result into the report; tests use it directly.
# === END CONTEXT ===
from __future__ import annotations

from shapely import STRtree
from shapely.geometry import Polygon

REL_TOL = 1e-9
GRID = 1e-7   # mm, snap-rounding grid for overlays


def partition(pieces: list[Polygon], region: Polygon) -> dict:
    invalid = [i for i, p in enumerate(pieces) if not p.is_valid or p.area <= 0]
    total = sum(p.area for p in pieces)
    overlap = 0.0
    tree = STRtree(pieces)
    for i, p in enumerate(pieces):
        for j in tree.query(p):
            if j > i:
                overlap += p.intersection(pieces[j], grid_size=GRID).area
    outside = sum(p.difference(region, grid_size=GRID).area for p in pieces)
    ra = region.area
    result = {
        "invalid_pieces": invalid,
        "coverage_error": abs(total - ra) / ra,
        "overlap": overlap / ra,
        "outside": outside / ra,
    }
    result["ok"] = (not invalid and result["coverage_error"] < REL_TOL
                    and result["overlap"] < REL_TOL and result["outside"] < REL_TOL)
    return result
