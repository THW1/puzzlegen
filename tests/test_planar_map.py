import numpy as np
import pytest

from puzzlegen.planar_map import PlanarMap


def two_squares():
    a = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], float)
    b = np.array([[1, 0], [2, 0], [2, 1], [1, 1]], float)
    return PlanarMap.from_polygons([a, b])


def test_invariants_and_counts():
    m = two_squares()
    m.check()
    assert len(m.verts) == 6
    assert len(m.origin) == 14          # 7 undirected edges
    assert m.n_faces == 3               # outside + 2 cells
    assert sum(m.is_interior_curve(c) for c in range(len(m.curve_he))) == 1


def test_snapping_merges_nearly_equal_vertices():
    a = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], float)
    b = np.array([[1 + 1e-9, 0], [2, 0], [2, 1], [1, 1 - 1e-9]], float)
    m = PlanarMap.from_polygons([a, b])
    m.check()
    assert len(m.verts) == 6


def test_clockwise_input_is_reoriented():
    a = np.array([[0, 0], [0, 1], [1, 1], [1, 0]], float)   # CW
    m = PlanarMap.from_polygons([a])
    m.check()
    assert m.face_polygon(1).exterior.is_ccw


def test_decorated_curve_is_shared():
    m = two_squares()
    c = next(c for c in range(len(m.curve_he)) if m.is_interior_curve(c))
    h = m.curve_he[c]
    a, b = m.verts[m.origin[h]], m.verts[m.origin[m.twin[h]]]
    mid = (a + b) / 2 + np.array([0.1, 0.0])   # push the edge midpoint into the right cell
    m.curve_pts[c] = np.array([a, mid, b])
    p1, p2 = m.face_polygon(1), m.face_polygon(2)
    assert p1.area + p2.area == pytest.approx(2.0)
    assert p1.intersection(p2).area == pytest.approx(0.0)


def test_overlapping_cells_rejected():
    a = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], float)
    with pytest.raises(ValueError):
        PlanarMap.from_polygons([a, a.copy()])
