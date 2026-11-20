# dingoConfig route B plan: one combined PDM page

Status: B1-B5 done (PRs #71-#84), editor phases in progress (memory-store STATE, AGENTS.md role table); what is built: `ui/README.md`. Decisions behind it: `DECISIONS.md` K1a (2026-11-14) and k2b, k3a, k4a (2026-11-15).

Goal: the three boards (A1, A2, B) look like one PDM in `ui/dingoConfig/`: 24 outputs in one grid, all inputs in one grid, one set of buttons.

## What the code gives us (read 2026-11-15, `ui/dingoConfig` @ main a1dc6aa)
- Pages are Blazor routes (`@page`): `/devices`, `/device/{id}`, `/plot`, `/can-log`, `/system-log`. A new page is one new `.razor` file plus a menu entry in `web/Components/Layout/NavMenu.razor`.
- `DeviceManager.GetDevicesByType<T>()` already returns every device in the project, so a page can hold all three boards at once.
- Every settings grid (`web/Components/Devices/FwDevice/Functions/*Grid.razor`) takes exactly one `Device`. `OutputsGrid` and `DigitalInputsGrid` list one board's rows; sorting is switched off.
- The variable picker (`VarMapSelectionDialog`) only lists the variables of the one device it is opened for. An output on board B cannot pick an input on board A; today that link is made by hand with a CAN output on one board and a CAN input on the other (32 of each per board).
- Read All / Write All / Burn are per device (`DeviceManager.ReadAllDeviceConfig(id)` etc.). Route A's "Read All first" guard is per device.

## Phases (each is one PR; each leaves the per-board pages working)
| Phase | What Dan gets | Needs firmware | Size |
|---|---|---|---|
| B1 | New page "PDM": live view only. 24 outputs in one grid (board, pad / connector pin, name, state, current, reset count), all 24 digital + 3 analog inputs, the three board temperatures and thermal flags side by side. | No | Small |
| B2 | The same grids become editable (enable, name, current / inrush limits, reset mode; input mode, pull, invert, debounce). One Read All / Write All / Burn for all three boards, with the route A guard (no write before a good read of every board). | No | Medium |
| B3 | Linked settings set once for the PDM: temperature limits on all three boards, fan on / off thresholds (6 params that must move together, PR #60), base IDs, and a "new PDM" project with our factory defaults instead of stock ones. | No | Medium |
| B4 | Cross-board picking: choose any input of the PDM as the trigger of any output; the tool creates the CAN output / CAN input pair on the two boards and shows the slots used. | No (uses stock CAN inputs / outputs); slot limits apply | Large |
| B5 | DBC export for the ECU with msg 37 and the msg 3 flags (done, PR #81). | No | Small |

"Needs firmware: No" comes from reading the code, not from a build. Each phase starts by proving it against the sim (`ui/tests/sim_bridge.py`) before any UI work.

## Risks
- B2: three boards written one after another; a failure half way leaves boards on different settings. The page must show per-board result and never auto-burn.
- B4: the firmware side of a cross-board link is stock, but slot allocation (which CAN input / output numbers are free, fan logic already uses A2 CAN inputs 24-27) is new logic and the biggest test job. Link loss behaviour per channel (hold / off / on, `firmware/sim/RESULTS.md`) must be shown next to each link.
- Upstream merges: every stock file we change makes later dingoConfig updates harder. New pages and components go in new files under `web/Components/CustomPdm/`; stock grids are reused by parameter, not edited, where possible.

## Tests
Same pattern as route A: C# tests in `ui/tests/CustomPdm.Tests`, live ones through the sim bridge with all three boards, one-line mutations to prove each test can fail, then a browser check.
