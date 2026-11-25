# PDM-2A plan (2 x board A, no board B) - SHELVED, not built

Status: **shelved by Dan, 2026-11-24.** Nothing below was built; no `pdm-2a/` folder exists. Kept on record at Dan's
request (2026-11-25). The 3-board PDM is unchanged.

## Why it was shelved
- One board of each type costs about the same as two (the assemblers' MOQ is 2), so dropping board B saves little
  (Dan, 2026-11-24). Cheaper routes for the 3-board PDM are in `docs/assembly-options.md`.
- **The plan's output sizing was wrong.** It sized outputs from estimated running current. Dan's fuse boxes are sized
  from each device's peak and inrush current, so the fuse rating is the sizing number
  (st185-link-ecu-config `sot/fuse-relay-map.csv`, read only). By that rule 7.5 A board A outputs cannot carry:

  | Circuit | Fuse | 7.5 A output |
  |---|---|---|
  | Low beams (both lamps) | HL 15 A | no |
  | High beams (both lamps) | HR 15 A | no |
  | Horn / hazard | HZ 15 A | no |
  | CAN-Lambda | LAM 10 A (Link guide) | no |
  | Tail | OEM TAIL 15 A | no |
  | Pop-up retract | RTR 30 A | no |
  | DRL, CSB3, cluster, Pi, alarm IG | 7.5 / 5 / 5 / 5 / 2 A | yes |

  So 2 x A cannot replace the custom boxes; the heavy circuits need board B's 15 A / 31 A outputs.
- Data found before shelving (not proof; measure on the car before relying on it): HWSTAR publishes no H6054 current;
  the Link CAN-Lambda manual gives heater 8 A max, controller 100 mA (`link-can-lambda-manual.pdf` p.5), not the "8.1 A"
  in the notes; no pop-up motor current is published. BTS7008-2EPA overload trip is 65-99 A;
  board A current sense reads full scale near 11.2 A (`docs/feature-parity.md`).

## Open item this raised for the 3-board PDM
The 3-board car setup (`docs/st185-car-config.dummy.md`) puts the low beams, high beams and horn (15 A fuses) on A1
and each pop-up motor (RTR 30 A) on A2 OUT4 / OUT5, all 7.5 A outputs. Logged in BACKLOG. Done 2026-11-25 (fusesize):
the car map now puts every circuit on an output rated for its fuse (board B 15 A / 31 A outputs, board A pairs for the
10 A circuits); stop / back-up lamps, wipers and washer stay on their OEM switches (`docs/st185-car-config.dummy.md`).

## The plan as approved on 2026-11-24 (unchanged below this line)

### Plan: "PDM-2A" - a second, fully independent product (2 x board A + 2 x input board, no board B)

## Context
Dan wants a cheaper PDM alongside the 3-board one: two finished products at two price levels.
- The ST185 circuit study found 15 PDM-worthy circuits. The two over 7.5 A (rear defogger about 15 A, windows 10-20 A) stay on their OEM relays (c11).
  The other 13 run at an estimated 0.5-6 A each and fit 16 x 7.5 A outputs with 3 spare.
  The "15 A" figures are today's fuse sizes, not load currents.
- Unproven against 7.5 A (J0 gate, before any copy work):
  - **Low beams** and **high beams:** each pair of lamps is on one output. The lamp current is not in either repo. Halogen 55 / 65 W would be about 9-11 A per pair, which is over the rating; if so, split them into four outputs (L / R) and use the spares.
  - **CAN-Lambda:** 8.1 A cold peak.
  - **Pop-up motors:** stall current.
  - Get each from the maker data. Over 7.5 A running means an extra output, or the load stays on its relay.
- Board B is 45-52 % of the cost.
- Dan's rules (2026-11-24):
  - The 3-board design and its documents are never modified.
  - The 2A version is a full duplicate in its own section, clearly marked.
  - Nothing in either version depends on the other: each can change completely on its own.
- c11 = a: the windows and defogger stay on their OEM relays.
- c12 = a: the same enclosure envelope, with the B bay empty.

## Isolation rules (apply to every job)
- **One section:** everything lives in `pdm-2a/` at the repo root. Its own `pdm-2a/AGENTS.md` router, `2A-DECISIONS.md`, `2A-README.md`, `VERIFIED-2A.lock`.
- **Copies, not references:**
  - Every source the 2A version needs is copied into `pdm-2a/` at the fork commit: board A, input board, `tools/` generators, firmware tree, sims, Renode bench, UI, enclosure, harness, heat model and docs.
  - No 2A script imports, reads or runs a path outside `pdm-2a/`.
  - ChibiOS is not committed, so the 2A firmware fetches its own copy into `pdm-2a/firmware/`.
- **Marking (impossible to mix up):**
  - Every 2A file gets the `2A-` prefix where the name is free to choose.
  - Every text file has a line-1 banner: `PDM-2A (2 x board A + 2 x input, no board B) - NOT the 3-board PDM`.
  - Generated files carry `variant: PDM-2A`.
  - Firmware board targets are renamed `pdm2a_a` (units 1 / 2) and `pdm2a_input`. The DBC files are `pdm2a_A1_0x500.dbc` etc.
  - The UI title bar and every page header read "PDM-2A (2 boards)".
  - The models folder is `custom-pdm-2a-enclosure-revA\revA\`.
  - Folder names avoid `-vN` / `-revN` (the REV_DIR check).
- **Allowed shared touches (repo plumbing, not design):**
  - the root `automation.yml` gets new `2a-*` entries only;
  - the root `AGENTS.md` gets one pointer line to `pdm-2a/AGENTS.md`;
  - the root STATE / BACKLOG / DECISIONS get `[2A]`-tagged lines through the coordinator.
  - No existing line in any of these is changed.
- **Enforcer:** `pdm-2a/tools/2A-isolation-check.py`, registered in `automation.yml` and run in every 2A job before commit.
  - (a) It fails if any file in `pdm-2a/` references a path outside it (except git / CI plumbing).
  - (b) It fails if the branch diff touches any file outside `pdm-2a/` other than the allow-list above, or changes an existing line of those files.
  - (c) It fails if any non-`pdm-2a` file references `pdm-2a/`.
  - Each 2A rule also goes into `pdm-2a/.claude-rules/2A-isolation.md`. That file is read by the 2A router only, not by the root rules.

## Jobs (each its own worktree, branch and PR, per git-and-prs.md; merged in order J0 → J5, with J2-J4 in parallel after J1)

### J0 - Scaffold
- Create `pdm-2a/` with its router, decisions, README (16 outputs / 14 digital + 2 analog inputs), the isolation check, and the rules file.
- Record ADR-2026-11-24-pdm-2a (root DECISIONS pointer plus `2A-DECISIONS.md` in full).

### J1 - Hardware copy
- Copy `hardware/board-a`, `hardware/input-board` and every `tools/` generator and check they use into `pdm-2a/hardware/` and `pdm-2a/tools/`. Rewrite the paths inside the copies.
- Proof at the fork: the copied `.kicad_pcb` / `.kicad_sch` are byte-identical to the originals (the fab diff is zero). After that they are free to diverge.
- Write the 2A fab pack in `pdm-2a/hardware/fab/`: quantities 2 x A and 2 x input, with a 2A fab README. Run DRC / ERC, parity, the hole check and verify_copper inside the copy.
- The pinout stays the same (hardware.md: no pin changes without proof).

### J2 - Firmware copy
- Copy the tracked firmware tree into `pdm-2a/firmware/`. Write a 2A `port_boards.py` that emits `pdm2a_a` only.
- Move board B's car-level logic to A1, under 2A-DECISIONS:
  - battery load shed;
  - ECU hold follower (ADR ecu-power-hold rules carried over);
  - auto sleep.
- New 2A fan logic: A2 fan output from A1 + A2 temperatures only (today it also listens to B over CAN).
- Write the 2A sims: `2A-s0`, `2A-s1`, `2A-s3`, `2A-s4`, `2A-s5` and the Renode bench, with their own expected counts. Include an s4 case for "no B frames on the bus".
- 2A build script `pdm-2a/firmware/sim/renode/2A-build_wsl.sh`, built from a `git archive` of the 2A branch path.

### J3 - UI copy (a full separate app)
- Copy `ui/` into `pdm-2a/ui/`. Re-title it, and give it its own solution name and namespace prefix (`CustomPdm2A`). It runs on port 5002 with bridge port 3335, so Dan's 3-board app on 5000 / 3333 is untouched.
- Changes in the copy:
  - **Board table:** one 2-board table `Pdm2ABoards` (A1 0x500, A2 0x540) replaces `PdmFactoryDefaults.Boards`, `PdmOps.Roles` and `DbcExport.RepoBoards`. B code paths are deleted: B presets, B ratings, B fan remotes, B thermal offsets.
  - **PdmView:** OUT1-16, IN1-14, analog IN15 / IN16 (compacted). The "No board B" problem is removed. A problem is added when a type-15 board is seen ("this is a PDM-2A project"). All "1-24" texts come from the table.
  - **PdmStarter / New PDM:** 2 boards. Texts name A1 and A2.
  - **Project file:** writes `"product": "PDM-2A"`. It refuses to open a file without that marker, and the 3-board app is not changed.
  - **New 2A ST185 starter and car builder:** `2A-st185-starter.json` and `St185Car2A.cs`, with the 15-circuit plan, no ECU loads, and the ECU-load preset block.
  - **Fixes carried in from the review:** the FunctionsPanel `"B"` default goes through `RoleOr`; whole-PDM problem list at the top of `/pdm`; save state on `/pdm`.
  - **Fan panel:** A1 / A2 temperatures only.
- **DBC:** a 2A DbcGen writes `pdm-2a/firmware/dbc/pdm2a_*.dbc` plus `pdm2a_PDM.dbc`.
- **Tests:** copy `CustomPdm.Tests` to `pdm-2a/ui/tests/CustomPdm2A.Tests`. Adapt the layout tests to 2 boards, and add bUnit tests for the New PDM, view numbering and the product marker. Live sim tests run under `[Collection("sim")]` against a 2-board bridge.
- **Launcher:** `pdm-2a/ui/2A-Start-PdmUi.ps1` (A `.so` files only). The 2A sim bridge copy has `BOARDS = {A1, A2}`.

### J4 - Enclosure, harness and heat (same envelope, empty B bay)
- Copy `enclosure/v2c` into `pdm-2a/enclosure/v2c/`, `harness/` into `pdm-2a/harness/`, and `sim/heat` + `tools/thermal_*` + `verify_thermal_box.py` into `pdm-2a/sim/` and `pdm-2a/tools/`. Use a separate scratch (`SCR=~/scratch/encl-2a`).
- Make the 2A model:
  - remove board B, its studs and its harness branches;
  - move the BATT / GND bar landing from B's M6 terminals to A1 / A2;
  - redo the X1 / X2 cavity map for 15 circuits plus feeds.
- Rebuild the F1 (Sunon side fans) and F2 (spiral-fin sink + concave flow cone + 1 x Noctua NF-A6x15 bottom fan) variants in the current revF-level model. F2 has never been run in the revF model.
- **Heat cases (Elmer revF method, 60 C air, gap pad k 1 / 3 / 6):** the 2A car loads, a rating case (16 x 7.5 A worst), the feed split over A1 / A2, and the drive cycle.

  | Case | Fans |
  |---|---|
  | F1 | 2 fans |
  | F1 | 1 fan |
  | F1 | no fan (wall and flat) |
  | F2 | Noctua on |
  | F2 | Noctua off |
  | No-fan sink | fanless option |

  - Pass limits as in `heat-analysis.md` section 1: Tj 150, laminate 130, MCU 105, FRAM 125, 5 V module 122.4, fan 70 C, firmware cut 98 / 104.
  - Re-derive `R_SYS_A` and re-run `thermal_a.py` and `verify_thermal_box.py` (A-only).
  - Then run the Fusion thermal cross-check, under the single-Fusion-driver rule.
- **Pick rule (log as a default in 2A-DECISIONS):** the fewest fans that pass every case with at least 10 K margin at k 3 and pass fans-off at k 6. F2 is preferred if it passes, as Dan wants.
- Run the full build checks in the copy: overlap, lugcheck, bomcheck, access, wirecheck, mass, CNC and the Fusion-vs-STEP tree check. Publish to `custom-pdm-2a-enclosure-revA\revA\` and record it in `VERIFIED-2A.lock`.

### J5 - 2A docs and order pack
- Write twins (`pdm-2a/docs/2A-*.md`) of:
  - order-readiness, order-checklist and assembly-options (re-quoted for the Spark / NextPCB / JLCPCB routes on the 2A set);
  - parts-audit, box-connectors, firmware-pin-map, the car config, feature-parity, system-verification, heat-analysis, enclosure, the harness cost study and the confidence report.
- Write the 2A order gates, mirroring ADR-order-gates.

## Verification (2A only, run inside pdm-2a/)
- `2A-isolation-check.py` passes on every PR, and `git diff main --stat` outside `pdm-2a/` shows only the allow-list.
- The original suite still passes unchanged on main (3-board s0 / s1 / s3 / s4 counts, UI tests, `VERIFIED.lock` hashes).
- **Hardware:** the 2A fab pack builds; DRC / ERC / parity / hole check pass.
- **Firmware:** the 2A builds pass, the 2A sims pass with their new expected counts, the Renode bench passes, and the stock `dingopdm_v7` md5 is unchanged.
- **UI:** `dotnet test pdm-2a/ui/tests/CustomPdm2A.Tests` (unit + live 2-board sim); manual run on http://localhost:5002/pdm.
- **Heat:** every case in the table with numbers in `2A-heat-analysis.md`, plus the Fusion cross-check.
- **Enclosure:** every build check passes; the release is hash-locked.

## Still open (unchanged)
- c7 (3-board order route) stays open; the 2A version gets its own order go / no-go after J5.
