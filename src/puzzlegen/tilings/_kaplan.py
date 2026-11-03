# === CONTEXT ===
# Purpose:     Substitution systems for the hat (H/T/P/F metatiles) and the Spectre
#              (9 tile types), returning every tile polygon together with its path in the
#              substitution tree (needed for hierarchical / metatile grouping).
# Decisions:   Vendored, not written from scratch: the rule tables (28 placement rules
#              for the hat, 9 supertile rules for the Spectre) come from Craig S. Kaplan's
#              reference implementations; getting them subtly wrong is easy. This file
#              is adapted from hat-amp 0.2.0 (Newton Winter, MIT), which ported Kaplan's
#              hatviz (BSD-3-Clause) and Spectre app. See THIRD_PARTY_NOTICES.md for the
#              licence texts and the caveat on the Spectre app's own licence.
#              Changes against hat-amp: geometry helpers inlined, tree walks also return
#              the child-index path of each tile, unused API (gold vertex, labelled
#              variants) dropped, and hats come from the H metatile, not from Kaplan's
#              intermediate patch (which holds overlapping scaffolding tiles).
#              The hat system places hats at scale 0.5 of HAT_OUTLINE (tests account for
#              it).
#              The rules are not trusted blindly: tests/test_hat_spectre.py checks that
#              every tile is congruent to the prototile, tiles do not overlap, and the
#              hat tiling contains reflected hats while the Spectre one contains none.
# Invariants:  Coordinates are unitless (hat: hex grid of unit edge; Spectre: unit
#              edge). Tree depth is uniform for hats (level + 1); Spectre leaves inside a
#              Mystic (Gamma) are one level deeper than the others.
# Related:     tilings/substitution.py (placement over the region, tags).
# Tests:       tests/test_hat_spectre.py
# === END CONTEXT ===
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

_HR3 = math.sqrt(3) / 2
IDENTITY = np.eye(3)


# ---------------------------------------------------------------- affine helpers
def pt(x: float, y: float) -> np.ndarray:
    return np.array([x, y], dtype=float)


def hex_pt(x: float, y: float) -> np.ndarray:
    return np.array([x + 0.5 * y, _HR3 * y], dtype=float)


def translation(tx: float, ty: float) -> np.ndarray:
    m = np.eye(3)
    m[0, 2], m[1, 2] = tx, ty
    return m


def rotation(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


def rot_about(p: np.ndarray, a: float) -> np.ndarray:
    return translation(p[0], p[1]) @ rotation(a) @ translation(-p[0], -p[1])


def apply_pt(t: np.ndarray, p: np.ndarray) -> np.ndarray:
    return t[:2, :2] @ p + t[:2, 2]


def from_flat(f) -> np.ndarray:
    a, b, tx, c, d, ty = f
    return np.array([[a, b, tx], [c, d, ty], [0.0, 0.0, 1.0]])


def _match_seg(p: np.ndarray, q: np.ndarray) -> np.ndarray:
    dx, dy = q[0] - p[0], q[1] - p[1]
    return np.array([[dx, p[1] - q[1], p[0]], [dy, dx, p[1]], [0.0, 0.0, 1.0]])


def match_two(p1, q1, p2, q2) -> np.ndarray:
    """Affine map taking segment p1->q1 onto p2->q2 (Kaplan's matchTwo)."""
    return _match_seg(p2, q2) @ np.linalg.inv(_match_seg(p1, q1))


def intersect(p1, q1, p2, q2) -> np.ndarray:
    d = (q2[1] - p2[1]) * (q1[0] - p1[0]) - (q2[0] - p2[0]) * (q1[1] - p1[1])
    ua = ((q2[0] - p2[0]) * (p1[1] - p2[1]) - (q2[1] - p2[1]) * (p1[0] - p2[0])) / d
    return pt(p1[0] + ua * (q1[0] - p1[0]), p1[1] + ua * (q1[1] - p1[1]))


def _walk(geom, T: np.ndarray, path: tuple, out: list) -> None:
    """Collect (polygon, path) for every leaf of a symbolic substitution tree."""
    if geom.leaf_shape is not None:
        out.append(((np.array(geom.leaf_shape) @ T[:2, :2].T) + T[:2, 2], path))
        return
    for k, (Tc, child) in enumerate(geom.children):
        _walk(child, T @ Tc, path + (k,), out)


# ---------------------------------------------------------------- hat
HAT_OUTLINE = [
    hex_pt(0, 0), hex_pt(-1, -1), hex_pt(0, -2), hex_pt(2, -2), hex_pt(2, -1),
    hex_pt(4, -2), hex_pt(5, -1), hex_pt(4, 0), hex_pt(3, 0), hex_pt(2, 2),
    hex_pt(0, 3), hex_pt(0, 2), hex_pt(-1, 2),
]


@dataclass
class _Node:
    shape: list = field(default_factory=list)       # metatile outline (or tile outline)
    children: list = field(default_factory=list)    # [(T, node)]
    leaf_shape: list | None = None                  # set for leaves (single tiles)
    quad: list = field(default_factory=list)        # Spectre key points

    def add(self, T: np.ndarray, node: "_Node") -> None:
        self.children.append((T, node))

    def child_pt(self, n: int, i: int) -> np.ndarray:
        T, g = self.children[n]
        return apply_pt(T, g.shape[i])

    def recentre(self) -> None:
        c = np.mean(self.shape, axis=0)
        self.shape = [p - c for p in self.shape]
        M = translation(-c[0], -c[1])
        self.children = [(M @ T, g) for T, g in self.children]


def _hat() -> _Node:
    return _Node(shape=list(HAT_OUTLINE), leaf_shape=list(HAT_OUTLINE))


def _hat_init() -> tuple[_Node, _Node, _Node, _Node]:
    hat = _hat()
    Ho = [pt(0, 0), pt(4, 0), pt(4.5, _HR3), pt(2.5, 5 * _HR3), pt(1.5, 5 * _HR3), pt(-0.5, _HR3)]
    H = _Node(shape=Ho)
    H.add(match_two(HAT_OUTLINE[5], HAT_OUTLINE[7], Ho[5], Ho[0]), hat)
    H.add(match_two(HAT_OUTLINE[9], HAT_OUTLINE[11], Ho[1], Ho[2]), hat)
    H.add(match_two(HAT_OUTLINE[5], HAT_OUTLINE[7], Ho[3], Ho[4]), hat)
    H.add(translation(2.5, _HR3) @ from_flat([-0.5, -_HR3, 0, _HR3, -0.5, 0])
          @ from_flat([0.5, 0, 0, 0, -0.5, 0]), hat)          # the reflected hat
    T = _Node(shape=[pt(0, 0), pt(3, 0), pt(1.5, 3 * _HR3)])
    T.add(from_flat([0.5, 0, 0.5, 0, 0.5, _HR3]), hat)
    two = translation(0, 2 * _HR3) @ from_flat([0.5, _HR3, 0, -_HR3, 0.5, 0]) \
        @ from_flat([0.5, 0, 0, 0, 0.5, 0])
    P = _Node(shape=[pt(0, 0), pt(4, 0), pt(3, 2 * _HR3), pt(-1, 2 * _HR3)])
    P.add(from_flat([0.5, 0, 1.5, 0, 0.5, _HR3]), hat)
    P.add(two, hat)
    F = _Node(shape=[pt(0, 0), pt(3, 0), pt(3.5, _HR3), pt(3, 2 * _HR3), pt(-1, 2 * _HR3)])
    F.add(from_flat([0.5, 0, 1.5, 0, 0.5, _HR3]), hat)
    F.add(two, hat)
    return H, T, P, F


_HAT_RULES = [
    ["H"], [0, 0, "P", 2], [1, 0, "H", 2], [2, 0, "P", 2], [3, 0, "H", 2],
    [4, 4, "P", 2], [0, 4, "F", 3], [2, 4, "F", 3], [4, 1, 3, 2, "F", 0],
    [8, 3, "H", 0], [9, 2, "P", 0], [10, 2, "H", 0], [11, 4, "P", 2],
    [12, 0, "H", 2], [13, 0, "F", 3], [14, 2, "F", 1], [15, 3, "H", 4],
    [8, 2, "F", 1], [17, 3, "H", 0], [18, 2, "P", 0], [19, 2, "H", 2],
    [20, 4, "F", 3], [20, 0, "P", 2], [22, 0, "H", 2], [23, 4, "F", 3],
    [23, 0, "F", 3], [16, 0, "P", 2], [9, 4, 0, 2, "T", 2], [4, 0, "F", 3],
]


def _hat_patch(H, T, P, F) -> _Node:
    shapes = {"H": H, "T": T, "P": P, "F": F}
    ret = _Node()
    for r in _HAT_RULES:
        if len(r) == 1:
            ret.add(IDENTITY.copy(), shapes[r[0]])
            continue
        if len(r) == 4:
            c, v, name, nv = r
            Tc, g = ret.children[c]
            p_pt = apply_pt(Tc, g.shape[(v + 1) % len(g.shape)])
            q_pt = apply_pt(Tc, g.shape[v])
        else:
            cp, vp, cq, vq, name, nv = r
            p_pt = ret.child_pt(cq, vq)
            q_pt = ret.child_pt(cp, vp)
        ns = shapes[name].shape
        ret.add(match_two(ns[nv], ns[(nv + 1) % len(ns)], p_pt, q_pt), shapes[name])
    return ret


def _hat_metatiles(patch: _Node) -> tuple[_Node, _Node, _Node, _Node]:
    bps1, bps2 = patch.child_pt(8, 2), patch.child_pt(21, 2)
    rbps = apply_pt(rot_about(bps1, -2 * math.pi / 3), bps2)
    p72, p252 = patch.child_pt(7, 2), patch.child_pt(25, 2)
    llc = intersect(bps1, rbps, patch.child_pt(6, 2), p72)
    w = patch.child_pt(6, 2) - llc
    Ho = [llc, bps1]
    w = apply_pt(rotation(-math.pi / 3), w)
    Ho.append(Ho[1] + w)
    Ho.append(patch.child_pt(14, 2))
    w = apply_pt(rotation(-math.pi / 3), w)
    Ho.append(Ho[3] - w)
    Ho.append(patch.child_pt(6, 2))

    def make(outline, idx):
        n = _Node(shape=outline)
        for i in idx:
            Tc, g = patch.children[i]
            n.add(Tc.copy(), g)
        return n
    H = make(Ho, [0, 9, 16, 27, 26, 6, 1, 8, 10, 15])
    P = make([p72, p72 + (bps1 - llc), bps1, llc], [7, 2, 3, 4, 28])
    F = make([bps2, patch.child_pt(24, 2), patch.child_pt(25, 0), p252, p252 + (llc - bps1)],
             [21, 20, 22, 23, 24, 25])
    aaa = Ho[2]
    bbb = Ho[1] + (Ho[4] - Ho[5])
    ccc = apply_pt(rot_about(bbb, -math.pi / 3), aaa)
    T = make([bbb, ccc, aaa], [11])
    for n in (H, P, F, T):
        n.recentre()
    return H, T, P, F


def hat_patch(level: int) -> list[tuple[np.ndarray, tuple]]:
    """All hats of the H metatile after `level` inflations, with their tree paths.
    Not Kaplan's intermediate patch: that one contains scaffolding tiles (children
    5, 12-14, 17-19) which belong to no extracted metatile and overlap real tiles
    (found by the overlap test; hat-amp's patch-level API returns them)."""
    H, T, P, F = _hat_init()
    for _ in range(level):
        H, T, P, F = _hat_metatiles(_hat_patch(H, T, P, F))
    out: list = []
    _walk(H, IDENTITY.copy(), (), out)
    return out


# ---------------------------------------------------------------- Spectre
SPECTRE_OUTLINE = [
    pt(0.0, 0.0), pt(1.0, 0.0), pt(1.5, -_HR3), pt(1.5 + _HR3, 0.5 - _HR3),
    pt(1.5 + _HR3, 1.5 - _HR3), pt(2.5 + _HR3, 1.5 - _HR3), pt(3.0 + _HR3, 1.5),
    pt(3.0, 2.0), pt(3.0 - _HR3, 1.5), pt(2.5 - _HR3, 1.5 + _HR3),
    pt(1.5 - _HR3, 1.5 + _HR3), pt(0.5 - _HR3, 1.5 + _HR3), pt(-_HR3, 1.5), pt(0.0, 1.0),
]
SPECTRE_KEYS = [SPECTRE_OUTLINE[3], SPECTRE_OUTLINE[5], SPECTRE_OUTLINE[7], SPECTRE_OUTLINE[11]]

_SPECTRE_RULES = {
    "Gamma":  ["Pi", "Delta", None, "Theta", "Sigma", "Xi", "Phi", "Gamma"],
    "Delta":  ["Xi", "Delta", "Xi", "Phi", "Sigma", "Pi", "Phi", "Gamma"],
    "Theta":  ["Psi", "Delta", "Pi", "Phi", "Sigma", "Pi", "Phi", "Gamma"],
    "Lambda": ["Psi", "Delta", "Xi", "Phi", "Sigma", "Pi", "Phi", "Gamma"],
    "Xi":     ["Psi", "Delta", "Pi", "Phi", "Sigma", "Psi", "Phi", "Gamma"],
    "Pi":     ["Psi", "Delta", "Xi", "Phi", "Sigma", "Psi", "Phi", "Gamma"],
    "Sigma":  ["Xi", "Delta", "Xi", "Phi", "Sigma", "Pi", "Lambda", "Gamma"],
    "Phi":    ["Psi", "Delta", "Psi", "Phi", "Sigma", "Pi", "Phi", "Gamma"],
    "Psi":    ["Psi", "Delta", "Psi", "Phi", "Sigma", "Psi", "Phi", "Gamma"],
}


def _spectre_base() -> dict[str, _Node]:
    def tile():
        return _Node(shape=list(SPECTRE_OUTLINE), leaf_shape=list(SPECTRE_OUTLINE),
                     quad=list(SPECTRE_KEYS))
    sys_ = {lab: tile() for lab in ("Delta", "Theta", "Lambda", "Xi", "Pi", "Sigma", "Phi", "Psi")}
    gamma = _Node(quad=list(SPECTRE_KEYS))            # Mystic: two Spectres at 30°
    gamma.add(IDENTITY.copy(), tile())
    v8 = SPECTRE_OUTLINE[8]
    gamma.add(translation(v8[0], v8[1]) @ rotation(math.pi / 6), tile())
    sys_["Gamma"] = gamma
    return sys_


def _spectre_super(sys_: dict[str, _Node]) -> dict[str, _Node]:
    quad = sys_["Delta"].quad
    R = from_flat([-1.0, 0, 0, 0, 1.0, 0])
    Ts, total, rot, tquad = [IDENTITY.copy()], 0.0, IDENTITY.copy(), list(quad)
    for ang, fi, ti in [(60, 3, 1), (0, 2, 0), (60, 3, 1), (60, 3, 1), (0, 2, 0),
                        (60, 3, 1), (-120, 3, 3)]:
        total += ang
        if ang:
            rot = rotation(math.radians(total))
            tquad = [apply_pt(rot, q) for q in quad]
        dest, src = apply_pt(Ts[-1], quad[fi]), tquad[ti]
        Ts.append(translation(dest[0] - src[0], dest[1] - src[1]) @ rot)
    Ts = [R @ T for T in Ts]
    squad = [apply_pt(Ts[6], quad[2]), apply_pt(Ts[5], quad[1]),
             apply_pt(Ts[3], quad[2]), apply_pt(Ts[0], quad[1])]
    out = {}
    for lab, subs in _SPECTRE_RULES.items():
        n = _Node(quad=squad)
        for k, sub in enumerate(subs):
            if sub is not None:
                n.add(Ts[k], sys_[sub])
        out[lab] = n
    return out


def spectre_patch(level: int) -> list[tuple[np.ndarray, tuple]]:
    """All Spectres of the Delta supertile after `level` inflations, with tree paths."""
    sys_ = _spectre_base()
    for _ in range(level):
        sys_ = _spectre_super(sys_)
    out: list = []
    _walk(sys_["Delta"], IDENTITY.copy(), (), out)
    return out
