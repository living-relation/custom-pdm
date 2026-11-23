"""Probe points (Fusion model mm: x, -y, z) for a built Fusion thermal model + the board model's own value there.

usage: python tools/fusion_thermal/probe_points.py <export json> <q W/mm3>
Prints one line per probe: name, X, Y, Z (what to type in Fusion's point probe) and the reference (board model) value.
Chips: middle of the driver lump (copper, = the board top under the exposed pad); parts: middle of the top sheet under
the part; 'laminate max': the board model's hottest node, in the sheet of its layer.
"""
import json
import sys

d = json.load(open(sys.argv[1]))
q = float(sys.argv[2])
r = d["reference"]
t = d["thickness"]
rows = []
if d["board"] == "IN":
    for k, (x, y) in d["probes"].items():
        rows.append((k, x, -y, t - 0.3, None))
    print("reference", {k: r[k] for k in ("board_max", "jumpers", "bat54s")})
else:
    ts = d["sheet_t"]
    ref_chip = {c["ref"]: c for c in r["chips"]}
    for c in d["chips"]:
        if c["P"] <= 0:
            continue
        w, h = c["ep"]
        hh = c["P"] / (q * w * h) if q > 0 else 0
        hh = max(hh, 0.1)
        rows.append((c["ref"], c["xy"][0], -c["xy"][1], round(t + hh / 2, 3),
                     f"board {ref_chip[c['ref']]['t_board']} Tj {ref_chip[c['ref']]['tj']} P {c['P']:.2f} RthJC {c['rthjc']}"))
    parts = r.get("parts", {})
    for k, (x, y) in d["probes"].items():
        rows.append((k, x, -y, round(t - ts / 2, 3), parts.get(k, {}).get("t", r.get("t_sensor_u6") if k == "U6" else None)))
    lx, ly = r["laminate_at"]
    z = ts / 2 if r["laminate_layer"] in ("B.Cu", "In2.Cu") else t - ts / 2
    rows.append(("laminate-max", lx, -ly, round(z, 3), f"{r['laminate_max']} ({r['laminate_layer']})"))
    print("reference t_sink", r["t_sink"], "tj_max", r["tj_max"], r["hottest_chip"], "laminate", r["laminate_max"],
          "U6", r["t_sensor_u6"], "t_j1", r["t_j1"])
for row in rows:
    print(f"{row[0]:13} X {row[1]:8.3f}  Y {row[2]:8.3f}  Z {row[3]:6.3f}  ref {row[4]}")
