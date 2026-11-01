import numpy as np
import pytest

from puzzlegen import checks
from puzzlegen.cleanup import _merge_rings, cleanup
from puzzlegen.config import build
from puzzlegen.region import make_region
from puzzlegen.tilings import REGISTRY


def _interior_lengths(m):
    return [float(np.linalg.norm(np.diff(m.curve_pts[c], axis=0)))
            for c in range(len(m.curve_he)) if m.is_interior_curve(c)]


@pytest.mark.parametrize("extra", [
    {}, {"tiling.voronoi.seeds": "uniform", "tiling.voronoi.lloyd": 0},
    {"tiling.kind": "grid", "region.shape": "circle", "region.size": [200.0, 200.0]},
    {"tiling.kind": "grid", "tiling.grid.cell": "hex", "region.shape": "polygon"},
])
@pytest.mark.parametrize("seed", [0, 1, 2])
def test_cleanup_keeps_partition_and_removes_short_joints(extra, seed):
    cfg = build({"seed": seed, "tiling.target_count": 40, **extra})
    rng = np.random.default_rng(seed)
    region = make_region(cfg)
    m = REGISTRY[cfg["tiling.kind"]](region, 40, rng, cfg)
    m2, stats = cleanup(m, cfg)
    m2.check()
    assert checks.partition([m2.face_polygon(f) for f in m2.inner_faces()], region)["ok"]
    short = [x for x in _interior_lengths(m2) if x < cfg["connectors.min_edge"]]
    assert len(short) == stats.get("short_joints_left", 0)
    assert stats.get("slivers_unmergeable", 0) == 0


def test_merge_rings():
    a = [0, 1, 2, 3]            # square 0-1-2-3
    b = [1, 4, 5, 2]            # square right of it, shares edge 1-2
    assert sorted(_merge_rings(a, b)) == [0, 1, 2, 3, 4, 5]
    assert _merge_rings(a, [6, 7, 8]) is None


def test_no_connectors_uses_collapse_threshold():
    cfg = build({"connectors.kinds": ["none"], "tiling.target_count": 40})
    rng = np.random.default_rng(0)
    m = REGISTRY["voronoi"](make_region(cfg), 40, rng, cfg)
    m2, _ = cleanup(m, cfg)
    assert min(_interior_lengths(m2)) >= cfg["cleanup.collapse_edge"]
    assert min(_interior_lengths(m2)) < cfg["connectors.min_edge"]
