"""Board B build stage: 3D model path of U8-U11 (BTS70012-1ESP, PG-TSDSO-24) -> the best-guess body in the repo.

usage (KiCad 9 python):  python tools/pcb_models_board_b.py <dingoPDM-Max.kicad_pcb>

Upstream points these footprints at a file on its author's disk, so the board STEP carried no body for them
(docs/order-readiness.md section 5). The model is hardware/board-b-max/Models/PG-TSDSO-24_bestguess.step, written by
tools/tsdso24_model.py (a labelled best guess; sources there). Only the model file name changes: no pad, net,
position or copper. Idempotent.
"""
import sys

import pcbnew

REFS = ("U8", "U9", "U10", "U11")
MODEL = "${KIPRJMOD}/Models/PG-TSDSO-24_bestguess.step"


def main(path):
    b = pcbnew.LoadBoard(path)
    n = 0
    for ref in REFS:
        fp = b.FindFootprintByReference(ref)
        if fp is None or str(fp.GetFPID().GetLibItemName()) != "TSDSO-24":
            raise SystemExit(f"{ref}: not a TSDSO-24 footprint")
        ms = fp.Models()
        if len(ms) != 1:
            raise SystemExit(f"{ref}: {len(ms)} 3D models, expected 1")
        if ms[0].m_Filename != MODEL:
            ms[0].m_Filename = MODEL
            n += 1
    if n:
        pcbnew.SaveBoard(path, b)
    print(f"pcb_models_board_b: {len(REFS)} footprints on {MODEL} ({n} changed)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])
