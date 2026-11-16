# ui - PC configuration tool

`dingoConfig/` is upstream dingoConfig (MIT, licence in `dingoConfig/LICENSE`), copied in the same way dingoFW lives in `firmware/` (DECISIONS 2026-11-10 B2a, K1a route A). Nothing goes upstream.

- Upstream: https://github.com/corygrant/dingoConfig, branch `development`, commit `01134ad057dee5c69788ccfecf63420740e932bc` (2026-10-26, "bump version"). It matches our firmware's dingoFW `development` @ 14084e9.
- Import commit: unmodified copy (tree hash equal to upstream `e9202a9`). Our changes are separate commits on top, so `git diff <import commit> -- ui/dingoConfig` shows all of them.
- Build output (`bin/`, `obj/`) is git-ignored.

## Our changes (route A)
- Device types 14 (board A) and 15 (board B): `dingoConfig/web/Definitions/device-definitions.json` plus `custompdm-a-signals.json` / `custompdm-b-signals.json` (cyclic layout of `firmware/boards/custompdm_*/msg.cpp`).
- Param block 0x7F00 (temperature limits, critical-exempt outputs, critical-soon margin, wake inputs): `dingoConfig/domain/CustomPdm/CustomPdmSettings.cs`, hooked into `FwDevice` for types 14 / 15 only. Shown on the device Configuration tab (Device panel); die temperature and the thermal flags on the device status (Dashboard) tab. Wake inputs on a shared line / the USB line are greyed out. For types 14 / 15, Read / Write Modified are off and Write All needs a successful Read All first (a new project holds stock dingoPDM defaults, not our factory defaults; A2 could otherwise be written with A1's ID).
- Route B phase B1 (`docs/ui-route-b-plan.md`): page `/pdm` (menu entry PDM), a read-only live view of the three boards as one PDM: `dingoConfig/domain/CustomPdm/PdmView.cs` (roles, numbering, connector pins from `docs/box-connectors.md`) and `dingoConfig/web/Components/CustomPdm/PdmPage.razor`. Board roles: the two type 14 devices by base ID are A1 then A2; the type 15 device is B.
- Route B phase B2: `/pdm` is editable (outputs: enable, name, current / inrush limit, inrush time, reset mode, reset count limit, reset time; digital inputs: enable, name, mode, pull, invert, debounce; stock limits) and has ONE Read All / Write All / Burn for the three boards: `dingoConfig/domain/CustomPdm/PdmOps.cs` (boards one after another, each waits for the board's own result; Write All and Burn refused unless A1, A2 and B are in the project, connected and read; Write All and Burn stop at the first failure, Read All goes on past a failed board, and every board keeps its result line; Burn only from its own button, after a fresh config check of all three) and `dingoConfig/application/Services/PdmOpsService.cs`. Stock edits for it: `DeviceManager.CheckConfig` public, one service line in `web/Program.cs`.
- Route B phase B3: `/pdm` "PDM settings" panel (`dingoConfig/web/Components/CustomPdm/PdmSettingsPanel.razor`, logic `dingoConfig/domain/CustomPdm/PdmLinked.cs`): temperature warn / critical / recovery / critical-soon margin set once for A1, A2, B (shows when the boards differ); fan on / off set once, written into the 6 A2 params that hold them (conditions 27-28, CAN inputs 25-28 operands; off below on, 0-125 C; left alone if A2's fan logic was changed by hand); base IDs with checks (range, no block overlap, A1 below A2) and Move = the stock Modify message (board moves at once, A2's fan CAN inputs follow A1 / B; then Write All and Burn). "New PDM" button on `/pdm` when no board is in the project (the menu entry PDM is always shown): A1, A2, B with our firmware's factory defaults (`dingoConfig/domain/CustomPdm/PdmFactoryDefaults.cs`, `PdmNewProject.razor`; proven equal to fresh boards param by param in the sim tests), so its Write All needs no Read All first (it replaces what the boards hold). Stock edits: `FwDevice.MaxCyclicId` follows a BaseId change (a device moved to a higher ID heard nothing), NavMenu entry always shown.
- Route B phase B5: DBC files for the ECU from ONE generator, `dingoConfig/domain/CustomPdm/DbcExport.cs` (source: the cyclic signals the app decodes, checked against `firmware/boards/custompdm_*/msg.cpp`). `dotnet run --project ui\tools\DbcGen` writes `firmware/dbc/custompdm_A1_0x500.dbc`, `_A2_0x540`, `_B_0x580` and `custompdm_PDM.dbc` (all three; `-- --check` compares only); the /pdm "Export DBC" button downloads one file with the boards of the project at their own base IDs (`web/Components/CustomPdm/DbcExportButton.razor`, `web/wwwroot/js/custompdm/download.js`). Signal names carry the board (`A1_Output1_Current`); msg 3 byte 7 is three flag bits; keypad msgs 24-26 are left out (the app does not decode them). A test keeps the committed files equal to the generator.
- Tests: `tests/CustomPdm.Tests` (C#). The live ones talk to the host simulation of our firmware through `tests/sim_bridge.py`.

## Run on DansPC (PowerShell, repo root)
Build and start the app (then open the address it prints):

    dotnet build ui\dingoConfig\dingoConfig.sln
    dotnet run --project ui\dingoConfig\web\web.csproj

Build the firmware host sim once (WSL), from a committed branch:

    wsl -e bash -c 'S=~/scratch/ui-sim; rm -rf $S; mkdir -p $S/src $S/so; cd /mnt/c/projects/active/custom-pdm; git archive main firmware | tar -x -C $S/src; cd $S/src/firmware; for u in 1 2; do bash sim/build.sh custompdm_a $S/so $u; done; bash sim/build.sh custompdm_b $S/so 1'

Tests (without `CUSTOMPDM_SIM_SO` the live ones are reported as Skipped):

    dotnet test ui\tests\CustomPdm.Tests
    $env:CUSTOMPDM_SIM_SO='/home/daniel/scratch/ui-sim/so'; dotnet test ui\tests\CustomPdm.Tests

Use the app with the simulated boards (A1 0x500, A2 0x540, B 0x580, 1000K): start the bridge, then in dingoConfig pick adapter "SLCAN TCP", port `localhost:3333`, bit rate 1000K, add the three devices (types "custom-pdm A" / "custom-pdm B"), and press Read All before any write (a new project's defaults are stock dingoPDM ones, not our factory defaults). The real-time sim is slower than a board: one Write All takes 40 to 55 s per board through the bridge (about 39 s on 2026-11-16). The /pdm Write All has no fixed wait: per board, it restarts on every frame the PC sends to that board and every config reply from it, fails "no reply (no answer for 10 s while writing)" 10 s after the last one, and gives up at 5 min per board ("write not confirmed in 5 min"):

    wsl -e python3 /mnt/c/projects/active/custom-pdm/ui/tests/sim_bridge.py /home/daniel/scratch/ui-sim/so --slcan-tcp 3333
