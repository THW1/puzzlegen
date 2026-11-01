# === CONTEXT ===
# Purpose:     Pairwise lock test per joint (DESIGN 5.4, 7.3): can the two pieces of a
#              joint slide apart in the plane, considering only each other?
# Decisions:   Analytic turning criterion instead of sampling translation directions.
#              Piece B can slide away from A along direction d iff the joint curve is a
#              graph over the axis perpendicular to d, i.e. iff all tangent directions
#              of the curve lie in an open half-plane. So the joint LOCKS iff the
#              continuous (unwrapped) tangent angle along the curve sweeps at least
#              180°. A plain straight edge sweeps 0°, a semicircular bump exactly 180°
#              (no undercut, does not lock), a keyhole tab about 290°.
#              A lock margin (connectors.lock_margin, default 20°) is required on top of
#              180°, so the undercut survives the clearance gap and print tolerances.
#              This works for any joint shape (tabs, swirls, jagged grouped outlines),
#              which is what makes connector-free puzzles checkable.
# Limitations: Tests each joint alone. Two non-locking joints between the same pair of
#              pieces (possible after grouping) can still lock together; that case needs
#              the sampled translation test of DESIGN 7.3 (M2/M3).
# Related:     report.py (stats), DESIGN 5.4.
# Tests:       tests/test_interlock.py
# === END CONTEXT ===
from __future__ import annotations

import math

import numpy as np

from .planar_map import PlanarMap


def turning_sweep(pts: np.ndarray) -> float:
    """Range (max - min) of the unwrapped tangent angle along a polyline, radians."""
    d = np.diff(pts, axis=0)
    d = d[np.linalg.norm(d, axis=1) > 1e-12]
    if len(d) < 2:
        return 0.0
    ang = np.unwrap(np.arctan2(d[:, 1], d[:, 0]))
    return float(ang.max() - ang.min())


def is_locking(pts: np.ndarray, margin_deg: float) -> bool:
    return turning_sweep(pts) >= math.pi + math.radians(margin_deg)


def joint_report(m: PlanarMap, margin_deg: float) -> dict:
    """Lock status of all interior joints and pieces without any locking joint."""
    locked_by_face: dict[int, int] = {f: 0 for f in m.inner_faces()}
    n_locked = n_joints = 0
    for c in range(len(m.curve_he)):
        if not m.is_interior_curve(c):
            continue
        n_joints += 1
        if is_locking(m.curve_pts[c], margin_deg):
            n_locked += 1
            h = m.curve_he[c]
            locked_by_face[m.face[h]] += 1
            locked_by_face[m.face[m.twin[h]]] += 1
    loose = sorted(f for f, k in locked_by_face.items() if k == 0)
    return {"joints": n_joints, "locked": n_locked, "unlocked": n_joints - n_locked,
            "loose_pieces": loose}
