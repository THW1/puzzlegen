# === CONTEXT ===
# Purpose:     The classic jigsaw tab (DESIGN 5.1) as a polyline in the local edge frame.
# Decisions:   Keyhole construction: straight neck + circular head arc of more than 180°.
#              Neck width (2*neck) and head width (2*r) are then exact, which makes the
#              min_neck check and, later, the uniqueness signatures (DESIGN 7.3)
#              analytic. Rejected for now: free Bezier tabs (prettier, but neck width is
#              only known by measuring the curve).
#              `skew` TILTS the whole keyhole (neck and head) about the neck base, so a
#              tab differs from its mirror image (flip prevention, DESIGN 7.5). Rejected:
#              shifting only the head sideways - that slants both neck sides and makes
#              the perpendicular neck width smaller than 2*neck (found by the M1 neck
#              check).
#              Shape in absolute mm; only the position t is relative to the chord
#              (DESIGN 5).
# Invariants:  Local frame: x along the chord from 0 to L, head on +y. The polyline starts
#              at (0, 0) and ends at (L, 0). neck < r, so the head undercuts the neck
#              (that is what locks). The perpendicular neck width is exactly 2*neck for
#              any tilt; |tilt| <= MAX_TILT keeps both neck base points below the head.
# Limitations: Sharp corners where the neck meets the chord and the head; rounding comes
#              with the fabrication offsets in M1 (fabrication.corner_radius).
# === END CONTEXT ===
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

ARC_POINTS = 32
MAX_TILT = math.radians(25)   # tilt at skew = +-1; config skew is within +-0.3


@dataclass(frozen=True)
class TabSpec:
    side: int        # +1: head bulges into the left face of the curve's canonical half-edge
    t: float         # head centre position along the chord, 0..1
    r: float         # head radius, mm
    neck: float      # neck half-width, mm (< r)
    neck_h: float    # straight neck height before the head, mm
    skew: float      # keyhole tilt, as a fraction of MAX_TILT (sign = direction)

    kind = "tab"

    @property
    def head_width(self) -> float:
        return 2 * self.r

    @property
    def neck_width(self) -> float:
        return 2 * self.neck

    def profile_range(self, n_pts: int) -> tuple[int, int]:
        """Index range of the connector itself in the curve polyline (neck base to neck
        base); used by uniqueness.profiles."""
        return 1, n_pts - 1

    @property
    def depth(self) -> float:
        return float(keyhole(self)[:, 1].max())


def keyhole(spec: TabSpec) -> np.ndarray:
    """Neck + head polyline, neck base centred at x = 0 on the chord (y = 0)."""
    n, r, hn = spec.neck, spec.r, spec.neck_h
    h = math.sqrt(r * r - n * n)
    # Upright keyhole in (u, v): neck sides u = -n / +n from the chord up to v = hn,
    # head circle centred at (0, hn + h). Arc clockwise over the top.
    a0 = math.atan2(-h, -n) + 2 * math.pi
    a1 = math.atan2(-h, n)
    ang = np.linspace(a0, a1, ARC_POINTS)
    arc = np.column_stack([r * np.cos(ang), hn + h + r * np.sin(ang)])
    al = spec.skew * MAX_TILT
    ca, sa = math.cos(al), math.sin(al)
    # Neck sides extended to the chord: rotated point (u, v) has y = u*sa + v*ca = 0.
    base_l = np.array([-n, n * sa / ca])
    base_r = np.array([n, -n * sa / ca])
    uv = np.vstack([base_l, arc, base_r])
    return np.column_stack([uv[:, 0] * ca - uv[:, 1] * sa, uv[:, 0] * sa + uv[:, 1] * ca])


def local_polyline(spec: TabSpec, length: float) -> np.ndarray:
    """Tab polyline from (0, 0) to (length, 0), head on +y."""
    k = keyhole(spec) + np.array([spec.t * length, 0.0])
    k[0, 1] = k[-1, 1] = 0.0   # exactly on the chord
    return np.vstack([[0.0, 0.0], k, [length, 0.0]])


def to_world(local: np.ndarray, a: np.ndarray, b: np.ndarray, side: int) -> np.ndarray:
    """Map local (x along a->b, y to the left of a->b times side) to world coordinates."""
    d = b - a
    ex = d / np.linalg.norm(d)
    ey = np.array([-ex[1], ex[0]]) * side
    return a + local[:, :1] * ex + local[:, 1:] * ey
