"""S1-S7: three boards in one box as one PDM. Commissioning, a PC-side 'single PDM' layer on stock
firmware logic, what outputs do when a CAN link is lost (three policies), thermal protection + fans (S4),
MCP9808 read failures + wake-up from sleep (S5), the wake-up input set (S6, Dan B2), and per-output link loss
with a start-up wait and critical outputs, stock params only (S7, Dan w1).
IDs used here: the factory base IDs, boards 0x500 / 0x540 / 0x580 (pdmsim.py BOARD_*), ECU command frame 0x4F0."""
import sys, json, struct, pdmsim as ps
SO = sys.argv[1] if len(sys.argv) > 1 else '/tmp/simout'
BASE = {'A1': ps.BOARD_A['base'][1], 'A2': ps.BOARD_A['base'][2], 'B': ps.BOARD_B['base'][1]}; ECU_ID = 0x4F0; ALIVE_SLOT = 31; TIMEOUT_MS = 1000   # Dan D3a: 1 s default (also the firmware default), adjustable per channel
res = []; info = {}
def check(name, ok, detail=''):
    res.append((name, bool(ok), str(detail))); print(('PASS ' if ok else 'FAIL ') + name + (' : ' + str(detail) if detail != '' else ''))

# ------------------------------------------------------------------ S1 commissioning
print('--- S1 commissioning')
# three fresh boards, each flashed with its own build (A unit 1, A unit 2, B): no setup needed
bus = ps.Bus(); tool = ps.Tool(bus)
fresh = {'A1': ps.Board(ps.BOARD_A, 'A1', SO, unit=1), 'A2': ps.Board(ps.BOARD_A, 'A2', SO, unit=2), 'B': ps.Board(ps.BOARD_B, 'B', SO)}
bus.add(tool, *fresh.values()); bus.run_for(1500)
check('three fresh boards come up at 1 Mbit/s and each answers alone on its own built-in ID', all(b.bitrate() == 1000000 for b in fresh.values()) and all(tool.version(BASE[k]) == ps.FW_VERSION for k in fresh), [hex(v) for v in BASE.values()])
frams = {k: b.fram() for k, b in fresh.items()}
# option b stays available: move a board to another ID / bit rate over CAN, save, restart
b1 = ps.Bus(); t1 = ps.Tool(b1); x = ps.Board(ps.BOARD_A, 'A1', SO, unit=1); b1.add(t1, x); b1.run_for(1200)
ok = t1.write(0x500, 0x0000, 0, 0x6A0, reply_base=0x6A0) is not None and t1.write(0x6A0, 0x0000, 1, 1) is not None and t1.burn(0x6A0)
b1 = ps.Bus(); t1 = ps.Tool(b1, 500000); y = ps.Board(ps.BOARD_A, 'A1', SO, unit=1, fram=x.fram()); b1.add(t1, y); b1.run_for(1200)
check('manual setup still works: ID and bit rate changed over CAN, saved, kept after a restart', ok and y.bitrate() == 500000 and t1.version(0x6A0) == ps.FW_VERSION, y.bitrate())

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
check('each board answers alone on its own ID', all(tool.version(BASE[k]) == ps.FW_VERSION for k in boards))
# s15a port: dingoFW development sends base + 2 + n for n = 0..37 (40 IDs with base + 0 / + 1), so 0x20 spacing overlapped
bus.log = []; bus.run_for(1000); ids = {k: sorted({f.id for f in bus.log if f.src == k and not f.ide}) for k in boards}; bus.log = None
blocks = {k: range(BASE[k], BASE[k] + 2 + ps.NUM_TX_MSGS) for k in boards}
check(f'CAN IDs: every frame a board sends lies in its own block base .. base + {1 + ps.NUM_TX_MSGS:#x} (status msg {ps.STATUS_MSG} = base + {2 + ps.STATUS_MSG:#x} the highest), and the three blocks do not overlap',
      all(ids[k] and set(ids[k]) <= set(blocks[k]) and ids[k][-1] == BASE[k] + 2 + ps.STATUS_MSG for k in boards)
      and all(not (set(blocks[a]) & set(blocks[b])) for a in boards for b in boards if a < b), {k: (hex(v[0]), hex(v[-1]), len(v)) if v else None for k, v in ids.items()})

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
        sk, si = INP[source[1]]; can_input(k, slot, BASE[sk] + 2 + ps.STATUS_MSG, si, timeout=policy != 'hold')   # other board's input bit (status msg)
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
check(f'temperatures on CAN: board (MCP9808, msg 0) and STM32 die (msg {ps.STATUS_MSG}) x10 track their own set values on each board',
      all(tv[k][0] == want[k][0] and abs(tv[k][1] - want[k][1]) <= 4 for k in tv), f'got {tv}, want {want}')
info['die_temp_x10'] = tv
# Dan s10b: outputs exempt from the critical shutdown (param 0x7F00 sub 3, bit i = output i); default = the fan output
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

# ------------------------------------------------------------------ S6 wake-up set (Dan B2): param 0x7F00 sub 5
print('--- S6 wake-up set')
WI = ps.TEMP_INDEX; WS = ps.WAKE_SUB
CANUSB = {8: 'PB8', 11: 'PA11', 12: 'PA12'}             # CAN RX + USB D- / D+, armed on every sleep (CAN wake on)
def wake_board(model, name):
    bus = ps.Bus(); t = ps.Tool(bus); b = ps.Board(model, name, SO); bus.add(t, b); bus.run_for(1200)
    return bus, t, b, model['base'][1]
def asleep_lines(model, name, writes):
    """Fresh board, the given param writes (each must be answered), sleep request: the EXTI lines armed in sleep."""
    bus, t, b, base = wake_board(model, name)
    ok = all(t.write(base, i, s_, v) is not None for i, s_, v in writes)
    t.sleep(base); bus.run_for(300)
    return ok and b.flags()['asleep'], ps.exti_lines(b), b.counters()['exti_clashes']
def refused(t, base, mask):
    """Single Write of a wake mask: (write reply?, warning frames ('R', src Config) as (data0, data1, data2), read-back)."""
    r = t.write(base, WI, WS, mask)
    w = [struct.unpack('<HHH', f.data[2:8]) for f in t.rxlog if f.id == base and f.data[0] == ord('R') and f.data[1] == ps.SRC_CONFIG]
    return r is not None, w, t.read(base, WI, WS)
A_IN = {i: p for i, (p, _) in enumerate(ps.BOARD_A['inputs'])}; B_IN = {i: p for i, (p, _) in enumerate(ps.BOARD_B['inputs'])}
def lines_of(pins): return {int(p[2:]): p for p in pins}
# one input wakes: A IN_2 (PC9); the old build-time set A 0x73 / B 0x0FF; A IN_3 (PC10) takes EXTI 10 when IN_1 is not set
r = {k: asleep_lines(m, n_, [(WI, WS, v)]) for k, (m, n_, v) in {'A 0x002': (ps.BOARD_A, 'A1', 0x002), 'A 0x073': (ps.BOARD_A, 'A1', 0x073),
     'A 0x004': (ps.BOARD_A, 'A1', 0x004), 'B 0x0FF': (ps.BOARD_B, 'B', 0x0FF), 'B 0x1FE': (ps.BOARD_B, 'B', 0x1FE)}.items()}
want = {'A 0x002': lines_of([A_IN[1]]), 'A 0x073': lines_of([A_IN[i] for i in (0, 1, 4, 5, 6)]), 'A 0x004': lines_of([A_IN[2]]),
        'B 0x0FF': lines_of([B_IN[i] for i in range(8)]), 'B 0x1FE': lines_of([B_IN[i] for i in range(1, 9)])}
check('wake mask set over CAN: exactly its inputs are armed in sleep, plus CAN RX and USB, no EXTI clash (A IN_2; A IN_1,2,5,6,7; A IN_3 alone on EXTI 10; B IN_1-8; B IN_2-9 with B_IN9 on EXTI 10)',
      all(v[0] and v[1] == want[k] | CANUSB and v[2] == 0 for k, v in r.items()), r)
info['wake_lines'] = {k: v[1] for k, v in r.items()}
# Shared lines and the USB line are refused: no write reply (upstream: an out-of-range Write gets none), one warning
# frame (refused mask, its bad inputs, the mask kept), the mask stays as it was, and sleep arms the old set
bus, t, b, base = wake_board(ps.BOARD_A, 'A1'); t.write(base, WI, WS, 0x002)
ra = {m: refused(t, base, m) for m in (0x005, 0x008, 0x00D)}
t.sleep(base); bus.run_for(300); la = ps.exti_lines(b)
check('board A: IN_1 + IN_3 (0x005, both on EXTI 10) and IN_4 (0x008, EXTI 11 = USB D-) refused: no Write reply, one CAN warning (R, src Config: refused mask, bad inputs, mask kept 0x002), mask stays 0x002',
      ra == {0x005: (False, [(0x005, 0x005, 0x002)], 0x002), 0x008: (False, [(0x008, 0x008, 0x002)], 0x002), 0x00D: (False, [(0x00D, 0x00D, 0x002)], 0x002)}, ra)
check('board A: after the refused writes, sleep arms the kept mask (IN_2 / PC9) only', b.flags()['asleep'] and la == lines_of([A_IN[1]]) | CANUSB, la)
bus, t, b, base = wake_board(ps.BOARD_B, 'B'); t.write(base, WI, WS, 0x0FF)
rb = {m: refused(t, base, m) for m in (0x101, 0x200, 0x3FF)}
check('board B: IN_1 + B_IN9 (0x101, EXTI 10), B_IN10 (0x200, EXTI 11 = USB D-) and all ten (0x3FF; bad = IN_1, B_IN9, B_IN10) refused the same way, mask stays 0x0FF',
      rb == {0x101: (False, [(0x101, 0x101, 0x0FF)], 0x0FF), 0x200: (False, [(0x200, 0x200, 0x0FF)], 0x0FF), 0x3FF: (False, [(0x3FF, 0x301, 0x0FF)], 0x0FF)}, rb)
ro = refused(t, base, 0x400)
check('board B: a bit above the last input (0x400, input 11) is out of range: no reply, no warning (stock range check), mask stays 0x0FF', ro == (False, [], 0x0FF), ro)
# full WriteAll (what dingoConfig does on "write all"): a refused mask gets the stock WriteAllOutOfRange reply
t.rxlog.clear(); t.send(base + 1, bytes([ps.CMD['WriteAllVal'], WI & 255, WI >> 8, WS]) + struct.pack('<I', 0x101)); bus.run_for(50)
oor = [(f.data[1] | f.data[2] << 8, f.data[3], struct.unpack('<I', f.data[4:8])[0]) for f in t.rxlog if f.id == base and f.data[0] == ps.WRITE_ALL_OUT_OF_RANGE]
wn = [f for f in t.rxlog if f.id == base and f.data[0] == ord('R') and f.data[1] == ps.SRC_CONFIG]
check('board B: WriteAllVal with a refused mask (0x101) -> stock WriteAllOutOfRange reply (0x7F00 / 5 / 0x101) plus the warning frame',
      oor == [(WI, WS, 0x101)] and len(wn) == 1, (oor, len(wn)))
# DisableDigInWake (0x0000 sub 4, upstream) wins over the mask
d = asleep_lines(ps.BOARD_A, 'A1', [(WI, WS, 0x073), (0x0000, 4, 1)])
check('DisableDigInWake on (0x0000 sub 4) with mask 0x73: no input armed, CAN and USB still are', d[0] and d[1] == CANUSB, d)
# digital-input PWM measurement uses the same EXTI line: sleep stops it first, so it neither blocks nor steals a wake line
bus, t, b, base = wake_board(ps.BOARD_A, 'A1')
for i_ in (1, 2):                                           # IN_2 (PC9) and IN_3 (PC10) measure PWM
    t.write(base, 0x1200 + i_, 5, 1); t.write(base, 0x1200 + i_, 0, 1)
run_pwm = ps.exti_lines(b); t.write(base, WI, WS, 0x003)    # IN_1 (PA10, same EXTI 10 as IN_3) + IN_2 may wake
t.sleep(base); bus.run_for(300); slp = (ps.exti_lines(b), b.counters()['exti_clashes'])
check('PWM inputs: IN_2 / IN_3 measuring PWM (EXTI 9 / 10 on port C while awake), mask IN_1 + IN_2: sleep arms PA10 and PC9 (IN_3 PWM stopped first), no clash',
      run_pwm == {9: 'PC9', 10: 'PC10'} and slp == (lines_of([A_IN[0], A_IN[1]]) | CANUSB, 0), (run_pwm, slp))
# saved with the rest of the config, kept after a restart
bus, t, b, base = wake_board(ps.BOARD_A, 'A1'); t.write(base, WI, WS, 0x042); sv = t.burn(base)
bus2 = ps.Bus(); t2 = ps.Tool(bus2); b2_ = ps.Board(ps.BOARD_A, 'A1', SO, fram=b.fram()); bus2.add(t2, b2_); bus2.run_for(1200)
kept = t2.read(base, WI, WS)
check('wake mask (0x042, IN_2 + IN_7) saved to FRAM and read back after a restart', sv and kept == 0x042, (sv, kept))

# ------------------------------------------------------------------ S7 per-output link loss + start-up wait (Dan w1, 2026-11-16)
print('--- S7 per-output link loss, start-up wait, critical outputs')
# Stock params only (no firmware change). Output board Q = A1, source board P = B: P's input 3 (index 2) is bit 2 of P's msg 37.
# Per source board, shared by all its links on Q:
#   ALIVE = CAN input on P's msg 37, bit 0, '>= 0' (true for every frame), time-out on (1 s): 1 while P's frames arrive
#   SEEN  = the same with the time-out off: 0 until P's first frame after Q powers up, then 1 until Q restarts
#   LOST  = virtual input 'SEEN AND NOT ALIVE' (lower index than the link virtual inputs that use it)
# Per link: L = CAN input on bit 2, Equal 1, time-out on (off for hold). Output trigger per loss setting:
#   off = L | hold = L (time-out off) | on = LOST OR L | condition C = (LOST AND C) OR L
#   critical outputs: NOT ALIVE in place of LOST (no start-up wait). b4_on = today's B4 'On' (slot Equal 0, 'NOT slot OR false').
P_MSG37 = BASE['B'] + 2 + ps.STATUS_MSG; P_BIT = 2; IGN = 0       # IGN = A1 direct input 1 (index 0), the example condition
S7 = dict(off=0, hold=1, on=2, on_crit=3, cond=4, cond_crit=5, b4_on=6)   # A1 output index per case
NONCRIT = ('off', 'hold', 'on', 'cond'); AND, OR, EQ, GE = 0, 1, 0, 4; s7_first_data = []
def s7_config(lost_vi=0):
    bq = ps.Bus(); tq = ps.Tool(bq); q = ps.Board(ps.BOARD_A, 'A1', SO, fram=frams['A1']); p = ps.Board(ps.BOARD_B, 'B', SO, fram=frams['B'])
    bq.add(tq, q, p); bq.run_for(1200)
    def Wq(index, sub, val):
        if tq.write(BASE['A1'], index, sub, val) is None: raise RuntimeError(f'S7: no reply A1 {index:#x}/{sub}')
    def slot(n, bit, op, operand, timeout):
        for sub, val in [(4, P_MSG37), (5, bit), (6, 1), (7, ps.f32(1.0)), (11, op), (12, ps.f32(operand)), (2, TIMEOUT_MS), (1, int(timeout)), (0, 1)]: Wq(0x1300 + n, sub, val)
    def virt(n, v0, n0, c0, v1, n1=0, c1=0, v2=0, n2=0):
        for sub, val in [(1, n0), (2, v0), (3, c0), (4, n1), (5, v1), (6, c1), (7, n2), (8, v2), (0, 1)]: Wq(0x1400 + n, sub, val)
    def out(o, var):
        for sub, val in [(2, ps.f32(7.5)), (3, ps.f32(15.0)), (1, var), (0, 1)]: Wq(0x1000 + o, sub, val)
    Wq(0x1200 + IGN, 0, 1); tq.write(BASE['B'], 0x1200 + P_BIT, 0, 1)
    slot(0, 0, GE, 0.0, True); slot(1, 0, GE, 0.0, False)
    ALIVE, SEEN, LOST, IGNV = q.var_canin(0), q.var_canin(1), q.var_virt(lost_vi), q.var_di(IGN)
    virt(lost_vi, SEEN, 0, AND, ALIVE, 1)
    L = {k: q.var_canin(2 + o) for k, o in S7.items()}
    for k, o in S7.items(): slot(2 + o, P_BIT, EQ, 0.0 if k == 'b4_on' else 1.0, k != 'hold')
    out(S7['off'], L['off']); out(S7['hold'], L['hold'])
    virt(1, LOST, 0, OR, L['on']); out(S7['on'], q.var_virt(1))
    virt(2, ALIVE, 1, OR, L['on_crit']); out(S7['on_crit'], q.var_virt(2))
    virt(3, LOST, 0, AND, IGNV, 0, OR, L['cond']); out(S7['cond'], q.var_virt(3))
    virt(4, ALIVE, 1, AND, IGNV, 0, OR, L['cond_crit']); out(S7['cond_crit'], q.var_virt(4))
    virt(5, L['b4_on'], 1, OR, 0); out(S7['b4_on'], q.var_virt(5))
    ok = tq.burn(BASE['A1']) and tq.burn(BASE['B'])
    return ok, (q.fram(), p.fram())
def s7_run(fr, p_bit, ign, p_on_ms, total_ms, loss=None, step=0.5):
    """Q (A1) and P (B) power up at t = 0; P is off the bus until p_on_ms (None = never) and inside loss = (t_off, t_back).
    Returns the time of Q's first msg-37 frame from P (ms) and per case a list of [on_ms, off_ms] intervals of the IN pin."""
    bus = ps.Bus(); ack = ps.PyNode('another node'); q = ps.Board(ps.BOARD_A, 'A1', SO, fram=fr[0]); p = ps.Board(ps.BOARD_B, 'B', SO, fram=fr[1])
    bus.add(ack, q, p)
    p.set_input(P_BIT, '12v' if p_bit else 'gnd', 'up'); q.set_input(IGN, '12v' if ign else 'gnd')
    for o in range(8): q.set_load(o, q.vbat / 4.5)
    first = []; bus.watch.append(lambda f: first.append(f.t / 1000) if f.id == P_MSG37 and not first else None)
    s7_first_data.clear(); bus.watch.append(lambda f: s7_first_data.append(f.data) if f.id == P_MSG37 and not s7_first_data else None)
    pins = {k: q.model['outputs'][o][0] for k, o in S7.items()}; iv = {k: [] for k in S7}
    while bus.now < total_ms * 1000:
        t = bus.now / 1000
        p.connected = p_on_ms is not None and t >= p_on_ms and not (loss and loss[0] <= t < loss[1])
        bus.run_for(step); t = bus.now / 1000
        for k, pn in pins.items():
            lv = q.level(pn)
            if lv and (not iv[k] or iv[k][-1][1] is not None): iv[k].append([t, None])
            if not lv and iv[k] and iv[k][-1][1] is None: iv[k][-1][1] = t
    return (first[0] if first else None), iv
def on_ms(ivs, t0, t1):                       # ON time inside [t0, t1)
    return round(sum(max(0, min(b if b is not None else t1, t1) - max(a, t0)) for a, b in ivs), 1)
def state(ivs, t): return int(any(a <= t and (b is None or b > t) for a, b in ivs))
def edges(ivs, t0, t1): return sum((t0 <= a < t1) + (b is not None and t0 <= b < t1) for a, b in ivs)
ok7, fr7 = s7_config()
check('S7 recipe written over CAN with stock params only (A1: 9 CAN inputs, 6 virtual inputs, 7 outputs) and saved', ok7)
# (b) start-up: Q's outputs work from about 502 ms after power-up (main waits 500 ms); P (powered since t = 0, inputs
# steady) stays off the bus until 0.5 s, 1.0 s or 1.5 s (past the 1 s time-out), then sends
blip = {}
for p_on in (500, 1000, 1500):
    for pb in (0, 1):
        t1st, iv = s7_run(fr7, pb, 1, p_on, p_on + 800)
        b_ = blip[(p_on, pb)] = {k: on_ms(iv[k], 0, t1st) for k in S7}; after = {k: state(iv[k], p_on + 790) for k in S7}
        info[f's7_boot_{p_on}_p{pb}'] = dict(first_frame_ms=t1st, on_before_first_ms=b_)
        crit_ok = p_on == 500 or (b_['on_crit'] > 0 and b_['cond_crit'] > 0 and (pb == 0 or (len(iv['on_crit']) == 1 and len(iv['cond_crit']) == 1)))
        check(f'start-up, P silent {p_on / 1000} s, P input {"ON" if pb else "OFF"}: non-critical outputs OFF until the first frame (worst blip 0 ms, 0.5 ms steps), '
              f'then every output follows P{"; critical ones act at once (ON from power-up, no dropout)" if p_on > 500 else ""}',
              t1st and t1st >= p_on and all(b_[k] == 0 for k in NONCRIT) and all(after[k] == pb for k in S7) and crit_ok, (t1st, b_, after))
check('reference: today\'s B4 "On" recipe pulses ON before the first frame (the blip this replaces)', blip[(1000, 0)]['b4_on'] > 400, blip[(1000, 0)]['b4_on'])
# P never appears: non-critical outputs wait (also past the 1 s time-out), critical ones act on their loss setting
t1st, iv = s7_run(fr7, 1, 1, None, 3000); never = {k: on_ms(iv[k], 0, 3000) for k in S7}; info['s7_never_on_ms'] = never
check('start-up, P never sends (3 s): non-critical outputs stay OFF throughout; on-critical and condition-critical (ignition on) ON throughout',
      t1st is None and all(never[k] == 0 for k in NONCRIT) and all(state(iv[k], 2999) == 1 and len(iv[k]) == 1 for k in ('on_crit', 'cond_crit')), never)
t1st, iv = s7_run(fr7, 1, 0, None, 3000)
check('start-up, P never sends, ignition off: condition-critical stays OFF, on-critical ON', on_ms(iv['cond_crit'], 0, 3000) == 0 and state(iv['on_crit'], 2999) == 1)
# both boards power up together (key on): no frame-wait blip either
t1st, iv = s7_run(fr7, 0, 1, 0, 1500); tog = {k: on_ms(iv[k], 0, 1500) for k in S7}; info['s7_together_first_frame_ms'] = t1st; info['s7_together_on_ms'] = tog
check('start-up, both boards power up together, P input OFF: non-critical outputs never ON', all(tog[k] == 0 for k in NONCRIT), (t1st, tog))
# key on with P's input already ON: P's first msg 37 must carry the real input (its first cyclic round is built in InitCan,
# before the device thread has read any input), else every link sees OFF for one 100 ms period and critical outputs drop out
t1st, iv = s7_run(fr7, 1, 1, 0, 1500); d1 = s7_first_data[0] if s7_first_data else b''
info['s7_together_p1'] = dict(first_frame_ms=t1st, first_bits=d1[:2].hex(), on=iv)
check('key on, both boards together, P input ON: P\'s first msg 37 shows the input ON; critical outputs ON with no dropout; all outputs ON by 120 ms after the first frame',
      t1st and (d1[0] >> P_BIT) & 1 and all(len(iv[k]) == 1 for k in ('on_crit', 'cond_crit'))
      and all(state(iv[k], t1st + 120) == 1 and len(iv[k]) == 1 for k in S7), (t1st, d1[:2].hex(), iv))
# (a) loss after running: P off the bus from 2.0 s to 4.5 s
LOSS = (2000, 4500); lossres = {}
for pb in (0, 1):
    for ig in (0, 1):
        t1st, iv = s7_run(fr7, pb, ig, 0, 6000, loss=LOSS)
        bef = {k: state(iv[k], 1990) for k in S7}; dur = {k: state(iv[k], 4400) for k in S7}; back = {k: state(iv[k], 5990) for k in S7}
        chg = {k: next((round(t - LOSS[0]) for a, b in iv[k] for t in (a, b) if t is not None and LOSS[0] <= t < LOSS[1]), None) for k in S7}
        nedge = {k: edges(iv[k], LOSS[0], LOSS[1]) for k in S7}
        want = dict(off=0, hold=pb, on=1, on_crit=1, cond=ig, cond_crit=ig, b4_on=1)
        lossres[(pb, ig)] = dict(before=bef, during=dur, back=back, change_ms=chg, edges=nedge)
        check(f'loss, P input {"ON" if pb else "OFF"}, ignition {"ON" if ig else "OFF"}: off / hold / on / condition / critical as set, one clean change at the time-out (no blip), follows P again after',
              all(bef[k] == pb for k in S7) and dur == want and all(back[k] == pb for k in S7)
              and all(nedge[k] == int(want[k] != pb) for k in S7) and all(TIMEOUT_MS - 100 <= c <= TIMEOUT_MS + 200 for c in chg.values() if c is not None),
              dict(during=dur, change_ms={k: v for k, v in chg.items() if v is not None}, edges=nedge))
info['s7_loss'] = {f'p{a}_ign{b}': v['change_ms'] for (a, b), v in lossres.items()}
# order rule: LOST must be evaluated before the link virtual inputs that use it (virtual inputs run in index order each cycle)
ok7m, fr7m = s7_config(lost_vi=7)
t1st, iv = s7_run(fr7m, 1, 1, 0, 4000, loss=(2000, 4000), step=0.1)
glitch = [round(b - a, 1) for a, b in [(iv['on'][i][1], iv['on'][i + 1][0]) for i in range(len(iv['on']) - 1)] if a is not None]
info['s7_lost_after_link_glitch_ms'] = glitch
check('order rule: with LOST at a higher virtual-input index than the "on" link, the output drops for one cycle at the time-out (so the UI must place LOST lower)',
      ok7m and len(glitch) == 1 and 0 < glitch[0] < 5, (glitch, iv['on']))

bad = [r for r in res if not r[1]]
print(f'\nS1-S7: {len(res) - len(bad)} of {len(res)} checks passed'); print(json.dumps(info))
json.dump(dict(checks=res, info=info, matrix=matrix), open('/tmp/s1_results.json', 'w'), indent=1)
