"""S1-S3: three boards in one box as one PDM. Commissioning, a PC-side 'single PDM' layer on stock
firmware logic, and what outputs do when a CAN link is lost (three policies).
IDs used here are examples only: boards 0x500 / 0x520 / 0x540, ECU command frame 0x4F0."""
import sys, json, pdmsim as ps
SO = sys.argv[1] if len(sys.argv) > 1 else '/tmp/simout'
BASE = {'A1': 0x500, 'A2': 0x520, 'B': 0x540}; ECU_ID = 0x4F0; ALIVE_SLOT = 31; TIMEOUT_MS = 500
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
    bus.run_for(600); before = snapshot(); t = bus.now; fault(); trace = {g: None for g in WATCH}
    while bus.now < t + 2_500_000:
        bus.run_for(5); p = pins_on()
        for g in WATCH:
            if trace[g] is None and (g in p) != bool(before[g]): trace[g] = round((bus.now - t) / 1000)
    after = snapshot(); stale = {k: round((bus.now - stat[k].last) / 1000) for k in boards}
    undo(); bus.run_for(800); back = snapshot()
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
check('policy off: switches OFF after the time-out', r['after'][2] == 0 and r['after'][22] == 0 and 400 <= r['change_ms'][2] <= 700, r['change_ms'])
check('policy on: stays ON', r['after'][3] == 1 and r['after'][23] == 1)
r = m[('ECU stops sending', 0)]
check('policy hold: stays OFF when it was off', r['after'][1] == 0 and r['after'][21] == 0)
check('policy on: turns ON after the time-out when it was off', r['after'][3] == 1 and r['after'][23] == 1 and 400 <= r['change_ms'][3] <= 700, r['change_ms'])
check('everything follows the ECU again when frames return', all(v == 0 for g, v in r['recovered'].items() if g != 5) and all(m[('ECU stops sending', 1)]['recovered'][g] == 1 for g in WATCH))
r = m[('board A1 CAN unplugged', 1)]
check('one board unplugged: only that board applies its policies, board B carries on', (r['after'][1], r['after'][2], r['after'][3]) == (1, 0, 1) and (r['after'][21], r['after'][22], r['after'][23]) == (1, 1, 1), r['after'])
check('merged view can flag the lost board: its status goes stale, the others stay fresh', r['status_age_ms']['A1'] > 2000 and r['status_age_ms']['B'] < 250, r['status_age_ms'])
# cross-board rule when the source board drops off
cmd[:] = [0] * 24; kb.set_input(2, '12v'); bus.run_for(500); pre = 5 in pins_on()
boards['B'].connected = False; dt = settle_time(5, 0); boards['B'].connected = True; bus.run_for(500); post = 5 in pins_on(); kb.set_input(2, 'gnd'); bus.run_for(400)
check('cross-board rule (policy off): output 5 drops when board B falls off the bus, returns when it is back', pre and 400 <= dt <= 700 and post, f'{dt} ms')
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
bad = [r for r in res if not r[1]]
print(f'\nS1-S3: {len(res) - len(bad)} of {len(res)} checks passed'); print(json.dumps(info))
json.dump(dict(checks=res, info=info, matrix=matrix), open('/tmp/s1_results.json', 'w'), indent=1)
