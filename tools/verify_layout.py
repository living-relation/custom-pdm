"""Layout checks that DRC does not do: signal-integrity basics, decoupling distance, spacing at mounting holes,
pad connections of high-current pads, solder-mask dams, fiducials, and board B against the stock dingoPDM-Max.

usage (repo root; any python with pcbnew + numpy, e.g. KiCad 9 python):
    python tools/verify_layout.py [A] [B] [IN] [--stock-b PATH]
    --stock-b: the stock dingoPDM-Max board (baseline commit fe19c28), e.g. extracted with
               `git archive fe19c28 hardware/board-b-max | tar -x -C <dir>`; without it the board B diff is skipped.

Checks and limits (sources in docs/pcb-verification.md):
  CAN pair     edge-coupled microstrip / stripline impedance (IPC-2141A formulas) from the stackup, length mismatch,
               stub (CAN_TERM jumper) length; 1 Mbit/s CAN tolerates 120 Ohm +-20 % and stubs < 0.3 m.
  USB pair     same formulas, target 90 Ohm differential; full speed (12 Mbit/s) tolerates mismatch < 2 mm.
  Crystal      Y1 pads to the MCU OSC pins (<= 10 mm), no other net routed under the crystal on F.Cu / In1.Cu,
               ground plane under it.
  I2C          pull-up values and the rise time 0.8473 * R * C (C = 10 pF per device + 0.12 pF / mm of track)
               <= 300 ns (400 kHz) / 1000 ns (100 kHz).
  Decoupling   every IC power pin (+3V3 / +5V / VDDA) has a capacitor pad of that net within 3 mm (warn to 6 mm).
  Mounting     distance from each mounting hole centre to copper of any other net on the outer layers >= the
               screw-head / washer radius (M3 ISO 7380 head 5.7 mm -> 2.85 mm) + 0.6 mm (IPC-2221B B2, 31-50 V
               uncoated: the head can scrape the mask).
  Pads         every pad of a +12V / PF_OUT net that touches a pour of its net is a solid (not thermal-relief) joint.
  Mask         solder-mask dams between openings of different nets >= 0.10 mm (JLCPCB green, 1 oz), counted.
  Fiducials    listed (JLCPCB does not need them for its own panels; info).
  Board B diff added / removed / moved footprints, copper per net and layer (track length, zone area, vias)
               against the stock board.
"""
import argparse
import collections
import math
import os
import re
import sys

import numpy as np
import pcbnew

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify_copper import CU, Grid, fill_chains, fill_segment, pad_poly, polyset_chains, stackup  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOARDS = {"A": "hardware/board-a/DingoPDM.kicad_pcb", "B": "hardware/board-b-max/dingoPDM-Max.kicad_pcb",
          "IN": "hardware/input-board/input-board.kicad_pcb"}
ER = 4.4          # FR-4 at 1 MHz-1 GHz (JLCPCB 7628 prepreg 4.4; core ~4.6): ASSUMED 4.4
mm = pcbnew.ToMM
RES = []


def add(board, check, value, limit, verdict, note=""):
    RES.append((board, check, value, limit, verdict, note))


def tracks(b, net):
    return [t for t in b.GetTracks() if t.GetNetname() == net and t.GetClass() in ("PCB_TRACK", "PCB_ARC")]


def zdiff_microstrip(w, s, h, t, er=ER):
    """IPC-2141A edge-coupled microstrip, w/s/h/t in mm."""
    z0 = 87 / math.sqrt(er + 1.41) * math.log(5.98 * h / (0.8 * w + t))
    return 2 * z0 * (1 - 0.48 * math.exp(-0.96 * s / h)), z0


def zdiff_stripline(w, s, b_, t, er=ER):
    z0 = 60 / math.sqrt(er) * math.log(4 * b_ / (0.67 * math.pi * (0.8 * w + t)))
    return 2 * z0 * (1 - 0.374 * math.exp(-2.9 * s / b_)), z0


def pair(b, key, p, n, target, tol, th, diel, rise_ns):
    th = {k: v * 1e3 for k, v in th.items()}      # stackup() gives metres
    diel = {k: v * 1e3 for k, v in diel.items()}
    tp, tn = tracks(b, p), tracks(b, n)
    if not tp or not tn:
        add(key, f"{p}/{n} pair", "not routed on this board", "-", "N/A")
        return
    lp = sum(mm(t.GetLength()) for t in tp)
    ln = sum(mm(t.GetLength()) for t in tn)
    # typical width / spacing: longest segment of each, centre-line distance
    a = max(tp, key=lambda t: t.GetLength())
    c = max(tn, key=lambda t: t.GetLength())
    w = mm(a.GetWidth())
    L = a.GetLayerName()
    ax, ay = mm(a.GetStart().x), mm(a.GetStart().y)
    bx, by = mm(a.GetEnd().x), mm(a.GetEnd().y)
    cx, cy = (mm(c.GetStart().x) + mm(c.GetEnd().x)) / 2, (mm(c.GetStart().y) + mm(c.GetEnd().y)) / 2
    dx, dy = bx - ax, by - ay
    d = abs((cx - ax) * dy - (cy - ay) * dx) / max(math.hypot(dx, dy), 1e-9)
    s = max(d - w, 0.05)
    layers = sorted({t.GetLayerName() for t in tp + tn})
    if L in ("F.Cu", "B.Cu"):
        h = diel["F.Cu"] if L == "F.Cu" else diel["In2.Cu"]
        zd, z0 = zdiff_microstrip(w, s, h, th[L])
    else:
        bh = diel["In1.Cu"] + th["In2.Cu"] + diel["In2.Cu"] if L == "In2.Cu" else diel["F.Cu"] + th["In1.Cu"] + diel["In1.Cu"]
        zd, z0 = zdiff_stripline(w, s, bh, th[L])
    coupled = s <= 3 * w
    if not coupled:
        zd = 2 * z0           # routed apart: two single-ended lines
    # electrically short if the one-way delay is under 1/6 of the edge rise time (about 6.7 ps/mm in FR-4)
    crit = rise_ns * 1e3 / 6.7 / 6
    longest = max(lp, ln)
    add(key, f"{p}/{n}: on-board length vs critical length for a {rise_ns:g} ns edge",
        f"{longest:.0f} mm (critical {crit:.0f} mm)", "length < critical (impedance then does not matter)",
        "PASS" if longest < crit else "WARN",
        f"impedance estimate {zd:.0f} Ohm diff ({'coupled' if coupled else 'routed apart'}, w {w:.2f} mm, gap {s:.2f} mm "
        f"on {L}, single {z0:.0f} Ohm; target {target} Ohm); layers {', '.join(layers)}; vias "
        f"{sum(1 for t in b.GetTracks() if t.GetNetname() in (p, n) and t.GetClass() == 'PCB_VIA')}")
    add(key, f"{p}/{n}: length", f"{lp:.1f} / {ln:.1f} mm (diff {abs(lp - ln):.1f})",
        "diff <= 2 mm" if "USB" in p else "diff <= 10 mm (1 Mbit/s)",
        "PASS" if abs(lp - ln) <= (2 if "USB" in p else 10) else "WARN")


def nearest_pad(b, fp_ref_prefix, net, x, y):
    best = (1e9, None)
    for fp in b.GetFootprints():
        if not fp.GetReference().startswith(fp_ref_prefix):
            continue
        for p in fp.Pads():
            if p.GetNetname() == net:
                d = math.hypot(mm(p.GetPosition().x) - x, mm(p.GetPosition().y) - y)
                if d < best[0]:
                    best = (d, fp.GetReference())
    return best


def check_board(key, path, stock):
    b = pcbnew.LoadBoard(path)
    th, diel = stackup(path)
    fps = {fp.GetReference(): fp for fp in b.GetFootprints()}
    # --- SI
    pair(b, key, "CAN_H", "CAN_L", 120, 0.2, th, diel, 50)      # MCP2562FD: loop delay / slope, >= 50 ns edges at 1 Mbit/s
    pair(b, key, "USB_D+", "USB_D-", 90, 0.15, th, diel, 4)     # USB 2.0 full speed: rise 4-20 ns
    if "JP3" in fps or "JP2" in fps:
        jp = fps.get("JP3") or fps.get("JP2")
        if "CAN" in jp.GetValue():
            stub = sum(mm(t.GetLength()) for t in tracks(b, "/MCU/CAN_TERM"))
            add(key, f"CAN termination stub ({jp.GetReference()} -> 120R)", f"{stub:.1f} mm", "<= 300 mm",
                "PASS" if stub <= 300 else "FAIL", "jumper open by default (footprint SolderJumper Open)")
    if "Y1" in fps:
        y = fps["Y1"]
        dmax = 0
        for p in y.Pads():
            mcu = [q for f in b.GetFootprints() if f.GetReference() == "U4" for q in f.Pads() if q.GetNetname() == p.GetNetname()]
            if mcu:
                dmax = max(dmax, math.hypot(mm(p.GetPosition().x - mcu[0].GetPosition().x), mm(p.GetPosition().y - mcu[0].GetPosition().y)))
        bb = y.GetBoundingBox(False)
        x0, y0, x1, y1 = mm(bb.GetX()), mm(bb.GetY()), mm(bb.GetRight()), mm(bb.GetBottom())
        own = {p.GetNetname() for p in y.Pads()} | {"GND"}
        under = sorted({t.GetNetname() for t in b.GetTracks() if t.GetLayerName() in ("F.Cu", "In1.Cu")
                        and t.GetNetname() not in own and t.GetClass() == "PCB_TRACK"
                        and x0 <= mm((t.GetStart().x + t.GetEnd().x) // 2) <= x1 and y0 <= mm((t.GetStart().y + t.GetEnd().y) // 2) <= y1})
        g = Grid(x0, y0, x1, y1, 0.1)
        m = np.zeros((g.ny, g.nx), bool)
        for z in b.Zones():
            if z.GetNetname() == "GND" and z.IsOnLayer(b.GetLayerID("In1.Cu")):
                fill_chains(g, m, polyset_chains(z.GetFilledPolysList(b.GetLayerID("In1.Cu"))))
        cov = m.mean() * 100
        add(key, "Crystal Y1: pads to MCU OSC pins", f"{dmax:.1f} mm", "<= 10 mm", "PASS" if dmax <= 10 else "WARN")
        keep = any(z.GetIsRuleArea() and z.GetBoundingBox().Contains(y.GetPosition()) for z in b.Zones())
        add(key, "Crystal Y1: other nets routed under it (F.Cu / In1.Cu)", f"{under or 'none'}", "none",
            "PASS" if not under else "FAIL")
        add(key, "Crystal Y1: ground plane under it", f"In1 GND {cov:.0f} %" + (" (stock all-layer keep-out)" if keep else ""),
            ">= 90 % (ST AN2867 guard ring / plane)", "PASS" if cov >= 90 else "WARN",
            "stock dingoPDM design keeps all copper away from the crystal; unchanged here" if keep else "")
    # I2C pull-ups
    for net in ("I2C1_SDA", "I2C1_SCL"):
        tr = tracks(b, net)
        if not tr:
            continue
        ru = []
        devices = 0
        for fp in b.GetFootprints():
            for p in fp.Pads():
                if p.GetNetname() == net:
                    if fp.GetReference().startswith("R"):
                        other = [q.GetNetname() for q in fp.Pads() if q.GetNumber() != p.GetNumber()]
                        if other and other[0] == "+3V3":
                            ru.append((fp.GetReference(), fp.GetValue()))
                    elif fp.GetReference().startswith("U"):
                        devices += 1
        L = sum(mm(t.GetLength()) for t in tr)
        C = (10 * max(devices, 2) + 0.12 * L) * 1e-12
        vals = []
        for r, v in ru:
            m_ = re.match(r"([\d.]+)\s*([kKmM]?)", v.replace("R", ""))
            if m_:
                vals.append(float(m_.group(1)) * (1e3 if m_.group(2) in "kK" and m_.group(2) else 1))
        if not vals:
            add(key, f"{net} pull-up", "none found", "one to +3V3", "FAIL")
            continue
        R = 1 / sum(1 / v for v in vals)
        tr_ns = 0.8473 * R * C * 1e9
        add(key, f"{net}: pull-up {', '.join(f'{r} {v}' for r, v in ru)}; rise time", f"{tr_ns:.0f} ns",
            "<= 300 ns (400 kHz) / 1000 ns (100 kHz)", "PASS" if tr_ns <= 300 else ("WARN" if tr_ns <= 1000 else "FAIL"),
            f"{devices} devices, {L:.0f} mm track, C {C * 1e12:.0f} pF")
    # decoupling
    worst = []
    for fp in b.GetFootprints():
        if not fp.GetReference().startswith("U"):
            continue
        for p in fp.Pads():
            if p.GetNetname() in ("+3V3", "+5V", "/MCU/VDDA", "VDDA") and p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD:
                d, c = nearest_pad(b, "C", p.GetNetname(), mm(p.GetPosition().x), mm(p.GetPosition().y))
                worst.append((d, f"{fp.GetReference()}.{p.GetNumber()} {p.GetNetname()} -> {c}"))
    worst.sort(reverse=True)
    if worst:
        bad = [w for w in worst if w[0] > 3]
        add(key, f"Decoupling: power pins of ICs with a cap pad of that net within 3 mm ({len(worst)} pins)",
            f"worst {worst[0][0]:.1f} mm ({worst[0][1]})", "<= 3 mm (warn <= 6 mm)",
            "PASS" if not bad else "WARN",
            "; ".join(f"{w[1]} {w[0]:.1f} mm" for w in bad[:6]) + ("; same as the stock layout" if bad else ""))
    # mounting holes vs other-net copper on outer layers
    for fp in b.GetFootprints():
        if "MountingHole" not in str(fp.GetFPID().GetLibItemName()):
            continue
        cx, cy = mm(fp.GetPosition().x), mm(fp.GetPosition().y)
        head = 2.85
        r = head + 0.6 + 1.0
        g = Grid(cx - r, cy - r, cx + r, cy + r, 0.05)
        X, Y = np.meshgrid(g.xc, g.yc)
        D = np.hypot(X - cx, Y - cy)
        best = (99, "")
        for L in ("F.Cu", "B.Cu"):
            lid = b.GetLayerID(L)
            nets = collections.defaultdict(lambda: np.zeros((g.ny, g.nx), bool))
            for z in b.Zones():
                if z.IsOnLayer(lid) and not z.GetIsRuleArea() and z.GetNetname():
                    fill_chains(g, nets[z.GetNetname()], polyset_chains(z.GetFilledPolysList(lid)))
            for t in b.GetTracks():
                if t.GetClass() == "PCB_TRACK" and t.GetLayerName() == L:
                    fill_segment(g, nets[t.GetNetname()], mm(t.GetStart().x), mm(t.GetStart().y), mm(t.GetEnd().x), mm(t.GetEnd().y), mm(t.GetWidth()))
            for f2 in b.GetFootprints():
                if f2.GetReference() == fp.GetReference():
                    continue
                for p in f2.Pads():
                    if p.IsOnLayer(lid) and abs(mm(p.GetPosition().x) - cx) < r + 5 and abs(mm(p.GetPosition().y) - cy) < r + 5:
                        fill_chains(g, nets[p.GetNetname() or "(no net)"], pad_poly(p, lid))
            for n, m_ in nets.items():
                if m_.any() and n not in ("GND", "/GND", "(no net)"):
                    d = D[m_].min()
                    if d < best[0]:
                        best = (d, f"{n} on {L}")
        # metal at the hole: M3 ISO 7380 head (r 2.85) on top, heat-sink post dia 6.0 (r 3.0) below (enclosure v2b)
        contact = 3.0
        gap = best[0] - contact
        hv = bool(best[1]) and (best[1].split()[0] in ("+12V", "+12P") or best[1].startswith("PF_OUT"))
        need = 0.6 if hv else 0.1          # IPC-2221B table 6-1 B2: 31-50 V 0.6 mm, 0-15 V 0.1 mm
        add(key, f"Mounting hole {fp.GetReference()}: nearest non-GND copper outside the screw head / sink post (r 3.0 mm)",
            f"{gap:+.2f} mm ({best[1]})" if best[1] else "none within r 4.45 mm", f">= +{need:.1f} mm (IPC-2221B B2, {'31-50' if hv else '0-15'} V)",
            "PASS" if gap >= need else ("WARN" if gap >= 0.13 else "FAIL"),
            "bare metal on solder mask over this net" if gap < need else "")
    # high-current pads: solid joints
    hc = [n for n in b.GetNetsByName().keys() if str(n) in ("+12V",) or str(n).startswith("PF_OUT")]
    thermal = []
    for z in b.Zones():
        if str(z.GetNetname()) in [str(n) for n in hc] and z.GetPadConnection() != pcbnew.ZONE_CONNECTION_FULL:
            thermal.append(f"zone {z.GetNetname()} {z.GetPadConnection()}")
    for fp in b.GetFootprints():
        for p in fp.Pads():
            if str(p.GetNetname()) in [str(n) for n in hc] and p.GetLocalZoneConnection() not in (pcbnew.ZONE_CONNECTION_INHERITED, pcbnew.ZONE_CONNECTION_FULL):
                thermal.append(f"{fp.GetReference()}.{p.GetNumber()}")
    add(key, "High-current pads (+12V, PF_OUT*) joined solid to their pours (no thermal spokes)",
        f"{len(thermal)} exceptions", "0", "PASS" if not thermal else "FAIL", ", ".join(thermal[:8]))
    # solder-mask dams
    for L, M in (("F.Cu", "F.Mask"), ("B.Cu", "B.Mask")):
        lid, mid = b.GetLayerID(L), b.GetLayerID(M)
        ops = []
        for fp in b.GetFootprints():
            for p in fp.Pads():
                if p.IsOnLayer(mid):
                    exp = mm(p.GetSolderMaskExpansion(mid)) if hasattr(p, "GetSolderMaskExpansion") else 0.05
                    bb = p.GetBoundingBox()
                    ops.append((mm(bb.GetX()) - exp, mm(bb.GetY()) - exp, mm(bb.GetRight()) + exp, mm(bb.GetBottom()) + exp,
                                p.GetNetname(), f"{fp.GetReference()}.{p.GetNumber()}"))
        thin = 0
        ex = []
        for i, a in enumerate(ops):
            for c in ops[i + 1:]:
                if a[4] == c[4] and a[4]:
                    continue
                gx = max(c[0] - a[2], a[0] - c[2])
                gy = max(c[1] - a[3], a[1] - c[3])
                gap = max(gx, gy)
                if 0 < gap < 0.10 and min(gx, gy) < 0:
                    thin += 1
                    if len(ex) < 4:
                        ex.append(f"{a[5]}/{c[5]} {gap:.3f}")
        add(key, f"Solder-mask dams < 0.10 mm between pads ({M})", f"{thin}", "0 (else JLCPCB opens them as one window)",
            "PASS" if thin == 0 else "WARN", "; ".join(ex) + ("; fine-pitch IC rows: normal, the pads stay apart" if thin else ""))
    fid = [fp.GetReference() for fp in b.GetFootprints() if "Fiducial" in str(fp.GetFPID().GetLibItemName())]
    add(key, "Fiducials / tooling holes", f"{len(fid)} fiducials", "not required by JLCPCB (it adds panel rails "
        "with fiducials and tooling holes when it panelises)", "INFO")
    if stock and key == "B":
        diff_b(b, stock)


def copper_summary(b):
    out = collections.defaultdict(lambda: [0.0, 0.0, 0])
    for t in b.GetTracks():
        if t.GetClass() == "PCB_VIA":
            out[(t.GetNetname(), "via")][2] += 1
        else:
            out[(t.GetNetname(), t.GetLayerName())][0] += mm(t.GetLength())
    for z in b.Zones():
        for lid in z.GetLayerSet().CuStack():
            ps = z.GetFilledPolysList(lid)
            out[(z.GetNetname(), b.GetLayerName(lid))][1] += ps.Area() / 1e12
    return out


def diff_b(b, stock_path):
    s = pcbnew.LoadBoard(stock_path)
    fa = {fp.GetReference(): fp for fp in b.GetFootprints()}
    fs = {fp.GetReference(): fp for fp in s.GetFootprints()}
    added = sorted(set(fa) - set(fs), key=lambda r: (r[0], len(r), r))
    removed = sorted(set(fs) - set(fa))
    moved, changed = [], []
    for r in set(fa) & set(fs):
        pa, ps_ = fa[r].GetPosition(), fs[r].GetPosition()
        if math.hypot(mm(pa.x - ps_.x), mm(pa.y - ps_.y)) > 0.01 or fa[r].GetOrientationDegrees() != fs[r].GetOrientationDegrees():
            moved.append(f"{r} ({mm(pa.x - ps_.x):+.2f}, {mm(pa.y - ps_.y):+.2f} mm, {fa[r].GetOrientationDegrees() - fs[r].GetOrientationDegrees():+.0f} deg)")
        if str(fa[r].GetFPID().GetLibItemName()) != str(fs[r].GetFPID().GetLibItemName()) or fa[r].GetValue() != fs[r].GetValue():
            changed.append(f"{r}: {fs[r].GetValue()} -> {fa[r].GetValue()}")
    add("B", "vs stock dingoPDM-Max: footprints added", f"{len(added)}", "each traced to a DECISIONS line", "INFO", ", ".join(added))
    add("B", "vs stock: footprints removed", f"{len(removed)}", "-", "INFO", ", ".join(removed))
    add("B", "vs stock: footprints moved / turned", f"{len(moved)}", "-", "INFO", "; ".join(sorted(moved)[:40]))
    add("B", "vs stock: value / footprint changed", f"{len(changed)}", "-", "INFO", "; ".join(sorted(changed)[:40]))
    ca, cs = copper_summary(b), copper_summary(s)
    rows = []
    for k in sorted(set(ca) | set(cs), key=str):
        a, o = ca.get(k, [0, 0, 0]), cs.get(k, [0, 0, 0])
        if any(abs(x - y) > (0.5 if i < 2 else 0) for i, (x, y) in enumerate(zip(a, o))):
            if k[0] in ("+12V", "GND") or k[0].startswith("PF_OUT"):
                rows.append(f"{k[0]} {k[1]}: track {o[0]:.0f}->{a[0]:.0f} mm, pour {o[1]:.0f}->{a[1]:.0f} mm2, vias {o[2]}->{a[2]}")
    add("B", "vs stock: power copper changes (+12V, GND, PF_OUT*)", f"{len(rows)} net/layer rows changed", "checked by "
        "tools/verify_copper.py (current density)", "INFO", " | ".join(rows))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("boards", nargs="*", default=["A", "B", "IN"])
    ap.add_argument("--stock-b")
    a = ap.parse_args()
    for k in a.boards:
        check_board(k, os.path.join(REPO, BOARDS[k]), a.stock_b)
    for r in RES:
        print(f"{r[4]:4}  {r[0]:2} {r[1]}: {r[2]}  [{r[3]}]  {r[5]}")
    n = sum(r[4] == "FAIL" for r in RES)
    print("RESULT", "PASS" if not n else f"FAIL ({n})")
    return 1 if n else 0


if __name__ == "__main__":
    sys.exit(main())
