DUMMY COPY of the car facts - DUMMY / DEMO / TEST ONLY - source: st185-link-ecu-config @ a0490839 (`sot/fuse-relay-map.csv`, `sot/channels.csv`, `docs/harness/circuit-plan.md`, `docs/harness/README.md`, `CAN-BUS-ID-ALLOCATION-TABLE.md`, `CAN-BUS-MASTER-DESIGN.md`, `docs/devices/SENSOR-AND-ACTUATOR-REFERENCE.md`) and st185-celica-repair-manual @ 66b0f72 (1992 EWD power source and headlight pages); both read only, nothing written there.

# ST185 car config (full-PDM demo, carsim 2026-11-23)

What this is: Dan's brief (2026-11-23): "my car wiring was based on NO PDM; pretend I WANT a PDM now". The config
`ui/examples/st185-car.dummy.json` puts every load of the car's fuse / relay boxes (st185 POWER box B1, LOGIC box B2,
trunk block B3, the kept OEM boxes J/B No.1, R/B No.2, R/B No.4 and the retract relay R8) on the PDM, except what the
ECU controls and powers. It is built by `ui/tests/CustomPdm.Tests/St185Car.cs`; `St185CarTests` keep the file, the map
and the tables below the same. It is a demo / test config: nothing is confirmed on the car. The PDM is unproven until
the PCBs are made.

In plain words:
- 20 car loads on 20 outputs; 3 outputs spare (A1 OUT6 7.5 A, B OUT2 / OUT3 31 A); A2 OUT2 runs the box fans.
- The ECU (Link G4X) keeps controlling AND powering its own loads through its own relays (Dan 2026-11-23 07:44):
  fuel pump, power steering pump, radiator and condenser fans, heater, A/C, ETB, throttle pedal, boost solenoid,
  injectors, coils. The PDM gets no command from the ECU, so no ECU CAN frame is needed.
- The EFI main relay K-EFI stays a relay: the ECU powers itself with it and parks the electronic throttle after the
  key is off (ECU Hold Power on Aux 6 with the ignition sense on DI 9, `sot/channels.csv` a28 / b28). What K-EFI's
  Bus 2 fed and the PDM now feeds (DRLs, CSB3, cluster) follows A1 IN5 = the K-EFI output, never the ignition and
  never a PDM timer. So during the ECU's after-run those stay on, and they go off when the ECU lets go.
- Auto sleep: each board mutes its CAN 10 s after IN5 (ECU hold), IN7 (tail switch) and IN9 (hazard switch) are all
  off, and sleeps 30 s after the bus is quiet. Wake: the ignition, EFI main, brake, tail, flash and hazard inputs.
- Every limit is a device preset, at or under both the output rating and the fuse that protects that wire today.

## Outputs

PDM numbers: 1-8 = A1 OUT1-8, 9-16 = A2 OUT1-8, 17-24 = B OUT1-8. Connector: `docs/box-connectors.md`.

| # | Board output | Connector | Load | Preset | Limit / inrush | Trigger | Replaces | Current (steady, source) |
|---|---|---|---|---|---|---|---|---|
| 1 | A1 OUT1 | X1-H | Low beams | LED lamp | 5 A / 15 A 100 ms | IN1 (head / flash) | K-HL relay (LOGIC M1) + HL 15 A | 2.0 A (presim CAR_LOADS) |
| 2 | A1 OUT2 | X1-J | High beams | LED lamp | 5 A / 15 A 100 ms | IN2 AND IN1 | K-HR relay (LOGIC M2) + HR 15 A | 2.5 A (CAR_LOADS) |
| 3 | A1 OUT3 | X1-K | DRLs | LED lamp | 5 A / 15 A 100 ms | IN3 AND IN5 AND NOT IN1 | K-DRL (LOGIC M8) + RLY-DRL (B5) + DRL 7.5 A | 0.5 A (st185 A34) |
| 4 | A1 OUT4 | X1-L | Stop lamps | Lamp (halogen) | 7.5 A / 75 A 100 ms | IN6 (brake switch) | J/B No.1 STOP 15 A | 4.4 A (ASSUMED 2 x 21 W + 18 W) |
| 5 | A1 OUT5 | X1-M | Horns | Horn | 7.5 A / 22.5 A 200 ms | IN4 | K-HORN (LOGIC M3) | 5.0 A (CAR_LOADS) |
| 7 | A1 OUT7 | X1-P | CSB3 switchboard | ECU / module feed | 5 A / 10 A 100 ms | IN5 (EFI main) | CSB 5 A (Bus 2) | 2.0 A (ASSUMED) |
| 8 | A1 OUT8 | X1-R | Centre cluster | ECU / module feed | 5 A / 10 A 100 ms | IN5 (EFI main) | DEV 5 A (Bus 2) | 1.5 A (ASSUMED) |
| 9 | A2 OUT1 | X1-S | Turn left | Lamp | 7.5 A / 75 A 100 ms | turn signals: IN8 or hazard IN9, 350 / 350 ms | OEM flasher, TURN 10 A, HZ 15 A | 3.3 A (ASSUMED) |
| 11 | A2 OUT3 | X1-U | Turn right | Lamp | 7.5 A / 75 A 100 ms | turn signals: IN10 or hazard IN9 | OEM flasher, TURN 10 A, HZ 15 A | 3.3 A (ASSUMED) |
| 12 | A2 OUT4 | X1-V | Pop-up LH | Motor | 7.5 A / 30 A 500 ms | pop-ups (below), limits IN11 / IN12 | retract relay R8 + RTR 30 A + K-POD + D1 / D2 | 5 A (ASSUMED) |
| 13 | A2 OUT5 | X1-W | Pop-up RH | Motor | 7.5 A / 30 A 500 ms | pop-ups (below), limits IN13 / IN14 | same | 5 A (ASSUMED) |
| 14 | A2 OUT6 | X1-X | Tail / park front | Lamp | 7.5 A / 75 A 100 ms | IN7 (over CAN, holds at loss) | taillight relay + TAIL 15 A | 1.3 A (ASSUMED) |
| 15 | A2 OUT7 | X1-A | Tail / licence / dash lights | Lamp | 7.5 A / 75 A 100 ms | IN7 (over CAN, holds at loss) | taillight relay + TAIL 15 A | 3.5 A (ASSUMED) |
| 16 | A2 OUT8 | X1-C | Washer pump | Motor | 7.5 A / 30 A 500 ms | IN21 (over CAN, off at loss) | washer switch, WIPER 20 A | 3.0 A (CAR_LOADS) |
| 17 | B OUT1 | Stud OUT1 | Power windows | Motor, limit raised | 25 A / 60 A 500 ms | IN16 (ignition) | R/B No.2 power main relay | about 10 A, 20 A stalled (ASSUMED) |
| 20 | B OUT4 | Stud OUT4 | Rear defogger | Heater, limit lowered | 20 A / 30 A 500 ms | IN22 (push on / off) AND IN16 AND NOT battery shed | defogger relay + DEFOGGER 30 A | 15 A (ASSUMED, about 200 W) |
| 21 | B OUT5 | X1-B | CAN-Lambda | Heater, limit lowered | 10 A / 15 A 500 ms | IN16 (ignition) | K-ON (LOGIC M7) + LAM 10 A | 8.1 A (CAR_LOADS) |
| 22 | B OUT6 | X1-D | Back-up lamps | Lamp | 15 A / 100 A 100 ms | IN24 (reverse switch) | back-up switch on GAUGE 15 A | 3.2 A (ASSUMED 2 x 21 W) |
| 23 | B OUT7 | X1-E | Wiper slow | Motor | 15 A / 60 A 500 ms | wiper: LO / HI / INT with the key on, park cam IN20, wash IN21 | wiper switch / relay, WIPER 20 A | 6.0 A (CAR_LOADS) |
| 24 | B OUT8 | X1-G | Wiper fast | Motor | 15 A / 60 A 500 ms | the wiper's fast state | same | (the same motor) |

Spare: 6 (A1 OUT6, X1-N, 7.5 A), 18 and 19 (B OUT2 / OUT3, studs, 31 A). 10 = A2 OUT2 = the box fans.

## Inputs

Ground-switched inputs: pull-up on and inverted (on = switch to ground). On the input boards (A IN3-7, B IN3-10) the
DIP switches: SW1 (10 k pull-up) ON for a ground-switched input, SW2 (10 k pull-down) ON for a 12 V input.

| Input | Board input | Connector | Name | Active | Wake | Wire in the car |
|---|---|---|---|---|---|---|
| IN1 | A1 IN1 | X2-7 | Head / flash (R-Y) | to ground | - | light switch HEAD / dimmer FLASH (IE1-2) |
| IN2 | A1 IN2 | X2-8 | High / flash (R-W) | to ground | yes | dimmer HIGH / FLASH (IE1-18) |
| IN3 | A1 IN3 | X2-9 | DRL switch | to ground | - | DRL-SW |
| IN4 | A1 IN4 | X2-10 | Horn switch | to ground | - | horn switch C15-10 (IE1-19) |
| IN5 | A1 IN5 | X2-11 | EFI main relay (Bus 2) | 12 V | yes | K-EFI 87 = LOGIC Bus 2 (key on and the ECU after-run) |
| IN6 | A1 IN6 | X2-12 | Brake switch | 12 V | yes | stop lamp switch output |
| IN7 | A1 IN7 | X2-13 | Light switch TAIL | to ground | yes | taillight relay coil wire |
| IN8 | A2 IN1 | X2-15 | Turn left | to ground | - | turn switch LEFT |
| IN9 | A2 IN2 | X2-16 | Hazard switch | to ground | yes | hazard switch H5 |
| IN10 | A2 IN3 | X2-17 | Turn right | to ground | - | turn switch RIGHT |
| IN11 | A2 IN4 | X2-18 | Pop-up LH at top | to ground | - | retract motor LH up limit contact (TO CHECK) |
| IN12 | A2 IN5 | X2-19 | Pop-up LH at bottom | to ground | - | retract motor LH down limit contact (TO CHECK) |
| IN13 | A2 IN6 | X2-20 | Pop-up RH at top | to ground | - | retract motor RH up limit contact (TO CHECK) |
| IN14 | A2 IN7 | X2-21 | Pop-up RH at bottom | to ground | - | retract motor RH down limit contact (TO CHECK) |
| IN16 | B IN2 | X2-24 | Ignition (IG2) | 12 V | yes | J/B1 1H-7 IGN |
| IN17 | B IN3 | X2-25 | Wiper LO | to ground | - | wiper switch LO |
| IN18 | B IN4 | X2-26 | Wiper HI | to ground | - | wiper switch HI |
| IN19 | B IN5 | X2-27 | Wiper INT | to ground | - | wiper switch INT |
| IN20 | B IN6 | X2-28 | Wiper park cam | 12 V | - | wiper motor park cam |
| IN21 | B IN7 | X2-29 | Washer switch | to ground | - | washer switch |
| IN22 | B IN8 | X2-30 | Rear defogger switch | to ground | - | defogger push switch (a press toggles) |
| IN23 | B IN9 | X2-31 | Light switch OFF (pods down) | to ground | - | light control switch OFF contact (was R8's down input) |
| IN24 | B IN10 | X2-32 | Reverse switch | 12 V | - | back-up switch output |

Free: IN15 (B IN1). Wake set per board: only inputs the firmware can arm (`core/sleep.cpp`: not A IN1 / IN3 / IN4,
not B IN1 / IN9 / IN10); the tail switch covers the head lamps (the rotary switch passes TAIL first).

## Pop-up headlamps (why the PDM can do what the stalk did)

The old way: the stalk grounds the R-Y wire; the retract control relay R8 reads that ground on its pin 8 and runs
the motors; st185 added K-POD so the DRL switch could ground pin 8 too. A PDM output can only SOURCE +12 V (a
high-side switch: on = +12 V, off = open). It can never pull a wire to ground, so it cannot "press" R8's input. That is
why the old plan kept R8 and K-POD.

The new way skips R8: the PDM reads the stalk (IN1), the DRL switch (IN3), the EFI main (IN5) and the light switch OFF
contact (IN23) as inputs, and drives each pop-up motor straight from its own output. A Toyota retract motor turns one
way only: a crank moves the lamp up in one half turn and down in the next (1992 EWD headlight page: motor plus UP and
DOWN limit contacts, R2 / R3; the same way ECUMaster PMU users run FC3S pop-ups: limit switches into PMU inputs, one
output per motor, HP Academy forum "fd3s pop up headlights with pdm" / "how do we manage pop up headlights using
pmu16"). So the motor only needs +12 V until its own limit contact says it has arrived, like a wiper park cam:

- up = (DRL switch AND EFI main) OR head / flash; down = light switch OFF AND NOT up (flash wins).
- each motor runs while (up AND NOT at top) OR (down AND NOT at bottom), and stops on its own contact.
- PDM function `pop-ups` (`PdmFunctions.SetPopUps`): 6 virtual inputs on A2 + 4 CAN inputs for IN1 / IN3 / IN5 / IN23.
- Removed: R8, RTR 30 A, K-POD, D1 / D2.
- TO CHECK on the bench: which motor pins are the limit contacts and that each closes to ground at its end (the
  config inverts them; change `invert` if they open instead); the motor's running and stall current (7.5 A output,
  30 A for 500 ms at start).

## Low battery (load shed)

Battery: AGM (`docs/devices/SENSOR-AND-ACTUATOR-REFERENCE.md` line 33; no model named in st185). Odyssey (an AGM
maker) gives the resting voltage per charge: 12.9 V full, 12.6 V 75 %, 12.2 V 50 %, 11.9 V 25 %, 11.5 V empty
(Odyssey technical manual, Table 4). So 11.5 V is not too high: at rest it is an EMPTY AGM, too low to rely on. Under a
load the voltage sits 0.1-0.3 V below the resting value, so 11.8 V with loads on is about 25-50 % charge: the lowest
point that still keeps enough to crank. Victron's BatteryProtect has the same 11.8 V off / 12.8 V back preset
(setting 7) with a 90 s delay. A lithium (LiFePO4) battery would need other numbers (flat curve, its own BMS cut-off).

The config: the rear defogger (the biggest load you can do without) goes off when the battery is at or under 11.8 V
for 30 s with the key on, and comes back at 12.8 V or more (only reached with the alternator charging). The 30 s is
far longer than a crank (s5: 6 V for 80 ms, 9.6 V for 1.2 s), so a crank never sheds. With the key off the shed is
not armed: nothing ECU-held or held by the ECU's after-run is ever touched. Lamps, horn, wipers and modules are never
shed (safety). Recipe: 2 conditions + 1 virtual input + 1 timer + 1 latch virtual input on B (stock functions).

## ECU and CAN

- The ECU's loads are not on the PDM (above), so the PDM reads no ECU frame and the ECU needs no new transmit stream.
- The PDM's own frames (0x500-0x527, 0x540-0x567, 0x580-0x5A7) sit inside st185's free range 0x3F2-0x63F (allocation
  table section 1); the ECU may read them (`docs/car-can-dummy/link_pdm_receive.dummy.json`), nothing has to.
- Cluster and RealDash: unchanged.

## Stays on its relay / fuse (and why)

| Load | Why |
|---|---|
| Fuel pump (K-FP, FP 40 A), EPS pump (K-EPS 50 A) + enable (K-EPS-EN), radiator + condenser fans (K-FAN / K-FAN2), A/C clutch (K-ACC), heater blower (R/B No.4 heater relay + 40 A), ETB (K-ETB), injectors, coils, boost solenoid | the ECU controls and powers them (Dan 2026-11-23 07:44) |
| EFI main relay K-EFI and Bus 2 (SW12, COP, INJ, ALMIG) | the ECU's own power hold and ETB after-run: a relay the ECU holds is simpler and safer than a PDM output that must never sleep, shed or time out |
| Starter (R/B No.4 starter relay + clutch switch C11) | hardware interlock (circuit 2) |
| Constant feeds (AM1, AM2, J/B1, DOME, ALM / ALMS, ALTS, ECU-B, door locks on POWER 30 A) | must work with the key off and the PDM asleep |
| Radio / RealDash Pi (CIG & RADIO 15 A, ACC) | needs the ACC key position: no input left for it |

## TO CHECK

- T1 Currents on the car: stop, turn, tail, back-up lamps (bulb sizes), pop-up motors, power windows, defogger.
- T2 The pop-up limit contacts (above) and the light switch OFF contact (R8 input pin, 1993 EWD p.116).
- T3 The power windows' key-off use (the OEM power main relay coil comes through key-off diode D6): IN16 only here.
- T4 The input-board DIP switches as in the Inputs table.
