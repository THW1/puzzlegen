import pytest
from shapely.geometry import Polygon, box

from puzzlegen import pipeline
from puzzlegen.config import build
from puzzlegen.fabricate import check_result, fabricate


def test_gap_between_neighbours_equals_clearance():
    cfg = build({"fabrication.clearance": 0.3, "fabrication.corner_radius": 0.0})
    a, b = box(0, 0, 10, 10), box(10, 0, 20, 10)
    fab = fabricate([a, b], cfg)
    assert fab.outlines[0].distance(fab.outlines[1]) == pytest.approx(0.3)


def test_thin_neck_detected():
    cfg = build({})
    # Two blocks joined by a 2 mm bridge (< min_neck 3 mm).
    dumbbell = box(0, 0, 10, 10).union(box(10, 4, 14, 6)).union(box(14, 0, 24, 10))
    res = check_result(fabricate([dumbbell], cfg))
    assert res["neck_below_min"] == [0] and not res["ok"]


def test_piece_too_small_for_clearance():
    cfg = build({"fabrication.clearance": 1.0, "connectors.min_wall": 4.0})
    res = check_result(fabricate([box(0, 0, 0.8, 0.8)], cfg))
    assert res["split_or_vanished"] == [0] and not res["ok"]


def test_convex_corners_rounded_concave_kept():
    cfg = build({"fabrication.clearance": 0.0, "fabrication.corner_radius": 1.0})
    ell = Polygon([(0, 0), (20, 0), (20, 10), (10, 10), (10, 20), (0, 20)])
    out = fabricate([ell], cfg).outlines[0]
    assert out.area < ell.area                       # convex corners lost material
    assert out.buffer(1e-6).contains(Polygon([(9.9, 9.9), (10, 9.9), (10, 10), (9.9, 10)]))


@pytest.mark.parametrize("extra", [{}, {"tiling.kind": "grid"},
                                   {"region.shape": "circle", "region.size": [180, 180]}])
def test_examples_pass_fabrication(extra):
    res = pipeline.run(build({"tiling.target_count": 30, **extra}))
    assert check_result(res.fab)["ok"]
