# puzzlegen

Generator for irregular interlocking puzzles (Voronoi, Penrose, hat/Spectre tilings)
for 3D printing (STL/3MF) and laser or plotter cutting (SVG/DXF), with an optional
matching frame and a verified unique solution.

- Design: [`DESIGN.md`](DESIGN.md)
- CLI and options (specification): [`USAGE.md`](USAGE.md)

## Status: milestone M2

Works now:
- Regions: rectangle, ellipse/circle, regular polygon, optional rounded corners.
- Tilings: Voronoi (blue-noise or uniform seeds, Lloyd relaxation), jittered square
  and hex grids.
- Cleanup: sliver merging, straightening, contraction of joints too short for a
  connector (every remaining joint carries one).
- Connectors: classic tabs (wide shape space, chosen to be as distinct as possible)
  and `swirl` joints (organic S-curves that lock by shape, no knobs).
- Uniqueness check with two guarantee levels (strict / joint-level), repair loop,
  mate-graph check and an exact solver for small puzzles (`puzzlegen verify`).
- Fabrication: clearance offset, convex-corner rounding, neck/feature checks.
- Frame: tray or ring, rectangular or offset exterior, thumb notch, split into
  bed-sized segments joined by dovetails.
- STL output: pieces with stepped chamfers and engraved IDs, packed onto plates; one
  STL per frame segment. `puzzlegen coupon` for clearance calibration.
- Report: partition, fabrication, uniqueness, interlock and mesh checks.

Not yet: Penrose and lock-aware grouping (M3), hat/Spectre (M4), laser output (M5).
Options for later milestones are accepted by the config parser but rejected with a
message naming the milestone.

Uniqueness in short: small puzzles (about 25 pieces or fewer) usually reach the
`strict` guarantee, and the exact solver confirms one solution. Larger puzzles reach
`joint-level`, because only about 60 tab shapes are distinguishable at the default
tolerance (DESIGN §7.2).

## Try it

```bash
pip install -e ".[dev]"
puzzlegen coupon                                    # -> out/coupon.stl, print first
puzzlegen generate examples/voronoi_rect.toml       # -> STL plates, frame, SVG, report
puzzlegen preview examples/voronoi_rect.toml        # -> out/voronoi_rect_preview.svg
puzzlegen verify examples/swirl_grid.toml           # uniqueness + interlock summary
puzzlegen preview examples/grid_square.toml --set tiling.grid.cell='"hex"'
python3 -m pytest -q
```
