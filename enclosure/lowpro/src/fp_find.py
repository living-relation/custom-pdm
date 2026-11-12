"""Print reference, position and footprint of connector footprints in the board files (KiCad coords)."""
import re, sys
for fn in sys.argv[1:]:
    t = open(fn, encoding="utf8").read()
    print("==", fn)
    for m in re.finditer(r'\(footprint "([^"]+)"(.*?)\n\t\(', t, re.S):
        pass
    # crude split on top-level footprints
    parts = t.split("\n\t(footprint ")
    for p in parts[1:]:
        name = p.split('"')[1]
        if not re.search(r"Connector|USB|Molex|JST|Terminal|REDCUBE|7461|DT", name, re.I):
            continue
        at = re.search(r"\(at ([-\d.]+) ([-\d.]+)( [-\d.]+)?\)", p)
        ref = re.search(r'\(property "Reference" "([^"]+)"', p)
        m3d = re.findall(r'\(model "([^"]+)"', p)
        print(f"  {ref.group(1) if ref else '?':6s} at {at.group(1)},{at.group(2)} rot{(at.group(3) or ' 0').strip()}  {name}  3d={[x.split('/')[-1] for x in m3d]}")
