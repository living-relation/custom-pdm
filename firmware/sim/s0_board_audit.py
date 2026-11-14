"""S0: per-board audit. Does the firmware port drive the redesigned board the way the pin map says?"""
import sys, pdmsim as ps
SO = sys.argv[1] if len(sys.argv) > 1 else '/tmp/simout'
res = []
def check(name, ok, detail=''):
    res.append((name, ok, detail)); print(('PASS ' if ok else 'FAIL ') + name + (' : ' + str(detail) if detail else ''))

def audit(model, label):
    bus = ps.Bus(); b = ps.Board(model, label, SO); tool = ps.Tool(bus); BASE = model['base'][1]; bus.add(b, tool)
    st = ps.Status(BASE); bus.watch.append(st.feed)
    n = len(model['outputs'])
    # --- reset state, before the firmware starts (main waits 500 ms)
    bus.run_for(100)
    check(f'{label} reset: all IN pins are outputs, low', all(b.pin_info(o[0])['mode'] == 'output' and b.level(o[0]) == 0 for o in model['outputs']))
    check(f'{label} reset: all DEN/DSEL pins are outputs', all(b.pin_info(p)['mode'] == 'output' for o in model['outputs'] for p in (o[1], o[2]) if p))
    check(f'{label} reset: input pins are inputs', all(b.pin_info(i[0])['mode'] == 'input' for i in model['inputs']))
    check(f'{label} reset: analog + IS pins in analog mode', all(b.pin_info(p)['mode'] == 'analog' for p in [model['analog'], model['batt']] + [o[4] for o in model['outputs']]))
    bus.run_for(1500)
    check(f'{label} boots, no fatal error', not b.flags()['fatal'], b.flags())
    c = b.counters()
    check(f'{label} counts: outputs/inputs/analog', (c['n_out'], c['n_di'], c['n_an']) == (n, len(model['inputs']), 1), (c['n_out'], c['n_di'], c['n_an']))
    check(f'{label} config fits 64 Kbit FRAM (8192 bytes) with CRC', c['config_bytes'] + 4 <= 8192, f"{c['config_bytes']} + 4 bytes")
    check(f'{label} factory default CAN: 1 Mbit/s, base ID {BASE:#x}', b.bitrate() == 1000000 and st.last > 0, b.bitrate())
    check(f'{label} battery reading', abs((st.batt() or 0) - 13.8) < 0.15, st.batt())
    b.set_temp(44.0, 58.5); bus.run_for(400)      # unequal: a board / die mix-up is 14.5 C off
    check(f'{label} temperatures: board 44.0 C in msg 0, STM32 die 58.5 C in msg 27 (x10)', st.board_temp_x10() == 440 and abs((st.die_temp_x10() or 0) - ps.die_temp_can(58.5)) <= 4,
          f'board {st.board_temp_x10()}, die {st.die_temp_x10()} (want {ps.die_temp_can(58.5)})')
    # Dan s11c: steady thermal flags in every cyclic msg 3, byte 7 (bit 0 over warn, 1 critical soon, 2 critical)
    fl = []
    for c in (56.0, 77.0, 81.0, 30.0): b.set_temp(c); bus.run_for(600); fl.append(st.thermal_flags())
    check(f'{label} thermal flags (msg 3 byte 7): 56 C warn (1), 77 C warn + critical soon (3), 81 C warn + critical (5), 30 C none (0)',
          fl == [ps.FLAG_WARN, ps.FLAG_WARN | ps.FLAG_SOON, ps.FLAG_WARN | ps.FLAG_CRIT, 0], fl)
    b.set_temp(30.0, 30.0)
    # --- every output: switch it alone with a known load, compare with the hardware model
    for i in range(n):
        tool.write(BASE, 0x1000 + i, 0, 1)                         # enable
        tool.write(BASE, 0x1000 + i, 2, ps.f32(40.0))              # generous limit for this check
    bus.run_for(50)
    ok_sw, ok_cur, det = True, True, []
    for i in range(n):
        want = [2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0][i]          # amps, different per output
        for k in range(n): b.set_load(k, b.vbat / ([2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0][k]))
        tool.write(BASE, 0x1000 + i, 1, 1)                         # input = var 1 (always true)
        bus.run_for(300)
        ins = [b.level(o[0]) for o in model['outputs']]
        if ins != [1 if k == i else 0 for k in range(n)]: ok_sw = False; det.append(f'out{i+1} pins {ins}')
        got = [b.L.sim_out_current(k) for k in range(n)]
        if abs(got[i] - want) > 0.15 or any(abs(got[k]) > 0.01 for k in range(n) if k != i): ok_cur = False; det.append(f'out{i+1} amps {[round(g, 2) for g in got]}')
        if st.out_state(i) != 1: ok_sw = False; det.append(f'out{i+1} CAN state {st.out_state(i)}')
        tool.write(BASE, 0x1000 + i, 1, 0); bus.run_for(60)
    check(f'{label} each output switches its own IN pin only', ok_sw, det)
    check(f'{label} each output reads its own current (IS pin, DSEL, ADC slot, kILIS)', ok_cur, det)
    # CAN current scaling as sent on the bus
    tool.write(BASE, 0x1000, 1, 1); b.set_load(0, b.vbat / 5.0); bus.run_for(300)
    print(f'   info: 5.0 A load on output 1 -> CAN OutputCurrent raw = {st.current(0)}, TotalCurrent raw = {st.total()} (DBC says 0.1 A per count)')
    tool.write(BASE, 0x1000, 1, 0); bus.run_for(100)
    # --- overcurrent: reset mode None latches Fault at once; the factory default (Count) retries first
    lim = model['limit'] or 15.0; o = n - 1; IN = model['outputs'][o][0]
    for sub, val in [(2, ps.f32(lim)), (3, ps.f32(lim * 2)), (4, 100), (5, 0)]: tool.write(BASE, 0x1000 + o, sub, val)   # reset mode None
    b.set_load(o, b.vbat / (lim * 1.3)); tool.write(BASE, 0x1000 + o, 1, 1); bus.run_for(400)
    check(f'{label} overcurrent at 1.3 x limit: reset mode None: output latches Fault at once, IN pin low', b.L.sim_out_state(o) == 3 and b.level(IN) == 0 and st.out_state(o) == 3, ps.STATE[b.L.sim_out_state(o)])
    b.set_load(o, b.vbat / (lim * 0.9)); tool.write(BASE, 0x1000 + o, 1, 0); bus.run_for(200); tool.write(BASE, 0x1000 + o, 1, 1); bus.run_for(300)
    check(f'{label} Fault stays latched after the command is cycled (needs a power cycle)', b.L.sim_out_state(o) == 3, ps.STATE[b.L.sim_out_state(o)])
    o = n - 2; IN = model['outputs'][o][0]
    for sub, val in [(2, ps.f32(lim)), (3, ps.f32(lim * 2)), (4, 100)]: tool.write(BASE, 0x1000 + o, sub, val)   # reset mode left at the factory default
    b.set_load(o, b.vbat / (lim * 1.3)); tool.write(BASE, 0x1000 + o, 1, 1)
    seq = []; t_end = bus.now + 6_000_000
    while bus.now < t_end:
        bus.run_for(5); s_ = b.L.sim_out_state(o)
        if not seq or seq[-1] != s_: seq.append(s_)
    check(f'{label} overcurrent, factory default (retry mode): 3 trips then Fault', seq.count(2) == 3 and seq[-1] == 3 and b.level(IN) == 0, [ps.STATE[x] for x in seq])
    # --- every digital input, one at a time
    for i in range(len(model['inputs'])): tool.write(BASE, 0x1200 + i, 0, 1); b.set_input(i, 'gnd', 'up')
    bus.run_for(300); base_bits = st.di(); ok_in, det = base_bits == 0, [f'idle bits {base_bits:#x}']
    for i in range(len(model['inputs'])):
        b.set_input(i, '12v'); bus.run_for(250)
        if st.di() != (1 << i): ok_in = False; det.append(f'in{i+1} -> bits {st.di():#x}')
        b.set_input(i, 'gnd'); bus.run_for(250)
    check(f'{label} each digital input sets its own bit (msg 27)', ok_in, det if not ok_in else '')
    b.set_analog(2.5); tool.write(BASE, 0x2200, 0, 1); bus.run_for(300)
    check(f'{label} analog input: 2.5 V at the wire reads 2500 mV', abs((st.an_mv() or 0) - 2500) < 15, st.an_mv())
    b.set_analog(5.0); bus.run_for(300)
    check(f'{label} analog input: 5.0 V at the wire reads about 5000 mV', abs((st.an_mv() or 0) - 5000) < 60, st.an_mv())
    c = b.counters()
    check(f'{label} no writes to non-output pins, no CAN overruns', c['bad_writes'] == 0 and c['rx_overruns'] == 0, {k: c[k] for k in ('bad_writes', 'last_bad_write', 'rx_overruns', 'tx_timeouts')})
    # --- floating direct inputs with default (no) pull
    b.set_input(0, 'open'); bus.run_for(100); c2 = b.counters()
    print(f"   info: input 1 left open with pull = None -> {c2['float_reads'] - c['float_reads']} floating reads in 100 ms (undefined level on real hardware)")
    # --- sleep (Dan s7a): request it with outputs on, then look at every PROFET line, the LEDs and the sensor
    for i in range(n - 2): b.set_load(i, b.vbat / (2.0 + i)); tool.write(BASE, 0x1000 + i, 1, 1)   # the last two are latched Fault (above)
    bus.run_for(300)
    dens = sorted({o[1] for o in model['outputs']}); dsels = sorted({o[2] for o in model['outputs'] if o[2]}); ins = [o[0] for o in model['outputs']]
    lv = lambda ps_: {p: b.level(p) for p in ps_}
    pre = (lv(dens), [b.level(p) for p in ins], lv(ps.LEDS), b.mcp_info())
    tool.sleep(BASE); bus.run_for(100)
    post = (lv(dens + dsels + ins), all(b.pin_info(p)['mode'] == 'output' for p in dens + dsels + ins), lv(ps.LEDS), b.mcp_info())
    check(f'{label} sleep request: IN / DEN{" / DSEL" if dsels else ""} of every channel driven low (were: DEN high, {n - 2} IN high), LEDs off (error LED was on)',
          b.flags()['asleep'] and all(v == 1 for v in pre[0].values()) and pre[1] == [1] * (n - 2) + [0, 0] and pre[2]['PC0'] == 1
          and all(v == 0 for v in post[0].values()) and post[1] and post[2] == {'PC0': 0, 'PC1': 0}, (b.flags(), pre[:3], post[:3]))
    check(f'{label} sleep request: MCP9808 alert output off and shutdown set, once (was converting, alert on)',
          (pre[3]['shutdown'], pre[3]['alert_on'], pre[3]['shutdown_calls']) == (0, 1, 0) and (post[3]['shutdown'], post[3]['alert_on'], post[3]['shutdown_calls']) == (1, 0, 1), (pre[3], post[3]))

audit(ps.BOARD_A, 'A'); audit(ps.BOARD_B, 'B')
bad = [r for r in res if not r[1]]
print(f'\nS0: {len(res) - len(bad)} of {len(res)} checks passed')
