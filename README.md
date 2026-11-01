# puzzlegen

Generator for irregular interlocking puzzles (Voronoi, Penrose, hat/Spectre tilings)
for 3D printing (STL/3MF) and laser or plotter cutting (SVG/DXF), with an optional
matching frame and a verified unique solution.

- Design: [`DESIGN.md`](DESIGN.md)
- CLI and options (specification): [`USAGE.md`](USAGE.md)

## Status: milestone M1

Works now:
- Regions: rectangle, ellipse/circle, regular polygon, optional rounded corners.
- Tilings: Voronoi (blue-noise or uniform seeds, Lloyd relaxation), jittered square
  and hex grids.
- Classic tab connectors with feasibility checks (min wall, min neck, end margin).
- Fabrication: clearance offset, convex-corner rounding, neck/feature checks.
- Frame: tray or ring, rectangular or offset exterior, thumb notch, split into
  bed-sized segments joined by dovetails.
- STL output: pieces with stepped top/bottom chamfers and engraved IDs (bottom,
  mirrored), packed onto plates; one STL per frame segment.
- `puzzlegen generate`, `preview`, `coupon` (clearance fit test), `list`.
- Report: partition, fabrication, mesh and interlock checks (pairwise lock test).

Not yet: cleanup of short joints and slivers, uniqueness, `swirl` joints (M2);
Penrose and lock-aware grouping (M3); hat/Spectre (M4); laser output (M5).
Options for later milestones are accepted by the config parser but rejected with a
message naming the milestone.

Known gap until M2: joints shorter than `connectors.min_edge` stay straight (about 30 %
on Voronoi), and square grids clipped to round regions can leave slivers that fail
the fabrication check.

## Try it

```bash
pip install -e ".[dev]"
puzzlegen coupon                                    # -> out/coupon.stl, print first
puzzlegen generate examples/voronoi_rect.toml       # -> STL plates, frame, SVG, report
puzzlegen preview examples/voronoi_rect.toml        # -> out/voronoi_rect_preview.svg
puzzlegen preview examples/grid_square.toml --set tiling.grid.cell='"hex"'
python3 -m pytest -q
```
