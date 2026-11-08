"""Board A step 2 (schematic): re-pin J3 so dual U8's two outputs land on the two J3 pins beside it.

U8 stays where the old BTS7002 was. Its OUT0 pads (left) face J3 pin 8, its OUT1 pads (right) face J3 pin 7.
OUT0 is PF_OUT1 and OUT1 is PF_OUT2 (set by sch_swap_board_a.py), so:
  J3 pin 7 = PF_OUT2 (was PF_OUT1), pin 8 = PF_OUT1 (was INPUT1), pin 12 = INPUT1 (was PF_OUT2).
Run from hardware/board-a after sch_swap_board_a.py.
"""
import re


def rd(p):
    with open(p, encoding="utf-8", newline="") as f:
        return f.read().replace("\r\n", "\n")


def wr(p, t):
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(t)


def rename_label_at(t, old, new, at):
    pat = re.compile(r'\(global_label "' + re.escape(old) + r'"(\n\s*(?:\(shape \w+\)\n\s*)?\(at ' + re.escape(at) + r'\))')
    t2, n = pat.subn(lambda m: f'(global_label "{new}"' + m.group(1), t)
    if n != 1:
        raise SystemExit(f"{old} at {at}: {n} matches")
    return t2


p = "Connectors.kicad_sch"
t = rd(p)
t = rename_label_at(t, "PF_OUT1", "PF_OUT2", "101.6 59.055 180")   # pin 7
t = rename_label_at(t, "INPUT1", "PF_OUT1", "101.6 61.595 180")    # pin 8
t = rename_label_at(t, "PF_OUT2", "INPUT1", "101.6 71.755 180")    # pin 12
wr(p, t)
print("re-pin OK")
