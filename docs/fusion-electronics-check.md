# Fusion Electronics check - board A, board B, input board

Job fusionelec, 2026-11-23. Boards from main 19479b5 (the PCBs are byte-identical on de6c419; drcclean only changed
schematic waivers / IDs). Fusion 2706.1.17 (trial, Ultimate, ends 2026-12-01). Every number below came from a tool run;
the scripts are in `tools/fusion_check/` (registered in `automation.yml` as `fusion-electronics-check`), the raw Fusion
reports in `docs/fusion-check/`.

## For Dan (plain English)

1. **All three boards came into Fusion whole.** Same parts, same connections, same 4 / 4 / 2 copper layers, same outline.
   The only things Fusion drops are 11 (A) / 43 (B) paste-only stencil openings that have no copper: they are in the
   KiCad Gerbers we send to JLCPCB, so nothing is lost for the order.
2. **Fusion's own rule checks found no new real defect.** Every Fusion DRC / ERC item is one of: something we already
   know and ordered for (vias in pads, filled and capped), the maker's USB-C pattern, a rule Fusion copied from KiCad's
   project settings, or a side effect of the translation (Fusion re-pours the copper fills and reads track joins its own
   way). The one real item, board A's 3 unused op-amp channels with floating inputs, was already found by KiCad and the
   drcclean job; its fix is on branch `fix/tlv-unused` (board A needs this check re-run after it merges).
3. **Fusion heat study: not run.** See section 5 (it cannot put the copper's current heating on the board, so it would
   not check what the Elmer / `thermal_board_b.py` models check).

![board A in Fusion](diagrams/fusion-board-a.png)

![board B in Fusion](diagrams/fusion-board-b.png)

![input board in Fusion](diagrams/fusion-input-board.png)

## 1. What was imported, where

Fusion project `custom-pdm`, folder `electronics-2026-11-23` (the old `board-A-2026-11-11`, `board-B-2026-11-11`,
`input-board` folders are untouched). Import = Fusion's KiCad importer (API `DataFolder.uploadFile` of the
`.kicad_pro`, "ECAD Design Upload Options": Sheets, Create Electronics Design; one click on OK per board, done by the
agent with screen control, DECISIONS 2026-11-08). Uploaded from a scratch copy of `hardware/` (nothing written back).

| Board | Fusion subfolder | Designs (v1) |
|---|---|---|
| A | `electronics-2026-11-23/board-A` | `DingoPDM` .fprj / .fsch / .fbrd |
| B | `electronics-2026-11-23/board-B` | `dingoPDM-Max` .fprj / .fsch / .fbrd |
| Input | `electronics-2026-11-23/input-board` | `input-board` .fprj / .fsch / .fbrd |

File formats: the PCBs are KiCad 9 (`20241229`), the schematics KiCad 10 (`20260306`). No KiCad 9 save-as copy was
needed: the nets came through (section 2). The KiCad 10 problem in `hardware.md` is the PCB file (PR #3: a KiCad 10
`.kicad_pcb` lost every net); Fusion reads KiCad 10 schematics. Fusion shows "Schematic/PCB sync deactivated" on every
import (the importer does not link the two), which is why the ERC lists every part as "FOOTPRINT not found in board".

## 2. Translation check (Fusion ULP `brdinfo.ulp` vs KiCad 9 pcbnew `kicad_ref.py`, compared by `compare2.py`)

Nets are compared by their pin sets, not by name (Fusion renames KiCad's hierarchical and auto nets: `/MCU/CAN_TX` ->
`MCU_CAN_TX`, `Net-(U8-IS)` -> `N$nn`; KiCad pads that share a number in one footprint get `_1`, `_2` ... suffixes).

| Item | Board A KiCad / Fusion | Board B KiCad / Fusion | Input KiCad / Fusion |
|---|---|---|---|
| Parts | 145 / 145 (same references) | 211 / 211 | 50 / 50 |
| Nets with 2+ pads | 113 / 113 (0 split, 0 merged, 0 pins missing) | 139 / 139 (0 / 0 / 0) | 36 / 36 (0 / 0 / 0) |
| Extra 1-pin signals in Fusion | 5 (`MCU_SWO_UNUSED` + 4 unnamed single pads) | 6 | 0 |
| Named nets kept by name | 59 of 64 (rest: hierarchical renames) | 66 of 75 | 36 of 36 (leading `/` dropped) |
| Pads | 528 / 517 | 798 / 755 | 159 / 159 |
| Pad difference | 11 paste-only openings (no copper, no number): D2 4, U21 3, D26 2, D27 2 | 43 paste-only: T1-T8 4 each, D2 4, U27 3, D29 2, D30 2 | none |
| Vias | 325 / 325 | 678 / 678 | 136 / 136 |
| Copper layers | 4 / 4 (Top, Route2, Route63, Bottom) | 4 / 4 | 2 / 2 |
| Outline (edge to edge) | 72.39 x 95.25 mm / same (KiCad's 72.44 x 95.30 includes the 0.05 mm line) | 111.39 x 95.25 mm / same | 66.0 x 64.0 mm / same (0.1 mm line) |

**Translation differences that matter: none.** Fusion also copies KiCad's net class "Default" (track 0.2 mm, via drill
0.4 mm, clearance 0.2 mm; B 0.2032 mm) into its net class 0, and does not copy KiCad's zone priorities: both show up in
the DRC below. Info: the KiCad stackup says 1.77 mm (upstream's dielectrics, kept on purpose by `tools/pcb_stackup.py`);
JLCPCB builds its own 1.6 mm (order checklist), so the board STEP is 0.17 mm thicker than the real board.

## 3. Fusion DRC with JLCPCB rules (`jlc4.dru` / `jlc2.dru`, from `mkdru.py`)

Rules = the JLCPCB limits in `tools/gen_fab_jlcpcb.py` (`JLC_LIMITS`): 4-layer track / clearance 0.09 mm (2-layer
0.10), SMD-SMD 0.15, hole 0.15, hole to hole 0.2, copper to edge 0.2, annular ring PTH 0.15 (2-layer 0.18) and via 0.05
(fixed, no drill-percentage), copper 35 um on all layers, dielectric 0.21 / 1.065 / 0.21 mm (1.6 mm board; 2-layer
1.53 mm). Fusion's net class 0 (copied from KiCad, see 2) still applies on top.

| Fusion DRC item | A | B | IN | Class | Why |
|---|---|---|---|---|---|
| Overlap (via in / touching an SMD pad, same net) | 66 | 168 | 50 | known, covered | The via-in-pad vias (58 / 151 / 27, `verify_dfm.py`); ordered Epoxy Filled & Capped (order checklist, fab notes). |
| Overlap (solder jumper pads JP1 / JP3 (A), JP1 / JP2 (B), and pads touching pads of one footprint) | 21 | 30 | 0 | import artefact | KiCad's custom-shape jumper pads become several overlapping Fusion pads. KiCad DRC: 0. |
| Copper clearance at USB-C J5 (A) / J2 (B) | 40 | 40 | - | known (maker pattern) | GCT USB4085: 0.15 mm gaps (drcclean group 8); Fusion's oval-pad translation reads them tighter. JLC check passes. |
| Copper clearance elsewhere | 15 | 123 (67 at U4) | 0 | rule artefact | Net class 0 = KiCad's 0.2 / 0.2032 mm clearance: LQFP U4 pins at 0.5 mm pitch have a 0.2 mm gap (B fails 0.2032 by 3 um, same as drcclean group 9); the rest are Fusion's re-poured fills. KiCad DRC at the same rules: 0 active. |
| Copper width | 0 | 101 | 0 | rule artefact | The 101 tracks of 0.2 mm vs the 0.2032 mm class width (the same 101 KiCad tracks, drcclean group 9). JLCPCB: 0.09 mm. |
| Drill size | 5 | 4 | 0 | rule artefact | 0.3 mm vias (U21 / U27 pad, FB1, D26) vs the class via drill 0.4 mm. JLCPCB: 0.15 mm. |
| Clearance (polygons with same rank) | 25 | 37 | 0 | import artefact | KiCad zone priorities (PF_OUT pours at J3 / T1-T8) are not copied; KiCad fills them in order. |
| Component exclude clearance (courtyards) | 25 | 42 | 0 | known + artefact | Around the DNP 5 V modules U14 (A) / U12 (B) next to U21 / U27 and its caps (KiCad courtyard items, waived by drcclean), the press-fit terminals, J1 / H1; the rest are Fusion's own keep-out shapes. |
| Annular ring | 6 | 22 | 8 | import artefact | Non-plated holes (Tag-Connect J4 / J5, REDCUBE T1-T8 centre holes, J2 / H1 / H2 on the input board) become pads with no ring. |
| Air wires (unrouted; items / wire pieces) | 8 / 8 | 12 / 25 | 0 | import artefact | Joints KiCad makes by copper overlap: a track that runs across a pad without ending on it (e.g. B C66.1 / C67.1 +12P, U22 pins 1-2) or a pad that joins its fill only by KiCad's own pour. KiCad: 0 unconnected, parity 0. Fusion only counts a track end or its own pour. |
| Wire stubs (warning) | 10 | 35 | 0 | import artefact | Track ends that sit off a pad centre or under a via; electrically joined in KiCad. |

Totals: A 221, B 614, input board 58 (raw lists in `docs/fusion-check/drc-*.txt`). **Real defects from the Fusion DRC: none.**

## 4. Fusion ERC (schematics)

| Fusion ERC item | A | B | IN | Class |
|---|---|---|---|---|
| Attribute FOOTPRINT not found in board (info) | 145 | 209 | 50 | import artefact (sync deactivated, section 1) |
| More than one OUTPUT pin on PF_OUTn | 24 | 72 | 0 | false alarm: PROFET output pins of one channel tied, as the data sheets require (drcclean group 3) |
| SUPPLY pin overwritten (regulator outputs, VCAP_1, DNP 5 V modules on +5VP) | 10 | 10 | 0 | false alarm (drcclean groups 4-6) |
| POWER pin connected to ... (info) | 31 | 39 | 0 | information only |
| Missing junction / segment with no visual connection | 11 | 14 | 0 | cosmetic (KiCad wire drawing; connectivity matches, section 2) |
| Only input pins / one pin on MCU_SWO_UNUSED | 2 | 0 | 0 | intentional (drcclean group 7) |
| **Uninvoked op-amp gates with unconnected inputs: U7 A, U12 A and B** | 6 | 0 | 0 | **real (small, known)**: 3 unused TLV9004 channels on board A float; KiCad `missing_unit` shows the same; fix on `fix/tlv-unused` |

## 5. Fusion thermal cross-check: not run

- Licence (Fusion MCP `licensing`, 2026-11-23): trial, Simulation extension active until 2026-12-01, no Flex tokens.
  Autodesk: Fusion solves Thermal and Electronics Cooling studies only in the cloud; without the Simulation Extension they
  cost 3 / 6 tokens each (help: "Tokens for simulation studies"). So today a solve would cost no tokens, but only for 8 days.
- Not run because it would not be a cross-check of the same physics: a Fusion Electronics Cooling study takes heat per
  body (chip) and a board-level copper description; it cannot apply the current-driven I^2R heating of the +12 V feed
  and output copper (board B: 9.1 W at 150 A, `docs/pcb-verification.md`), which is what limits board B in
  `thermal_board_b.py` and the Elmer model. It also needs a 3D PCB and a study set up through the experimental `adsk.sim`
  API or by hand. DECISIONS 2026-11-08 (Dan) also says "No Fusion thermal study".
- If the coordinator still wants a chip-only check (driver losses + sink at 70.9 / 74.5 C, `docs/heat-analysis.md`,
  fans on), it must be run before 2026-12-01 while the trial extension is active.

## How to re-run

1. Upload: Fusion Data Panel or API `uploadFile` of each `.kicad_pro` (scratch copy), Sheets, OK.
2. Open each `.fbrd`; Fusion text command `Electron.run "RUN tools/fusion_check/brdinfo.ulp <out>.txt"` and
   `geo.ulp`; `DRC LOAD tools/fusion_check/jlc4.dru` (`jlc2.dru` for the input board; Fusion asks "use these settings
   anyway?" (same-signal clearance note): Yes), `DRC`, `RUN errs.ulp <out>.txt`; on each `.fsch`: `ERC`, `RUN errs.ulp`.
3. `"%LOCALAPPDATA%\Programs\KiCad\9.0\bin\python.exe" tools/fusion_check/kicad_ref.py ref.json`, then
   `compare2.py ref.json A|B|IN <brdinfo out>`, `classify.py <errs out> <geo out> <out.json>`, `ercsum.py <erc out>`.
