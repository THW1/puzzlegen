# === CONTEXT ===
# Purpose:     Swirl joint (DESIGN 5.4): an S-curve over most of the joint with two
#              hooking lobes, one into each piece. It locks by shape, with no distinct knob.
# Decisions:   Built from a prescribed turning function instead of control points:
#              theta(u) = th * sin(3*pi*u) over the window, with th = th1, th2, th3 on
#              the three thirds (separate amplitudes make crest and trough differ, which
#              enlarges the shape alphabet for uniqueness). The curve rises (crest into one
#              piece), descends through the chord at the middle, and returns (trough into
#              the other piece): an S. Each crest/trough flank turns back when th > 90°,
#              which forms the hooks. The tangent sweep is th1 + th2, so the lock
#              criterion (interlock.py: sweep >= 180° + margin) holds when
#              max(th1, th3) + th2 >= 180° + margin (enforced when sampling).
#              Rejected: theta = th*sin(2*pi*u) - it rises and falls on the same side, so
#              it gives one mushroom-shaped bump, not an S.
#              The integrated curve is rotated and scaled so that it ends exactly at the
#              window end on the chord. Rotation shifts all tangent angles equally, so
#              the sweep is unchanged; with th1 != th2 it leaves a small kink at the
#              window ends.
#              The S is point-symmetric only for th1 == th3; `side` and unequal
#              amplitudes make swirls differ from their mirror images.
#              Rejected: Bezier S-curves - their sweep (and so whether they lock) is
#              only known after measuring.
# Invariants:  Local frame as for tabs: x along the chord from 0 to L, first lobe on +y;
#              connectors/tab.py::to_world applies `side`. Polyline =
#              [(0,0), window..., (L,0)]; the window starts and ends on the chord. |th| < 180° keeps the curve free of self-intersections.
# Related:     connectors/__init__.py (sampling, feasibility), interlock.py, DESIGN 5.4.
# Tests:       tests/test_connectors.py
# === END CONTEXT ===
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

SAMPLES = 96
MAX_WINDOW = 32.0      # mm; longer joints get a straight run beside the swirl
MIN_WINDOW = 16.0      # mm; below this the lobe throats get narrower than ~3.3 mm


@dataclass(frozen=True)
class SwirlSpec:
    side: int      # +1: first lobe bulges into the left face of the canonical half-edge
    t: float       # window centre along the chord, 0..1
    w: float       # window length, mm
    th1: float     # turning amplitude of the first third, rad
    th2: float     # turning amplitude of the middle third, rad
    th3: float     # turning amplitude of the last third, rad

    kind = "swirl"

    def profile_range(self, n_pts: int) -> tuple[int, int]:
        return 1, n_pts - 1

    @property
    def sweep(self) -> float:
        return max(self.th1, self.th3) + self.th2


def window_curve(spec: SwirlSpec) -> np.ndarray:
    """S-curve from (0, 0) to (w, 0), first lobe towards +y (to_world applies side)."""
    u = np.linspace(0.0, 1.0, SAMPLES)
    s = np.sin(3 * math.pi * u)            # + on the outer thirds, - in the middle third
    amp = np.where(u <= 1 / 3, spec.th1, np.where(u < 2 / 3, spec.th2, spec.th3))
    theta = amp * s
    tang = np.column_stack([np.cos(theta), np.sin(theta)])
    du = 1.0 / (SAMPLES - 1)
    pts = np.vstack([[0.0, 0.0], np.cumsum((tang[1:] + tang[:-1]) / 2 * du, axis=0)])
    e = pts[-1]
    ang = math.atan2(e[1], e[0])
    rot = np.array([[math.cos(-ang), -math.sin(-ang)], [math.sin(-ang), math.cos(-ang)]])
    pts = (pts @ rot.T) * (spec.w / np.linalg.norm(e))
    pts[0], pts[-1] = (0.0, 0.0), (spec.w, 0.0)
    return pts


def local_polyline(spec: SwirlSpec, length: float) -> np.ndarray:
    win = window_curve(spec) + np.array([spec.t * length - spec.w / 2, 0.0])
    return np.vstack([[0.0, 0.0], win, [length, 0.0]])
