import json

from puzzlegen.cli import main


def _cfg(tmp_path, body="[tiling]\ntarget_count = 25\n"):
    p = tmp_path / "c.toml"
    p.write_text('name = "t"\n' + body)
    return p


def test_preview_writes_svg_and_report(tmp_path):
    rc = main(["preview", str(_cfg(tmp_path)), "--out", str(tmp_path / "o")])
    assert rc == 0
    rep = json.loads((tmp_path / "o" / "t_report.json").read_text())
    assert rep["checks"]["partition"]["ok"]
    assert rep["stats"]["pieces"] == 25
    svg = (tmp_path / "o" / "t_preview.svg").read_text()
    assert svg.count("<path ") == 25


def test_output_is_reproducible(tmp_path):
    runs = []
    for _ in range(2):
        assert main(["preview", str(_cfg(tmp_path)), "--seed", "5",
                     "--out", str(tmp_path / "o")]) == 0
        runs.append([(tmp_path / "o" / f).read_bytes()
                     for f in ("t_report.json", "t_preview.svg")])
    assert runs[0] == runs[1]


def test_exit_codes(tmp_path):
    assert main(["preview", str(_cfg(tmp_path, "[tiling]\nkind = 'nope'\n"))]) == 1
    assert main(["generate", str(_cfg(tmp_path))]) == 1          # stl not implemented yet
    assert main(["generate", str(_cfg(tmp_path)), "--set", 'output.formats=["svg"]',
                 "--out", str(tmp_path / "g")]) == 0
    assert main(["coupon"]) == 1
    assert main(["list"]) == 0
