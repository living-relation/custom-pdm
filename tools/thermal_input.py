"""Input board steady heat model: its own resistor / clamp losses on its real copper, in the air under the lid.

usage (repo root; KiCad 9 python with numpy + scipy + matplotlib):
    python tools/thermal_input.py [--air 60] [--vin 16] [--res 0.25] [--plots DIR] [--json FILE]
tests: python tools/test_thermal_models.py (InputBoard)

The input board (hardware/input-board/input-board.kicad_pcb, 2 layers, 1 oz, three fitted: one per main board) carries no
load current and sits on the PA12 input deck under the lid, not on the heat sink. Heat model:
  * One in-plane sheet per cell (cell --res mm): copper of F.Cu + B.Cu as the board file holds it (zones as stored, tracks,
    pads; 35 um, tools/copper_order.py "IN") + FR-4 (k 0.3, board thickness from the stackup); both faces to the air
    with h 9 W/m2K (ASSUMED: 3 natural convection in a closed box, as tools/thermal_board_b.py htop, + 6 radiation to the
    lid and deck; the linearised h_rad = eps sigma (T1^2 + T2^2)(T1 + T2) is about 7.9 at 65 C with eps 0.9 solder
    mask, taken lower because the facing parts are warm too). --h 3 (no radiation) is the pessimistic bound: the DIP
    switch rise grows from about 5 K to about 17 K (docs/heat-analysis.md).
  * Heat in (worst case, per input, docs DECISIONS 2026-11-08 input network): the wire input at --vin (16 V ASSUMED,
    the top of a charging car system; load dump not steady) through the 4.7 k series resistor into the BAT54S clamp at
    3.3 V + 0.35 V, with the 10 k pull-down switched on (the larger of pull-up / pull-down loss); AIN: 10 k + 20 k
    divider, clamped. Each resistor's loss on its own pads, the clamp's on the BAT54S pads. All 8 inputs on at once.
  * Limits: laminate 130 C (as thermal_board_b); Omron A6S DIP switch -20 to +70 C (Omron A6S data sheet, A102-E1-02,
    docs/parts-audit.md 10); BAT54S Tj 150 C (Nexperia BAT54 series data sheet). The board alone is run at the cabin
    air (60 C); the self-heating offset (board - air) is what the whole-box run adds to the lid air.
"""
import argparse
import json
import os
import sys

import numpy as np
import pcbnew
import scipy.sparse as sp
import scipy.sparse.linalg as spla

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify_copper as VC  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PCB = os.path.join(REPO, "hardware/input-board/input-board.kicad_pcb")
K_CU, K_FR4 = 390.0, 0.3
T_CU = 35e-6
V_CLAMP = 3.3 + 0.35
LIMITS = dict(laminate=130.0, dip=70.0, diode=150.0)


def losses(vin):
    """(ref, W) per part, worst case: every input at vin, pull-down on."""
    out = []
    for i in range(1, 9):
        i_ser = max(vin - V_CLAMP, 0.0) / 4.7e3
        out += [(f"R{i}", i_ser ** 2 * 4.7e3), (f"R{16 + i}", vin ** 2 / 10e3), (f"D{i}", i_ser * 0.35)]
    v_ain = min(vin * 20e3 / 30e3, V_CLAMP)          # 10 k / 20 k divider, clamped
    i_a = (vin - v_ain) / 10e3
    out += [("R25", i_a ** 2 * 10e3), ("R26", v_ain ** 2 / 20e3), ("D9", max(i_a - v_ain / 20e3, 0) * 0.35)]
    return out


def solve(board, res, h, t_air, parts):
    bb = board.GetBoardEdgesBoundingBox()
    x0, y0 = VC.mm(bb.GetX()), VC.mm(bb.GetY())
    g = VC.Grid(x0, y0, x0 + VC.mm(bb.GetWidth()), y0 + VC.mm(bb.GetHeight()), res)
    edge = np.zeros((g.ny, g.nx), bool)
    ps = pcbnew.SHAPE_POLY_SET()
    board.GetBoardPolygonOutlines(ps)
    VC.fill_chains(g, edge, VC.polyset_chains(ps))
    layers = ["F.Cu", "B.Cu"]
    lid = {n: board.GetLayerID(n) for n in layers}
    cov = {n: np.zeros((g.ny, g.nx), bool) for n in layers}
    for z in board.Zones():
        if not z.GetIsRuleArea():
            for n in layers:
                if z.IsOnLayer(lid[n]):
                    VC.fill_chains(g, cov[n], VC.polyset_chains(z.GetFilledPolysList(lid[n])))
    for t in board.GetTracks():
        n = t.GetLayerName()
        if t.GetClass() == "PCB_TRACK" and n in cov:
            VC.fill_segment(g, cov[n], VC.mm(t.GetStart().x), VC.mm(t.GetStart().y), VC.mm(t.GetEnd().x),
                            VC.mm(t.GetEnd().y), VC.mm(t.GetWidth()))
    for fp in board.GetFootprints():
        for p in fp.Pads():
            for n in layers:
                if p.IsOnLayer(lid[n]) and p.GetAttribute() != pcbnew.PAD_ATTRIB_NPTH:
                    VC.fill_chains(g, cov[n], VC.pad_poly(p, lid[n]))
    t_pcb = board.GetDesignSettings().GetBoardThickness() * 1e-9
    s = (K_CU * T_CU * (cov["F.Cu"].astype(float) + cov["B.Cu"]) + K_FR4 * t_pcb)
    ids = -np.ones((g.ny, g.nx), np.int64)
    ids[edge] = np.arange(int(edge.sum()))
    N = int(edge.sum())
    rows, cols, vals = [], [], []
    for a, b, sa, sb in ((ids[:, :-1], ids[:, 1:], s[:, :-1], s[:, 1:]), (ids[:-1, :], ids[1:, :], s[:-1, :], s[1:, :])):
        m = (a >= 0) & (b >= 0)
        rows.append(a[m]); cols.append(b[m]); vals.append(2 * sa[m] * sb[m] / (sa[m] + sb[m]))
    G = sp.coo_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(N, N)).tocsr()
    G = G + G.T
    gb = np.full(N, 2 * h * (res * 1e-3) ** 2)
    A = (sp.diags(np.asarray(G.sum(axis=1)).ravel() + gb) - G).tocsc()
    Q = np.zeros(N)
    for ref, P in parts:
        fp = board.FindFootprintByReference(ref)
        m = np.zeros((g.ny, g.nx), bool)
        for p in fp.Pads():
            VC.fill_chains(g, m, VC.pad_poly(p, lid["F.Cu"] if p.IsOnLayer(lid["F.Cu"]) else lid["B.Cu"]))
        nodes = ids[m & edge]
        nodes = nodes[nodes >= 0]
        Q[nodes] += P / len(nodes)
    Tn = spla.spsolve(A, Q + gb * t_air)
    return g, edge, ids, Tn, float(Q.sum()), float((gb * (Tn - t_air)).sum())


def at_part(board, g, edge, ids, Tn, ref):
    fp = board.FindFootprintByReference(ref)
    xs = [VC.mm(p.GetPosition().x) for p in fp.Pads()]
    ys = [VC.mm(p.GetPosition().y) for p in fp.Pads()]
    m = np.outer((g.yc >= min(ys)) & (g.yc <= max(ys)), (g.xc >= min(xs)) & (g.xc <= max(xs))) & edge
    return float(Tn[ids[m]].max())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--air", type=float, default=60.0)
    ap.add_argument("--vin", type=float, default=16.0)
    ap.add_argument("--h", type=float, default=9.0)
    ap.add_argument("--res", type=float, default=0.25)
    ap.add_argument("--plots")
    ap.add_argument("--json")
    a = ap.parse_args()
    board = pcbnew.LoadBoard(PCB)
    parts = losses(a.vin)
    g, edge, ids, Tn, p_in, p_out = solve(board, a.res, a.h, a.air, parts)
    t_max = float(Tn.max())
    dip = max(at_part(board, g, edge, ids, Tn, r) for r in ("SW1", "SW2"))
    diode = max(at_part(board, g, edge, ids, Tn, f"D{i}") for i in range(1, 10))
    out = dict(air=a.air, vin=a.vin, h=a.h, res=a.res, p_total=round(p_in, 3), p_out=round(p_out, 3),
               board_max=round(t_max, 1), rise_max=round(t_max - a.air, 1), dip_switch=round(dip, 1),
               dip_rise=round(dip - a.air, 1), bat54s=round(diode, 1))
    out["pass"] = dict(laminate=t_max <= LIMITS["laminate"], dip=dip <= LIMITS["dip"], diode=diode <= LIMITS["diode"])
    print(f"input board: {p_in:.3f} W in ({p_out:.3f} W out) at {a.vin} V on all 9 inputs, air {a.air} C, h {a.h}: "
          f"board max {t_max:.1f} C (+{t_max - a.air:.1f} K), DIP switch {dip:.1f} C (+{dip - a.air:.1f} K, limit 70), "
          f"BAT54S board {diode:.1f} C")
    if a.plots:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        f = np.full((g.ny, g.nx), np.nan)
        f[edge] = Tn[ids[edge]]
        fig, ax = plt.subplots(figsize=(6.4, 5.6))
        im = ax.imshow(f, extent=(g.x0, g.x0 + g.nx * g.res, g.y0 + g.ny * g.res, g.y0), cmap="inferno")
        fig.colorbar(im, ax=ax, label="board (C)")
        for r in ("SW1", "SW2", "J1", "J2"):
            fp = board.FindFootprintByReference(r)
            ax.annotate(r, (VC.mm(fp.GetPosition().x), VC.mm(fp.GetPosition().y)), color="c", fontsize=8)
        ax.set_aspect("equal")
        ax.set_title(f"input board, {p_in:.2f} W (all inputs at {a.vin:g} V), air {a.air:g} C: max {t_max:.1f} C, "
                     f"DIP {dip:.1f} C", fontsize=8)
        fig.tight_layout()
        os.makedirs(a.plots, exist_ok=True)
        fig.savefig(os.path.join(a.plots, f"thermal-board-in-air{a.air:g}.png"), dpi=110)
        plt.close(fig)
    if a.json:
        json.dump(out, open(a.json, "w"), indent=1)
    ok = all(out["pass"].values())
    print("RESULT", "PASS" if ok else "FAIL", "(limits: laminate 130 C, DIP switch 70 C, BAT54S 150 C)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
