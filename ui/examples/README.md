DUMMY STARTER - not a source of truth and not car data; built by hand in the /pdm UI on the simulated boards (uiwalk job, 2026-11-21) from `docs/car-loads.dummy.md`, itself a dummy copy of st185-link-ecu-config @ 1bf9f527 (read only; Dan approves any use).

# ui/examples

- `st185-starter.json`: a dingoConfig project file (A1 0x500, A2 0x540, B 0x580, 1000K) to start a car setup from. Open it with the "Load the ST185 starter" button on the empty /pdm page (it loads like a New PDM, so Write All works), or with File > Open (then it counts as "not read": Read All comes first).
- Outputs: B OUT1 radiator fan (on at 92, off at 88 from the CAN value "ECU coolant", 0x3F5 bytes 0-1 x 0.1), B OUT2 condenser fan and B OUT3 fuel pump (ECU frame 0x3F4 byte 1 / byte 0; at loss fan on, pump off), B OUT5 CAN-Lambda, B OUT6 A/C clutch (keypad 0x28 button 1), B OUT7 / OUT8 wiper slow / fast, A1 OUT1 / OUT2 low / high beams (high = IN2 AND IN1), A1 OUT5 horn, A1 OUT7 / OUT8 switchboard / cluster (ignition; cluster off-delay 5 s), A2 OUT1 / OUT3 turn left / right with hazard.
- Inputs: IN15 ignition, IN16-19 wiper slow / fast / park cam / intermittent, IN1 head, IN2 high, IN5 horn (pull-up, inverted), IN8-10 turn left / right / hazard.
- Limits and inrush come from the device presets (`ui/README.md` table); the CAN IDs, bytes and temperatures are examples, not the Link ECU's real setup (that is not finished: `.claude/rules/other-repos.md`).
- Test: `UiWalkTests` loads the file, checks that its critical settings equal New PDM's factory settings and that the functions above read back in words.
- Changing it: load it in the app, edit, Save As over this file, run the tests.

## st185-car.json (the ST185 install config)

DUMMY COPY of the car facts: st185-link-ecu-config @ 839be705 (read only; nothing written there). It is the install config Dan approved (c4 = a, 2026-11-23), not an example.

- Built, not hand-made: `St185Car` in `ui/tests/CustomPdm.Tests/St185CarTests.cs` (the car map) sets it up on a New PDM with the /pdm domain code; `$env:CUSTOMPDM_WRITE_CAR_CONFIG='1'; dotnet test ui\tests\CustomPdm.Tests --filter St185CarTests` writes the file, and without the variable the test checks the file is still exactly what the map builds.
- Open it with "Load the ST185 car config" on the empty /pdm page (loaded like a New PDM and the starter: writable, critical settings proven equal to the factory ones).
- The full map in words, the TO CONFIRM list (the ECU frame 0x3F4 is a placeholder) and the install steps: `docs/st185-car-config.md`.
- Tests: `St185CarTests`, `St185CarButtonTests` (bUnit), `St185CarLiveSimTests` (Write All + Burn + power cycle + Read All on the sim boards gives back every function in words; key on, ECU frame and ECU loss on the output pins).
