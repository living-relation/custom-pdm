"""Fusion side of the v2c release (Dan 2026-11-16: one Fusion design per part, inserted into the assembly as external (linked)
components; every component carries its part number + description). Dan 2026-11-20: ONE source of truth: one parts folder
("Parts"), one heat-sink subassembly design (in Parts), one top assembly design; a new release updates them as new VERSIONS of
the same designs (no per-rev folders, copies or rev letters in names) and every reference points at the newest version.
Fasteners (Dan 2026-11-20): screws / set screws that SR Fasteners offers are NOT part designs: they are placed with Dan's SR
Fasteners code (SRFastener/fastener_place.place_stack) inside the subassembly / top assembly as local bodies, on hole edges
found in code from the build's screw list (meta.json "screws": head-seat point + axis) and the set-screw placements. STEP PNs
ISO4762-* -> SR "SSH-M", ISO7380-* -> "SBH-M", McMaster 92015A106 / 92015A107 (DIN 916 cup) -> "SSC-M" (ISO 4029 cup).
Fasteners SR lacks (DIN976-M6x19 threaded rod, standoffs, inserts) stay linked part designs.
Run INSIDE Fusion (Fusion MCP execute_python, or as a Fusion script); no other agent may drive Fusion at the same time.
Each step is resumable and kept short (MCP calls time out at about 80 s):
    REL = r"<staged release>"; exec(open(r"<this file>").read()); st = load()
    sync_parts(st)          # repeat until 0 left: upload new PNs, push a changed STEP as a new version, check each
    set_props(st)           # repeat until 0 left: PN + description on every part design
    build_subassembly(st)   # repeat until 0 left: heat-sink subassembly design (linked sink, gap pads, fans, tie mounts)
    sr_place(st, sub=True)  # repeat until 0 left: SR fan screws, tie-mount screws, set-screw studs in the subassembly
    build_assembly(st)      # repeat until 0 left: top assembly = subassembly + every other linked part
    sr_place(st, sub=False) # repeat until 0 left: every other SR screw in the top assembly
    check_refs(st); compare_tree(st)   # [] = newest versions only; Fusion tree == STEP tree (SR local bodies allowed)
Reads REL: Parts/<PN>.stp, BOM-v2c-F1.csv, check/meta.json (placements 4x4 row-major mm; subassemblies; screws),
check/part_geom.json, check/bomcheck.json (STEP tree), REVLOG.md."""
import adsk.core, adsk.fusion, os, sys, json, csv, time, re
REL = globals().get("REL") or r"C:\Users\danie\.personal OneDrive\OneDrive\Desktop\models\custom-pdm-enclosure"   # the staged release folder
VAR = "F1"; PROJECT = "custom-pdm"; FOLDER = "enclosure-v2c"; PARTS = "Parts"; ASM = f"custom-pdm-enclosure-v2c-{VAR}"
SR_HOME = r"C:\projects\active\sr-fastener"
SR_STEP = re.compile(r"^(ISO4762-|ISO7380-|92015A)")            # STEP PNs that SR Fasteners bodies stand for in Fusion
SET_SCREWS = {"92015A106": ("M3", 10.0), "92015A107": ("M3", 12.0)}   # McMaster DIN 916 cup point -> SR SSC-M (ISO 4029)
SR_FAM = {"4762": "SSH-M", "7380": "SBH-M"}
SR_FIN = {"SSH-M": "ZN", "SBH-M": "SS", "SSC-M": "SS"}            # BOM materials: ISO 4762 steel zinc, 7380 A2, set screws 18-8
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
def step_key(pn):
    """STEP PN -> the SR key the Fusion body carries (None if not an SR fastener)"""
    m = re.match(r"^ISO(4762|7380)-(M[\d.]+)x([\d.]+)$", pn)
    if m: return f"SR:{SR_FAM[m.group(1)]}:{m.group(2)}x{float(m.group(3)):g}"
    if pn in SET_SCREWS: return f"SR:SSC-M:{SET_SCREWS[pn][0]}x{SET_SCREWS[pn][1]:g}"
    return None
def load():
    proj = next(p for p in app.data.dataProjects if p.name == PROJECT)
    MIG = globals().get("MIGRATE", False)                            # one-time rename of the revC copies: coordinator only
    top = _folder(proj.rootFolder, FOLDER); parts = _folder(top, PARTS, old=("parts-revC",) if MIG else ())
    for old in ((f"{ASM}-revC",) if MIG else ()):
        df = _find(top, old)
        if df and not _find(top, ASM): df.name = ASM
    meta = json.load(open(os.path.join(REL, "check", "meta.json")))
    bom = {r["part_number"]: r for r in csv.DictReader(open(os.path.join(REL, f"BOM-v2c-{VAR}.csv"), encoding="utf-8"))}
    gp = os.path.join(REL, "check", "part_geom.json")
    geom = json.load(open(gp)) if os.path.exists(gp) else {}
    rl = os.path.join(REL, "REVLOG.md")
    rows = [l.split("|")[1].strip() for l in open(rl, encoding="utf-8").read().splitlines() if re.match(r"^\| *[A-Z]{1,2}(\.\d+)? *\|", l)] if os.path.exists(rl) else []
    rev = rows[-1] if rows else "?"
    subs = set(meta["subassemblies"]) | {f"CPDM-ENC-100-{VAR}"}
    ext = [pn for pn in bom if not SR_STEP.match(pn) and pn not in subs]   # part designs in Parts (SR screws are bodies, not designs)
    return dict(proj=proj, top=top, parts=parts, meta=meta, bom=bom, ext=ext, geom=geom, rev=rev, log=[])
def _open(df):
    doc = next((d for d in app.documents if d.dataFile and d.dataFile.id == df.id), None)
    return (doc, False) if doc else (app.documents.open(df, False), True)
def _des(doc): return adsk.fusion.Design.cast(doc.products.itemByProductType("DesignProductType"))
def design_geom(doc):
    """bodies / bbox (mm) / volume (mm3) of an open Fusion design, over every component"""
    des = _des(doc)
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
    des = _des(doc); rc = des.rootComponent
    if des.designType == adsk.fusion.DesignTypes.ParametricDesignType: des.designType = adsk.fusion.DesignTypes.DirectDesignType
    for i in range(rc.occurrences.count - 1, -1, -1): rc.occurrences.item(i).deleteMe()
    for i in range(rc.bRepBodies.count - 1, -1, -1): rc.bRepBodies.item(i).deleteMe()
    im = app.importManager; im.importToTarget(im.createSTEPImportOptions(step), rc)
def sync_parts(st, budget_s=25.0, timeout_s=600):
    """every part-design PN: missing -> upload; present but not matching its STEP -> same design, new version; then the check
    passes. st['synced'] holds the checked PNs (persist it between calls with the caller's json file)."""
    st.setdefault("synced", {}); t0 = time.time()
    for pn in st["ext"]:
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
    return len(st["ext"]) - len(st["synced"])
def _desc(st, pn):
    r = st["bom"][pn]
    return f"{r['name']} | {r['description']} | material: {r['material']} | maker: {r['maker']}"[:1000]
def set_props(st, budget_s=25.0):
    """PN + description on the root component of every part design (saves a version only when they change)"""
    st.setdefault("props", {}); t0 = time.time()
    for pn in st["ext"]:
        if pn in st["props"] or time.time() - t0 > budget_s: continue
        doc, opened = _open(_find(st["parts"], pn))
        rc = _des(doc).rootComponent
        if rc.partNumber != pn or rc.description != _desc(st, pn):
            rc.partNumber = pn; rc.description = _desc(st, pn); doc.save("part number + description")
        st["props"][pn] = True
        if opened: doc.close(False)
    return len(st["ext"]) - len(st["props"])
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
    rc = _des(doc).rootComponent
    rc.partNumber = pn; rc.description = desc
    return doc, rc
def _linked(rc): return sum(1 for i in range(rc.occurrences.count) if rc.occurrences.item(i).isReferencedComponent)
def _places(st, items):
    """linked-part placements [(pn, m)]; screws and set-screw studs are SR bodies (sr_place), not linked parts"""
    return [(st["meta"]["placements"][nm]["pn"], m) for nm in items if not nm.startswith(("screws_", "standoff-studs-"))
            for m in st["meta"]["placements"][nm]["m"]]
def _fill(st, rc, places, budget_s, skip=0):
    """insert the placements [(pn, m)] in order, resuming at the linked-occurrence count (minus `skip` leading ones)"""
    t0 = time.time(); n = _linked(rc) - skip
    while n < len(places) and time.time() - t0 < budget_s:
        pn, m = places[n]; rc.occurrences.addByInsert(_find(st["parts"], pn), _mx(m), True); n += 1
    return len(places) - n
def _sub(st):
    (spn, sa), = st["meta"]["subassemblies"].items(); return spn, sa
def build_subassembly(st, clear=False, budget_s=30.0):
    spn, sa = _sub(st)
    doc, rc = _design(st, spn, spn, f"{sa['name']} | {sa['desc']}", folder=st["parts"])
    if clear:
        for i in range(rc.occurrences.count - 1, -1, -1): rc.occurrences.item(i).deleteMe()
    left = _fill(st, rc, _places(st, sa["items"]), budget_s)
    if not left: doc.save(f"release {st['rev']}: {_linked(rc)} linked parts")
    return left
def build_assembly(st, clear=False, budget_s=30.0):
    spn, sa = _sub(st)
    doc, rc = _design(st, ASM, f"CPDM-ENC-100-{VAR}", f"custom-pdm enclosure v2c {VAR} top assembly (heat-sink subassembly {spn} + linked parts + SR Fasteners screws)")
    if clear:
        for i in range(rc.occurrences.count - 1, -1, -1): rc.occurrences.item(i).deleteMe()
    if _linked(rc) == 0:
        rc.occurrences.addByInsert(_find(st["parts"], spn), adsk.core.Matrix3D.create(), True)   # the heat-sink subassembly, world frame
    places = _places(st, [nm for nm in st["meta"]["placements"] if nm not in sa["items"]])
    left = _fill(st, rc, places, budget_s, skip=1)
    if not left:
        for i in range(doc.documentReferences.count):
            r = doc.documentReferences.item(i)
            if r.isOutOfDate: r.getLatestVersion()
        doc.save(f"release {st['rev']}: heat-sink subassembly + {len(places)} linked parts")
    return left
# ---------------- SR Fasteners ----------------
def _sr():
    if SR_HOME not in sys.path: sys.path.insert(0, SR_HOME)
    from SRFastener import fastener_place as fp, fastener_core as fc
    return fp, fc, fc.load_catalog()
def sr_jobs(st, sub):
    """[(key, family, size, L, at_mm, axis, off_mm)]: sub=True -> fan + tie screws and the set-screw studs (heat-sink
    subassembly), sub=False -> every other screw (top assembly). Set screws: SR origin = top face, so off = top above the boss face."""
    m = st["meta"]; jobs = []
    for i, s in enumerate(m["screws"]):
        if (s.get("grp") in ("fan", "tie")) != sub: continue
        jobs.append((f"screw{i}", SR_FAM[s.get("fam", "4762")], s["size"], float(s["L"]), s["at"], s["axis"], 0.0))
    if sub:
        for nm, pl in m["placements"].items():
            if not nm.startswith("standoff-studs-"): continue
            size, L = SET_SCREWS[pl["pn"]]; zmin = st["geom"][pl["pn"]]["bbox"][2]
            for j, mm in enumerate(pl["m"]):
                top = mm[11] + zmin + L                                      # set-screw top face (world z, mm)
                jobs.append((f"{nm}#{j}", "SSC-M", size, L, [mm[3], mm[7], m["Z_BOT"]], [0.0, 0.0, 1.0], round(top - m["Z_BOT"], 4)))
    return jobs
def _hole_edge(des, at_mm, axis, d_mm, tol_cm=0.01):
    """the circular hole edge centred on the head-seat point, normal along the screw axis, radius 0.4..0.85 d (the bolt hole,
    not a counterbore wall); smallest |r - 0.55 d| wins. Bodies of SR components are skipped."""
    P = adsk.core.Point3D.create(*[v / 10.0 for v in at_mm]); A = adsk.core.Vector3D.create(*axis); A.normalize()
    best = None
    for occ in des.rootComponent.allOccurrences:
        if occ.component.attributes.itemByName("srfastener", "part_number"): continue
        for b in occ.bRepBodies:
            bb = b.boundingBox
            if not (bb.minPoint.x - 0.05 <= P.x <= bb.maxPoint.x + 0.05 and bb.minPoint.y - 0.05 <= P.y <= bb.maxPoint.y + 0.05
                    and bb.minPoint.z - 0.05 <= P.z <= bb.maxPoint.z + 0.05): continue
            for e in b.edges:
                c = adsk.core.Circle3D.cast(e.geometry) or adsk.core.Arc3D.cast(e.geometry)
                if c is None or c.center.distanceTo(P) > tol_cm: continue
                if abs(c.normal.dotProduct(A)) < 0.999: continue
                r = c.radius * 10.0
                if not 0.4 * d_mm <= r <= 0.85 * d_mm: continue
                sc = abs(r - 0.55 * d_mm)
                if best is None or sc < best[0]: best = (sc, e, occ.fullPathName, round(r, 3))
    return best
def sr_place(st, sub, budget_s=40.0):
    """place the SR Fasteners screws of the subassembly (sub=True) or the top assembly on hole edges found in code; resumable
    (done keys kept as an attribute on the root component). Returns the number left; problems go to st['sr_log']."""
    fp, fc, cat = _sr()
    spn, sa = _sub(st)
    df = _find(st["parts"], spn) if sub else _find(st["top"], ASM)
    doc, _ = _open(df); doc.activate(); des = _des(doc); des.activateRootComponent(); rc = des.rootComponent
    a = rc.attributes.itemByName("cadfetch", "sr_done"); done = json.loads(a.value) if a else []
    jobs = sr_jobs(st, sub); t0 = time.time(); log = st.setdefault("sr_log", [])
    for key, code, size, L, at, ax, off in jobs:
        if key in done or time.time() - t0 > budget_s: continue
        d = float(size[1:]); hit = _hole_edge(des, at, ax, d)
        if hit is None: log.append(f"{key} {code} {size}x{L:g}: no hole edge at {at}"); done.append(key); continue
        _, edge, owner, r = hit
        A = adsk.core.Vector3D.create(*ax)
        hole = fp.read_hole(edge)
        if hole.into.dotProduct(A) > 0: hole = fp.read_hole(edge, flip=True)   # 'into' must point away from the head
        fam = fc.family(cat, code); row = fc.size_row(fam, size)
        fin = SR_FIN[code] if SR_FIN[code] in fc.finishes_for(cat, fam, row) else fc.finishes_for(cat, fam, row)[0]
        it = fc.item(cat, code, size, fin, L); notes = []
        occ = fp._place_one(app, des, cat, it, hole, off / 10.0, True, notes)
        o = occ.transform2.translation; want = [at[i] / 10.0 + ax[i] * off / 10.0 for i in range(3)]
        err = max(abs(o.x - want[0]), abs(o.y - want[1]), abs(o.z - want[2])) * 10.0
        z = occ.transform2.getAsCoordinateSystem()[3]
        if err > 0.02 or z.dotProduct(A) < 0.999: log.append(f"{key}: placed {err:.3f} mm off / axis {z.dotProduct(A):.4f} ({owner} r{r})")
        if notes: log.append(f"{key}: {notes}")
        done.append(key)
    rc.attributes.add("cadfetch", "sr_done", json.dumps(done))
    left = len([j for j in jobs if j[0] not in done])
    if not left: doc.save(f"release {st['rev']}: SR Fasteners screws ({len(jobs)}) on hole edges from meta.json")
    return left
# ---------------- checks ----------------
def _sr_key(comp):
    g = lambda k: (comp.attributes.itemByName("srfastener", k).value if comp.attributes.itemByName("srfastener", k) else None)
    if g("family") is None: return None
    return f"SR:{g('family')}:{g('size')}x{float(g('length')):g}"
def compare_tree(st):
    """Fusion tree vs STEP tree (bomcheck.json 'tree': depth, PN, file, count; SR-standing STEP PNs mapped to their SR key).
    Fails on a PN / count / depth difference, a local (non-linked) component that is not an SR Fasteners body, or a linked part
    design whose body count differs from its STEP (a merged / fused design)."""
    tree = json.load(open(os.path.join(REL, "check", "bomcheck.json")))["tree"]
    want = {}
    for d, n, f, c in tree:
        k = (d, step_key(n) or n); want[k] = want.get(k, 0) + c
    got = {}; probs = []
    def walk(occs, d):
        for i in range(occs.count):
            o = occs.item(i); srk = _sr_key(o.component); pn = srk or o.component.partNumber or o.component.name
            got[(d, pn)] = got.get((d, pn), 0) + 1
            if srk:
                if o.component.bRepBodies.count != 1: probs.append(f"{pn}: SR component with {o.component.bRepBodies.count} bodies")
                continue
            if not o.isReferencedComponent: probs.append(f"{pn}: local component (not a linked design, not SR Fasteners)"); continue
            if o.component.occurrences.count: walk(o.component.occurrences, d + 1)
            elif pn in st["geom"] and o.component.bRepBodies.count != st["geom"][pn]["solids"]:
                probs.append(f"{pn}: {o.component.bRepBodies.count} bodies vs STEP {st['geom'][pn]['solids']}")
    df = _find(st["top"], ASM)
    if df is None: return [f"{ASM}: design missing"]
    doc, opened = _open(df)
    walk(_des(doc).rootComponent.occurrences, 1)
    if opened: doc.close(False)
    for k in sorted(set(want) | set(got), key=str):
        if want.get(k, 0) != got.get(k, 0): probs.append(f"depth {k[0]} {k[1]}: STEP x{want.get(k, 0)} vs Fusion x{got.get(k, 0)}")
    st["tree_counts"] = dict(step=sum(want.values()), fusion=sum(got.values()))
    return probs
def check_refs(st):
    """[] when the top assembly and the subassembly reference only the NEWEST version of designs in the parts folder (or the
    subassembly design); else the problems. The build check for Dan's one-source-of-truth rule (2026-11-20)."""
    probs = []; ok_ids = {st["parts"].dataFiles.item(i).id for i in range(st["parts"].dataFiles.count)}
    spn, _ = _sub(st); sub = _find(st["parts"], spn)
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
def tree_lines(st):
    """the top assembly's browser tree as text lines (for the review PNG): depth, name, linked / SR / local"""
    out = []
    def walk(occs, d):
        for i in range(occs.count):
            o = occs.item(i); srk = _sr_key(o.component)
            kind = "SR body" if srk else ("linked" if o.isReferencedComponent else "LOCAL")
            out.append(f"{'    ' * d}{o.name}   [{kind}]  PN {o.component.partNumber}")
            if o.isReferencedComponent and o.component.occurrences.count: walk(o.component.occurrences, d + 1)
    df = _find(st["top"], ASM); doc, opened = _open(df)
    walk(_des(doc).rootComponent.occurrences, 0)
    if opened: doc.close(False)
    return out
