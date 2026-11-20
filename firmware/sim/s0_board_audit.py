"""S0: per-board audit. Does the firmware port drive the redesigned board the way the pin map says?"""
import sys, struct, pdmsim as ps
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
    want_type = ps.DEVICE_TYPE[model['fw']]
    check(f'{label} reports its own device type {want_type} in msg 0 byte 1 bits 4-7 (stock 0 / 1; dingoConfig route A)', st.pdm_type() == want_type, st.pdm_type())
    check(f'{label} battery reading', abs((st.batt() or 0) - 13.8) < 0.15, st.batt())
    b.set_temp(44.0, 58.5); bus.run_for(400)      # unequal: a board / die mix-up is 14.5 C off
    check(f'{label} temperatures: board 44.0 C in msg 0, STM32 die 58.5 C in msg {ps.STATUS_MSG} (x10)', st.board_temp_x10() == 440 and abs((st.die_temp_x10() or 0) - ps.die_temp_can(58.5)) <= 4,
          f'board {st.board_temp_x10()}, die {st.die_temp_x10()} (want {ps.die_temp_can(58.5)})')
    # Dan s11c: steady thermal flags in every cyclic msg 3, byte 7 (bit 0 over warn, 1 critical soon, 2 critical)
    fl = []; td = ps.temp_default(model); temps = (td['warn'] + 0.5, td['crit'] - 3.0, td['crit'] + 1.0, 30.0)
    for c in temps: b.set_temp(c); bus.run_for(600); fl.append(st.thermal_flags())
    check(f'{label} thermal flags (msg 3 byte 7, factory limits warn {td["warn"]} / critical {td["crit"]}): {temps[0]} C warn (1), {temps[1]} C warn + critical soon (3), '
          f'{temps[2]} C warn + critical (5), 30 C none (0)', fl == [ps.FLAG_WARN, ps.FLAG_WARN | ps.FLAG_SOON, ps.FLAG_WARN | ps.FLAG_CRIT, 0], fl)
    # presim (docs/system-verification.md 1): readings must not move with VDDA (TLV1117LV +-1.5 %): battery and die
    # temperature at VDDA 3.25 V vs 3.30 V (GetVDDA from VREFINT; TS_CAL taken at 3.3 V needs the VDDA ratio)
    b.set_temp(30.0, 58.5); bus.run_for(600); ref = (st.die_temp_x10(), st.batt())
    b.set_vdda(3.25); bus.run_for(600); low = (st.die_temp_x10(), st.batt()); b.set_vdda(3.3); bus.run_for(300)
    check(f'{label} die temperature and battery reading independent of VDDA (3.25 vs 3.30 V)',
          abs((low[0] or 0) - (ref[0] or 0)) <= 5 and abs((low[1] or 0) - (ref[1] or 0)) <= 0.15, f'{ref} -> {low}')
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
        # 1 ms samples: dingoFW development goes Overcurrent -> Fault in the next 2 ms device cycle on the last allowed trip
        bus.run_for(1); s_ = b.L.sim_out_state(o)
        if not seq or seq[-1] != s_: seq.append(s_)
    check(f'{label} overcurrent, factory default (retry mode): 3 trips then Fault', seq.count(2) == 3 and seq[-1] == 3 and b.level(IN) == 0, [ps.STATE[x] for x in seq])
    # --- every digital input, one at a time
    for i in range(len(model['inputs'])): tool.write(BASE, 0x1200 + i, 0, 1); b.set_input(i, 'gnd', 'up')
    bus.run_for(300); base_bits = st.di(); ok_in, det = base_bits == 0, [f'idle bits {base_bits:#x}']
    for i in range(len(model['inputs'])):
        b.set_input(i, '12v'); bus.run_for(250)
        if st.di() != (1 << i): ok_in = False; det.append(f'in{i+1} -> bits {st.di():#x}')
        b.set_input(i, 'gnd'); bus.run_for(250)
    check(f'{label} each digital input sets its own bit (msg {ps.STATUS_MSG})', ok_in, det if not ok_in else '')
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
    wmask = tool.read(BASE, ps.TEMP_INDEX, ps.WAKE_SUB)
    tool.sleep(BASE); bus.run_for(300)   # dingoFW development: 100 ms CAN quiet + 20 ms transceiver settle before STOP
    # Dan B2: factory default = no input wakes it (every input enabled above), CAN and USB do
    check(f'{label} wake-up set, factory default: wake mask (0x7F00 sub {ps.WAKE_SUB}) = 0, sleep arms CAN RX (PB8) and USB D- / D+ (PA11 / PA12) only, no input pin',
          wmask == 0 and ps.exti_lines(b) == {8: 'PB8', 11: 'PA11', 12: 'PA12'}, (wmask, ps.exti_lines(b)))
    post = (lv(dens + dsels + ins), all(b.pin_info(p)['mode'] == 'output' for p in dens + dsels + ins), lv(ps.LEDS), b.mcp_info())
    check(f'{label} sleep request: IN / DEN{" / DSEL" if dsels else ""} of every channel driven low (were: DEN high, {n - 2} IN high), LEDs off (error LED was on)',
          b.flags()['asleep'] and all(v == 1 for v in pre[0].values()) and pre[1] == [1] * (n - 2) + [0, 0] and pre[2]['PC0'] == 1
          and all(v == 0 for v in post[0].values()) and post[1] and post[2] == {'PC0': 0, 'PC1': 0}, (b.flags(), pre[:3], post[:3]))
    check(f'{label} sleep request: MCP9808 alert output off and shutdown set, once (was converting, alert on)',
          (pre[3]['shutdown'], pre[3]['alert_on'], pre[3]['shutdown_calls']) == (0, 1, 0) and (post[3]['shutdown'], post[3]['alert_on'], post[3]['shutdown_calls']) == (1, 0, 1), (pre[3], post[3]))

def safety(model, label):
    """MCU safety (core/safety.h, ADR-2026-11-20-presim-findings item 3): brown-out level from the option bytes, the
    independent watchdog, sleep with the watchdog running. Expectations from the sources, not from firmware constants:
    BOR_LEV 00 = level 3 (RM0390 Rev 6 3.8.6), LSI 17 / 32 / 47 kHz (DS DocID027107 Table 42)."""
    BASE = model['base'][1]; ins = [o[0] for o in model['outputs']]
    def system(**kw):
        bus = ps.Bus(); tool = ps.Tool(bus); b = ps.Board(model, label, SO, **kw); bus.add(b, tool); bus.log = []
        infos = []; bus.watch.append(lambda f: infos.append((chr(f.data[0]), f.data[1]) + struct.unpack('<HHH', f.data[2:8]))
                                     if f.id == BASE and f.data[0] in (ord('R'), ord('E'), ord('F')) else None)
        return bus, tool, b, infos
    init = lambda infos: [m for m in infos if m[1] == ps.SRC_INIT]
    # 1. factory option bytes (BOR off): first start writes level 3 once, outputs off, no CAN frame, then one MCU reset
    bus, tool, b, infos = system(opt=ps.OPT_FACTORY); b.watch(*ins); bus.run_for(2000)
    t_rst = b.resets[0][0] if b.resets else None
    early = [f for f in bus.log if f.src == label and t_rst is not None and f.t < t_rst]; bus.log = None
    on_edges = [e for e in b.edges() if e[2] == 1]
    check(f'{label} factory option bytes (BOR off): the first start writes BOR level 3 once, sends no CAN frame and switches no output before it, '
          f'then resets the MCU once (about 0.5 s in); the next start writes nothing, runs and answers',
          len(b.resets) == 1 and b.resets[0][1] == 'software' and 490_000 <= t_rst <= 520_000 and b.bor_level_bits() == 0 and not early
          and not on_edges and b.wdg()['opt_writes'] == 0 and not b.flags()['fatal'] and tool.version(BASE) == ps.FW_VERSION and init(infos) == [],
          (b.resets, b.bor_level_bits(), len(early), on_edges[:3], b.wdg()['opt_writes'], init(infos)))
    # 2. low battery: not written (the option sector is erased and re-written: needs a healthy supply), warning once CAN is up
    bus, tool, b, infos = system(opt=ps.OPT_FACTORY, vbat=9.0); bus.run_for(1500)
    low = (list(b.resets), b.bor_level_bits(), b.wdg()['opt_writes'], init(infos))
    bus = ps.Bus(); tool = ps.Tool(bus); b2 = ps.Board(model, label, SO, fram=b.fram(), opt=b.opt()); bus.add(b2, tool); bus.run_for(2000)
    check(f'{label} BOR level not written at 9.0 V battery (start-up dip): warning R / Init / {ps.MSG_BOR_LOW_VBAT} (battery x10 about 90, level bits 3), no reset; '
          'written at the next start at 13.8 V', low[0] == [] and low[1] == 3 and low[2] == 0 and len(low[3]) == 1 and low[3][0][:3] == ('R', ps.SRC_INIT, ps.MSG_BOR_LOW_VBAT) and 85 <= low[3][0][3] <= 92 and low[3][0][4] == 3
          and len(b2.resets) == 1 and b2.bor_level_bits() == 0, (low, b2.resets, b2.bor_level_bits()))
    # 3. a write that does not take: no reset loop, warning, the board runs
    bus, tool, b, infos = system(opt=ps.OPT_FACTORY); b.L.sim_opt_fail(1); bus.run_for(1500)
    check(f'{label} BOR write that does not take: warning R / Init / {ps.MSG_BOR_FAILED} (level read back 3), no reset, the board runs',
          b.resets == [] and init(infos) == [('R', ps.SRC_INIT, ps.MSG_BOR_FAILED, 3, 3)] and tool.version(BASE) == ps.FW_VERSION, (b.resets, init(infos)))
    # 4. watchdog running from the start, timeout >= 1 s even with the fastest LSI, refreshed in normal running
    bus, tool, b, infos = system(); bus.run_for(1500)
    w = b.wdg(); t_min = (4 << w['pr']) * (w['rlr'] + 1) / ps.LSI_HZ[2]; t_max = (4 << w['pr']) * (w['rlr'] + 1) / ps.LSI_HZ[0]
    for i in range(len(model['outputs'])): tool.write(BASE, 0x1000 + i, 0, 1); tool.write(BASE, 0x1000 + i, 1, 1); b.set_load(i, b.vbat / 2.0)
    tool.burn(BASE); bus.run_for(3000); w = b.wdg()
    check(f'{label} watchdog runs from boot: timeout {t_min:.3f} s at LSI 47 kHz (>= {ps.SAFETY_WDG_MIN_MS / 1000:.1f} s), {t_max:.2f} s at 17 kHz; '
          f'longest refresh gap in 4.5 s of running (every output on, writes, Burn) <= half the shortest timeout, no reset',
          w['running'] and t_min >= ps.SAFETY_WDG_MIN_MS / 1000 and t_max <= 3.0 and w['max_gap_us'] <= t_min * 1e6 / 2 and b.resets == [] and w['refreshes'] >= 4.5 / 0.3,
          dict(pr=w['pr'], rlr=w['rlr'], max_gap_ms=w['max_gap_us'] / 1000, refreshes=w['refreshes'], resets=b.resets))
    INFO[f'{label}_wdg'] = dict(pr=w['pr'], rlr=w['rlr'], t_min_s=round(t_min, 4), t_typ_s=round((4 << w['pr']) * (w['rlr'] + 1) / ps.LSI_HZ[1], 4),
                                t_max_s=round(t_max, 3), max_gap_ms=w['max_gap_us'] / 1000)
    # 5. a stuck thread stops the refreshes: reset after the timeout for that LSI, every output off from the reset,
    #    back with its saved config and the watchdog warning
    fram = b.fram()
    for thread, lsi in (('DeviceThread', ps.LSI_HZ[1]), ('DeviceThread', ps.LSI_HZ[0]), ('DeviceThread', ps.LSI_HZ[2]),
                        ('SlowThread', ps.LSI_HZ[1]), ('CAN Rx', ps.LSI_HZ[1]), ('CAN Tx', ps.LSI_HZ[1]), ('CAN Cyclic Tx', ps.LSI_HZ[1])):
        bus, tool, b, infos = system(fram=fram, lsi=lsi)
        for i in range(len(model['outputs'])): b.set_load(i, b.vbat / 2.0)
        bus.run_for(1500); on0 = [b.level(p) for p in ins]; t_stall = bus.now
        ok_stall = b.stall(thread); timeout = (4 << b.wdg()['pr']) * (b.wdg()['rlr'] + 1) / lsi * 1e6
        while not b.resets and bus.now < t_stall + timeout + 500_000: bus.run_for(5)
        t_r = b.resets[0][0] if b.resets else None
        off = [b.level(p) for p in ins]                     # the new start, at most 5 ms after the reset
        bus.run_for(1500); back = [b.level(p) for p in ins]
        # the last refresh: within one slow-thread round (250 ms + its I2C read) before or after the stall (a thread that
        # had just checked in still counts once)
        check(f'{label} stuck {thread} (LSI {lsi // 1000} kHz): watchdog reset {timeout / 1e6:.2f} s after the last refresh (within one 250 ms slow-thread round of the stall), '
              f'every IN low from the reset, outputs back with the saved config after the restart, warning R / Init / {ps.MSG_WDG_RESET}',
              ok_stall and all(on0) and len(b.resets) == 1 and b.resets[0][1] == 'watchdog' and abs(t_r - t_stall - timeout) <= 260_000
              and not any(off) and all(back) and init(infos) == [('R', ps.SRC_INIT, ps.MSG_WDG_RESET, 0, 0)],
              dict(stalled=ok_stall, on=on0, resets=b.resets, after_ms=None if t_r is None else (t_r - t_stall) / 1000, off=off, back=back, init=init(infos)))
    # 6. sleep (STOP) with the watchdog running: RTC wake-ups refresh it, no reset in 60 s, at both LSI ends
    for lsi in (ps.LSI_HZ[0], ps.LSI_HZ[2]):
        bus, tool, b, infos = system(lsi=lsi); bus.run_for(1500); tool.sleep(BASE); bus.run_for(60_000); w = b.wdg()
        per = (w['rtc_wut'] + 1) * 16 / lsi
        check(f'{label} sleep 60 s (LSI {lsi // 1000} kHz): no watchdog reset, still asleep; sleep timeout {w["timeout_us"] / 1e6:.1f} s, RTC wake-up every {per:.2f} s '
              '(a quarter of it, same LSI), each one a refresh', b.flags()['asleep'] and not b.flags()['wdg_reset'] and b.resets == []
              and per * 1e6 <= w['timeout_us'] / 4 + 1 and abs(w['rtc_wakes'] - int(60 / per)) <= 1, dict(w, resets=b.resets))

INFO = {}
audit(ps.BOARD_A, 'A'); audit(ps.BOARD_B, 'B')
safety(ps.BOARD_A, 'A'); safety(ps.BOARD_B, 'B')
print('   info: ' + str(INFO))
bad = [r for r in res if not r[1]]
print(f'\nS0: {len(res) - len(bad)} of {len(res)} checks passed')
