# === CONTEXT ===
# Purpose:     Command-line entry point (USAGE 2): subcommands, --set overrides, exit codes.
# Decisions:   argparse, no click/typer dependency (DESIGN 10.2).
#              All USAGE subcommands exist from the start; those not implemented yet exit
#              with code 1 and name the milestone, so the CLI surface never changes shape.
#              M0: `preview` (SVG + report) and `list` work. `generate` also runs when
#              output.formats asks only for SVG; STL/3MF/DXF arrive in M1/M5.
# Invariants:  Exit codes: 0 ok, 1 config error, 2 checks failed, 3 internal error
#              (USAGE 2.3).
# Related:     config.load, pipeline.run, export2d.preview_svg, report.build.
# Tests:       tests/test_cli.py
# === END CONTEXT ===
from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path

from . import __version__
from .config import SCHEMA, ConfigError, load

NOT_YET = {"verify": "M2", "coupon": "M1"}
FORMAT_MILESTONE = {"stl": "M1", "3mf": "M6", "dxf": "M5"}


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="puzzlegen", description=__doc__)
    ap.add_argument("--version", action="version", version=f"puzzlegen {__version__}")
    sub = ap.add_subparsers(dest="command", required=True)
    for name, help_ in [("generate", "full pipeline and all outputs"),
                        ("preview", "SVG preview and report only"),
                        ("verify", "uniqueness and interlock check only")]:
        p = sub.add_parser(name, help=help_)
        p.add_argument("config", help="TOML configuration file")
        p.add_argument("--seed", type=int)
        p.add_argument("--set", dest="sets", action="append", default=[],
                       metavar="KEY=VALUE")
        p.add_argument("--out", help="output directory")
        p.add_argument("--allow-ambiguous", action="store_true")
        p.add_argument("-v", "--verbose", action="count", default=0)
    sub.add_parser("coupon", help="fit-test strip for clearance calibration")
    sub.add_parser("list", help="available tilings, groupings, connectors")
    return ap


def _list() -> None:
    from .tilings import REGISTRY
    print("tilings (implemented):", ", ".join(sorted(REGISTRY)))
    print("groupings (implemented): identity")
    print("connectors (implemented): tab, none")
    print(f"config keys: {len(SCHEMA)} (see USAGE.md section 3)")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "list":
        _list()
        return 0
    if args.command in NOT_YET:
        print(f"puzzlegen {args.command}: not implemented yet "
              f"(planned for milestone {NOT_YET[args.command]})", file=sys.stderr)
        return 1
    try:
        sets = list(args.sets)
        if args.seed is not None:
            sets.append(f"seed={args.seed}")
        if args.out:
            sets.append(f"out_dir='{args.out}'")   # TOML literal string: no escapes
        if args.allow_ambiguous:
            sets.append("uniqueness.allow_ambiguous=true")
        cfg = load(args.config, sets)
        formats = ["svg"] if args.command == "preview" else cfg["output.formats"]
        missing = [f for f in formats if f in FORMAT_MILESTONE]
        if missing:
            raise ConfigError(
                "output format(s) not implemented yet: " + ", ".join(
                    f"{f} ({FORMAT_MILESTONE[f]})" for f in missing)
                + '; use `preview` or --set output.formats=\'["svg"]\'')
        from . import export2d, pipeline, report
        res = pipeline.run(cfg)
    except ConfigError as e:
        print(f"puzzlegen: config error: {e}", file=sys.stderr)
        return 1
    except Exception:
        traceback.print_exc()
        return 3

    out = Path(cfg["out_dir"])
    out.mkdir(parents=True, exist_ok=True)
    name = cfg["name"]
    rep = report.build(res)
    (out / f"{name}_report.json").write_text(report.dumps(rep))
    if cfg["output.preview"] or "svg" in formats:
        (out / f"{name}_preview.svg").write_text(export2d.preview_svg(res))
    s = rep["stats"]
    print(f"{name}: {s['pieces']} pieces, {s['joints']} joints, "
          f"connectors {s['connectors']} -> {out}/")
    if not report.checks_ok(rep):
        print("puzzlegen: checks failed, see report 'checks'", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
