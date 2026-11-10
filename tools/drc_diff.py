"""Compare two kicad-cli DRC JSON reports: counts per type, and the items of chosen types.

usage: python tools/drc_diff.py <baseline.json> <new.json> [type ...]
"""
import collections
import json
import sys

base, new = (json.load(open(p)) for p in sys.argv[1:3])
show = set(sys.argv[3:])
cb = collections.Counter(v["type"] for v in base.get("violations", []))
cn = collections.Counter(v["type"] for v in new.get("violations", []))
print(f"{'type':28} {'base':>5} {'new':>5} {'delta':>6}")
for k in sorted(set(cb) | set(cn)):
    print(f"{k:28} {cb.get(k, 0):5} {cn.get(k, 0):5} {cn.get(k, 0) - cb.get(k, 0):+6}")
print(f"{'unconnected':28} {len(base.get('unconnected_items', [])):5} {len(new.get('unconnected_items', [])):5}")
print(f"{'schematic parity':28} {len(base.get('schematic_parity', [])):5} {len(new.get('schematic_parity', [])):5}")
for u in new.get("unconnected_items", []):
    print("UNCONNECTED", [(i["description"], i["pos"]["x"], i["pos"]["y"]) for i in u["items"]])
for v in new.get("violations", []):
    if v["type"] in show:
        print(v["type"], "|", v["description"][:110], "|", [(i["description"][:60], round(i["pos"]["x"], 2), round(i["pos"]["y"], 2)) for i in v["items"]])
if "parity" in show:
    c = collections.Counter(p["type"] for p in new.get("schematic_parity", []))
    print(dict(c))
    for p in new.get("schematic_parity", []):
        if p["type"] != "footprint_symbol_field_mismatch":
            print(p["type"], "|", p["description"], [i["description"] for i in p["items"]])
