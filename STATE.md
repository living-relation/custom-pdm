# STATE - custom-pdm

Updated 2026-11-08. Decisions live in `DECISIONS.md`; scripts are listed in `automation.yml`.

**Last cleanup:** 2026-11-08 @ 46e5a49 (repo-cleanup PR)
**Kept branches:** feat/input-board (active, input expansion WIP)
**Hook:** state-check workflow installed, comment mode (2026-11-08)

## Status
- Repo created (public). Board A design source is KiCad (`hardware/board-a/`). Rebuild it with `tools/build_board_a.ps1` (baseline + scripts, then ERC/DRC). The PCB must stay KiCad 9 format (KiCad 9.0.8 python edits it): Fusion's importer loses all nets from a KiCad 10 PCB. Schematics are KiCad 10 format upstream and import fine. kicad-cli 10 is used read-only. Fusion is for viewing, 3D and later checks (re-import after each round).
- Reference KiCad sources (dingoPDM v7.5, dingoPDM-Max) cloned locally under `reference/` (git-ignored, about 350 MB).
- dingoPDM v7.5 imported into Fusion Electronics (Fusion project `custom-pdm`, Sheets translation): design, schematic and board files created. Check: 115/115 named nets match; all 156 parts. Board checked: outline 72.39 x 95.25 mm, 4 copper layers, 522 pads, board image looks right.
- Part and net lists from the import are in the models folder (`Desktop\models\custom-pdm-import-check`, OneDrive, add-only).
- BOM v4 is in `docs/custom-pdm-bom-v4.xlsx` (prices are estimates, many yellow guesses).
- Board A step 1 done (PR #2): U8+U9 (2x BTS7002) replaced by one BTS7008-2EPA dual at U8. J3 re-pinned: pin 7 = OUT2, pin 8 = OUT1 (was IN1), pin 12 = IN1 (was OUT2). PF_DEN2 MCU pin is now PF_DSEL1_2. PF_IS2 ADC path is spare (buffer input tied to GND). DRC/parity: 0 unconnected, no shorts, all other findings same as the unmodified dingoPDM baseline (28 clearance findings pre-exist).
- Fusion `custom-pdm` project: root = clean import of the original; `board-A` = unmodified re-import (+ `LINKED-COPY-unused`, deletable); `board-A-dual-k9` = modified board A (143 parts, 111 nets = KiCad); `board-A-dual` = broken KiCad 10 import with no nets (deletable).
- Board A inputs (branch `feat/input-board`, WIP, not merged):
  - Schematic/PCB scripts add J6 (JST GH 12-pin) at the left edge, IN_3..IN_10 on PA8, PA15, PB4, PB5, PB13, PC14, PC15, PD2, spare analog on PC2 (R12 DNP). Run with `tools/build_board_a.ps1 -WithInputs`; the default build is unchanged.
  - Router is importable (`route_board_a.py`); `pcb_rework.py` rips up / reconnects; `pcb_inputs_board_a.py` fans out U4 pins with exact KiCad collision checks.
  - Pin plan (Dan, A4a): IN_3..IN_10 = PC10, PC11, PB4, PB5, PB13, PC13, PB3 (ex-SWO), PD2. All 8 test points removed (TP8-TP10 were dingo's E1-E3 expansion pads on PC10/PC11/PC13, already routed out). SWO dropped (Tag-Connect pin unused).
  - Result (fan-out experiments, 2026-11-08): only 5 new inputs escape without disturbing dingo's own signals: PC10, PC11, PC13, PB3 (existing copper) + PB4. PB5/PD2/PB13/PA15 each box in a neighbour (CAN_STANDBY, I2C SCL/SDA, PF_DSEL3_4) that then can't reconnect, even with 0.6/0.3 vias. Waiting on Dan (A5).
  - Input board (DIP pulls, DT panel connector) not started.
- Plan B (3 boards on CAN, one enclosure) leads; Plan C (one brain + power slices) still open.

## Open items
- A5 (Dan): 5 direct inputs per board A, or re-lay out the area around U4 (bigger board OK), or 5 direct + I2C expander.
- Heat sink design: two pedestals (U8/U11 and U10/U13), insulating gap pad, pocket for J3 pins, center standoff.
- Harness: J3 pinout changed on board A (see Status).
- Firmware (later): outputs 1-2 are now a dual pair (DSEL on the old PF_DEN2 pin).
- Review the 28 pre-existing DRC clearance findings before ordering.
- Decide 256 Kbit FRAM vs 64 Kbit substitute.
- Design the 150 A feed busbar.
- Pick connector part numbers.
- Pick fab: JLCPCB vs PCBWay.
