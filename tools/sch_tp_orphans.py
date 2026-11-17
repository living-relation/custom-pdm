"""Board A: remove the labels and power symbols that only connected to a removed test point (text edit).

tools/sch_inputs_board_a.py deletes every Connector:TestPoint symbol (Dan, 2026-11-08). Five items sat directly on such
a test point's pin and nothing else: global labels I2C1_SCL / I2C1_SDA (TP5 / TP6, I2C sheet), labels CAN_TX / CAN_RX
(TP2 / TP3, MCU sheet) and the GND power symbol #PWR08 (TP1, Power sheet). With the test point gone they are the ERC
errors stock dingoPDM does not have (4 x label_dangling, 1 x pin_not_connected). Removing them changes no net: each
net still has its other labels / pins (netlist identical).

Rule: a label, global label or power symbol is removed when its connection point is a removed test point's pin AND no
wire, bus entry, junction or other item ends there (a test point that sch_inputs_board_a.py turned into a label keeps
its wire to U4, so that label stays).

remove_orphans(text, points) is called by tools/sch_inputs_board_a.py right after the test points are removed.
Standalone, on a board A folder that is already built (safe to re-run):
    python sch_tp_orphans.py <baseline commit>      e.g. 542b3b9; reads the test-point positions with git show
"""
import glob
import re
import subprocess
import sys

TESTPOINT_LIB = "Connector:TestPoint"


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


def key(x, y):
    return (round(float(x), 3), round(float(y), 3))


def testpoint_pins(t):
    """{(x, y): ref} of the Connector:TestPoint symbols in a sheet (pin 1 sits at the symbol origin)."""
    out = {}
    for m in re.finditer(r'\n\t\(symbol\s*\(lib_id "%s"\)\s*\(at ([\d.\-]+) ([\d.\-]+)' % re.escape(TESTPOINT_LIB), t):
        b = t[m.start() + 2:block_end(t, m.start() + 2)]
        out[key(m.group(1), m.group(2))] = re.search(r'"Reference" "([^"]+)"', b).group(1)
    return out


def _touched(t, pt, skip):
    """True when something other than the block at `skip` connects at pt (wire / bus end, junction, label, symbol)."""
    x, y = pt
    for m in re.finditer(r'\(xy ([\d.\-]+) ([\d.\-]+)\)', t):
        if key(*m.groups()) == pt:
            return True
    for m in re.finditer(r'\n\t\((junction|label|global_label|hierarchical_label|no_connect|symbol)\s', t):
        s = m.start() + 2
        if s == skip:
            continue
        a = re.search(r'\(at ([\d.\-]+) ([\d.\-]+)', t[s:s + 400])
        if a and key(*a.groups()) == pt:
            return True
    return False


def remove_orphans(t, points):
    """Remove labels / power symbols sitting alone on `points`. Returns (new text, [description, ...])."""
    removed = []
    while True:
        hit = None
        for m in re.finditer(r'\n\t\((label|global_label) "([^"]*)"|\n\t\(symbol\s*\(lib_id "(power:[^"]+)"\)', t):
            s = m.start() + 2
            a = re.search(r'\(at ([\d.\-]+) ([\d.\-]+)', t[s:s + 400])
            if not a or key(*a.groups()) not in points or _touched(t, key(*a.groups()), s):
                continue
            e = block_end(t, s)
            if m.group(1):
                what = f"{m.group(1)} {m.group(2)}"
            else:
                what = "power " + re.search(r'"Reference" "([^"]+)"', t[s:e]).group(1)
            hit = (s, e, f"{what} at {key(*a.groups())}")
            break
        if not hit:
            return t, removed
        s, e, what = hit
        k = s - 2                                     # also drop the line break + tab before the block
        if k > 0 and t[k - 1] == "\r":                # CRLF working copy (git autocrlf)
            k -= 1
        t = t[:k] + t[e:]
        removed.append(what)


def main():
    if len(sys.argv) != 2 or not glob.glob("DingoPDM.kicad_sch"):
        raise SystemExit("usage: run from hardware/board-a: python sch_tp_orphans.py <baseline commit>")
    base = sys.argv[1]
    total = []
    for f in sorted(glob.glob("*.kicad_sch")):
        old = subprocess.run(["git", "show", f"{base}:./{f}"], capture_output=True, text=True, encoding="utf-8")
        if old.returncode:
            continue                                  # sheet not in the baseline
        pts = testpoint_pins(old.stdout)
        if not pts:
            continue
        with open(f, encoding="utf-8", newline="") as fh:
            t = fh.read()
        if testpoint_pins(t):
            raise SystemExit(f"{f}: test points still present (run tools/sch_inputs_board_a.py first)")
        new, removed = remove_orphans(t, set(pts))
        if new != t:
            with open(f, "w", encoding="utf-8", newline="") as fh:
                fh.write(new)
        total += [f"{f}: {r}" for r in removed]
    for line in total:
        print("  removed", line)
    print("test-point orphans:", f"{len(total)} removed" if total else "nothing to change")


if __name__ == "__main__":
    main()
