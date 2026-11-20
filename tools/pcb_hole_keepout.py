"""Copper keep-out around the board mounting holes (last PCB stage of board A and board B; KiCad 9 python).

usage: python tools/pcb_hole_keepout.py <board.kicad_pcb>

Why (pcbverify 2026-11-20, docs/pcb-verification.md): each mounting hole H* sits on an aluminium heat-sink post,
dia 6.0 mm (enclosure/v2b/src/build_v2b.py, BOSS), under an M3 ISO 7380 head (dia 5.7 mm). The +12V pour on the
bottom copper started 3.11 mm from the hole centre, 0.11 mm outside the post: bare metal pressing on solder mask over
the 150 A feed. IPC-2221B table 6-1, 31-50 V: 0.6 mm uncoated (B2), so copper pours stay out of a circle of
r = 3.0 + 0.6 = 3.6 mm on the outer layers. Only pours are kept out (tracks, pads, vias are untouched; none of them
are inside 3.6 mm). Idempotent: an existing keep-out named 'hole-keepout' is replaced. Pours are refilled.
"""
import math
import sys

import pcbnew

R_KEEP = 3.6        # mm: sink post radius 3.0 + 0.6 (IPC-2221B B2, 31-50 V)
NAME = "hole-keepout"
mm = pcbnew.FromMM


def main(path):
    b = pcbnew.LoadBoard(path)
    old = [z for z in b.Zones() if z.GetIsRuleArea() and z.GetZoneName().startswith(NAME)]
    holes = [fp for fp in b.GetFootprints() if "MountingHole" in str(fp.GetFPID().GetLibItemName())]
    for z in old:
        b.Remove(z)
    for fp in holes:
        z = pcbnew.ZONE(b)
        z.SetIsRuleArea(True)
        z.SetZoneName(f"{NAME}-{fp.GetReference()}")
        z.SetDoNotAllowCopperPour(True)
        z.SetDoNotAllowTracks(False)
        z.SetDoNotAllowVias(False)
        z.SetDoNotAllowPads(False)
        z.SetDoNotAllowFootprints(False)
        ls = pcbnew.LSET()
        ls.AddLayer(pcbnew.F_Cu)
        ls.AddLayer(pcbnew.B_Cu)
        z.SetLayerSet(ls)
        o = z.Outline()
        o.NewOutline()
        cx, cy = fp.GetPosition().x, fp.GetPosition().y
        n = 48
        for i in range(n):
            a = 2 * math.pi * i / n
            # polygon circumscribing the circle, so the keep-out is at least R_KEEP everywhere
            r = mm(R_KEEP) / math.cos(math.pi / n)
            o.Append(int(cx + r * math.cos(a)), int(cy + r * math.sin(a)))
        b.Add(z)
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    b.Save(path)
    print(f"hole keep-out r {R_KEEP} mm on F.Cu / B.Cu: {', '.join(fp.GetReference() for fp in holes)} "
          f"({len(old)} old keep-outs replaced)")


if __name__ == "__main__":
    main(sys.argv[1])
