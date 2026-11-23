"""The copper that is ORDERED per board: the one table the fab notes, the KiCad stackups and every copper / heat check
read, so no check can pass on a copper thickness that is not on the order form.

usage (repo root, any python 3; no KiCad needed):
    python tools/copper_order.py            print the table
    python tools/copper_order.py --check    fab notes (hardware/fab/*/fab-notes.md), KiCad stackups and this table agree
                                            (exit 1 on any difference)

Decisions:
  board B   1 oz outer + 1 oz inner (35 / 35 um): Dan, 2026-11-22, c1 = a (docs/order-readiness.md 3.3: JLCPCB's
            default 0.5 oz inner gives 136-137 C laminate at the 150 A feed limit, limit 130 C; 1 oz inner 115-120 C).
  board A   JLCPCB default 1 oz outer + 0.5 oz inner (35 / 17.5 um): nothing else was decided; tools/verify_copper.py
            is run at this copper (docs/pcb-verification.md).
  input     2 layers, 1 oz (35 um): JLCPCB default; the board carries no load current.
Sources: JLCPCB "Copper Weight" help article (read 2026-11-22): FR-4 outer 1 oz (= 35 um) or 2 oz; inner 0.5 oz
(default), 1 oz or 2 oz, https://jlcpcb.com/help/article/jlcpcb-copper-weight . 0.5 oz = 17.5 um is half of the 1 oz
figure (IPC nominal 17.1 um; ASSUMED as in docs/pcb-verification.md since 2026-11-20).

Used by: tools/verify_copper.py and tools/thermal_board_b.py (default copper = this table; --outer-um / --inner-um
with any other value is a what-if run: it is labelled so, exits 2 and writes "ordered": false into its JSON),
tools/verify_thermal_box.py (refuses a JSON that was not run at the ordered copper), tools/gen_fab_jlcpcb.py (fab
notes row + order remark), tools/pcb_stackup.py (KiCad stackup).
"""
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UM_PER_OZ = 35.0
# key: outer / inner copper weight in oz (inner None = 2-layer board), board file, fab folder, who decided
ORDER = {
    "A": dict(outer_oz=1.0, inner_oz=0.5, pcb="hardware/board-a/DingoPDM.kicad_pcb", fab="board-a",
              why="kept at JLCPCB's default, 2026-11-22 (only board B was changed)"),
    "B": dict(outer_oz=1.0, inner_oz=1.0, pcb="hardware/board-b-max/dingoPDM-Max.kicad_pcb", fab="board-b",
              why="Dan, 2026-11-22, c1 = a (docs/order-readiness.md 3.3)"),
    "IN": dict(outer_oz=1.0, inner_oz=None, pcb="hardware/input-board/input-board.kicad_pcb", fab="input-board",
               why="JLCPCB's default (2 layers, no load current)"),
}
OUTER, INNER = ("F.Cu", "B.Cu"), ("In1.Cu", "In2.Cu")
FAB_TAG = {v["fab"]: k for k, v in ORDER.items()}


def key_of(board):
    """A / B / IN for a verify_copper board key (BSTOCK, B4: board B) or a fab folder name."""
    b = str(board)
    if b in FAB_TAG:
        return FAB_TAG[b]
    b = b.upper()
    return "IN" if b.startswith("IN") else b[0]


def oz(v):
    return f"{v:g} oz"


def um(key):
    """(outer um, inner um or None) ordered for this board."""
    o = ORDER[key_of(key)]
    return o["outer_oz"] * UM_PER_OZ, (None if o["inner_oz"] is None else o["inner_oz"] * UM_PER_OZ)


def thickness(key):
    """{layer: metres} of the ordered copper."""
    outer, inner = um(key)
    th = {n: outer * 1e-6 for n in OUTER}
    if inner is not None:
        th.update({n: inner * 1e-6 for n in INNER})
    return th


def apply(th, key, outer_um=None, inner_um=None):
    """The copper a check must use: the ORDERED copper of board `key` written into th (layer -> m), unless a what-if
    value is given. Returns (th, ordered, label); ordered is False when any layer differs from the order."""
    want = thickness(key)
    th = dict(th)
    th.update({n: v for n, v in want.items() if n in th})
    if outer_um:
        th.update({n: outer_um * 1e-6 for n in OUTER if n in th})
    if inner_um:
        th.update({n: inner_um * 1e-6 for n in INNER if n in th})
    ordered = all(abs(th[n] - want[n]) < 0.05e-6 for n in want if n in th)
    k = key_of(key)
    label = (f"ORDERED copper, board {k}: {text(k)}" if ordered else
             f"WHAT-IF copper (NOT what is ordered for board {k}: {text(k)}): no verdict for the order")
    return th, ordered, label


def text(key):
    """Short words for one board, e.g. '1 oz outer (35 um) + 1 oz inner (35 um)'."""
    o = ORDER[key_of(key)]
    outer, inner = um(key)
    s = f"{oz(o['outer_oz'])} outer ({outer:g} um)"
    return s if inner is None else s + f" + {oz(o['inner_oz'])} inner ({inner:g} um)"


def fab_row(key):
    """The 'Copper weight' cell of fab-notes.md."""
    k = key_of(key)
    o = ORDER[k]
    if o["inner_oz"] is None:
        return f"{oz(o['outer_oz'])} (35 um), both layers: {o['why']}"
    default = " = JLCPCB's default" if o["inner_oz"] == 0.5 else " (NOT JLCPCB's default 0.5 oz: set it on the order form)"
    return (f"Outer copper weight {oz(o['outer_oz'])} ({um(k)[0]:g} um); inner copper weight {oz(o['inner_oz'])} "
            f"({um(k)[1]:g} um){default}: {o['why']}; table: `tools/copper_order.py`")


def remark(key):
    """Sentence for the order remark ('' when the order is JLCPCB's default)."""
    k = key_of(key)
    o = ORDER[k]
    if o["inner_oz"] in (None, 0.5):
        return ""
    return (f"Copper: outer layers {oz(o['outer_oz'])}, inner layers {oz(o['inner_oz'])} ({um(k)[1]:g} um finished) as "
            f"selected on the order form: please do not build this board with {oz(0.5)} inner copper.")


def stackup_um(path):
    """{layer: um} of the copper layers in a .kicad_pcb stackup block; {} when the file has none (KiCad then uses
    its 35 um default)."""
    t = open(path, encoding="utf-8").read()
    k = t.find("(stackup")
    if k < 0:
        return {}
    s = t[k:t.find("(copper_finish", k)]
    return {m.group(1): float(m.group(2)) * 1e3 for m in
            re.finditer(r'\(layer "([^"]+\.Cu)"\s*\(type "copper"\)\s*\(thickness ([0-9.]+)\)', s)}


def check():
    bad = []
    for k, o in ORDER.items():
        outer, inner = um(k)
        want = {n: outer for n in OUTER}
        if inner is not None:
            want.update({n: inner for n in INNER})
        have = stackup_um(os.path.join(REPO, o["pcb"]))
        if not have and inner is None and outer == 35.0:
            st = "no stackup block (KiCad default 35 um)"
        elif have.keys() == want.keys() and all(abs(have[n] - want[n]) < 0.05 for n in want):
            st = "stackup " + " / ".join(f"{have[n]:g}" for n in ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu") if n in have) + " um"
        else:
            st = None
            bad.append(f"board {k}: KiCad stackup {have or 'missing'} != ordered {want} (run tools/pcb_stackup.py)")
        notes = os.path.join(REPO, "hardware", "fab", o["fab"], "fab-notes.md")
        t = open(notes, encoding="utf-8").read() if os.path.exists(notes) else ""
        row = f"| Copper weight | {fab_row(k)} |"
        ok_row = row in t
        ok_rem = (not remark(k)) or remark(k) in t
        if not ok_row:
            bad.append(f"board {k}: {os.path.relpath(notes, REPO)} has no row '{row}' (run tools/gen_fab_jlcpcb.py)")
        if not ok_rem:
            bad.append(f"board {k}: the order remark in {os.path.relpath(notes, REPO)} does not carry the copper sentence")
        print(f"{'ok  ' if st and ok_row and ok_rem else 'FAIL'} board {k}: ordered {text(k)}; KiCad: {st or 'DIFFERENT'}; "
              f"fab notes row {'ok' if ok_row else 'DIFFERENT'}; remark {'ok' if ok_rem else 'MISSING'}")
    for b in bad:
        print("  " + b)
    print("RESULT", "PASS" if not bad else f"FAIL ({len(bad)})")
    return 1 if bad else 0


if __name__ == "__main__":
    if "--check" in sys.argv:
        sys.exit(check())
    for k, o in ORDER.items():
        print(f"board {k}: {text(k)}  [{o['why']}]")
