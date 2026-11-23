"""JLCPCB fab + assembly outputs for board A, board B and the input board.

usage (repo root, KiCad 9 python for pcbnew; kicad-cli 10 does the plotting):
    "%LOCALAPPDATA%\\Programs\\KiCad\\9.0\\bin\\python.exe" tools/gen_fab_jlcpcb.py [A] [B] [IN]     (default: all three)

Writes hardware/fab/<board>/ (read-only on the design; plots and checks run on a temp copy):
  gerber/                   Gerbers + Excellon drill (PTH / NPTH), JLCPCB's KiCad settings (see GERBER_OPTS)
  <board>-gerber.zip        the file to upload (git-ignored, *.zip)
  <board>-bom-jlcpcb.csv    assembler BOM: Comment, Designator, Footprint, LCSC
  <board>-cpl-jlcpcb.csv    placement: Designator, Mid X, Mid Y, Layer, Rotation (JLCPCB rotation offsets applied)
  <board>-bom-full.csv      every part: maker, MPN, LCSC, Digi-Key, approved alternates, who fits it
  jlcpcb-drc.txt            DRC against JLCPCB's published limits + worst geometry values
Dates are stripped from Gerber / drill headers so a re-run on an unchanged board gives identical files.

Sources (read 2026-11-16):
  JLCPCB "How to generate Gerber and drill files in KiCad 9" (layers, Protel extensions, X2, netlist attributes,
    4.6 mm, Excellon mm decimal, oval holes 'alternate', absolute origin, separate PTH / NPTH):
    https://jlcpcb.com/help/article/how-to-generate-gerber-and-drill-files-in-kicad-9
  JLCPCB pick-and-place file: Designator, Mid X, Mid Y (mm), Layer (Top / Bottom), Rotation (degrees, positive =
    counter-clockwise): https://jlcpcb.com/help/article/pick-place-file-for-pcb-assembly
  JLCPCB BOM: Comment, Designator, Footprint, LCSC part number:
    https://jlcpcb.com/help/article/how-to-generate-bom-and-centroid-files-from-kicad-8
  JLCPCB capabilities (limits in JLC_LIMITS): https://jlcpcb.com/capabilities/pcb-capabilities
  Rotation offsets: KiBot's JLCPCB table (https://kibot.readthedocs.io/en/latest/notes_position.html), the entries
    that match footprints on these boards, plus Infineon TDSO-14 / TSDSO-24 (pin 1 in the same corner as KiCad's
    TSSOP footprints, so the TSSOP offset).
"""
import csv
import glob
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

import pcbnew

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import copper_order  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.expandvars(r"%LOCALAPPDATA%\Programs\KiCad\10.0\bin\kicad-cli.exe")
BOARDS = {"A": ("board-a", "DingoPDM", "board-a"), "B": ("board-b-max", "dingoPDM-Max", "board-b"),
          "IN": ("input-board", "input-board", "input-board")}
GERBER_OPTS = ["--precision", "6"]                 # defaults kept: Protel extensions, X2, netlist attributes
DRILL_OPTS = ["--format", "excellon", "--drill-origin", "absolute", "--excellon-units", "mm",
              "--excellon-zeros-format", "decimal", "--excellon-oval-format", "alternate", "--excellon-separate-th"]
# KiBot JLCPCB rotation table entries that match these boards (regex on the footprint name) + TDSO / TSDSO
# 2026-11-20 (pcbverify): every entry checked part by part against the LCSC part's own footprint in the JLCEDA /
# EasyEDA library by tools/verify_cpl.py (pads turned by the CPL rotation must land on ours). Changed from KiBot's
# table: SOT-223 180 -> 270 (C15578), JST GH SM horizontal 180 -> 0 (C265421), new: JST GH BM vertical 180
# (C20089173), Molex Micro-Fit 43045 horizontal 180 (C277636); Omron A6S DIP switch 270 (C231310) until hwtemp
# (2026-11-23: the input-board DIP switches became solder jumpers, no part).
ROTATIONS = [(r"^SOT-223", 270), (r"^SOT-23", 180), (r"^SOIC-", 270), (r"^MSOP-", 270), (r"^TSSOP-", 270),
             (r"^LQFP-", 270), (r"^JST_GH_BM", 180), (r"^T?S?DSO-\d+$", 270), (r"^Molex_Micro-Fit_3\.0_43045", 180),
             (r"^D_DO-218AB_Vishay_SM8S", 180)]   # hwprotect 2026-11-20: D2 Bourns SM8S24CA-Q (C1976790), verify_cpl
# Placement centre: JLCPCB puts its footprint's origin (the part centre) on Mid X / Mid Y. Where our KiCad origin is
# a pin instead, shift by this footprint-local offset (mm, KiCad footprint frame; tools/verify_cpl.py measures it).
OFFSETS = [(r"^USB_C_Receptacle_GCT_USB4085", (2.973, 2.18)), (r"^Converter_DCDC_TRACO_TSR-1_THT", (2.54, 0.0)),
           (r"^Molex_Micro-Fit_3\.0_43045-1200", (7.5, 1.5)), (r"^D_DO-218AB_Vishay_SM8S", (1.912, 0.0))]
NOT_PARTS = re.compile(r"MountingHole|DingoFace|SolderJumper|WirePads|Tag-Connect")
PRESS_FIT = {"7461084"}                            # MPNs JLCPCB does not fit (press-fit, see fab-notes)
# Parts with thin stock (MPN -> what was seen, where, when). Sources: docs/order-readiness.md section 4 (live look-ups
# 2026-11-22) and docs/parts-audit.md section 13; the approved alternate comes from the part's own Alternates field.
THIN_STOCK = {
    "LMZM23601V5SILR": "135 at LCSC on 2026-11-22 (C2868357)",
    "SM8S24CA-Q": "400 at Digi-Key on 2026-11-22; LCSC C1976790 not checked",
    "BTS700121ESPXUMA1": "17 at LCSC on 2026-11-22 (C3232444)",
    "ECS-80-18-30Q-CES-TR": "no LCSC number (global sourcing); Digi-Key 50-ECS-80-18-30Q-CES-TRCT-ND",
    "74650074R": "no LCSC number (global sourcing); Digi-Key 732-74650074RCT-ND",
    "CY15B064J-SXE": "0 at LCSC on 2026-11-23 (C2953601, global sourcing); Digi-Key 448-CY15B064J-SXE-ND (hwtemp FRAM)",
}
NO_ALT = "none approved: if JLCPCB cannot get it, quote the board at PCBWay by MPN (`*-bom-full.csv`)"
# JLCPCB limits (capabilities page). 4-layer board, 1 oz outer copper (the stackup is left as it is).
JLC_LIMITS = {
    4: dict(track=0.09, clearance=0.09, smd_pad_gap=0.15, hole=0.15, via_dia=0.25, via_ring=0.05, pth_ring=0.15,
            via_h2h=0.2, pad_h2h=0.45, hole_cu=0.2, pth_track=0.28, edge=0.2, silk_w=0.15, silk_h=1.0),
    2: dict(track=0.10, clearance=0.10, smd_pad_gap=0.15, hole=0.15, via_dia=0.25, via_ring=0.05, pth_ring=0.18,
            via_h2h=0.2, pad_h2h=0.45, hole_cu=0.2, pth_track=0.28, edge=0.2, silk_w=0.15, silk_h=1.0),
}
mm = pcbnew.ToMM


def run(args):
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"{' '.join(args[:4])} ... failed:\n{r.stdout}\n{r.stderr}")
    return r.stdout


def field(fp, name):
    f = next((f for f in fp.GetFields() if f.GetName() == name), None)
    return f.GetText() if f else ""


def strip_dates(folder):
    """Drop the date lines KiCad writes into Gerber / drill headers (comments / optional attributes)."""
    for p in glob.glob(os.path.join(folder, "*")):
        if p.endswith(".gbrjob"):
            os.remove(p)                          # job file: not needed by JLCPCB, full of dates
            continue
        t = open(p, encoding="utf-8", errors="replace").read().splitlines(True)
        keep = [ln for ln in t if "CreationDate" not in ln and not re.match(r"^(G04|;).*\bdate\b", ln, re.I)]
        if keep != t:
            open(p, "w", encoding="utf-8", newline="").write("".join(keep))


def jlc_rotation(fpname, rot):
    off = next((o for pat, o in ROTATIONS if re.search(pat, fpname)), 0)
    return (rot + off) % 360, off


def jlc_offset(fpname, rot):
    """Board-frame shift (mm, y down) from our footprint origin to JLCPCB's part centre."""
    ox, oy = next((o for pat, o in OFFSETS if re.search(pat, fpname)), (0.0, 0.0))
    a = math.radians(rot)                       # KiCad: counter-clockwise on screen, y down
    return ox * math.cos(a) + oy * math.sin(a), -ox * math.sin(a) + oy * math.cos(a)


def parts(board):
    """(footprint, kind) for every footprint; kind: jlc-smt / jlc-tht / press-fit / dnp / not-a-part."""
    out = []
    for fp in board.GetFootprints():
        name = str(fp.GetFPID().GetLibItemName())
        if NOT_PARTS.search(name) or not field(fp, "MPN"):
            kind = "not-a-part"
        elif fp.IsDNP() or fp.IsExcludedFromBOM():
            kind = "dnp"
        elif field(fp, "MPN") in PRESS_FIT:
            kind = "press-fit"
        elif fp.GetAttributes() & pcbnew.FP_THROUGH_HOLE:
            kind = "jlc-tht"
        else:
            kind = "jlc-smt"
        out.append((fp, kind))
    return out


def nat(ref):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", ref)]


def write_bom_cpl(board, out, tag):
    rows, groups, full, glob_src = [], {}, {}, {}
    for fp, kind in parts(board):
        ref, name = fp.GetReference(), str(fp.GetFPID().GetLibItemName())
        if kind in ("jlc-smt", "jlc-tht"):
            if fp.GetLayer() != pcbnew.F_Cu:
                raise SystemExit(f"{ref}: bottom-side assembly not handled (JLCPCB does not mirror like KiCad)")
            rot, off = jlc_rotation(name, fp.GetOrientationDegrees())
            p = fp.GetPosition()
            dx, dy = jlc_offset(name, fp.GetOrientationDegrees())
            rows.append((ref, f"{mm(p.x) + dx:.4f}", f"{-(mm(p.y) + dy):.4f}", "Top", f"{rot:g}", off))
            # no LCSC number = JLCPCB global sourcing: the Comment is the maker part number (what JLCPCB's part
            # search takes), the LCSC cell stays empty; fab-notes.md and the full BOM name these lines
            lcsc = field(fp, "LCSC")
            k = (fp.GetValue() if lcsc else field(fp, "MPN"), name, lcsc)
            groups.setdefault(k, []).append(ref)
            if not lcsc:
                glob_src.setdefault((field(fp, "Manufacturer"), field(fp, "MPN"), field(fp, "Digi-Key_PN"),
                                     field(fp, "Alternates")), []).append(ref)
        if kind != "not-a-part":
            k = (fp.GetValue(), name, field(fp, "Manufacturer"), field(fp, "MPN"), field(fp, "LCSC"),
                 field(fp, "Digi-Key_PN"), field(fp, "Alternates"), kind)
            full.setdefault(k, []).append(ref)
    rows.sort(key=lambda r: nat(r[0]))
    with open(os.path.join(out, f"{tag}-cpl-jlcpcb.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        w.writerows(r[:5] for r in rows)
    with open(os.path.join(out, f"{tag}-bom-jlcpcb.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC"])
        for (value, name, lcsc), refs in sorted(groups.items(), key=lambda kv: nat(sorted(kv[1], key=nat)[0])):
            w.writerow([value, ",".join(sorted(refs, key=nat)), name, lcsc])
    who = {"jlc-smt": "JLCPCB SMT", "jlc-tht": "JLCPCB THT", "dnp": "do not fit",
           "press-fit": "not JLCPCB: press in after delivery (fab-notes.md)"}
    with open(os.path.join(out, f"{tag}-bom-full.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Qty", "Designator", "Value", "Footprint", "Manufacturer", "MPN", "LCSC", "Digi-Key",
                    "Approved alternates", "Fitted by"])
        for k, refs in sorted(full.items(), key=lambda kv: nat(sorted(kv[1], key=nat)[0])):
            value, name, mf, mpn, lcsc, dk, alt, kind = k
            w.writerow([len(refs), ",".join(sorted(refs, key=nat)), value, name, mf, mpn,
                        lcsc or "(none: JLCPCB global sourcing by MPN)", dk, alt, who[kind]])
    gs = [(sorted(refs, key=nat), mf, mpn, dk, alt) for (mf, mpn, dk, alt), refs in glob_src.items()]
    return len(rows), sum(len(v) for v in groups.values()), len(groups), [r for r in rows if r[5]], sorted(gs, key=lambda g: nat(g[0][0]))


def geometry(board, lim):
    """Worst values straight from the copper (independent of DRC rules), and every hole pair under JLCPCB's limits
    (KiCad DRC does not flag same-net holes that touch or overlap)."""
    close = []
    tracks = [t for t in board.GetTracks() if t.GetClass() == "PCB_TRACK"]
    vias = [v for v in board.GetTracks() if v.GetClass() == "PCB_VIA"]
    g = {}
    g["track width min"] = min(mm(t.GetWidth()) for t in tracks)
    g["via hole min"] = min(mm(v.GetDrillValue()) for v in vias) if vias else None
    g["via diameter min"] = min(mm(v.GetWidth(pcbnew.F_Cu)) for v in vias) if vias else None
    g["via annular ring min"] = min((mm(v.GetWidth(pcbnew.F_Cu)) - mm(v.GetDrillValue())) / 2 for v in vias) if vias else None
    holes = [(mm(v.GetPosition().x), mm(v.GetPosition().y), mm(v.GetDrillValue()) / 2, "via", "") for v in vias]
    ring = []
    for fp in board.GetFootprints():
        for p in fp.Pads():
            d = p.GetDrillSize()
            if d.x <= 0:
                continue
            r = min(mm(d.x), mm(d.y)) / 2
            holes.append((mm(p.GetPosition().x), mm(p.GetPosition().y), r, "pad", fp.GetReference()))
            if p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH:
                try:
                    s = p.GetSize(pcbnew.F_Cu)            # KiCad 9: pad size per layer (padstack)
                except TypeError:
                    s = p.GetSize()
                ring.append(((min(mm(s.x) - mm(d.x), mm(s.y) - mm(d.y))) / 2, fp.GetReference()))
    g["PTH pad annular ring min"] = min(ring) if ring else None
    g["drill min"] = min(2 * h[2] for h in holes) if holes else None
    best = {"via-via": (1e9, ""), "pad hole involved": (1e9, "")}
    coloc = []
    cell = {}
    for i, h in enumerate(holes):
        cell.setdefault((int(h[0] // 3), int(h[1] // 3)), []).append(i)
    for (cx, cy), ids in cell.items():
        near = [j for dx in (-1, 0, 1) for dy in (-1, 0, 1) for j in cell.get((cx + dx, cy + dy), [])]
        for i in ids:
            for j in near:
                if j <= i:
                    continue
                a, b = holes[i], holes[j]
                dist = math.hypot(a[0] - b[0], a[1] - b[1])
                if dist < 0.001:
                    coloc.append(f"{a[3]} {a[4]} / {b[3]} {b[4]} at ({a[0]:.2f}, {a[1]:.2f})".replace("  ", " "))
                    continue
                gap = dist - a[2] - b[2]
                if a[3] == b[3] == "pad" and a[4] == b[4]:
                    continue                      # holes of one footprint (press-fit / terminal pin groups) are its own design
                key = "via-via" if a[3] == b[3] == "via" else "pad hole involved"
                if gap < best[key][0]:
                    best[key] = (gap, f"{a[3]} {a[4]} / {b[3]} {b[4]}".strip())
                if gap < (lim["via_h2h"] if key == "via-via" else lim["pad_h2h"]) - 1e-6:
                    close.append(f"{a[3]} {a[4]} ({a[0]:.2f}, {a[1]:.2f}) / {b[3]} {b[4]} ({b[0]:.2f}, {b[1]:.2f}): "
                                 f"{gap:.3f} mm".replace("  ", " "))
    g["hole-to-hole gap min (via-via)"] = best["via-via"]
    g["hole-to-hole gap min (pad holes, other footprints)"] = best["pad hole involved"]
    return g, coloc, sorted(close)


def zone_check(path):
    """Refill every zone of a fresh copy in memory (KiCad 9, the PCB's own version); largest change of filled area."""
    b = pcbnew.LoadBoard(path)
    zones = list(b.Zones())
    before = [z.CalculateFilledArea() for z in zones]
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    after = [z.CalculateFilledArea() for z in zones]
    worst = (0.0, "")
    for z, a0, a1 in zip(zones, before, after):
        rel = abs(a1 - a0) / max(a0, 1.0)
        if rel > worst[0]:
            worst = (rel, f"{z.GetNetname() or z.GetZoneName()} on {z.GetLayerName()}")
    return worst


def jlc_drc(src_dir, stem, layers, tmp):
    """DRC on a copy with only JLCPCB's limits as rules (board minimums zeroed). Returns {type: (n, worst, eg)}."""
    L = JLC_LIMITS[layers]
    work = os.path.join(tmp, "drc")
    shutil.copytree(src_dir, work)
    pro = os.path.join(work, stem + ".kicad_pro")
    j = json.load(open(pro, encoding="utf-8-sig"))
    rules = j["board"]["design_settings"]["rules"]
    for k in list(rules):
        if k.startswith("min_") and isinstance(rules[k], (int, float)):
            rules[k] = 0.0
    json.dump(j, open(pro, "w", encoding="utf-8"), indent=2)
    dru = f"""(version 1)
(rule "JLC track width" (constraint track_width (min {L['track']}mm)))
(rule "JLC clearance" (constraint clearance (min {L['clearance']}mm)))
(rule "JLC SMD pad to pad" (condition "A.Pad_Type == 'SMD' && B.Pad_Type == 'SMD'") (constraint clearance (min {L['smd_pad_gap']}mm)))
(rule "JLC hole size" (constraint hole_size (min {L['hole']}mm)))
(rule "JLC via diameter" (condition "A.Type == 'Via'") (constraint via_diameter (min {L['via_dia']}mm)))
(rule "JLC via annular ring" (condition "A.Type == 'Via'") (constraint annular_width (min {L['via_ring']}mm)))
(rule "JLC PTH annular ring" (condition "A.Type == 'Pad'") (constraint annular_width (min {L['pth_ring']}mm)))
(rule "JLC hole to hole (pad)" (constraint hole_to_hole (min {L['pad_h2h']}mm)))
(rule "JLC hole to hole (via-via)" (condition "A.Type == 'Via' && B.Type == 'Via'") (constraint hole_to_hole (min {L['via_h2h']}mm)))
(rule "JLC hole to copper" (constraint hole_clearance (min {L['hole_cu']}mm)))
(rule "JLC PTH hole to track" (condition "A.Pad_Type == 'Through-hole' && B.Type == 'Track'") (constraint hole_clearance (min {L['pth_track']}mm)))
(rule "JLC copper to edge" (constraint edge_clearance (min {L['edge']}mm)))
(rule "JLC silkscreen text" (condition "A.Layer == 'F.Silkscreen' || A.Layer == 'B.Silkscreen'") (constraint text_thickness (min {L['silk_w']}mm)) (constraint text_height (min {L['silk_h']}mm)))
"""
    open(os.path.join(work, stem + ".kicad_dru"), "w", encoding="utf-8").write(dru)
    rep = os.path.join(tmp, "drc.json")
    subprocess.run([CLI, "pcb", "drc", "--format", "json", "--severity-all", "-o", rep, os.path.join(work, stem + ".kicad_pcb")],
                   capture_output=True, text=True)
    d = json.load(open(rep, encoding="utf-8"))
    wanted = {"clearance", "track_width", "hole_clearance", "hole_to_hole", "annular_width", "via_diameter",
              "drill_out_of_range", "copper_edge_clearance", "text_height", "text_thickness", "holes_co_located",
              "drilled_holes_co_located", "drilled_holes_too_close"}
    res = {}
    for v in d.get("violations", []):
        if v["type"] not in wanted:
            continue
        m = re.search(r"actual ([\d.]+) mm", v["description"])
        rule = re.search(r"rule '([^']+)'", v["description"])
        key = (v["type"], rule.group(1) if rule else "")
        n, worst, eg = res.get(key, (0, None, []))
        a = float(m.group(1)) if m else None
        if a is not None and (worst is None or a < worst):
            worst = a
        if len(eg) < 4:
            eg.append(" / ".join(i["description"] for i in v["items"])[:110])
        res[key] = (n + 1, worst, eg)
    return res, dru


def vias_in_pads(b):
    """Vias whose centre sits inside a same-net SMD pad (same rule as tools/verify_dfm.py): mostly the PROFET /
    regulator exposed-pad thermal vias and the VDDA via in FB1. Open vias there wick solder from the joint (voids),
    so they are ordered epoxy-filled and capped. Returns {ref: count}."""
    vias = [t for t in b.GetTracks() if t.GetClass() == "PCB_VIA"]
    out = {}
    for fp in b.GetFootprints():
        for p in fp.Pads():
            if p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD:
                continue
            bb = p.GetBoundingBox()
            for v in vias:
                if v.GetNetname() == p.GetNetname() and bb.Contains(v.GetPosition()) and p.HitTest(v.GetPosition()):
                    out.setdefault(fp.GetReference(), set()).add(v.m_Uuid.AsString())
    return {r: len(s) for r, s in out.items()}


def notes(tag, layers, b, size, press, gsrc=()):
    vip = vias_in_pads(b)
    nv = sum(vip.values())
    fill = (f"Epoxy filled and capped (POFV, 'via in pad'): {nv} vias sit in SMD pads of "
            + ", ".join(f"{r} ({n})" for r, n in sorted(vip.items(), key=lambda x: (-x[1], nat(x[0])))[:10])
            + (" ..." if len(vip) > 10 else "") + "; ADR-2026-11-20-presim-findings item 5") if vip else "Tented (no via in an SMD pad)"
    a = ["# Fab notes: " + tag, "",
         "Generated by `tools/gen_fab_jlcpcb.py`; why each value: `hardware/fab/README.md`.", "",
         "| Option | Value |", "|---|---|",
         f"| Layers | {layers} |",
         f"| Size | {size[0]:.1f} x {size[1]:.1f} mm |",
         "| Material | FR-4 |",
         "| Thickness | 1.6 mm |",
         "| Surface finish | ENIG |",
         f"| Copper weight | {copper_order.fab_row(tag)} |",
         "| Solder mask | green (Dan, DECISIONS 2026-11-17 a3a; the mask limits in the checks are the green ones) |",
         "| Silkscreen | white |",
         "| Order number | JLCPCB default |",
         f"| Via covering | {fill} |",
         "",
         "Solder mask: green, silkscreen: white.",
         ""]
    vip_remark = (f" Via in pad: {nv} vias sit in SMD pads (fab-notes.md lists the parts): please epoxy-fill and cap them "
                  "(plated over, flat) so no solder wicks into them.") if vip else ""
    cu_remark = copper_order.remark(tag)
    if cu_remark:
        vip_remark += " " + cu_remark
    if press or vip:
        a += ["Order remark (paste into the PCB remark field):", ""]
    if vip and not press:
        a += ["> " + vip_remark.strip(), ""]
    if press:
        a += [
              "> Press-fit holes: footprints " + ", ".join(press) + " (8 holes each, Wurth 7461084 press-fit terminal). "
              "Finished hole 1.475 mm +-0.05 mm (as in the drill file), round, plated; hole wall copper 25-60 um "
              "(Wurth 7461084 data sheet). Board thickness must not be below 1.6 mm (terminal range 1.6-3.2 mm). "
              "Please confirm the hole wall copper you can hold; if under 25 um, please say so before production."
              + vip_remark,
              "",
              "Assembly: JLCPCB fits every part in `*-bom-jlcpcb.csv` (SMT + through-hole). The press-fit terminals "
              + ", ".join(press) + " are left out of the JLCPCB BOM / CPL (not soldered: 'wave and reflow soldering is "
              "not applicable', Wurth); press them in after delivery: arbor press, one stroke at a right angle, board "
              "supported under every pin by a plate with 1.75 mm (-0 / +0.1) holes, at least 40 N per pin "
              "(8 pins per terminal), 3 mm from other parts and the board edge (all Wurth 7461084 data sheet).", ""]
    elif vip:
        a += ["Assembly: JLCPCB fits every part in `*-bom-jlcpcb.csv`.", ""]
    else:
        a += ["Order remark: none needed.", "", "Assembly: JLCPCB fits every part in `*-bom-jlcpcb.csv`.", ""]
    if gsrc:
        a += ["Global sourcing (parts with NO LCSC number: in `*-bom-jlcpcb.csv` their Comment is the maker part "
              "number and the LCSC cell is empty; JLCPCB shows them as not matched until they are added through "
              "'Global Sourcing' / 'Parts pre-order' by that part number):", "",
              "| Parts | Qty per board | Maker | Part number (MPN) | Digi-Key | Approved alternate |", "|---|---|---|---|---|---|"]
        a += [f"| {refs[0]}-{refs[-1]} |" .replace(f"{refs[0]}-{refs[0]}", refs[0]) + f" {len(refs)} | {mf} | {mpn} | {dk} | {alt or NO_ALT} |"
              for refs, mf, mpn, dk, alt in gsrc]
        a += [""]
    thin = {}
    for fp, kind in parts(b):
        if kind in ("jlc-smt", "jlc-tht") and field(fp, "MPN") in THIN_STOCK:
            thin.setdefault((field(fp, "MPN"), field(fp, "Manufacturer"), field(fp, "Alternates")), []).append(fp.GetReference())
    if thin:
        a += ["Thin stock (order soon; if JLCPCB shows a part short, use its approved alternate):", "",
              "| Parts | Qty per board | Part | Stock seen | Approved alternate |", "|---|---|---|---|---|"]
        for (mpn, mf, alt), refs in sorted(thin.items(), key=lambda kv: nat(sorted(kv[1], key=nat)[0])):
            refs = sorted(refs, key=nat)
            a += [f"| {', '.join(refs)} | {len(refs)} | {mf} {mpn} | {THIN_STOCK[mpn]} | {alt or NO_ALT} |"]
        a += [""]
    return "\n".join(a)


def main():
    want = [x.upper() for x in sys.argv[1:]] or list(BOARDS)
    for key in want:
        folder, stem, tag = BOARDS[key]
        src = os.path.join(REPO, "hardware", folder)
        out = os.path.join(REPO, "hardware", "fab", tag)
        gdir = os.path.join(out, "gerber")
        if os.path.isdir(gdir):
            shutil.rmtree(gdir)
        os.makedirs(gdir)
        tmp = tempfile.mkdtemp(prefix="fab-")
        try:
            copy = os.path.join(tmp, "src")
            shutil.copytree(src, copy)
            pcb = os.path.join(copy, stem + ".kicad_pcb")
            b = pcbnew.LoadBoard(os.path.join(src, stem + ".kicad_pcb"))
            n = b.GetCopperLayerCount()
            cu = ["F.Cu"] + [f"In{i}.Cu" for i in range(1, n - 1)] + ["B.Cu"]
            layers = ",".join(cu + ["F.Paste", "B.Paste", "F.Silkscreen", "B.Silkscreen", "F.Mask", "B.Mask", "Edge.Cuts"])
            run([CLI, "pcb", "export", "gerbers", "-o", gdir, "-l", layers] + GERBER_OPTS + [pcb])
            run([CLI, "pcb", "export", "drill", "-o", gdir + os.sep] + DRILL_OPTS + [pcb])
            strip_dates(gdir)
            zrel, zwhere = zone_check(pcb)            # JLCPCB: "check zone fills before plotting"
            zf = os.path.join(out, f"{tag}-gerber.zip")
            with zipfile.ZipFile(zf, "w", zipfile.ZIP_DEFLATED) as z:
                for p in sorted(glob.glob(os.path.join(gdir, "*"))):
                    z.write(p, os.path.basename(p))
            ncpl, nbom, nlines, rotated, gsrc = write_bom_cpl(b, out, tag)
            geo, coloc, close = geometry(b, JLC_LIMITS[n])
            drc, dru = jlc_drc(copy, stem, n, os.path.join(tmp, "d"))
            bb = b.GetBoardEdgesBoundingBox()
            press = sorted({fp.GetReference() for fp, k in parts(b) if k == "press-fit"}, key=nat)
            open(os.path.join(out, "fab-notes.md"), "w", encoding="utf-8", newline="\n").write(
                notes(tag, n, b, (mm(bb.GetWidth()), mm(bb.GetHeight())), press, gsrc))
            L = JLC_LIMITS[n]
            rep = [f"JLCPCB check: {tag} ({n} layers). Limits: JLCPCB capabilities page, "
                   f"{'multilayer' if n > 2 else '1-2 layer'}, 1 oz outer copper (read 2026-11-16).",
                   f"Zone fills: a refill (KiCad 9) changes the filled area by at most {100 * zrel:.3f} % ({zwhere or '-'}); "
                   + ("current" if zrel < 0.001 else "REFILL AND RE-SAVE THE PCB BEFORE ORDERING"),
                   "Drilled holes on the same spot (two vias / via on a pad): "
                   + (f"{len(coloc)}: " + "; ".join(coloc[:6]) if coloc else "none"),
                   f"Hole pairs closer than JLCPCB's hole-to-hole limits (via-via {L['via_h2h']} mm, pad hole "
                   f"{L['pad_h2h']} mm): " + (f"{len(close)}: " + "; ".join(close[:12]) if close else "none"),
                   f"Assembly: {nbom} parts in {nlines} BOM lines, {ncpl} placements; rotation offsets applied to: "
                   + (", ".join(sorted({f'{r[0]} +{r[5]}' for r in rotated}, key=nat)) or "none"), "",
                   "Worst values from the copper:"]
            lim = {"track width min": L["track"], "via hole min": L["hole"], "via diameter min": L["via_dia"],
                   "via annular ring min": L["via_ring"], "PTH pad annular ring min": L["pth_ring"], "drill min": L["hole"],
                   "hole-to-hole gap min (via-via)": L["via_h2h"],
                   "hole-to-hole gap min (pad holes, other footprints)": L["pad_h2h"]}
            for k, v in geo.items():
                val, where = (v if isinstance(v, tuple) else (v, ""))
                if val is None:
                    continue
                ok = "ok" if val >= lim[k] - 1e-6 else "BELOW JLCPCB"
                rep.append(f"  {k:52s} {val:7.3f} mm  (JLCPCB {lim[k]} mm)  {ok}  {where}")
            rep += ["", "DRC with JLCPCB's limits as the only rules (count, worst actual, examples):"]
            if not drc:
                rep.append("  no violations")
            for (typ, rule), (cnt, worst, eg) in sorted(drc.items()):
                rep.append(f"  {typ} [{rule}]: {cnt}" + (f", worst {worst} mm" if worst is not None else ""))
                rep += [f"      {e}" for e in eg]
            rep += ["", "Rules used:", dru]
            open(os.path.join(out, "jlcpcb-drc.txt"), "w", encoding="utf-8", newline="\n").write("\n".join(rep))
            print(f"{tag}: {len(glob.glob(os.path.join(gdir, '*')))} gerber/drill files, {nlines} BOM lines, {ncpl} CPL rows, "
                  f"DRC types {len(drc)}, zone change {100 * zrel:.3f} %, co-located holes {len(coloc)}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
