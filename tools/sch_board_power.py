"""Board power-change schematic edits for board A and board B (text edits, like the other sch_*.py scripts).

usage (from the board folder, after tools/sch_board_fix.py):  python sch_board_power.py A|B

Decisions: DECISIONS.md 2026-11-13 r2a and 2026-11-14 (s4a, s5a, s6a). Part fields only: no symbol, pin, net or
footprint change.
  * r2a  U4 MCU -> STM32F446RET7 (-40 to 105 C grade, same LQFP-64 die and pinout; ST DS10693 Rev 11, section 8
         "Ordering information": 6 = -40 to 85 C, 7 = -40 to 105 C).
  * s4a  U2 3.3 V regulator -> TI TLV1117LV33DCYR (SOT-223 DCY: pin 1 GND, pin 2 OUT, pin 3 IN, tab OUT = the
         existing symbol / footprint pins; TI SBVS160C Table 5-1). s5a: genuine TI part, bought through the
         assembler's Digi-Key / Mouser sourcing (LCSC C15578 had no stock on 2026-11-14).
  * s6a  power LED off: the LED and its 120 ohm resistor (A: D3 + R3, B: D5 + R3; both behind solder jumper JP1)
         are do-not-fit and left out of the BOM and the position files. Footprints and copper stay.
  * t1a  (2026-11-14) quad op-amp sense buffers LM324PWR -> TI LM2902PWR (A: U7, U12; B: U7, U22): same TSSOP-14
         pinout (TI SLOS066AE Figure 5-1 / Table 5-1 covers both), TA -40 to 125 C (6.3). Every placed unit of each
         symbol is changed, on the sheets the board's hierarchy uses (board B's MedCurrentDrivers.kicad_sch is not
         in the hierarchy and is left alone).
  * ADR-2026-11-20-is-buffer (supersedes t1a's part): the sense buffers become TI TLV9004IPWR, rail-to-rail in and
         out on the 3.3 V rail (the LM2902 input range stops at VCC-1.5 / -2 V and clipped board A's readings below
         the 7.5 A limit when hot, docs/pcb-verification.md). Same TSSOP-14 pinout, checked pin by pin: TI SBOS833R
         Table 6-5 (TLV9004 PW: 1 OUT1, 2 IN1-, 3 IN1+, 4 V+, 5 IN2+, 6 IN2-, 7 OUT2, 8 OUT3, 9 IN3-, 10 IN3+, 11 V-,
         12 IN4+, 13 IN4-, 14 OUT4) = TI SLOS066AE Table 5-1 (LM2902 PW) = the LM324 symbol's pin numbers; TA -40 to
         125 C (SBOS833R 7.3). The symbol stays the generic Amplifier_Operational:LM324 quad (KiCad 9 / 10 libraries
         have TLV9004 only as TLV9004xRUCR, the X2QFN pin numbering); Value / MPN / LCSC / Digi-Key / Datasheet carry
         the part.
  * ADR-2026-11-20-is-fullscale follow-up (hwfix, 2026-11-20): the IS-chain clamp zeners (A: D9, D12, D13, D14;
         B: D14, D16, D18, D20-D24) PDZ3.3B -> Nexperia PDZ5.1B,115 (same PDZ-B series data sheet, SOD-323, same
         footprint). With the rail-to-rail TLV9004 behind it the zener no longer needs to sit at the 3.3 V rail: the
         op-amp's own input diodes take the overdrive (TI SBOS833R 7.1 note 2: <= 10 mA; 4.7 k limits it to about
         0.3 mA), and the 3.3 V zener's soft knee (rdif <= 1000 Ohm at 0.5 mA, IR <= 5 uA at 1 V, -2.4 mV/K) can hold a
         PROFET fault (IIS(FAULT) 4.4 mA min) under the 2.475 V firmware threshold when hot (tools/verify_spice.py).
         PDZ5.1B: VZ 4.96-5.20 V, rdif <= 60 / 250 Ohm at 5 / 0.5 mA, +0.3 mV/K (Nexperia PDZ-B series Table 2).
         D1 (BATT_SENSE, straight to the MCU pin) stays PDZ3.3B.
The PCB side (values, fields, DNP / BOM / position attributes) is tools/pcb_board_power.py.
Safe to re-run: a symbol already carrying the new data is left alone.
"""
import glob
import re
import sys

BOARD = sys.argv[1].upper()
# part data: (value, LCSC, Digi-Key, Manufacturer, MPN, Datasheet)
MCU = ("STM32F446RET7", "C1343794", "497-16775-ND", "STMicroelectronics", "STM32F446RET7",
       "https://www.st.com/resource/en/datasheet/stm32f446re.pdf")
LDO = ("TLV1117LV33DCYR", "C15578", "296-28778-1-ND", "Texas Instruments", "TLV1117LV33DCYR",
       "https://www.ti.com/lit/ds/symlink/tlv1117lv.pdf")
# ref -> (sheet, expected LCSC before the change, new part or None)
PARTS = {"U4": ("MCU.kicad_sch", "C69336", MCU), "U2": ("Power.kicad_sch", "C35879", LDO)}
LED = {"A": "D3", "B": "D5"}[BOARD]
DNP = {LED: ("Power.kicad_sch", "C2899888"), "R3": ("Power.kicad_sch", "C229076")}   # green LED, 120 ohm
# t1a: op-amp part, its old LCSC, the refs and the sheets that hold their units (all units of a ref get the new data)
OPAMP = ("TLV9004IPWR", "C2058050", "296-51827-1-ND", "Texas Instruments", "TLV9004IPWR",
         "https://www.ti.com/lit/ds/symlink/tlv9004.pdf")      # ADR-2026-11-20-is-buffer (was LM2902PWR, C46864)
OPAMP_OLD_LCSC = "C7942"                                 # TI LM324PWR
OPAMP_UNITS = {"A": {"U7": 4, "U12": 3}, "B": {"U7": 5, "U22": 5}}[BOARD]   # units placed today (A: U7 unit 1 and
OPAMP_REFS = set(OPAMP_UNITS)                                                # U12 units 1 / 2 are not placed)
IS_ZENER = ("5.1V", "C85392", "1727-5155-1-ND", "Nexperia", "PDZ5.1B,115",
            "https://assets.nexperia.com/documents/data-sheet/PDZ-B_SER.pdf")
IS_ZENER_OLD_LCSC = "C426855"                           # Nexperia PDZ3.3B,115
IS_ZENERS = {"A": {"D9", "D12", "D13", "D14"},
             "B": {"D14", "D16", "D18", "D20", "D21", "D22", "D23", "D24"}}[BOARD]
OPAMP_SHEETS = {"A": ("HighCurrentDrivers.kicad_sch", "MedCurrentDrivers.kicad_sch"),
                "B": ("HighCurrentDrivers.kicad_sch", "HighCurrentDrivers2.kicad_sch")}[BOARD]


def rd(p):
    with open(p, encoding="utf-8", newline="") as f:
        return f.read()


def wr(p, t):
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(t)


def block_end(t, start):
    depth, i, in_str = 0, start, False
    while i < len(t):
        c = t[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise ValueError("unbalanced")


def symbol_by_ref(t, ref):
    """The one top-level symbol of this sheet whose instances use `ref` (a sheet used once: one instance)."""
    found = []
    for m in re.finditer(r"\n\t\(symbol[\s(]", t):
        s = m.start() + 2
        e = block_end(t, s)
        b = t[s:e]
        refs = set(re.findall(r'\(reference "([^"]+)"\)', b))
        if ref in refs:
            if refs != {ref}:
                raise SystemExit(f"{ref}: symbol has more than one instance reference {sorted(refs)}: not handled")
            found.append((s, e))
    if len(found) != 1:
        raise SystemExit(f"{ref}: {len(found)} symbols found")
    return found[0]


def get_prop(b, name):
    m = re.search(r'\n\t\t\(property "%s" "([^"]*)"' % re.escape(name), b)
    return m.group(1) if m else None


def set_prop(b, name, value):
    """Set a symbol property; add it (hidden, at the symbol origin) when missing."""
    pat = re.compile(r'(\n\t\t\(property "%s" ")[^"]*(")' % re.escape(name))
    if pat.search(b):
        return pat.sub(lambda m: m.group(1) + value.replace('"', '\\"') + m.group(2), b, count=1)
    x, y = re.search(r"\(at ([\d.\-]+) ([\d.\-]+)", b).groups()
    prop = (f'\n\t\t(property "{name}" "{value}"\n\t\t\t(at {x} {y} 0)\n\t\t\t(hide yes)\n\t\t\t(show_name no)\n'
            f'\t\t\t(do_not_autoplace no)\n\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)\n\t\t\t)\n\t\t)')
    k = b.index("\n\t\t(pin ") if "\n\t\t(pin " in b else b.index("\n\t\t(instances")
    return b[:k] + prop + b[k:]


def set_flag(b, name, value):
    b, n = re.subn(r"\n\t\t\(%s (yes|no)\)" % name, f"\n\t\t({name} {value})", b, count=1)
    if n != 1:
        raise SystemExit(f"no ({name} ...) line")
    return b


def edit(fname, ref, fn):
    t = rd(fname)
    s, e = symbol_by_ref(t, ref)
    new = fn(t[s:e])
    if new != t[s:e]:
        wr(fname, t[:s] + new + t[e:])
        return True
    return False


if not glob.glob("*.kicad_sch"):
    raise SystemExit("run from the board folder")
for ref, (sheet, old_lcsc, part) in PARTS.items():
    def change(b, ref=ref, old_lcsc=old_lcsc, part=part):
        if get_prop(b, "LCSC") == part[1]:
            return b
        if get_prop(b, "LCSC") != old_lcsc:
            raise SystemExit(f"{ref}: LCSC is {get_prop(b, 'LCSC')}, expected {old_lcsc} (or {part[1]})")
        for name, v in zip(("Value", "LCSC", "Digi-Key_PN", "Manufacturer", "MPN", "Datasheet"), part):
            b = set_prop(b, name, v)
        return b
    print(f"{ref}: {part[4]}", "set" if edit(sheet, ref, change) else "already set")

for ref, (sheet, lcsc) in DNP.items():
    def dnp(b, ref=ref, lcsc=lcsc):
        if get_prop(b, "LCSC") != lcsc:
            raise SystemExit(f"{ref}: LCSC is {get_prop(b, 'LCSC')}, expected {lcsc}")
        return set_flag(set_flag(set_flag(b, "dnp", "yes"), "in_bom", "no"), "in_pos_files", "no")
    print(f"{ref}: do not fit, out of BOM and position files", "(set)" if edit(sheet, ref, dnp) else "(already)")

units = {r: 0 for r in OPAMP_REFS}                       # t1a: every unit of every op-amp ref
changed = 0
for sheet in OPAMP_SHEETS:
    t = rd(sheet)
    out, pos = [], 0
    for m in re.finditer(r"\n\t\(symbol[\s(]", t):
        s = m.start() + 2
        if s < pos:
            continue
        e = block_end(t, s)
        b = t[s:e]
        refs = set(re.findall(r'\(reference "([^"]+)"\)', b))
        if not refs & OPAMP_REFS:
            continue
        if len(refs) != 1 or '(lib_id "Amplifier_Operational:LM324")' not in b:
            raise SystemExit(f"{sheet}: op-amp symbol {sorted(refs)} not a single-instance LM324 symbol")
        ref = refs.pop()
        units[ref] += 1
        if get_prop(b, "LCSC") != OPAMP[1]:
            if get_prop(b, "LCSC") not in (OPAMP_OLD_LCSC, "C46864"):     # baseline LM324PWR, or t1a's LM2902PWR
                raise SystemExit(f"{ref}: LCSC is {get_prop(b, 'LCSC')}, expected {OPAMP_OLD_LCSC} (or {OPAMP[1]})")
            for name, v in zip(("Value", "LCSC", "Digi-Key_PN", "Manufacturer", "MPN", "Datasheet"), OPAMP):
                b = set_prop(b, name, v)
            changed += 1
        out.append(t[pos:s] + b)
        pos = e
    new = "".join(out) + t[pos:]
    if new != t:
        wr(sheet, new)
for ref in sorted(units):
    if units[ref] != OPAMP_UNITS[ref]:
        raise SystemExit(f"{ref}: {units[ref]} op-amp units found, expected {OPAMP_UNITS[ref]}")
print(f"op-amps {', '.join(sorted(OPAMP_REFS))}: {OPAMP[4]}, {changed} of {sum(units.values())} units set")

# IS-chain zeners: every symbol (a driver sheet used several times carries several references) whose references are
# all IS zeners of this board; D1 (BATT_SENSE) is never one of them
ROOT = {"A": "DingoPDM.kicad_sch", "B": "dingoPDM-Max.kicad_sch"}[BOARD]
sheets, todo = [], [ROOT]
while todo:
    f = todo.pop()
    if f not in sheets:
        sheets.append(f)
        todo += re.findall(r'\(property "Sheetfile" "([^"]+)"', rd(f))
seen, zchanged = set(), 0
for sheet in sheets:
    t = rd(sheet)
    out, pos = [], 0
    for m in re.finditer(r"\n\t\(symbol[\s(]", t):
        s = m.start() + 2
        if s < pos:
            continue
        e = block_end(t, s)
        b = t[s:e]
        refs = set(re.findall(r'\(reference "([^"]+)"\)', b))
        if not refs or not refs <= IS_ZENERS or get_prop(b, "LCSC") not in (IS_ZENER_OLD_LCSC, IS_ZENER[1]):
            continue
        seen |= refs
        if get_prop(b, "LCSC") == IS_ZENER_OLD_LCSC:
            for name, v in zip(("Value", "LCSC", "Digi-Key_PN", "Manufacturer", "MPN", "Datasheet"), IS_ZENER):
                b = set_prop(b, name, v)
            zchanged += 1
        out.append(t[pos:s] + b)
        pos = e
    new = "".join(out) + t[pos:]
    if new != t:
        wr(sheet, new)
if seen != IS_ZENERS:
    raise SystemExit(f"IS zeners found {sorted(seen)}, expected {sorted(IS_ZENERS)}")
print(f"IS zeners {', '.join(sorted(IS_ZENERS))}: {IS_ZENER[4]}, {zchanged} symbols set")

print("board power schematic edits OK")
