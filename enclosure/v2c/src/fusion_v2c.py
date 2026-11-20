"""Fusion side of the v2c release (Dan 2026-11-16: one Fusion design per part, inserted into the assembly as external (linked)
components; every component carries its part number + description). Run INSIDE Fusion (Fusion MCP execute_python, or as a
Fusion script) while holding the Fusion lock (projects-AGENTS.md section 5). Step by step, resumable:
    exec(open(r"<this file>").read()); st = load(); upload_parts(st); set_props(st); build_assembly(st)
Reads the release folder (REL): parts/<PN>.stp, BOM-v2c-F1.csv, check/meta.json (placements: 4x4 row-major, mm).
Fusion: project custom-pdm, folder enclosure-v2c (parts in enclosure-v2c/parts), assembly design custom-pdm-enclosure-v2c-F1."""
import adsk.core, adsk.fusion, os, json, csv, time
REL = r"C:\Users\danie\.personal OneDrive\OneDrive\Desktop\models\custom-pdm-enclosure-v2c\v2c"
VAR = "F1"; PROJECT = "custom-pdm"; FOLDER = "enclosure-v2c"; ASM = f"custom-pdm-enclosure-v2c-{VAR}"
app = adsk.core.Application.get()
def _folder(parent, name):
    f = parent.dataFolders.itemByName(name)
    return f if f else parent.dataFolders.add(name)
def load():
    proj = next(p for p in app.data.dataProjects if p.name == PROJECT)
    top = _folder(proj.rootFolder, FOLDER); parts = _folder(top, "parts")
    meta = json.load(open(os.path.join(REL, "check", "meta.json")))
    bom = {r["part_number"]: r for r in csv.DictReader(open(os.path.join(REL, f"BOM-v2c-{VAR}.csv"), encoding="utf-8"))}
    return dict(top=top, parts=parts, meta=meta, bom=bom, files={}, log=[])
def _find(folder, stem):
    for i in range(folder.dataFiles.count):
        df = folder.dataFiles.item(i)
        if df.name == stem: return df
    return None
def upload_parts(st, timeout_s=900):
    """upload every parts/<PN>.stp once (skips PNs already in the folder); waits for each translation"""
    for pn in st["bom"]:
        df = _find(st["parts"], pn)
        if df is None:
            fut = st["parts"].uploadFile(os.path.join(REL, "parts", pn + ".stp")); t0 = time.time()
            while fut.uploadState == adsk.core.UploadStates.UploadProcessing and time.time() - t0 < timeout_s:
                adsk.doEvents(); time.sleep(0.5)
            if fut.uploadState != adsk.core.UploadStates.UploadFinished:
                st["log"].append(f"{pn}: upload state {fut.uploadState}"); continue
            df = fut.dataFile
        st["files"][pn] = df
    return {k: v.name for k, v in st["files"].items()}
def set_props(st):
    """open each part design, set root component part number + description, save, close"""
    for pn, df in st["files"].items():
        r = st["bom"][pn]; desc = f"{r['name']} | {r['description']} | material: {r['material']} | maker: {r['maker']} | rev v2c"
        doc = app.documents.open(df, False)
        des = adsk.fusion.Design.cast(doc.products.itemByProductType("DesignProductType"))
        rc = des.rootComponent
        if rc.partNumber != pn or rc.description != desc:
            rc.partNumber = pn; rc.description = desc[:1000]
            doc.save("v2c: part number + description")
        doc.close(False)
    return len(st["files"])
def build_assembly(st):
    """new design, every placement inserted as a referenced (external) component, saved as ASM in the enclosure-v2c folder"""
    doc = app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
    des = adsk.fusion.Design.cast(app.activeProduct); des.designType = adsk.fusion.DesignTypes.ParametricDesignType
    root = des.rootComponent; root.partNumber = f"CPDM-ENC-100-{VAR}"; root.description = f"custom-pdm enclosure v2c {VAR} assembly"
    n = 0
    for item, pl in st["meta"]["placements"].items():
        df = st["files"][pl["pn"]]
        for m in pl["m"]:
            mm = list(m); mm[3] /= 10.0; mm[7] /= 10.0; mm[11] /= 10.0            # mm -> cm (Fusion internal units)
            mx = adsk.core.Matrix3D.create(); mx.setWithArray(mm)
            root.occurrences.addByInsert(df, mx, True); n += 1
    doc.saveAs(ASM, st["top"], "v2c F1: parts inserted as external components (one design per part)", "")
    return n
