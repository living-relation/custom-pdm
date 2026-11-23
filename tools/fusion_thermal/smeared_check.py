"""Our board model run three ways on one case: real copper, smeared copper, and the Fusion "lite" board (fusion2).

Why: the Fusion cross-check model (build_fusion_board.py "lite") can hold only a few bodies, so its copper is one mean
conductivity per sheet (net gaps, islands and narrow necks are gone), F.Cu + In1.Cu and In2.Cu + B.Cu are one sheet
each, and every via / plated-hole barrel outside the driver pads and J1 is spread evenly over the core. This runs
tools/thermal_a.py / thermal_board_b.py on the SAME case with those simplifications, so a Fusion vs model difference
splits into "the lite board" (lite vs real, our own solver) and "Fusion's solver" (Fusion vs lite).

  real     the board model as it is (the Elmer-chain reference, docs/heat-analysis.md)
  smeared  every copper layer replaced by its board-mean thickness over the whole outline (net gaps gone)
  lite     smeared + F.Cu / In1.Cu and In2.Cu / B.Cu merged + barrels outside the driver exposed pads and J1 spread
           evenly over the core (as build_fusion_board.py). Heat placement stays the model's own (the Fusion model
           lumps the copper I2R into 10 mm tiles: not repeated here).

usage (repo root, KiCad 9 python with numpy + scipy):
    python tools/fusion_thermal/smeared_check.py A|B CASE [--air fans] [--json OUT]
"""
import argparse
import json
import math
import os
import sys

import numpy as np
import scipy.sparse as sp

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import export_board as EB  # noqa: E402
import thermal_board_b as TB  # noqa: E402
import verify_copper as VC  # noqa: E402

_orig = TB.Thermal.matrix
G_MERGE = 1.0          # W/K per cell between the two layers of one lite sheet (FR-4 link is ~1e-4 W/K): merged


def _mean_th(self):
    return {n: (self.th[n] * float(self.cov[n][self.edge].mean()) if n in self.cov else v) for n, v in self.th.items()}


def _smeared(self, *args, **kw):
    cov, th = self.cov, self.th
    self.th = _mean_th(self)
    self.cov = {n: self.edge.copy() for n in cov}
    try:
        return _orig(self, *args, **kw)
    finally:
        self.cov, self.th = cov, th


def _rects(board):
    """Driver exposed-pad rectangles (any BTS700x on the board) and the J1 box + 0.5 mm, KiCad mm."""
    out = []
    for fp in board.GetFootprints():
        val = fp.GetValue()
        typ = next((t for t in ("BTS70012", "BTS7004", "BTS7008") if t in val), None)
        if typ and fp.GetReference().startswith("U"):
            x, y = VC.mm(fp.GetPosition().x), VC.mm(fp.GetPosition().y)
            w, h = TB.EP[typ]
            out.append((x - w / 2, y - h / 2, x + w / 2, y + h / 2))
    out.append(tuple(EB.fp_box(board, "J1", 0.5)))
    return out


def _lite(self, *args, **kw):
    g, L = self.g, VC.CU
    rects = _rects(self.board)

    def inside(x, y):
        return any(r[0] <= x <= r[2] and r[1] <= y <= r[3] for r in rects)

    holes = self.holes
    kept = [h for h in holes if inside(h[0], h[1])]
    spread = sum(TB.K_CU * math.pi * (d * 1e-3 + TB.TPLATE) * TB.TPLATE for (x, y, d, vl) in holes
                 if len(vl) >= 2 and not inside(x, y))            # W m / K, as export_board.py's core
    m_in = np.zeros((g.ny, g.nx), bool)
    for r in rects:
        m_in |= np.outer((g.yc >= r[1]) & (g.yc <= r[3]), (g.xc >= r[0]) & (g.xc <= r[2]))
    rest = self.edge & ~m_in
    A = (self.res * 1e-3) ** 2
    k_extra = spread / (rest.sum() * A)                            # W/mK added to the core outside the patches
    dz_core = self.diel.get(L[1], 0.0)
    cov, th = self.cov, self.th
    self.th = _mean_th(self)
    self.cov = {n: self.edge.copy() for n in cov}
    self.holes = kept
    try:
        M, gb = _orig(self, *args, **kw)
    finally:
        self.cov, self.th, self.holes = cov, th, holes
    rows, cols, vals = [], [], []
    for ka, kb, mask, gval in ((0, 1, self.edge, G_MERGE), (2, 3, self.edge, G_MERGE),
                               (1, 2, rest, k_extra * A / dz_core)):
        a, b = self.ids[ka][mask], self.ids[kb][mask]
        ok = (a >= 0) & (b >= 0)
        a, b = a[ok], b[ok]
        rows += [a, b, a, b]
        cols += [a, b, b, a]
        vals += [np.full(len(a), gval), np.full(len(a), gval), np.full(len(a), -gval), np.full(len(a), -gval)]
    X = sp.coo_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=M.shape)
    self.lite_info = dict(kept_holes=len(kept), spread_holes=len(holes) - len(kept), k_core=TB.K_FR4 + k_extra)
    return (M + X).tocsc(), gb


def spots(ref):
    out = {c["ref"]: c["t_board"] for c in ref["chips"]}
    out.update({k: v["t"] for k, v in ref.get("parts", {}).items()})
    out.update(U6=ref["t_sensor_u6"], laminate_max=ref["laminate_max"], t_sink=ref["t_sink"])
    return out


def run(which, case, air, mode):
    TB.Thermal.matrix = {"real": _orig, "smeared": _smeared, "lite": _lite}[mode]
    try:
        return spots(EB.main_board(which, case, air)["reference"])
    finally:
        TB.Thermal.matrix = _orig


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("board", choices=["A", "B"])
    ap.add_argument("case")
    ap.add_argument("--air", default="fans")
    ap.add_argument("--json")
    a = ap.parse_args()
    res = {m: run(a.board, a.case, a.air, m) for m in ("real", "smeared", "lite")}
    print(f"{a.board} {a.case} ({a.air}): spot  real  smeared  lite  (C)")
    for k in res["real"]:
        print(f"  {k:13} {res['real'][k]!s:>6} {res['smeared'].get(k)!s:>8} {res['lite'].get(k)!s:>6}")
    if a.json:
        with open(a.json, "w") as f:
            json.dump(dict(board=a.board, case=a.case, air=a.air, **res), f, indent=1)
    return 0


if __name__ == "__main__":
    np.seterr(all="ignore")
    sys.exit(main())
