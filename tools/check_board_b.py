"""Board B netlist checks for the channel 5-8 additions. usage: python tools/check_board_b.py <netlist.net>"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import netlist_pins  # noqa: E402

d = netlist_pins.parse(sys.argv[1])
by_net = {}
for ref, rows in d.items():
    for pin, fn, net in rows:
        by_net.setdefault(net, []).append((ref, pin, fn))
pin_net = {(ref, pin): net for ref, rows in d.items() for pin, fn, net in rows}
bad = 0

# LM324 unit: (+in, -in, out)
UNITS = [("3", "2", "1"), ("5", "6", "7"), ("10", "9", "8"), ("12", "13", "14")]
for ch in range(1, 9):
    is_net = f"PF_IS{ch}"
    nodes = by_net.get(is_net, [])
    rs = [r for r, p, f in nodes if r.startswith("R")]
    mcu = [p for r, p, f in nodes if r == "U4"]
    path = "?"
    for r in rs:
        other = [pin_net[(r, p)] for p in ("1", "2") if pin_net.get((r, p)) != is_net][0]
        for ref, p, f in by_net[other]:
            for plus, minus, out in UNITS:
                if p == out and ref.startswith("U"):
                    path = f"{r} <- {ref} out{out} <- +in {pin_net[(ref, plus)]}"
    ok = mcu and path != "?" and (f"CH{ch}/" in path if ch > 4 else True)
    bad += not ok
    print(f"{is_net:8} U4 pin {mcu}  {path}  {'OK' if ok else 'CHECK'}")

for ch in range(5, 9):
    outs = sorted({r for r, p, f in by_net.get(f"PF_OUT{ch}", []) if r.startswith("U")})
    jp = sorted(p for r, p, f in by_net.get(f"PF_OUT{ch}", []) if r == "J6")
    ok = len(outs) == 1 and len(jp) == 2
    bad += not ok
    print(f"PF_OUT{ch}: switch {outs} J6 pins {jp} {'OK' if ok else 'CHECK'}")
for net in ("PF_IN5", "PF_IN6", "PF_IN7", "PF_IN8", "PF_DEN5_6", "PF_DEN7_8"):
    sw = sorted(r for r, p, f in by_net.get(net, []) if r.startswith("U") and r != "U4")
    rr = sorted(r for r, p, f in by_net.get(net, []) if r.startswith("R"))
    mcu = [p for r, p, f in by_net.get(net, []) if r == "U4"]
    print(f"{net:10} U4 pin {mcu} parts {sorted(set(r for r, p, f in by_net.get(net, []) if r != 'U4'))}")
    bad += not mcu
print("FAIL" if bad else "ALL OK")
sys.exit(1 if bad else 0)
