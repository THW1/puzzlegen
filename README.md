# puzzlegen

Generator for irregular interlocking puzzles (Voronoi, Penrose, hat/Spectre tilings)
for 3D printing (STL/3MF) and laser or plotter cutting (SVG/DXF), with an optional
matching frame and a verified unique solution.

- Design: [`DESIGN.md`](DESIGN.md)
- CLI and options (specification): [`USAGE.md`](USAGE.md)

## Status: milestone M0

Works now:
- Rectangle region; Voronoi tiling (blue-noise or uniform seeds, Lloyd relaxation) and
  jittered square/hex grids.
- Classic tab connectors with feasibility checks (min wall, min neck, end margin).
- `puzzlegen preview` writes an SVG preview and a JSON report; `puzzlegen list`.
- Partition check (pieces cover the region exactly, no overlaps) in every report.

Not yet: STL and frame (M1), cleanup of short joints and uniqueness (M2), Penrose (M3),
hat/Spectre (M4), laser output (M5). Options for later milestones are accepted by the
config parser but rejected with a message naming the milestone.

## Try it

```bash
pip install -e ".[dev]"
puzzlegen preview examples/voronoi_rect.toml        # -> out/voronoi_rect_preview.svg
puzzlegen preview examples/grid_square.toml --set tiling.grid.cell='"hex"'
python3 -m pytest -q
```
