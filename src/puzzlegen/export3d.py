# === CONTEXT ===
# Purpose:     2D outlines -> printable solids -> binary STL (DESIGN 9.2): piece extrusion
#              with edge chamfers, engraved IDs, frame segments, plate packing.
# Decisions:   manifold3d for extrusion and booleans (guaranteed-manifold output). STL
#              is written directly with numpy, so trimesh is not needed for M1.
#              Chamfers/fillets are built as a stack of thin slabs (STEP mm high), each
#              inset by the profile at its height. Rejected: true lofts between offset
#              outlines - offsetting changes vertex counts and topology, so a loft is not
#              well defined. STEP = 0.2 mm (one typical layer): finer steps are invisible
#              after slicing but multiply the triangle count (0.1 mm gave ~37 MB for 40
#              pieces). Outlines are simplified by SIMPLIFY = 0.01 mm before extrusion,
#              which shifts edges by at most 0.01 mm, far below the clearance.
#              Piece IDs use a built-in seven-segment stroke font, mirrored because the
#              label is read from below. Rejected: a font dependency for ten digits.
#              Plates: shelf packing of axis-aligned bounding boxes, largest first.
#              Frame segments are written one per file (they are usually bed-sized).
# Invariants:  All solids sit on z = 0 and are manifold (checked into the report).
# Related:     fabricate.py (piece outlines), frame.py (frame 2D geometry),
#              coupon.py reuses `piece_solid` and `write_stl`.
# Tests:       tests/test_export3d.py
# === END CONTEXT ===
from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

import manifold3d as mf
import numpy as np
from shapely import affinity
from shapely.geometry import LineString, MultiPolygon, Polygon
from shapely.ops import polylabel, unary_union

from .config import Config

STEP = 0.2          # slab height for chamfer/fillet profiles, mm (one typical layer)
SIMPLIFY = 0.01     # mm, outline simplification before extrusion (<< nozzle width)
LABEL_STROKE = 0.25  # stroke width as a fraction of digit height
LABEL_MIN_H = 3.0    # smallest legible digit height, mm
LABEL_MAX_H = 8.0

# Seven-segment digits: segments a (top) .. g (middle) in a 0.6 x 1.0 cell.
_SEG = {"a": [(0, 1), (0.6, 1)], "b": [(0.6, 1), (0.6, 0.5)], "c": [(0.6, 0.5), (0.6, 0)],
        "d": [(0, 0), (0.6, 0)], "e": [(0, 0.5), (0, 0)], "f": [(0, 1), (0, 0.5)],
        "g": [(0, 0.5), (0.6, 0.5)]}
_DIGITS = {"0": "abcdef", "1": "bc", "2": "abged", "3": "abgcd", "4": "fgbc", "5": "afgcd",
           "6": "afgedc", "7": "abc", "8": "abcdefg", "9": "abcdfg"}


# ---------------------------------------------------------------- 2D -> manifold
def _cross_section(g: Polygon | MultiPolygon) -> mf.CrossSection:
    contours = []
    for p in getattr(g, "geoms", [g]):
        contours.append(np.asarray(p.exterior.coords)[:-1])
        contours.extend(np.asarray(r.coords)[:-1] for r in p.interiors)
    return mf.CrossSection(contours, mf.FillRule.EvenOdd)


def _slab(g, z0: float, z1: float) -> mf.Manifold:
    return mf.Manifold.extrude(_cross_section(g), z1 - z0).translate((0.0, 0.0, z0))


def _edge_profile(spec: str) -> tuple[str, float]:
    if spec == "none":
        return "none", 0.0
    kind, size = spec.split(":")
    return kind, float(size)


def _inset(kind: str, size: float, d: float) -> float:
    """Inset at distance d (0..size) from the chamfered face edge."""
    if kind == "chamfer":
        return size - d
    if kind == "fillet":
        return size - np.sqrt(max(0.0, size * size - (size - d) ** 2))
    return 0.0


def piece_solid(outline: Polygon, thickness: float, top: str, bottom_chamfer: float
                ) -> mf.Manifold:
    """Extrude with a stepped bottom chamfer and a stepped top chamfer/fillet."""
    tkind, tsize = _edge_profile(top)
    bsize = bottom_chamfer
    outline = outline.simplify(SIMPLIFY, preserve_topology=True)
    parts: list[mf.Manifold] = []
    nb = int(round(bsize / STEP))
    for k in range(nb):                      # bottom chamfer
        z0, z1 = k * STEP, (k + 1) * STEP
        g = outline.buffer(-_inset("chamfer", bsize, (k + 0.5) * STEP), quad_segs=4)
        if not g.is_empty:
            parts.append(_slab(g, z0, z1))
    nt = int(round(tsize / STEP))
    z_mid0, z_mid1 = nb * STEP, thickness - nt * STEP
    parts.append(_slab(outline, z_mid0, z_mid1))
    for k in range(nt):                      # top edge, k = 0 at the top face
        z1 = thickness - k * STEP
        g = outline.buffer(-_inset(tkind, tsize, (k + 0.5) * STEP), quad_segs=4)
        if not g.is_empty:
            parts.append(_slab(g, z1 - STEP, z1))
    return mf.Manifold.batch_boolean(parts, mf.OpType.Add)


# ---------------------------------------------------------------- labels
def label_polygon(text: str, height: float) -> Polygon | MultiPolygon:
    """Stroke-font text, baseline at y = 0, starting at x = 0."""
    strokes = []
    x = 0.0
    for ch in text:
        if ch == ".":
            strokes.append(LineString([(x + 0.1 * height, 0.0), (x + 0.1 * height + 1e-3, 0.0)]))
            x += 0.4 * height
            continue
        for s in _DIGITS[ch]:
            (ax, ay), (bx, by) = _SEG[s]
            strokes.append(LineString([(x + ax * height, ay * height),
                                       (x + bx * height, by * height)]))
        x += 0.9 * height
    w = LABEL_STROKE * height
    return unary_union([s.buffer(w / 2, cap_style="square") for s in strokes])


def place_label(outline: Polygon, text: str, mirror: bool = True):
    """Largest label that fits inside the outline (with margin), or None."""
    margin = 1.0
    inner = outline.buffer(-margin)
    if inner.is_empty:
        return None
    if isinstance(inner, MultiPolygon):
        inner = max(inner.geoms, key=lambda g: g.area)
    centre = polylabel(inner, tolerance=0.1)
    h = LABEL_MAX_H
    while h >= LABEL_MIN_H:
        lab = label_polygon(text, h)
        if mirror:
            lab = affinity.scale(lab, -1, 1, origin=(0, 0))
        c = lab.centroid
        lab = affinity.translate(lab, centre.x - c.x, centre.y - c.y)
        if inner.contains(lab):
            return lab
        h *= 0.85
    return None


# ---------------------------------------------------------------- output
@dataclass
class Part:
    name: str
    solid: mf.Manifold


def write_stl(path: Path, solid: mf.Manifold) -> None:
    mesh = solid.to_mesh()
    v = np.asarray(mesh.vert_properties)[:, :3].astype(np.float64)
    t = np.asarray(mesh.tri_verts, dtype=np.int64)
    tri = v[t]
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    ln = np.linalg.norm(n, axis=1, keepdims=True)
    n = np.divide(n, ln, out=np.zeros_like(n), where=ln > 0)
    rec = np.zeros(len(t), dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
    rec["n"], rec["v"] = n, tri
    with open(path, "wb") as fh:
        fh.write(b"puzzlegen binary STL".ljust(80, b"\0"))
        fh.write(struct.pack("<I", len(t)))
        fh.write(rec.tobytes())


def pack(parts: list[Part], bed: tuple[float, float], gap: float) -> list[list[Part]]:
    """Shelf packing of bounding boxes; parts are translated in place onto plates."""
    def size(p: Part):
        x0, y0, _, x1, y1, _ = p.solid.bounding_box()
        return x1 - x0, y1 - y0
    order = sorted(range(len(parts)), key=lambda i: -size(parts[i])[1])
    plates: list[list[Part]] = [[]]
    x = y = shelf_h = 0.0
    for i in order:
        w, h = size(parts[i])
        if w > bed[0] or h > bed[1]:
            raise ValueError(f"part {parts[i].name} ({w:.0f} x {h:.0f} mm) exceeds the bed")
        if x + w > bed[0]:                       # next shelf
            x, y, shelf_h = 0.0, y + shelf_h + gap, 0.0
        if y + h > bed[1]:                       # next plate
            plates.append([])
            x = y = shelf_h = 0.0
        x0, y0, *_ = parts[i].solid.bounding_box()
        parts[i].solid = parts[i].solid.translate((x - x0, y - y0, 0.0))
        plates[-1].append(parts[i])
        x += w + gap
        shelf_h = max(shelf_h, h)
    return [p for p in plates if p]


def build_pieces(outlines: list[Polygon | None], cfg: Config) -> tuple[list[Part], dict]:
    t = cfg["fabrication.thickness"]
    depth = cfg["fabrication.label_depth"]
    parts, unlabeled, bad = [], [], []
    for i, o in enumerate(outlines):
        if o is None:
            continue
        s = piece_solid(o, t, cfg["fabrication.top_edge"], cfg["fabrication.bottom_chamfer"])
        if cfg["fabrication.label"] == "bottom":
            lab = place_label(o, str(i + 1))
            if lab is None:
                unlabeled.append(i + 1)
            else:
                s = s - _slab(lab, -0.01, depth)
        if s.status() != mf.Error.NoError or s.is_empty():
            bad.append(i + 1)
        parts.append(Part(f"piece{i + 1}", s))
    return parts, {"unlabeled": unlabeled, "non_manifold": bad}


def build_frame(frame) -> list[Part]:
    parts = []
    for k, seg in enumerate(frame.segments):
        solids = []
        if seg.floor is not None:
            solids.append(_slab(seg.floor, 0.0, frame.floor_h))
        if seg.wall is not None:
            solids.append(_slab(seg.wall, frame.floor_h, frame.floor_h + frame.wall_h))
        parts.append(Part(f"frame{k + 1}", mf.Manifold.batch_boolean(solids, mf.OpType.Add)))
    return parts


def export(outlines, frame, cfg: Config, out: Path, name: str) -> dict:
    pieces, info = build_pieces(outlines, cfg)
    files = []
    if cfg["output.per_piece"]:
        for p in pieces:
            f = out / f"{name}_{p.name}.stl"
            write_stl(f, p.solid)
            files.append(f.name)
    bed = tuple(cfg["output.bed"])
    plates = pack(pieces, bed, cfg["output.plate_gap"])
    for k, plate in enumerate(plates, 1):
        f = out / f"{name}_plate{k}.stl"
        write_stl(f, mf.Manifold.batch_boolean([p.solid for p in plate], mf.OpType.Add))
        files.append(f.name)
    frame_parts = build_frame(frame) if frame is not None else []
    too_big = []
    for p in frame_parts:
        x0, y0, _, x1, y1, _ = p.solid.bounding_box()
        if (x1 - x0 > bed[0] or y1 - y0 > bed[1]) and (y1 - y0 > bed[0] or x1 - x0 > bed[1]):
            too_big.append(p.name)
        f = out / f"{name}_{p.name}.stl"
        x0, y0, *_ = p.solid.bounding_box()
        write_stl(f, p.solid.translate((-x0, -y0, 0.0)))
        files.append(f.name)
        if p.solid.status() != mf.Error.NoError:
            info["non_manifold"].append(p.name)
    return {"ok": not info["non_manifold"] and not too_big, "files": files,
            "plates": len(plates), "frame_segments": len(frame_parts),
            "frame_segments_exceeding_bed": too_big, **info,
            "warnings": ["unlabeled"] if info["unlabeled"] else []}
