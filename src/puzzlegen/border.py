# === CONTEXT ===
# Purpose:     Natural border (DESIGN 3): keep whole pieces whose centroid lies inside
#              the outline, so the puzzle's outer edge (and the frame cavity) follows the
#              pieces instead of cutting through them.
# Decisions:   Runs after grouping, on pieces: tilings are generated over the outline
#              grown by region.margin, then selected here. The new region is the exact
#              union of the kept pieces. Enclosed pieces (inside a hole of the kept set)
#              are added and only the largest connected part is kept, so the region is
#              one polygon without holes (the frame and the map need that).
#              "natural+clip" means the same here; its rectangular outside comes from
#              frame.exterior = "bbox".
#              The map is rebuilt from the kept pieces' full outlines with chaining, so
#              bent joints keep their shape and each piece's outer edge becomes one
#              chain curve (room for frame connectors).
# Related:     pipeline.run (calls select before connectors), config.py:region.border,
#              region.margin; frame.py uses the returned region for the cavity.
# Tests:       tests/test_border.py
# === END CONTEXT ===
from __future__ import annotations

import math

from shapely.geometry import Polygon
from shapely.ops import unary_union

from .config import Config
from .planar_map import PlanarMap


def margin(cfg: Config, region: Polygon, n_pieces: int) -> float:
    m = cfg["region.margin"]
    return 2 * math.sqrt(region.area / max(1, n_pieces)) if m == "auto" else m


def select(m: PlanarMap, region: Polygon) -> tuple[PlanarMap, Polygon]:
    polys = {f: m.face_polygon(f) for f in m.inner_faces()}
    keep = {f for f, p in polys.items() if region.contains(p.centroid)}
    union = unary_union([polys[f] for f in keep])
    if union.geom_type == "MultiPolygon":                  # keep the largest part
        main = max(union.geoms, key=lambda g: g.area)
        keep = {f for f in keep if main.buffer(1e-6).contains(polys[f].representative_point())}
        union = main
    if union.interiors:                                    # fill holes with enclosed pieces
        filled = Polygon(union.exterior)
        keep |= {f for f, p in polys.items() if filled.contains(p.representative_point())}
        union = unary_union([polys[f] for f in keep])
    faces = sorted(keep)
    new = PlanarMap.from_polygons([m.face_ring(f) for f in faces],
                                  tags=[m.face_tag[f] for f in faces], chained=True)
    return new, Polygon(union.exterior)
