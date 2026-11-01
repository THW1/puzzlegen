import re
from pathlib import Path

import pytest

from puzzlegen.config import SCHEMA, ConfigError, build, check_implemented, load, parse_value


def test_defaults_resolve():
    cfg = build({})
    assert cfg["tiling.kind"] == "voronoi"
    assert cfg["region.size"] == [200.0, 150.0]
    assert "region.path" not in cfg.values


def test_unknown_key_rejected(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text("[tiling]\nkindd = 'grid'\n")
    with pytest.raises(ConfigError, match="tiling.kindd"):
        load(p)


@pytest.mark.parametrize("raw, msg", [
    ({"tiling.kind": "square"}, "must be one of"),
    ({"tiling.target_count": 1}, ">= 2"),
    ({"tiling.target_count": 2.5}, "integer"),
    ({"connectors.head_size": [8, 5]}, "<= second"),
    ({"fabrication.top_edge": "bevel"}, "chamfer"),
    ({"tiling.target_count": 10, "tiling.target_size": 20.0}, "mutually exclusive"),
    ({"grouping.strategy": "hierarchy"}, "substitution tiling"),
    ({"tiling.hat.b": 0.0}, "periodically"),
    ({"region.shape": "svg"}, "region.path"),
])
def test_invalid_values(raw, msg):
    with pytest.raises(ConfigError, match=msg):
        build(raw)


def test_set_override_parsing(tmp_path):
    cfg = load(None, ["tiling.target_count=12", 'tiling.kind="grid"',
                      'output.formats=["svg"]', "region.size=[100, 80]"])
    assert cfg["tiling.target_count"] == 12
    assert cfg["tiling.kind"] == "grid"
    assert cfg["output.formats"] == ["svg"]
    assert cfg["region.size"] == [100.0, 80.0]
    assert parse_value("grid") == "grid"          # bare word -> string


def test_not_implemented_options_rejected():
    with pytest.raises(ConfigError, match="not implemented yet"):
        check_implemented(build({"tiling.kind": "hat"}))
    check_implemented(build({}))


def test_schema_matches_usage():
    """Every schema key appears in USAGE.md section 3 and vice versa (config.py invariant)."""
    usage = (Path(__file__).parents[1] / "USAGE.md").read_text()
    section = usage[usage.index("## 3. Configuration file"):usage.index("## 4. Outputs")]
    documented: set[str] = set()
    prefix = ""
    for line in section.splitlines():
        m = re.match(r"^#{3,4} .*`\[([\w.]+)\]`", line)
        if m:
            prefix = m.group(1) + "."
        elif line.startswith("### 3.1"):
            prefix = ""
        row = re.match(r"^\| `([\w`, ]+)` \|", line)
        if row:
            for k in re.findall(r"\w+", row.group(1)):
                documented.add(prefix + k)
    assert documented == set(SCHEMA)
