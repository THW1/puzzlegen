import itertools

import pytest

from puzzlegen.config import build
from puzzlegen.frame import make_frame
from puzzlegen.region import make_region


def _frame(**kv):
    cfg = build(kv)
    return cfg, make_frame(make_region(cfg), cfg)


def test_none_style():
    assert _frame(**{"frame.style": "none"})[1] is None


def test_cavity_gap_is_half_clearance():
    cfg, fr = _frame()
    region = make_region(cfg)
    assert fr.cavity.area > region.area
    assert region.exterior.hausdorff_distance(fr.cavity.exterior) == pytest.approx(
        cfg["fabrication.clearance"] / 2 * 2 ** 0.5, rel=1e-3)   # mitre corner: c/2*sqrt2


@pytest.mark.parametrize("style", ["tray", "ring"])
@pytest.mark.parametrize("shape", ["rect", "circle"])
def test_segments_fit_bed_and_do_not_overlap(style, shape):
    cfg, fr = _frame(**{"frame.style": style, "frame.max_segment": 110.0,
                        "region.shape": shape, "region.size": [200.0, 180.0]})
    assert len(fr.segments) >= 4
    solids = [s.floor if s.floor is not None else s.wall for s in fr.segments]
    for s in solids:
        x0, y0, x1, y1 = s.bounds
        assert x1 - x0 <= 110.0 + 5 and y1 - y0 <= 110.0 + 5     # + dovetail depth
    for a, b in itertools.combinations(solids, 2):
        assert a.intersection(b).area < 1e-6
        # side neighbours are exactly `clearance` apart, corner neighbours c*sqrt(2)
        assert a.distance(b) >= cfg["fabrication.clearance"] - 1e-3
    if style == "tray":
        assert all(s.wall is None or s.floor.buffer(1e-6).contains(s.wall)
                   for s in fr.segments)


def test_single_segment_when_small():
    _, fr = _frame(**{"region.size": [100.0, 80.0]})
    assert len(fr.segments) == 1 and fr.cuts == {"x": [], "y": []}
