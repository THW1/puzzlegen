import pytest
from shapely.geometry import Polygon

from puzzlegen import pipeline
from puzzlegen.config import build
from puzzlegen.fabricate import check_result

from pathlib import Path

EXAMPLES = Path(__file__).parents[1] / "examples"
HEART = {"region.shape": "svg", "region.path": str(EXAMPLES / "heart.svg"),
         "region.size": [200.0, 180.0]}


def test_svg_region_is_non_convex_heart():
    from puzzlegen.region import make_region
    r = make_region(build(HEART))
    assert r.is_valid and r.convex_hull.area - r.area > 100      # the cleft between lobes
    x0, y0, x1, y1 = r.bounds
    assert x1 - x0 <= 200.0 + 1e-6 and y1 - y0 <= 180.0 + 1e-6


@pytest.mark.parametrize("kind", ["voronoi", "grid", "penrose", "hat"])
def test_heart_clip_partition(kind):
    res = pipeline.run(build({**HEART, "tiling.kind": kind, "tiling.target_count": 30,
                              "seed": 1}))
    assert res.partition["ok"] and check_result(res.fab)["ok"]


def test_natural_border_keeps_whole_pieces_and_frame_follows():
    cfg = build({**HEART, "region.border": "natural", "tiling.kind": "voronoi",
                 "tiling.target_count": 30, "frame.connectors": False, "seed": 2})
    res = pipeline.run(cfg)
    assert res.partition["ok"]
    from puzzlegen.region import make_region
    heart = make_region(cfg)
    # every kept piece has its centroid inside the heart, and the outline is jagged
    assert all(heart.contains(p.centroid) for p in res.pieces)
    assert abs(res.region.area - heart.area) > 1.0
    assert res.frame.cavity.buffer(1e-6).contains(res.region)


def test_heart_hat_with_frame_connectors_passes_all_checks():
    """M4 exit criterion (examples/heart_hat.toml): hats in a heart-shaped frame with a
    matching border and frame connectors pass all checks; the exact solver proves one
    assembly."""
    from puzzlegen.config import load
    res = pipeline.run(load(EXAMPLES / "heart_hat.toml"))
    u = res.uniqueness
    assert res.partition["ok"] and check_result(res.fab)["ok"]
    assert u["ok"] and u["guarantee"] == "exact"
    assert not res.interlock["loose_pieces"] and res.interlock["frame_locked"] > 0
    assert isinstance(res.region, Polygon)
