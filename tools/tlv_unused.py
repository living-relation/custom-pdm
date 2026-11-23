"""Unused TLV9004 channels on board A (job tlvunused, 2026-11-23; found by job drcclean, docs/drc-erc-review.md).

  python             tools/tlv_unused.py sch                          (from hardware/board-a, after the board-a.net export)
  python.exe (KiCad 9) tools/tlv_unused.py pcb <board.kicad_pcb> <netlist.net>   (after hw_5v_module.py pcb)

Board A fits 6 of the 8 TLV9004 channels (two quad TLV9004IPWR, U7 and U12, as current-sense followers). Stock
dingoPDM never placed U7 channel A (unit 1, pins 1-3) or U12 channels A and B (units 1 and 2, pins 1-3 / 5-7) in the
schematic, so those pins had no net and the inputs floated (ERC missing_unit / missing_input_pin).

Fix (coordinator default 2026-11-23): each unused channel is a voltage follower, OUT tied to IN-, IN+ to GND.
  * TI SBOA204A "How to Properly Configure Unused Operational Amplifiers" (Oct 2017, rev. Sep 2018): configure the
    unused channel as a follower (output to the inverting input, negative feedback) with the non-inverting input on
    "any reference voltage that is within the specified common mode and output ranges"; the technique favours
    rail-to-rail input / output parts. (For single-supply parts it prefers a mid-supply divider and notes that a
    grounded input pins the output at the low rail; a divider is two new parts per channel, out of scope here.)
  * TI SBOS833R (TLV9002 / TLV9004 data sheet) 7.5: input common-mode range (V-) - 0.1 V .. (V+) + 0.1 V, so GND
    (V-) is inside it; rail-to-rail output (swing from rail 20 mV max at RL 10 k). The output then rests at the GND
    rail with no load: the same state every used IS follower is in whenever its PROFET output is off (IS = 0 V), which
    the supply-current budget already counts (8 x IQ, tools/verify_mcu.py).
Schematic: one new unit instance per unused channel (same symbol, same reference, U7 unit 1, U12 units 1 / 2) at a
free spot of its sheet, with wires OUT -> IN- and IN+ -> a GND power symbol. UUIDs are uuid5 (stable rebuilds).
PCB: the pads get the netlist nets; OUT - IN- (neighbour pads, 0.65 mm pitch) joined by one straight top track at the
pad centre line, as the stock design joins its used channels; IN+ gets a GND via (0.8 / 0.4 mm) to the In1 GND plane
on a short top track (exact-shape clearance check, tools/hw_protect.py Copper). No footprint, pad, terminal or other
net changes; zones refilled. Idempotent.
"""
import os
import re
import sys
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import hw_protect as H  # noqa: E402

LIB_ID = "Amplifier_Operational:LM324"            # the generic quad symbol board A uses for the TLV9004IPWR
# (ref, unit, sheet): out pin, in- pin, in+ pin (TI SBOS833R Table 6-5, PW: 1 OUT1, 2 IN1-, 3 IN1+, 5 IN2+, 6 IN2-, 7 OUT2)
UNUSED = [
    ("U7", 1, "HighCurrentDrivers.kicad_sch", ("1", "2", "3")),
    ("U12", 1, "MedCurrentDrivers.kicad_sch", ("1", "2", "3")),
    ("U12", 2, "MedCurrentDrivers.kicad_sch", ("7", "6", "5")),
]
NS = uuid.UUID("3f0c7c1e-6a54-4b71-9f8e-7c1d2b9a4e10")
MPN = "TLV9004IPWR"


def _uuids(b, key):
    n = [0]

    def rep(m):
        n[0] += 1
        return f'(uuid "{uuid.uuid5(NS, f"{key}/{n[0]}")}")'
    return re.sub(r'\(uuid "[^"]+"\)', rep, b)


def _wire(pts, key, nl):
    (x0, y0), (x1, y1) = pts
    return (f"(wire{nl}\t\t(pts{nl}\t\t\t(xy {H.fmt(x0)} {H.fmt(y0)}) (xy {H.fmt(x1)} {H.fmt(y1)}){nl}\t\t){nl}"
            f"\t\t(stroke{nl}\t\t\t(width 0){nl}\t\t\t(type default){nl}\t\t){nl}"
            f'\t\t(uuid "{uuid.uuid5(NS, key)}"){nl}\t)')


def _pwr_refs():
    nums = []
    for f in os.listdir("."):
        if f.endswith(".kicad_sch"):
            nums += [int(n) for n in re.findall(r'\(reference "#PWR0*(\d+)"\)', H.rd(f))]
    return max(nums)


def sch():
    if not os.path.exists("DingoPDM.kicad_sch"):
        raise SystemExit("run from hardware/board-a")
    pwr = _pwr_refs()
    for ref, unit, sheet, (o, n, p) in UNUSED:
        t = H.rd(sheet)
        nl = "\r\n" if "\r\n" in t else "\n"
        inst = [(s, e) for s, e in H.top_blocks(t, "symbol")
                if f'(reference "{ref}")' in t[s:e] and f'(lib_id "{LIB_ID}")' in t[s:e]]
        units = {int(re.search(r"\n\t\t\(unit (\d+)\)", t[s:e]).group(1)): (s, e) for s, e in inst}
        if unit in units:
            print(f"  {ref} unit {unit}: already placed")
            continue
        if not units:
            raise SystemExit(f"{ref}: no {LIB_ID} instance on {sheet}")
        s, e = units[min(units)]
        tpl = t[s:e]
        if H.get_prop(tpl, "MPN") != MPN:
            raise SystemExit(f"{ref}: MPN {H.get_prop(tpl, 'MPN')}, expected {MPN}")
        lib = H.lib_block(t, LIB_ID)
        k = lib.index(f'(symbol "LM324_{unit}_1"')
        pins = {num: (float(px), float(py)) for px, py, num in
                re.findall(r'\(pin \w+ \w+\s*\(at ([\d.\-]+) ([\d.\-]+) \d+\)[\s\S]*?\(number "([^"]+)"',
                           lib[k:H.block_end(lib, k)])}
        if sorted(pins) != sorted((o, n, p)):
            raise SystemExit(f"{ref} unit {unit}: symbol pins {sorted(pins)}, expected {sorted((o, n, p))}")
        # free spot: symbol body +-7.62 mm wide, feedback wire 7.62 mm below, GND symbol 5 mm left
        ox, oy = H.free_box(t, 33.02, 22.86)
        x, y = ox + 17.78, oy + 10.16
        b = H.move_block(tpl, x, y)
        b = re.sub(r"(\n\t\t\(unit )\d+(\))", rf"\g<1>{unit}\2", b, count=1)
        b = re.sub(r"(\(reference \"%s\"\)\s*\(unit )\d+(\))" % re.escape(ref), rf"\g<1>{unit}\2", b)
        b = _uuids(b, f"{ref}/{unit}/symbol")
        pe = {num: (round(x + px, 4), round(y - py, 4)) for num, (px, py) in pins.items()}
        (xo, yo), (xn, yn), (xp, yp) = pe[o], pe[n], pe[p]
        key = f"{ref}/{unit}"
        xl = xn - 2.54
        items = [b,
                 _wire(((xo, yo), (xo, yo + 7.62)), key + "/w1", nl),
                 _wire(((xo, yo + 7.62), (xl, yo + 7.62)), key + "/w2", nl),
                 _wire(((xl, yo + 7.62), (xl, yn)), key + "/w3", nl),
                 _wire(((xl, yn), (xn, yn)), key + "/w4", nl),
                 _wire(((xp, yp), (xp - 5.08, yp)), key + "/w5", nl)]
        project = re.search(r'\(project "([^"]+)"', tpl).group(1)
        path = re.search(r'\(path "([^"]+)"', tpl).group(1)
        pwr += 1
        g = H.gnd_symbol(t, xp - 5.08, yp, f"#PWR0{pwr}", project, path)
        items.append(_uuids(g, key + "/gnd"))
        note = (f"tlvunused: {ref} channel {'AB'[unit - 1]} not used: follower, IN+ to GND (TI SBOA204A; "
                f"TLV9004 VCM (V-)-0.1 V .. (V+)+0.1 V, SBOS833R 7.5)")
        items.append(re.sub(r'\(uuid "[^"]+"\)', f'(uuid "{uuid.uuid5(NS, key + "/text")}")', H.text(note, ox, oy)))
        items = [it.replace("\r\n", "\n").replace("\n", nl) for it in items]
        t = _insert(t, items, nl)
        H.wr(sheet, t)
        print(f"  {ref} unit {unit} ({sheet}) at ({H.fmt(x)}, {H.fmt(y)}): OUT {o} -> IN- {n}, IN+ {p} -> GND (#PWR0{pwr})")
    print("tlv_unused sch: done")


def _insert(t, items, nl):
    for marker in (nl + "\t(sheet_instances", nl + "\t(embedded_fonts"):
        if marker in t:
            k = t.index(marker)
            break
    else:
        k = t.rstrip().rindex(")")
        while t[k - 1] in "\r\n\t ":
            k -= 1
    return t[:k] + "".join(nl + "\t" + it for it in items) + t[k:]


def pcb(path, netfile):
    import math
    import pcbnew
    import netlist_pins
    mm, tomm = pcbnew.FromMM, pcbnew.ToMM

    def V(x, y):
        return pcbnew.VECTOR2I(mm(x), mm(y))

    nl = netlist_pins.parse(netfile)
    padnet = {(r, p): n for r, rows in nl.items() for p, fn, n in rows}
    b = pcbnew.LoadBoard(path)

    def pad(ref, num):
        return next(q for q in b.FindFootprintByReference(ref).Pads() if q.GetNumber() == num)

    def xy(it):
        q = it.GetPosition()
        return round(tomm(q.x), 4), round(tomm(q.y), 4)

    # 1. nets from the netlist (only on pads that have none; anything else is an error)
    changed = 0
    for ref, unit, sheet, pins in UNUSED:
        for num in pins:
            want, q = padnet.get((ref, num)), pad(ref, num)
            if not want:
                raise SystemExit(f"{ref} pin {num}: no net in the netlist (run tlv_unused.py sch first)")
            if q.GetNetname() == want:
                continue
            if q.GetNetname():
                raise SystemExit(f"{ref} pad {num}: on {q.GetNetname()}, netlist says {want}")
            ni = b.FindNet(want)
            if ni is None:
                ni = pcbnew.NETINFO_ITEM(b, want)
                ni.thisown = False
                b.Add(ni)
            q.SetNet(ni)
            changed += 1
        o, n, p = pins
        if padnet[(ref, o)] != padnet[(ref, n)] or padnet[(ref, p)] != "GND" or padnet[(ref, o)] == "GND":
            raise SystemExit(f"{ref} unit {unit}: netlist is not a follower with IN+ on GND")
    if not changed:
        print("tlv_unused pcb: already applied")
        return
    edge = pcbnew.SHAPE_POLY_SET()
    b.GetBoardPolygonOutlines(edge)
    K = H.Copper(b, pcbnew, mm, tomm, V, edge)
    # 2. OUT - IN-: one straight top track between the neighbour pads (pad centre line, as stock)
    for ref, unit, sheet, (o, n, p) in UNUSED:
        a, c = xy(pad(ref, o)), xy(pad(ref, n))
        net = padnet[(ref, o)]
        if abs(a[0] - c[0]) > 1e-3 or abs(abs(a[1] - c[1]) - 0.65) > 1e-3:
            raise SystemExit(f"{ref}: pads {o} / {n} are not neighbours in one row")
        if not K.seg_ok(net, a, c, "F.Cu"):
            raise SystemExit(f"{ref}: OUT - IN- track {a} -> {c} not clear")
        K.add_track(net, a, c, "F.Cu")
        print(f"  {ref} unit {unit}: {net} top track pad {o} {a} -> pad {n} {c}")
    # 3. IN+: a GND via beside the pad on a short top track
    for ref, unit, sheet, (o, n, p) in UNUSED:
        a = xy(pad(ref, p))
        v = K.via_near("GND", a, rmin=0.6, rmax=2.5)
        K.stub("GND", a, v)
        K.add_via("GND", v)
        print(f"  {ref} unit {unit}: IN+ pad {p} -> GND via {v} ({math.hypot(v[0] - a[0], v[1] - a[1]):.2f} mm)")
    for z in b.Zones():
        z.UnFill()
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    b.Save(path)
    print("tlv_unused pcb: done")


if __name__ == "__main__":
    if sys.argv[1:2] == ["sch"]:
        sch()
    elif sys.argv[1:2] == ["pcb"] and len(sys.argv) == 4:
        pcb(sys.argv[2], sys.argv[3])
    else:
        raise SystemExit(__doc__)
