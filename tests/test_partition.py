# === CONTEXT ===
# Purpose:     M0 exit criterion (DESIGN 12): every generated puzzle is a valid partition
#              of the region, before and after connectors, for random seeds and sizes.
# Decisions:   Property-based (hypothesis) over seed, region size, piece count and
#              tiling; example count kept small so the suite stays fast.
# === END CONTEXT ===
import numpy as np
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from puzzlegen import checks, connectors
from puzzlegen.config import build
from puzzlegen.region import make_region
from puzzlegen.tilings import REGISTRY

TILINGS = [("voronoi", {}), ("voronoi", {"tiling.voronoi.seeds": "uniform",
                                         "tiling.voronoi.lloyd": 0}),
           ("grid", {}), ("grid", {"tiling.grid.cell": "hex"})]


def _make(seed, w, h, n, kind, extra):
    cfg = build({"seed": seed, "region.size": [w, h], "tiling.kind": kind,
                 "tiling.target_count": n, **extra})
    rng = np.random.default_rng(seed)
    region = make_region(cfg)
    return cfg, rng, region, REGISTRY[kind](region, n, rng, cfg)


@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(seed=st.integers(0, 10_000), w=st.floats(60, 300), h=st.floats(60, 300),
       n=st.integers(4, 80), t=st.sampled_from(range(len(TILINGS))))
def test_partition_before_and_after_connectors(seed, w, h, n, t):
    kind, extra = TILINGS[t]
    cfg, rng, region, m = _make(seed, w, h, n, kind, extra)
    m.check()
    before = [m.face_polygon(f) for f in m.inner_faces()]
    assert checks.partition(before, region)["ok"]

    connectors.assign(m, cfg, rng)
    m.check()
    after = [m.face_polygon(f) for f in m.inner_faces()]
    res = checks.partition(after, region)
    assert res["ok"], res


@settings(max_examples=10, deadline=None)
@given(seed=st.integers(0, 10_000), n=st.integers(10, 200))
def test_voronoi_count_is_exact(seed, n):
    *_, m = _make(seed, 200, 150, n, "voronoi", {})
    assert m.n_faces - 1 == n


def test_grid_count_close_to_target():
    for n in (20, 50, 100, 200):
        *_, m = _make(1, 200, 150, n, "grid", {})
        assert abs((m.n_faces - 1) - n) <= 0.1 * n + 2


def test_regression_geos_overlay_seed51():
    """Hex grid case where unsnapped GEOS overlay reported a false overlap (checks.py)."""
    rng0 = np.random.default_rng(51)
    n = int(rng0.integers(3, 400))
    w, h = rng0.uniform(40, 400, 2)
    cfg, rng, region, m = _make(51, w, h, n, "grid",
                                {"tiling.grid.cell": "hex", "tiling.grid.jitter": 0.4})
    connectors.assign(m, cfg, rng)
    res = checks.partition([m.face_polygon(f) for f in m.inner_faces()], region)
    assert res["ok"], res
