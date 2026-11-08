# STATE - custom-pdm

Updated 2026-11-08.

## Status
- Repo created (public). Board A design source is KiCad (`hardware/board-a/`, KiCad 10 format; KiCad 10.0.7 on DansPC). Edits are scripted in `tools/` and checked with KiCad ERC/DRC; Fusion is for viewing, 3D and later checks (re-import after each round).
- Reference KiCad sources (dingoPDM v7.5, dingoPDM-Max) cloned locally under `reference/` (git-ignored, about 350 MB).
- dingoPDM v7.5 imported into Fusion Electronics (Fusion project `custom-pdm`, Sheets translation): design, schematic and board files created. Check: 115/115 named nets match; all 156 parts. Board checked: outline 72.39 x 95.25 mm, 4 copper layers, 522 pads, board image looks right.
- Part and net lists from the import are in the models folder (`Desktop\models\custom-pdm-import-check`, OneDrive, add-only).
- BOM v4 is in `docs/custom-pdm-bom-v4.xlsx` (prices are estimates, many yellow guesses).
- Board A step 1 done (PR #2): U8+U9 (2x BTS7002) replaced by one BTS7008-2EPA dual at U8. J3 re-pinned: pin 7 = OUT2, pin 8 = OUT1 (was IN1), pin 12 = IN1 (was OUT2). PF_DEN2 MCU pin is now PF_DSEL1_2. PF_IS2 ADC path is spare (buffer input tied to GND). DRC/parity: 0 unconnected, no shorts, all other findings same as the unmodified dingoPDM baseline (28 clearance findings pre-exist).
- Fusion: `custom-pdm` project holds the clean import (root) and a `board-A` folder with an independent re-import of the unmodified design; `LINKED-COPY-unused` there can be deleted.
- Next: re-import the modified board A into Fusion and review in 3D; then add 8 universal analog inputs (start with the spare PF_IS2 path).
- Plan B (3 boards on CAN, one enclosure) leads; Plan C (one brain + power slices) still open.

## Open items
- Harness: J3 pinout changed on board A (see Status).
- Firmware (later): outputs 1-2 are now a dual pair (DSEL on the old PF_DEN2 pin).
- Review the 28 pre-existing DRC clearance findings before ordering.
- Decide 256 Kbit FRAM vs 64 Kbit substitute.
- Design the 150 A feed busbar.
- Pick connector part numbers.
- Pick fab: JLCPCB vs PCBWay.

## Decisions 2026-11-08
- PDM mounts inside the cabin (design air temp up to about 60 C). Enclosure: aluminum, or MJF print with a heat sink; thermal pads, small fan allowed.
- 8 A outputs are limited to 7.5 A (BTS7008-2EPA rating, all channels on at 85 C).
- Heat checks: hand calc now, Elmer 3D model (handbuilt-cad sim stack) once the layout exists. No Fusion thermal study.
- Found: BTS7002-1EPP and BTS7008-2EPA share the TSDSO-14 footprint and pins 1-4 (GND, IN/IN0, DEN, IS) and 15 (VS). The dual adds DSEL (pad 5) and IN1 (pad 6), and splits outputs (pads 12-14 OUT0, 8-10 OUT1).
