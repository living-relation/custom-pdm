"""Board build stage (last): the KiCad stackup's copper thickness = the copper that is ordered (tools/copper_order.py).

usage:  python tools/pcb_stackup.py <board.kicad_pcb> <A|B>

Text edit of the (stackup ...) block only: the four copper (thickness ...) values; the one prepreg layer takes the
difference so the board thickness in (general ...) stays as it was (the board STEP and the enclosure model do not
change). Nothing else in the file changes: no footprint, pad, net, track or zone (the file stays KiCad 9 format;
line ends kept). Idempotent.
The upstream boards carried 43.18 um outer / 17.272 um inner; JLCPCB builds 35 um (1 oz) outer and the inner
weight on the order form, so the heat checks must not read the upstream numbers (docs/order-readiness.md 3.3).
The dielectric thicknesses are upstream's, not JLCPCB's (JLCPCB builds its own 1.6 mm stackup; fab-notes.md).
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import copper_order  # noqa: E402


def fmt(mm):
    return ("%.6f" % mm).rstrip("0").rstrip(".")


def main(path, key):
    with open(path, encoding="utf-8", newline="") as f:
        t = f.read()
    a = t.find("(stackup")
    z = t.find("(copper_finish", a)
    if a < 0 or z < 0:
        raise SystemExit(f"{path}: no stackup block")
    s = t[a:z]
    want = {n: v * 1e3 for n, v in copper_order.thickness(key).items()}      # mm
    n_set = 0

    def one(m):
        nonlocal n_set
        n_set += 1
        return m.group(1) + fmt(want[m.group(2)]) + ")"
    s2 = re.sub(r'(\(layer "([^"]+\.Cu)"\s*\(type "copper"\)\s*\(thickness )[0-9.]+\)', one, s)
    if n_set != len(want):
        raise SystemExit(f"{path}: {n_set} copper layers in the stackup, expected {len(want)}")
    # the board thickness in (general ...) stays: the one prepreg takes the copper difference
    g = re.search(r"\(general\s*\(thickness ([0-9.]+)\)", t)
    pre = re.compile(r'(\(type "prepreg"\)\s*\(thickness )([0-9.]+)\)')
    if not g or len(pre.findall(s2)) != 1:
        raise SystemExit(f"{path}: need (general (thickness ...)) and exactly one prepreg layer")
    total = float(g.group(1))
    others = sum(float(v) for v in re.findall(r"\(thickness ([0-9.]+)\)", s2)) - float(pre.search(s2).group(2))
    s2 = pre.sub(lambda m: m.group(1) + fmt(total - others) + ")", s2)
    t2 = t[:a] + s2 + t[z:]
    if t2 != t:
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(t2)
    print(f"pcb_stackup {key}: copper {copper_order.text(key)}; board thickness {fmt(total)} mm"
          + ("" if t2 != t else " (already set)"))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2].upper())
