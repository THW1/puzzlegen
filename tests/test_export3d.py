import struct

import manifold3d as mf
import pytest
from shapely.geometry import box

from puzzlegen.export3d import Part, label_polygon, pack, piece_solid, place_label, write_stl


def test_piece_solid_is_manifold_with_chamfers():
    s = piece_solid(box(0, 0, 20, 10), 4.0, "chamfer:0.4", 0.3)
    assert s.status() == mf.Error.NoError and s.genus() == 0
    x0, y0, z0, x1, y1, z1 = s.bounding_box()
    assert (z0, z1) == pytest.approx((0.0, 4.0))
    assert s.volume() < 20 * 10 * 4                  # chamfers removed material
    assert s.volume() > 20 * 10 * 4 * 0.97


def test_fillet_profile():
    s = piece_solid(box(0, 0, 20, 10), 4.0, "fillet:0.6", 0.0)
    assert s.status() == mf.Error.NoError


def test_label_fits_and_mirrors():
    outline = box(0, 0, 30, 20)
    lab = place_label(outline, "42")
    assert lab is not None and outline.buffer(-0.99).contains(lab)
    assert place_label(box(0, 0, 3, 3), "123") is None          # too small
    assert label_polygon("1.5", 5).is_valid


def test_stl_roundtrip(tmp_path):
    s = piece_solid(box(0, 0, 10, 10), 3.0, "none", 0.0)
    f = tmp_path / "a.stl"
    write_stl(f, s)
    data = f.read_bytes()
    n = struct.unpack("<I", data[80:84])[0]
    assert n == s.num_tri() and len(data) == 84 + 50 * n


def test_pack_respects_bed():
    parts = [Part(f"p{i}", piece_solid(box(0, 0, 40, 30), 3.0, "none", 0.0))
             for i in range(10)]
    plates = pack(parts, (100.0, 100.0), 2.0)
    assert sum(len(p) for p in plates) == 10 and len(plates) >= 2
    for plate in plates:
        boxes = [p.solid.bounding_box() for p in plate]
        assert all(0 <= b[0] and b[3] <= 100 and 0 <= b[1] and b[4] <= 100 for b in boxes)
    with pytest.raises(ValueError):
        pack([Part("big", piece_solid(box(0, 0, 150, 10), 3, "none", 0))], (100, 100), 2)
