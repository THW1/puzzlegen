import math

import numpy as np
import pytest
from shapely.geometry import Polygon

from puzzlegen import connectors
from puzzlegen.config import build
from puzzlegen.connectors.tab import TabSpec, local_polyline
from puzzlegen.region import make_region
from puzzlegen.tilings import REGISTRY


def test_tab_geometry_is_exact():
    spec = TabSpec(side=1, t=0.5, r=3.0, neck=2.0, neck_h=1.0, skew=0.0)
    pts = local_polyline(spec, 30.0)
    assert tuple(pts[0]) == (0.0, 0.0) and tuple(pts[-1]) == (30.0, 0.0)
    head = Polygon(pts[1:-1])
    assert head.is_valid
    xs, ys = pts[:, 0], pts[:, 1]
    assert xs.max() - xs.min() <= 30.0
    assert ys.max() == pytest.approx(spec.depth, abs=1e-2)
    # head wider than neck -> undercut (the lock)
    # 32 arc samples: chord error ~0.008 mm per side
    assert head.bounds[2] - head.bounds[0] == pytest.approx(2 * spec.r, abs=0.03)
    assert spec.neck_width < spec.head_width


def test_skew_breaks_mirror_symmetry():
    s = TabSpec(1, 0.5, 3.0, 2.0, 1.0, 0.25)
    pts = local_polyline(s, 30.0)
    mirrored = np.column_stack([30.0 - pts[::-1, 0], pts[::-1, 1]])
    assert not np.allclose(pts, mirrored)


def _puzzle(seed=3, **extra):
    cfg = build({"seed": seed, "tiling.target_count": 40, **extra})
    rng = np.random.default_rng(seed)
    region = make_region(cfg)
    m = REGISTRY[cfg["tiling.kind"]](region, 40, rng, cfg)
    return cfg, m, connectors.assign(m, cfg, rng)


def test_min_wall_and_min_neck_hold():
    cfg, m, stats = _puzzle()
    assert stats["tab"] > 0
    min_neck = cfg["fabrication.min_neck"] + cfg["fabrication.clearance"]
    for c, spec in enumerate(m.curve_spec):
        if spec is None:
            continue
        assert spec.neck_width >= min_neck - 1e-9
        h = m.curve_he[c]
        recv = m.face[h] if spec.side > 0 else m.face[m.twin[h]]
        head = Polygon(m.curve_pts[c][1:-1])
        dist = head.distance(m.face_boundary_except(recv, c))
        # Later tabs only shrink the receiving face where they keep min_wall themselves.
        assert dist >= cfg["connectors.min_wall"] - 1e-6


def test_short_edges_get_no_tab():
    cfg, m, stats = _puzzle()
    for c, spec in enumerate(m.curve_spec):
        h = m.curve_he[c]
        L = float(np.linalg.norm(m.verts[m.origin[h]] - m.verts[m.origin[m.twin[h]]]))
        if L < cfg["connectors.min_edge"]:
            assert spec is None


def test_kind_none_leaves_edges_straight():
    _, m, stats = _puzzle(**{"connectors.kinds": ["none"]})
    assert stats["none"] > 0 and "tab" not in stats
    assert all(len(p) == 2 for p in m.curve_pts)


def test_same_seed_same_result():
    _, m1, _ = _puzzle(seed=7)
    _, m2, _ = _puzzle(seed=7)
    assert all(np.array_equal(a, b) for a, b in zip(m1.curve_pts, m2.curve_pts))
    assert not math.isnan(m1.verts.sum())
