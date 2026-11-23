"""Generate the input daughter board schematic (KiCad 10 format) from a parts list. Pure python.

usage: python gen_input_board_sch.py <out_dir>

Circuit (Dan, 2026-11-08/09): 8 digital channels + 1 analog channel.
  Digital channel i (1..8), wire side net INW_i, MCU side net IN_i:
    J2.i (wire, Micro-Fit) -> INW_i -> R 4.7k -> IN_i -> J1.i (JST GH to board A)
    IN_i: BAT54S clamp (A=GND, K=+3V3, COM=IN_i) + 10 nF to GND
    INW_i: 10k pull-up via solder jumper JP<i> to +3V3, 10k pull-down via solder jumper JP<8+i> to GND (pulls on the
           wire side, so a switch to ground reads a solid 0 V). Jumpers are open as built and bridged by hand at assembly
           (setting table: docs/order-checklist.md, input board section 8). They replace the Omron A6S-8104 DIP switches SW1 / SW2 (job hwtemp, 2026-11-23):
           the lid air reaches 75-91 C and the A6S is rated -20..+70 C; no SMD DIP switch rated >= 105 C was found
           (docs/parts-audit.md 11, 17).
  Analog (0-5 V in): J2.9 -> AINW -> 10k -> AIN -> 20k -> GND; AIN: BAT54S clamp + 10 nF; AIN -> J1.9
  J1.10 = +3V3 (from board A), J1.11-12 = GND, J2.10-12 = GND.
Every pin gets a net label at its end (no wires), so the netlist is exact and easy to check.
"""
import re, sys, os, uuid

SYMLIB = r"C:\Users\danie\AppData\Local\Programs\KiCad\10.0\share\kicad\symbols"
OUT = sys.argv[1] if len(sys.argv) > 1 else "."
PROJECT = "input-board"
ROOT = str(uuid.uuid5(uuid.NAMESPACE_URL, "custom-pdm/input-board/root"))
NCH = 8
_n = 0


def uid():
    """Stable uuids so re-running the generator gives the same file."""
    global _n
    _n += 1
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"custom-pdm/input-board/{_n}"))


def block_end(t, s):
    d, i, q = 0, s, False
    while True:
        c = t[i]
        if q:
            if c == "\\":
                i += 2
                continue
            if c == '"':
                q = False
        elif c == '"':
            q = True
        elif c == "(":
            d += 1
        elif c == ")":
            d -= 1
            if d == 0:
                return i + 1
        i += 1


LIBS = {}


def libsym(lib_id):
    """(embedded lib_symbols text, {pin number: (x, y, angle)})."""
    if lib_id in LIBS:
        return LIBS[lib_id]
    lib, name = lib_id.split(":")
    t = open(os.path.join(SYMLIB, lib + ".kicad_sym"), encoding="utf-8").read()
    s = t.index(f'\n\t(symbol "{name}"') + 2
    blk = t[s:block_end(t, s)]
    if "(extends" in blk:
        raise SystemExit(f"{lib_id} extends another symbol: not handled")
    pins = {m.group(5): (float(m.group(1)), float(m.group(2)), int(m.group(3)))
            for m in re.finditer(r'\(pin \w+ \w+\s*\(at ([\d.\-]+) ([\d.\-]+) (\d+)\)[\s\S]*?\(name "([^"]*)"[\s\S]*?\(number "([^"]*)"', blk)}
    emb = blk.replace(f'(symbol "{name}"', f'(symbol "{lib_id}"', 1)
    emb = "\n".join(("\t" + ln) if ln else ln for ln in emb.split("\n"))
    LIBS[lib_id] = (emb, pins)
    return LIBS[lib_id]


def fmt(v):
    return ("%.4f" % v).rstrip("0").rstrip(".")


def prop(name, val, x, y, hide=False):
    h = "\n\t\t\t(hide yes)" if hide else ""
    return (f'\t\t(property "{name}" "{val}"\n\t\t\t(at {fmt(x)} {fmt(y)} 0){h}\n\t\t\t(show_name no)\n'
            f'\t\t\t(do_not_autoplace no)\n\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)\n'
            f'\t\t\t\t(justify left)\n\t\t\t)\n\t\t)')


def label(net, x, y, ang):
    just = "left bottom" if ang in (0, 90) else "right bottom"
    return (f'\t(label "{net}"\n\t\t(at {fmt(x)} {fmt(y)} {ang})\n\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1.27 1.27)\n'
            f'\t\t\t)\n\t\t\t(justify {just})\n\t\t)\n\t\t(uuid "{uid()}")\n\t)')


LABEL_ANGLE = {0: 180, 180: 0, 270: 90, 90: 270}   # pin direction -> label pointing away from the body
items, used_libs = [], []


def part(ref, lib_id, value, fp, x, y, nets, desc="", in_bom=True):
    """Place a symbol at (x, y), unrotated; nets = {pin number: net} (every pin must be listed)."""
    emb, pins = libsym(lib_id)
    if lib_id not in used_libs:
        used_libs.append(lib_id)
    if pins and set(nets) != set(pins):
        raise SystemExit(f"{ref}: pins {sorted(pins)} vs nets given {sorted(nets)}")
    pin_txt = "\n".join(f'\t\t(pin "{n}"\n\t\t\t(uuid "{uid()}")\n\t\t)' for n in pins)
    s = (f'\t(symbol\n\t\t(lib_id "{lib_id}")\n\t\t(at {fmt(x)} {fmt(y)} 0)\n\t\t(unit 1)\n\t\t(body_style 1)\n'
         f'\t\t(exclude_from_sim no)\n\t\t(in_bom {"yes" if in_bom else "no"})\n\t\t(on_board yes)\n\t\t(in_pos_files yes)\n\t\t(dnp no)\n'
         f'\t\t(uuid "{uid()}")\n'
         + prop("Reference", ref, x + 2.54, y - 3.81) + "\n" + prop("Value", value, x + 2.54, y + 3.81) + "\n"
         + prop("Footprint", fp, x, y, True) + "\n" + prop("Datasheet", "", x, y, True) + "\n"
         + prop("Description", desc, x, y, True) + "\n" + (pin_txt + "\n" if pin_txt else "")
         + f'\t\t(instances\n\t\t\t(project "{PROJECT}"\n\t\t\t\t(path "/{ROOT}"\n\t\t\t\t\t(reference "{ref}")\n'
         f'\t\t\t\t\t(unit 1)\n\t\t\t\t)\n\t\t\t)\n\t\t)\n\t)')
    items.append(s)
    for n, net in nets.items():
        px, py, pa = pins[n]
        items.append(label(net, x + px, y - py, LABEL_ANGLE[pa]))


R, C, D = "Device:R_Small_US", "Device:C_Small", "Diode:BAT54S"
FR, FC = "Resistor_SMD:R_0603_1608Metric", "Capacitor_SMD:C_0603_1608Metric"
FD = "Package_TO_SOT_SMD:SOT-23"
FJP = "Jumper:SolderJumper-2_P1.3mm_Open_RoundedPad1.0x1.5mm"   # KiCad 9 library: pads 1.3 mm apart (0.3 mm gap)
FJ1 = "Connector_JST:JST_GH_SM12B-GHS-TB_1x12-1MP_P1.25mm_Horizontal"
FJ2 = "Connector_Molex:Molex_Micro-Fit_3.0_43045-1200_2x06_P3.00mm_Horizontal"
FH = "MountingHole:MountingHole_3.2mm_M3"

for i in range(1, NCH + 1):
    y = 30.48 + (i - 1) * 20.32
    part(f"R{i}", R, "4.7k", FR, 50.8, y, {"1": f"INW_{i}", "2": f"IN_{i}"}, "series, input protection")
    part(f"D{i}", D, "BAT54S", FD, 81.28, y, {"1": "GND", "2": "+3V3", "3": f"IN_{i}"}, "clamp to GND / +3V3")
    part(f"C{i}", C, "10nF", FC, 111.76, y, {"1": f"IN_{i}", "2": "GND"}, "filter")
    part(f"R{8 + i}", R, "10k", FR, 132.08, y, {"1": f"INW_{i}", "2": f"PU_{i}"}, f"pull-up via JP{i}")
    part(f"R{16 + i}", R, "10k", FR, 152.4, y, {"1": f"INW_{i}", "2": f"PD_{i}"}, f"pull-down via JP{8 + i}")
ya = 30.48 + NCH * 20.32
part("R25", R, "10k", FR, 50.8, ya, {"1": "AINW", "2": "AIN"}, "analog divider top (0-5 V in -> 0-3.33 V)")
part("R26", R, "20k", FR, 132.08, ya, {"1": "AIN", "2": "GND"}, "analog divider bottom")
part("D9", D, "BAT54S", FD, 81.28, ya, {"1": "GND", "2": "+3V3", "3": "AIN"}, "clamp to GND / +3V3")
part("C9", C, "10nF", FC, 111.76, ya, {"1": "AIN", "2": "GND"}, "filter")
for i in range(1, NCH + 1):
    yj = 30.48 + (i - 1) * 20.32
    part(f"JP{i}", "Jumper:SolderJumper_2_Open", f"PU{i}", FJP, 190.5, yj, {"1": f"PU_{i}", "2": "+3V3"},
         f"input {i}: bridged = 10k pull-up to +3V3 (open as built)", in_bom=False)
    part(f"JP{8 + i}", "Jumper:SolderJumper_2_Open", f"PD{i}", FJP, 220.98, yj, {"1": f"PD_{i}", "2": "GND"},
         f"input {i}: bridged = 10k pull-down to GND (open as built)", in_bom=False)
j1 = {str(i): f"IN_{i}" for i in range(1, NCH + 1)}
j1.update({"9": "AIN", "10": "+3V3", "11": "GND", "12": "GND"})
part("J1", "Connector_Generic:Conn_01x12", "JST GH 12p to board A J6", FJ1, 266.7, 50.8, j1,
     "pins 1-8 inputs, 9 analog, 10 +3V3, 11-12 GND (board A uses inputs 1-5)")
j2 = {str(i): f"INW_{i}" for i in range(1, NCH + 1)}
j2.update({"9": "AINW", "10": "GND", "11": "GND", "12": "GND"})
part("J2", "Connector_Generic:Conn_02x06_Odd_Even", "Micro-Fit 2x6 wires", FJ2, 266.7, 116.84, j2,
     "wires from the box connector: 1-8 inputs, 9 analog 0-5 V, 10-12 GND")
part("H1", "Mechanical:MountingHole", "M3", FH, 254.0, 160.02, {}, in_bom=False)
part("H2", "Mechanical:MountingHole", "M3", FH, 269.24, 160.02, {}, in_bom=False)

note = (f'\t(text "Input board (custom-pdm). 8 on/off inputs + 1 analog 0-5 V.\\nPer input: 4.7k series, BAT54S clamp, 10 nF; '
        f'10k pull-up (JP1-8) and 10k pull-down (JP9-16) on the wire side, solder jumpers bridged at assembly.\\nBoth open = MCU weak pull (firmware). '
        f'Generated by tools/gen_input_board_sch.py - edit the script, not this file."\n\t\t(exclude_from_sim no)\n'
        f'\t\t(at 30.48 12.7 0)\n\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1.27 1.27)\n\t\t\t)\n\t\t\t(justify left bottom)\n'
        f'\t\t)\n\t\t(uuid "{uid()}")\n\t)')
items.append(note)

head = (f'(kicad_sch\n\t(version 20260306)\n\t(generator "eeschema")\n\t(generator_version "10.0")\n\t(uuid "{ROOT}")\n'
        f'\t(paper "A3")\n\t(title_block\n\t\t(title "custom-pdm input board")\n\t\t(rev "A")\n'
        f'\t\t(comment 1 "Generated by tools/gen_input_board_sch.py")\n\t)\n\t(lib_symbols\n'
        + "\n".join(libsym(l)[0] for l in used_libs) + "\n\t)\n")
tail = '\t(sheet_instances\n\t\t(path "/"\n\t\t\t(page "1")\n\t\t)\n\t)\n\t(embedded_fonts no)\n)\n'
os.makedirs(OUT, exist_ok=True)
with open(os.path.join(OUT, PROJECT + ".kicad_sch"), "w", encoding="utf-8", newline="\n") as f:
    f.write(head + "\n".join(items) + "\n" + tail)
print("schematic written:", sum(1 for s in items if s.startswith("\t(symbol")), "symbols,",
      sum(1 for s in items if s.startswith("\t(label")), "labels")
