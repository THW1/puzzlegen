import pytest

from puzzlegen import checks, pipeline
from puzzlegen.config import build
from puzzlegen.fabricate import check_result
from puzzlegen.grouping import boundary_cycle


def test_boundary_cycle():
    # two unit squares side by side -> one hexagon-like cycle of 6 vertices
    a, b = [0, 1, 4, 3], [1, 2, 5, 4]
    assert sorted(boundary_cycle([a, b])) == [0, 1, 2, 3, 4, 5]
    # two squares touching at a corner only -> pinch -> None
    assert boundary_cycle([[0, 1, 2, 3], [2, 4, 5, 6]]) is None


@pytest.mark.parametrize("kind", [{"tiling.kind": "voronoi"},
                                  {"tiling.kind": "grid", "tiling.grid.cell": "hex"}])
def test_grow_partition_size_and_necks(kind):
    cfg = build({**kind, "grouping.strategy": "grow", "tiling.target_count": 20,
                 "connectors.kinds": ["none"], "grouping.compactness": 0.3, "seed": 3})
    res = pipeline.run(cfg)
    assert res.partition["ok"]
    assert 15 <= len(res.pieces) <= 25
    assert check_result(res.fab)["ok"]                      # no necks below min_neck
    assert res.interlock["locked"] > 0                      # shape alone locks some joints


def test_hierarchy_hybrid_locks():
    cfg = build({"tiling.kind": "penrose", "grouping.strategy": "hierarchy",
                 "tiling.target_count": 25, "connectors.placement": "unlocked", "seed": 1})
    res = pipeline.run(cfg)
    assert res.partition["ok"]
    assert res.interlock["locked"] >= 0.7 * res.interlock["joints"]


def test_placement_unlocked_skips_locking_chains():
    cfg = build({"tiling.kind": "voronoi", "grouping.strategy": "grow", "seed": 4,
                 "tiling.target_count": 20, "connectors.placement": "unlocked"})
    res = pipeline.run(cfg)
    m = res.pmap
    from puzzlegen.interlock import is_locking
    # Joints that lock by shape keep their outline (spec "shape"), no tab added.
    shapes = [c for c, s in enumerate(m.curve_spec) if s is not None and s.kind == "shape"]
    assert any(is_locking(m.curve_pts[c], 20) for c in shapes)
    assert checks.partition(res.pieces, res.region)["ok"]


def test_regression_concave_chained_ring_orientation():
    """A grown concave piece whose junction-only polygon is clockwise was reversed by
    from_rings and produced duplicate edges (M4 stress run, seed 0)."""
    res = pipeline.run(build({"seed": 0, "tiling.kind": "voronoi", "grouping.strategy": "grow",
                              "tiling.target_count": 30, "connectors.placement": "unlocked",
                              "grouping.compactness": 0.2}))
    assert res.partition["ok"]
