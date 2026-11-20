"""BOM / part-file check of the v2c assembly (Dan 2026-11-16: every part is its own file, inserted into the assembly, with its part
number and description). Usage: $CAD_PY bomcheck_v2c.py F1 [RUN_DIR]. Reads <run>/<VAR>/xref/<assembly>.step (STEP assembly with
external references) and BOM-v2c-<VAR>.csv. FAILS (exit 1) if any component of the assembly
  - is not an external reference to a part file that exists (Parts/<PN>.stp; subassemblies too),
  - has no part number (PRODUCT name) or no description, or its part file's PRODUCT name / description differ,
  - its part file holds no solid,
or if the instance count per part number differs from the BOM CSV. Writes <run>/<VAR>/bomcheck.json."""
import os, sys, re, json, csv
VAR = sys.argv[1]; RUN = sys.argv[2] if len(sys.argv) > 2 else os.environ["RUN_DIR"]
OUT = os.path.join(RUN, VAR); meta = json.load(open(os.path.join(OUT, "meta.json")))
AF = os.path.join(OUT, meta["assembly"]["file"]); AD = os.path.dirname(AF)
def parse(path):
    t = open(path, encoding="latin-1").read(); t = t[t.find("DATA;"):]
    ents = {}
    for m in re.finditer(r"#(\d+)\s*=\s*(.*?);\s*(?=#\d+\s*=|ENDSEC)", t, re.S):
        ents[int(m.group(1))] = re.sub(r"\s+", " ", m.group(2))
    return ents
def refs(s): return [int(x) for x in re.findall(r"#(\d+)", s)]
def strs(s): return re.findall(r"'((?:[^']|'')*)'", s)
fails = []; inst = {}; files = {}; TREE = []        # TREE: (depth, product, file, instances) for the report / Fusion tree check
def walk(path, depth=0, mult=1, seen=()):
    """one STEP assembly file: its top product's NEXT_ASSEMBLY_USAGE_OCCURRENCEs; a child whose external file is itself an
    assembly (revD subassembly) is walked in turn (its own references resolve from its own folder)"""
    E = parse(path); base = os.path.dirname(path)
    typ = {k: v.split("(", 1)[0].strip() for k, v in E.items()}
    prod = {k: strs(v) for k, v in E.items() if typ[k] == "PRODUCT"}
    pdf = {k: refs(v)[-1] for k, v in E.items() if typ[k] == "PRODUCT_DEFINITION_FORMATION"}
    pd = {k: refs(v)[0] for k, v in E.items() if typ[k] == "PRODUCT_DEFINITION"}
    def pd_product(k): return prod[pdf[pd[k]]]
    nauo = [refs(v)[:2] for k, v in E.items() if typ[k] == "NEXT_ASSEMBLY_USAGE_OCCURRENCE"]
    children = {c for _, c in nauo}; roots = {p for p, _ in nauo if p not in children}
    dfiles = {os.path.splitext(os.path.basename(strs(v)[0]))[0]: strs(v)[0] for k, v in E.items() if typ[k] == "DOCUMENT_FILE"}
    docfile = {}
    for k, v in E.items():
        if typ[k] == "APPLIED_DOCUMENT_REFERENCE":
            for tg in refs(v)[1:]:
                if tg in pd: docfile[tg] = dfiles.get(pd_product(tg)[0])
    count = {}
    for (parent, child) in nauo:
        if parent not in roots: continue                                    # only this file's own top level
        name, _, desc = (pd_product(child) + ["", "", ""])[:3]
        count[name] = count.get(name, 0) + 1
    for (parent, child) in nauo:
        if parent not in roots: continue
        name, _, desc = (pd_product(child) + ["", "", ""])[:3]
        if (path, name) in seen: continue
        seen = seen + ((path, name),)
        fn = docfile.get(child)
        if not name: fails.append(f"component #{child}: no part number")
        if not desc: fails.append(f"{name}: no description")
        if not fn: fails.append(f"{name}: not an external reference (no DOCUMENT_FILE) in {os.path.basename(path)}"); continue
        pf = os.path.join(base, fn)
        if not os.path.exists(pf): fails.append(f"{name}: referenced file missing {fn} (from {os.path.basename(path)})"); continue
        PE = parse(pf); pp = [strs(v) for k, v in PE.items() if v.startswith("PRODUCT(")]
        if not any(p[:1] == [name] and (p + ["", "", ""])[2] == desc for p in pp): fails.append(f"{name}: file PRODUCT name / description differ")
        TREE.append((depth + 1, name, os.path.relpath(pf, AD), count[name]))
        if any(v.startswith("NEXT_ASSEMBLY_USAGE_OCCURRENCE") for v in PE.values()):
            files[name] = fn; walk(pf, depth + 1, mult * count[name])          # subassembly
        else:
            inst[name] = inst.get(name, 0) + mult * count[name]; files[name] = fn
            if not any(v.startswith(("MANIFOLD_SOLID_BREP", "BREP_WITH_VOIDS")) for v in PE.values()): fails.append(f"{name}: part file holds no solid")
walk(AF)
SUBS = set(meta.get("subassemblies", {}))
# revD (Dan 2026-11-20): one part = one solid for every made part; every bought part carries its maker's model (or is a
# standard part built from its standard's table: ISO / DIN); "bought-drawn" or maker "(TBD)" fails. Exception (handbuilt-cad
# Conventions "Off-the-shelf CAD": a labelled best-guess from the datasheet when no maker CAD exists; coordinator 2026-11-20): a
# "bought-drawn" part passes when its description carries BEST_GUESS and its source cites the maker's published page.
MADE_KINDS = ("made", "made-set"); STD = ("ISO ", "DIN "); BEST_GUESS = "BEST-GUESS FROM DATASHEET"
def best_guess_ok(c): return c["kind"] == "bought-drawn" and BEST_GUESS in (c.get("desc") or "") and bool(c.get("source")) and "(TBD)" not in c["maker"]
for pn, c in meta.get("parts", {}).items():
    pf = os.path.join(AD, "Parts", pn + ".stp")
    nsol = sum(1 for v in parse(pf).values() if v.startswith(("MANIFOLD_SOLID_BREP", "BREP_WITH_VOIDS"))) if os.path.exists(pf) else 0
    if c["kind"] in MADE_KINDS and nsol != 1: fails.append(f"{pn}: made part file holds {nsol} solids (one part = one solid)")
    if c["kind"].startswith("bought") and not best_guess_ok(c):
        if c["kind"] == "bought-drawn" or "(TBD)" in c["maker"] or not (c.get("source") or c["maker"].startswith(STD)):
            fails.append(f"{pn}: bought part without its maker's model (kind {c['kind']}, maker {c['maker']}, source {c.get('source') or '-'})")
for spn in SUBS:
    if spn not in files: fails.append(f"{spn}: subassembly is not its own referenced file")
bom = {r["part_number"]: r for r in csv.DictReader(open(os.path.join(OUT, f"BOM-{meta['rev']}-{VAR}.csv")))}
for pn, r in bom.items():
    if inst.get(pn, 0) != int(r["qty"]): fails.append(f"{pn}: BOM qty {r['qty']} vs assembly instances {inst.get(pn, 0)}")
    if not r["description"] or not r["name"]: fails.append(f"{pn}: BOM row lacks name / description")
for pn in inst:
    if pn not in bom: fails.append(f"{pn}: in the assembly, not in the BOM")
res = dict(assembly=os.path.relpath(AF, OUT), components=sum(inst.values()), part_numbers=len(inst), external_files=sum(1 for v in files.values() if v),
           subassemblies=sorted(n for n in files if n in SUBS), tree=TREE, fails=fails)
json.dump(res, open(os.path.join(OUT, "bomcheck.json"), "w"), indent=1)
print(json.dumps({k: v for k, v in res.items() if k not in ("fails", "tree")}), "fails:", len(fails))
for d, n, f, c in TREE: print("  " * d + f"{n} x{c}  ({f})")
for f in fails: print("FAIL", f)
sys.exit(1 if fails else 0)
