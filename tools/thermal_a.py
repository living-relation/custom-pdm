"""Board A steady heat model on the real copper: drivers + copper I^2R, gap pad on the heat-sink pedestals, lid air.

usage (repo root; KiCad 9 python with numpy + scipy + matplotlib, as tools/thermal_board_b.py):
    python tools/thermal_a.py [--case rating feed150a car] [--res 0.3] [--kpad 3] [--air fans|nofan]
                                    [--plots DIR] [--json FILE]
tests: python tools/test_thermal_models.py

The same finite-volume model as tools/thermal_board_b.py (its Thermal class: every copper layer's real copper of all nets,
FR-4 between, via / hole barrels, gap pad on the pedestals, air gap under the board, lid air over it), set up for board A
(hardware/board-a/DingoPDM.kicad_pcb, the board fitted twice as A1 and A2):
  * Copper: the ORDERED copper (tools/copper_order.py: board A 1 oz outer + 1 oz inner, 35 / 35 um).
  * Heat in: (1) the four BTS7008-2EPA drivers (U8, U10, U11, U13; two 7.5 A channels each) on their exposed pad (pad
    15): P = R x (I0^2 + I1^2), R = 1.80 W / (2 x 7.5^2) = 16 mOhm per channel (the worst-case 1.80 W per chip of
    docs/enclosure-layout.md 4.3, as sim/heat/geometry.py); (2) copper I^2R of +12V and every loaded output on the real
    copper (tools/verify_copper.solve_net, J3 wire pads as the output terminals, J1 as the feed), scaled to the local
    copper temperature; (3) J1 bolted joint (20 uOhm, ASSUMED as thermal_board_b) + half of each BATT bar segment
    beside it; (4) the 5 V module LMZM23601V5 (U21), 0.2 W ASSUMED (thermal_board_b P_5V).
  * Heat out: B.Cu on the two pedestals (sim/heat/geometry.py PED["A"], hull + 1.5 mm) through the TGP 3000 pad (k 3,
    0.86 mm after 15 % squeeze, thermal_board_b PAD_T); the rest of the bottom through the 4 mm air gap; the top to
    the lid air (3 W/m2K); J1's terminal node through the BATT bar (Cu 20 x 5) to board B (113.4 mm) and to the other A
    board (74.4 mm), both far ends at the sink + 15 K (ASSUMED as thermal_board_b DT_A1). Pedestal, plate and lid air
    at the hottest pedestal top under an A board in the whole-box model: 60 C cabin + R_sys x box heat (R_SYS_A).
  * Limits: Tj = board top under the EP + P x RthJC max (1.4 K/W, Infineon BTS7008-2EPA Table 6) <= 150 C; laminate
    <= 130 C (as thermal_board_b); logic parts (MCU, FRAM 105 C ambient; 5 V module 125 C TJ) reported at the board
    under them, and the U6 MCP9808 reading, for board A's firmware warn / critical.

Cases (the loaded board is A1; the box heat counts every board):
  rating     every output of the box at its rating (A1, A2 8 x 7.5 A, B 184 A: 304 A, above the 150 A feed: upper bound)
  feed150a   both A boards at their rating (2 x 60 A) + 30 A on B (B's ratings x 30 / 184): the 150 A feed limit with the
             A boards loaded first - the hottest board A case the firmware allows
  car        docs/car-loads.dummy.md (dummy test copy), currents as tools/verify_thermal_box.py: A1 OUT1-8 2.0 2.5 0.5 0.2
             5.0 0.15 5.0 5.0 A; A2 0.2 0.13 0.2 3.0 A; B 118.1 A (thermal_board_b car)
"""
import argparse
import json
import os
import sys

import numpy as np
import pcbnew
import scipy.sparse.linalg as spla

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import thermal_board_b as TB  # noqa: E402
import verify_copper as VC  # noqa: E402

REPO = TB.REPO
PCB = os.path.join(REPO, "hardware/board-a/DingoPDM.kicad_pcb")
A_DRV = VC.A_DRV                                     # U8: (PF_OUT1, PF_OUT2), ...
R_CH = 1.80 / (2 * 7.5 ** 2)                         # Ohm per channel
RTHJC_A = 1.4                                        # K/W max, Infineon BTS7008-2EPA Table 6 (docs/heat-analysis.md)
PED_A = [(-1.905, 13.132, 11.379, 14.021), (-1.981, 10.922, -13.970, -11.227)]   # sim/heat/geometry.py PED["A"]
LOGIC_REFS_A = {"U4": "MCU STM32F446RET7", "U5": "FRAM MB85RC64TA", "U21": "5 V module LMZM23601V5", "Y1": "crystal",
                "U6": "MCP9808"}
G_BARS = TB.K_CU * 20e-3 * 5e-3 * (1 / 113.4e-3 + 1 / 74.4e-3)
L_BAR = {"B-A1": 113.4e-3, "A1-A2": 74.4e-3}
OUTS = [f"PF_OUT{i}" for i in range(1, 9)]
CAR_A1 = [2.0, 2.5, 0.5, 0.2, 5.0, 0.15, 5.0, 5.0]
CAR_A2 = [0.2, 0.13, 0.2, 3.0, 0.0, 0.0, 0.0, 0.0]
# board B for the box total: chips exact, copper scaled from board B's rating run (thermal_board_b --case rating, ordered
# copper, 0.3 mm grid, 2026-11-23: 17.3 W at 184 A) by (I_B / 184)^2 - an estimate for the box total only
P_CU_B_RATING = 17.3
# pedestal temperature per W of box heat under board A (hottest of A1 / A2) in the whole-box Elmer model of the revF
# enclosure (sim/heat HEAT_GEOM=revF, m2, 2026-11-23): fans on 0.412 K/W (feed150a; car 0.334) -> 0.41; fans off on a wall
# 1.092 K/W (car; feed150 0.962) -> 1.09. Board A sits at the fan (air inlet) end, so it runs cooler than board B (0.54).
R_SYS_A = {"fans": 0.41, "nofan": 1.09}


def load_board():
    return pcbnew.LoadBoard(PCB)


def case_currents(name):
    if name == "rating":
        this = {n: 7.5 for n in OUTS}
        return dict(this=this, other_a=dict(this), I_B=184.0, b_scale=1.0)
    if name == "feed150a":
        this = {n: 7.5 for n in OUTS}
        return dict(this=this, other_a=dict(this), I_B=30.0, b_scale=30.0 / 184.0)
    if name == "car":
        return dict(this=dict(zip(OUTS, CAR_A1)), other_a=dict(zip(OUTS, CAR_A2)), I_B=118.1, b_scale=None)
    raise SystemExit(f"unknown case {name}")


def chip_list(cur):
    out = []
    for u, (o0, o1) in A_DRV.items():
        out.append(dict(ref=u, net=f"{o0}+{o1}", type="BTS7008", I=cur[o0] + cur[o1], I0=cur[o0], I1=cur[o1],
                        P=R_CH * (cur[o0] ** 2 + cur[o1] ** 2)))
    return out


def board_b_heat(c):
    """Board B's heat for the box total (W): drivers at their currents + copper estimate + 5 V module."""
    if c["b_scale"] is None:                     # car: thermal_board_b car currents
        cur, _ = TB.case_currents("car")
    else:
        cur = {n: v * c["b_scale"] for n, v in TB.case_currents("rating")[0].items()}
    chips = TB.chip_list(cur)
    return sum(x["P"] for x in chips) + P_CU_B_RATING * (sum(cur.values()) / 184.0) ** 2 + TB.P_5V


def copper_fields(board, cur, th, diel, res, feed_res):
    base = VC.board_cfg("A")["nets"]
    fields, rs = [], []
    for net, ncfg in base.items():
        if net == "+12V":
            src = [s[:2] + (cur[A_DRV[s[0]][0]] + cur[A_DRV[s[0]][1]],) for s in ncfg["src"]]
            src = [s for s in src if s[2] > 0]
            if not src:
                continue
            c = dict(ncfg, src=src, I=sum(s[2] for s in src))
            r, f = VC.solve_net(board, net, c, feed_res, th, diel)
        else:
            if cur[net] <= 0:
                continue
            r, f = VC.solve_net(board, net, dict(ncfg, I=cur[net]), res, th, diel)
        rs.append(r)
        fields.append(f)
    return rs, fields


def run_case(board, th, diel, case, a, T, plots=None):
    c = case_currents(case)
    cur = c["this"]
    chips = chip_list(cur)
    for ch in chips:
        fp = board.FindFootprintByReference(ch["ref"])
        ch["xy"] = (VC.mm(fp.GetPosition().x), VC.mm(fp.GetPosition().y))
    i_this, i_other = sum(cur.values()), sum(c["other_a"].values())
    rs, fields = copper_fields(board, cur, th, diel, a.cu_res, a.feed_res)
    r_m = VC.RHO * 1.31 / (20e-3 * 5e-3)         # BATT bar Ohm per m at about 100 C
    p_j1 = TB.R_JOINT * i_this ** 2 + 0.5 * r_m * (L_BAR["B-A1"] * (i_this + i_other) ** 2 + L_BAR["A1-A2"] * i_other ** 2)
    joints = [("J1", p_j1), ("U21", TB.P_5V)]
    p_chip = sum(x["P"] for x in chips)
    p_joint = sum(j[1] for j in joints)
    Amat, gb = T.matrix(a.kpad, a.htop, a.hbot, True, g_bar=G_BARS)   # J1: bars to B and to the other A board
    lu = spla.splu(Amat)
    p_b = board_b_heat(c)
    i_tot = i_this + i_other + c["I_B"]
    p_ext = 3.2 * (i_tot / 150.0) ** 2           # bars / joints / contacts / harness (docs/heat-analysis.md 3)
    out = dict(case=case, board="A1", I_A1=round(i_this, 2), I_A2=round(i_other, 2), I_B=c["I_B"], kpad=a.kpad,
               air=a.air, res=a.res)
    Tn = None
    for it in range(3):
        Q = T.heat(fields, chips, joints, Tn)
        p_cu = float(T.q_copper.sum())
        sq = sum(v * v for v in cur.values())
        p_other = sum(x["P"] for x in chip_list(c["other_a"])) + TB.P_5V + \
            (p_cu * sum(v * v for v in c["other_a"].values()) / sq if sq else 0.0)
        p_box = p_chip + p_cu + p_joint + p_other + p_b + p_ext
        tsink = TB.T_CABIN + TB.R_SYS[a.air] * p_box
        Tn = lu.solve(Q + gb * tsink + T.gbar * (tsink + TB.DT_A1))
    T0 = lu.solve(Q - T.q_copper + gb * tsink + T.gbar * (tsink + TB.DT_A1))
    dcu = Tn - T0
    g = T.g
    lay = {}
    for k, n in enumerate(VC.CU):
        f = np.full((g.ny, g.nx), np.nan)
        f[T.edge] = Tn[T.ids[k][T.edge]]
        j, i = np.unravel_index(np.nanargmax(f), f.shape)
        lay[n] = dict(t_max=round(float(np.nanmax(f)), 1), at=(round(float(g.xc[i]), 1), round(float(g.yc[j]), 1)))
    kmax = int(np.argmax(Tn[:-1]))
    for ch in chips:
        top = float(Tn[ch["nodes"]].max())
        ch["t_board"] = round(top, 1)
        ch["tj"] = round(top + ch["P"] * RTHJC_A, 1)
        ch.pop("nodes")
    hot = max(chips, key=lambda x: x["tj"])
    parts = TB.part_temps(board, T, Tn, LOGIC_REFS_A)
    fp6 = board.FindFootprintByReference("U6")
    x6, y6 = VC.mm(fp6.GetPosition().x), VC.mm(fp6.GetPosition().y)
    n6 = T.ids[0][int(np.argmin(abs(g.yc - y6))), int(np.argmin(abs(g.xc - x6)))]
    out.update(p_chip=round(p_chip, 2), p_copper=round(p_cu, 2), p_joints=round(p_joint, 2), p_other_a=round(p_other, 2),
               p_board_b=round(p_b, 2), p_bars_contacts=round(p_ext, 2), p_box=round(p_box, 2), t_sink=round(tsink, 1),
               laminate_max=round(float(Tn[:-1].max()), 1), t_j1=round(float(Tn[-1]), 1),
               laminate_at=lay[VC.CU[kmax // T.ncell]]["at"], laminate_layer=VC.CU[kmax // T.ncell],
               copper_rise_max=round(float(dcu[:-1].max()), 1), copper_rise_at_hot=round(float(dcu[kmax]), 1),
               layers=lay, chips=[{k: ch[k] for k in ("ref", "net", "type", "I", "P", "t_board", "tj")} for ch in chips],
               hottest_chip=hot["ref"], tj_max=hot["tj"], t_sensor_u6=round(float(Tn[n6]), 1) if n6 >= 0 else None,
               parts=parts, feed=[dict(net=r["net"], I=round(r["I"], 1), drop_mv=round(r["drop_mv"], 1),
                                       p_w=round(r["power_w"], 2)) for r in rs])
    sq = sum(v * v for v in cur.values())
    out.update(chips_other_a=[dict(ref=x["ref"], P=round(x["P"], 3)) for x in chip_list(c["other_a"])],
               p_copper_other_a=round(p_cu * sum(v * v for v in c["other_a"].values()) / sq, 3) if sq else 0.0,
               assumptions=dict(dt_bar=TB.DT_A1, p5v=TB.P_5V, r_sys=TB.R_SYS[a.air], pad_mm=TB.PAD_T * 1e3))
    out["pass"] = dict(tj=out["tj_max"] <= TB.LIMITS["tj"], laminate=out["laminate_max"] <= TB.LIMITS["laminate"],
                       logic=all(p["t"] <= 105.0 for r, p in parts.items() if r in ("U4", "U5")))
    if plots:
        TB.plot(plots, case, a, T, Tn, dcu, out, board, name="a")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", nargs="+", default=["rating", "feed150a", "car"])
    ap.add_argument("--res", type=float, default=0.3)
    ap.add_argument("--cu-res", type=float, default=0.2)
    ap.add_argument("--feed-res", type=float, default=0.3)
    ap.add_argument("--kpad", type=float, default=3.0)
    ap.add_argument("--htop", type=float, default=3.0)
    ap.add_argument("--hbot", type=float, default=TB.K_AIR / 4e-3 + 1.0)
    ap.add_argument("--air", default="fans", choices=sorted(TB.R_SYS))
    ap.add_argument("--plots")
    ap.add_argument("--json")
    ap.add_argument("--dt-bar", type=float, default=TB.DT_A1, help="sensitivity: BATT bar far ends over the sink (K)")
    ap.add_argument("--p5v", type=float, default=TB.P_5V, help="sensitivity: 5 V module loss (W)")
    ap.add_argument("--rsys", type=float, help="sensitivity / box result: sink K per W for --air")
    a = ap.parse_args()
    TB.R_SYS.update(R_SYS_A)                 # board A's own pedestal temperature per W (--rsys still overrides)
    TB.set_assumptions(a)
    board = load_board()
    th, diel = VC.stackup(PCB)
    th, ordered, label = VC.copper_order.apply(th, "A", None, None)
    T = TB.Thermal(board, th, diel, a.res, peds=PED_A)
    print(f"board A thermal: {label}; cell {a.res} mm, {T.N} nodes; gap pad k {a.kpad} / {TB.PAD_T * 1e3:.2f} mm; "
          f"air {a.air} (R_sys {TB.R_SYS[a.air]} K/W)")
    res, fails = [], 0
    for case in a.case:
        r = run_case(board, th, diel, case, a, T, a.plots)
        r["copper_um"] = {n: round(th[n] * 1e6, 2) for n in VC.CU}
        r["ordered"] = ordered
        res.append(r)
        ok = all(r["pass"].values())
        fails += not ok
        pt = ", ".join(f"{k} {v['t']}" for k, v in r["parts"].items())
        print(f"  {case:9} A1 {r['I_A1']:5.1f} A: P chips {r['p_chip']:.2f} + copper {r['p_copper']:.2f} + joints/5V "
              f"{r['p_joints']:.2f} W (box {r['p_box']:.1f} W) -> sink {r['t_sink']} C | Tj max {r['tj_max']} C "
              f"({r['hottest_chip']}) {'ok' if r['pass']['tj'] else 'FAIL'} | laminate max {r['laminate_max']} C at "
              f"{r['laminate_at']} {r['laminate_layer']} {'ok' if r['pass']['laminate'] else 'FAIL'} | parts: {pt}")
    if a.json:
        with open(a.json, "w") as f:
            json.dump(res, f, indent=1, default=str)
    print("RESULT", "PASS" if not fails else f"FAIL ({fails})",
          f"(limits: Tj <= {TB.LIMITS['tj']} C, laminate <= {TB.LIMITS['laminate']} C, MCU / FRAM board <= 105 C)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
