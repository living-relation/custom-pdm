import json, os, sys, pcbnew
HW = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'hardware')
out = {}
boards = {
    'A': os.path.join(HW, 'board-a', 'DingoPDM.kicad_pcb'),
    'B': os.path.join(HW, 'board-b-max', 'dingoPDM-Max.kicad_pcb'),
    'IN': os.path.join(HW, 'input-board', 'input-board.kicad_pcb'),
}
for k, p in boards.items():
    b = pcbnew.LoadBoard(p)
    fps = list(b.GetFootprints())
    pads = [pd for f in fps for pd in f.Pads()]
    th = [pd for pd in pads if pd.GetAttribute() == pcbnew.PAD_ATTRIB_PTH]
    smd = [pd for pd in pads if pd.GetAttribute() in (pcbnew.PAD_ATTRIB_SMD, pcbnew.PAD_ATTRIB_CONN)]
    npth = [pd for pd in pads if pd.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH]
    used = set(pd.GetNetname() for pd in pads if pd.GetNetCode() > 0)
    allnets = set(n for n in b.GetNetsByName().keys() if n)
    trknets = set(t.GetNetname() for t in b.GetTracks() if t.GetNetCode() > 0)
    vias = [t for t in b.GetTracks() if t.Type() == pcbnew.PCB_VIA_T]
    zones = list(b.Zones())
    bb = b.GetBoardEdgesBoundingBox()
    refs = sorted(f.GetReference() for f in fps)
    out[k] = dict(
        footprints=len(fps), refs=refs,
        footprints_no_pads=sorted(f.GetReference() for f in fps if len(list(f.Pads())) == 0),
        pads=len(pads), pads_pth=len(th), pads_smd=len(smd), pads_npth=len(npth),
        pads_unnamed=sum(1 for pd in pads if pd.GetNumber() == ''),
        nets_all=len(allnets), nets_on_pads=len(used), nets_names=sorted(used | trknets),
        nets_unnamed=sorted(n for n in used if n.startswith('Net-') or n.startswith('unconnected-')),
        copper_layers=b.GetCopperLayerCount(), vias=len(vias), zones=len(zones),
        tracks=sum(1 for t in b.GetTracks() if t.Type() == pcbnew.PCB_TRACE_T),
        outline_mm=[round(pcbnew.ToMM(bb.GetWidth()), 2), round(pcbnew.ToMM(bb.GetHeight()), 2)],
        padlist=[[f.GetReference(), pd.GetNumber(), pd.GetNetname(), int(pd.GetAttribute())] for f in fps for pd in f.Pads()],
        thickness_mm=round(pcbnew.ToMM(b.GetDesignSettings().GetBoardThickness()), 3),
    )
json.dump(out, open(sys.argv[1], 'w'), indent=1)
for k, v in out.items():
    print(k, {x: y for x, y in v.items() if x not in ('refs', 'nets_names')})

