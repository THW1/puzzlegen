import math
from collections import Counter

import numpy as np
from shapely.geometry import Polygon

from puzzlegen import checks, pipeline
from puzzlegen.config import build
from puzzlegen.region import make_region
from puzzlegen.tilings import penrose

PHI = (1 + 5 ** 0.5) / 2


def _angles(ring):
    out = []
    n = len(ring)
    for i in range(n):
        a, b = ring[i - 1] - ring[i], ring[(i + 1) % n] - ring[i]
        ang = math.degrees(math.atan2(a[0] * b[1] - a[1] * b[0], a @ b)) % 360
        out.append(round(min(ang, 360 - ang)))          # rhombi are convex; ring may be CW
    return tuple(sorted(out))


def test_subdivision_rules_are_geometrically_correct():
    """The rules are verified, not trusted: area is conserved, every BC pair is a thick
    or thin rhombus with equal sides, and thick:thin approaches phi."""
    tris = penrose.sun(0j, 1.0, 0.0)
    area0 = sum(Polygon([(z.real, z.imag) for z in t[1:]]).area for t in tris)
    for _ in range(6):
        tris, _ = penrose.subdivide(tris)
    area = sum(Polygon([(z.real, z.imag) for z in t[1:]]).area for t in tris)
    assert abs(area - area0) < 1e-9
    shapes = Counter()
    for idx in penrose.pair_rhombi(tris):
        if len(idx) != 2:
            continue
        ring = penrose.rhombus_polygon(tris, idx)
        sides = np.linalg.norm(np.roll(ring, -1, axis=0) - ring, axis=1)
        assert np.allclose(sides, sides[0], rtol=1e-6)
        shapes[_angles(ring)] += 1
    assert set(shapes) == {(72, 72, 108, 108), (36, 36, 144, 144)}
    ratio = shapes[(72, 72, 108, 108)] / shapes[(36, 36, 144, 144)]
    assert abs(ratio - PHI) < 0.05


def test_penrose_partition_and_count():
    cfg = build({"tiling.kind": "penrose", "tiling.target_count": 60, "seed": 1})
    region = make_region(cfg)
    m = penrose.generate(region, 60, np.random.default_rng(1), cfg)
    m.check()
    assert checks.partition([m.face_polygon(f) for f in m.inner_faces()], region)["ok"]
    assert 0.8 * 60 <= m.n_faces - 1 <= 1.5 * 60          # clipped border cells add some


def test_hierarchy_tags_cells():
    cfg = build({"tiling.kind": "penrose", "grouping.strategy": "hierarchy",
                 "tiling.target_count": 20, "seed": 2})
    m = penrose.generate(make_region(cfg), 20, np.random.default_rng(2), cfg)
    tags = Counter(m.face_tag[1:])
    assert None not in tags and len(tags) >= 15
    assert np.median(list(tags.values())) >= 4              # several cells per piece


def test_penrose_puzzle_passes_checks():
    res = pipeline.run(build({"tiling.kind": "penrose", "tiling.target_count": 40, "seed": 0}))
    assert res.partition["ok"] and res.uniqueness["ok"]
    assert not res.interlock["loose_pieces"]


def test_patch_always_covers_region():
    """The sun is a decagon (inscribed radius cos 18° of its corner radius); a too
    small patch left a 0.27 mm^2 gap at the region edge for one seed (M3)."""
    for seed in range(6):
        for shape in ("circle", "rect"):
            cfg = build({"tiling.kind": "penrose", "tiling.target_count": 30, "seed": seed,
                         "region.shape": shape, "region.size": [200.0, 200.0]})
            region = make_region(cfg)
            m = penrose.generate(region, 30, np.random.default_rng(seed), cfg)
            res = checks.partition([m.face_polygon(f) for f in m.inner_faces()], region)
            assert res["ok"], (seed, shape, res)
