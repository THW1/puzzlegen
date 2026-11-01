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
    assert svg.count('<path id="p') == 25


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
    assert main(["generate", str(_cfg(tmp_path)), "--set", 'output.formats=["dxf"]']) == 1
    assert main(["verify", str(_cfg(tmp_path))]) == 0
    assert main(["coupon", "--clearance", "0.3:0.1:0.05"]) == 1
    assert main(["list"]) == 0


def test_generate_writes_stl(tmp_path):
    out = tmp_path / "g"
    assert main(["generate", str(_cfg(tmp_path)), "--out", str(out),
                 "--set", "frame.max_segment=120"]) == 0
    rep = json.loads((out / "t_report.json").read_text())
    assert rep["checks"]["mesh"]["ok"] and rep["checks"]["fabrication"]["ok"]
    assert rep["checks"]["mesh"]["frame_segments"] == 4
    assert (out / "t_plate1.stl").stat().st_size > 84
    assert len(list(out.glob("t_frame*.stl"))) == 4


def test_require_lock_fails_on_loose_pieces(tmp_path):
    body = "[tiling]\ntarget_count = 25\n[connectors]\nkinds = ['none']\nrequire_lock = true\n"
    assert main(["preview", str(_cfg(tmp_path, body)), "--out", str(tmp_path / "o")]) == 2


def test_coupon(tmp_path):
    assert main(["coupon", "--out", str(tmp_path), "--clearance", "0.15:0.25:0.05"]) == 0
    assert (tmp_path / "coupon.stl").stat().st_size > 84
