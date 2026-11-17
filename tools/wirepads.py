"""Wire pads in place of on-board connectors (Dan 2026-11-12: e6a, p1a, a1a, a2b). Same holes, same spots, no copper change.

  python   tools/wirepads.py lib                        write the two pads-only footprints into the dingoPDM library
  python   tools/wirepads.py sch-a <Connectors.kicad_sch>  board A J3 symbol: footprint, value, no orderable part
  python   tools/wirepads.py sch <file.kicad_sch> <ref>    same for any REF_FP symbol (board B J6 is set by sch_board_b.py)
  python.exe (KiCad 9) tools/wirepads.py pcb <board.kicad_pcb> <ref>   swap the board footprint in place

Board A J3: DT15-12PA header (12 x 1.77 mm holes) -> DT15-12PA_WirePads: the same 12 holes, wires (16 AWG outputs,
  20 AWG IN / CAN) solder straight in. Pins: 1 CAN_L, 2 CAN_H, 3 OUT8, 4 OUT7, 5 OUT6, 6 OUT5, 7 OUT2, 8 OUT1,
  9 OUT4, 10 OUT3, 11 IN2, 12 IN1.
Board B J6: Micro-Fit 3.0 2x2 header -> MicroFit_2x02_WirePads: the same 4 holes (1.02 mm, 20 AWG), no locating pegs.
  Pins: 1 CAN_L, 2 CAN_H, 3 IN2, 4 IN1.
Silkscreen names sit between the pad rows (top surface). The footprints are generated here, so a rebuild keeps them.
"""
import os
import re
import sys
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
LIBDIR = os.path.normpath(os.path.join(HERE, "..", "hardware", "board-a", "libraries"))
LIB = os.path.join(LIBDIR, "dingoPDM.pretty")
NS = uuid.UUID("6b1f6f1e-2f3a-4c55-9d43-1c0de00a0000")

# name: (description, pads [(num, x, y, shape)], pad size, drill, labels {num: (text, x, y)}, courtyard (x0, y0, x1, y1))
A_X, A_Y = 4.56, (11.11, 6.67, 2.22, -2.22, -6.67, -11.11)
A_NAMES = {1: "CL", 2: "CH", 3: "O8", 4: "O7", 5: "O6", 6: "O5", 7: "O2", 8: "O1", 9: "O4", 10: "O3", 11: "I2", 12: "I1"}
FOOTPRINTS = {
    "DT15-12PA_WirePads": (
        "Wire solder pads in the DT15-12PA hole pattern (12 x 1.77 mm drill, 2.655 mm pad); "
        "16 AWG outputs, 20 AWG IN / CAN. CL/CH = CAN_L/CAN_H, O1-O8 = OUT1-8, I1/I2 = IN1/IN2.",
        [(n, -A_X if n <= 6 else A_X, A_Y[n - 1] if n <= 6 else -A_Y[n - 7], "rect" if n == 1 else "circle") for n in range(1, 13)],
        2.655, 1.77,
        {n: (t, -1.8 if n <= 6 else 1.8, A_Y[n - 1] if n <= 6 else -A_Y[n - 7]) for n, t in A_NAMES.items()},
        (-6.2, -12.75, 6.2, 12.75)),
    "MicroFit_2x02_WirePads": (
        "Wire solder pads in the Molex Micro-Fit 3.0 2x02 hole pattern (4 x 1.02 mm drill, 1.5 mm pad), 20 AWG. "
        "CL/CH = CAN_L/CAN_H, I1/I2 = IN1/IN2.",
        [(1, 0, 0, "roundrect"), (2, 3, 0, "circle"), (3, 0, 3, "circle"), (4, 3, 3, "circle")],
        1.5, 1.02,
        {1: ("CL", 0, -1.65), 2: ("CH", 3, -1.65), 3: ("I2", 0, 4.65), 4: ("I1", 3, 4.65)},
        (-1.25, -2.6, 4.25, 5.6)),
}
REF_AT = {"DT15-12PA_WirePads": (0, 0), "MicroFit_2x02_WirePads": (1.5, 6.6)}
VALUES = {"DT15-12PA_WirePads": "WIRE PADS X1/X2/CAN", "MicroFit_2x02_WirePads": "WIRE PADS CAN + IN1-2"}
ORDER_FIELDS = ("LCSC", "Digi-Key_PN", "MPN", "Manufacturer")
REF_FP = {"J3": "DT15-12PA_WirePads", "J6": "MicroFit_2x02_WirePads"}


def uid(*parts):
    return str(uuid.uuid5(NS, "/".join(map(str, parts))))


def text_block(kind, name, val, x, y, layer, hide, key, size=1.02, thick=0.16):
    head = f'\t(property "{name}" "{val}"' if kind == "property" else f'\t(fp_text user "{val}"'
    return (f'{head}\n\t\t(at {x:g} {y:g} 0)\n\t\t(unlocked yes)\n\t\t(layer "{layer}")\n'
            + ("\t\t(hide yes)\n" if hide else "")
            + f'\t\t(uuid "{uid(key)}")\n\t\t(effects\n\t\t\t(font\n\t\t\t\t(size {size:g} {size:g})\n'
            f'\t\t\t\t(thickness {thick:g})\n\t\t\t)\n\t\t)\n\t)\n')


def footprint_text(name):
    descr, pads, size, drill, labels, (cx0, cy0, cx1, cy1) = FOOTPRINTS[name]
    out = [f'(footprint "{name}"\n\t(version 20241229)\n\t(generator "pcbnew")\n\t(generator_version "9.0")\n\t(layer "F.Cu")\n',
           f'\t(descr "{descr}")\n\t(tags "wire solder pad")\n',
           text_block("property", "Reference", "REF**", *REF_AT[name], "F.SilkS", False, (name, "ref")),
           text_block("property", "Value", VALUES[name], 0, cy1 + 1.5, "F.Fab", False, (name, "val")),
           text_block("property", "Datasheet", "", 0, 0, "F.Fab", True, (name, "ds")),
           text_block("property", "Description", "", 0, 0, "F.Fab", True, (name, "desc")),
           '\t(attr through_hole)\n']
    for n, (t, x, y) in sorted(labels.items()):
        out.append(text_block("fp_text", None, t, x, y, "F.SilkS", False, (name, "lbl", n)))
    out.append(f'\t(fp_rect\n\t\t(start {cx0:g} {cy0:g})\n\t\t(end {cx1:g} {cy1:g})\n\t\t(stroke\n\t\t\t(width 0.05)\n'
               f'\t\t\t(type default)\n\t\t)\n\t\t(fill no)\n\t\t(layer "F.CrtYd")\n\t\t(uuid "{uid(name, "crt")}")\n\t)\n')
    for n, x, y, shape in pads:
        out.append(f'\t(pad "{n}" thru_hole {shape}\n\t\t(at {x:g} {y:g})\n\t\t(size {size:g} {size:g})\n\t\t(drill {drill:g})\n'
                   + ('\t\t(roundrect_rratio 0.166667)\n' if shape == "roundrect" else '')
                   + f'\t\t(layers "*.Cu" "*.Mask")\n\t\t(remove_unused_layers no)\n\t\t(uuid "{uid(name, "pad", n)}")\n\t)\n')
    out.append('\t(embedded_fonts no)\n)\n')
    return "".join(out)


def write_lib():
    for name in FOOTPRINTS:
        p = os.path.join(LIB, name + ".kicad_mod")
        with open(p, "w", encoding="utf-8", newline="\r\n") as fh:
            fh.write(footprint_text(name))
        print("wrote", p)


def block_end(t, s):
    depth = 0
    for i in range(s, len(t)):
        if t[i] == "(":
            depth += 1
        elif t[i] == ")":
            depth -= 1
            if depth == 0:
                return i + 1
    raise ValueError("unbalanced")


def sch(path, ref="J3"):
    raw = open(path, "rb").read().decode("utf-8")
    name = REF_FP[ref]
    k = raw.index(f'(property "Reference" "{ref}"')
    s = raw.rindex("\n\t(symbol", 0, k) + 1
    e = block_end(raw, s)
    blk = raw[s:e]
    new = re.sub(r'\(property "Footprint" "[^"]*"', f'(property "Footprint" "dingoPDM:{name}"', blk, count=1)
    new = re.sub(r'\(property "Value" "[^"]*"', f'(property "Value" "{VALUES[name]}"', new, count=1)
    for fld in ("LCSC", "Digi-Key_PN", "MPN", "Manufacturer"):
        new = re.sub(rf'\(property "{fld}" "[^"]*"', f'(property "{fld}" ""', new, count=1)
    if new == blk:
        raise SystemExit(f"{ref}: nothing changed")
    open(path, "wb").write((raw[:s] + new + raw[e:]).encode("utf-8"))
    print(f"{ref} symbol: footprint dingoPDM:{name}, value {VALUES[name]}, order fields cleared")


def pcb(path, ref):
    import pcbnew
    sys.path.insert(0, HERE)
    import pcb_rework
    name = REF_FP[ref]
    b = pcbnew.LoadBoard(path)
    old = b.FindFootprintByReference(ref)
    if old is None or old.IsFlipped():
        raise SystemExit(f"{ref}: not on the board, or on the bottom side")
    fp = pcbnew.FootprintLoad(LIB, name)
    if fp is None:
        raise SystemExit(f"{name}: not in {LIB} (run 'wirepads.py lib' first)")
    fp.SetFPID(pcbnew.LIB_ID("dingoPDM", name))
    fp.SetReference(ref)
    fp.SetValue(VALUES[name])
    fp.SetPath(old.GetPath())
    fp.SetSheetname(old.GetSheetname())
    fp.SetSheetfile(old.GetSheetfile())
    fp.SetPosition(old.GetPosition())
    fp.SetOrientation(old.GetOrientation())
    olds = {p.GetNumber(): p for p in old.Pads() if p.GetNumber()}
    news = {p.GetNumber(): p for p in fp.Pads()}
    if sorted(olds) != sorted(news):
        raise SystemExit(f"{ref}: numbered pads differ ({sorted(olds)} vs {sorted(news)})")
    for n, p in news.items():
        o = olds[n]
        if abs(p.GetPosition().x - o.GetPosition().x) + abs(p.GetPosition().y - o.GetPosition().y) > 1000 or p.GetDrillSize() != o.GetDrillSize() or p.GetSize() != o.GetSize():
            raise SystemExit(f"{ref}.{n}: hole / pad not identical to the old footprint")
        p.SetNet(o.GetNet())
        p.SetPinFunction(o.GetPinFunction())
        p.SetPinType(o.GetPinType())
    b.Add(fp)
    for f in old.GetFields():                    # keep the symbol's extra fields; order numbers are blank now
        if f.GetName() in ("Reference", "Value", "Footprint", "Datasheet", "Description"):
            continue
        nf = pcbnew.PCB_FIELD(fp, fp.GetNextFieldId(), f.GetName())
        nf.SetText("" if f.GetName() in ORDER_FIELDS else f.GetText())
        nf.SetVisible(False)
        nf.SetLayer(pcbnew.F_Fab)
        nf.SetPosition(fp.GetPosition())
        nf.thisown = False
        fp.AddField(nf)
    print(f"{ref}: {old.GetFPID().GetUniStringLibId()} -> dingoPDM:{name}, {len(news)} pads in the same holes")
    b = pcb_rework.remove_and_reload(b, [old], path)   # saves
    # same numbered holes, but the old footprint's locating pegs / pad clearances are gone (board B J6 Micro-Fit):
    # refill, else the saved fill is stale (fab hole check 2026-11-17: PF_OUT2 F.Cu changed 0.46 % on refill)
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    b.Save(path)


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "lib":
        write_lib()
    elif cmd == "sch-a":
        sch(sys.argv[2], "J3")
    elif cmd == "sch":
        sch(sys.argv[2], sys.argv[3])
    elif cmd == "pcb":
        pcb(sys.argv[2], sys.argv[3])
    else:
        raise SystemExit(__doc__)
