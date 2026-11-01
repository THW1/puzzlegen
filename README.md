# puzzlegen

Generator for irregular interlocking puzzles (Voronoi, Penrose, hat/Spectre tilings)
for 3D printing (STL/3MF) and laser or plotter cutting (SVG/DXF), with an optional
matching frame and a verified unique solution.

- Design: [`DESIGN.md`](DESIGN.md)
- CLI and options (specification): [`USAGE.md`](USAGE.md)

## Status: milestone M3

Works now:
- Regions: rectangle, ellipse/circle, regular polygon, optional rounded corners.
- Tilings: Voronoi (blue-noise or uniform seeds, Lloyd relaxation), jittered square
  and hex grids, **Penrose P3** (rhombi; subdivision rules verified geometrically).
- Grouping: `hierarchy` (Penrose supertiles as pieces) and `grow` (pieces grown from
  small cells, with a local search that makes joints lock by shape).
- Cleanup: sliver and fragile-piece merging, chain joints for bent edges,
  contraction of joints too short for a connector.
- Connectors: classic tabs and `swirl` joints; hybrid placement (`unlocked`) puts
  connectors only where the shape does not lock already.
- Uniqueness check with two guarantee levels (strict / joint-level), repair loop,
  mate-graph check and an exact solver for small puzzles (`puzzlegen verify`).
- Fabrication checks, tray/ring frame with dovetailed segments, STL with chamfers and
  engraved IDs, `puzzlegen coupon`, JSON report with all checks.

Not yet: hat/Spectre and `metatile` grouping, SVG regions, natural borders (M4); laser
output (M5); Penrose P2 kites/darts, 3MF, more connector kinds (M6).

Uniqueness in short: small puzzles (about 25 pieces or fewer) usually reach the
`strict` guarantee; larger ones reach `joint-level` (DESIGN §7.2). 100-piece Penrose
puzzles passed all checks in 7 of 8 seeds.

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
puzzlegen preview examples/grid_square.toml --set tiling.grid.cell='"hex"'
python3 -m pytest -q
```
