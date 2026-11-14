"""Digi-Key numbers for parts whose schematic Digi-Key_PN field is "TBD" or missing (text edit, like the other sch_*.py).

usage (from the board folder, after tools/sch_board_power.py):  python sch_digikey.py A|B

Only the Digi-Key_PN field changes, and only on symbols whose MPN field is a key of DIGIKEY below and whose
Digi-Key_PN is "TBD", empty or missing. Any other Digi-Key number already there stops the script.
Rule (Dan, 2026-11-14): parts are chosen by design need and cost, not stock: the number is recorded even when Digi-Key
has none in stock. Only an exact maker-part match on the Digi-Key product page counts; no match = stays "TBD".
Cut tape (CT) number for reel parts, tube number for tube parts. Looked up 2026-11-14 on digikey.com:
  * MCP2562FD-E/SN          tube   https://www.digikey.com/en/products/detail/microchip-technology/MCP2562FD-E-SN/4842808
  * GRM21BR6YA106KE43L      CT     https://www.digikey.com/en/products/detail/murata-electronics/GRM21BR6YA106KE43L/5026445
  * BTS70041EPPXUMA1        CT     https://www.digikey.com/en/products/detail/infineon-technologies/BTS70041EPPXUMA1/7791523
  * MB85RC64TAPNF-G-AWERE2  TR (the only packaging listed; part status "Obsolete")
                                   https://www.digikey.com/en/products/result?keywords=MB85RC64TAPNF-G-AWERE2
Left "TBD" (no exact Digi-Key listing): KEMET C0805C473K5RAC7800 (Digi-Key search lands on C0805C473K5RACTU),
UNI-ROYAL 0805W8F1200T5E (no Digi-Key result). The PCB side is tools/pcb_digikey.py. Safe to re-run.
"""
import glob
import re
import sys

# MPN field -> Digi-Key number
DIGIKEY = {
    "MCP2562FD-E/SN": "MCP2562FD-E/SN-ND",
    "GRM21BR6YA106KE43L": "490-10514-1-ND",
    "BTS70041EPPXUMA1": "BTS70041EPPXUMA1CT-ND",
    "MB85RC64TAPNF-G-AWERE2": "865-MB85RC64TAPNF-G-AWERE2TR-ND",
}
UNSET = (None, "", "TBD")


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


def main():
    board = sys.argv[1].upper()
    if board not in ("A", "B") or not glob.glob("*.kicad_sch"):
        raise SystemExit("usage: run from the board folder: python sch_digikey.py A|B")
    done = []
    for fname in sorted(glob.glob("*.kicad_sch")):
        t = rd(fname)
        out, pos = [], 0
        for m in re.finditer(r"\n\t\(symbol[\s(]", t):
            s = m.start() + 2
            e = block_end(t, s)
            b = t[s:e]
            dk = DIGIKEY.get(get_prop(b, "MPN"))
            if dk:
                have = get_prop(b, "Digi-Key_PN")
                refs = ",".join(sorted(set(re.findall(r'\(reference "([^"]+)"\)', b))))
                if have not in UNSET + (dk,):
                    raise SystemExit(f"{fname} {refs}: Digi-Key_PN is {have!r}, expected TBD or {dk}")
                if have != dk:
                    b = set_prop(b, "Digi-Key_PN", dk)
                    done.append(f"{fname} {refs}: {get_prop(b, 'MPN')} -> {dk}")
            out += [t[pos:s], b]
            pos = e
        out.append(t[pos:])
        new = "".join(out)
        if new != t:
            wr(fname, new)
    for line in done:
        print("  digikey:", line)
    print(f"board {board} Digi-Key schematic stage:", f"{len(done)} symbols set" if done else "nothing to change")


if __name__ == "__main__":
    main()
