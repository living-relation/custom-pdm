# STATE - custom-pdm

Updated 2026-11-07.

## Status
- Repo created (public). No design files in the repo yet; the Fusion import lives in the Fusion project.
- Reference KiCad sources (dingoPDM v7.5, dingoPDM-Max) cloned locally under `reference/` (git-ignored, about 350 MB).
- dingoPDM v7.5 imported into Fusion Electronics (Fusion project `custom-pdm`, Sheets translation): design, schematic and board files created. Check: 115/115 named nets match; all 156 parts. Board checked: outline 72.39 x 95.25 mm, 4 copper layers, 522 pads, board image looks right.
- Part and net lists from the import are in the models folder (`Desktop\models\custom-pdm-import-check`, OneDrive, add-only).
- BOM v4 is in `docs/custom-pdm-bom-v4.xlsx` (prices are estimates, many yellow guesses).
- Next: check the imported board by eye, then start the board A changes (replace 2x BTS7002 with a 4th BTS7008 dual; add 8 universal analog inputs).
- Plan B (3 boards on CAN, one enclosure) leads; Plan C (one brain + power slices) still open.

## Open items
- Decide 256 Kbit FRAM vs 64 Kbit substitute.
- Design the 150 A feed busbar.
- Pick connector part numbers.
- Pick fab: JLCPCB vs PCBWay.

## Decisions 2026-11-08
- PDM mounts inside the cabin (design air temp up to about 60 C). Enclosure: aluminum, or MJF print with a heat sink; thermal pads, small fan allowed.
- 8 A outputs are limited to 7.5 A (BTS7008-2EPA rating, all channels on at 85 C).
- Heat checks: hand calc now, Elmer 3D model (handbuilt-cad sim stack) once the layout exists. No Fusion thermal study.
- Found: BTS7002-1EPP and BTS7008-2EPA share the TSDSO-14 footprint and pins 1-4 (GND, IN/IN0, DEN, IS) and 15 (VS). The dual adds DSEL (pad 5) and IN1 (pad 6), and splits outputs (pads 12-14 OUT0, 8-10 OUT1).
