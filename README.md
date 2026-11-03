# puzzlegen

Generator for irregular interlocking puzzles (Voronoi, Penrose, hat/Spectre tilings)
for 3D printing (STL/3MF) and laser or plotter cutting (SVG/DXF), with an optional
matching frame and a verified unique solution.

- Design: [`DESIGN.md`](DESIGN.md)
- CLI and options (specification): [`USAGE.md`](USAGE.md)

## Status: milestone M4

Works now:
- Regions: rectangle, ellipse/circle, regular polygon, rounded corners, and **SVG
  outlines** (non-convex, e.g. a heart; `pip install svgelements`).
- Tilings: Voronoi, jittered square/hex grids, Penrose P3 (rhombi), **hat** and
  **Spectre** aperiodic monotiles (substitution systems vendored from Kaplan's reference
  implementations and verified geometrically; see `THIRD_PARTY_NOTICES.md`).
- Grouping: `hierarchy` (supertiles), `metatile` (hat clusters), `grow` (pieces grown
  from small cells with a lock objective).
- **Natural border**: whole pieces along the outline; the frame follows them, and
  **frame connectors** tie edge pieces to the frame.
- Connectors: classic tabs and `swirl` joints; hybrid placement (`unlocked`).
- Uniqueness check with three guarantee levels: `exact` (solver proof, ≤ 30 pieces),
  `strict`, `joint-level`; repair loop and mate-graph check (`puzzlegen verify`).
- Fabrication checks, tray/ring frame with dovetailed segments, STL with chamfers and
  engraved IDs, colour sets for multi-colour printing, `puzzlegen coupon`, JSON report.

Not yet: laser/plotter output (M5); Penrose P2, other Tile(a,b) shapes, curved Spectre
edges, 3MF, more connector kinds (M6).

## Try it

```bash
pip install -e ".[dev]"
puzzlegen coupon                                    # -> out/coupon.stl, print first
puzzlegen generate examples/voronoi_rect.toml       # -> STL plates, frame, SVG, report
puzzlegen preview examples/voronoi_rect.toml        # -> out/voronoi_rect_preview.svg
puzzlegen verify examples/swirl_grid.toml           # uniqueness + interlock summary
puzzlegen preview examples/penrose.toml             # Penrose rhombi with tabs
puzzlegen preview examples/penrose_hier.toml        # Penrose supertiles, hybrid tabs
puzzlegen preview examples/grow_shape.toml          # grown pieces, mostly shape-locked
puzzlegen generate examples/heart_hat.toml          # hats in a heart-shaped frame
puzzlegen preview examples/grid_square.toml --set tiling.grid.cell='"hex"'
python3 -m pytest -q
```
