# === CONTEXT ===
# Purpose:     Load, validate and resolve the TOML configuration. The schema here IS the
#              option contract documented in USAGE.md section 3.
# Decisions:   One declarative SCHEMA table (key -> default + validator) instead of one
#              dataclass per section: the table mirrors the USAGE tables 1:1, so keeping
#              them in sync is a line-by-line comparison.
#              The full USAGE schema is accepted from the start; options whose
#              implementation arrives in a later milestone are rejected by
#              `check_implemented` with a clear message, not silently ignored.
#              Unknown keys are an error (USAGE 3: no silent typos).
# Invariants:  Every key and default in SCHEMA matches USAGE.md section 3. Change both
#              together.
# Related:     cli.py (--set overrides via `apply_override`); report.py writes
#              `Config.as_dict()` into the report.
# Tests:       tests/test_config.py
# === END CONTEXT ===
from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable


class ConfigError(ValueError):
    """Invalid configuration (CLI exit code 1)."""


# ---------------------------------------------------------------- validators
def _num(kind: type, lo: float | None = None, hi: float | None = None,
         lo_open: bool = False) -> Callable[[str, Any], Any]:
    def check(key: str, v: Any) -> Any:
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ConfigError(f"{key}: expected a number, got {v!r}")
        if kind is int and not isinstance(v, int):
            raise ConfigError(f"{key}: expected an integer, got {v!r}")
        v = kind(v)
        if lo is not None and (v < lo or (lo_open and v == lo)):
            raise ConfigError(f"{key}: must be {'>' if lo_open else '>='} {lo}, got {v}")
        if hi is not None and v > hi:
            raise ConfigError(f"{key}: must be <= {hi}, got {v}")
        return v
    return check


def _choice(*options: str) -> Callable[[str, Any], Any]:
    def check(key: str, v: Any) -> Any:
        if v not in options:
            raise ConfigError(f"{key}: must be one of {', '.join(options)}; got {v!r}")
        return v
    return check


def _bool(key: str, v: Any) -> bool:
    if not isinstance(v, bool):
        raise ConfigError(f"{key}: expected true or false, got {v!r}")
    return v


def _str(key: str, v: Any) -> str:
    if not isinstance(v, str) or not v:
        raise ConfigError(f"{key}: expected a non-empty string, got {v!r}")
    return v


def _pair(lo: float = 0.0, ordered: bool = False) -> Callable[[str, Any], Any]:
    def check(key: str, v: Any) -> Any:
        if not (isinstance(v, list) and len(v) == 2):
            raise ConfigError(f"{key}: expected a list of two numbers, got {v!r}")
        a, b = (_num(float, lo, lo_open=True)(key, x) for x in v)
        if ordered and a > b:
            raise ConfigError(f"{key}: first value must be <= second, got {v!r}")
        return [a, b]
    return check


def _list_of(*options: str) -> Callable[[str, Any], Any]:
    def check(key: str, v: Any) -> Any:
        if not isinstance(v, list) or not v:
            raise ConfigError(f"{key}: expected a non-empty list, got {v!r}")
        for x in v:
            _choice(*options)(key, x)
        return list(dict.fromkeys(v))
    return check


def _auto_or(inner: Callable[[str, Any], Any]) -> Callable[[str, Any], Any]:
    def check(key: str, v: Any) -> Any:
        return v if v == "auto" else inner(key, v)
    return check


def _float_or_random(key: str, v: Any) -> Any:
    return v if v == "random" else _num(float)(key, v)


_EDGE_RE = re.compile(r"^(none|(chamfer|fillet):\d+(\.\d+)?)$")


def _edge(key: str, v: Any) -> str:
    if not isinstance(v, str) or not _EDGE_RE.match(v):
        raise ConfigError(f"{key}: expected none, chamfer:X or fillet:X; got {v!r}")
    return v


_OPTIONAL = object()   # default for keys with no default (e.g. region.path)

# ---------------------------------------------------------------- schema
# key -> (default, validator). Mirrors USAGE.md section 3, in the same order.
SCHEMA: dict[str, tuple[Any, Callable[[str, Any], Any]]] = {
    "name": ("puzzle", _str),
    "seed": (0, _num(int, 0)),
    "out_dir": ("out", _str),

    "region.shape": ("rect", _choice("rect", "circle", "polygon", "svg")),
    "region.size": ([200.0, 150.0], _pair()),
    "region.sides": (6, _num(int, 3)),
    "region.corner_radius": (0.0, _num(float, 0)),
    "region.path": (_OPTIONAL, _str),
    "region.border": ("clip", _choice("clip", "natural", "natural+clip")),
    "region.margin": ("auto", _auto_or(_num(float, 0))),

    "tiling.kind": ("voronoi", _choice("voronoi", "penrose", "hat", "spectre", "grid")),
    "tiling.target_count": (100, _num(int, 2)),
    "tiling.target_size": (_OPTIONAL, _num(float, 0, lo_open=True)),
    "tiling.rotation": (0.0, _float_or_random),
    "tiling.voronoi.seeds": ("poisson", _choice("poisson", "uniform")),
    "tiling.voronoi.lloyd": (1, _num(int, 0, 10)),
    "tiling.voronoi.density_image": (_OPTIONAL, _str),
    "tiling.voronoi.density_contrast": (0.5, _num(float, 0, 1)),
    "tiling.voronoi.size_spread": (0.0, _num(float, 0, 1)),
    "tiling.penrose.variant": ("p3", _choice("p3", "p2")),
    "tiling.penrose.start": ("sun", _choice("sun", "triangle")),
    "tiling.penrose.levels": ("auto", _auto_or(_num(int, 1))),
    "tiling.hat.a": (1.0, _num(float, 0)),
    "tiling.hat.b": (1.7320508, _num(float, 0)),
    "tiling.hat.levels": ("auto", _auto_or(_num(int, 1))),
    "tiling.hat.flip_mode": (False, _bool),
    "tiling.spectre.levels": ("auto", _auto_or(_num(int, 1))),
    "tiling.spectre.curved_edges": (True, _bool),
    "tiling.grid.cell": ("square", _choice("square", "hex")),
    "tiling.grid.jitter": (0.15, _num(float, 0, 0.4)),

    "grouping.strategy": ("identity", _choice("identity", "hierarchy", "grow", "metatile")),
    "grouping.level": ("auto", _auto_or(_num(int, 1))),
    "grouping.cells_per_piece": ("auto", _auto_or(_num(float, 1))),
    "grouping.compactness": (0.5, _num(float, 0, 1)),

    "cleanup.collinear_angle": (5.0, _num(float, 0, 30)),
    "cleanup.collapse_edge": (2.0, _num(float, 0)),
    "cleanup.min_area_ratio": (0.35, _num(float, 0, 1)),
    "cleanup.split_degree4": (False, _bool),

    "connectors.kinds": (["tab"], _list_of("tab", "dovetail", "tee", "double", "swirl",
                                            "wave", "none")),
    "connectors.head_size": ([5.0, 8.0], _pair(ordered=True)),
    "connectors.neck_ratio": ([0.55, 0.75], _pair(ordered=True)),
    "connectors.min_edge": (12.0, _num(float, 0, lo_open=True)),
    "connectors.end_margin": (3.0, _num(float, 0)),
    "connectors.min_wall": (3.5, _num(float, 0)),
    "connectors.double_above": (45.0, _num(float, 0, lo_open=True)),
    "connectors.lock_margin": (20.0, _num(float, 0, 90)),
    "connectors.require_lock": (False, _bool),
    "connectors.placement": ("all", _choice("all", "unlocked")),

    "uniqueness.enabled": (True, _bool),
    "uniqueness.tolerance_k": (3.0, _num(float, 1)),
    "uniqueness.flippable": (False, _bool),
    "uniqueness.max_iter": (2000, _num(int, 0)),
    "uniqueness.exact_solver": ("auto", _choice("auto", "always", "never")),
    "uniqueness.allow_ambiguous": (False, _bool),

    "fabrication.mode": ("fdm", _choice("fdm", "laser")),
    "fabrication.clearance": (0.25, _num(float, 0, 1)),
    "fabrication.kerf": (0.15, _num(float, 0, 1)),
    "fabrication.thickness": (4.0, _num(float, 0, lo_open=True)),
    "fabrication.min_neck": (3.0, _num(float, 0, lo_open=True)),
    "fabrication.min_feature": (1.6, _num(float, 0, lo_open=True)),
    "fabrication.corner_radius": (0.5, _num(float, 0)),
    "fabrication.top_edge": ("chamfer:0.4", _edge),
    "fabrication.bottom_chamfer": (0.3, _num(float, 0)),
    "fabrication.label": ("bottom", _choice("none", "bottom")),
    "fabrication.label_depth": (0.4, _num(float, 0, lo_open=True)),

    "frame.style": ("tray", _choice("none", "tray", "ring")),
    "frame.wall": (8.0, _num(float, 0, lo_open=True)),
    "frame.floor": (1.6, _num(float, 0, lo_open=True)),
    "frame.height": ("auto", _auto_or(_num(float, 0, lo_open=True))),
    "frame.exterior": ("bbox", _choice("bbox", "offset")),
    "frame.connectors": ("auto", _auto_or(_bool)),
    "frame.max_segment": (220.0, _num(float, 0, lo_open=True)),
    "frame.thumb_notch": (True, _bool),

    "output.formats": (["stl", "svg"], _list_of("stl", "3mf", "svg", "dxf")),
    "output.bed": ([256.0, 256.0], _pair()),
    "output.plate_gap": (3.0, _num(float, 0)),
    "output.per_piece": (False, _bool),
    "output.preview": (True, _bool),
    "output.color_sets": (1, _num(int, 1, 16)),
}

_SECTIONS = {k.rsplit(".", 1)[0] for k in SCHEMA if "." in k}


# ---------------------------------------------------------------- loading
def _flatten(d: dict, prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in d.items():
        key = f"{prefix}{k}"
        # A dict is a section only if the schema has that section; otherwise it is a
        # value (and then rejected as unknown or wrongly typed).
        if isinstance(v, dict) and key in _SECTIONS:
            out.update(_flatten(v, key + "."))
        else:
            out[key] = v
    return out


@dataclass(frozen=True)
class Config:
    values: dict[str, Any]

    def __getitem__(self, key: str) -> Any:
        return self.values[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)

    def as_dict(self) -> dict[str, Any]:
        """Nested dict of all resolved values (for the report)."""
        out: dict[str, Any] = {}
        for key, v in self.values.items():
            node = out
            *parts, last = key.split(".")
            for p in parts:
                node = node.setdefault(p, {})
            node[last] = v
        return out

    def ns(self) -> SimpleNamespace:
        """Attribute view: cfg.ns().tiling.voronoi.lloyd."""
        def conv(d: Any) -> Any:
            return SimpleNamespace(**{k: conv(v) for k, v in d.items()}) \
                if isinstance(d, dict) else d
        return conv(self.as_dict())


def parse_value(text: str) -> Any:
    """Parse a --set VALUE as TOML; bare words fall back to strings."""
    try:
        return tomllib.loads(f"v = {text}")["v"]
    except tomllib.TOMLDecodeError:
        return text


def apply_override(raw: dict[str, Any], assignment: str) -> None:
    if "=" not in assignment:
        raise ConfigError(f"--set expects KEY=VALUE, got {assignment!r}")
    key, text = assignment.split("=", 1)
    key = key.strip()
    if key not in SCHEMA:
        raise ConfigError(f"--set: unknown key {key!r}")
    raw[key] = parse_value(text.strip())


def build(raw_flat: dict[str, Any]) -> Config:
    unknown = sorted(set(raw_flat) - set(SCHEMA))
    if unknown:
        raise ConfigError(f"unknown key(s): {', '.join(unknown)}")
    values: dict[str, Any] = {}
    for key, (default, check) in SCHEMA.items():
        if key in raw_flat:
            values[key] = check(key, raw_flat[key])
        elif default is not _OPTIONAL:
            values[key] = default
    if "tiling.target_size" in raw_flat and "tiling.target_count" in raw_flat:
        raise ConfigError("tiling.target_count and tiling.target_size are mutually exclusive")
    _cross_check(values)
    return Config(values)


def load(path: str | Path | None, overrides: list[str] = ()) -> Config:
    raw: dict[str, Any] = {}
    if path is not None:
        try:
            with open(path, "rb") as fh:
                raw = _flatten(tomllib.load(fh))
        except tomllib.TOMLDecodeError as e:
            raise ConfigError(f"{path}: {e}") from None
        except OSError as e:
            raise ConfigError(f"cannot read config: {e}") from None
    for a in overrides:
        apply_override(raw, a)
    return build(raw)


def _cross_check(v: dict[str, Any]) -> None:
    """Rules between options (USAGE 3.3, 3.4, 3.6)."""
    if v["region.shape"] == "svg" and "region.path" not in v:
        raise ConfigError("region.path is required for region.shape = \"svg\"")
    if v["grouping.strategy"] == "hierarchy" and v["tiling.kind"] in ("voronoi", "grid"):
        raise ConfigError("grouping.strategy = \"hierarchy\" needs a substitution tiling "
                          "(penrose, hat, spectre)")
    if v["grouping.strategy"] == "metatile" and v["tiling.kind"] != "hat":
        raise ConfigError("grouping.strategy = \"metatile\" requires tiling.kind = \"hat\"")
    if v["connectors.double_above"] <= v["connectors.min_edge"]:
        raise ConfigError("connectors.double_above must be > connectors.min_edge")
    # The wall between a socket and another edge is a link like a neck: after the
    # clearance offset it must still be >= min_neck (fabricate.py neck check).
    if v["connectors.min_wall"] < v["fabrication.min_neck"] + v["fabrication.clearance"]:
        raise ConfigError("connectors.min_wall must be >= fabrication.min_neck + "
                          "fabrication.clearance")
    a, b = v["tiling.hat.a"], v["tiling.hat.b"]
    if a == 0 or b == 0:
        raise ConfigError("tiling.hat: Tile(1,0) and Tile(0,1) tile periodically; "
                          "a and b must both be > 0")


# ---------------------------------------------------------------- milestones
# (key, allowed values or predicate, milestone that adds the rest)
_IMPLEMENTED: list[tuple[str, Callable[[Any], bool], str]] = [
    ("region.shape", lambda x: x != "svg", "M4"),
    ("region.border", lambda x: x == "clip", "M4"),
    ("tiling.kind", lambda x: x in ("voronoi", "grid", "penrose"), "M4"),
    ("tiling.penrose.variant", lambda x: x == "p3", "M6"),
    ("tiling.rotation", lambda x: x == 0, "M6"),
    ("tiling.voronoi.size_spread", lambda x: x == 0, "M6"),
    ("grouping.strategy", lambda x: x != "metatile", "M4"),
    ("connectors.kinds", lambda x: set(x) <= {"tab", "swirl", "none"}, "M6"),
    ("fabrication.mode", lambda x: x == "fdm", "M5"),
    ("cleanup.split_degree4", lambda x: not x, "M6"),
]


def check_implemented(cfg: Config) -> None:
    """Reject options that are valid per USAGE but not implemented yet."""
    for key, ok, milestone in _IMPLEMENTED:
        if not ok(cfg[key]):
            raise ConfigError(f"{key} = {cfg[key]!r} is not implemented yet "
                              f"(planned for milestone {milestone})")
    if cfg.get("tiling.voronoi.density_image") is not None:
        raise ConfigError("tiling.voronoi.density_image is not implemented yet "
                          "(planned for milestone M6)")


def piece_target(cfg: Config) -> int:
    """Target piece count, from target_count or target_size (USAGE 3.3)."""
    size = cfg.get("tiling.target_size")
    if size is None:
        return cfg["tiling.target_count"]
    w, h = cfg["region.size"]
    return max(2, round(w * h / (size * size)))
