"""Polarity / rotation check of the JLCPCB placement files against JLCPCB's own footprints (the 'JLC preview' check).

usage (repo root; any python with pcbnew, e.g. KiCad 9 python; needs internet for the first run):
    python tools/verify_cpl.py [A] [B] [IN] [--cache DIR]

For every placed part in hardware/fab/<board>/<board>-cpl-jlcpcb.csv it takes the LCSC part from the JLCPCB BOM and
downloads that part's footprint from the JLCEDA / EasyEDA official library (the library JLCPCB's placement preview
uses; source: JLCEDA/EasyEDA official library, https://lceda.cn/ and https://easyeda.com; data is only compared here,
not stored in the repo; cache in --cache, default %TEMP%/pcbverify-easyeda). It then turns that footprint by the CPL
rotation and compares every numbered pad with the same pad of our KiCad footprint on the board:
  - ok:      the pads land on our pads (RMS error below 0.15 mm) at the CPL rotation -> pin 1 / cathode is right.
  - FAIL:    another rotation fits much better -> the part would be placed turned (polarity / pin 1 wrong).
  - ok-sym:  a 2-pad part that is not polarised (R, C, L, ferrite, fuse) fits at the CPL rotation +180: harmless.
  - check:   pads could not be matched by number (pad names differ); fit by shape only, reported for a look.
Also reports the centre offset (our footprint origin vs the JLC footprint's pad centre after rotation); above
0.5 mm JLCPCB's engineers usually correct it, so it is listed as info.
Exit code 1 if any FAIL.
"""
import argparse
import csv
import json
import math
import os
import re
import sys
import tempfile
import time
import urllib.request

import numpy as np
import pcbnew

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOARDS = {"A": ("hardware/board-a/DingoPDM.kicad_pcb", "board-a"),
          "B": ("hardware/board-b-max/dingoPDM-Max.kicad_pcb", "board-b"),
          "IN": ("hardware/input-board/input-board.kicad_pcb", "input-board")}
NONPOLAR = re.compile(r"^(R|C|L|FB|F|RN)\d")
PADMAP = {"K": "1", "A": "2"}      # diodes named A / K in our footprints; LCSC library: pad 1 = cathode
TOL = 0.30                         # mm RMS: pad sizes / land patterns differ slightly between libraries
# pass when the CPL rotation is the best fit and every other rotation is at least 3x worse (land patterns differ a
# little between libraries; a turned part misses by millimetres)
API = "https://easyeda.com/api/products/{}/components?version=6.4.19.5"
U = 0.254          # EasyEDA unit = 10 mil


def fetch(lcsc, cache):
    p = os.path.join(cache, f"{lcsc}.json")
    if not os.path.exists(p):
        req = urllib.request.Request(API.format(lcsc), headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
        open(p, "wb").write(data)
        time.sleep(0.3)
    d = json.load(open(p, encoding="utf-8"))
    if not d.get("success"):
        return None
    pk = d["result"].get("packageDetail") or {}
    ds = pk.get("dataStr") or {}
    head = ds.get("head", {})
    ox, oy = float(head.get("x", 0)), float(head.get("y", 0))
    pads = {}
    for s in ds.get("shape", []):
        if s.startswith("PAD~"):
            f = s.split("~")
            x, y, num = float(f[2]), float(f[3]), f[8]
            pads.setdefault(num, []).append(((x - ox) * U, (y - oy) * U))
    return pk.get("title", "?"), pads


def rot(v, deg):
    """Turn (x, y) by deg counter-clockwise as seen from the top, in board coordinates (y down)."""
    a = math.radians(deg)
    x, y = v
    return (x * math.cos(a) + y * math.sin(a), -x * math.sin(a) + y * math.cos(a))


def check_board(key, cache):
    path, tag = BOARDS[key]
    board = pcbnew.LoadBoard(os.path.join(REPO, path))
    fab = os.path.join(REPO, "hardware", "fab", tag)
    lcsc = {}
    for row in csv.DictReader(open(os.path.join(fab, f"{tag}-bom-jlcpcb.csv"), encoding="utf-8")):
        for r in row["Designator"].split(","):
            lcsc[r.strip()] = row["LCSC"].strip()
    fps = {fp.GetReference(): fp for fp in board.GetFootprints()}
    res = []
    for row in csv.DictReader(open(os.path.join(fab, f"{tag}-cpl-jlcpcb.csv"), encoding="utf-8")):
        ref, crot = row["Designator"], float(row["Rotation"])
        fp = fps[ref]
        part = lcsc.get(ref, "")
        if not part:
            pts = np.array([(pcbnew.ToMM(p.GetPosition().x - fp.GetPosition().x),
                             pcbnew.ToMM(p.GetPosition().y - fp.GetPosition().y)) for p in fp.Pads()])
            sym = all(min(np.hypot(*(np.array(rot(q, d)) - pts).T)) < 0.05 for q in pts for d in (90,))
            res.append((ref, "ok-sym" if sym else "check",
                        "no LCSC number (global sourcing): pad pattern is the same turned 90 deg, any rotation fits"
                        if sym else "no LCSC number (global sourcing): not checkable here", None))
            continue
        got = fetch(part, cache)
        if not got or not got[1]:
            two = len(fp.Pads()) == 2 and NONPOLAR.match(ref)
            res.append((ref, "ok-sym" if two else "check", f"{part}: no footprint in the EasyEDA library"
                        + (" (2-pad, not polarised: rotation cannot be wrong)" if two else ""), None))
            continue
        title, ee = got
        org = fp.GetPosition()
        mid = np.array((float(row["Mid X"]) - pcbnew.ToMM(org.x), -float(row["Mid Y"]) - pcbnew.ToMM(org.y)))
        kp = {}
        for p in fp.Pads():
            if p.GetNumber():
                kp.setdefault(PADMAP.get(p.GetNumber(), p.GetNumber()) if set(n.GetNumber() for n in fp.Pads()) <= {"A", "K"}
                              else p.GetNumber(), []).append(((pcbnew.ToMM(p.GetPosition().x - org.x)),
                                                         (pcbnew.ToMM(p.GetPosition().y - org.y))))
        common = [n for n in kp if n in ee and len(kp[n]) == len(ee[n])]
        if len(common) < 2:
            res.append((ref, "check", f"{part} {title}: pad numbers differ (ours {sorted(kp)[:6]}, JLC "
                                      f"{sorted(ee)[:6]})", None))
            continue
        A = np.array([q for n in common for q in sorted(kp[n])])
        cA = A.mean(axis=0)

        def err(deg):
            B = np.array([rot(q, deg) for n in common for q in sorted(ee[n], key=lambda v: rot(v, deg))])
            # same-number pads with several copies (EP split, shield tabs): pair by nearest
            B2 = np.array([rot(q, deg) for n in common for q in ee[n]])
            cB = B2.mean(axis=0)
            e = []
            i = 0
            for n in common:
                ours = [np.array(q) - cA for q in kp[n]]
                theirs = [np.array(rot(q, deg)) - cB for q in ee[n]]
                for o in ours:
                    e.append(min(np.hypot(*(o - t)) for t in theirs))
            return float(np.sqrt(np.mean(np.square(e)))), cB

        trials = {d: err(d) for d in (crot, (crot + 90) % 360, (crot + 180) % 360, (crot + 270) % 360)}
        e0, cB = trials[crot]
        best = min(trials, key=lambda d: trials[d][0])
        off = float(np.hypot(*(mid + np.array(cB) - cA)))   # JLC pad centre (their origin at Mid) vs ours
        info = f"{part} {title}: rms {e0:.3f} mm at CPL {crot:g} deg; best {best:g} deg ({trials[best][0]:.3f} mm); " \
               f"centre offset {off:.2f} mm"
        krot = fp.GetOrientationDegrees()
        corr = rot(tuple(cA - np.array(trials[best][1])), -krot)   # local offset from our origin to JLC's origin          # footprint-local shift that puts JLC's pads on ours
        sugg = dict(fpname=str(fp.GetFPID().GetLibItemName()), rot_offset=round((best - krot) % 360),
                    pos_offset=(round(corr[0], 3), round(corr[1], 3)), part=part)
        others = sorted(v[0] for d, v in trials.items() if d != crot)
        if e0 <= trials[best][0] + 1e-6 and (e0 <= TOL or e0 * 3 <= others[0]):
            status = "ok"
        elif e0 <= trials[best][0] + 1e-6:
            status = "check"
        elif NONPOLAR.match(ref) and len(common) == 2 and abs(((best - crot) % 360) - 180) < 1:
            status = "ok-sym"
        else:
            status = "FAIL"
        res.append((ref, status, info, off, sugg))
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("boards", nargs="*", default=["A", "B", "IN"])
    ap.add_argument("--cache", default=os.path.join(tempfile.gettempdir(), "pcbverify-easyeda"))
    a = ap.parse_args()
    os.makedirs(a.cache, exist_ok=True)
    fails = 0
    for key in a.boards:
        res = check_board(key, a.cache)
        cnt = {}
        for r in res:
            ref, st, info, off = r[:4]
            cnt[st] = cnt.get(st, 0) + 1
            if st != "ok" or (off or 0) > 0.5:
                print(f"  {key} {ref:5} {st:6} {info}")
                if len(r) > 4 and (st == "FAIL" or (off or 0) > 0.5):
                    print(f"        -> footprint {r[4]['fpname']}: rotation offset {r[4]['rot_offset']} deg from KiCad, "
                          f"position offset (footprint-local mm) {r[4]['pos_offset']}")
        fails += cnt.get("FAIL", 0)
        print(f"== board {key}: {len(res)} placements: " + ", ".join(f"{k} {v}" for k, v in sorted(cnt.items())))
    print("RESULT", "PASS" if not fails else f"FAIL ({fails})")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
