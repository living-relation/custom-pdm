"""Input board build stage: 3D model of J2 (Molex Micro-Fit 3.0 43045-1200) -> Molex's own STEP in the repo.

usage (KiCad 9 python):  python tools/pcb_models_input_board.py <input-board.kicad_pcb>

KiCad's stock footprint Connector_Molex:Molex_Micro-Fit_3.0_43045-1200_2x06_P3.00mm_Horizontal names a 3D file that
KiCad's library does not ship, so the board STEP had no body for J2 (BACKLOG 2026-11-24). The model is
hardware/input-board/Models/430451200.stp: Molex's STEP AP242 for part 430451200 (TraceParts part 33-16012026-074394,
version 1.2.1), downloaded 2026-11-24 from the 3D Model download on https://www.molex.com/en-us/products/part-detail/430451200.
Model axes (read from the STEP): X across the 6 columns, pins at X = -7.5 .. +7.5 (3 mm pitch); Y up from the board
(tails to Y = -3.69, peg to Y = -3.69, housing top Y = 8.26); Z toward the mating face (face at Z = 0, row nearest the
pegs at Z = -8.92, second row Z = -11.92, pegs Z = -4.60). The footprint has pad 1 at (0, 0), pads 7-12 at y = +3, pegs
at y = -4.32. KiCad applies the model's rotate angles negated, X then Y then Z, then the offset (mm, Y up): rotate
(-90, 0, 180) gives (x, y, z) -> (-x, z, y), offset (7.5, 8.92, 0) puts the row at Z = -8.92 on pads 1-6 and the pegs
in their holes. Only the model entry changes: no pad, net, position or copper. Idempotent. Check: the J2 pins in the
board STEP (kicad-cli pcb export step) sit on the pad centres (docs/pcb-verification.md, J2 model check).
"""
import sys

import pcbnew

REF = "J2"
FOOTPRINT = "Molex_Micro-Fit_3.0_43045-1200_2x06_P3.00mm_Horizontal"
MODEL = "${KIPRJMOD}/Models/430451200.stp"
OFFSET = (7.5, 8.92, 0.0)
ROTATE = (-90.0, 0.0, 180.0)


def main(path):
    b = pcbnew.LoadBoard(path)
    fp = b.FindFootprintByReference(REF)
    if fp is None or str(fp.GetFPID().GetLibItemName()) != FOOTPRINT:
        raise SystemExit(f"{REF}: not a {FOOTPRINT} footprint")
    ms = fp.Models()
    if len(ms) != 1:
        raise SystemExit(f"{REF}: {len(ms)} 3D models, expected 1")
    m = ms[0]
    want = (MODEL, OFFSET, ROTATE)
    have = (m.m_Filename, (m.m_Offset.x, m.m_Offset.y, m.m_Offset.z), (m.m_Rotation.x, m.m_Rotation.y, m.m_Rotation.z))
    if have != want:
        m.m_Filename = MODEL
        m.m_Offset = pcbnew.VECTOR3D(*OFFSET)
        m.m_Rotation = pcbnew.VECTOR3D(*ROTATE)
        m.m_Show = True
        pcbnew.SaveBoard(path, b)
    print(f"pcb_models_input_board: {REF} on {MODEL} ({'changed' if have != want else 'unchanged'})")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])
