DUMMY COPY of the car facts - DUMMY / DEMO / TEST ONLY - source: st185-link-ecu-config @ a0490839 (`sot/fuse-relay-map.csv`, `sot/channels.csv`, `docs/harness/circuit-plan.md`, `docs/harness/README.md`, `CAN-BUS-ID-ALLOCATION-TABLE.md`, `CAN-BUS-MASTER-DESIGN.md`, `docs/devices/SENSOR-AND-ACTUATOR-REFERENCE.md`) and st185-celica-repair-manual @ 66b0f72 (1992 EWD power source and headlight pages); both read only, nothing written there.

# ST185 car config (full-PDM demo, carsim 2026-11-23)

What this is: Dan's brief (2026-11-23): "my car wiring was based on NO PDM; pretend I WANT a PDM now". The config
`ui/examples/st185-car.dummy.json` puts every load of the car's fuse / relay boxes (st185 POWER box B1, LOGIC box B2,
trunk block B3, the kept OEM boxes J/B No.1, R/B No.2, R/B No.4 and the retract relay R8) on the PDM, except what the
ECU controls and powers and what no PDM output is rated for (below). It is built by `ui/tests/CustomPdm.Tests/St185Car.cs`; `St185CarTests` keep the file, the map
and the tables below the same. It is a demo / test config: nothing is confirmed on the car. The PDM is unproven until
the PCBs are made.

In plain words:
- 14 car loads on 17 outputs (3 loads on a firmware pair of two board A outputs); 6 outputs spare (A1 OUT4-6, A2 OUT1,
  OUT7, OUT8, all 7.5 A); A2 OUT2 runs the box fans.
- Output sizing (fusesize, 2026-11-25): each st185 fuse box sizes a circuit's fuse from the device's peak / inrush
  current, so the FUSE RATING is the sizing number (`docs/pdm-2a-plan.md`): every output (a pair: its derated pair
  rating) is rated at least the fuse of its circuit. 15 A circuits (low / high beams, horns, tail) on board B's
  15 A outputs, 30 A circuits (pop-ups, windows, defogger) on its 31 A studs, 10 A circuits (turn signals,
  CAN-Lambda) on board A pairs: 7.5 A / 0.5954 = 12.5 A (`PdmView.PairRating`: the two switches share unevenly, the
  hotter one takes up to 59.5 %). `St185CarTests.EveryCarOutputIsRatedForItsCircuitsFuse` fails on any output under
  its fuse.
- Stop lamps, back-up lamps, wipers and washer stay on their OEM switches and fuses (STOP 15 A, GAUGE 15 A,
  WIPER 20 A): after the above, the best free output is a 12.5 A board A pair. The stock st185 way has no relay coil
  for them (the switch carries the lamp / motor current), and the harness cost study found these moves only add wire.
- The ECU (Link G4X) keeps controlling AND powering its own loads through its own relays (Dan 2026-11-23 07:44):
  fuel pump, power steering pump, radiator and condenser fans, heater, A/C, ETB, throttle pedal, boost solenoid,
  injectors, coils. The PDM gets no command from the ECU, so no ECU CAN frame is needed.
- The EFI main relay K-EFI stays a relay: the ECU powers itself with it and parks the electronic throttle after the
  key is off (ECU Hold Power on Aux 6 with the ignition sense on DI 9, `sot/channels.csv` a28 / b28). What K-EFI's
  Bus 2 fed and the PDM now feeds (DRLs, CSB3, cluster) follows A1 IN5 = the K-EFI output, never the ignition and
  never a PDM timer. So during the ECU's after-run those stay on, and they go off when the ECU lets go.
- Auto sleep: each board mutes its CAN 10 s after IN5 (ECU hold), IN7 (tail switch) and IN9 (hazard switch) are all
  off, and sleeps 30 s after the bus is quiet. Wake: the ignition, EFI main, tail, flash and hazard inputs.
- Every limit is a device preset, at or under both the output rating and the fuse that protects that wire today.

## Outputs

PDM numbers: 1-8 = A1 OUT1-8, 9-16 = A2 OUT1-8, 17-24 = B OUT1-8. Connector: `docs/box-connectors.md`.

| # | Board output | Connector | Load | Preset | Limit / inrush | Trigger | Replaces | st185 fuse / output rating | Current (steady, source) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | A1 OUT1 | X1-H | CAN-Lambda | Heater, limit lowered | 10 A / 15 A 500 ms | IN16 (ignition, over CAN, off at loss) | K-ON (LOGIC M7) + LAM 10 A | 10 A / 12.5 A pair (+ 2 = A1 OUT2, X1-J) | 8.1 A (CAR_LOADS; Link manual: heater 8 A max) |
| 3 | A1 OUT3 | X1-K | DRLs | LED lamp | 5 A / 15 A 100 ms | IN3 AND IN5 AND NOT IN1 | K-DRL (LOGIC M8) + RLY-DRL (B5) + DRL 7.5 A | 7.5 A / 7.5 A | 0.5 A (st185 A34) |
| 7 | A1 OUT7 | X1-P | CSB3 switchboard | ECU / module feed | 5 A / 10 A 100 ms | IN5 (EFI main) | CSB 5 A (Bus 2) | 5 A / 7.5 A | 2.0 A (ASSUMED) |
| 8 | A1 OUT8 | X1-R | Centre cluster | ECU / module feed | 5 A / 10 A 100 ms | IN5 (EFI main) | DEV 5 A (Bus 2) | 5 A / 7.5 A | 1.5 A (ASSUMED) |
| 11 | A2 OUT3 | X1-U | Turn left | Lamp, limit lowered | 10 A / 100 A 100 ms | turn signals: IN8 or hazard IN9, 350 / 350 ms | OEM flasher, TURN 10 A, HZ 15 A | 10 A / 12.5 A pair (+ 12 = A2 OUT4, X1-V) | 3.3 A (ASSUMED) |
| 13 | A2 OUT5 | X1-W | Turn right | Lamp, limit lowered | 10 A / 100 A 100 ms | turn signals: IN10 or hazard IN9 | OEM flasher, TURN 10 A, HZ 15 A | 10 A / 12.5 A pair (+ 14 = A2 OUT6, X1-X) | 3.3 A (ASSUMED) |
| 17 | B OUT1 | Stud OUT1 | Power windows | Motor, limit raised | 25 A / 60 A 500 ms | IN16 (ignition) | R/B No.2 power main relay | 30 A / 31 A | about 10 A, 20 A stalled (ASSUMED) |
| 18 | B OUT2 | Stud OUT2 | Pop-up LH | Motor | 15 A / 60 A 500 ms | pop-ups (below), limits IN17 / IN18 | retract relay R8 + RTR 30 A + K-POD + D1 / D2 | 30 A / 31 A | 5 A (ASSUMED) |
| 19 | B OUT3 | Stud OUT3 | Pop-up RH | Motor | 15 A / 60 A 500 ms | pop-ups (below), limits IN19 / IN20 | same | 30 A / 31 A | 5 A (ASSUMED) |
| 20 | B OUT4 | Stud OUT4 | Rear defogger | Heater, limit lowered | 20 A / 30 A 500 ms | IN22 (push on / off) AND IN16 AND NOT battery shed | defogger relay + DEFOGGER 30 A | 30 A / 31 A | 15 A (ASSUMED, about 200 W) |
| 21 | B OUT5 | X1-B | Low beams | LED lamp | 5 A / 15 A 100 ms | IN1 (head / flash, over CAN, holds at loss) | K-HL relay (LOGIC M1) + HL 15 A | 15 A / 15 A | 2.0 A (presim CAR_LOADS) |
| 22 | B OUT6 | X1-D | High beams | LED lamp | 5 A / 15 A 100 ms | IN2 AND IN1 (over CAN) | K-HR relay (LOGIC M2) + HR 15 A | 15 A / 15 A | 2.5 A (CAR_LOADS) |
| 23 | B OUT7 | X1-E | Horns | Horn | 15 A / 45 A 200 ms | IN4 (over CAN, off at loss) | K-HORN (LOGIC M3) | 15 A / 15 A | 5.0 A (CAR_LOADS) |
| 24 | B OUT8 | X1-G | Tail / park / licence / dash lights | Lamp (halogen) | 15 A / 100 A 100 ms | IN7 (over CAN, holds at loss) | taillight relay + TAIL 15 A | 15 A / 15 A | 4.8 A (ASSUMED: front 1.3 A + rear / licence / dash 3.5 A) |

Pairs (firmware output pairing, stock 'Primary output' on the Advanced screen; `functions/profet.cpp`): the follower
copies the primary's on / off / PWM, the primary checks its limit against the sum and reports it; both channels of one
BTS7008-2EPA (`docs/firmware-pin-map.md`): 1 + 2 (A1 OUT1 + OUT2, U8), 11 + 12 (A2 OUT3 + OUT4, U11), 13 + 14 (A2 OUT5 +
OUT6, U10). The two cavities of a pair join in a splice just behind X1, one wire on to the load.

Spare: 4, 5, 6 (A1 OUT4-6, X1-L / M / N), 9 (A2 OUT1, X1-S), 15, 16 (A2 OUT7 / OUT8, X1-A / C), all 7.5 A (5 + 6 and
15 + 16 can pair to 12.5 A). 10 = A2 OUT2 = the box fans.

## Inputs

Ground-switched inputs: pull-up on and inverted (on = switch to ground). On the input boards (A IN3-7, B IN3-10) the
solder jumpers (they replaced the DIP switches, hwtemp): the pull-up row bridged for a ground-switched input, the
pull-down row for a 12 V input; per board: `docs/order-checklist.md` section 8.

| Input | Board input | Connector | Name | Active | Wake | Wire in the car |
|---|---|---|---|---|---|---|
| IN1 | A1 IN1 | X2-7 | Head / flash (R-Y) | to ground | - | light switch HEAD / dimmer FLASH (IE1-2) |
| IN2 | A1 IN2 | X2-8 | High / flash (R-W) | to ground | yes | dimmer HIGH / FLASH (IE1-18) |
| IN3 | A1 IN3 | X2-9 | DRL switch | to ground | - | DRL-SW |
| IN4 | A1 IN4 | X2-10 | Horn switch | to ground | - | horn switch C15-10 (IE1-19) |
| IN5 | A1 IN5 | X2-11 | EFI main relay (Bus 2) | 12 V | yes | K-EFI 87 = LOGIC Bus 2 (key on and the ECU after-run) |
| IN7 | A1 IN7 | X2-13 | Light switch TAIL | to ground | yes | taillight relay coil wire |
| IN8 | A2 IN1 | X2-15 | Turn left | to ground | - | turn switch LEFT |
| IN9 | A2 IN2 | X2-16 | Hazard switch | to ground | yes | hazard switch H5 |
| IN10 | A2 IN3 | X2-17 | Turn right | to ground | - | turn switch RIGHT |
| IN16 | B IN2 | X2-24 | Ignition (IG2) | 12 V | yes | J/B1 1H-7 IGN |
| IN17 | B IN3 | X2-25 | Pop-up LH at top | to ground | - | retract motor LH up limit contact (TO CHECK) |
| IN18 | B IN4 | X2-26 | Pop-up LH at bottom | to ground | - | retract motor LH down limit contact (TO CHECK) |
| IN19 | B IN5 | X2-27 | Pop-up RH at top | to ground | - | retract motor RH up limit contact (TO CHECK) |
| IN20 | B IN6 | X2-28 | Pop-up RH at bottom | to ground | - | retract motor RH down limit contact (TO CHECK) |
| IN22 | B IN8 | X2-30 | Rear defogger switch | to ground | - | defogger push switch (a press toggles) |
| IN23 | B IN9 | X2-31 | Light switch OFF (pods down) | to ground | - | light control switch OFF contact (was R8's down input) |

Free: IN6 (A1 IN6), IN11-14 (A2 IN4-7), IN15 (B IN1), IN21 (B IN7), IN24 (B IN10). The pop-up limit contacts are on
B, the motors' board (`PdmFunctions.SetPopUps`: the stop must not wait for CAN). Wake set per board: only inputs the firmware can arm (`core/sleep.cpp`: not A IN1 / IN3 / IN4,
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
- PDM function `pop-ups` (`PdmFunctions.SetPopUps`): 6 virtual inputs on B + 3 CAN inputs for IN1 / IN3 / IN5 (IN23 is on B).
- Removed: R8, RTR 30 A, K-POD, D1 / D2.
- TO CHECK on the bench: which motor pins are the limit contacts and that each closes to ground at its end (the
  config inverts them; change `invert` if they open instead); the motor's running and stall current (31 A stud output:
  15 A limit, 60 A for 500 ms at start; RTR 30 A fuse).

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
| Radio / RealDash Pi (CIG & RADIO 15 A, ACC) | needs the ACC key position (not wired to the PDM) |
| Stop lamps (stop lamp switch, J/B No.1 STOP 15 A) | no free output is rated 15 A (the best is a 12.5 A board A pair); the switch carries the lamp current (no relay coil to drive) |
| Back-up lamps (back-up switch, J/B No.1 GAUGE 15 A) | as the stop lamps |
| Wipers + washer (OEM wiper switch / relay, J/B No.1 WIPER 20 A) | 20 A fuse: no free output is rated for it; the OEM switch and wiper relay do the park and intermittent wipes |

## TO CHECK

- T1 Currents on the car: turn and tail lamps (bulb sizes), pop-up motors, power windows, defogger.
- T2 The pop-up limit contacts (above) and the light switch OFF contact (R8 input pin, 1993 EWD p.116).
- T3 The power windows' key-off use (the OEM power main relay coil comes through key-off diode D6): IN16 only here.
- T4 The input-board solder jumpers as in the Inputs table (`docs/order-checklist.md` section 8).
- T5 The board A output pairs (A1 OUT1 + OUT2, A2 OUT3 + OUT4, A2 OUT5 + OUT6): the current share of the two channels
  of each BTS7008-2EPA, and the switching skew (host sim: the follower switches 2-3 ms before its primary, so one
  channel takes a lamp's cold inrush alone for that time).
