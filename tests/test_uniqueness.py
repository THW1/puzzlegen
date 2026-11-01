import numpy as np
from shapely.geometry import box

from puzzlegen import pipeline, uniqueness
from puzzlegen.config import build
from puzzlegen.connectors.tab import TabSpec, local_polyline, to_world
from puzzlegen.planar_map import PlanarMap


def _strip(n=3, w=30.0, h=30.0):
    """n squares in a row; every interior joint gets the SAME tab."""
    polys = [np.array(box(i * w, 0, (i + 1) * w, h).exterior.coords)[:-1] for i in range(n)]
    m = PlanarMap.from_polygons(polys)
    spec = TabSpec(1, 0.5, 3.5, 2.0, 1.5, 0.0)
    for c in range(len(m.curve_he)):
        if m.is_interior_curve(c):
            hh = m.curve_he[c]
            a, b = m.verts[m.origin[hh]], m.verts[m.origin[m.twin[hh]]]
            m.curve_pts[c] = to_world(local_polyline(spec, h), a, b, spec.side)
            m.curve_spec[c] = spec
    return m


def test_true_partner_profile_is_exact_negative():
    m = _strip(2)
    p = uniqueness.profiles(m)
    assert len(p) == 2
    assert np.allclose(p[0].pts, -p[1].pts)


def test_identical_connectors_are_ambiguous():
    m = _strip(3)
    pieces = [m.face_polygon(f) for f in m.inner_faces()]
    v = uniqueness.verify(m, pieces, box(0, 0, 90, 30), 0.75, False)
    assert v.strict and v.joint            # same tab, same joint length -> ambiguous
    assert not v.ok


def test_mate_graph_components():
    m = _strip(3)
    c = next(c for c in range(len(m.curve_he)) if m.is_interior_curve(c))
    m.curve_spec[c] = None
    comps, unmated = uniqueness._mate_graph(m)
    assert comps == 2


def test_small_puzzle_is_unique_and_solver_agrees():
    cfg = build({"seed": 3, "tiling.kind": "grid", "tiling.target_count": 16})
    res = pipeline.run(cfg)
    u = res.uniqueness
    assert u["ok"] and u["mate_graph_components"] == 1
    assert u["exact_solver"]["unique"]


def test_flippable_finds_more_pairs():
    base = build({"seed": 1, "tiling.target_count": 30})
    flip = build({"seed": 1, "tiling.target_count": 30, "uniqueness.flippable": True})
    a = pipeline.run(base).uniqueness
    b = pipeline.run(flip).uniqueness
    assert a["ok"] and b["ok"]
    assert len(b["shape_compatible_pairs"]) >= len(a["shape_compatible_pairs"])
