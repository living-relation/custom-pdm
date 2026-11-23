# STATE (max 30 lines, overwrite only)
Repo: custom-pdm
Branch: chore/cad-models-fusion
Last_Verified_SHA: dd90054
Updated: 2026-11-21 -- enclcheck

## Current Goal
- Objective: PR #118 head dd90054 = main 2e3c68d merged (TI 5 V module boards); rebuilt with re-exported board STEPs: build 55 items / 51 PNs, bom 0 fails, access 0 / 66, lug 0 / 43, CNC 9 parts pass, drawings 11 ok, clearance 31 known pairs (identical to cadfetch5), asm drawing ok, deliverable_lock OK 18; part STEPs vs published revD: 50 / 52 DATA equal, only CPDM-PCB-A / CPDM-PCB-B changed (new 5 V module) -> boards need a release (fold into revE)
- Spec_Ref: coordinator messages to enclcheck 2026-11-21 (A: merge 2e3c68d + re-check; B: Dan 09:32 real round wires instead of ribbons)

## Active Blocker
- Status: NONE
- Detail: B not started in code (context); research done: no "Make Wires" / "Create Wires" add-in installed (AddIns, ApplicationPlugins, handbuilt-cad fusion_addins; Fusion has 3153 commands, none for wires) -> sweep with the Fusion API. Fusebox example (st185-link-ecu-config main cad/fusebox/src/build_fusion.py, read only): wires = TemporaryBRep cylinders + quarter-torus bends at 3 x OD (cyl / quarter_bend, harness_tails ~line 1394), grouped per function into components (Harness_wires, Wire_feed, Wire_neg), tinted appearances (tint())

## Next Single Step
- [NEXT] B (enclcheck plan): new enclosure/v2c/src/harness_paths_v2c.py = ONE path table (JSON in the run: wire ID -> polyline + OD + colour) from harness/enclosure-wire-list.csv (111 rows) + pin positions (A J3 / A J6 / B J6 / B J7 pads from the .kicad_pcb via W(); IN J1 / J2 Molex pins; X1 HD34-24-21SN / X2 HDP24-24-47SE cavities from the vendor STEPs; T5-T8 lugs = T58; splices SP1-4 at X2 rear; fans via the 8183K5 gland) along the existing ribbon / USB lanes in build_v2c.py lines 708-737; OD per WP in harness/src/enclosure_harness.py (GXL16 2.80, GXL12 3.65, M22759/16-20 1.52; GH28 OD TBD -> state the assumption); USB = 4 round 4.0 cables
- [NEXT] B: build_v2c.py: replace made("wire-ribbons" CPDM-HAR-202) / ("usb-cables" CPDM-HAR-203) / HAR-201 by one subassembly CPDM-HAR-200 with one tube() solid per wire named by wire ID, coloured per list; bomcheck / clearance (wire-plastic OK) / access / asm_drawing pick() names updated; model-length column vs list (flag TBD or > 10 %), lengths into the PR body only
- [NEXT] B: fusion_v2c.py: harness design built natively (pipe along 3D sketch polylines from the same JSON, one body per wire ID) instead of the STEP upload; extend compare_tree; hold the Fusion lock; then publish revE (rename models top folder to -revE, keep revD, delete revC after the hash check), deliverable_lock, README / PR body; clear %TEMP%\cadfetch and ~/scratch/cadfetch, ~/scratch/encl-v2c-revD

## Pointers
- Branch_States: none
- Backlog: BACKLOG.md
- Latest_ADR: ADR-2026-11-20-presim
