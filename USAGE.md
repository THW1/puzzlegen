# puzzlegen — Usage and Options Reference

> **Status: specification, partly implemented.** This document defines the command-line
> interface and configuration options. Options of milestones not reached yet are
> accepted by the parser but rejected with a message naming the milestone; the README
> lists what works today. Code and this document are updated together whenever an
> option changes. The design rationale is in
> [`DESIGN.md`](DESIGN.md); section numbers (§) below refer to it.

All lengths are in **mm**, all angles in **degrees**.

---

## 1. Quick start

```bash
pip install -e .                      # from a clone; Python ≥ 3.11
puzzlegen coupon --out out/           # print first: find your clearance
puzzlegen preview examples/voronoi_rect.toml      # SVG only, seconds
puzzlegen generate examples/voronoi_rect.toml     # STL + SVG + report
```

Minimal config (everything else uses defaults):

```toml
name = "first"
[tiling]
kind = "voronoi"
target_count = 30
```

This makes a 200 × 150 mm rectangle with about 30 Voronoi pieces, tab connectors and
a tray frame. Output goes to `out/first_*`.

---

## 2. Commands

| Command | Purpose |
|---------|---------|
| `puzzlegen generate CONFIG` | Full pipeline: geometry, checks, all requested outputs, report |
| `puzzlegen preview CONFIG` | Runs up to the verifier and writes only the SVG preview and report (no 3D) |
| `puzzlegen verify CONFIG` | Runs up to the verifier and prints the uniqueness, interlock and other check results; writes no files. Exit code 0 or 2 |
| `puzzlegen coupon` | Writes a fit-test strip: one head/socket pair per clearance value |
| `puzzlegen list` | Lists the available tilings, groupings and connector kinds |

### 2.1 Options for `generate`, `preview`, `verify`
| Flag | Description |
|------|-------------|
| `--seed N` | Override `seed` from the config |
| `--set KEY=VALUE` | Override any config value; repeatable. KEY is dotted: `--set tiling.target_count=200 --set frame.style=ring`. VALUE is parsed as TOML (`--set output.formats='["svg"]'`) |
| `--out DIR` | Output directory (overrides `out_dir`) |
| `--allow-ambiguous` | Same as `uniqueness.allow_ambiguous = true`. Outputs are always written; the exit code stays 2 if a check fails |
| `-v`, `-vv` | More log output (to stderr) |

### 2.2 Options for `coupon`
| Flag | Default | Description |
|------|---------|-------------|
| `--clearance A:B:STEP` | `0.10:0.40:0.05` | Clearance values to test |
| `--thickness T` | `4.0` | Coupon thickness |
| `--head-size S` | `6.0` | Head size of the test connector |
| `--mode fdm\|laser` | `fdm` | Laser mode writes SVG with `--kerf` values instead |
| `--out DIR` | `out` | Output directory |

How to use the coupon: print it, then pick the **smallest clearance that assembles by
hand without force and does not fall apart** when shaken. Put that value into
`fabrication.clearance`.

### 2.3 Exit codes
| Code | Meaning |
|------|---------|
| 0 | Success; all checks passed |
| 1 | Configuration error (unknown key, invalid value, conflicting options) |
| 2 | Checks failed: ambiguous connectors, unlocked joints where locks are required, printability limits, non-manifold mesh. The report lists the details |
| 3 | Internal error (bug) |

---

## 3. Configuration file

The configuration file is TOML. Unknown keys are an error (no silent typos). Every
value can be overridden with `--set`. The resolved configuration, including all
defaults, is written to the report.

### 3.1 Top level
| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `name` | string | `"puzzle"` | Prefix of all output files |
| `seed` | int | `0` | Random seed. Same seed + config + dependency versions give identical output |
| `out_dir` | path | `"out"` | Output directory |

### 3.2 `[region]` — puzzle outline (§3)
| Key | Type | Default | Allowed | Description |
|-----|------|---------|---------|-------------|
| `shape` | string | `"rect"` | `rect`, `circle`, `polygon`, `svg` | Outline type |
| `size` | [w, h] | `[200, 150]` | > 0 | Bounding size. For `circle`: `[d, d]`; unequal values give an ellipse. For `svg`: the box the path is fitted into, keeping its aspect ratio |
| `sides` | int | `6` | ≥ 3 | Number of sides for `polygon` |
| `corner_radius` | float | `0.0` | ≥ 0 | Rounds the corners of `rect` and `polygon` |
| `path` | path | — | `.svg` file | Required for `svg`. The first closed path is used; holes are kept |
| `border` | string | `"clip"` | `clip`, `natural`, `natural+clip` | `clip`: cut cells at the outline (smooth border). `natural`: keep whole cells whose centroid is inside (jagged border that matches the pieces). `natural+clip`: natural cavity inside a rectangular outer border |
| `margin` | float | auto | ≥ 0 | How far beyond the outline the tiling is generated. Auto = 2 × the mean piece size |

### 3.3 `[tiling]` — cell generator (§4)
| Key | Type | Default | Allowed | Description |
|-----|------|---------|---------|-------------|
| `kind` | string | `"voronoi"` | `voronoi`, `penrose`, `hat`, `spectre`, `grid` | Tiling generator |
| `target_count` | int | `100` | ≥ 2 | Wanted number of **pieces** (after grouping), ±10 % |
| `target_size` | float | — | > 0 | Alternative: wanted mean piece diameter. Mutually exclusive with `target_count` |
| `rotation` | float or `"random"` | `0` | — | Rotates the tiling relative to the region |

#### `[tiling.voronoi]`
| Key | Type | Default | Allowed | Description |
|-----|------|---------|---------|-------------|
| `seeds` | string | `"poisson"` | `poisson`, `uniform` | `poisson`: even sizes. `uniform`: chaotic sizes and sharper angles |
| `lloyd` | int | `1` | 0–10 | Lloyd relaxation iterations. 0 = raw, 3+ = honeycomb-like |
| `density_image` | path | — | PNG/JPG | Grey-scale map: dark areas get smaller pieces |
| `density_contrast` | float | `0.5` | 0–1 | How strongly the image modulates piece size (0 = ignore) |
| `size_spread` | float | `0.0` | 0–1 | Random piece-size variation via a weighted (power) diagram |

#### `[tiling.penrose]`
| Key | Type | Default | Allowed | Description |
|-----|------|---------|---------|-------------|
| `variant` | string | `"p3"` | `p3` (rhombs), `p2` (kites and darts) | Penrose tile set |
| `start` | string | `"sun"` | `sun`, `triangle` | Starting configuration before subdivision. `sun` gives fivefold symmetry at the centre |
| `levels` | int or `"auto"` | `"auto"` | ≥ 1 | Number of subdivision steps. Auto picks the value that matches the target count; `grouping.level` then sets the piece level |

#### `[tiling.hat]`
| Key | Type | Default | Allowed | Description |
|-----|------|---------|---------|-------------|
| `a`, `b` | float | `1.0`, `1.7320508` | a, b > 0 | Shape in the Tile(a, b) family: hat = (1, √3), turtle = (√3, 1). (1, 0) and (0, 1) are rejected because those tiles tile periodically |
| `levels` | int or `"auto"` | `"auto"` | ≥ 1 | Number of substitution steps |
| `flip_mode` | bool | `false` | — | `true`: no top marking, so reflected hats must be flipped by the player. Sets `uniqueness.flippable = true` |

#### `[tiling.spectre]`
| Key | Type | Default | Allowed | Description |
|-----|------|---------|---------|-------------|
| `levels` | int or `"auto"` | `"auto"` | ≥ 1 | Number of substitution steps |
| `curved_edges` | bool | `true` | — | Use the Spectre's curved edges. `false` gives the straight-edged Tile(1,1) polygon; the tiling is the same, but a flipped piece can then fit where its mirror image would, so `uniqueness.flippable` should stay on or the top must be marked |

#### `[tiling.grid]`
| Key | Type | Default | Allowed | Description |
|-----|------|---------|---------|-------------|
| `cell` | string | `"square"` | `square`, `hex` | Base grid |
| `jitter` | float | `0.15` | 0–0.4 | Random vertex displacement, as a fraction of cell size |

### 3.4 `[grouping]` — cells → pieces (§6.2)
| Key | Type | Default | Allowed | Description |
|-----|------|---------|---------|-------------|
| `strategy` | string | `"identity"` | `identity`, `hierarchy`, `grow`, `metatile` | `identity`: 1 cell = 1 piece. `hierarchy`: a piece = all tiles under one supertile (Penrose, hat, spectre only). `grow`: random region growing. `metatile`: hat H/T/P/F clusters |
| `level` | int or `"auto"` | `"auto"` | ≥ 1, < `tiling.*.levels` | `hierarchy` only: supertile level that becomes a piece |
| `cells_per_piece` | float or `"auto"` | `"auto"` | ≥ 1 | `grow` only: mean piece size in cells |
| `compactness` | float | `0.5` | 0–1 | `grow` only: 1 = round pieces, 0 = tentacle-like pieces (more shape lock, more fragile) |

Rules: `hierarchy` with `voronoi` or `grid` is a configuration error. `metatile`
requires `tiling.kind = "hat"`. In shape-locked modes (`hierarchy`, `grow`,
`metatile` with `connectors.kinds = ["none"]`) uniqueness is checked, not
constructed (§6.2).

### 3.5 `[cleanup]` (§6.3)
| Key | Type | Default | Allowed | Description |
|-----|------|---------|---------|-------------|
| `collinear_angle` | float | `5.0` | 0–30 | Consecutive edges between the same two pieces that bend less than this are merged into one curve |
| `collapse_edge` | float | `2.0` | ≥ 0 | Joints shorter than this are contracted to a point when no connectors are used (shape-locked modes). With connectors, `connectors.min_edge` is the threshold instead, so every remaining joint can carry one |
| `min_area_ratio` | float | `0.35` | 0–1 | Pieces smaller than this × median area are merged into a neighbour |
| `split_degree4` | bool | `false` | — | Split vertices where 4+ pieces meet into degree-3 vertices (for grids and Penrose; planned for M3). Contracting short joints creates such vertices on purpose |

### 3.6 `[connectors]` (§5)
| Key | Type | Default | Allowed | Description |
|-----|------|---------|---------|-------------|
| `kinds` | list | `["tab"]` | `tab`, `dovetail`, `tee`, `double`, `swirl`, `wave`, `none` | Connector kinds the optimiser may use. More kinds = more distinct signatures. `swirl` replaces the whole joint with an S-curve that locks by shape (connector-free look, DESIGN §5.4). `wave` and `none` do not lock |
| `head_size` | [min, max] | `[5.0, 8.0]` | > 0 | Range of head widths |
| `neck_ratio` | [min, max] | `[0.55, 0.75]` | 0.3–0.9 | Neck width / head width. Smaller = stronger lock, weaker neck |
| `min_edge` | float | `12.0` | > 0 | Joints shorter than this get no connector. Cleanup contracts them to a point, so the two pieces then touch only at a corner |
| `end_margin` | float | `3.0` | ≥ 0 | Minimum distance of a connector from the joint's end vertices |
| `min_wall` | float | `3.5` | ≥ `fabrication.min_neck` + `fabrication.clearance` | Minimum material between a connector and other edges of the piece. This wall is a link like a neck, so it must still be ≥ `min_neck` after the clearance offset |
| `double_above` | float | `45.0` | > `min_edge` | Joints longer than this may get a `double` connector, if `double` is in `kinds` |
| `lock_margin` | float | `20.0` | 0–90 | A joint locks if its tangent direction turns by at least 180° + this many degrees (DESIGN §5.4) |
| `require_lock` | bool | `false` | — | Fail the run (exit code 2) if any piece has no locking joint (`interlock.loose_pieces`) |
| `placement` | string | `"all"` | `all`, `unlocked` | `all`: connectors on every joint that fits one. `unlocked`: only on joints that do not already lock by shape (hybrid mode for grouped outlines) |

### 3.7 `[uniqueness]` (§7)
| Key | Type | Default | Allowed | Description |
|-----|------|---------|---------|-------------|
| `enabled` | bool | `true` | — | Run the optimiser and the verifier. `false` places connectors randomly and skips the check |
| `tolerance_k` | float | `3.0` | ≥ 1 | Connector shapes closer than `tolerance_k × clearance` (Hausdorff distance) count as interchangeable |
| `flippable` | bool | `false` | — | Also compare mirrored signatures. Needed if pieces carry no top marking |
| `max_iter` | int | `2000` | ≥ 0 | Maximum connector re-draws in the repair loop (at most 10 verification rounds) |
| `exact_solver` | string | `"auto"` | `auto`, `always`, `never` | Backtracking cross-check that counts assemblies (up to 2). `auto` runs it when there are ≤ 30 pieces |
| `allow_ambiguous` | bool | `false` | — | Kept for compatibility: outputs are always written, and the exit code is still 2 if ambiguous pairs remain |

### 3.8 `[fabrication]` (§5.3, §8)
| Key | Type | Default | Allowed | Description |
|-----|------|---------|---------|-------------|
| `mode` | string | `"fdm"` | `fdm`, `laser` | `laser` cuts each shared edge once; then `kerf` replaces `clearance` |
| `clearance` | float | `0.25` | 0–1 | Total gap between neighbouring pieces and to the frame. Calibrate with `coupon` |
| `kerf` | float | `0.15` | 0–1 | Laser/cutter kerf (laser mode) |
| `thickness` | float | `4.0` | > 0 | Piece thickness |
| `min_neck` | float | `3.0` | > 0 | Minimum connector neck width after offset; violations shrink or move the connector |
| `min_feature` | float | `1.6` | > 0 | Minimum material width anywhere |
| `corner_radius` | float | `0.5` | ≥ 0 | Rounding of convex piece corners |
| `top_edge` | string | `"chamfer:0.4"` | `none`, `chamfer:X`, `fillet:X` | Edge treatment on the top face only; also marks the top side |
| `bottom_chamfer` | float | `0.3` | ≥ 0 | Bottom-edge chamfer against elephant foot |
| `label` | string | `"bottom"` | `none`, `bottom` | Engrave the piece ID on the bottom face |
| `label_depth` | float | `0.4` | > 0 | Engraving depth |

### 3.9 `[frame]` (§3)
| Key | Type | Default | Allowed | Description |
|-----|------|---------|---------|-------------|
| `style` | string | `"tray"` | `none`, `tray`, `ring` | `tray`: wall + floor. `ring`: wall only |
| `wall` | float | `8.0` | > `min_feature` | Width of the frame wall |
| `floor` | float | `1.6` | > 0 | Floor thickness (`tray` only) |
| `height` | float or `"auto"` | `"auto"` | > 0 | Wall height above the floor. Auto = piece thickness |
| `exterior` | string | `"bbox"` | `bbox`, `offset` | `bbox`: rectangular outside. `offset`: outside follows the region outline |
| `connectors` | bool or `"auto"` | `"auto"` | — | Connectors between the frame and edge pieces. Auto = on for `natural` borders, off for `clip` |
| `max_segment` | float | `220.0` | > 0 | Split the frame into segments no longer than this, joined by dovetails. Should be less than the bed size |
| `thumb_notch` | bool | `true` | — | Adds a notch in the wall for removing the first piece |

### 3.10 `[output]` (§9)
| Key | Type | Default | Allowed | Description |
|-----|------|---------|---------|-------------|
| `formats` | list | `["stl", "svg"]` | `stl`, `3mf`, `svg`, `dxf` | Output formats |
| `bed` | [w, h] | `[256, 256]` | > 0 | Print bed size for plate packing |
| `plate_gap` | float | `3.0` | ≥ 0 | Gap between parts on a plate |
| `per_piece` | bool | `false` | — | Also write one STL per piece |
| `preview` | bool | `true` | — | Write a coloured SVG preview of the assembled puzzle |

---

## 4. Outputs

| File | Content |
|------|---------|
| `<name>_plate<k>.stl` / `.3mf` | Packed pieces for print bed k |
| `<name>_frame<k>.stl` | Frame segment k |
| `<name>_piece<id>.stl` | Single pieces (`output.per_piece`) |
| `<name>_cut.svg` / `.dxf` | Cut paths: layers `cut`, `frame`, `engrave` (laser mode: each shared edge once) |
| `<name>_preview.svg` | Assembled puzzle, coloured pieces, piece IDs |
| `<name>_report.json` | Resolved config, seed, versions, piece and joint statistics, connector histogram, min neck and feature, ambiguous pairs, unlocked joints, piece ancestry, plate assignment |

The report's `checks` block is the place to look when the exit code is 2.

---

## 5. Recipes

**Classic Voronoi in a tray (good first print):**
```toml
name = "voronoi_rect"
[region]
size = [180, 130]
[tiling]
kind = "voronoi"
target_count = 40
[tiling.voronoi]
lloyd = 2
```

**Penrose, pieces made of supertiles (jagged, shape-locking outlines):**
```toml
name = "penrose_hier"
[region]
shape = "circle"
size = [200, 200]
border = "natural"
[tiling]
kind = "penrose"
target_count = 60
[grouping]
strategy = "hierarchy"
[connectors]
kinds = ["tab", "tee"]      # extra locks on long joints; makes uniqueness constructive
```

**Hats in a heart-shaped frame with matching border:**
```toml
name = "heart_hat"
[region]
shape = "svg"
path = "heart.svg"
size = [200, 180]
border = "natural"
[tiling]
kind = "hat"
target_count = 120
[connectors]
kinds = ["tab", "tee", "dovetail"]
[frame]
connectors = true
```

**Spectre (all pieces the same handedness, no mirrored pieces):**
```toml
[tiling]
kind = "spectre"
target_count = 80
```

**Connector-free, locking by shape (`swirl` works since M2; lock-aware `grow` follows in M3):**
```toml
[tiling]
kind = "voronoi"
target_count = 20          # swirls need larger pieces
[connectors]
kinds = ["swirl"]          # organic S-shaped joints, no knobs
min_edge = 22.0            # swirls need joints >= ~22 mm for 3 mm throats
require_lock = true        # every piece must hook into a neighbour
```
or, with jagged outlines made of many small cells:
```toml
[tiling]
kind = "grid"
target_count = 60          # pieces
[tiling.grid]
cell = "hex"
[grouping]
strategy = "grow"
cells_per_piece = 12
compactness = 0.2          # low = more arms and overhangs
[connectors]
kinds = ["none"]           # pure shape lock; or kinds = ["tab"] with
require_lock = true        # placement = "unlocked": tabs only where shape does not lock
```

**Laser-cut plywood (3 mm):**
```toml
[fabrication]
mode = "laser"
kerf = 0.15
thickness = 3.0
[frame]
style = "ring"
[output]
formats = ["svg", "dxf"]
```

---

## 6. Troubleshooting

| Symptom (report / exit code 2) | What to change |
|--------------------------------|----------------|
| `ambiguous_pairs > 0` (joint-level) | Add connector kinds (`["tab", "swirl"]`), widen `head_size`, raise `max_iter`, or lower `target_count` |
| `guarantee = "joint-level"` instead of `"strict"` | Normal above ~25 pieces (limited number of distinguishable tab shapes, DESIGN §7.2). For `strict`: fewer pieces, wider `head_size`, or mixed kinds |
| Many `skipped_infeasible` with `swirl` | Joints too short: raise `connectors.min_edge` to about 22 and lower `target_count` |
| Joint-level ambiguity on `grid` tilings | Grid joints have almost equal lengths, so more of them are comparable: raise `tiling.grid.jitter` (0.3 fixed all stress-test cases) or widen `head_size` |
| `mate_graph_components > 1`, many `skipped_infeasible` | Pieces too small for tabs (below ~18 mm): lower `target_count`, or reduce `head_size`, `min_wall` and `min_neck` together |
| `interlock.unlocked > 0` | Some joints have no connector (see `connectors.skipped_infeasible`): lower `min_wall`/`head_size` or raise `min_edge`; for shape-locked groupings, add `tab` to `kinds` |
| `min_neck` violations | Larger pieces (`target_count` ↓), smaller `clearance`, or larger `head_size` |
| Many slivers along the border | `border = "natural"` or raise `cleanup.min_area_ratio` |
| Pieces too loose or too tight | Re-run `coupon` and adjust `clearance` |
| Frame does not fit the bed | Lower `frame.max_segment` |
