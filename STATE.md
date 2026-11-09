# STATE - custom-pdm

Updated 2026-11-08. Decisions live in `DECISIONS.md`; scripts are listed in `automation.yml`.

**Last cleanup:** 2026-11-08 @ 46e5a49 (repo-cleanup PR)
**Kept branches:** none
**Hook:** state-check workflow installed, comment mode (2026-11-08)

## Status
- Repo created (public). Board A design source is KiCad (`hardware/board-a/`). Rebuild it with `tools/build_board_a.ps1` (baseline + scripts, then ERC/DRC). The PCB must stay KiCad 9 format (KiCad 9.0.8 python edits it): Fusion's importer loses all nets from a KiCad 10 PCB. Schematics are KiCad 10 format upstream and import fine. kicad-cli 10 is used read-only. Fusion is for viewing, 3D and later checks (re-import after each round).
- Reference KiCad sources (dingoPDM v7.5, dingoPDM-Max) cloned locally under `reference/` (git-ignored, about 350 MB).
- dingoPDM v7.5 imported into Fusion Electronics (Fusion project `custom-pdm`, Sheets translation): design, schematic and board files created. Check: 115/115 named nets match; all 156 parts. Board checked: outline 72.39 x 95.25 mm, 4 copper layers, 522 pads, board image looks right.
- Part and net lists from the import are in the models folder (`Desktop\models\custom-pdm-import-check`, OneDrive, add-only).
- BOM v4 is in `docs/custom-pdm-bom-v4.xlsx` (prices are estimates, many yellow guesses).
- Board A step 1 done (PR #2): U8+U9 (2x BTS7002) replaced by one BTS7008-2EPA dual at U8. J3 re-pinned: pin 7 = OUT2, pin 8 = OUT1 (was IN1), pin 12 = IN1 (was OUT2). PF_DEN2 MCU pin is now PF_DSEL1_2. PF_IS2 ADC path is spare (buffer input tied to GND). DRC/parity: 0 unconnected, no shorts, all other findings same as the unmodified dingoPDM baseline (28 clearance findings pre-exist).
- Fusion `custom-pdm` project: root = clean import of the original; `board-A` = unmodified re-import (+ `LINKED-COPY-unused`, deletable); `board-A-dual-k9` = modified board A (143 parts, 111 nets = KiCad); `board-A-dual` = broken KiCad 10 import with no nets (deletable).
- Board A inputs DONE (PR #7, 2026-11-09), part of the default build. Fusion re-import `board-A-inputs` checked: 135/135 parts, all nets match by pin set (J1/J2/J5 multi-pad pins only renamed).
  - J6 (JST GH 12-pin, side entry) at the left edge: 1-5 IN_3..IN_7 = PC10, PC11, PB4, PC13, PB3 (ex-SWO); 6-8 NC; 9 PC2 spare analog (R12 DNP); 10 +3V3; 11-12 GND.
  - All test points removed (THT ones that joined layers got a via; dead-end stubs removed). SWO dropped. GND fenced-in pad C32.1 got a stitching via; one floating GND sliver covered by a no-fill area.
  - DRC: 0 unconnected, 0 shorts, same 28 inherited clearance findings as stock dingo. DRT logo G1 removed (Dan), so no new silkscreen notes. ERC 623 (was 632).
  - Board B (Max) check: ~9 new inputs escape without rework (PC10, PC11, PC13, PB3 + PB12, PB10, PB1, PC4, PB4). Plan ~9 there (Dan, A6a). System: 7 + 7 + ~11 = ~25 inputs.
  - Input board (DIP pulls, DT panel connector) not started.
- Plan B (3 boards on CAN, one enclosure) leads; Plan C (one brain + power slices) still open.

## Open items
- Next: input daughter board (5 inputs + spare analog on J6; per input 4.7 k + BAT54S + 10 nF, DIP 10 k up/down/off; DT 12-pin panel receptacle wired to it).
- Heat sink design: two pedestals (U8/U11 and U10/U13), insulating gap pad, pocket for J3 pins, center standoff.
- Harness: J3 pinout changed on board A (see Status).
- Firmware (later): outputs 1-2 are now a dual pair (DSEL on the old PF_DEN2 pin).
- Review the 28 pre-existing DRC clearance findings before ordering.
- Decide 256 Kbit FRAM vs 64 Kbit substitute.
- Design the 150 A feed busbar.
- Pick connector part numbers.
- Pick fab: JLCPCB vs PCBWay.
