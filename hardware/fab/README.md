# Fab outputs (JLCPCB; PCBWay fallback)

Everything in `hardware/fab/` is generated: never hand-edit it, re-run the script.

## Regenerate

```
"%LOCALAPPDATA%\Programs\KiCad\9.0\bin\python.exe" tools/gen_fab_jlcpcb.py          (all boards; or A / B / IN)
```

KiCad 9 python reads the PCBs (BOM, placement, geometry checks); kicad-cli 10 plots on a temp copy, so the design files are not touched. A re-run on unchanged boards gives identical files (dates are stripped). Part fields come from `tools/sch_bom_fields.py` (run in the board builds); change parts there, rebuild, then re-run this.

## What to upload (per board folder: `board-a`, `board-b`, `input-board`)

| JLCPCB step | File |
|---|---|
| Gerber | `<board>-gerber.zip` (Gerbers + PTH / NPTH Excellon drill from `gerber/`; the zip is git-ignored, re-run the script to get it) |
| PCB options + remark | `fab-notes.md` (layers, size, 1.6 mm, ENIG, the remark to paste) |
| Assembly BOM | `<board>-bom-jlcpcb.csv` (Comment, Designator, Footprint, LCSC) |
| Assembly CPL | `<board>-cpl-jlcpcb.csv` (Designator, Mid X, Mid Y, Layer, Rotation) |
| Check before paying | `jlcpcb-drc.txt` (DRC against JLCPCB limits, worst values), then JLCPCB's own part-placement preview |

Quantities for one PDM: 2 x board A, 1 x board B, 3 x input board. `<board>-bom-full.csv` lists every part with maker, MPN, LCSC, Digi-Key, approved alternates and who fits it: use it for PCBWay (turnkey quote by MPN) or when JLCPCB shows a part short (pick the approved alternate). Stock / basic-extended status and the reasons for part choices: `docs/parts-audit.md` section 13.

## Settings and where they come from

- Gerbers: F/B copper + inner layers, paste, silkscreen, mask, Edge.Cuts; Protel extensions, X2, netlist attributes, 4.6 mm. Drill: Excellon, mm, decimal, absolute origin, oval holes 'alternate', PTH and NPTH separate. JLCPCB "How to generate Gerber and drill files in KiCad 9".
- CPL: mm, Top / Bottom, rotation positive = counter-clockwise (JLCPCB "Pick & place file for PCB assembly"); KiCad's rotation plus JLCPCB's known offsets: SOT-23 / SOT-223 +180, SOIC / MSOP / TSSOP / LQFP +270, JST GH side-entry +180 (KiBot's JLCPCB table), Infineon TDSO-14 / TSDSO-24 +270 (pin 1 in the TSSOP corner). Every other footprint: no offset. Positions are footprint origins in the Gerber coordinates (absolute). No part sits on the bottom side.
- Board: 1.6 mm, ENIG (the KiCad stackup says 1.77 mm; JLCPCB builds its own 4-layer 1.6 mm stackup; copper weight is left as it is). The terminals need at least 1.6 mm (7461084: 1.6-3.2 mm; 74650074R: 1.6-2.0 mm, Wurth data sheets), and JLCPCB's thickness tolerance is +-10 %, hence the remark.
- Press-fit (7461084: A J1 / J2, B J1 / J3): JLCPCB makes press-fit holes (+-0.05 mm, 0.55-2.0 mm, multilayer ENIG, round, named in the remark; capabilities page); the footprint's 1.475 mm finished hole is Wurth's chemical-surface value with the same +-0.05 mm. Wurth also asks for 25-60 um copper in the hole; JLCPCB publishes an 18 um average: the remark asks them to confirm. JLCPCB's assembly service does not list press-fit, and Wurth says the part is never soldered, so the six terminals are left out of the JLCPCB BOM / CPL and pressed in after delivery (how: `fab-notes.md`).

## Check results (2026-11-16)

DRC with JLCPCB's limits as the only rules: no violation on any board. Worst values: track 0.20 mm (limit 0.09), via 0.40 / 0.80 mm (0.15 / 0.25), PTH annular ring 0.15 mm at the USB-C socket (absolute minimum 0.15, 0.20 recommended), smallest copper gap 0.114 mm on board B (U4 pad 64, from the 2026-11-16 e1 check; limit 0.09). Not caught by KiCad's DRC (same-net holes) and found by the script's own hole check, each a layout fix before ordering:
- board A: two GND vias 0.2 mm apart (holes overlap by 0.195 mm) near (-27.5, 5.3).
- board B: 8 vias drilled into the T1-T4 terminal pin holes (overlap up to 0.365 mm); 3 more vias 0.05-0.17 mm from T2-T4 pin holes (limit 0.45 mm); zone fill out of date (a refill changes PF_OUT2 on F.Cu by 0.46 %).
- input board: two pairs of +3V3 vias overlapping (0.2 / 0.1 mm).
Details: each board's `jlcpcb-drc.txt`.
