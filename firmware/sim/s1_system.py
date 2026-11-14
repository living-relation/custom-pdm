"""S1-S5: three boards in one box as one PDM. Commissioning, a PC-side 'single PDM' layer on stock
firmware logic, what outputs do when a CAN link is lost (three policies), thermal protection + fans (S4), and
MCP9808 read failures + wake-up from sleep (S5).
IDs used here are examples only: boards 0x500 / 0x520 / 0x540, ECU command frame 0x4F0."""
import sys, json, struct, pdmsim as ps
SO = sys.argv[1] if len(sys.argv) > 1 else '/tmp/simout'
BASE = {'A1': 0x500, 'A2': 0x520, 'B': 0x540}; ECU_ID = 0x4F0; ALIVE_SLOT = 31; TIMEOUT_MS = 1000   # Dan D3a: 1 s default (also the firmware default), adjustable per channel
res = []; info = {}
def check(name, ok, detail=''):
    res.append((name, bool(ok), str(detail))); print(('PASS ' if ok else 'FAIL ') + name + (' : ' + str(detail) if detail != '' else ''))

# ------------------------------------------------------------------ S1 commissioning
print('--- S1 commissioning')
# three fresh boards, each flashed with its own build (A unit 1, A unit 2, B): no setup needed
bus = ps.Bus(); tool = ps.Tool(bus)
fresh = {'A1': ps.Board(ps.BOARD_A, 'A1', SO, unit=1), 'A2': ps.Board(ps.BOARD_A, 'A2', SO, unit=2), 'B': ps.Board(ps.BOARD_B, 'B', SO)}
bus.add(tool, *fresh.values()); bus.run_for(1500)
check('three fresh boards come up at 1 Mbit/s and each answers alone on its own built-in ID', all(b.bitrate() == 1000000 for b in fresh.values()) and all(tool.version(BASE[k]) == (0, 5, 9) for k in fresh), [hex(v) for v in BASE.values()])
frams = {k: b.fram() for k, b in fresh.items()}
# option b stays available: move a board to another ID / bit rate over CAN, save, restart
b1 = ps.Bus(); t1 = ps.Tool(b1); x = ps.Board(ps.BOARD_A, 'A1', SO, unit=1); b1.add(t1, x); b1.run_for(1200)
ok = t1.write(0x500, 0x0000, 0, 0x6A0, reply_base=0x6A0) is not None and t1.write(0x6A0, 0x0000, 1, 1) is not None and t1.burn(0x6A0)
b1 = ps.Bus(); t1 = ps.Tool(b1, 500000); y = ps.Board(ps.BOARD_A, 'A1', SO, unit=1, fram=x.fram()); b1.add(t1, y); b1.run_for(1200)
check('manual setup still works: ID and bit rate changed over CAN, saved, kept after a restart', ok and y.bitrate() == 500000 and t1.version(0x6A0) == (0, 5, 9), y.bitrate())

# ------------------------------------------------------------------ the system: 3 boards, ECU, tool, 1 Mbit/s
bus = ps.Bus(); tool = ps.Tool(bus); ecu = ps.PyNode('ecu')
boards = {'A1': ps.Board(ps.BOARD_A, 'A1', SO, fram=frams['A1'], unit=1), 'A2': ps.Board(ps.BOARD_A, 'A2', SO, fram=frams['A2'], unit=2), 'B': ps.Board(ps.BOARD_B, 'B', SO, fram=frams['B'])}
stat = {k: ps.Status(BASE[k]) for k in boards}
for s_ in stat.values(): bus.watch.append(s_.feed)
bus.add(tool, ecu, *boards.values())
cmd = [0] * 24                                     # the ECU's 24 on/off commands
def ecu_tx(t):
    v = sum(b << i for i, b in enumerate(cmd)); ecu.send(ECU_ID, bytes([v & 255, (v >> 8) & 255, (v >> 16) & 255, 0xA5, 0, 0, 0, 0]))
ecu.every(20000, ecu_tx, start=5000)
bus.run_for(1500)
check('after a power cycle: all three still run at 1 Mbit/s on their own IDs', all(b.bitrate() == 1000000 for b in boards.values()) and all(s_.last > 0 for s_ in stat.values()), [b.bitrate() for b in boards.values()])
check('each board answers alone on its own ID', all(tool.version(BASE[k]) == (0, 5, 9) for k in boards))

# ------------------------------------------------------------------ S2 the single-PDM layer
print('--- S2 single-PDM layer')
# Global numbering (matches the README mix): 1-8 = A1, 9-16 = A2 (7.5 A), 17-20 = B out 5-8 (15 A), 21-24 = B out 1-4 (30 A class)
OUT = {g: ('A1', g - 1) for g in range(1, 9)} | {g: ('A2', g - 9) for g in range(9, 17)} | {g: ('B', g - 17 + 4) for g in range(17, 21)} | {g: ('B', g - 21) for g in range(21, 25)}
LIMIT = {g: 7.5 for g in range(1, 17)} | {g: 15.0 for g in range(17, 21)} | {g: 30.0 for g in range(21, 25)}
INP = {}; n_ = 1                                    # global input numbers
for k in ('A1', 'A2', 'B'):
    for i in range(len(boards[k].model['inputs'])): INP[n_] = (k, i); n_ += 1
info['inputs_total'] = len(INP)
writes = [0]
def W(k, index, sub, val):
    writes[0] += 1; r = tool.write(BASE[k], index, sub, val)
    if r is None: raise RuntimeError(f'no reply {k} {index:#x}/{sub}')
def can_input(k, slot, can_id, bit, timeout):
    for sub, val in [(4, can_id), (5, bit), (6, 1), (11, 0), (12, ps.f32(1.0)), (2, TIMEOUT_MS), (1, 1 if timeout else 0), (0, 1)]: W(k, 0x1300 + slot, sub, val)
virt_used = {k: 0 for k in boards}
def set_output(g, policy, source=('ecu', None)):
    """policy on link loss: 'hold' | 'off' | 'on'. source: ('ecu', None) = ECU command bit g-1, or ('input', n) = global input n."""
    k, o = OUT[g]; b = boards[k]; slot = o                                  # CAN input slot = local output number
    if source[0] == 'ecu': can_input(k, slot, ECU_ID, g - 1, timeout=policy != 'hold')
    else:
        sk, si = INP[source[1]]; can_input(k, slot, BASE[sk] + 2 + 27, si, timeout=policy != 'hold')   # other board's input bit (msg 27)
    var = b.var_canin(slot)
    if policy == 'on':                                                        # output = command OR NOT link-alive
        v = virt_used[k]; virt_used[k] += 1
        for sub, val in [(2, b.var_canin(slot)), (3, 1), (4, 1), (5, b.var_canin(ALIVE_SLOT)), (0, 1)]: W(k, 0x1400 + v, sub, val)
        var = b.var_virt(v)
    for sub, val in [(2, ps.f32(LIMIT[g])), (3, ps.f32(LIMIT[g] * 2)), (1, var), (0, 1)]: W(k, 0x1000 + o, sub, val)
def alive_input(k):                                                           # true while ECU frames arrive (byte 3 = 0xA5)
    for sub, val in [(4, ECU_ID), (5, 24), (6, 8), (11, 0), (12, ps.f32(165.0)), (2, TIMEOUT_MS), (1, 1), (0, 1)]: W(k, 0x1300 + ALIVE_SLOT, sub, val)
POLICY = {g: 'off' for g in range(1, 25)}
POLICY.update({1: 'hold', 2: 'off', 3: 'on', 21: 'hold', 22: 'off', 23: 'on'})
t0 = bus.now
for k in boards: alive_input(k)
for g in range(1, 25):
    if g == 5: set_output(5, 'off', source=('input', [n for n, v in INP.items() if v == ('B', 2)][0]))   # cross-board rule: B input-board ch 1 -> output 5 (on A1)
    else: set_output(g, POLICY[g])
info['config_writes'] = writes[0]; info['config_seconds'] = round((bus.now - t0) / 1e6, 2)
for k in boards: check(f'{k}: config saved to FRAM', tool.burn(BASE[k]))
kb = boards['B']; kb.set_input(2, 'gnd', 'up'); W('B', 0x1200 + 2, 0, 1)
for g, (k, o) in OUT.items(): boards[k].set_load(o, boards[k].vbat / (LIMIT[g] * 0.6))
bus.run_for(300)
def pins_on():      # ground truth: which IN pins are high, as global output numbers
    return [g for g, (k, o) in OUT.items() if boards[k].level(boards[k].model['outputs'][o][0])]
def can_on():       # what the unified view shows, from status frames only
    return [g for g, (k, o) in OUT.items() if stat[k].out_state(o) == 1]
ok, det = True, []
for g in range(1, 25):
    if g == 5: continue
    cmd[:] = [0] * 24; cmd[g - 1] = 1; bus.run_for(200)
    if pins_on() != [g] or can_on() != [g]: ok = False; det.append((g, pins_on(), can_on()))
check('walking one ECU bit through 23 outputs: exactly that output switches, on the right board, and the merged status agrees', ok, det)
cmd[:] = [0] * 24; bus.run_for(200)
kb.set_input(2, '12v'); t_sw = bus.now
while 5 not in pins_on() and bus.now < t_sw + 2_000_000: bus.run_for(1)
lat_x = (bus.now - t_sw) / 1000
check('cross-board rule: an input on board B switches output 5 on board A1', pins_on() == [5], pins_on())
kb.set_input(2, 'gnd'); bus.run_for(400)
check('cross-board rule releases again', pins_on() == [], pins_on())
bus.run_for(30); cmd[9] = 1; t_sw = None; base_n = bus.count
# latency: from the ECU frame that carries the new bit to the IN pin going high
seen = []
def w(f):
    if f.id == ECU_ID and f.data[1] & 2 and not seen: seen.append(f.t)
bus.watch.append(w)
while 10 not in pins_on(): bus.run_for(0.1)
info['latency_ecu_ms'] = round((bus.now - seen[0]) / 1000, 1); info['latency_cross_board_ms'] = round(lat_x, 1)
cmd[:] = [0] * 24; bus.run_for(300)
b0, t0 = bus.busy_us, bus.now; bus.run_for(2000); info['bus_load_pct'] = round(100 * (bus.busy_us - b0) / (bus.now - t0), 1)
info['frames_per_s'] = None
c = {k: boards[k].counters() for k in boards}
check('no CAN receive overruns or transmit time-outs on any board', all(v['rx_overruns'] == 0 and v['tx_timeouts'] == 0 for v in c.values()), {k: (v['rx_overruns'], v['tx_timeouts']) for k, v in c.items()})
check('no board in fatal error', not any(b.flags()['fatal'] for b in boards.values()))
total = sum((stat[k].total() or 0) for k in boards)
for g, (k, o) in OUT.items(): cmd[g - 1] = 1 if g in (1, 9, 17, 21) else 0
bus.run_for(400); total = sum((stat[k].total() or 0) for k in boards); want = sum(LIMIT[g] * 0.6 for g in (1, 9, 17, 21))
check('one total-current number from three boards', abs(total - want) <= 4, f'{total} A shown, {want:.1f} A real (CAN sends whole amps)')
cmd[:] = [0] * 24; bus.run_for(300)
frams2 = {k: boards[k].fram() for k in boards}

# ------------------------------------------------------------------ S3 link loss
print('--- S3 link loss')
WATCH = [1, 2, 3, 21, 22, 23]          # hold / off / on  on A1, and the same on B
def snapshot(): p = pins_on(); return {g: int(g in p) for g in WATCH + [5]}
def settle_time(g, expect, limit_ms=3000):
    t = bus.now
    while (g in pins_on()) != bool(expect) and bus.now < t + limit_ms * 1000: bus.run_for(2)
    return round((bus.now - t) / 1000)
matrix = []
def case(name, pre_cmd, fault, undo):
    cmd[:] = [0] * 24
    for g in WATCH: cmd[g - 1] = pre_cmd
    bus.run_for(TIMEOUT_MS + 300); before = snapshot(); t = bus.now; fault(); trace = {g: None for g in WATCH}
    while bus.now < t + 2_500_000:
        bus.run_for(5); p = pins_on()
        for g in WATCH:
            if trace[g] is None and (g in p) != bool(before[g]): trace[g] = round((bus.now - t) / 1000)
    after = snapshot(); stale = {k: round((bus.now - stat[k].last) / 1000) for k in boards}
    undo(); bus.run_for(TIMEOUT_MS + 500); back = snapshot()
    matrix.append(dict(case=name, cmd=pre_cmd, before=before, after=after, change_ms=trace, recovered=back, status_age_ms=stale))
    print(f'  {name} (cmd {"ON" if pre_cmd else "OFF"}): after {after}  change at ms {trace}  recovered {back}')
def ecu_off(): ecu.powered = False
def ecu_on(): ecu.powered = True
def unplug(k):
    def f(): boards[k].connected = False
    return f
def plug(k):
    def f(): boards[k].connected = True
    return f
case('ECU stops sending', 1, ecu_off, ecu_on)
case('ECU stops sending', 0, ecu_off, ecu_on)
case('board A1 CAN unplugged', 1, unplug('A1'), plug('A1'))
case('board B CAN unplugged', 1, unplug('B'), plug('B'))
m = {(r['case'], r['cmd']): r for r in matrix}
r = m[('ECU stops sending', 1)]
check('policy hold: stays ON when the ECU goes quiet', r['after'][1] == 1 and r['after'][21] == 1)
check('policy off: switches OFF after the time-out', r['after'][2] == 0 and r['after'][22] == 0 and TIMEOUT_MS - 100 <= r["change_ms"][2] <= TIMEOUT_MS + 200, r['change_ms'])
check('policy on: stays ON', r['after'][3] == 1 and r['after'][23] == 1)
r = m[('ECU stops sending', 0)]
check('policy hold: stays OFF when it was off', r['after'][1] == 0 and r['after'][21] == 0)
check('policy on: turns ON after the time-out when it was off', r['after'][3] == 1 and r['after'][23] == 1 and TIMEOUT_MS - 100 <= r["change_ms"][3] <= TIMEOUT_MS + 200, r['change_ms'])
check('everything follows the ECU again when frames return', all(v == 0 for g, v in r['recovered'].items() if g != 5) and all(m[('ECU stops sending', 1)]['recovered'][g] == 1 for g in WATCH))
r = m[('board A1 CAN unplugged', 1)]
check('one board unplugged: only that board applies its policies, board B carries on', (r['after'][1], r['after'][2], r['after'][3]) == (1, 0, 1) and (r['after'][21], r['after'][22], r['after'][23]) == (1, 1, 1), r['after'])
check('merged view can flag the lost board: its status goes stale, the others stay fresh', r['status_age_ms']['A1'] > 2000 and r['status_age_ms']['B'] < 250, r['status_age_ms'])
# cross-board rule when the source board drops off
cmd[:] = [0] * 24; kb.set_input(2, '12v'); bus.run_for(500); pre = 5 in pins_on()
boards['B'].connected = False; dt = settle_time(5, 0); boards['B'].connected = True; bus.run_for(500); post = 5 in pins_on(); kb.set_input(2, 'gnd'); bus.run_for(400)
check('cross-board rule (policy off): output 5 drops when board B falls off the bus, returns when it is back', pre and TIMEOUT_MS - 100 <= dt <= TIMEOUT_MS + 200 and post, f'{dt} ms')
info['cross_rule_drop_ms'] = dt
# power cycle of A1 while the ECU is silent, then while the ECU is talking
def power_cycle(k):
    old = boards[k]; fr = old.fram(); old.powered = False; old.connected = False
    nb = ps.Board(old.model, k, SO, fram=fr, unit=2 if k == 'A2' else 1); nb.t0 = bus.now; boards[k] = nb; bus.nodes[bus.nodes.index(old)] = nb
    for g, (kk, o) in OUT.items():
        if kk == k: nb.set_load(o, nb.vbat / (LIMIT[g] * 0.6))
    return nb
for g in WATCH: cmd[g - 1] = 1
bus.run_for(500); ecu.powered = False; bus.run_for(100)
power_cycle('A1'); t = bus.now; first_on = None
while bus.now < t + 3_000_000:
    bus.run_for(2)
    if first_on is None and 3 in pins_on(): first_on = round((bus.now - t) / 1000)
boot_silent = {g: int(g in pins_on()) for g in (1, 2, 3)}
check('board restarts with no ECU on the bus: hold = OFF (nothing to hold), off = OFF, on = ON', boot_silent == {1: 0, 2: 0, 3: 1}, boot_silent)
info['boot_default_on_ms'] = first_on
ecu.powered = True; bus.run_for(800)
check('ECU returns after the restart: outputs follow commands', all(g in pins_on() for g in (1, 2, 3)))
power_cycle('A1'); t = bus.now; first = {}
while bus.now < t + 2_000_000:
    bus.run_for(2)
    for g in (1, 2, 3):
        if g not in first and g in pins_on(): first[g] = round((bus.now - t) / 1000)
info['boot_to_output_ms'] = first
check('board restarts while the ECU is talking: outputs come back on by themselves', len(first) == 3, first)
check('saved config survived both restarts', boards['A1'].bitrate() == 1000000 and tool.version(BASE['A1']) is not None)

# ------------------------------------------------------------------ extras
print('--- extras')
# stock CAN hardware filter option: does configuration over CAN still work with it on?
b2 = ps.Bus(); t2 = ps.Tool(b2); x = ps.Board(ps.BOARD_A, 'A1', SO, fram=frams2['A1']); b2.add(t2, x); b2.run_for(1200)
t2.write(BASE['A1'], 0x0000, 3, 1); t2.burn(BASE['A1']); fr = x.fram()
b3 = ps.Bus(); t3 = ps.Tool(b3); e3 = ps.PyNode('ecu'); y = ps.Board(ps.BOARD_A, 'A1', SO, fram=fr); b3.add(t3, e3, y)
e3.every(20000, lambda t: e3.send(ECU_ID, bytes([1, 0, 0, 0xA5, 0, 0, 0, 0])), 5000); y.set_load(0, 3.0); b3.run_for(1500)
v = t3.version(BASE['A1']); info['filter_on_tool_reply'] = v is not None; info['filter_on_ecu_cmd_works'] = bool(y.level('PB10')); info['filter_on_dropped'] = y.counters()['rx_filtered']
print(f"  CAN filter option ON: ECU command still works = {info['filter_on_ecu_cmd_works']}, tool gets an answer over CAN = {info['filter_on_tool_reply']}, frames filtered = {info['filter_on_dropped']}")
# sleep: which pins are armed as wake-up sources (board B, sleep enabled, bus silent)
b4 = ps.Bus(); t4 = ps.Tool(b4); z = ps.Board(ps.BOARD_B, 'B', SO, fram=frams['B']); b4.add(t4, z); b4.run_for(1200)
t4.write(BASE['B'], 0x0000, 2, 1); t4.powered = False; b4.run_for(34000)
names = 'ABCDEFGH'; ex = {p: names[z.L.sim_exti_port(p)] for p in range(16) if z.L.sim_exti_port(p) >= 0}
info['sleep_entered'] = z.flags()['asleep']; info['sleep_wake_lines'] = {f'EXTI{p}': f'P{v}{p}' for p, v in ex.items()}; info['sleep_exti_clashes'] = z.counters()['exti_clashes']
print(f"  sleep after 30 s idle: {info['sleep_entered']}, wake lines {info['sleep_wake_lines']}, clashes {info['sleep_exti_clashes']}")

# ------------------------------------------------------------------ S4 thermal (r5a, r3c, r7a; docs/firmware-thermal-plan.md)
print('--- S4 thermal')
# fresh boards (factory defaults): limits, fan output, temperatures on CAN
b5 = ps.Bus(); t5 = ps.Tool(b5)
f5 = {'A1': ps.Board(ps.BOARD_A, 'A1', SO, unit=1), 'A2': ps.Board(ps.BOARD_A, 'A2', SO, unit=2), 'B': ps.Board(ps.BOARD_B, 'B', SO)}
st5 = {k: ps.Status(BASE[k]) for k in f5}
for s_ in st5.values(): b5.watch.append(s_.feed)
fk, fo = ps.FAN; a2f = f5['A2']; FAN_IN = a2f.model['outputs'][fo][0]
b5.add(t5, *f5.values()); fan_boot = []
for _ in range(300): b5.run_for(5); fan_boot.append(a2f.level(FAN_IN))          # every 5 ms from power-up, all boards at 30 C
lim = {k: {n: t5.read(BASE[k], ps.TEMP_INDEX, sub) for n, sub in ps.TEMP_PARAM.items()} for k in f5}
check('thermal: factory defaults on every board (param block 0x7F00): warn 55, critical 80, recovery 6, critical-soon margin 5 deg C', all(v == ps.TEMP_DEFAULT for v in lim.values()), lim)
def pins_high(b): return [i for i, o in enumerate(b.model['outputs']) if b.level(o[0])]
fan_seen = []; t_ = b5.now
while b5.now < t_ + 10_000_000: b5.run_for(500); fan_seen.append(tuple(tuple(pins_high(f5[k])) for k in ('A1', 'A2', 'B')))
check('fans: power-up at room temperature (30 C on all three boards): A2 OUT2 never on (every 5 ms for 1.5 s from power-up, then every 0.5 s for 10 s), status Off; no other output on',
      sum(fan_boot) == 0 and all(p == ((), (), ()) for p in fan_seen) and st5['A2'].out_state(fo) == 0, (sum(fan_boot), fan_seen[-1], st5['A2'].out_state(fo)))
# Fans follow the hottest board (Dan s12a on 45 / off 40 C, s13a A2 + A1 + B); default config only, no ECU
fan_edges = [0]
def fan_at(a1=None, a2=None, b=None, ms=700):
    for k, c in (('A1', a1), ('A2', a2), ('B', b)):
        if c is not None: f5[k].set_temp(c)
    last = a2f.level(FAN_IN)
    for _ in range(ms // 10):
        b5.run_for(10); v = a2f.level(FAN_IN); fan_edges[0] += v != last; last = v
    return last
seq = [(c, fan_at(a2=c)) for c in (44.5, 45.0, 42.0, 40.5, 40.0, 44.0, 46.0, 39.0)]
check('fan on A2\'s own sensor: off at 44.5, on at 45.0, stays on at 42.0 / 40.5, off at 40.0, stays off at 44.0, on at 46.0, off at 39.0',
      [v for c, v in seq] == [0, 1, 1, 1, 0, 0, 1, 0], seq)
fan_edges[0] = 0; off_band = [fan_at(a2=c, ms=400) for c in [44.5, 40.5] * 6]
fan_at(a2=45.5); fan_edges[0] = 0; on_band = [fan_at(a2=c, ms=400) for c in [40.5, 44.5] * 6]; chatter = fan_edges[0]
fan_at(a2=30.0)
check('fan: no chatter between the limits (44.5 / 40.5 C x6 from off stays off, from on stays on; no edge at all, 10 ms samples)',
      off_band == [0] * 12 and on_band == [1] * 12 and chatter == 0, (off_band, on_band, chatter))
seq = [('A1 46', fan_at(a1=46.0)), ('A1 41', fan_at(a1=41.0)), ('A1 40', fan_at(a1=40.0)), ('B 45.5', fan_at(b=45.5)), ('B 39.5', fan_at(b=39.5)),
       ('A1 47', fan_at(a1=47.0)), ('B 42', fan_at(b=42.0)), ('A1 35', fan_at(a1=35.0)), ('B 38', fan_at(b=38.0))]
check('fan follows the hottest board over CAN (A2 at 30 C): on when only A1 (46 C) or only B (45.5 C) is hot; off only once every board is <= 40 C (B at 42 keeps it on after A1 cools)',
      [v for n, v in seq] == [1, 1, 0, 1, 0, 1, 1, 1, 0], seq)
# a remote board's temperature stops arriving (CAN loss): its CAN inputs time out (1 s) to 0 = neither hot nor cool
bb = f5['B']; fan_at(b=47.0); pre = a2f.level(FAN_IN); bb.connected = False; bb.set_temp(30.0)
lost_on = fan_at(ms=2500); bb.connected = True; back = fan_at(ms=800)
check('remote reading lost while it was hot (B 47 C, then B off the bus and cooling): fan stays on for 2.5 s (a missing reading is not "cool"); off once B is back at 30 C',
      (pre, lost_on, back) == (1, 1, 0), (pre, lost_on, back))
bb.connected = False; quiet = fan_at(ms=1500); local = fan_at(a2=46.0); held = fan_at(a2=35.0, ms=1500); bb.connected = True; back = fan_at(ms=800)
check('remote reading lost while cool: fan stays off (no vote either way); A2\'s own 46 C still turns it on; with B missing it stays on at A2 35 C; off once B is back (30 C)',
      (quiet, local, held, back) == (0, 1, 1, 0), (quiet, local, held, back))
f5['A1'].set_temp(47.5, 63.0); f5['A2'].set_temp(52.0, 41.0); b5.run_for(800)
tv = {k: (st5[k].board_temp_x10(), st5[k].die_temp_x10()) for k in ('A1', 'A2')}
want = {'A1': (475, ps.die_temp_can(63.0)), 'A2': (520, ps.die_temp_can(41.0))}
check('temperatures on CAN: board (MCP9808, msg 0) and STM32 die (msg 27) x10 track their own set values on each board',
      all(tv[k][0] == want[k][0] and abs(tv[k][1] - want[k][1]) <= 4 for k in tv), f'got {tv}, want {want}')
info['die_temp_x10'] = tv
# Dan s10b: outputs exempt from the critical shutdown (device param 8, bit i = output i); default = the fan output
ex = {k: t5.read(BASE[k], ps.TEMP_INDEX, ps.TEMP_EXEMPT_SUB) for k in f5}
check('critical-exempt outputs (param 0x7F00 sub 3): factory default = the fan output only (A2 bit 1 = 2), none on A1 and B', ex == {'A1': 0, 'A2': 2, 'B': 0}, ex)
a2 = f5['A2']; t5.write(BASE['A2'], 0x1000, 0, 1); t5.write(BASE['A2'], 0x1000, 1, 1)    # A2 OUT1 on (always true), not exempt
a2.set_load(0, a2.vbat / 3.0); a2.set_load(fo, a2.vbat / 0.12); a2.set_temp(50.0); b5.run_for(700); pre = pins_high(a2)   # 50 C: fan on (>= 45)
a2.set_temp(80.0); b5.run_for(400); hot = (pins_high(a2), st5['A2'].dev_state()); a2.set_temp(70.0); b5.run_for(400); back = pins_high(a2)
check('A2 at critical (80 C): the exempt fan output OUT2 stays on, the non-exempt OUT1 goes off (state OverTemp); OUT1 back at 70 C',
      pre == [0, 1] and hot == ([1], 2) and back == [0, 1], (pre, hot, back))

# configured board A1 (single-PDM config from S2), ECU commanding A1 outputs 1, 2, 4
b6 = ps.Bus(); t6 = ps.Tool(b6); e6 = ps.PyNode('ecu'); a1 = ps.Board(ps.BOARD_A, 'A1', SO, fram=frams2['A1'])
st6 = ps.Status(BASE['A1']); b6.watch.append(st6.feed); infos = []
b6.watch.append(lambda f: infos.append((f.t, f.data[1], struct.unpack('<H', f.data[2:4])[0], struct.unpack('<H', f.data[4:6])[0])) if f.id == BASE['A1'] and f.data[0] == ord('E') else None)
e6.every(20000, lambda t: e6.send(ECU_ID, bytes([0b1011, 0, 0, 0xA5, 0, 0, 0, 0])), 5000)
b6.add(t6, e6, a1)
for o_ in range(8): a1.set_load(o_, a1.vbat / 4.0)
b6.run_for(1500); CMD_ON = [0, 1, 3]
def temp_step(c, ms=400): a1.set_temp(c); b6.run_for(ms); return pins_high(a1)
p_cool = temp_step(40.0); s_cool = st6.dev_state()
p_warn = temp_step(56.0); s_warn = st6.dev_state(); m_warn = [x for x in infos if x[1] == 3]
s_hold = (temp_step(53.6), st6.dev_state()); s_clear = (temp_step(53.4), st6.dev_state())
check('above warn (56 C > 55): state OverTemp, one CAN error message (State_Overtemp, 560), outputs unchanged',
      p_cool == CMD_ON and s_cool == 0 and p_warn == CMD_ON and s_warn == 2 and len(m_warn) == 1 and m_warn[0][2] == 560, (p_cool, s_cool, p_warn, s_warn, m_warn))
check('warn clears only below warn - 1.5 C (stock MCP9808 hysteresis): 53.6 C still OverTemp, 53.4 C Run',
      s_hold == (CMD_ON, 2) and s_clear == (CMD_ON, 0), (s_hold, s_clear))
p77 = temp_step(77.0); v_shed = [a1.L.sim_var(a1.var_virt(ps.SHED['virt0'] + l)) for l in (0, 1)]
check('load-shed example ships disabled: at 77 C (above both example levels, below critical) no output is shed', p77 == CMD_ON and v_shed == [0.0, 0.0], (p77, v_shed))
infos.clear(); t_ = b6.now; a1.set_temp(80.0); t_off = None
while b6.now < t_ + 1_000_000:
    b6.run_for(2)
    if t_off is None and not pins_high(a1): t_off = round((b6.now - t_) / 1000)
m_crit = [x for x in infos if x[1] == 9]
check('at critical (80 C): every output off within one sensor read, state OverTemp, CAN error message (Overtemp, 800, limit 800), no fatal error',
      pins_high(a1) == [] and t_off is not None and t_off <= 260 and st6.dev_state() == 2 and len(m_crit) == 1 and m_crit[0][2:] == (800, 800) and not a1.flags()['fatal'],
      (t_off, pins_high(a1), st6.dev_state(), m_crit, a1.flags()))
info['crit_off_ms'] = t_off
edges = 0; last = pins_high(a1)
for c in [79.5, 80.0] * 8 + [77.0, 74.0, 74.5, 74.0]:
    p = temp_step(c, 300); edges += p != last; last = p
check('critical: no chatter at the limit (79.5 / 80.0 C x8) and still off at 74.0 C (recovery is below 80 - 6 = 74)', edges == 0 and last == [], (edges, last))
t_ = b6.now; a1.set_temp(73.5); t_on = None
while b6.now < t_ + 1_000_000:
    b6.run_for(2)
    if t_on is None and pins_high(a1) == CMD_ON: t_on = round((b6.now - t_) / 1000)
edges = 0; last = pins_high(a1)
for c in [74.5, 73.5] * 8 + [79.5]:
    p = temp_step(c, 300); edges += p != last; last = p
check('critical recovers by itself at 73.5 C (no power cycle), then no chatter at 73.5 / 74.5 C and stays on at 79.5 C',
      t_on is not None and t_on <= 260 and edges == 0 and last == CMD_ON and not a1.flags()['fatal'], (t_on, edges, last))
info['crit_recover_ms'] = t_on
# limits changed over CAN act at once (no restart)
ok_w = all(t6.write(BASE['A1'], ps.TEMP_INDEX, ps.TEMP_PARAM[n], v) is not None for n, v in (('warn', 50), ('crit', 70), ('hyst', 4)))
rd = {n: t6.read(BASE['A1'], ps.TEMP_INDEX, sub) for n, sub in ps.TEMP_PARAM.items()}
seq = [(c, temp_step(c), st6.dev_state()) for c in (45.0, 51.0, 69.5, 70.0, 66.5, 65.5)]
check('limits set over CAN (warn 50, critical 70, recovery 4) act at once: 51 C OverTemp, 70 C all off, 66.5 C still off, 65.5 C back on',
      ok_w and rd == {'warn': 50, 'crit': 70, 'hyst': 4, 'soon': 5} and [(p, s) for c, p, s in seq] == [(CMD_ON, 0), (CMD_ON, 2), (CMD_ON, 2), ([], 2), ([], 2), (CMD_ON, 2)], (rd, seq))
for n in ('warn', 'crit', 'hyst'): t6.write(BASE['A1'], ps.TEMP_INDEX, ps.TEMP_PARAM[n], ps.TEMP_DEFAULT[n])
temp_step(40.0)
# the prefilled load-shed example, enabled as documented (docs/firmware-thermal-plan.md section 7):
# output 1 sheds at level 0 (70 C, back at 65 C), output 2 at level 1 (75 C, back at 70 C), output 4 is never shed
S = ps.SHED
for i in range(4): t6.write(BASE['A1'], 0x1500 + S['cond0'] + i, 0, 1)
for l in (0, 1): t6.write(BASE['A1'], 0x1400 + S['virt0'] + l, 0, 1)
for o_, l, v in ((0, 0, 1), (1, 1, 2)):                       # VI v = command AND NOT latch(l); output input = VI v
    for sub, val in [(2, a1.var_canin(o_)), (3, 0), (4, 1), (5, a1.var_virt(S['virt0'] + l)), (8, 0), (0, 1)]: t6.write(BASE['A1'], 0x1400 + v, sub, val)
    t6.write(BASE['A1'], 0x1000 + o_, 1, a1.var_virt(v))
seq = [(c, temp_step(c)) for c in (60.0, 69.5, 70.0, 74.5, 75.0, 79.0, 72.0, 70.5, 70.0, 66.0, 65.5, 65.0)]
want = [CMD_ON, CMD_ON, [1, 3], [1, 3], [3], [3], [3], [3], [1, 3], [1, 3], [1, 3], CMD_ON]
check('load-shed example enabled: low priority (out 1) off at 70 C, high priority (out 2) off at 75 C, out 4 never; each returns at its own lower limit (70 / 65 C)',
      [p for c, p in seq] == want, seq)

# ------------------------------------------------------------------ S5 MCP9808 reads and wake-up (sleep fix, Dan s7a)
print('--- S5 warn before critical, sensor reads, wake-up')
# Dan: over-temperature should be avoidable from CAN warnings first. Rising ramp on A1: warn 55, critical 80.
infos.clear()
for c in [50.0 + 0.5 * k for k in range(61)]: a1.set_temp(c); b6.run_for(300)
w_ = [x for x in infos if x[1] == 3]; c_ = [x for x in infos if x[1] == 9]
check('rising ramp 50 -> 80 C (0.5 C every 300 ms): the warn message (State_Overtemp, 55.5 C) comes once, about 14 s before the critical message (Overtemp, 80.0 C)',
      len(w_) == 1 and w_[0][2] == 555 and len(c_) == 1 and c_[0][2] == 800 and c_[0][0] - w_[0][0] >= 10_000_000, (w_, c_))
a1.set_temp(40.0); b6.run_for(600)
# Dan s11c: steady thermal flags in every cyclic msg 3 (byte 7) + a one-shot critical-soon event (A1, limits 55 / 80 / 6, margin 5)
fl3 = []; ev = []
b6.watch.append(lambda f: fl3.append((f.t, f.data[7])) if f.id == BASE['A1'] + 2 + 3 else None)
b6.watch.append(lambda f: ev.append((f.data[0], f.data[1]) + struct.unpack('<HHH', f.data[2:8])) if f.id == BASE['A1'] and f.data[0] in (ord('R'), ord('E')) else None)
W_, S_, C_ = ps.FLAG_WARN, ps.FLAG_SOON, ps.FLAG_CRIT
FSEQ = [(50.0, 0), (55.0, 0), (55.5, W_), (54.0, W_), (53.0, 0), (60.0, W_), (74.5, W_), (75.0, W_ | S_), (74.0, W_ | S_), (73.0, W_),
        (76.0, W_ | S_), (80.0, W_ | C_), (77.0, W_ | C_), (73.5, W_), (40.0, 0)]
bad = []; t_s = b6.now
for c, want in FSEQ:
    a1.set_temp(c); t0_ = b6.now; b6.run_for(700)
    got = [x for t, x in fl3 if t >= t0_ + 400_000]
    if len(got) < 2 or any(x != want for x in got): bad.append((c, want, got))
gaps = [b_ - a_ for (a_, _), (b_, _) in zip(fl3, fl3[1:]) if a_ >= t_s]
check('thermal flags, msg 3 byte 7 (bit 0 warn > 55 / clears < 53.5; bit 1 critical soon >= 75 / clears < 73.5 or at critical; bit 2 critical >= 80 / clears < 74): right in every frame of a 15-step ramp',
      not bad, bad)
check('msg 3 (with the flags) goes out every 100 ms through the whole ramp: no frame missing', gaps and max(gaps) <= 120_000, max(gaps) if gaps else None)
soon_ev = [e for e in ev if e[0] == ord('R') and e[1] == 9]
check('critical-soon event (type Warning R, src Overtemp 9; temp x10, critical x10, margin): once per entry - 75.0 C, then 76.0 C after it cleared at 73.0 C',
      [e[2:] for e in soon_ev] == [(750, 800, 5), (760, 800, 5)], soon_ev)
ok_m = t6.write(BASE['A1'], ps.TEMP_INDEX, ps.TEMP_PARAM['soon'], 8) is not None
m8 = []
for c in (71.5, 72.0, 40.0): a1.set_temp(c); b6.run_for(700); m8.append(fl3[-1][1])
ok_0 = t6.write(BASE['A1'], ps.TEMP_INDEX, ps.TEMP_PARAM['soon'], 0) is not None; a1.set_temp(79.5); b6.run_for(700); m0 = fl3[-1][1]
t6.write(BASE['A1'], ps.TEMP_INDEX, ps.TEMP_PARAM['soon'], 5); a1.set_temp(40.0); b6.run_for(700)
check('critical-soon margin set over CAN (0x7F00 sub 4) acts at once: margin 8 -> flag at 72.0 C, not 71.5 C; margin 0 -> no flag even at 79.5 C',
      ok_m and ok_0 and m8 == [W_, W_ | S_, 0] and m0 == W_, (ok_m, ok_0, m8, m0))
# A failed I2C read is "no reading": it must never trip or clear critical. Board A1 from S4 (ECU commands outputs 1, 2, 4).
TS = 14                                           # MsgSrc::TempSensor
def ts_msgs(): return [x for x in infos if x[1] == TS]
infos.clear(); seen0 = (temp_step(40.0), st6.dev_state())
a1.mcp_fail(-1); a1.set_temp(90.0); b6.run_for(2000)          # the sensor would say 90 C if it could be read
hold_w = (pins_high(a1), st6.dev_state(), st6.board_temp_x10()); m_w = ts_msgs()
a1.mcp_fail(0); trip = (temp_step(90.0), st6.dev_state())
check('reads fail while cool (40 C) and the board heats to 90 C: no trip for 2 s (outputs on, state Run, msg 0 keeps 40.0 C); the first good read trips critical',
      seen0 == (CMD_ON, 0) and hold_w == (CMD_ON, 0, 400) and trip == ([], 2), (seen0, hold_w, trip))
check('8 failed reads in a row: exactly one CAN error message, src TempSensor (14), count 4', len(m_w) == 1 and m_w[0][2] == 4, m_w)
infos.clear(); a1.mcp_fail(-1); a1.set_temp(40.0); b6.run_for(2000)    # in critical now; it cools while reads fail
hold_c = (pins_high(a1), st6.dev_state(), st6.board_temp_x10()); n_fail = a1.mcp_info()['fw_fails']
a1.mcp_fail(0); b6.run_for(400); rec = (pins_high(a1), st6.dev_state(), st6.board_temp_x10(), a1.mcp_info()['fw_fails'])
check('in critical (90 C), reads fail while it cools to 40 C: critical held for 2 s (all off, msg 0 keeps 90.0 C); good reads clear it (outputs back, Run, 40.0 C, count 0)',
      hold_c == ([], 2, 900) and n_fail >= 7 and rec == (CMD_ON, 0, 400, 0), (hold_c, n_fail, rec))
infos.clear(); a1.mcp_fail(3); b6.run_for(1500); m3 = ts_msgs(); a1.mcp_fail(4); b6.run_for(1500); m4 = ts_msgs()
check('fault message threshold: 3 failed reads then good ones = no message; later 4 in a row = one message again (count 4)', m3 == [] and len(m4) == 1 and m4[0][2] == 4, (m3, m4))
# Wake-up = MCU reset without a power-on reset: the MCP9808 is still in shutdown and holds 85 C from before sleep
# until its first conversion; the board is at 41 C now. Board A1 with the S2 config, no ECU on the bus.
b7 = ps.Bus(); t7 = ps.Tool(b7); w7 = ps.Board(ps.BOARD_A, 'A1', SO, fram=frams2['A1']); w7.mcp_carry(85.0); w7.set_temp(41.0)
temps7 = []; errs7 = []
b7.watch.append(lambda f: temps7.append(struct.unpack('<H', f.data[6:8])[0]) if f.id == BASE['A1'] + 2 else None)
b7.watch.append(lambda f: errs7.append(f.data[1]) if f.id == BASE['A1'] and f.data[0] == ord('E') else None)
b7.add(t7, w7); b7.run_for(20)
den7 = {o[1]: w7.level(o[1]) for o in w7.model['outputs']}; mi0 = w7.mcp_info()          # before main() runs (500 ms)
b7.run_for(1500); mi1 = w7.mcp_info()
check('wake-up: DEN high on every channel before the firmware starts (Profet constructor), sensor back to continuous with alert on',
      all(v == 1 for v in den7.values()) and (mi0['shutdown'], mi0['alert_on']) == (1, 0) and (mi1['shutdown'], mi1['alert_on']) == (0, 1), (den7, mi0, mi1))
check('wake-up: the stale 85 C is never used (msg 0 only 0 = no reading yet, then 41.0 C; no over-temp or critical message)',
      temps7 and set(temps7) <= {0, 410} and temps7[-1] == 410 and not (set(errs7) & {3, 9}), (sorted(set(temps7)), errs7))
bad = [r for r in res if not r[1]]
print(f'\nS1-S5: {len(res) - len(bad)} of {len(res)} checks passed'); print(json.dumps(info))
json.dump(dict(checks=res, info=info, matrix=matrix), open('/tmp/s1_results.json', 'w'), indent=1)
