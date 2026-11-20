"""Print the clearance report (check.json) of a v2b run: overlaps first, then near misses. Usage: show_check.py F1|F2"""
import json, os, sys
d = json.load(open(os.path.join(os.environ["RUN_DIR"], sys.argv[1], "check.json")))
for r in d["pairs"]:
    print(f"{r['overlap_mm3']:9.1f} mm3  gap {r['min_gap']:6.3f}  {r['a']} | {r['b']}  {r['overlap_bbox'] or r['at_a']}")
