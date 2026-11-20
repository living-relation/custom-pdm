"""Fusion side of the v2c release (Dan 2026-11-16: one Fusion design per part, inserted into the assembly as external (linked)
components; every component carries its part number + description). Dan 2026-11-20: ONE source of truth: one parts folder, one
heat-sink subassembly design, one top assembly design; a new release updates them as new VERSIONS of the same designs (no per-rev
folders or copies) and every reference points at the newest version.
Run INSIDE Fusion (Fusion MCP execute_python, or as a Fusion script) while holding the Fusion lock (projects-AGENTS.md section 5).
Each step is resumable and kept short (MCP calls time out at about 80 s):
    exec(open(r"<this file>").read()); st = load()
    sync_parts(st)          # repeat until it returns 0 left: upload new PNs, push a changed STEP as a new version, check each
    set_props(st)           # repeat until 0 left: PN + description on every part design
    build_subassembly(st)   # heat-sink subassembly design (sink, gap pads, fans, fan screws, tie anchors)
    build_assembly(st)      # repeat until done: top assembly = subassembly + every other placement, all linked
    check_refs(st)          # [] = every reference is the newest version of a design in the parts folder
Reads REL: parts/<PN>.stp, BOM-v2c-F1.csv, check/meta.json (placements 4x4 row-major mm; subassemblies), check/part_geom.json."""
import adsk.core, adsk.fusion, os, json, csv, time
REL = globals().get("REL") or r"C:\Users\danie\.personal OneDrive\OneDrive\Desktop\models\custom-pdm-enclosure"   # the current release folder
VAR = "F1"; PROJECT = "custom-pdm"; FOLDER = "enclosure-v2c"; PARTS = "Parts"; ASM = f"custom-pdm-enclosure-v2c-{VAR}"
app = adsk.core.Application.get()
def _folder(parent, name, old=()):
    f = parent.dataFolders.itemByName(name)
    for o in old:                                                    # one-time migration: per-rev folder -> the one folder
        if f is None and parent.dataFolders.itemByName(o): f = parent.dataFolders.itemByName(o); f.name = name
    return f if f else parent.dataFolders.add(name)
def _find(folder, stem):
    for i in range(folder.dataFiles.count):
        df = folder.dataFiles.item(i)
        if df.name == stem: return df
    return None
def load():
    proj = next(p for p in app.data.dataProjects if p.name == PROJECT)
    MIG = globals().get("MIGRATE", False)                            # one-time rename of the revC copies: only after Dan's yes (a5)
    top = _folder(proj.rootFolder, FOLDER); parts = _folder(top, PARTS, old=("parts-revC",) if MIG else ())
    for old in ((f"{ASM}-revC",) if MIG else ()):                    # migration: the revC assembly copy becomes THE assembly
        df = _find(top, old)
        if df and not _find(top, ASM): df.name = ASM
    meta = json.load(open(os.path.join(REL, "check", "meta.json")))
    bom = {r["part_number"]: r for r in csv.DictReader(open(os.path.join(REL, f"BOM-v2c-{VAR}.csv"), encoding="utf-8"))}
    gp = os.path.join(REL, "check", "part_geom.json")
    geom = json.load(open(gp)) if os.path.exists(gp) else {}
    rev = open(os.path.join(REL, "REVLOG.md"), encoding="utf-8").read().strip().splitlines()[-3].split("|")[1].strip() if os.path.exists(os.path.join(REL, "REVLOG.md")) else "?"
    return dict(proj=proj, top=top, parts=parts, meta=meta, bom=bom, geom=geom, rev=rev, log=[])
def _open(df):
    doc = next((d for d in app.documents if d.dataFile and d.dataFile.id == df.id), None)
    return (doc, False) if doc else (app.documents.open(df, False), True)
def design_geom(doc):
    """bodies / bbox (mm) / volume (mm3) of an open Fusion design, over every component"""
    des = adsk.fusion.Design.cast(doc.products.itemByProductType("DesignProductType"))
    bodies = [b for c in des.allComponents for b in c.bRepBodies]
    bb = des.rootComponent.boundingBox
    return dict(solids=len(bodies), volume=round(sum(b.volume for b in bodies) * 1000, 3),
                bbox=[round(v * 10, 3) for v in (bb.minPoint.x, bb.minPoint.y, bb.minPoint.z, bb.maxPoint.x, bb.maxPoint.y, bb.maxPoint.z)])
def geom_problems(want, got, tol_mm=1.0, tol_vol=0.002):
    """[] when the design matches its STEP fingerprint. Body count and volume are exact tests; Fusion's boundingBox is not tight on
    spline / thread faces (TE nut 2411-001-2405: +0.45 mm), so the box gets 1 mm"""
    p = []
    if want["solids"] != got["solids"]: p.append(f"bodies {got['solids']} != STEP solids {want['solids']}")
    if max(abs(a - b) for a, b in zip(want["bbox"], got["bbox"])) > tol_mm: p.append(f"bbox {got['bbox']} != STEP {want['bbox']}")
    if abs(got["volume"] - want["volume"]) > tol_vol * max(want["volume"], 1.0): p.append(f"volume {got['volume']} != STEP {want['volume']}")
    return p
def _replace_geometry(doc, step):
    """new VERSION of the same design: remove its bodies / occurrences, import the STEP into its root component, save"""
    des = adsk.fusion.Design.cast(doc.products.itemByProductType("DesignProductType")); rc = des.rootComponent
    if des.designType == adsk.fusion.DesignTypes.ParametricDesignType: des.designType = adsk.fusion.DesignTypes.DirectDesignType
    for i in range(rc.occurrences.count - 1, -1, -1): rc.occurrences.item(i).deleteMe()
    for i in range(rc.bRepBodies.count - 1, -1, -1): rc.bRepBodies.item(i).deleteMe()
    im = app.importManager; im.importToTarget(im.createSTEPImportOptions(step), rc)
def sync_parts(st, budget_s=25.0, timeout_s=600):
    """every BOM PN: missing -> upload; present but not matching its STEP -> same design, new version; then the check passes.
    st['synced'] holds the checked PNs (persist it between calls with the caller's json file)."""
    st.setdefault("synced", {}); t0 = time.time()
    for pn in st["bom"]:
        if pn in st["synced"] or time.time() - t0 > budget_s: continue
        step = os.path.join(REL, "Parts", pn + ".stp"); df = _find(st["parts"], pn)
        if df is None:
            fut = st["parts"].uploadFile(step); t1 = time.time()
            while fut.uploadState == adsk.core.UploadStates.UploadProcessing and time.time() - t1 < timeout_s:
                adsk.doEvents(); time.sleep(0.5)
            st["synced"][pn] = "uploaded" if fut.uploadState == adsk.core.UploadStates.UploadFinished else f"upload state {fut.uploadState}"
            continue
        doc, opened = _open(df)
        bad = geom_problems(st["geom"][pn], design_geom(doc)) if pn in st["geom"] else ["no STEP fingerprint"]
        if bad and pn in st["geom"]:
            _replace_geometry(doc, step); doc.save(f"release {st['rev']}: geometry from Parts/{pn}.stp")
            bad2 = geom_problems(st["geom"][pn], design_geom(doc))
            st["synced"][pn] = "new version" if not bad2 else f"MISMATCH after update: {bad2}"
        else:
            st["synced"][pn] = "ok" if not bad else f"MISMATCH: {bad}"
        if opened: doc.close(False)
    return len(st["bom"]) - len(st["synced"])
def _desc(st, pn):
    r = st["bom"][pn]
    return f"{r['name']} | {r['description']} | material: {r['material']} | maker: {r['maker']}"[:1000]
def set_props(st, budget_s=25.0):
    """PN + description on the root component of every part design (saves a version only when they change)"""
    st.setdefault("props", {}); t0 = time.time()
    for pn in st["bom"]:
        if pn in st["props"] or time.time() - t0 > budget_s: continue
        doc, opened = _open(_find(st["parts"], pn))
        rc = adsk.fusion.Design.cast(doc.products.itemByProductType("DesignProductType")).rootComponent
        if rc.partNumber != pn or rc.description != _desc(st, pn):
            rc.partNumber = pn; rc.description = _desc(st, pn); doc.save("part number + description")
        st["props"][pn] = True
        if opened: doc.close(False)
    return len(st["bom"]) - len(st["props"])
def _mx(m):
    """meta.json 4x4 row-major (mm, rotation rounded to 9 digits) -> Fusion Matrix3D (cm). The rotation is re-orthonormalised:
    Fusion rejects the rounded one ("invalid argument transform")."""
    import math
    x = [m[0], m[4], m[8]]; y = [m[1], m[5], m[9]]
    nx = math.sqrt(sum(v * v for v in x)); x = [v / nx for v in x]
    d = sum(a * b for a, b in zip(x, y)); y = [b - d * a for a, b in zip(x, y)]
    ny = math.sqrt(sum(v * v for v in y)); y = [v / ny for v in y]
    z = [x[1] * y[2] - x[2] * y[1], x[2] * y[0] - x[0] * y[2], x[0] * y[1] - x[1] * y[0]]
    mx = adsk.core.Matrix3D.create()
    mx.setWithArray([x[0], y[0], z[0], m[3] / 10.0, x[1], y[1], z[1], m[7] / 10.0, x[2], y[2], z[2], m[11] / 10.0, 0, 0, 0, 1])
    return mx
def _design(st, name, pn, desc, folder=None):
    """open THE design of that name in its folder (top folder, or Parts for a subassembly; create it once), root PN / description set"""
    folder = folder or st["top"]; df = _find(folder, name)
    if df: doc, _ = _open(df)
    else:
        doc = app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
        adsk.fusion.Design.cast(app.activeProduct).designType = adsk.fusion.DesignTypes.ParametricDesignType
        doc.saveAs(name, folder, "created", "")
    doc.activate()
    rc = adsk.fusion.Design.cast(doc.products.itemByProductType("DesignProductType")).rootComponent
    rc.partNumber = pn; rc.description = desc
    return doc, rc
def _fill(st, rc, places, budget_s):
    """insert the placements [(pn, m)] in order, resuming at rc.occurrences.count (a full rebuild clears first)"""
    t0 = time.time(); n = rc.occurrences.count
    while n < len(places) and time.time() - t0 < budget_s:
        pn, m = places[n]; rc.occurrences.addByInsert(_find(st["parts"], pn), _mx(m), True); n += 1
    return len(places) - n
def _places(st, items):
    return [(st["meta"]["placements"][nm]["pn"], m) for nm in items for m in st["meta"]["placements"][nm]["m"]]
def build_subassembly(st, clear=False, budget_s=30.0):
    (spn, sa), = st["meta"]["subassemblies"].items()
    doc, rc = _design(st, spn, spn, f"{sa['name']} | {sa['desc']}", folder=st["parts"])
    if clear:
        for i in range(rc.occurrences.count - 1, -1, -1): rc.occurrences.item(i).deleteMe()
    left = _fill(st, rc, _places(st, sa["items"]), budget_s)
    if not left: doc.save(f"release {st['rev']}: {rc.occurrences.count} linked parts")
    return left
def build_assembly(st, clear=False, budget_s=30.0):
    (spn, sa), = st["meta"]["subassemblies"].items()
    doc, rc = _design(st, ASM, f"CPDM-ENC-100-{VAR}", f"custom-pdm enclosure v2c {VAR} assembly, release {st['rev']}")
    if clear:
        for i in range(rc.occurrences.count - 1, -1, -1): rc.occurrences.item(i).deleteMe()
    if rc.occurrences.count == 0:
        rc.occurrences.addByInsert(_find(st["parts"], spn), adsk.core.Matrix3D.create(), True)   # the heat-sink subassembly, world frame
    rest = [nm for nm in st["meta"]["placements"] if nm not in sa["items"]]
    t0 = time.time(); places = _places(st, rest); n = rc.occurrences.count - 1
    while n < len(places) and time.time() - t0 < budget_s:
        pn, m = places[n]; rc.occurrences.addByInsert(_find(st["parts"], pn), _mx(m), True); n += 1
    if n >= len(places):
        for i in range(doc.documentReferences.count):
            r = doc.documentReferences.item(i)
            if r.isOutOfDate: r.getLatestVersion()
        doc.save(f"release {st['rev']}: heat-sink subassembly + {len(places)} linked parts")
    return len(places) - n
SR_PREFIX = ("SSH", "SBH", "SFH", "SLH")            # SR Fastener components (Dan 2026-11-20: the one allowed local kind)
def compare_tree(st):
    """Fusion tree vs STEP tree (bomcheck.json 'tree': depth, PN, file, count). Fails on a PN / count / depth difference, a
    non-linked component that is not an SR Fastener part, or a part design whose body count differs from its STEP."""
    tree = json.load(open(os.path.join(REL, "check", "bomcheck.json")))["tree"]
    want = {}
    for d, n, f, c in tree: want[(d, n)] = want.get((d, n), 0) + c
    got = {}; probs = []
    def walk(occs, d):
        for i in range(occs.count):
            o = occs.item(i); pn = o.component.partNumber or o.component.name
            got[(d, pn)] = got.get((d, pn), 0) + 1
            if not o.isReferencedComponent and not pn.startswith(SR_PREFIX): probs.append(f"{pn}: local component (not a linked design)")
            if o.isReferencedComponent and o.component.occurrences.count: walk(o.component.occurrences, d + 1)
            elif pn in st["geom"] and o.component.bRepBodies.count != st["geom"][pn]["solids"]:
                probs.append(f"{pn}: {o.component.bRepBodies.count} bodies vs STEP {st['geom'][pn]['solids']}")
    df = _find(st["top"], ASM)
    if df is None: return [f"{ASM}: design missing"]
    doc, opened = _open(df)
    walk(adsk.fusion.Design.cast(doc.products.itemByProductType("DesignProductType")).rootComponent.occurrences, 1)
    if opened: doc.close(False)
    for k in set(want) | set(got):
        if want.get(k, 0) != got.get(k, 0) and not k[1].startswith(SR_PREFIX): probs.append(f"depth {k[0]} {k[1]}: STEP x{want.get(k, 0)} vs Fusion x{got.get(k, 0)}")
    return probs
def check_refs(st):
    """[] when the top assembly and the subassembly reference only the NEWEST version of designs in the parts folder (or the
    subassembly design); else the problems. The build check for Dan's one-source-of-truth rule (2026-11-20)."""
    probs = []; ok_ids = {st["parts"].dataFiles.item(i).id for i in range(st["parts"].dataFiles.count)}
    (spn, _), = st["meta"]["subassemblies"].items(); sub = _find(st["parts"], spn)
    if sub: ok_ids.add(sub.id)
    for name, fo in ((spn, st["parts"]), (ASM, st["top"])):
        df = _find(fo, name)
        if df is None: probs.append(f"{name}: design missing"); continue
        doc, opened = _open(df)
        for i in range(doc.documentReferences.count):
            r = doc.documentReferences.item(i)
            if r.dataFile.id not in ok_ids: probs.append(f"{name}: references {r.dataFile.name} outside {FOLDER}/{PARTS}")
            if r.isOutOfDate: probs.append(f"{name}: {r.dataFile.name} v{r.version} is not the newest (v{r.dataFile.latestVersionNumber})")
        if opened: doc.close(False)
    return probs
