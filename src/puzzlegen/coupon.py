# === CONTEXT ===
# Purpose:     Fit-test coupon (USAGE 2.2): one tab/socket block pair per clearance value,
#              printed apart, so the user can pick the smallest clearance that assembles
#              by hand.
# Decisions:   Uses the same tab geometry (connectors/tab.py), clearance offset and
#              corner rounding as real pieces, and the same extrusion and label code
#              (export3d.py), so the coupon measures exactly what the puzzle will get.
#              Only the clearance varies between pairs; the tab shape is fixed.
#              The clearance value is engraved (mirrored) on the bottom of both blocks.
# Related:     cli.py::_coupon, export3d.piece_solid / place_label / write_stl.
# === END CONTEXT ===
from __future__ import annotations

from pathlib import Path

import manifold3d as mf
import numpy as np
from shapely.geometry import Polygon, box

from .connectors.tab import TabSpec, local_polyline, to_world
from .export3d import _slab, pack, Part, piece_solid, place_label, write_stl

BLOCK_W, BLOCK_H = 24.0, 18.0
CORNER_R = 0.5


def pair(clearance: float, head_size: float) -> tuple[Polygon, Polygon]:
    """Exact male/female outlines sharing the edge x = BLOCK_W, then offset."""
    r = head_size / 2
    spec = TabSpec(side=-1, t=0.5, r=r, neck=0.65 * r, neck_h=max(0.5, 0.3 * r), skew=0.0)
    a, b = np.array([BLOCK_W, 0.0]), np.array([BLOCK_W, BLOCK_H])
    head = Polygon(to_world(local_polyline(spec, BLOCK_H), a, b, spec.side)[1:-1])
    male = box(0, 0, BLOCK_W, BLOCK_H).union(head)
    female = box(BLOCK_W, 0, 2 * BLOCK_W, BLOCK_H).difference(head)
    return _offset(male, clearance), _offset(female, clearance)


def _offset(p: Polygon, c: float) -> Polygon:
    q = p.buffer(-c / 2, join_style="round", quad_segs=8)
    return q.buffer(-CORNER_R, quad_segs=8).buffer(CORNER_R, quad_segs=8)


def write(out: Path, values: list[float], thickness: float, head_size: float) -> Path:
    parts = []
    for c in values:
        for k, outline in enumerate(pair(c, head_size)):
            s = piece_solid(outline, thickness, "chamfer:0.4", 0.3)
            lab = place_label(outline, f"{c:.2f}")
            if lab is not None:
                s = s - _slab(lab, -0.01, 0.4)
            parts.append(Part(f"c{c}_{k}", s))
    plates = pack(parts, (250.0, 250.0), 4.0)
    if len(plates) > 1:
        raise ValueError("too many clearance values for one 250 x 250 mm plate")
    path = out / "coupon.stl"
    write_stl(path, mf.Manifold.batch_boolean([p.solid for p in plates[0]], mf.OpType.Add))
    return path
