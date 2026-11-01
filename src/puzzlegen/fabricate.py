# === CONTEXT ===
# Purpose:     Turn exact piece outlines into printable outlines (DESIGN 8): clearance
#              offset, convex-corner rounding, and printability checks.
# Decisions:   Each piece shrinks by clearance/2 and the frame cavity grows by
#              clearance/2 (frame.py), so every gap is `clearance` (DESIGN 3, 8).
#              Only CONVEX corners are rounded (opening by corner_radius). Concave
#              corners stay sharp: an FDM perimeter reproduces inner corners of a solid
#              sharply but rounds outer corners by the bead radius, so a rounded convex
#              corner always fits its sharp concave partner. Rejected: also closing
#              concave corners - that adds material where the neighbour's corner sits.
#              Checks use morphological erosion: a neck narrower than min_neck splits
#              the piece when eroded by min_neck/2 (fatal); parts thinner than
#              min_feature vanish in an opening by min_feature/2 (warning only, because
#              every acute corner tip is "thin" and only very acute ones matter).
# Invariants:  Connectors widen necks to min_neck + clearance (connectors/__init__.py), so
#              after the clearance offset tab necks are >= min_neck.
# Related:     pipeline.run -> fabricate(); export3d.py extrudes `outlines`;
#              frame.py uses the same clearance for the cavity.
# Tests:       tests/test_fabricate.py
# === END CONTEXT ===
from __future__ import annotations

from dataclasses import dataclass, field

import shapely
from shapely.geometry import MultiPolygon, Polygon

from .config import Config

ERODE_SLACK = 0.99   # erode slightly less than the limit: exact-limit necks must survive


@dataclass
class Fabricated:
    outlines: list[Polygon | None]               # index i = piece i; None if unusable
    issues: dict[str, list] = field(default_factory=dict)
    stats: dict = field(default_factory=dict)


def fabricate(pieces: list[Polygon], cfg: Config) -> Fabricated:
    c = cfg["fabrication.clearance"]
    rc = cfg["fabrication.corner_radius"]
    min_neck = cfg["fabrication.min_neck"]
    min_feat = cfg["fabrication.min_feature"]
    outlines: list[Polygon | None] = []
    split, thin_neck, thin_feat = [], [], []
    for i, p in enumerate(pieces):
        q = p.buffer(-c / 2, join_style="round", quad_segs=8) if c > 0 else p
        if rc > 0:
            q = q.buffer(-rc, join_style="round", quad_segs=8).buffer(
                rc, join_style="round", quad_segs=8)
        q = _largest(q, i, split)
        outlines.append(q)
        if q is None:
            continue
        core = q.buffer(-ERODE_SLACK * min_neck / 2, quad_segs=8)
        if isinstance(core, MultiPolygon) and len(core.geoms) > 1:
            thin_neck.append(i)
        opened = q.buffer(-min_feat / 2, quad_segs=8).buffer(min_feat / 2, quad_segs=8)
        lost = q.difference(opened)
        if any(g.area > min_feat ** 2 for g in getattr(lost, "geoms", [lost])):
            thin_feat.append(i)
    usable = [q for q in outlines if q is not None]
    return Fabricated(
        outlines=outlines,
        issues={"split_or_vanished": split, "neck_below_min": thin_neck,
                "thin_features": thin_feat},
        stats={"min_piece_area": min(q.area for q in usable) if usable else 0.0,
               "pieces_usable": len(usable)},
    )


def _largest(q, i: int, split: list) -> Polygon | None:
    """The offset must leave exactly one polygon; otherwise record piece i."""
    if q.is_empty:
        split.append(i)
        return None
    if isinstance(q, MultiPolygon):
        split.append(i)
        q = max(q.geoms, key=lambda g: g.area)
    return shapely.geometry.polygon.orient(q, 1.0)


def check_result(fab: Fabricated) -> dict:
    """Report block; fatal issues make 'ok' false (warnings do not)."""
    return {
        "ok": not fab.issues["split_or_vanished"] and not fab.issues["neck_below_min"],
        **fab.issues,
        "warnings": ["thin_features"] if fab.issues["thin_features"] else [],
    }
