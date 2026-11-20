"""Presim item 7: EMC / signal integrity as far as tools allow - CAN / USB pair impedance by a 2-D field solver (cross-
check of the IPC-2141A estimate in tools/verify_layout.py), PWM edge spectrum into the load cables, decoupling loop
inductance at the MCU supply pins.

usage (repo root, KiCad 9 python with pcbnew + numpy + scipy): python tools/verify_si.py [--json out.json]

Field solver: 2-D finite differences on the cross-section (cell 10 um), Laplace's equation with the dielectric
interface, the reference plane below and a grounded box far away; C per metre from the charge (Gauss) on each trace,
with and without the dielectric; Z = 1 / (c sqrt(C C0)); differential = 2 x odd-mode. Self-check: a 50 Ohm microstrip
(w 2.95 mm, h 1.6 mm, er 4.4, Wadell / IPC formula) must come out at 50 +- 3 Ohm. FR-4 er 4.4 ASSUMED (as verify_layout).
"""
import argparse
import json
import math
import os
import sys

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
RES = []
C0 = 299792458.0
EPS0 = 8.854e-12
ER = 4.4


def add(group, check, value, limit, verdict, note=""):
    RES.append(dict(group=group, check=check, value=value, limit=limit, verdict=verdict, note=note))


def solve_pair(w, s, h, t, er, single=False, cell=None):
    """Odd-mode (or single-line) impedance of an edge-coupled microstrip over a plane: w, s, h, t in metres.
    Cell: the trace is at least 1 cell thick and 10 cells wide, the dielectric 10 cells high."""
    cell = cell or min(t, w / 10, h / 10)
    W = (2 * w + s) + 12 * h + 4e-3
    H = h + t + 8 * h + 2e-3
    nx, ny = int(W / cell), int(H / cell)
    x = (np.arange(nx) + 0.5) * cell - W / 2
    y = (np.arange(ny) + 0.5) * cell
    X, Y = np.meshgrid(x, y)
    ytr = (Y >= h) & (Y < h + max(t, cell))
    if single:
        c1 = ytr & (abs(X) <= w / 2)
        c2 = np.zeros_like(c1)
    else:
        c1 = ytr & (X >= s / 2) & (X <= s / 2 + w)
        c2 = ytr & (X <= -s / 2) & (X >= -s / 2 - w)

    def cap(eps_r):
        eps = np.where(Y < h, eps_r, 1.0)
        fixed = c1 | c2
        val = np.where(c1, 1.0, np.where(c2, -1.0, 0.0))
        N = nx * ny
        idx = np.arange(N).reshape(ny, nx)
        rows, cols, vals = [], [], []
        b = np.zeros(N)
        for j in range(ny):
            for i in range(nx):
                k = idx[j, i]
                if fixed[j, i]:
                    rows.append(k); cols.append(k); vals.append(1.0); b[k] = val[j, i]
                    continue
                diag = 0.0
                for dj, di in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                    jj, ii = j + dj, i + di
                    if jj < 0:                       # the reference plane at y = 0: V = 0
                        e = eps[j, i]; diag += e; continue
                    if jj >= ny or ii < 0 or ii >= nx:   # far box grounded
                        e = eps[j, i]; diag += e; continue
                    e = 2 * eps[j, i] * eps[jj, ii] / (eps[j, i] + eps[jj, ii])
                    diag += e
                    rows.append(k); cols.append(idx[jj, ii]); vals.append(-e)
                rows.append(k); cols.append(k); vals.append(diag)
        A = sp.csr_matrix((vals, (rows, cols)), shape=(N, N))
        V = spla.spsolve(A, b).reshape(ny, nx)
        # charge on conductor 1: sum of eps * (V1 - Vneighbour) over its boundary (per metre: x eps0)
        q = 0.0
        for j, i in zip(*np.nonzero(c1)):
            for dj, di in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                jj, ii = j + dj, i + di
                if 0 <= jj < ny and 0 <= ii < nx and not fixed[jj, ii]:
                    e = 2 * eps[j, i] * eps[jj, ii] / (eps[j, i] + eps[jj, ii])
                    q += e * (V[j, i] - V[jj, ii])
                elif jj < 0:
                    q += eps[j, i] * V[j, i]
        return q * EPS0
    c, c0 = cap(er), cap(1.0)
    return 1.0 / (C0 * math.sqrt(c * c0))


def pairs():
    import pcbnew
    import verify_copper as VC
    from verify_layout import tracks, zdiff_microstrip
    z50 = solve_pair(2.95e-3, 0, 1.6e-3, 35e-6, ER, single=True)
    u_ = 2.95 / 1.6
    ee = (ER + 1) / 2 + (ER - 1) / 2 / math.sqrt(1 + 12 / u_)
    z_hj = 376.73 / (math.sqrt(ee) * (u_ + 1.393 + 0.667 * math.log(u_ + 1.444)))     # Hammerstad-Jensen, t = 0
    add("Field solver", "self-check: 2.95 mm microstrip on 1.6 mm FR-4 (er 4.4)", f"{z50:.1f} Ohm",
        f"Hammerstad-Jensen {z_hj:.1f} Ohm +- 6 %", "PASS" if abs(z50 / z_hj - 1) <= 0.06 else "FAIL",
        "grid at the trace thickness; the solver reads a few % high (coarse corners), enough for a pass / fail on a pair")
    mm = pcbnew.ToMM
    for key, path in (("A", "hardware/board-a/DingoPDM.kicad_pcb"), ("B", "hardware/board-b-max/dingoPDM-Max.kicad_pcb")):
        full = os.path.join(ROOT, path)
        b = pcbnew.LoadBoard(full)
        th, diel = VC.stackup(full)
        for p, n, target, tol in (("CAN_H", "CAN_L", 120, 0.2), ("USB_D+", "USB_D-", 90, 0.15)):
            tp, tn = tracks(b, p), tracks(b, n)
            if not tp or not tn:
                continue
            a_ = max(tp, key=lambda t: t.GetLength())
            c_ = max(tn, key=lambda t: t.GetLength())
            w = mm(a_.GetWidth())
            L = a_.GetLayerName()
            ax, ay, bx, by = mm(a_.GetStart().x), mm(a_.GetStart().y), mm(a_.GetEnd().x), mm(a_.GetEnd().y)
            cx, cy = (mm(c_.GetStart().x) + mm(c_.GetEnd().x)) / 2, (mm(c_.GetStart().y) + mm(c_.GetEnd().y)) / 2
            d = abs((cx - ax) * (by - ay) - (cy - ay) * (bx - ax)) / max(math.hypot(bx - ax, by - ay), 1e-9)
            s = max(d - w, 0.05)
            if L not in ("F.Cu", "B.Cu"):
                add("Pair impedance", f"board {key} {p}/{n}", f"on {L} (stripline): not solved here", "-", "INFO")
                continue
            h = diel["F.Cu"] if L == "F.Cu" else diel["In2.Cu"]
            t = th[L]
            coupled = s <= 3 * w
            z_fd = 2 * solve_pair(w * 1e-3, s * 1e-3, h, t, ER) if coupled else 2 * solve_pair(w * 1e-3, 0, h, t, ER, single=True)
            z_ipc, _ = zdiff_microstrip(w, s, h * 1e3, t * 1e3)
            length = max(sum(mm(x.GetLength()) for x in tp), sum(mm(x.GetLength()) for x in tn))
            short = length < (50 if "CAN" in p else 4) * 1e3 / 6.7 / 6
            add("Pair impedance", f"board {key} {p}/{n} (w {w:.2f} mm, gap {s:.2f} mm, h {h * 1e3:.3f} mm, {L})",
                f"field solver {z_fd:.0f} Ohm diff (IPC-2141A {z_ipc:.0f}); {length:.0f} mm long",
                f"{target} Ohm +-{tol * 100:.0f} %, or electrically short", "PASS" if short or abs(z_fd / target - 1) <= tol else "WARN",
                "electrically short at its edge rate (verify_layout critical length), so the impedance does not "
                "matter for SI" if short else "longer than the critical length: impedance matters")


def pwm_spectrum():
    """Trapezoidal PWM current into a load cable: envelope of the harmonics (2 I D) |sinc(pi f D T)| |sinc(pi f tr)|;
    above f2 = 1/(pi tr) it falls 40 dB/decade. The PROFETs' slew rate sets tr (data sheets, max = fastest edge)."""
    import presim_parts as P
    for model, i in (("BTS70012-1ESP", 25.0), ("BTS7004-1EPP", 15.0), ("BTS7008-2EPA", 7.5)):
        d = P.PROFET[model]
        tr = 14.4 / d["dvdt"][2]
        f2 = 1 / (math.pi * tr)
        rows = []
        for f in (150e3, 530e3, 5.9e6, 30e6):     # CISPR 25 LW start, MW start, SW, top of the conducted range
            env = 2 * i * 0.5 * (1 / (math.pi * f * 0.5 / 100)) * (1 / (math.pi * f * tr))
            rows.append(f"{f / 1e6:g} MHz {20 * math.log10(env / 1e-6):.0f} dBuA")
        add("PWM spectrum", f"{model} PWM of {i} A at 100 Hz 50 %: edge {tr * 1e6:.0f} us (fastest slew), corner "
            f"{f2 / 1e3:.1f} kHz", "; ".join(rows), "below the CISPR 25 class 3 current-probe limits (lab test)", "INFO",
            "the slow PROFET edges put every AM-band harmonic 40 dB/decade below the corner; the radio bands then "
            "depend on the cable routing and the CAN / MCU noise, not on the PWM edges: chamber test")


def decoupling():
    import pcbnew
    mm = pcbnew.ToMM
    for key, path in (("A", "hardware/board-a/DingoPDM.kicad_pcb"), ("B", "hardware/board-b-max/dingoPDM-Max.kicad_pcb")):
        b = pcbnew.LoadBoard(os.path.join(ROOT, path))
        caps = [(fp, p) for fp in b.GetFootprints() if fp.GetReference().startswith("C") for p in fp.Pads()]
        u4 = [fp for fp in b.GetFootprints() if fp.GetReference() == "U4"][0]
        worst = []
        for p in u4.Pads():
            if p.GetPinFunction() not in ("VDD", "VDDA", "VREF+", "VBAT") or p.GetNetname() in ("", "GND"):
                continue
            px, py = mm(p.GetPosition().x), mm(p.GetPosition().y)
            best = min(((math.hypot(mm(cp.GetPosition().x) - px, mm(cp.GetPosition().y) - py), fp.GetReference())
                        for fp, cp in caps if cp.GetNetname() == p.GetNetname()), default=(99, "-"))
            dist = best[0]
            # loop: trace pad -> cap (0.3 mm wide, partial inductance 0.2 l (ln(2 l / w) + 0.5) nH/mm) + 2 vias x 0.5 nH
            l_nh = 0.2 * dist * (math.log(2 * max(dist, 0.5) / 0.3) + 0.5) + 1.0
            worst.append((l_nh, p.GetNumber(), best[1], dist))
        none = [f"pin {pn} ({p.GetPinFunction()}, net {p.GetNetname()})" for l_, pn, r_, d_ in worst if r_ == "-"
                for p in u4.Pads() if p.GetNumber() == pn]
        if none:
            add("Decoupling", f"board {key}: MCU supply pins with no capacitor on their own net", "; ".join(none),
                "VDDA: 100 nF + 1 uF at the pin (ST DS 6.1.6 power supply scheme, AN4488 2.1)", "WARN",
                "VDDA is fed from +3V3 through a ferrite bead with no capacitor after it (stock dingoPDM / Max the same): "
                "the ADC reference and the VDDA supply sit behind the bead with nothing to hold them; hardware add of "
                "two 0402 / 0603 caps: report to the coordinator")
            worst = [w_ for w_ in worst if w_[2] != "-"]
        worst.sort(reverse=True)
        l, pin, ref, dist = worst[0]
        add("Decoupling", f"board {key}: MCU supply pins ({len(worst)}): worst loop", f"pin {pin} -> {ref} {dist:.1f} mm, "
            f"about {l:.1f} nH", "<= 5 nH (100 nF stays a short above about 7 MHz)", "PASS" if l <= 5 else "WARN",
            "loop = pad-to-cap trace (partial inductance) + 2 plane vias; ground return in the plane below")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json")
    a = ap.parse_args()
    pairs()
    pwm_spectrum()
    decoupling()
    for r in RES:
        print(f"{r['verdict']:<5} [{r['group']}] {r['check']}: {r['value']} (limit {r['limit']})" + (f" - {r['note']}" if r['note'] else ""))
    cnt = {v: sum(r["verdict"] == v for r in RES) for v in ("PASS", "WARN", "FAIL", "INFO")}
    print("TOTAL", cnt)
    if a.json:
        json.dump(RES, open(a.json, "w"), indent=1)
    return 1 if cnt["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
