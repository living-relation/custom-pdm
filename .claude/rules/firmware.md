# Firmware

Enforcer: the AGENTS.md firmware checks (builds, s0, s1, s3, Renode); s0 board audit; none yet for the rest.

- Board folders are generated: change `firmware/tools_custom/port_boards.py`, re-run it, never hand-edit `firmware/boards/custompdm_*`.
- Custom features live behind custom options (e.g. `PRO_FEATURES`) so stock builds stay byte-identical: check the stock `dingopdm_v7` .bin md5 against main on every firmware change.
- CONFIG_VERSION: the high byte counts our param layout, the low byte is upstream's; bump it only when the layout changes; saved configs then fall back to defaults (the tool must Write All).
- Build from an LF `git archive` of a committed branch (Windows checkout is CRLF); WSL builds in your own scratch folder, never in `~/renode-pdm/src` or the shared `/home/daniel/scratch/ui-sim`; `make clean` between boards in one folder; start WSL jobs from an LF `.sh` file (Never do: `Start-Process wsl ... bash -c "..."` dropped the arguments, 2026-11-15).
- After any firmware merge, rebuild the shared UI sim `.so` (`/home/daniel/scratch/ui-sim/so`) from main when no job uses it.
- Do not flash anything: no hardware exists yet. Renode does not emulate STOP: EXTI wake from sleep stays untested in Renode.
- Every firmware feature or setting is checked against the dingo UI (dingoConfig; docs at corygrant/dingoElec): shown / editable, or the UI change it needs (Dan, 2026-11-14).
- Never do: assume a stock default (the stock overcurrent retry is None, not "3 tries"); quote a timing measured with identical message timing in every case (the power-up ON pulse first read 4 ms).
- Watchdog (MCU_SAFETY, `core/safety.h`): every essential thread calls `SAFETY_CHECKIN(<task>)` once per loop and no loop may block longer than half the shortest run timeout (500 ms); a new thread either checks in (add it to `SafetyTask`) or is shown to be non-essential; s0 / s1 / s3 report the longest refresh gap and fail on any watchdog reset (2026-11-20).
- Sim plants (firmware/sim, Renode models) use data-sheet values (kILIS, thresholds, timings), never copies of firmware constants: a copied 5950 kILIS let a 9 % error pass s0 (2026-11-20).
- ECU loss: a load the ECU controls stays ECU-commanded and goes OFF at ECU loss and at key off; EPS is never held on; no fan or other load is held on at ECU loss (Dan, 2026-11-23 07:00; ADR-2026-11-23-ecu-loss).
- ECU power hold: the ECU keeps control of what it controls (its main relay is held after key off for the electronic throttle body); an ECU-held feed follows only the ECU hold signal, never ignition, PDM timers, sleep or load shed, and the ECU going quiet at the end of its hold is not a fault (Dan, 2026-11-23 07:10; ADR-2026-11-23-ecu-power-hold).
- ECU loads stay off the PDM: the fuel pump, power steering pump (EPS), radiator and condenser fans, heater, A/C, electronic throttle body, electronic throttle pedal, boost solenoid, injectors and coils are CONTROLLED AND POWERED by the ECU (its own relays and outputs); no car config, preset or sim puts them on a PDM output (Dan, 2026-11-23 07:44; ADR-2026-11-23-ecu-loads).
- Never guess Link ECU CAN values: the CAN docs / rules and a partial map are in Dan's center-cluster-esp32-p4, realdash-dashboard-builder and st185-link-ecu-config repos (read only); any ECU <-> PDM CAN config here is marked DUMMY / DEMO / TEST ONLY (file name or line 1, and where the UI / docs show it) until Dan confirms it (Dan, 2026-11-23 07:04; ADR-2026-11-23-link-can-dummy).
