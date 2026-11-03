"""The vendored substitution systems are verified geometrically, not trusted."""
import numpy as np
import pytest
from shapely import STRtree
from shapely.geometry import Polygon

from puzzlegen import checks
from puzzlegen.config import build
from puzzlegen.region import make_region
from puzzlegen.tilings import substitution
from puzzlegen.tilings._kaplan import HAT_OUTLINE, SPECTRE_OUTLINE, hat_patch, spectre_patch


def _sig(p):
    return np.round(np.sort(np.linalg.norm(np.roll(p, -1, 0) - p, axis=1)), 6)


def _signed_area(p):
    x, y = p[:, 0], p[:, 1]
    return 0.5 * float(x @ np.roll(y, -1) - y @ np.roll(x, -1))


def _overlap(polys):
    tree = STRtree(polys)
    return sum(polys[i].intersection(polys[j]).area
               for i in range(len(polys)) for j in tree.query(polys[i]) if j > i)


@pytest.mark.parametrize("level", [1, 2, 3])
def test_hat_patch_is_a_valid_tiling(level):
    tiles = hat_patch(level)
    proto = np.array(HAT_OUTLINE) * 0.5           # the system places hats at scale 0.5
    assert all(np.allclose(_sig(p), _sig(proto), atol=1e-6) for p, _ in tiles)
    assert _overlap([Polygon(p) for p, _ in tiles]) < 1e-8
    reflected = sum(_signed_area(p) < 0 for p, _ in tiles) / len(tiles)
    assert 0.1 < reflected < 0.15                 # hat tilings need reflected hats
    assert len({len(path) for _, path in tiles}) == 1   # uniform tree depth


@pytest.mark.parametrize("level", [1, 2, 3])
def test_spectre_patch_is_chiral_and_valid(level):
    tiles = spectre_patch(level)
    proto = np.array(SPECTRE_OUTLINE)
    assert all(np.allclose(_sig(p), _sig(proto), atol=1e-6) for p, _ in tiles)
    assert _overlap([Polygon(p) for p, _ in tiles]) < 1e-8
    signs = {np.sign(_signed_area(p)) for p, _ in tiles}
    assert len(signs) == 1                        # strictly chiral: one handedness only


@pytest.mark.parametrize("kind", ["hat", "spectre"])
def test_tiling_partitions_region(kind):
    cfg = build({"tiling.kind": kind, "tiling.target_count": 40, "seed": 2})
    region = make_region(cfg)
    gen = substitution.generate_hat if kind == "hat" else substitution.generate_spectre
    m = gen(region, 40, np.random.default_rng(2), cfg)
    m.check()
    assert checks.partition([m.face_polygon(f) for f in m.inner_faces()], region)["ok"]


def test_metatile_tags_group_hats():
    cfg = build({"tiling.kind": "hat", "grouping.strategy": "metatile",
                 "tiling.target_count": 20, "seed": 1})
    m = substitution.generate_hat(make_region(cfg), 20, np.random.default_rng(1), cfg)
    sizes = np.bincount(np.unique([str(t) for t in m.face_tag[1:]], return_inverse=True)[1])
    assert sizes.max() <= 4 + 2                   # metatiles hold 1-4 hats (+ clipped parts)


def test_unsupported_tile_variants_rejected():
    from puzzlegen.config import ConfigError, check_implemented
    with pytest.raises(ConfigError, match="not implemented"):
        check_implemented(build({"tiling.kind": "hat", "tiling.hat.a": 1.7320508,
                                 "tiling.hat.b": 1.0}))
    with pytest.raises(ConfigError, match="not implemented"):
        check_implemented(build({"tiling.kind": "spectre", "tiling.spectre.curved_edges": True}))
