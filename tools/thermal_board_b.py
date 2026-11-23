"""Board B steady heat model on the real copper: drivers + copper I^2R, gap pad on the heat-sink pedestals, lid air.

usage (repo root; KiCad 9 python with numpy + scipy, as tools/verify_copper.py):
    python tools/thermal_board_b.py [--case feed150 car rating ...] [--res 0.4] [--kpad 3] [--air fans|nofan]
                                    [--path BOARD] [--plots DIR] [--json FILE]

ADR-2026-11-20-boardb-feed: board B's +12 V copper loss (tools/verify_copper.py) was found in a model with no heat
sink. This puts it into the enclosure (docs/enclosure-v2c.md, docs/heat-analysis.md) to see the real hot spot.

Model (finite volume, one node per cell and copper layer; cell = --res mm):
  * Copper: every copper layer's real copper of ALL nets (filled zones as stored, tracks, arcs, pads, vias) from the
    board file, sheet conductance k_Cu * t (t = the ORDERED copper, tools/copper_order.py: board B 35 um outer and
    35 um inner, Dan 2026-11-22; --outer-um / --inner-um with another value is a labelled what-if run, exit 2); FR-4 between the layers (k 0.3 W/mK in plane and
    through, ASSUMED as docs/heat-analysis.md); every via and plated hole is a copper barrel (plating 20 um) joining
    its layers. In-plane conductance at a cell = copper sheet + half of each neighbouring dielectric.
  * Heat in: (1) driver losses on their exposed-pad outline on F.Cu: P = I^2 x R, with R from the worst-case losses
    in docs/enclosure-layout.md 4.3 (BTS70012 2.37 W at 31 A -> 2.47 mOhm, BTS7004 1.80 W at 15 A -> 8.0 mOhm);
    (2) copper I^2R of +12V and every loaded output, solved on the real copper by tools/verify_copper.solve_net, per
    layer, scaled to the local copper temperature (rho x (1 + 0.00393 (T - 20)), two passes); (3) bolted joints
    (20 uOhm each, ASSUMED as docs/heat-analysis.md): J1 feed (1), T1-T4 riser foot + lug seat (2), T5-T8 (1).
  * Heat out: B.Cu on the three pedestals (bottom-mask window hull + 1.5 mm, sim/heat/geometry.py PED) through the
    gap pad (1 mm, k --kpad, DECISIONS b3a: k >= 3) to the pedestal top; the rest of the bottom face through the
    4 mm air gap to the plate (k_air / gap + radiation, about 8.5 W/m2K); the top face to the air under the lid
    (--htop, default 3 W/m2K, natural convection in a closed box, ASSUMED). Pedestal, plate and lid air are taken at
    the heat-sink MAX temperature of the enclosure model for the case's total box heat: T = 60 C cabin air +
    R_sys x P_box, R_sys = 0.47 K/W with the F1 fans (74.6 C at 31.1 W, docs/enclosure-v2c.md 4) or 0.98 K/W fans
    off on a wall (90.6 C at 31.1 W). P_box = board B drivers + copper + joints, + bars / contacts / harness
    (docs/heat-analysis.md 3: 3.2 W at 150 A, x (I / 150)^2) + the A boards (car case only, their share of the feed).
  * Limits (pass / fail): driver Tj = board top under the pad + P x RthJC max <= 150 C (Infineon); laminate (any
    copper / FR-4 node) <= 130 C (FR-4 UL relative thermal index, the usual long-term limit; JLCPCB FR-4 Tg 135-155
    C). Reported, not a pass / fail limit here: how much the copper loss lifts the hot spot (verify_copper's
    no-sink 10 K rule is a layout-fault screen; here the real limits above already include the copper heat).

Cases (board B outputs OUT1-4 BTS70012 31 A, OUT5-8 BTS7004 15 A):
  rating      every output at its rating (184 A: above the 150 A feed limit; the PR #109 upper bound)
  feed150     150 A on board B split in proportion to the ratings (x 0.815)
  feed150hi   OUT1-4 at 31 A + 26 A over OUT5-8 (the BTS70012 pair next to J1 loaded first)
  feed150lo   OUT5-8 at 15 A + 90 A over OUT1-4 (the far BTS7004 rail loaded first)
  car         docs/car-loads.dummy.md (dummy test copy): OUT1 radiator fan 30 A, OUT2 condenser fan 30 A, OUT3 fuel
              pump 25 A, OUT5 CAN lambda 8.1 A, OUT6 A/C clutch 10 A, OUT7 wiper 15 A (one speed at a time):
              118.1 A on B, the other 31.9 A of the feed on the A boards
"""
import argparse
import json
import math
import os
import sys

import numpy as np
import pcbnew
import scipy.sparse as sp
import scipy.sparse.linalg as spla

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify_copper as VC  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
K_CU, K_FR4, K_AIR = 390.0, 0.3, 0.03
TPLATE = VC.TPLATE
HI = {"PF_OUT1": "U8", "PF_OUT2": "U9", "PF_OUT3": "U10", "PF_OUT4": "U11"}
MED = {"PF_OUT5": "U23", "PF_OUT6": "U24", "PF_OUT7": "U25", "PF_OUT8": "U26"}
R_ON = {"BTS70012": 2.37 / 31 ** 2, "BTS7004": 1.80 / 15 ** 2}
RTHJC = {"BTS70012": 0.7, "BTS7004": 2.4}           # K/W max, Infineon Table 6 (docs/heat-analysis.md)
EP = {"BTS70012": (6.40, 2.77), "BTS7004": (2.65, 4.00)}   # sim/heat/geometry.py (KiCad axes)
PED_B = [(-12.22, 12.32, 11.15, 14.07), (-12.22, 12.32, -14.07, -11.15), (53.623, 56.265, -27.415, 46.417)]
PED_MARGIN = 1.5
R_JOINT = 20e-6
R_SYS = {"fans": 0.47, "nofan": 0.98}
# J1 (Wurth 7461084 M6 press-fit feed terminal) and the BATT bar: the terminal body + press-fit pins tie every layer's
# J1 barrels to one node (0.5 W/K per pin and layer, ASSUMED: solid CuSn pins); the BATT bar (Cu 20 x 5 mm,
# 113.4 mm from B to A1, docs/heat-analysis.md 3) joins that node to board A1's terminal, taken at the sink + 15 K
# (A1's own feed corner: verify_copper A hot spot 8.5 K over its mean, + margin; ASSUMED).
G_PIN = 0.5
G_BAR = K_CU * 20e-3 * 5e-3 / 113.4e-3
DT_A1 = 15.0
T_CABIN = 60.0
LIMITS = dict(tj=150.0, laminate=130.0)


def case_currents(name):
    o = [f"PF_OUT{i}" for i in range(1, 9)]
    rating = {n: (31.0 if n in HI else 15.0) for n in o}
    if name == "rating":
        return rating, 0.0
    if name == "feed150":
        return {n: v * 150.0 / 184.0 for n, v in rating.items()}, 0.0
    if name == "feed150hi":
        return {n: (31.0 if n in HI else 26.0 / 4) for n in o}, 0.0
    if name == "feed150lo":
        return {n: (90.0 / 4 if n in HI else 15.0) for n in o}, 0.0
    if name == "car":
        cur = dict(PF_OUT1=30.0, PF_OUT2=30.0, PF_OUT3=25.0, PF_OUT4=0.0, PF_OUT5=8.1, PF_OUT6=10.0, PF_OUT7=15.0,
                   PF_OUT8=0.0)
        return cur, 150.0 - sum(cur.values())
    raise SystemExit(f"unknown case {name}")


def chip_list(cur):
    out = []
    for net, u in list(HI.items()) + list(MED.items()):
        t = "BTS70012" if net in HI else "BTS7004"
        out.append(dict(ref=u, net=net, type=t, I=cur[net], P=cur[net] ** 2 * R_ON[t]))
    return out


def copper_fields(board, cur, th, diel, res, feed_res):
    """verify_copper solve for +12V and each loaded output with this case's currents."""
    base = VC.board_cfg("B")["nets"]
    fields, rs = [], []
    for net, ncfg in base.items():
        if net == "+12V":
            net_of = {v: k for k, v in {**HI, **MED}.items()}
            src = [s[:2] + (cur[net_of[s[0]]],) for s in ncfg["src"]]
            src = [s for s in src if s[2] > 0]
            c = dict(ncfg, src=src, I=sum(s[2] for s in src))
            r, f = VC.solve_net(board, net, c, feed_res, th, diel)
        else:
            if cur[net] <= 0:
                continue
            c = dict(ncfg, I=cur[net])
            r, f = VC.solve_net(board, net, c, res, th, diel)
        rs.append(r)
        fields.append(f)
    return rs, fields


class Thermal:
    def __init__(self, board, th, diel, res):
        self.board, self.th, self.diel, self.res = board, th, diel, res
        bb = board.GetBoardEdgesBoundingBox()
        x0, y0 = VC.mm(bb.GetX()), VC.mm(bb.GetY())
        self.g = g = VC.Grid(x0, y0, x0 + VC.mm(bb.GetWidth()), y0 + VC.mm(bb.GetHeight()), res)
        edge = np.zeros((g.ny, g.nx), bool)
        ps = pcbnew.SHAPE_POLY_SET()
        board.GetBoardPolygonOutlines(ps)
        VC.fill_chains(g, edge, VC.polyset_chains(ps))
        self.edge = edge
        L = VC.CU
        cov = {n: np.zeros((g.ny, g.nx), bool) for n in L}
        lid = {n: board.GetLayerID(n) for n in L}
        for z in board.Zones():
            if z.GetIsRuleArea():
                continue
            for n in L:
                if z.IsOnLayer(lid[n]):
                    VC.fill_chains(g, cov[n], VC.polyset_chains(z.GetFilledPolysList(lid[n])))
        self.holes = []
        for t in board.GetTracks():
            cls = t.GetClass()
            if cls == "PCB_VIA":
                v = t.Cast()
                x, y = VC.mm(v.GetPosition().x), VC.mm(v.GetPosition().y)
                w = VC.mm(v.GetWidth(lid["F.Cu"]))
                vl = [n for n in L if v.IsOnLayer(lid[n])]
                for n in vl:
                    i0, j0, d2 = VC.disc(g, x, y, w / 2)
                    cov[n][j0:j0 + d2.shape[0], i0:i0 + d2.shape[1]] |= d2 <= (w / 2) ** 2
                self.holes.append((x, y, VC.mm(v.GetDrillValue()), vl))
            elif t.GetLayerName() in cov:
                if cls == "PCB_ARC":
                    a = t.Cast()
                    p = [a.GetStart(), a.GetMid(), a.GetEnd()]
                    for s, e in zip(p, p[1:]):
                        VC.fill_segment(g, cov[t.GetLayerName()], VC.mm(s.x), VC.mm(s.y), VC.mm(e.x), VC.mm(e.y),
                                        VC.mm(t.GetWidth()))
                else:
                    VC.fill_segment(g, cov[t.GetLayerName()], VC.mm(t.GetStart().x), VC.mm(t.GetStart().y),
                                    VC.mm(t.GetEnd().x), VC.mm(t.GetEnd().y), VC.mm(t.GetWidth()))
        for fp in board.GetFootprints():
            for p in fp.Pads():
                if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                    continue
                for n in L:
                    if p.IsOnLayer(lid[n]):
                        VC.fill_chains(g, cov[n], VC.pad_poly(p, lid[n]))
                if p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH and p.GetDrillSize().x > 0:
                    self.holes.append((VC.mm(p.GetPosition().x), VC.mm(p.GetPosition().y),
                                       VC.mm(p.GetDrillSize().x), [n for n in L if p.IsOnLayer(lid[n])]))
        self.cov = {n: cov[n] & edge for n in L}
        # nodes
        self.nl = len(L)
        self.ids = -np.ones((self.nl, g.ny, g.nx), np.int64)
        ncell = int(edge.sum())
        for k in range(self.nl):
            self.ids[k][edge] = np.arange(k * ncell, (k + 1) * ncell)
        self.ncell = ncell
        self.N = ncell * self.nl + 1                 # + the J1 terminal / bar node
        self.term = self.N - 1
        j1 = board.FindFootprintByReference("J1")
        self.j1_nodes = []
        for p in j1.Pads():
            if p.GetDrillSize().x > 0:
                i, j = g.cell(VC.mm(p.GetPosition().x), VC.mm(p.GetPosition().y))
                self.j1_nodes += [int(self.ids[k][j, i]) for k in range(self.nl) if self.ids[k][j, i] >= 0]

    def matrix(self, kpad, htop, hbot, bar=True):
        g, L, th, diel = self.g, VC.CU, self.th, self.diel
        A = (self.res * 1e-3) ** 2
        rows, cols, vals = [], [], []
        dz = [diel.get(n, 0.0) for n in L]          # dielectric below layer k
        for k, n in enumerate(L):
            share = (dz[k] if k < self.nl - 1 else 0) / 2 + (dz[k - 1] if k > 0 else 0) / 2
            s = np.where(self.cov[n], K_CU * th[n], 0.0) + K_FR4 * share
            ii = self.ids[k]
            for a, b, sa, sb in ((ii[:, :-1], ii[:, 1:], s[:, :-1], s[:, 1:]), (ii[:-1, :], ii[1:, :], s[:-1, :], s[1:, :])):
                m = (a >= 0) & (b >= 0)
                rows.append(a[m])
                cols.append(b[m])
                vals.append(2 * sa[m] * sb[m] / (sa[m] + sb[m]))
            if k < self.nl - 1:
                a, b = self.ids[k], self.ids[k + 1]
                m = (a >= 0) & (b >= 0)
                rows.append(a[m])
                cols.append(b[m])
                vals.append(np.full(int(m.sum()), K_FR4 * A / dz[k]))
        zpos, z = {}, 0.0
        for n in L:
            zpos[n] = z
            z += th[n] + diel.get(n, 0.0)
        for (x, y, d, vl) in self.holes:
            i, j = g.cell(x, y)
            ks = [L.index(n) for n in vl]
            for ka, kb in zip(ks, ks[1:]):
                a, b = self.ids[ka][j, i], self.ids[kb][j, i]
                if a < 0 or b < 0:
                    continue
                length = abs(zpos[L[kb]] - zpos[L[ka]])
                rows.append(np.array([a]))
                cols.append(np.array([b]))
                vals.append(np.array([K_CU * math.pi * (d * 1e-3 + TPLATE) * TPLATE / length]))
        rows.append(np.full(len(self.j1_nodes), self.term))
        cols.append(np.array(self.j1_nodes))
        vals.append(np.full(len(self.j1_nodes), G_PIN))
        G = sp.coo_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))),
                          shape=(self.N, self.N)).tocsr()
        G = G + G.T
        # boundaries (to the sink temperature)
        ped = np.zeros((g.ny, g.nx), bool)
        for (a, b, c, d) in PED_B:
            i0, i1, j0, j1 = g.win(a - PED_MARGIN, c - PED_MARGIN, b + PED_MARGIN, d + PED_MARGIN)
            xs = (g.xc >= a - PED_MARGIN) & (g.xc <= b + PED_MARGIN)
            ys = (g.yc >= c - PED_MARGIN) & (g.yc <= d + PED_MARGIN)
            ped |= np.outer(ys, xs)
        ped &= self.edge
        self.ped = ped
        gb = np.zeros(self.N)
        bot = self.ids[self.nl - 1]
        gb[bot[ped]] += A * kpad / 1.0e-3
        gb[bot[self.edge & ~ped]] += A * hbot
        gb[self.ids[0][self.edge]] += A * htop
        self.gbar = np.zeros(self.N)
        self.gbar[self.term] = G_BAR if bar else 0.0
        D = sp.diags(np.asarray(G.sum(axis=1)).ravel() + gb + self.gbar)
        return (D - G).tocsc(), gb

    def heat(self, fields, chips, joints, Tcell=None):
        """W per node: copper I^2R per layer (scaled to temperature if Tcell is given), chips on F.Cu, joints."""
        g, L = self.g, VC.CU
        Q = np.zeros(self.N)
        for f in fields:
            fg = f["g"]
            for k, n in enumerate(L):
                q = f["q_layers"][n] + (f["via_q"] / 2 if n in ("In1.Cu", "In2.Cu") else 0)
                J, I = np.nonzero(q > 0)
                ci = np.clip(((fg.xc[I] - g.x0) / g.res).astype(int), 0, g.nx - 1)
                cj = np.clip(((fg.yc[J] - g.y0) / g.res).astype(int), 0, g.ny - 1)
                w = q[J, I] * (fg.res * 1e-3) ** 2
                ci, cj = self.snap(n, ci, cj)                 # heat goes into this layer's copper, never bare FR-4
                node = self.ids[k][cj, ci]
                ok = node >= 0
                if Tcell is not None:
                    w = w * (1 + VC.ALPHA * (Tcell[node[ok]] - 20.0)) / 1.0
                    np.add.at(Q, node[ok], w)
                else:
                    np.add.at(Q, node[ok], w[ok])
        self.q_copper = Q.copy()
        for c in chips:
            x, y = c["xy"]
            wx, wy = EP[c["type"]]
            xs = (g.xc >= x - wx / 2) & (g.xc <= x + wx / 2)
            ys = (g.yc >= y - wy / 2) & (g.yc <= y + wy / 2)
            m = np.outer(ys, xs) & self.edge & self.cov["F.Cu"]
            nodes = self.ids[0][m]
            c["nodes"] = nodes
            Q[nodes] += c["P"] / len(nodes)
        for (ref, P) in joints:            # J1: into the terminal node; T1-T8: over the terminal's pad copper
            if ref == "J1":
                Q[self.term] += P
                continue
            nodes = self.pad_nodes(ref)
            Q[nodes] += P / len(nodes)
        return Q

    def snap(self, layer, ci, cj):
        """Move each (ci, cj) that is not copper on `layer` to the nearest copper cell within 2 cells (the current
        grid and this grid rasterise hole / clearance edges differently)."""
        cov = self.cov[layer]
        ci, cj = ci.copy(), cj.copy()
        bad = ~cov[cj, ci]
        for r in (1, 2):
            if not bad.any():
                break
            for di in range(-r, r + 1):
                for dj in range(-r, r + 1):
                    if max(abs(di), abs(dj)) != r or not bad.any():
                        continue
                    ni = np.clip(ci + di, 0, self.g.nx - 1)
                    nj = np.clip(cj + dj, 0, self.g.ny - 1)
                    ok = bad & cov[nj, ni]
                    ci[ok], cj[ok] = ni[ok], nj[ok]
                    bad &= ~ok
        return ci, cj

    def pad_nodes(self, ref):
        g, L = self.g, VC.CU
        fp = self.board.FindFootprintByReference(ref)
        nodes = []
        for p in fp.Pads():
            for k in (0, self.nl - 1):
                lid = self.board.GetLayerID(L[k])
                if p.IsOnLayer(lid):
                    m = np.zeros((g.ny, g.nx), bool)
                    VC.fill_chains(g, m, VC.pad_poly(p, lid))
                    m &= self.cov[L[k]]
                    nodes += list(self.ids[k][m])
        return np.array([n for n in nodes if n >= 0], np.int64)


def run_case(board, th, diel, case, a, T, plots=None):
    cur, i_a = case_currents(case)
    chips = chip_list(cur)
    for c in chips:
        fp = board.FindFootprintByReference(c["ref"])
        c["xy"] = (VC.mm(fp.GetPosition().x), VC.mm(fp.GetPosition().y))
    i_b = sum(cur.values())
    rs, fields = copper_fields(board, cur, th, diel, a.cu_res, a.feed_res)
    r_bar = VC.RHO * 1.31 * 113.4e-3 / (20e-3 * 5e-3)
    joints = [("J1", R_JOINT * i_b ** 2 + 0.5 * r_bar * 150.0 ** 2)]   # joint + half the bar at 150 A
    for i, net in enumerate(list(HI) + list(MED)):
        joints.append((f"T{i + 1}", (2 if net in HI else 1) * R_JOINT * cur[net] ** 2))
    p_chip = sum(c["P"] for c in chips)
    p_joint = sum(j[1] for j in joints)
    # A boards (car case only): their share of the feed spread over 16 outputs, drivers + copper (verify_copper
    # board A: 2.2 W at 60 A per board) - an estimate for the box total only
    p_a = 0.0
    if i_a > 0:
        ia = i_a / 16
        p_a = 16 * ia ** 2 * (1.80 / 2 / 7.5 ** 2) + 2 * 2.2 * (i_a / 2 / 60.0) ** 2
    p_ext = 3.2 * ((i_b + i_a) / 150.0) ** 2
    Amat, gb = T.matrix(a.kpad, a.htop, a.hbot, not a.no_bar)
    lu = spla.splu(Amat)
    out = dict(case=case, I_B=i_b, I_A=i_a, kpad=a.kpad, air=a.air, res=a.res)
    Tn = None
    for it in range(3):
        Q = T.heat(fields, chips, joints, Tn)
        p_cu = float(T.q_copper.sum())
        p_box = p_chip + p_cu + p_joint + p_a + p_ext
        tsink = T_CABIN + R_SYS[a.air] * p_box
        Tn = lu.solve(Q + gb * tsink + T.gbar * (tsink + DT_A1))
    # without the copper loss (same sink temperature): the copper's own share of the hot spot
    Q0 = Q - T.q_copper
    T0 = lu.solve(Q0 + gb * tsink + T.gbar * (tsink + DT_A1))
    g = T.g
    lay = {}
    for k, n in enumerate(VC.CU):
        f = np.full((g.ny, g.nx), np.nan)
        f[T.edge] = Tn[T.ids[k][T.edge]]
        j, i = np.unravel_index(np.nanargmax(f), f.shape)
        lay[n] = dict(t_max=round(float(np.nanmax(f)), 1), at=(round(float(g.xc[i]), 1), round(float(g.yc[j]), 1)))
    kmax = int(np.argmax(Tn[:-1]))
    dcu = Tn - T0
    for c in chips:
        top = float(Tn[c["nodes"]].max())
        c["t_board"] = round(top, 1)
        c["tj"] = round(top + c["P"] * RTHJC[c["type"]], 1)
        c.pop("nodes")
    hot = max(chips, key=lambda c: c["tj"])
    # presim (docs/system-verification.md 6): what the board's own MCP9808 (U6) reads, for the firmware's warn /
    # critical limits: the F.Cu cell under its footprint centre
    fp6 = board.FindFootprintByReference("U6")
    x6, y6 = VC.mm(fp6.GetPosition().x), VC.mm(fp6.GetPosition().y)
    i6, j6 = int(np.argmin(abs(g.xc - x6))), int(np.argmin(abs(g.yc - y6)))
    n6 = T.ids[0][j6, i6]
    t_sensor = round(float(Tn[n6]), 1) if n6 >= 0 else None
    out.update(p_chip=round(p_chip, 2), p_copper=round(p_cu, 2), p_joints=round(p_joint, 2), p_a_boards=round(p_a, 2),
               p_bars_contacts=round(p_ext, 2), p_box=round(p_box, 2), t_sink=round(tsink, 1),
               laminate_max=round(float(Tn[:-1].max()), 1), t_j1=round(float(Tn[-1]), 1),
               laminate_at=lay[VC.CU[kmax // T.ncell]]["at"], laminate_layer=VC.CU[kmax // T.ncell],
               copper_rise_max=round(float(dcu[:-1].max()), 1), copper_rise_at_hot=round(float(dcu[kmax]), 1),
               layers=lay, chips=[{k: c[k] for k in ("ref", "net", "type", "I", "P", "t_board", "tj")} for c in chips],
               hottest_chip=hot["ref"], tj_max=hot["tj"], t_sensor_u6=t_sensor,
               feed=[dict(net=r["net"], I=round(r["I"], 1), drop_mv=round(r["drop_mv"], 1), p_w=round(r["power_w"], 2))
                     for r in rs])
    out["pass"] = dict(tj=out["tj_max"] <= LIMITS["tj"], laminate=out["laminate_max"] <= LIMITS["laminate"])
    if plots:
        plot(plots, case, a, T, Tn, dcu, out, board)
    return out


def plot(folder, case, a, T, Tn, dcu, out, board):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    g = T.g
    os.makedirs(folder, exist_ok=True)
    fig, ax = plt.subplots(1, 3, figsize=(18, 5.6))
    ext = (g.x0, g.x0 + g.nx * g.res, g.y0 + g.ny * g.res, g.y0)
    for k, (n, axx) in enumerate(((VC.CU[0], ax[0]), (VC.CU[-1], ax[1]))):
        f = np.full((g.ny, g.nx), np.nan)
        f[T.edge] = Tn[T.ids[k * (T.nl - 1)][T.edge]]
        im = axx.imshow(f, extent=ext, cmap="inferno", vmin=out["t_sink"], vmax=max(out["laminate_max"], out["t_sink"] + 1))
        axx.set_title(f"{n} temperature (C), case {case}")
        fig.colorbar(im, ax=axx, shrink=0.8)
        axx.contour(g.xc, g.yc, T.ped, levels=[0.5], colors="c", linewidths=0.8)
    f = np.full((g.ny, g.nx), np.nan)
    f[T.edge] = np.max([dcu[T.ids[k][T.edge]] for k in range(T.nl)], axis=0)
    im = ax[2].imshow(f, extent=ext, cmap="viridis")
    ax[2].set_title("rise caused by the copper I2R (K)")
    fig.colorbar(im, ax=ax[2], shrink=0.8)
    for axx in ax:
        for c in out["chips"]:
            fp = board.FindFootprintByReference(c["ref"])
            axx.annotate(c["ref"], (VC.mm(fp.GetPosition().x), VC.mm(fp.GetPosition().y)), color="w", fontsize=7)
        axx.set_aspect("equal")
    fig.suptitle(f"board B, {case}: B {out['I_B']:.0f} A, sink {out['t_sink']} C ({a.air}), pad k {a.kpad}; "
                 f"Tj max {out['tj_max']} C ({out['hottest_chip']}), laminate max {out['laminate_max']} C")
    fig.tight_layout()
    fig.savefig(os.path.join(folder, f"thermal-board-b-{case}-{a.air}.png"), dpi=110)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", nargs="+", default=["feed150", "feed150hi", "feed150lo", "car", "rating"])
    ap.add_argument("--res", type=float, default=0.4)
    ap.add_argument("--cu-res", type=float, default=0.2)
    ap.add_argument("--feed-res", type=float, default=0.3)
    ap.add_argument("--kpad", type=float, default=3.0)
    ap.add_argument("--htop", type=float, default=3.0)
    ap.add_argument("--hbot", type=float, default=K_AIR / 4e-3 + 1.0)
    ap.add_argument("--air", default="fans", choices=sorted(R_SYS))
    ap.add_argument("--no-bar", action="store_true", help="J1 terminal adiabatic (no BATT bar heat path)")
    ap.add_argument("--outer-um", type=float)
    ap.add_argument("--inner-um", type=float)
    ap.add_argument("--path")
    ap.add_argument("--plots")
    ap.add_argument("--json")
    a = ap.parse_args()
    path = a.path or os.path.join(REPO, "hardware/board-b-max/dingoPDM-Max.kicad_pcb")
    board = pcbnew.LoadBoard(path)
    th, diel = VC.stackup(path)
    th, ordered, label = VC.copper_order.apply(th, "B", a.outer_um, a.inner_um)   # default: the ORDERED copper
    T = Thermal(board, th, diel, a.res)
    print(f"board B thermal: {label}")
    print(f"board B thermal: {path}; copper um " + ", ".join(f"{n} {th[n] * 1e6:.1f}" for n in VC.CU) +
          f"; cell {a.res} mm, {T.N} nodes; gap pad k {a.kpad}; air {a.air}; h top {a.htop}, bottom {a.hbot:.1f}")
    res, fails = [], 0
    for case in a.case:
        r = run_case(board, th, diel, case, a, T, a.plots)
        r["copper_um"] = {n: round(th[n] * 1e6, 2) for n in VC.CU}
        r["ordered"] = ordered                       # tools/verify_thermal_box.py refuses a what-if JSON
        res.append(r)
        ok = all(r["pass"].values())
        fails += not ok
        print(f"  {case:9} B {r['I_B']:5.1f} A: P chips {r['p_chip']:.1f} + copper {r['p_copper']:.1f} + joints "
              f"{r['p_joints']:.2f} W (box {r['p_box']:.1f} W) -> sink {r['t_sink']} C | Tj max {r['tj_max']} C "
              f"({r['hottest_chip']}) {'ok' if r['pass']['tj'] else 'FAIL'} | laminate max {r['laminate_max']} C at "
              f"{r['laminate_at']} {r['laminate_layer']} {'ok' if r['pass']['laminate'] else 'FAIL'} | copper I2R "
              f"lifts it {r['copper_rise_at_hot']} K (max {r['copper_rise_max']} K)")
        print("            chips Tj: " + ", ".join(f"{c['ref']} {c['tj']}" for c in r["chips"]) +
              " | feed: " + ", ".join(f"{f['net']} {f['drop_mv']} mV {f['p_w']} W" for f in r["feed"] if f["net"] == "+12V"))
    if a.json:
        with open(a.json, "w") as f:
            json.dump(res, f, indent=1, default=str)
    if not ordered:
        print(f"RESULT WHAT-IF (not the ordered copper, tools/copper_order.py): {fails} case(s) over the limits; "
              "no verdict for the order")
        return 2
    print("RESULT", "PASS" if not fails else f"FAIL ({fails})",
          f"(limits: Tj <= {LIMITS['tj']} C, laminate <= {LIMITS['laminate']} C)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
