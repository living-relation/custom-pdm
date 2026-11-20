"""Presim item 8: manufacturing checks beyond KiCad DRC / the JLCPCB-limit DRC (tools/gen_fab_jlcpcb.py):
via-in-pad, copper / parts to the board edge, silkscreen size, drill / annular ring vs the cheap JLCPCB process,
BOM availability (zero stock without an approved alternate, extended-part count), and whether the boards still match
the ones the enclosure v2c clash check used.

usage (repo root, KiCad 9 python with pcbnew): python tools/verify_dfm.py [--json out.json]
Limits: JLCPCB PCB capabilities page (jlcpcb.com/capabilities/pcb-capabilities, read 2026-11-20): min via drill 0.3 mm
(0.15-0.25 mm at extra cost), via annular ring >= 0.13 mm (4-layer 0.1 mm), trace to board outline >= 0.2 mm (0.3 mm
recommended; 0.4 mm for V-cut), silkscreen line >= 0.15 mm and text height >= 1.0 mm; JLCPCB assembly: parts within
about 3 mm of an edge need edge rails (JLCPCB adds them when it panelises), vias in SMD pads wick solder unless
plugged ("via-in-pad" / epoxy-filled and capped option). The placement / polarity check is tools/verify_cpl.py.
"""
import argparse
import json
import math
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOARDS = {"A": "hardware/board-a/DingoPDM.kicad_pcb", "B": "hardware/board-b-max/dingoPDM-Max.kicad_pcb",
          "IN": "hardware/input-board/input-board.kicad_pcb"}
V2C_EXPORT = "94adcc4"      # main commit the enclosure v2c board STEPs were exported from (docs/enclosure-v2c.md)
RES = []


def add(group, check, value, limit, verdict, note=""):
    RES.append(dict(group=group, check=check, value=value, limit=limit, verdict=verdict, note=note))


def board_checks(key, path):
    import pcbnew
    mm = pcbnew.ToMM
    b = pcbnew.LoadBoard(os.path.join(ROOT, path))
    outline = pcbnew.SHAPE_POLY_SET()
    b.GetBoardPolygonOutlines(outline)
    ol = outline.Outline(0)

    def d_edge(x, y):
        best = 1e9
        n = ol.PointCount()
        for i in range(n):
            a, c = ol.CPoint(i), ol.CPoint((i + 1) % n)
            ax, ay, cx, cy = mm(a.x), mm(a.y), mm(c.x), mm(c.y)
            dx, dy = cx - ax, cy - ay
            L2 = dx * dx + dy * dy or 1e-12
            t = max(0, min(1, ((x - ax) * dx + (y - ay) * dy) / L2))
            best = min(best, math.hypot(x - ax - t * dx, y - ay - t * dy))
        return best
    vias = [t for t in b.GetTracks() if t.GetClass() == "PCB_VIA"]
    # via-in-pad
    vip = {}
    for fp in b.GetFootprints():
        for p in fp.Pads():
            if p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD:
                continue
            bb = p.GetBoundingBox()
            for v in vias:
                if v.GetNetname() == p.GetNetname() and bb.Contains(v.GetPosition()) and p.HitTest(v.GetPosition()):
                    vip.setdefault(fp.GetReference(), set()).add(id(v))
    n_vip = sum(len(s) for s in vip.values())
    parts = ", ".join(f"{r} {len(s)}" for r, s in sorted(vip.items(), key=lambda x: -len(x[1]))[:8])
    add("Via-in-pad", f"board {key}: vias inside SMD pads", f"{n_vip} vias in {len(vip)} parts ({parts})",
        "0, or order plugged + capped vias", "WARN" if n_vip else "PASS",
        "mostly the PROFET / regulator exposed-pad thermal vias: open 0.3 mm vias wick solder from the pad (voids under "
        "the EP, higher RthJC, solder balls on the back). Order JLCPCB 'epoxy filled & capped' (via-in-pad) for this "
        "board, or tented on the back as a cheaper middle way; the heat model assumes unfilled 20 um barrels" if n_vip else "")
    # copper to the outline: KiCad's exact edge_clearance check runs in the JLC-limit DRC (gen_fab_jlcpcb.py)
    fab = {"A": "board-a", "B": "board-b", "IN": "input-board"}[key]
    txt = open(os.path.join(ROOT, "hardware", "fab", fab, "jlcpcb-drc.txt"), encoding="utf-8").read()
    rule = re.search(r'"JLC copper to edge" \(constraint edge_clearance \(min ([0-9.]+)mm\)\)', txt)
    clean = "no violations" in txt
    add("Edge", f"board {key}: copper to the board outline (KiCad edge_clearance, JLC-limit DRC)",
        f"rule {rule.group(1) if rule else '?'} mm: " + ("no violations" if clean else "violations, see jlcpcb-drc.txt"),
        ">= 0.2 mm (JLCPCB)", "PASS" if clean and rule else "FAIL", f"hardware/fab/{fab}/jlcpcb-drc.txt")
    near = sorted({fp.GetReference() for fp in b.GetFootprints() if not fp.IsDNP() and fp.GetAttributes() & pcbnew.FP_SMD
                   and d_edge(mm(fp.GetPosition().x), mm(fp.GetPosition().y)) < 3.0})
    add("Edge", f"board {key}: SMD parts within 3 mm of an edge", f"{len(near)} ({', '.join(near[:10])})",
        "edge rails when panelised (JLCPCB adds 5 mm rails)", "INFO", "order with JLCPCB edge rails / panel")
    # silkscreen
    thin, small = 0, 0
    for d in b.GetDrawings():
        if d.GetLayerName() not in ("F.Silkscreen", "B.Silkscreen"):
            continue
        if d.GetClass() in ("PCB_TEXT",):
            if mm(d.GetTextHeight()) < 1.0:
                small += 1
        elif hasattr(d, "GetWidth") and 0 < mm(d.GetWidth()) < 0.15:
            thin += 1
    for fp in b.GetFootprints():
        for it in fp.GraphicalItems():
            if it.GetLayerName() in ("F.Silkscreen", "B.Silkscreen") and hasattr(it, "GetWidth") and 0 < mm(it.GetWidth()) < 0.15 \
                    and it.GetClass() != "PCB_TEXT":
                thin += 1
        for t in (fp.Reference(), fp.Value()):
            if t.IsVisible() and t.GetLayerName() in ("F.Silkscreen", "B.Silkscreen") and mm(t.GetTextHeight()) < 1.0:
                small += 1
    add("Silkscreen", f"board {key}: lines < 0.15 mm / text < 1.0 mm high", f"{thin} lines, {small} texts",
        "0 (JLCPCB prints them unreadable or drops them)", "PASS" if not (thin or small) else "WARN",
        "cosmetic only: no electrical or assembly effect (the CPL uses the files, not the silk)")
    # drills / annular rings of vias
    dmin = min((mm(v.GetDrillValue()) for v in vias), default=0)
    ring = min(((mm(v.GetWidth(pcbnew.F_Cu)) - mm(v.GetDrillValue())) / 2 for v in vias), default=0)
    small_drills = sum(1 for v in vias if mm(v.GetDrillValue()) < 0.3 - 1e-6)
    add("Drills", f"board {key}: vias ({len(vias)})", f"smallest drill {dmin:.2f} mm ({small_drills} under 0.3 mm), "
        f"smallest annular ring {ring:.3f} mm", "drill >= 0.3 mm (no extra cost), ring >= 0.13 mm", "PASS" if small_drills == 0
        and ring >= 0.13 - 1e-6 else "WARN", "under 0.3 mm JLCPCB charges extra; JLC-limit DRC passes either way")


def bom():
    t = open(os.path.join(ROOT, "docs", "parts-audit.md"), encoding="utf-8").read()
    sec = t[t.find("### 13.2"):]
    sec = sec[:sec.find("\n### ", 10)]
    rows = re.findall(r"^\| ([^|]+) \| (C\d+) \| (\w+) \| (\d+) \| (\d+) \| ([^|]+) \| ([^|]*) \|", sec, re.M)
    short = [(m, lc, st, need, alt.strip()) for m, lc, typ, st, need, _, alt in rows if int(st) < int(need)]
    no_alt = [f"{m.strip()} ({lc}, {st} in stock, {need} per PDM)" for m, lc, st, need, alt in short if alt in ("", "-")]
    ext = sum(1 for r in rows if r[2] == "ext")
    add("BOM", "parts short at JLCPCB for one PDM (stock read 2026-11-16, docs/parts-audit.md 13.2)",
        f"{len(short)} short; without an approved alternate: {len(no_alt)}", "every short part has global sourcing or an "
        "approved alternate (rule: Dan 2026-11-14)", "PASS" if not no_alt else "WARN", "; ".join(no_alt[:6]))
    add("BOM", "JLCPCB extended parts (loading fee each)", f"{ext} of {len(rows)} part types", "information", "INFO",
        "about 3 USD feeder fee per extended part type per order (JLCPCB)")
    add("BOM", "lifecycle (NRND / obsolete)", "not checked automatically: no distributor API in this repo",
        "every part active", "INFO", "parts-audit 13.2 lists stock only; bench / order time: read lifecycle on the "
        "Octopart / Digi-Key pages (Dan 2026-11-11 lookup rule)")


def clash():
    import pcbnew
    import subprocess
    import tempfile
    diffs = []
    for key, path in (("A", BOARDS["A"]), ("B", BOARDS["B"]), ("IN", BOARDS["IN"])):
        old = os.path.join(tempfile.gettempdir(), f"presim_v2c_{key}.kicad_pcb")
        with open(old, "wb") as f:
            f.write(subprocess.run(["git", "-C", ROOT, "show", f"{V2C_EXPORT}:{path}"], capture_output=True, check=True).stdout)
        out = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "board_semdiff.py"), old, os.path.join(ROOT, path)],
                             capture_output=True, text=True).stdout
        m = re.search(r"footprint geometry differences: (\d+)", out)
        diffs.append((key, int(m.group(1)) if m else -1))
    ok = all(n == 0 for _, n in diffs)
    add("3D clash", f"boards vs the ones enclosure v2c was checked with (board STEPs from {V2C_EXPORT})",
        ", ".join(f"{k}: {n} footprint geometry changes" for k, n in diffs), "0 (then the v2c F1 clash result holds: no "
        "unintended overlaps, docs/enclosure-v2c.md)", "PASS" if ok else "WARN",
        "tools/board_semdiff.py (footprint, position, rotation, side, pads); re-export the STEPs and re-run "
        "enclosure-v2c-build after the d2tvs DO-218 change (job d2tvs)" if ok else "re-export STEPs, re-run the v2c build")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json")
    a = ap.parse_args()
    for k, p in BOARDS.items():
        board_checks(k, p)
    bom()
    clash()
    for r in RES:
        print(f"{r['verdict']:<5} [{r['group']}] {r['check']}: {r['value']} (limit {r['limit']})" + (f" - {r['note']}" if r['note'] else ""))
    cnt = {v: sum(r["verdict"] == v for r in RES) for v in ("PASS", "WARN", "FAIL", "INFO")}
    print("TOTAL", cnt)
    if a.json:
        json.dump(RES, open(a.json, "w"), indent=1)
    return 1 if cnt["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
