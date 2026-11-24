"""Fusion helpers for the build package: fresh import of the KiCad boards, .f3z / .f3d / STEP / EAGLE exports.

Run inside Fusion (Fusion MCP "script", or Scripts and Add-Ins), under the fusion-desktop lock:
    import importlib.util as u; s = u.spec_from_file_location("ep", r"<repo>/tools/fusion_check/export_package.py")
    ep = u.module_from_spec(s); s.loader.exec_module(ep); ep.<function>(...)

Why a fresh import (docs/fusion-electronics-check.md, "Build package exports"): an Electronics design (.fprj + its
linked .fsch / .fbrd) exports as one .f3z only through File > Export of the opened design, and Fusion first saves a
new version of every design that has pending changes; opening an imported design always marks the board changed
(polygon / sync update), so exporting from the checked folder would add versions to it. The package job therefore
imports the same KiCad files into a new folder of its own and exports from that copy; the checked designs stay
untouched. The 3D PCB has no external references, so Fusion offers .f3d (not .f3z) for it.

Functions:
    folder(*names)                      -> DataFolder in hub "dgrip", project "custom-pdm" (created if missing)
    upload(names, kicad_pro)            -> starts DataFolder.uploadFile of a .kicad_pro: Fusion shows "ECAD Design
                                           Upload Options" (Sheets, Create Electronics Design): click OK
    listing(*names)                     -> prints the folder's files (name, extension, version, id)
    open_design(fprj_id)                -> opens the .fprj (schematic, board come with it); returns the documents
    run_ulp(ulp, out)                   -> runs an EAGLE ULP on the active board (Electron.run)
    export_3d(fprj_id, out_dir, base)   -> opens the 3D PCB of the design, writes <base>-3D-PCB.f3d and .step
    close_all()                         -> closes every open document WITHOUT saving
The .f3z and the EAGLE .sch / .brd come from the Export dialog (File > Export with the design / schematic / board
tab active: types "Autodesk Fusion Archive Files (*.f3z)", "EAGLE 9.X ... (*.sch / *.brd)"), clicked by hand or
with screen control; Fusion has no API for them.
"""
import os
import time

import adsk.core
import adsk.fusion

HUB, PROJECT = "dgrip", "custom-pdm"


def _app():
    return adsk.core.Application.get()


def _wait(sec):
    t = time.time()
    while time.time() - t < sec:
        adsk.doEvents()
        time.sleep(0.1)


def folder(*names):
    app = _app()
    hub = next(app.data.dataHubs.item(i) for i in range(app.data.dataHubs.count) if app.data.dataHubs.item(i).name == HUB)
    proj = next(hub.dataProjects.item(i) for i in range(hub.dataProjects.count) if hub.dataProjects.item(i).name == PROJECT)
    f = proj.rootFolder
    for n in names:
        sub = f.dataFolders.itemByName(n)
        f = sub if sub else f.dataFolders.add(n)
    return f


def upload(names, kicad_pro):
    f = folder(*names)
    fut = f.uploadFile(kicad_pro)
    print("upload started", kicad_pro, "->", "/".join(names), fut.uploadState if fut else None)
    return fut


def listing(*names):
    f = folder(*names)
    for i in range(f.dataFiles.count):
        d = f.dataFiles.item(i)
        print(d.name, d.fileExtension, "v%d" % d.versionNumber, d.id)


def open_design(fprj_id):
    app = _app()
    df = app.data.findFileById(fprj_id)
    app.documents.open(df, True)
    _wait(3)
    return [app.documents.item(i) for i in range(app.documents.count)]


def run_ulp(ulp, out):
    app = _app()
    for i in range(app.documents.count):
        d = app.documents.item(i)
        if d.objectType == "adsk::electron::BoardDocument":
            d.activate()
    return app.executeTextCommand('Electron.run "RUN \'%s\' \'%s\'"' % (ulp.replace("\\", "/"), out.replace("\\", "/")))


def export_3d(fprj_id, out_dir, base):
    app = _app()
    open_design(fprj_id)
    for i in range(app.documents.count):
        d = app.documents.item(i)
        if d.objectType == "adsk::electron::BoardDocument":
            d.activate()
    app.userInterface.commandDefinitions.itemById("Switch3dPcbDocCmd").execute()
    _wait(10)
    doc = app.activeDocument
    des = adsk.fusion.Design.cast(doc.products.itemByProductType("DesignProductType"))
    if des is None:
        raise RuntimeError("no 3D PCB document became active")
    os.makedirs(out_dir, exist_ok=True)
    em = des.exportManager
    f3d = os.path.join(out_dir, base + "-3D-PCB.f3d")
    step = os.path.join(out_dir, base + "-3D-PCB.step")
    ok1 = em.execute(em.createFusionArchiveExportOptions(f3d))
    ok2 = em.execute(em.createSTEPExportOptions(step))
    print("3D PCB", des.rootComponent.allOccurrences.count, "occurrences; f3d", ok1, os.path.getsize(f3d) if ok1 else 0,
          "step", ok2, os.path.getsize(step) if ok2 else 0)


def close_all():
    app = _app()
    while app.documents.count:
        app.documents.item(app.documents.count - 1).close(False)
