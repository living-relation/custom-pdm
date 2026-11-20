"""BOM / part-file check of the v2c assembly (Dan 2026-11-16: every part is its own file, inserted into the assembly, with its part
number and description). Usage: $CAD_PY bomcheck_v2c.py F1 [RUN_DIR]. Reads <run>/<VAR>/xref/<assembly>.step (STEP assembly with
external references) and BOM-v2c-<VAR>.csv. FAILS (exit 1) if any component of the assembly
  - is not an external reference to a part file that exists (parts/<PN>.stp),
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
E = parse(AF)
typ = {k: v.split("(", 1)[0].strip() for k, v in E.items()}
prod = {k: strs(v) for k, v in E.items() if typ[k] == "PRODUCT"}
pdf = {k: refs(v)[-1] for k, v in E.items() if typ[k] == "PRODUCT_DEFINITION_FORMATION"}
pd = {k: refs(v)[0] for k, v in E.items() if typ[k] == "PRODUCT_DEFINITION"}
def pd_product(k): return prod[pdf[pd[k]]]
nauo = [refs(v) for k, v in E.items() if typ[k] == "NEXT_ASSEMBLY_USAGE_OCCURRENCE"]
dfiles = {os.path.splitext(os.path.basename(strs(v)[0]))[0]: strs(v)[0] for k, v in E.items() if typ[k] == "DOCUMENT_FILE"}
docfile = {}   # PD that carries an APPLIED_DOCUMENT_REFERENCE -> the DOCUMENT_FILE named after its product (OCC names it <name>.stp)
for k, v in E.items():
    if typ[k] == "APPLIED_DOCUMENT_REFERENCE":
        for tg in refs(v)[1:]:
            if tg in pd: docfile[tg] = dfiles.get(pd_product(tg)[0])
fails = []; inst = {}; files = {}
for (parent, child) in [(r[0], r[1]) for r in nauo]:
    name, _, desc = (pd_product(child) + ["", "", ""])[:3]
    inst[name] = inst.get(name, 0) + 1
    if name in files: continue
    fn = docfile.get(child)
    files[name] = fn
    if not name: fails.append(f"component #{child}: no part number")
    if not desc: fails.append(f"{name}: no description")
    if not fn: fails.append(f"{name}: not an external reference (no DOCUMENT_FILE)"); continue
    pf = os.path.join(AD, fn)
    if not os.path.exists(pf): fails.append(f"{name}: part file missing {fn}"); continue
    PE = parse(pf); pp = [strs(v) for k, v in PE.items() if v.startswith("PRODUCT(")]
    if not any(p[:1] == [name] and (p + ["", "", ""])[2] == desc for p in pp): fails.append(f"{name}: part file PRODUCT name / description differ")
    if not any(v.startswith(("MANIFOLD_SOLID_BREP", "BREP_WITH_VOIDS")) for v in PE.values()): fails.append(f"{name}: part file holds no solid")
bom = {r["part_number"]: r for r in csv.DictReader(open(os.path.join(OUT, f"BOM-{meta['rev']}-{VAR}.csv")))}
for pn, r in bom.items():
    if inst.get(pn, 0) != int(r["qty"]): fails.append(f"{pn}: BOM qty {r['qty']} vs assembly instances {inst.get(pn, 0)}")
    if not r["description"] or not r["name"]: fails.append(f"{pn}: BOM row lacks name / description")
for pn in inst:
    if pn not in bom: fails.append(f"{pn}: in the assembly, not in the BOM")
res = dict(assembly=os.path.relpath(AF, OUT), components=sum(inst.values()), part_numbers=len(inst), external_files=sum(1 for v in files.values() if v), fails=fails)
json.dump(res, open(os.path.join(OUT, "bomcheck.json"), "w"), indent=1)
print(json.dumps({k: v for k, v in res.items() if k != "fails"}), "fails:", len(fails))
for f in fails: print("FAIL", f)
sys.exit(1 if fails else 0)
