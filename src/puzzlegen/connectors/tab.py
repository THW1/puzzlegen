# === CONTEXT ===
# Purpose:     The classic jigsaw tab (DESIGN 5.1) as a polyline in the local edge frame.
# Decisions:   Keyhole construction: straight neck + circular head arc of more than 180°.
#              Neck width (2*neck) and head width (2*r) are then exact, which makes the
#              min_neck check and, later, the uniqueness signatures (DESIGN 7.3)
#              analytic. Rejected for now: free Bezier tabs (prettier, but neck width is
#              only known by measuring the curve).
#              `skew` shifts the head sideways, so a tab differs from its mirror image
#              (flip prevention, DESIGN 7.5).
#              Shape in absolute mm; only the position t is relative to the chord
#              (DESIGN 5).
# Invariants:  Local frame: x along the chord from 0 to L, head on +y. The polyline starts
#              at (0, 0) and ends at (L, 0). neck < r, so the head undercuts the neck
#              (that is what locks).
# Limitations: Sharp corners where the neck meets the chord and the head; rounding comes
#              with the fabrication offsets in M1 (fabrication.corner_radius).
# === END CONTEXT ===
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

ARC_POINTS = 32


@dataclass(frozen=True)
class TabSpec:
    side: int        # +1: head bulges into the left face of the curve's canonical half-edge
    t: float         # head centre position along the chord, 0..1
    r: float         # head radius, mm
    neck: float      # neck half-width, mm (< r)
    neck_h: float    # straight neck height before the head, mm
    skew: float      # sideways head shift, as a fraction of r

    kind = "tab"

    @property
    def head_width(self) -> float:
        return 2 * self.r

    @property
    def neck_width(self) -> float:
        return 2 * self.neck

    @property
    def depth(self) -> float:
        return self.neck_h + math.sqrt(self.r ** 2 - self.neck ** 2) + self.r


def local_polyline(spec: TabSpec, length: float) -> np.ndarray:
    """Tab polyline from (0, 0) to (length, 0), head on +y."""
    c = spec.t * length
    dx = spec.skew * spec.r
    n, r, hn = spec.neck, spec.r, spec.neck_h
    h = math.sqrt(r * r - n * n)
    cx, cy = c + dx, hn + h
    # Arc over the top, clockwise from the left neck point to the right neck point.
    a0 = math.atan2(-h, -n) + 2 * math.pi
    a1 = math.atan2(-h, n)
    ang = np.linspace(a0, a1, ARC_POINTS)
    arc = np.column_stack([cx + r * np.cos(ang), cy + r * np.sin(ang)])
    return np.vstack([[0.0, 0.0], [c - n, 0.0], arc, [c + n, 0.0], [length, 0.0]])


def to_world(local: np.ndarray, a: np.ndarray, b: np.ndarray, side: int) -> np.ndarray:
    """Map local (x along a->b, y to the left of a->b times side) to world coordinates."""
    d = b - a
    ex = d / np.linalg.norm(d)
    ey = np.array([-ex[1], ex[0]]) * side
    return a + local[:, :1] * ex + local[:, 1:] * ey
