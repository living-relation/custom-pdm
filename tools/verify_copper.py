"""High-current copper check: DC current density, IR drop, via currents and copper self-heating on the real copper.

usage (repo root; KiCad 9 python with numpy + scipy, e.g. "%LOCALAPPDATA%\\Programs\\KiCad\\9.0\\bin\\python.exe"
       after `python -m pip install --user scipy`; or any python where `import pcbnew` works):
    python tools/verify_copper.py [A] [B] [--res 0.1] [--outer-um 35] [--h 10] [--plots DIR] [--json FILE]

What it does, per board (board A, board B; the input board carries no load current):
  1. Rasterises the copper of each high-current net on every copper layer from the board file: filled zones (as
     stored; tools/gen_fab_jlcpcb.py checks that a refill changes nothing), tracks, arcs, pads, vias. Cell = --res mm.
  2. Builds a resistor network: each cell is a node, neighbours on a layer are joined by the sheet conductance
     sigma * t (square cells); every via / plated hole is a barrel node per layer, joined to the copper ring around
     the hole and to the next layer by the barrel resistance rho * L / (pi * (d + tp) * tp).
  3. Solves the DC field (scipy sparse direct solve) with the real terminals: plated terminal / press-fit holes are
     held at 0 V (the pin touches the whole barrel), driver pins / exposed pads inject or draw the channel current
     spread over the pad copper.  Every output at its rating at the same time (worst case; board B's 184 A of
     ratings is more than the 150 A feed, so the +12V result is an upper bound).
  4. Reports per net: resistance, IR drop and I^2R loss; peak sheet current (A/mm) per layer outside the pads; the
     narrowest equivalent cross-section ('neck'); the via / barrel carrying the most current.
  5. Copper self-heating: all I^2R of the board on one in-plane thermal sheet (copper of every net + FR-4) with
     convection h on both faces (default 10 W/m2K, still air, no heat sink: conservative), gives the peak rise and
     where it is.  The IPC-2221 internal-layer chart (k = 0.024, the most conservative IPC curve; IPC-2152 charts
     run cooler for the same section) gives a second opinion for the neck.

Pass / fail limits (printed with the result):
  - IR drop per output at rating  <= 100 mV (0.8 % of 12 V)   [design target, this file]
  - +12V feed drop (terminal to the farthest driver) <= 100 mV
  - copper hot spot <= 10 K above the board's mean copper self-heating (a neck that runs much hotter than the
    rest of the plane is a layout fault; IPC-2152 designs commonly allow a 10 K rise). The board-wide mean rise
    and the total I^2R are reported for the heat model (docs/heat-analysis.md counts only the driver losses).
  - via barrel: its own I^2R must not heat its middle more than 10 K above its ends (1-D fin, ends held by the
    planes: dT = I^2 rho L^2 / (8 k A^2); 0.4 mm drill / 20 um wall / 1.6 mm -> 22 A). The IPC-2221 external chart
    for the same section (1.9 A, a long-trace chart) is printed as a conservative second opinion; the barrel I^2R
    also goes into the self-heating sheet.

Assumptions (all printed): copper rho 1.72e-8 Ohm m at 20 C (x1.31 at 100 C); via / hole plating 20 um (same as
docs/heat-analysis.md); stackup copper from the board file unless --outer-um / --inner-um override; FR-4 k 0.3,
copper k 390 W/mK.
"""
import argparse
import json
import math
import os
import re
import sys
import time

import numpy as np
import pcbnew
import scipy.sparse as sp
import scipy.sparse.linalg as spla

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RHO = 1.72e-8          # Ohm m, copper at 20 C
ALPHA = 0.00393        # 1/K
TPLATE = 20e-6         # m, via / hole wall plating (ASSUMED, same as docs/heat-analysis.md)
K_CU, K_FR4 = 390.0, 0.3
LIM = dict(out_drop_mv=100.0, feed_drop_mv=100.0, hot_spot_k=10.0, via_dt_k=10.0, via_warn=1.25)
CU = ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"]
nm = pcbnew.FromMM
mm = pcbnew.ToMM


def ch(ref, pads):
    return (ref, [str(p) for p in pads])


# Board configurations: net -> dict(I, src (where the current enters), snk (terminal, held at 0 V))
# Board A: BTS7008-2EPA (TDSO-14): OUT0 = pins 12-14, OUT1 = pins 8-10, VS = EP 15. 7.5 A per output (rating).
A_DRV = {"U8": ("PF_OUT1", "PF_OUT2"), "U11": ("PF_OUT3", "PF_OUT4"), "U10": ("PF_OUT5", "PF_OUT6"),
         "U13": ("PF_OUT7", "PF_OUT8")}
A_J3 = {"PF_OUT1": 8, "PF_OUT2": 7, "PF_OUT3": 10, "PF_OUT4": 9, "PF_OUT5": 6, "PF_OUT6": 5, "PF_OUT7": 4,
        "PF_OUT8": 3}
B_HI = {"U8": "PF_OUT1", "U9": "PF_OUT2", "U10": "PF_OUT3", "U11": "PF_OUT4"}      # BTS70012-1ESP, 31 A
B_MED = {"U23": "PF_OUT5", "U24": "PF_OUT6", "U25": "PF_OUT7", "U26": "PF_OUT8"}   # BTS7004-1EPP, 15 A


def board_cfg(key):
    if key in ("BSTOCK", "B4"):
        # stock dingoPDM-Max (baseline commit fe19c28, extracted by --path) or our board B with only the four
        # BTS70012 loaded: the same 4 x 31 A on the same feed, to compare the +12V copper like for like
        nets = {o: dict(I=31.0, src=[ch(u, range(13, 25))], snk=[ch(f"T{i + 1}", [1])] if key == "B4" else None)
                for i, (u, o) in enumerate(B_HI.items())}
        nets = {"+12V": dict(I=124.0, feed=True, snk=[ch("J1", [1])], src=[ch(u, [25]) + (31.0,) for u in B_HI])}
        return dict(path="hardware/board-b-max/dingoPDM-Max.kicad_pcb", nets=nets)
    if key == "A":
        nets = {}
        for u, (o0, o1) in A_DRV.items():
            nets[o0] = dict(I=7.5, src=[ch(u, [12, 13, 14])], snk=[ch("J3", [A_J3[o0]])])
            nets[o1] = dict(I=7.5, src=[ch(u, [8, 9, 10])], snk=[ch("J3", [A_J3[o1]])])
        nets["+12V"] = dict(I=60.0, feed=True, snk=[ch("J1", [1])],
                            src=[ch(u, [15]) + (15.0,) for u in A_DRV])
        return dict(path="hardware/board-a/DingoPDM.kicad_pcb", nets=nets)
    nets = {}
    for i, (u, o) in enumerate(B_HI.items()):
        nets[o] = dict(I=31.0, src=[ch(u, range(13, 25))], snk=[ch(f"T{i + 1}", [1])])
    for i, (u, o) in enumerate(B_MED.items()):
        nets[o] = dict(I=15.0, src=[ch(u, range(8, 15))], snk=[ch(f"T{i + 5}", [1])])
    nets["+12V"] = dict(I=184.0, feed=True, snk=[ch("J1", [1])],
                        src=[ch(u, [25]) + (31.0,) for u in B_HI] + [ch(u, [15]) + (15.0,) for u in B_MED])
    return dict(path="hardware/board-b-max/dingoPDM-Max.kicad_pcb", nets=nets)


def stackup(path):
    t = open(path, encoding="utf-8").read()
    s = t[t.find("(stackup"):]
    s = s[:s.find("(copper_finish")]
    th, diel, last = {}, {}, None
    for m in re.finditer(r'\(layer "([^"]+)"\s*\(type "([^"]+)"\)(?:\s*\(color "[^"]*"\))?\s*(?:\(thickness ([0-9.]+)\))?', s):
        name, typ, v = m.groups()
        if typ == "copper":
            th[name] = float(v) * 1e-3
            last = name
        elif typ in ("core", "prepreg") and last:
            diel[last] = float(v) * 1e-3          # dielectric below layer `last`
    return th, diel


# ---------------------------------------------------------------- rasterising
class Grid:
    def __init__(self, x0, y0, x1, y1, res):
        self.res = res
        self.x0, self.y0 = x0, y0
        self.nx = int(math.ceil((x1 - x0) / res)) + 1
        self.ny = int(math.ceil((y1 - y0) / res)) + 1
        self.xc = x0 + (np.arange(self.nx) + 0.5) * res
        self.yc = y0 + (np.arange(self.ny) + 0.5) * res

    def win(self, bx0, by0, bx1, by1):
        i0 = max(0, int((bx0 - self.x0) / self.res) - 1)
        i1 = min(self.nx, int((bx1 - self.x0) / self.res) + 2)
        j0 = max(0, int((by0 - self.y0) / self.res) - 1)
        j1 = min(self.ny, int((by1 - self.y0) / self.res) + 2)
        return i0, i1, j0, j1

    def cell(self, x, y):
        return (min(self.nx - 1, max(0, int((x - self.x0) / self.res))),
                min(self.ny - 1, max(0, int((y - self.y0) / self.res))))


def chain_pts(c):
    n = c.PointCount()
    return np.array([[mm(c.CPoint(i).x), mm(c.CPoint(i).y)] for i in range(n)])


def polyset_chains(ps):
    out = []
    for i in range(ps.OutlineCount()):
        out.append(chain_pts(ps.Outline(i)))
        for j in range(ps.HoleCount(i)):
            out.append(chain_pts(ps.Hole(i, j)))
    return out


def fill_chains(g, mask, chains):
    """Even-odd fill of closed point chains (outlines + holes) at cell centres."""
    if not chains:
        return
    allp = np.vstack(chains)
    i0, i1, j0, j1 = g.win(allp[:, 0].min(), allp[:, 1].min(), allp[:, 0].max(), allp[:, 1].max())
    ys = g.yc[j0:j1]
    e = []
    for c in chains:
        if len(c) < 3:
            continue
        e.append(np.hstack([c, np.roll(c, -1, axis=0)]))
    e = np.vstack(e)
    x1, y1, x2, y2 = e.T
    xs = g.xc[i0:i1]
    for jj, y in enumerate(ys):
        hit = (y1 <= y) != (y2 <= y)
        if not hit.any():
            continue
        xi = x1[hit] + (y - y1[hit]) * (x2[hit] - x1[hit]) / (y2[hit] - y1[hit])
        xi.sort()
        row = np.zeros(len(xs), bool)
        for a, b in zip(xi[0::2], xi[1::2]):
            row ^= (xs >= a) & (xs < b)
        mask[j0 + jj, i0:i1] |= row


def fill_segment(g, mask, ax, ay, bx, by, w):
    r = w / 2
    i0, i1, j0, j1 = g.win(min(ax, bx) - r, min(ay, by) - r, max(ax, bx) + r, max(ay, by) + r)
    X, Y = np.meshgrid(g.xc[i0:i1], g.yc[j0:j1])
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = np.zeros_like(X) if L2 == 0 else np.clip(((X - ax) * dx + (Y - ay) * dy) / L2, 0, 1)
    d2 = (X - ax - t * dx) ** 2 + (Y - ay - t * dy) ** 2
    mask[j0:j1, i0:i1] |= d2 <= r * r


def disc(g, x, y, r):
    i0, i1, j0, j1 = g.win(x - r, y - r, x + r, y + r)
    X, Y = np.meshgrid(g.xc[i0:i1], g.yc[j0:j1])
    return i0, j0, (X - x) ** 2 + (Y - y) ** 2


def pad_poly(pad, layer):
    ps = pcbnew.SHAPE_POLY_SET()
    pad.TransformShapeToPolygon(ps, layer, 0, nm(0.005), pcbnew.ERROR_INSIDE)
    return polyset_chains(ps)


class NetCopper:
    """Copper of one net on every layer + its holes."""

    def __init__(self, board, net, res, layers):
        self.net = net
        lid = {n: board.GetLayerID(n) for n in layers}
        items = []
        for t in board.GetTracks():
            if t.GetNetname() == net:
                items.append(t)
        pads = [p for fp in board.GetFootprints() for p in fp.Pads() if p.GetNetname() == net]
        zones = [z for z in board.Zones() if z.GetNetname() == net and not z.GetIsRuleArea()]
        ext = []
        for o in items + pads + zones:
            b = o.GetBoundingBox()
            ext.append((mm(b.GetX()), mm(b.GetY()), mm(b.GetRight()), mm(b.GetBottom())))
        ext = np.array(ext)
        x0, y0 = ext[:, 0].min() - 1, ext[:, 1].min() - 1
        self.g = g = Grid(x0, y0, ext[:, 2].max() + 1, ext[:, 3].max() + 1, res)
        self.layers = layers
        self.mask = {n: np.zeros((g.ny, g.nx), bool) for n in layers}
        for z in zones:
            for n in layers:
                if z.IsOnLayer(lid[n]):
                    fill_chains(g, self.mask[n], polyset_chains(z.GetFilledPolysList(lid[n])))
        self.holes = []          # (x, y, drill, layers, kind, pad)
        for t in items:
            cls = t.GetClass()
            if cls == "PCB_VIA":
                v = t.Cast()
                x, y = mm(v.GetPosition().x), mm(v.GetPosition().y)
                w = mm(v.GetWidth(lid["F.Cu"]))
                vl = [n for n in layers if v.IsOnLayer(lid[n])]
                for n in vl:
                    i0, j0, d2 = disc(g, x, y, w / 2)
                    self.mask[n][j0:j0 + d2.shape[0], i0:i0 + d2.shape[1]] |= d2 <= (w / 2) ** 2
                self.holes.append((x, y, mm(v.GetDrillValue()), vl, "via", None))
            elif cls == "PCB_ARC":
                a = t.Cast()
                p = [a.GetStart(), a.GetMid(), a.GetEnd()]
                n = t.GetLayerName()
                if n in self.mask:
                    for s, e in zip(p, p[1:]):
                        fill_segment(g, self.mask[n], mm(s.x), mm(s.y), mm(e.x), mm(e.y), mm(t.GetWidth()))
            else:
                n = t.GetLayerName()
                if n in self.mask:
                    fill_segment(g, self.mask[n], mm(t.GetStart().x), mm(t.GetStart().y), mm(t.GetEnd().x),
                                 mm(t.GetEnd().y), mm(t.GetWidth()))
        self.padcells = {}       # (ref, num, idx) -> {layer: bool mask in window}
        for p in pads:
            for n in layers:
                if p.IsOnLayer(lid[n]) and p.GetAttribute() != pcbnew.PAD_ATTRIB_NPTH:
                    fill_chains(g, self.mask[n], pad_poly(p, lid[n]))
            if p.GetDrillSize().x > 0 and p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH:
                self.holes.append((mm(p.GetPosition().x), mm(p.GetPosition().y), mm(p.GetDrillSize().x),
                                   [n for n in layers if p.IsOnLayer(lid[n])], "pth", p))
        # drilled holes are not copper in the plane
        for (x, y, d, vl, kind, p) in self.holes:
            i0, j0, d2 = disc(g, x, y, d / 2)
            for n in layers:
                self.mask[n][j0:j0 + d2.shape[0], i0:i0 + d2.shape[1]] &= ~(d2 < (d / 2) ** 2)
        self.pads = pads

    def pad_mask(self, pad, layer_name, board):
        m = np.zeros((self.g.ny, self.g.nx), bool)
        fill_chains(self.g, m, pad_poly(pad, board.GetLayerID(layer_name)))
        return m & self.mask[layer_name]


# ---------------------------------------------------------------- solving
def solve_net(board, net, cfg, res, th, diel, tplate=TPLATE):
    t0 = time.time()
    layers = CU
    cu = NetCopper(board, net, res, layers)
    g = cu.g
    ny, nx = g.ny, g.nx
    nl = len(layers)
    idx = -np.ones((nl, ny, nx), np.int64)
    n = 0
    for k, L in enumerate(layers):
        c = int(cu.mask[L].sum())
        idx[k][cu.mask[L]] = np.arange(n, n + c)
        n += c
    rows, cols, vals = [], [], []

    def add(a, b, gval):
        rows.append(a)
        cols.append(b)
        vals.append(gval)

    # in-plane links
    for k, L in enumerate(layers):
        gs = th[L] / RHO           # sigma * t  [S]
        ii = idx[k]
        for a, b in ((ii[:, :-1], ii[:, 1:]), (ii[:-1, :], ii[1:, :])):
            m = (a >= 0) & (b >= 0)
            add(a[m], b[m], np.full(int(m.sum()), gs))
    # barrels: one node per (hole, layer); ring cells join it
    zpos = {}
    z = 0.0
    for L in layers:
        zpos[L] = z
        z += th[L] + diel.get(L, 0.0)
    barrel = {}
    hole_info = []
    for hi, (x, y, d, vl, kind, p) in enumerate(cu.holes):
        r0, r1 = d / 2, d / 2 + max(res * 1.5, 0.15)
        i0, j0, d2 = disc(g, x, y, r1)
        ring = (d2 >= r0 * r0 * 0.98) & (d2 <= r1 * r1)
        hn = {}
        for L in vl:
            k = layers.index(L)
            sub = idx[k][j0:j0 + d2.shape[0], i0:i0 + d2.shape[1]]
            cells = sub[ring & (sub >= 0)]
            if len(cells) == 0:
                continue
            hn[L] = n
            gs = th[L] / RHO * 4.0 / max(1, len(cells))      # ring -> barrel: ~4 sheet squares in parallel total
            add(np.full(len(cells), n), cells, np.full(len(cells), max(gs, th[L] / RHO * 0.5)))
            n += 1
        ls = [L for L in layers if L in hn]
        segs = []
        for a, b in zip(ls, ls[1:]):
            length = abs(zpos[b] - zpos[a])
            rbar = RHO * length / (math.pi * (d * 1e-3 + tplate) * tplate)
            add(np.array([hn[a]]), np.array([hn[b]]), np.array([1.0 / rbar]))
            segs.append((hn[a], hn[b], 1.0 / rbar))
        barrel[hi] = hn
        hole_info.append((x, y, d, kind, p, segs))
    N = n
    r = np.concatenate(rows)
    c = np.concatenate(cols)
    v = np.concatenate(vals)
    G = sp.coo_matrix((v, (r, c)), shape=(N, N)).tocsr()
    G = G + G.T
    diag = np.asarray(G.sum(axis=1)).ravel()
    Lap = sp.diags(diag) - G

    def pads_of(ref, nums):
        return [p for p in cu.pads if p.GetParentFootprint().GetReference() == ref and p.GetNumber() in nums]

    # Dirichlet at terminal barrels (and their ring copper)
    fixed = np.zeros(N, bool)
    for ref, nums in [s[:2] for s in cfg["snk"]]:
        for hi, (x, y, d, kind, p, segs) in enumerate(hole_info):
            if p is not None and p.GetParentFootprint().GetReference() == ref and p.GetNumber() in nums:
                for L, node in barrel[hi].items():
                    fixed[node] = True
    if not fixed.any():
        raise SystemExit(f"{net}: no sink barrel found")
    # current injection
    b = np.zeros(N)
    srcs = []
    for s in cfg["src"]:
        ref, nums = s[0], s[1]
        cur = s[2] if len(s) > 2 else cfg["I"]
        sign = -1.0 if cfg.get("feed") else 1.0
        cells = []
        for p in pads_of(ref, nums):
            m = cu.pad_mask(p, "F.Cu", board)
            cells.append(idx[0][m])
        cells = np.concatenate(cells) if cells else np.array([], np.int64)
        cells = cells[cells >= 0]
        if len(cells) == 0:
            raise SystemExit(f"{net}: no copper under {ref} pads {nums}")
        np.add.at(b, cells, sign * cur / len(cells))
        srcs.append((ref, cells, cur))
    free = ~fixed
    # floating islands (not connected to the fixed nodes) make the matrix singular: drop them
    A = Lap[free][:, free].tocsc()
    from scipy.sparse.csgraph import connected_components
    ncomp, lab = connected_components(G, directed=False)
    good = np.isin(lab, np.unique(lab[fixed]))
    keep = free & good
    A = Lap[keep][:, keep].tocsc()
    V = np.zeros(N)
    V[keep] = spla.spsolve(A, b[keep])
    lost = b[~good].sum()
    # results
    P = 0.0
    edge_r, edge_c = G.nonzero()
    up = edge_r < edge_c
    er, ec = edge_r[up], edge_c[up]
    ev = np.asarray(G[er, ec]).ravel()
    P = float((ev * (V[er] - V[ec]) ** 2).sum())
    I = cfg["I"]
    res_out = dict(net=net, I=I, nodes=int(N), res_mm=res, power_w=P, lost_current=float(lost))
    drops = []
    for ref, cells, cur in srcs:
        drops.append((ref, float(np.abs(V[cells]).mean()) * 1e3, cur))
    res_out["drops_mv"] = drops
    res_out["drop_mv"] = max(d for _, d, _ in drops)
    res_out["r_mohm"] = P / I ** 2 * 1e3 if not cfg.get("feed") else res_out["drop_mv"] / I
    # sheet current density per layer (A/mm), q (W/m2) on the grid
    excl = np.zeros((ny, nx), bool)
    for p in cu.pads:
        if p.GetParentFootprint().GetReference() in [s[0] for s in cfg["src"]] + [s[0] for s in cfg["snk"]]:
            for L in layers:
                if p.IsOnLayer(board.GetLayerID(L)):
                    excl |= cu.pad_mask(p, L, board)
    for (x, y, d, kind, p, segs) in hole_info:
        if p is not None:
            i0, j0, d2 = disc(g, x, y, d / 2 + 0.6)
            excl[j0:j0 + d2.shape[0], i0:i0 + d2.shape[1]] |= d2 <= (d / 2 + 0.6) ** 2
    Ksum = np.zeros((ny, nx))
    qsum = np.zeros((ny, nx))
    per_layer = {}
    for k, L in enumerate(layers):
        ii = idx[k]
        Vg = np.where(ii >= 0, V[np.maximum(ii, 0)], np.nan)
        gx = np.zeros((ny, nx))
        gy = np.zeros((ny, nx))
        dx = (Vg[:, 1:] - Vg[:, :-1]) / (res * 1e-3)
        dy = (Vg[1:, :] - Vg[:-1, :]) / (res * 1e-3)
        dx = np.nan_to_num(dx)
        dy = np.nan_to_num(dy)
        gx[:, :-1] += dx / 2
        gx[:, 1:] += dx / 2
        gy[:-1, :] += dy / 2
        gy[1:, :] += dy / 2
        E = np.hypot(gx, gy) * (ii >= 0)
        K = E * th[L] / RHO * 1e-3          # A per mm of width
        q = (E ** 2) * th[L] / RHO          # W/m2
        Ksum += K
        qsum += q
        Kx = np.where(excl, 0, K)
        j, i = np.unravel_index(np.argmax(Kx), Kx.shape)
        per_layer[L] = dict(k_max=float(Kx.max()), at=(round(float(g.xc[i]), 2), round(float(g.yc[j]), 2)),
                            cells=int((ii >= 0).sum()))
    res_out["layers"] = per_layer
    Kx = np.where(excl, 0, Ksum)
    j, i = np.unravel_index(np.argmax(Kx), Kx.shape)
    res_out["neck"] = dict(k_sum_max=float(Kx.max()), w_eq_mm=float(I / max(Kx.max(), 1e-9)),
                           at=(round(float(g.xc[i]), 2), round(float(g.yc[j]), 2)))
    # vias / barrels
    worst = (0.0, None)
    nvia = 0
    via_q = np.zeros((ny, nx))
    for (x, y, d, kind, p, segs) in hole_info:
        if kind != "via":
            continue
        nvia += 1
        ib = max([abs(V[a] - V[bn]) * gg for a, bn, gg in segs] or [0.0])
        pv = sum((V[a] - V[bn]) ** 2 * gg for a, bn, gg in segs)
        ci, cj = g.cell(x, y)
        via_q[cj, ci] += pv / (res * 1e-3) ** 2
        lim = via_limit(d)
        if ib / lim > worst[0] / via_limit(worst[1][2] if worst[1] else d):
            worst = (ib, (round(x, 2), round(y, 2), d))
    res_out["vias"] = nvia
    res_out["via_max_a"] = worst[0]
    res_out["via_max_at"] = worst[1]
    res_out["via_limit_a"] = via_limit(worst[1][2]) if worst[1] else None
    res_out["via_ipc_a"] = via_ipc_chart(worst[1][2]) if worst[1] else None
    res_out["vias_over_ipc"] = int(sum(1 for (x, y, d, kind, p, segs) in hole_info if kind == "via" and
                                       max([abs(V[a] - V[bn]) * gg for a, bn, gg in segs] or [0]) > via_ipc_chart(d)))
    res_out["seconds"] = round(time.time() - t0, 1)
    return res_out, dict(g=g, q=qsum + via_q, K=Ksum, excl=excl)


def via_limit(drill_mm, tp=TPLATE, dt=LIM["via_dt_k"], L=1.6e-3):
    """Current that heats a via barrel's middle dt above its ends: both ends sit in copper planes, so the barrel is a
    fin with uniform I^2R: dT = I^2 rho L^2 / (8 k A^2)  ->  I = A sqrt(8 k dT / rho) / L."""
    A = math.pi * (drill_mm * 1e-3 + tp) * tp
    return A * math.sqrt(8 * K_CU * dt / RHO) / L


def via_ipc_chart(drill_mm, tp=TPLATE, dt=LIM["via_dt_k"]):
    """IPC-2221 external chart for the barrel section (a long-trace chart: very conservative for a 1.6 mm barrel)."""
    area_mil2 = math.pi * (drill_mm * 1e-3 + tp) * tp / (0.0254e-3) ** 2
    return 0.048 * dt ** 0.44 * area_mil2 ** 0.725


# ---------------------------------------------------------------- thermal sheet
def board_thermal(board, fields, res, th, h, layers=CU):
    """Copper self-heating: one in-plane sheet for the whole board, Joule heat from every solved net."""
    bb = board.GetBoardEdgesBoundingBox()
    x0, y0 = mm(bb.GetX()), mm(bb.GetY())
    g = Grid(x0, y0, x0 + mm(bb.GetWidth()), y0 + mm(bb.GetHeight()), res)
    edge = np.zeros((g.ny, g.nx), bool)
    ps = pcbnew.SHAPE_POLY_SET()
    board.GetBoardPolygonOutlines(ps)
    fill_chains(g, edge, polyset_chains(ps))
    kt = np.full((g.ny, g.nx), K_FR4 * 1.5e-3)
    for L in layers:
        cov = np.zeros((g.ny, g.nx), bool)
        lid = board.GetLayerID(L)
        for z in board.Zones():
            if z.IsOnLayer(lid) and not z.GetIsRuleArea():
                fill_chains(g, cov, polyset_chains(z.GetFilledPolysList(lid)))
        for t in board.GetTracks():
            if t.GetClass() == "PCB_TRACK" and t.GetLayerName() == L:
                fill_segment(g, cov, mm(t.GetStart().x), mm(t.GetStart().y), mm(t.GetEnd().x), mm(t.GetEnd().y),
                             mm(t.GetWidth()))
        kt += cov * K_CU * th[L]
    Q = np.zeros((g.ny, g.nx))
    for f in fields:
        fg = f["g"]
        J, I = np.nonzero(f["q"] > 0)
        ci = np.clip(((fg.xc[I] - g.x0) / g.res).astype(int), 0, g.nx - 1)
        cj = np.clip(((fg.yc[J] - g.y0) / g.res).astype(int), 0, g.ny - 1)
        np.add.at(Q, (cj, ci), f["q"][J, I] * (fg.res * 1e-3) ** 2)      # W per thermal cell
    Q *= edge
    ids = -np.ones((g.ny, g.nx), np.int64)
    ids[edge] = np.arange(int(edge.sum()))
    N = int(edge.sum())
    rows, cols, vals = [], [], []
    for a, b, ka, kb in ((ids[:, :-1], ids[:, 1:], kt[:, :-1], kt[:, 1:]), (ids[:-1, :], ids[1:, :], kt[:-1, :], kt[1:, :])):
        m = (a >= 0) & (b >= 0)
        rows.append(a[m])
        cols.append(b[m])
        vals.append(2 * ka[m] * kb[m] / (ka[m] + kb[m]))
    G = sp.coo_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(N, N)).tocsr()
    G = G + G.T
    conv = 2 * h * (g.res * 1e-3) ** 2
    A = sp.diags(np.asarray(G.sum(axis=1)).ravel() + conv) - G
    T = spla.spsolve(A.tocsc(), Q[edge])
    dT = np.zeros((g.ny, g.nx))
    dT[edge] = T
    j, i = np.unravel_index(np.argmax(dT), dT.shape)
    return dict(p_total=float(Q.sum()), dt_max=float(dT.max()), dt_mean=float(T.mean()),
                at=(round(float(g.xc[i]), 2), round(float(g.yc[j]), 2)), h=h, res=res), (g, dT)


def ipc2221_dt(I, area_mil2, k=0.024):
    """IPC-2221 I = k dT^0.44 A^0.725 solved for dT (k 0.024 internal = conservative stand-in for IPC-2152)."""
    return (I / (k * area_mil2 ** 0.725)) ** (1 / 0.44)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("boards", nargs="*", default=["A", "B"])
    ap.add_argument("--res", type=float, default=0.1)
    ap.add_argument("--feed-res", type=float, default=0.2)
    ap.add_argument("--outer-um", type=float)
    ap.add_argument("--inner-um", type=float)
    ap.add_argument("--h", type=float, default=10.0)
    ap.add_argument("--plots")
    ap.add_argument("--json")
    ap.add_argument("--nets", nargs="*")
    ap.add_argument("--path", help="board file to use instead of the repo one (e.g. a stock baseline)")
    a = ap.parse_args()
    out = {}
    fails = 0
    for key in a.boards:
        cfg = board_cfg(key)
        path = a.path or os.path.join(REPO, cfg["path"])
        board = pcbnew.LoadBoard(path)
        th, diel = stackup(path)
        if a.outer_um:
            th["F.Cu"] = th["B.Cu"] = a.outer_um * 1e-6
        if a.inner_um:
            th["In1.Cu"] = th["In2.Cu"] = a.inner_um * 1e-6
        print(f"== board {key}: {cfg['path']}  copper um " +
              ", ".join(f"{L} {th[L] * 1e6:.1f}" for L in CU) + f"  plating {TPLATE * 1e6:.0f} um  rho {RHO}")
        rs, fields = [], []
        for net, ncfg in cfg["nets"].items():
            if a.nets and net not in a.nets:
                continue
            r, f = solve_net(board, net, ncfg, a.feed_res if ncfg.get("feed") else a.res, th, diel)
            rs.append(r)
            fields.append(f)
            lim = LIM["feed_drop_mv"] if ncfg.get("feed") else LIM["out_drop_mv"]
            t_tot_mm = sum(th[L] for L in CU if r["layers"][L]["cells"]) * 1e3
            area_mil2 = (r["neck"]["w_eq_mm"] / 0.0254) * (t_tot_mm / 0.0254)
            r["neck"]["ipc2221_int_dt"] = ipc2221_dt(r["I"], area_mil2)
            ok_drop = r["drop_mv"] <= lim
            ok_via = r["vias"] == 0 or r["via_max_a"] <= r["via_limit_a"]
            warn_via = not ok_via and r["via_max_a"] <= r["via_limit_a"] * LIM["via_warn"]
            r["pass_drop"], r["pass_via"], r["warn_via"] = ok_drop, ok_via, warn_via
            fails += (not ok_drop) + (not ok_via and not warn_via)
            lay = " ".join(f"{L[:3]} {r['layers'][L]['k_max']:.1f}" for L in CU)
            print(f"  {net:8} I {r['I']:6.1f} A  drop {r['drop_mv']:6.1f} mV {'ok' if ok_drop else 'FAIL'}  "
                  f"P {r['power_w']:.3f} W  peak A/mm [{lay}]  neck {r['neck']['k_sum_max']:.1f} A/mm at "
                  f"{r['neck']['at']} w_eq {r['neck']['w_eq_mm']:.2f} mm IPC dT {r['neck']['ipc2221_int_dt']:.1f} K  "
                  f"vias {r['vias']} max {r['via_max_a']:.2f} A (fin limit {r['via_limit_a'] or 0:.1f}, IPC chart {r['via_ipc_a'] or 0:.2f}: {r['vias_over_ipc']} over) {'ok' if ok_via else ('WARN' if warn_via else 'FAIL')} at {r['via_max_at']}  "
                  f"[{r['nodes']} nodes, {r['seconds']} s]")
            if ncfg.get("feed"):
                print("           per driver drop mV: " + ", ".join(f"{u} {d:.1f}" for u, d, _ in r["drops_mv"]))
        tr, (tg, dT) = board_thermal(board, fields, 0.25, th, a.h)
        ok_t = tr["dt_max"] - tr["dt_mean"] <= LIM["hot_spot_k"]
        fails += not ok_t
        print(f"  copper self-heating: {tr['p_total']:.2f} W I2R on the board; hot spot {tr['dt_max'] - tr['dt_mean']:.1f} K "
              f"above the board mean at {tr['at']} {'ok' if ok_t else 'FAIL'} (peak {tr['dt_max']:.1f} K, mean "
              f"{tr['dt_mean']:.1f} K with h {a.h} W/m2K both faces and no sink)")
        out[key] = dict(nets=rs, thermal=tr, copper_um={L: th[L] * 1e6 for L in CU})
        if a.plots:
            plots(a.plots, key, fields, tg, dT, board)
    if a.json:
        with open(a.json, "w") as f:
            json.dump(out, f, indent=1, default=str)
    print("RESULT", "PASS" if not fails else f"FAIL ({fails})")
    return 1 if fails else 0


def plots(folder, key, fields, tg, dT, board):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("  (matplotlib missing: no plots)")
        return
    os.makedirs(folder, exist_ok=True)
    ext = [tg.x0, tg.x0 + tg.nx * tg.res, tg.y0 + tg.ny * tg.res, tg.y0]
    K = np.zeros((tg.ny, tg.nx))
    for f in fields:
        fg = f["g"]
        J, I = np.nonzero(f["K"] > 0)
        ci = np.clip(((fg.xc[I] - tg.x0) / tg.res).astype(int), 0, tg.nx - 1)
        cj = np.clip(((fg.yc[J] - tg.y0) / tg.res).astype(int), 0, tg.ny - 1)
        np.maximum.at(K, (cj, ci), f["K"][J, I])
    fig, ax = plt.subplots(1, 2, figsize=(14, 6))
    im = ax[0].imshow(K, extent=ext, cmap="inferno", vmax=np.percentile(K[K > 0], 99.5) if (K > 0).any() else 1)
    fig.colorbar(im, ax=ax[0], label="sheet current, all layers (A/mm)")
    ax[0].set_title(f"board {key}: current density at rated current")
    im = ax[1].imshow(dT, extent=ext, cmap="coolwarm")
    fig.colorbar(im, ax=ax[1], label="copper self-heating rise (K)")
    ax[1].set_title(f"board {key}: I2R self-heating (no sink, h both faces)")
    for x in ax:
        x.set_xlabel("x (mm, board file)")
        x.set_ylabel("y (mm)")
    fig.tight_layout()
    p = os.path.join(folder, f"pcbverify-current-board-{key.lower()}.png")
    fig.savefig(p, dpi=110)
    print("  plot", p)


if __name__ == "__main__":
    sys.exit(main())
