"""Export one board heat case for the Fusion thermal cross-check (ADR-2026-11-23-fusion-check).

usage (repo root, KiCad 9 python with numpy + scipy, as tools/thermal_board_b.py):
    python tools/fusion_thermal/export_board.py A|B CASE [--air fans|nofan] --json OUT
    python tools/fusion_thermal/export_board.py IN in60 --json OUT

Runs the board model's own case (tools/thermal_a.py / thermal_board_b.py / thermal_input.py: same inputs; its result
is the reference) and writes what tools/fusion_thermal/build_fusion_board.py needs to build an equivalent Fusion
"Thermal" study model:
  * sheets: the copper layers lumped into a top and a bottom sheet (main boards: F.Cu + In1.Cu / In2.Cu + B.Cu; input
    board: one sheet), their in-plane conductance per tile (W/K per square; real copper of all nets, ordered copper);
  * core (main boards): FR-4 + every via / plated-hole barrel per tile as a through-plane conductivity;
  * heat: driver losses on their exposed pads (chips); the copper I2R of the case (temperature-scaled, as the model
    solved it) + bolted joints + 5 V module lumped per heat tile, top or bottom sheet by layer; J1 joint + half bar;
  * boundaries: gap pads on the pedestals (TGP 3000, k 3, 0.86 mm) to the pedestal top at the case's sink temperature,
    the 4 mm air gap and the lid air as h to the same temperature, the BATT bar(s) as a conductance to sink + 15 K;
  * probe points (chips, U6 sensor, MCU, FRAM, 5 V module) and the reference results of the board model.
"""
import argparse
import json
import math
import os
import sys
from types import SimpleNamespace

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)
import thermal_board_b as TB  # noqa: E402
import verify_copper as VC  # noqa: E402

TS = 0.3          # sheet thickness in the Fusion model (mm): conductance kept, k = G / TS
TILE_K = 2.5      # tile size for the conductance maps (mm)
TILE_Q = 10.0     # tile size for the lumped copper / joint heat (mm)


def tiles(g, edge, val, s):
    """[x0, y0, x1, y1, mean of val over the tile's board cells, board fraction of the tile] per s x s mm tile."""
    nx, ny = int(math.ceil(g.nx * g.res / s)), int(math.ceil(g.ny * g.res / s))
    ti = np.minimum((np.arange(g.nx) * g.res / s).astype(int), nx - 1)
    tj = np.minimum((np.arange(g.ny) * g.res / s).astype(int), ny - 1)
    J, I = np.nonzero(edge)
    key = tj[J] * nx + ti[I]
    sm = np.bincount(key, weights=val[J, I], minlength=nx * ny)
    n = np.bincount(key, minlength=nx * ny)
    out = []
    for k in np.nonzero(n)[0]:
        i, j = k % nx, k // nx
        x0, y0 = g.x0 + i * s, g.y0 + j * s
        x1, y1 = min(x0 + s, g.x0 + g.nx * g.res), min(y0 + s, g.y0 + g.ny * g.res)
        out.append([round(x0, 3), round(y0, 3), round(x1, 3), round(y1, 3), float(sm[k] / n[k]),
                    float(n[k] * g.res ** 2 / ((x1 - x0) * (y1 - y0)))])
    return out


def heat_tiles(g, recs, s):
    acc = {}
    for x, y, w in recs:
        k = (int((x - g.x0) // s), int((y - g.y0) // s))
        acc[k] = acc.get(k, 0.0) + w
    return [[round(g.x0 + (i + 0.5) * s, 3), round(g.y0 + (j + 0.5) * s, 3), w] for (i, j), w in sorted(acc.items())]


def fp_box(board, ref, margin=0.0):
    fp = board.FindFootprintByReference(ref)
    xs = [VC.mm(p.GetPosition().x) for p in fp.Pads()]
    ys = [VC.mm(p.GetPosition().y) for p in fp.Pads()]
    return [round(min(xs) - margin, 3), round(min(ys) - margin, 3), round(max(xs) + margin, 3), round(max(ys) + margin, 3)]


def fp_xy(board, ref):
    fp = board.FindFootprintByReference(ref)
    return [round(VC.mm(fp.GetPosition().x), 3), round(VC.mm(fp.GetPosition().y), 3)]


def outline_of(board):
    bb = board.GetBoardEdgesBoundingBox()
    return [round(v, 3) for v in (VC.mm(bb.GetX()), VC.mm(bb.GetY()), VC.mm(bb.GetX() + bb.GetWidth()),
                                  VC.mm(bb.GetY() + bb.GetHeight()))]


def main_board(which, case, air):
    import pcbnew
    import thermal_a as TA
    if which == "A":
        path = TA.PCB
        TB.R_SYS.update(TA.R_SYS_A)
        peds, logic, mod = TA.PED_A, TA.LOGIC_REFS_A, "U21"
    else:
        path = os.path.join(TB.REPO, "hardware/board-b-max/dingoPDM-Max.kicad_pcb")
        peds, logic, mod = TB.PED_B, TB.LOGIC_REFS_B, "U27"
    board = pcbnew.LoadBoard(path)
    th, diel = VC.stackup(path)
    th, ordered, label = VC.copper_order.apply(th, which, None, None)
    T = TB.Thermal(board, th, diel, 0.3, peds=peds)
    a = SimpleNamespace(cu_res=0.2, feed_res=0.3, kpad=3.0, htop=3.0, hbot=TB.K_AIR / 4e-3 + 1.0, air=air,
                        no_bar=False, res=0.3)
    ref = (TA.run_case if which == "A" else TB.run_case)(board, th, diel, case, a, T)
    g, L = T.g, VC.CU
    # the heat the model put on pad copper besides the chips and J1: recomputed exactly as in run_case
    if which == "A":
        c = TA.case_currents(case)
        i_this, i_other = sum(c["this"].values()), sum(c["other_a"].values())
        r_m = VC.RHO * 1.31 / (20e-3 * 5e-3)
        p_j1 = TB.R_JOINT * i_this ** 2 + 0.5 * r_m * (TA.L_BAR["B-A1"] * (i_this + i_other) ** 2 +
                                                        TA.L_BAR["A1-A2"] * i_other ** 2)
        joints, g_bar, chips, rthjc = [(mod, TB.P_5V)], TA.G_BARS, TA.chip_list(c["this"]), {"BTS7008": TA.RTHJC_A}
    else:
        cur, _ = TB.case_currents(case)
        i_b = sum(cur.values())
        r_bar = VC.RHO * 1.31 * 113.4e-3 / (20e-3 * 5e-3)
        p_j1 = TB.R_JOINT * i_b ** 2 + 0.5 * r_bar * 150.0 ** 2
        joints = [(f"T{i + 1}", (2 if net in TB.HI else 1) * TB.R_JOINT * cur[net] ** 2)
                  for i, net in enumerate(list(TB.HI) + list(TB.MED))] + [(mod, TB.P_5V)]
        g_bar, chips, rthjc = TB.G_BAR, TB.chip_list(cur), TB.RTHJC
    q = T.q_copper.copy()
    q[-1] = 0.0
    for ref_, P in joints:
        nodes = T.pad_nodes(ref_)
        if len(nodes) and P > 0:
            q[nodes] += P / len(nodes)
    J, I = np.nonzero(T.edge)
    top, bot = [], []
    for n in np.nonzero(q[:-1] > 0)[0]:
        k, idx = divmod(int(n), T.ncell)
        (top if k < 2 else bot).append((float(g.xc[I[idx]]), float(g.yc[J[idx]]), float(q[n])))
    s_top = sum(np.where(T.cov[n], TB.K_CU * th[n], 0.0) for n in L[:2])
    s_bot = sum(np.where(T.cov[n], TB.K_CU * th[n], 0.0) for n in L[2:])
    barrel = np.zeros((g.ny, g.nx))           # W m / K per cell: k_Cu pi (d + t) t of every through barrel
    for (x, y, d, vl) in T.holes:
        if len(vl) >= 2:
            i, j = g.cell(x, y)
            barrel[j, i] += TB.K_CU * math.pi * (d * 1e-3 + VC.TPLATE) * VC.TPLATE
    core = tiles(g, T.edge, barrel, TILE_K)
    for c_ in core:                           # k_eff = k_FR4 + sum over the tile / tile board area
        c_[4] = TB.K_FR4 + c_[4] / (g.res * 1e-3) ** 2
    t_tot = sum(th[n] for n in L) + sum(diel.get(n, 0.0) for n in L)
    chips_out = [dict(ref=c_["ref"], type=c_["type"], P=c_["P"], I=c_["I"], xy=fp_xy(board, c_["ref"]),
                      ep=list(TB.EP[c_["type"]]), rthjc=rthjc[c_["type"]]) for c_ in chips]
    # lite model: one conductivity per sheet (mean in-plane conductance over the board), via patches under each
    # driver's exposed pad (its own barrels), the rest of the core one conductivity (all other barrels spread)
    jbox = fp_box(board, "J1", 0.5)
    m_patch = np.zeros((g.ny, g.nx), bool)
    patches = []
    for c_ in chips_out:
        (x, y), (w, h) = c_["xy"], c_["ep"]
        r = [x - w / 2, y - h / 2, x + w / 2, y + h / 2]
        m = np.outer((g.yc >= r[1]) & (g.yc <= r[3]), (g.xc >= r[0]) & (g.xc <= r[2])) & T.edge
        m_patch |= m
        area = m.sum() * (g.res * 1e-3) ** 2
        patches.append(dict(ref=c_["ref"], rect=[round(v, 3) for v in r],
                            k=TB.K_FR4 + float(barrel[m].sum()) / area if area > 0 else TB.K_FR4,
                            n_barrels=int(np.count_nonzero(barrel[m]))))
    m_j1 = np.outer((g.yc >= jbox[1]) & (g.yc <= jbox[3]), (g.xc >= jbox[0]) & (g.xc <= jbox[2])) & T.edge
    rest = T.edge & ~m_patch & ~m_j1
    lite = dict(k_top=float(s_top[T.edge].mean()) / (TS * 1e-3) + TB.K_FR4,
                k_bot=float(s_bot[T.edge].mean()) / (TS * 1e-3) + TB.K_FR4,
                k_core=TB.K_FR4 + float(barrel[rest].sum()) / (rest.sum() * (g.res * 1e-3) ** 2), patches=patches)
    peds_out = [[a_ - TB.PED_MARGIN, c_ - TB.PED_MARGIN, b_ + TB.PED_MARGIN, d_ + TB.PED_MARGIN]
                for (a_, b_, c_, d_) in peds]
    probes = {"U6": fp_xy(board, "U6")}
    probes.update({r_: fp_xy(board, r_) for r_ in logic if board.FindFootprintByReference(r_) is not None})
    return dict(
        board=which, case=case, air=air, label=label, ordered=ordered, outline=outline_of(board),
        thickness=round(t_tot * 1e3, 3), sheet_t=TS, core_t=round(t_tot * 1e3 - 2 * TS, 3), k_fr4=TB.K_FR4,
        sheets=dict(top=tiles(g, T.edge, s_top, TILE_K), bot=tiles(g, T.edge, s_bot, TILE_K)), core=core, lite=lite,
        heat=dict(top=heat_tiles(g, top, TILE_Q), bot=heat_tiles(g, bot, TILE_Q), tile=TILE_Q), chips=chips_out,
        j1=dict(box=jbox, P=p_j1, g_bar=g_bar, t_bar=ref["t_sink"] + TB.DT_A1),
        peds=peds_out, pad=dict(t=TB.PAD_T * 1e3, k=a.kpad), t_sink=ref["t_sink"], h_top=a.htop, h_bot=a.hbot,
        probes=probes, reference=ref,
        totals=dict(p_chips=sum(c_["P"] for c_ in chips), p_dist=float(q.sum()), p_j1=p_j1))


def input_board():
    import pcbnew
    import thermal_input as TI
    board = pcbnew.LoadBoard(TI.PCB)
    parts = TI.losses(16.0)
    g, edge, ids, Tn, p_in, p_out = TI.solve(board, 0.25, 9.0, 60.0, parts)
    lid = {n: board.GetLayerID(n) for n in ("F.Cu", "B.Cu")}
    cov = {n: np.zeros((g.ny, g.nx), bool) for n in lid}
    for z in board.Zones():
        if not z.GetIsRuleArea():
            for n in lid:
                if z.IsOnLayer(lid[n]):
                    VC.fill_chains(g, cov[n], VC.polyset_chains(z.GetFilledPolysList(lid[n])))
    for t in board.GetTracks():
        n = t.GetLayerName()
        if t.GetClass() == "PCB_TRACK" and n in cov:
            VC.fill_segment(g, cov[n], VC.mm(t.GetStart().x), VC.mm(t.GetStart().y), VC.mm(t.GetEnd().x),
                            VC.mm(t.GetEnd().y), VC.mm(t.GetWidth()))
    for fp in board.GetFootprints():
        for p in fp.Pads():
            for n in lid:
                if p.IsOnLayer(lid[n]) and p.GetAttribute() != pcbnew.PAD_ATTRIB_NPTH:
                    VC.fill_chains(g, cov[n], VC.pad_poly(p, lid[n]))
    t_pcb = board.GetDesignSettings().GetBoardThickness() * 1e-9
    s = TI.K_CU * TI.T_CU * (cov["F.Cu"].astype(float) + cov["B.Cu"])
    heaters = [dict(ref=r_, P=P, box=fp_box(board, r_, 0.3)) for r_, P in parts if P > 0]
    jp = max(TI.at_part(board, g, edge, ids, Tn, r_) for r_ in TI.JUMPERS)
    diode = max(TI.at_part(board, g, edge, ids, Tn, f"D{i}") for i in range(1, 10))
    probes = {r_: fp_xy(board, r_) for r_ in ("JP1", "JP9", "JP16", "D1", "R1", "R17", "R25")}
    return dict(board="IN", case="in60", outline=outline_of(board), thickness=round(t_pcb * 1e3, 3), k_fr4=TI.K_FR4,
                sheets=dict(one=tiles(g, edge, s, TILE_K)), lite=dict(k_one=float(s[edge].mean()) / t_pcb + TI.K_FR4),
                parts=heaters, h=9.0, t_air=60.0, probes=probes,
                reference=dict(p_total=p_in, board_max=round(float(Tn.max()), 1), jumpers=round(jp, 1),
                               bat54s=round(diode, 1)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("board", choices=["A", "B", "IN"])
    ap.add_argument("case")
    ap.add_argument("--air", default="fans")
    ap.add_argument("--json", required=True)
    a = ap.parse_args()
    out = input_board() if a.board == "IN" else main_board(a.board, a.case, a.air)
    with open(a.json, "w") as f:
        json.dump(out, f, indent=1, default=str)
    r = out["reference"]
    print(f"{a.board} {a.case}: reference " + json.dumps({k: r.get(k) for k in (
        "t_sink", "tj_max", "hottest_chip", "laminate_max", "laminate_at", "t_sensor_u6", "board_max", "jumpers")}))
    if "totals" in out:
        print("heat totals", {k: round(v, 3) for k, v in out["totals"].items()},
              "| top / bot heat tiles", len(out["heat"]["top"]), len(out["heat"]["bot"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
