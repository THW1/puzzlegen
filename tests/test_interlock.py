import math

import numpy as np

from puzzlegen.connectors.tab import TabSpec, local_polyline
from puzzlegen.interlock import is_locking, turning_sweep


def test_straight_edge_does_not_lock():
    assert turning_sweep(np.array([[0, 0], [10, 0]])) == 0.0
    assert not is_locking(np.array([[0, 0], [5, 0], [10, 0]]), 20)


def test_semicircle_is_the_limit_case():
    a = np.linspace(math.pi, 0, 200)
    bump = np.column_stack([5 + 2 * np.cos(a), 2 * np.sin(a)])
    pts = np.vstack([[0, 0], bump, [10, 0]])
    assert abs(math.degrees(turning_sweep(pts)) - 180) < 3
    assert not is_locking(pts, 5)


def test_keyhole_tab_locks():
    for skew in (-0.3, 0.0, 0.3):
        pts = local_polyline(TabSpec(1, 0.5, 3.0, 1.8, 1.0, skew), 30.0)
        assert math.degrees(turning_sweep(pts)) > 250
        assert is_locking(pts, 20)


def test_s_curve_with_overhangs_locks():
    # Two lobes that each turn 110 degrees: sweep 220 degrees.
    u = np.linspace(0, 1, 400)
    theta = math.radians(110) * np.sin(2 * math.pi * u)
    pts = np.cumsum(np.column_stack([np.cos(theta), np.sin(theta)]), axis=0)
    assert abs(math.degrees(turning_sweep(pts)) - 220) < 2
    assert is_locking(pts, 20)
