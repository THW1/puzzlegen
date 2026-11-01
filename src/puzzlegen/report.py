# === CONTEXT ===
# Purpose:     Build <name>_report.json (DESIGN 9.3, USAGE 4). Every check result goes
#              here, never only to stdout.
# Decisions:   Floats rounded to 6 decimals and keys sorted, so reports diff cleanly and
#              are byte-stable for a given config + seed (G6).
# Related:     pipeline.Result; the `checks` block decides the CLI exit code (cli.py).
# === END CONTEXT ===
from __future__ import annotations

import json
import platform

import numpy as np
import scipy
import shapely

from . import __version__, fabricate
from .pipeline import Result


def _round(x):
    if isinstance(x, float):
        return round(x, 6)
    if isinstance(x, dict):
        return {k: _round(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_round(v) for v in x]
    return x


def build(res: Result) -> dict:
    areas = np.array([p.area for p in res.pieces])
    m = res.pmap
    interior = [c for c in range(len(m.curve_he)) if m.is_interior_curve(c)]
    lengths = np.array([np.linalg.norm(m.verts[m.origin[m.curve_he[c]]]
                                       - m.verts[m.origin[m.twin[m.curve_he[c]]]])
                        for c in interior])
    tabs = [m.curve_spec[c] for c in interior
            if m.curve_spec[c] is not None and m.curve_spec[c].kind == "tab"]
    report = {
        "version": __version__,
        "versions": {"python": platform.python_version(), "numpy": np.__version__,
                     "scipy": scipy.__version__, "shapely": shapely.__version__},
        "config": res.cfg.as_dict(),
        "stats": {
            "pieces": len(res.pieces),
            "piece_area": {"min": float(areas.min()), "median": float(np.median(areas)),
                           "max": float(areas.max())},
            "joints": len(interior),
            "joint_length": {"min": float(lengths.min()), "median": float(np.median(lengths)),
                             "max": float(lengths.max())},
            "connectors": dict(sorted(res.connector_stats.items())),
            "cleanup": res.cleanup,
            "min_tab_neck_width": min((t.neck_width for t in tabs), default=None),
        },
        "checks": {"partition": res.partition,
                   "fabrication": fabricate.check_result(res.fab),
                   "uniqueness": res.uniqueness,
                   "interlock": {**res.interlock,
                                 "ok": not (res.cfg["connectors.require_lock"]
                                            and res.interlock["loose_pieces"])}},
    }
    if res.frame is not None:
        report["stats"]["frame_segments"] = len(res.frame.segments)
    return _round(report)


def dumps(report: dict) -> str:
    return json.dumps(report, indent=2, sort_keys=True) + "\n"


def checks_ok(report: dict) -> bool:
    return all(v.get("ok", True) for v in report["checks"].values())


def add_export(report: dict, export_info: dict) -> None:
    report["checks"]["mesh"] = _round(export_info)
