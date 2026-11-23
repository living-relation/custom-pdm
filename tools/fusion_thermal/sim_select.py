"""Preselect study faces / bodies by body name in the active Fusion Simulation model, then open a setup command.

Runs INSIDE Fusion (Fusion MCP script tool): exec(open(this file).read(), ns); ns["pick"](...)
The adsk.sim API (preview) returns no Simulations product in Fusion 2706.1.17 (Simulations.get -> None), so the loads are
made with the normal Thermal Loads dialog: this preselects the exact faces / bodies on the simulation working model and
opens the dialog; only the load type and value are typed in the dialog.
"""
import adsk.core
import adsk.fusion


def _wm():
    app = adsk.core.Application.get()
    return adsk.fusion.WorkingModel.cast(app.activeDocument.products.itemByProductType("WorkingModelProductType"))


def _all():
    """{body name: body} for root bodies and every occurrence's bodies (as proxies in the assembly context)."""
    root = _wm().rootComponent
    out = {b.name: b for b in root.bRepBodies}
    for occ in root.allOccurrences:
        for b in occ.bRepBodies:
            out[b.name] = b
    return out


def bodies(prefix=""):
    return [b for n, b in _all().items() if n.startswith(prefix)]


def pick(faces=(), whole=(), command="SimThermalLoadsCmd"):
    """faces: [(body name, 'top' | 'bottom')] -> the face with the highest / lowest centroid z;
    whole: [body name prefix] -> whole bodies. Then runs `command` (None: only select)."""
    app = adsk.core.Application.get()
    ui = app.userInterface
    sel = ui.activeSelections
    sel.clear()
    n = 0
    allb = _all()
    for name, side in faces:
        b = allb[name]
        f = (max if side == "top" else min)(b.faces, key=lambda x: x.centroid.z)
        sel.add(f)
        n += 1
    for pre in whole:
        for nm, b in allb.items():
            if nm.startswith(pre):
                sel.add(b)
                n += 1
    if command:
        ui.commandDefinitions.itemById(command).execute()
    return n
