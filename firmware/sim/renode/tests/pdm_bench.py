"""Robot Framework keywords for the custom-pdm Renode bench.

Repeats the checks of firmware/sim/s1_system.py against the real firmware binaries in Renode.
Board pin tables, the status-frame decoder and the parameter protocol constants come from firmware/sim/pdmsim.py.
The 'single PDM' configuration (can_input / set_output / alive_input) is the same recipe as in s1_system.py.
State is kept between tests on purpose: the tests run in file order, like the script they repeat."""
import os, sys, struct, types
from robot.libraries.BuiltIn import BuiltIn
from robot.api import logger

BASE = {}; ECU_ID = 0x4F0; ALIVE_SLOT = 31; TIMEOUT_MS = 1000
MACH = {'A1': 'a1', 'A2': 'a2', 'B': 'b'}
PCLK1 = 36_000_000        # mcuconf.h: 8 MHz / 5 * 180 / 2 = 144 MHz, APB1 = / 4
CAN_BTR = 0x4000641C
STEP = 20                 # ms between pin samples when timing a change
WATCH = [1, 2, 3, 21, 22, 23]


class pdm_bench:
    ROBOT_LIBRARY_SCOPE = 'GLOBAL'

    def __init__(self, simdir, resc):
        sys.path.insert(0, simdir)
        import pdmsim
        BASE.update({'A1': pdmsim.BOARD_A['base'][1], 'A2': pdmsim.BOARD_A['base'][2], 'B': pdmsim.BOARD_B['base'][1]})   # factory base IDs
        s = self; s.ps = pdmsim; s.resc = resc; s.now = 0; s.writes = 0; s.matrix = {}; s.cmd = [0] * 24
        s.model = {'A1': pdmsim.BOARD_A, 'A2': pdmsim.BOARD_A, 'B': pdmsim.BOARD_B}
        # global numbering as in s1_system.py: 1-8 = A1, 9-16 = A2, 17-20 = B out 5-8, 21-24 = B out 1-4
        s.OUT = {g: ('A1', g - 1) for g in range(1, 9)} | {g: ('A2', g - 9) for g in range(9, 17)} | \
                {g: ('B', g - 17 + 4) for g in range(17, 21)} | {g: ('B', g - 21) for g in range(21, 25)}
        s.LIMIT = {g: 7.5 for g in range(1, 17)} | {g: 15.0 for g in range(17, 21)} | {g: 30.0 for g in range(21, 25)}
        s.INP = {}; n = 1
        for k in ('A1', 'A2', 'B'):
            for i in range(len(s.model[k]['inputs'])): s.INP[n] = (k, i); n += 1
        s.virt_used = {k: 0 for k in BASE}; s.vbat = 13.8

    # ------------------------------------------------------------------ plumbing
    def _x(s, c, m=None):
        r = BuiltIn().run_keyword('Execute Command', c, *([f'machine={m}'] if m else []))
        return str(r).strip()
    def _n(s, c, m=None):
        v = int(s._x(c, m), 0); return v - (1 << 64) if v >= (1 << 63) else v
    def _run(s, ms): s._x(f'emulation RunFor "{ms / 1000.0:.6f}"'); s.now += ms
    def _ecu(s, c): return s._x('sysbus.ecu ' + c, 'ecu')
    def _ecun(s, c): return s._n('sysbus.ecu ' + c, 'ecu')
    def _var(s, k, what, i): return getattr(s.ps.Board, 'var_' + what)(types.SimpleNamespace(model=s.model[k]), i)
    def _check(s, ok, detail=''):
        logger.info(f'detail: {detail}', also_console=False)
        if not ok: raise AssertionError(str(detail) or 'check failed')

    # ------------------------------------------------------------------ PC tool (real dingoFW parameter protocol)
    def _flush(s, limit_ms=6000):
        t = 0
        while s._ecun('Pending') and t < limit_ms: s._run(20); t += 20
        return s._ecun('Failed')
    def _ask(s, base, payload, reply_base=None, wait_ms=400):
        s._ecu('ClearStats'); s._ecu(f'QueueRequest {base + 1:#x} "{bytes(payload).hex()}" {(reply_base or base):#x}')
        if s._flush(wait_ms): return None
        return bytes.fromhex(s._ecu('LastReply'))
    def _write1(s, base, index, sub, val, reply_base=None):
        return s._ask(base, bytes([s.ps.CMD['Write'], index & 255, index >> 8, sub]) + struct.pack('<I', val & 0xFFFFFFFF), reply_base)
    def _read1(s, base, index, sub):
        d = s._ask(base, [s.ps.CMD['Read'], index & 255, index >> 8, sub, 0, 0, 0, 0]); return None if d is None else struct.unpack('<I', d[4:8])[0]
    def _version(s, base):
        d = s._ask(base, [s.ps.CMD['Version'], 0, 0, 0, 0, 0, 0, 0]); return None if d is None else (d[4], d[5], (d[6] << 8) | d[7])
    def _burn(s, base):
        # the reply comes after the FRAM write: 4.4 kB at 400 kbit/s on I2C is about 100 ms, so wait longer than for a parameter
        s._ecu('ReplyTimeoutUs 1000000'); d = s._ask(base, [s.ps.CMD['BurnSettings'], 1, 3, 8, 0, 0, 0, 0], wait_ms=3500); s._ecu('ReplyTimeoutUs 100000')
        return bool(d and d[4])
    def _W(s, k, index, sub, val):          # queued: sent one after the other, each waits for its reply
        s.writes += 1
        p = bytes([s.ps.CMD['Write'], index & 255, index >> 8, sub]) + struct.pack('<I', val & 0xFFFFFFFF)
        s._ecu(f'QueueRequest {BASE[k] + 1:#x} "{p.hex()}" {BASE[k]:#x}')

    # ------------------------------------------------------------------ boards
    def _bitrate(s, k):
        v = s._n('sysbus.canBtrSpy LastValue', MACH[k])        # last CAN_BTR value the firmware wrote
        return round(PCLK1 / (((v & 0x3FF) + 1) * (3 + ((v >> 16) & 15) + ((v >> 20) & 7))))
    def _status(s, k, frames=None):
        frames = frames or (0, 1, 2, 3, s.ps.STATUS_MSG)
        st = s.ps.Status(BASE[k])
        for n in frames:
            h = s._ecu(f'Last {BASE[k] + 2 + n:#x}')
            if h != 'none': f = s.ps.Frame(BASE[k] + 2 + n, bytes.fromhex(h)); f.t = s.now; st.feed(f)
        return st
    def _age_ms(s, k): return s._ecun(f'AgeUs {BASE[k] + 2:#x}') / 1000.0
    def _pins_on(s):
        m = {k: s._n('sysbus.adc1 OutputsOn', MACH[k]) for k in BASE}
        return [g for g, (k, o) in s.OUT.items() if (m[k] >> o) & 1]
    def _can_on(s):
        st = {k: s._status(k, (3,)) for k in BASE}
        return [g for g, (k, o) in s.OUT.items() if st[k].out_state(o) == 1]
    def _pin(s, k, name): return s._x(f'sysbus.adc1 PinLevel "{name}"', MACH[k]) == 'True'
    def _fatal(s, k): return s._pin(k, 'PC0') or not s._pin(k, 'PC1')          # error LED on, or status LED off
    def _set_cmd(s, on):
        s.cmd = [1 if g in on else 0 for g in range(1, 25)]; v = sum(b << i for i, b in enumerate(s.cmd))
        s._ecu(f'SetPeriodicData {ECU_ID:#x} "{bytes([v & 255, (v >> 8) & 255, (v >> 16) & 255, 0xA5, 0, 0, 0, 0]).hex()}"')
    def _ecu_on(s): s._ecu(f'SetPeriodic {ECU_ID:#x} "000000A500000000" 20000'); s._set_cmd([g for g in range(1, 25) if s.cmd[g - 1]])
    def _ecu_off(s): s._ecu(f'RemovePeriodic {ECU_ID:#x}')
    def _plug(s, k, on): s._x(('connector Connect' if on else 'connector Disconnect') + ' sysbus.can1 bus', MACH[k])
    def _input(s, k, i, high):
        p = s.model[k]['inputs'][i][0]; s._x(f'sysbus.gpioPort{p[1]} OnGPIO {int(p[2:])} {"true" if high else "false"}', MACH[k])
    def _load(s, g, amps): k, o = s.OUT[g]; s._x(f'sysbus.adc1 SetLoad {o} {s.vbat / amps:.4f}', MACH[k])
    def _settle_inputs(s, ks):
        """The world outside the MCU: nothing on USB (VBUS low), every digital input wire low. Renode's GPIO model
        shows the board-init ODR value on input pins until something drives them, so this runs 10 ms after each start."""
        s._run(10)
        for k in ks:
            s._x('sysbus.gpioPortA OnGPIO 9 false', MACH[k])
            for i in range(len(s.model[k]['inputs'])): s._input(k, i, False)
    def _power_cycle(s, *ks):
        # supply off and on: the MCP9808 sees a power-on reset too (a plain machine Reset is an MCU reset only)
        for k in ks: s._x('sysbus.i2c1.tempSensor PowerOnReset', MACH[k]); s._x('machine Reset', MACH[k])
        s._settle_inputs(ks)
    def _fram_written(s, k): return s._n('sysbus.i2c1.fram BytesWritten', MACH[k])

    # ------------------------------------------------------------------ S1 commissioning
    def start_bench(s):
        s._x(f'include @{s.resc}'); s._run(10)
        s.vbus_before = {k: (s._n('sysbus ReadDoubleWord 0x40020010', MACH[k]) >> 9) & 1 for k in BASE}    # GPIOA IDR bit 9, before the bench drives it
        s._settle_inputs(list(BASE)); s._run(1480)

    def fresh_boards_answer_on_their_own_ids(s):
        br = {k: s._bitrate(k) for k in BASE}; ver = {k: s._version(BASE[k]) for k in BASE}
        s._check(all(v == 1000000 for v in br.values()) and all(v == s.ps.FW_VERSION for v in ver.values()), f'bit rates {br}, versions {ver}; USB VBUS pin read before the bench drove it low: {s.vbus_before}')

    def no_board_is_in_fatal_error(s):
        f = {k: s._fatal(k) for k in BASE}; st = {k: s._status(k, (0,)) for k in BASE}
        batt = {k: st[k].batt() for k in BASE}
        s._check(not any(f.values()) and all(b is not None and abs(b - s.vbat) < 0.3 for b in batt.values()), f'fatal {f}, battery volts in status {batt}')

    def fresh_boards_wrote_default_config_to_fram(s):
        w = {k: s._fram_written(k) for k in BASE}; s.fram_w = w
        s._check(all(4000 < v < 5000 for v in w.values()), f'FRAM bytes written at first start {w}')

    def power_cycle_keeps_ids_and_config(s):
        s._power_cycle(*BASE)
        s._ecu('ClearSeen'); s._run(1500)
        br = {k: s._bitrate(k) for k in BASE}; ver = {k: s._version(BASE[k]) for k in BASE}; w = {k: s._fram_written(k) for k in BASE}
        seen = {k: s._ecun(f'Count {BASE[k] + 2:#x}') for k in BASE}
        s._check(all(v == 1000000 for v in br.values()) and all(v == s.ps.FW_VERSION for v in ver.values()) and all(v > 0 for v in seen.values())
                 and w == s.fram_w and not any(s._fatal(k) for k in BASE), f'bit rates {br}, versions {ver}, status frames {seen}, FRAM bytes written {w} (unchanged = config was read back valid)')

    def factory_defaults_fan_output_and_temperature_limits(s):
        # fans: board A2 OUT2 (global output 10) is OFF at room temperature (temperature-switched since 2026-11-14);
        # r5a / r6c: limits 55 / 80 / 6 deg C; s10b exempt mask; s11c critical-soon margin 5 (param block 0x7F00 sub 0-4)
        seen = []
        for _ in range(10): s._run(200); seen.append(s._pins_on())
        st = s._status('A2', (3,)).out_state(s.OUT[10][1])
        lim = {k: tuple(s._read1(BASE[k], s.ps.TEMP_INDEX, sub) for sub in (0, 1, 2, 3, 4)) for k in BASE}
        s._check(s.OUT[10] == s.ps.FAN and all(p == [] for p in seen) and st == 0, f'output pins high every 200 ms for 2 s at 30 C: {seen}; A2 OUT2 status {st}')
        s._check(lim == {'A1': (55, 80, 6, 0, 5), 'A2': (55, 80, 6, 2, 5), 'B': (55, 80, 6, 0, 5)}, f'warn / critical / recovery / critical-exempt mask / critical-soon margin from the boards: {lim}')

    def _fan_steps(s, steps, ms=800):
        out = []
        for k, c in steps:
            s._temp(k, c); s._run(ms); out.append((k, c, 10 in s._pins_on()))
        return out

    def fan_follows_a2_temperature_ramp(s):
        # Dan s12a: on at 45, off at 40 deg C; A2's own MCP9808; A1 / B stay at 30 C
        got = s._fan_steps([('A2', 30.0), ('A2', 46.0), ('A2', 42.0), ('A2', 39.0)])
        s._temp('A2', 30.0); s._run(400)
        s._check([v for k, c, v in got] == [False, True, True, False], f'(board, C, fan on) {got}')

    def fan_turns_on_when_only_a_remote_board_is_hot(s):
        # Dan s13a: the hottest of the three boards; A1 / B board temperature reaches A2 in their msg 0 over CAN
        got = s._fan_steps([('A1', 47.0), ('A1', 41.0), ('A1', 39.0), ('B', 46.0), ('B', 30.0)])
        s._temp('A1', 30.0); s._run(400)
        s._check([v for k, c, v in got] == [True, True, False, True, False], f'A2 at 30 C; (board, C, fan on) {got}')

    # ------------------------------------------------------------------ S2 the single-PDM layer (recipe from s1_system.py)
    def _can_input(s, k, slot, can_id, bit, timeout):
        for sub, val in [(4, can_id), (5, bit), (6, 1), (11, 0), (12, s.ps.f32(1.0)), (2, TIMEOUT_MS), (1, 1 if timeout else 0), (0, 1)]: s._W(k, 0x1300 + slot, sub, val)
    def _set_output(s, g, policy, source=('ecu', None)):
        k, o = s.OUT[g]; slot = o
        if source[0] == 'ecu': s._can_input(k, slot, ECU_ID, g - 1, timeout=policy != 'hold')
        else:
            sk, si = s.INP[source[1]]; s._can_input(k, slot, BASE[sk] + 2 + s.ps.STATUS_MSG, si, timeout=policy != 'hold')
        var = s._var(k, 'canin', slot)
        if policy == 'on':
            v = s.virt_used[k]; s.virt_used[k] += 1
            for sub, val in [(2, s._var(k, 'canin', slot)), (3, 1), (4, 1), (5, s._var(k, 'canin', ALIVE_SLOT)), (0, 1)]: s._W(k, 0x1400 + v, sub, val)
            var = s._var(k, 'virt', v)
        for sub, val in [(2, s.ps.f32(s.LIMIT[g])), (3, s.ps.f32(s.LIMIT[g] * 2)), (1, var), (0, 1)]: s._W(k, 0x1000 + o, sub, val)
    def _alive_input(s, k):
        for sub, val in [(4, ECU_ID), (5, 24), (6, 8), (11, 0), (12, s.ps.f32(165.0)), (2, TIMEOUT_MS), (1, 1), (0, 1)]: s._W(k, 0x1300 + ALIVE_SLOT, sub, val)

    def configure_as_one_pdm_and_save(s):
        s._ecu_on(); s._set_cmd([]); s._run(100); s._ecu('ClearStats'); t0 = s.now
        policy = {g: 'off' for g in range(1, 25)}; policy.update({1: 'hold', 2: 'off', 3: 'on', 21: 'hold', 22: 'off', 23: 'on'})
        for k in BASE: s._alive_input(k)
        s.cross_in = [n for n, v in s.INP.items() if v == ('B', 2)][0]
        for g in range(1, 25):
            if g == 5: s._set_output(5, 'off', source=('input', s.cross_in))      # cross-board rule: B input-board ch 1 -> output 5 (on A1)
            else: s._set_output(g, policy[g])
        failed = s._flush(); done = s._ecun('Done'); secs = (s.now - t0) / 1000.0; fl = s._ecu('FailedList')
        retries = s._ecun('Retries'); rl = s._ecu('RetriedList')
        burned = {k: s._burn(BASE[k]) for k in BASE}
        s._write1(BASE['B'], 0x1200 + 2, 0, 1)                                       # enable board B input 3 (input-board channel 1)
        for g in s.OUT: s._load(g, s.LIMIT[g] * 0.6)
        s._run(300)
        s._check(failed == 0 and done == s.writes and all(burned.values()), f'{s.writes} parameter writes, {done} acknowledged, {failed} failed {fl}, {retries} sent a second time after 100 ms without a reply {rl}, {secs:.2f} s, saved to FRAM {burned}')

    def walking_one_ecu_bit_through_23_outputs(s):
        bad = []
        for g in range(1, 25):
            if g == 5: continue
            s._set_cmd([g]); s._run(200); p, c = s._pins_on(), s._can_on()
            if p != [g] or c != [g]: bad.append((g, p, c))
        s._set_cmd([]); s._run(200)
        s._check(not bad, f'(output, pins high, status says on) where wrong: {bad}')

    def cross_board_rule_switches_and_releases(s):
        s._input('B', 2, True); t = 0
        while 5 not in s._pins_on() and t < 2000: s._run(10); t += 10
        on = s._pins_on(); s._input('B', 2, False); s._run(400); off = s._pins_on()
        s._check(on == [5] and off == [], f'on after {t} ms (10 ms steps): pins {on}; after release: {off}')

    def one_total_current_number_from_three_boards(s):
        on = (1, 9, 17, 21); s._set_cmd(on); s._run(400)
        total = sum((s._status(k, (0,)).total() or 0) for k in BASE); want = sum(s.LIMIT[g] * 0.6 for g in on)
        fatal = {k: s._fatal(k) for k in BASE}; s._set_cmd([]); s._run(300)
        s._check(abs(total - want) <= 4 and not any(fatal.values()), f'{total} A shown, {want:.1f} A real (CAN sends whole amps); fatal {fatal}')

    # ------------------------------------------------------------------ S3 link loss
    def _snapshot(s): p = s._pins_on(); return {g: int(g in p) for g in WATCH + [5]}
    def _case(s, name, pre, fault, undo):
        s._set_cmd(WATCH if pre else []); s._run(TIMEOUT_MS + 300); before = s._snapshot(); t0 = s.now; fault(); trace = {g: None for g in WATCH}
        while s.now < t0 + 2500:
            s._run(STEP); p = s._pins_on()
            for g in WATCH:
                if trace[g] is None and (g in p) != bool(before[g]): trace[g] = s.now - t0
        after = s._snapshot(); stale = {k: round(s._age_ms(k)) for k in BASE}
        undo(); s._run(TIMEOUT_MS + 500); back = s._snapshot()
        r = dict(before=before, after=after, change_ms=trace, recovered=back, status_age_ms=stale); s.matrix[(name, pre)] = r
        logger.info(f'{name} (cmd {"ON" if pre else "OFF"}): {r}', also_console=False); return r
    def _in_window(s, ms): return ms is not None and TIMEOUT_MS - 100 <= ms <= TIMEOUT_MS + 200

    def ecu_goes_quiet_while_outputs_are_on(s):
        r = s._case('ecu', 1, s._ecu_off, s._ecu_on); a = r['after']
        s._check(all(r['before'][g] == 1 for g in WATCH), f'outputs were not all on before the fault: {r["before"]}')
        s._check(a[1] == 1 and a[21] == 1, f'policy hold did not stay ON: {a}')
        s._check(a[2] == 0 and a[22] == 0 and s._in_window(r['change_ms'][2]) and s._in_window(r['change_ms'][22]), f'policy off: after {a}, change at ms {r["change_ms"]}')
        s._check(a[3] == 1 and a[23] == 1, f'policy on did not stay ON: {a}')
        s._check(all(r['recovered'][g] == 1 for g in WATCH), f'did not follow the ECU again: {r["recovered"]}')

    def ecu_goes_quiet_while_outputs_are_off(s):
        r = s._case('ecu', 0, s._ecu_off, s._ecu_on); a = r['after']
        s._check(a[1] == 0 and a[21] == 0, f'policy hold did not stay OFF: {a}')
        s._check(a[2] == 0 and a[22] == 0, f'policy off turned on: {a}')
        s._check(a[3] == 1 and a[23] == 1 and s._in_window(r['change_ms'][3]) and s._in_window(r['change_ms'][23]), f'policy on: after {a}, change at ms {r["change_ms"]}')
        s._check(all(v == 0 for g, v in r['recovered'].items() if g != 5), f'did not follow the ECU again: {r["recovered"]}')

    def board_a1_unplugged_from_can(s):
        r = s._case('A1', 1, lambda: s._plug('A1', False), lambda: s._plug('A1', True)); a = r['after']; age = r['status_age_ms']
        s._check((a[1], a[2], a[3]) == (1, 0, 1) and (a[21], a[22], a[23]) == (1, 1, 1), f'after {a}')
        s._check(age['A1'] > 2000 and age['B'] < 250 and age['A2'] < 250, f'status age ms {age}')
        s._check(all(r['recovered'][g] == 1 for g in WATCH), f'recovered {r["recovered"]}')

    def board_b_unplugged_from_can(s):
        r = s._case('B', 1, lambda: s._plug('B', False), lambda: s._plug('B', True)); a = r['after']; age = r['status_age_ms']
        s._check((a[21], a[22], a[23]) == (1, 0, 1) and (a[1], a[2], a[3]) == (1, 1, 1), f'after {a}')
        s._check(age['B'] > 2000 and age['A1'] < 250, f'status age ms {age}')
        s._check(all(r['recovered'][g] == 1 for g in WATCH), f'recovered {r["recovered"]}')

    def cross_board_rule_drops_when_its_source_board_is_lost(s):
        s._set_cmd([]); s._input('B', 2, True); s._run(500); pre = 5 in s._pins_on()
        s._plug('B', False); t = 0
        while 5 in s._pins_on() and t < 3000: s._run(STEP); t += STEP
        s._plug('B', True); s._run(500); post = 5 in s._pins_on(); s._input('B', 2, False); s._run(400)
        s._check(pre and s._in_window(t) and post and 5 not in s._pins_on(), f'on before {pre}, dropped after {t} ms, back {post}')

    def board_restarts_with_no_ecu_on_the_bus(s):
        s._set_cmd(WATCH); s._run(500); s._ecu_off(); s._run(100)
        s._power_cycle('A1'); t0 = s.now; first_on = None
        while s.now < t0 + 3000:
            s._run(STEP)
            if first_on is None and 3 in s._pins_on(): first_on = s.now - t0
        p = s._pins_on(); got = {g: int(g in p) for g in (1, 2, 3)}
        s._ecu_on(); s._run(800); back = s._pins_on()
        s._check(got == {1: 0, 2: 0, 3: 1}, f'{got} (default-on output came on {first_on} ms after the restart)')
        s._check(all(g in back for g in (1, 2, 3)), f'after the ECU returned: {back}')

    def board_restarts_while_the_ecu_is_talking(s):
        w = s._fram_written('A1'); s._power_cycle('A1'); t0 = s.now; first = {}
        while s.now < t0 + 2000:
            s._run(STEP); p = s._pins_on()
            for g in (1, 2, 3):
                if g not in first and g in p: first[g] = s.now - t0
        ok = s._bitrate('A1') == 1000000 and s._version(BASE['A1']) is not None and s._fram_written('A1') == w
        s._set_cmd([]); s._run(300)
        s._check(len(first) == 3 and ok, f'outputs back at ms {first}; config still valid {ok}')

    # ------------------------------------------------------------------ overcurrent (defaults from core/param_defs.h: Count mode, 3 tries, 1 s apart, 1 s inrush)
    def overcurrent_retries_three_times_then_latches_fault(s):
        g = 4; k, o = s.OUT[g]; s._load(g, 10.0)                # 10 A: above the 7.5 A limit, below the 15 A inrush limit
        s._set_cmd([g]); t0 = s.now; edges = []; last = 0; states = set()
        while s.now < t0 + 8000:
            s._run(STEP); lvl = int(g in s._pins_on())
            if lvl != last: edges.append((s.now - t0, lvl)); last = lvl
            if (s.now - t0) % 200 == 0: states.add(s._status(k, (3,)).out_state(o))
        final = s._status(k, (3,)).out_state(o); rises = [t for t, l in edges if l == 1]; falls = [t for t, l in edges if l == 0]
        on_ms = [f - r for r, f in zip(rises, falls)]
        s._load(g, s.LIMIT[g] * 0.6); s._run(1500); still = s._status(k, (3,)).out_state(o); pin_after = int(g in s._pins_on())
        s._power_cycle(k); s._run(1500); p = s._pins_on(); again = s._status(k, (3,)).out_state(o)
        s._set_cmd([]); s._run(300)
        s._check(len(rises) == 3 and len(falls) == 3 and all(900 <= x <= 1150 for x in on_ms), f'ON pulses at ms {rises}, lengths {on_ms}, edges {edges}')
        s._check(final == 3 and 2 in states and still == 3 and pin_after == 0, f'status states seen {states}, final {final} (3 = Fault), with a normal load still {still}, pin {pin_after}')
        s._check(g in p and again == 1, f'after a power cycle: pins {p}, state {again}')

    # ------------------------------------------------------------------ temperature sensor (I2C)
    def board_temperature_reaches_the_status_frame(s):
        k = 'A2'; st = s._status(k, (0,)); t30 = struct.unpack('<H', st.m[0][6:8])[0]; run_state = st.dev_state()
        s._x('sysbus.i2c1.tempSensor Temperature 60', MACH[k]); s._run(800)
        st = s._status(k, (0,)); t60 = struct.unpack('<H', st.m[0][6:8])[0]; hot_state = st.dev_state()
        s._x('sysbus.i2c1.tempSensor Temperature 30', MACH[k]); s._run(800); back = s._status(k, (0,)).dev_state()
        s._check(t30 == 300 and t60 == 600 and hot_state != run_state and back == run_state, f'temperature x10: {t30} then {t60}; device state {run_state} -> {hot_state} -> {back}')

    # ------------------------------------------------------------------ thermal (r5a; limits = factory defaults 55 / 80 / 6 deg C)
    def _temp(s, k, board_c=None, die_c=None):
        if board_c is not None: s._x(f'sysbus.i2c1.tempSensor Temperature {board_c}', MACH[k])
        if die_c is not None: s._x(f'sysbus.adc1 DieTemperature {die_c}', MACH[k])
    def _a1_on(s): return [g for g in s._pins_on() if s.OUT[g][0] == 'A1']
    def _info(s, k):            # last frame on the board's base ID: info / error messages (no tool request is running)
        h = s._ecu(f'Last {BASE[k]:#x}'); d = bytes.fromhex(h) if h != 'none' else bytes(8)
        return (chr(d[0]), d[1], struct.unpack('<H', d[2:4])[0], struct.unpack('<H', d[4:6])[0])

    def board_and_die_temperatures_reach_can(s):
        s._temp('A1', 47.5, 63.0); s._temp('A2', 52.0, 41.0); s._run(800)
        got = {k: (struct.unpack('<H', s._status(k, (0,)).m[0][6:8])[0], s._status(k, (s.ps.STATUS_MSG,)).die_temp_x10()) for k in ('A1', 'A2')}
        want = {'A1': (475, s.ps.die_temp_can(63.0)), 'A2': (520, s.ps.die_temp_can(41.0))}
        s._temp('A1', 30, 30); s._temp('A2', 30, 30); s._run(400)
        s._check(all(got[k][0] == want[k][0] and abs(got[k][1] - want[k][1]) <= 4 for k in got), f'board / die x10: got {got}, want {want}')

    def above_warn_outputs_unchanged(s):
        s._set_cmd([1, 2, 4]); s._run(400); before = s._a1_on(); st0 = s._status('A1', (0,)).dev_state()
        s._temp('A1', 56.0); s._run(600); hot = s._a1_on(); st1 = s._status('A1', (0,)).dev_state(); msg = s._info('A1')
        s._temp('A1', 40.0); s._run(600); back = s._status('A1', (0,)).dev_state()
        s._check(before == [1, 2, 4] and hot == before and (st0, st1, back) == (0, 2, 0) and msg == ('E', 3, 560, 0), f'A1 outputs on {before} -> {hot}; state {st0} -> {st1} -> {back}; last message {msg}')

    def at_critical_all_off_then_recovers_below_critical_minus_hysteresis(s):
        s._set_cmd([1, 2, 4]); s._run(400); before = s._a1_on(); others = [g for g in s._pins_on() if s.OUT[g][0] != 'A1']
        s._temp('A1', 80.0); t = 0
        while s._a1_on() and t < 1000: s._run(STEP); t += STEP
        s._run(200)                 # status frame 0 goes out every 100 ms: let it carry the new state
        off = s._a1_on(); st = s._status('A1', (0,)).dev_state(); msg = s._info('A1'); others_hot = [g for g in s._pins_on() if s.OUT[g][0] != 'A1']
        trace = []
        for c in (79.5, 80.0, 79.5, 80.0, 77.0, 74.0): s._temp('A1', c); s._run(400); trace.append((c, s._a1_on()))
        s._temp('A1', 73.5); t2 = 0
        while s._a1_on() != before and t2 < 1000: s._run(STEP); t2 += STEP
        back = s._a1_on(); fatal = s._fatal('A1')
        s._temp('A1', 30.0); s._set_cmd([]); s._run(600)
        s._check(before == [1, 2, 4] and off == [] and t <= 300 and st == 2 and msg == ('E', 9, 800, 800) and others_hot == others,
                 f'A1 on {before}, all off after {t} ms: {off}; state {st}; last message {msg}; other boards {others} -> {others_hot}')
        s._check(all(p == [] for c, p in trace), f'still off near the limit and at 74.0 C (recovery below 74): {trace}')
        s._check(back == before and t2 <= 300 and not fatal, f'back on {back} {t2} ms after 73.5 C, fatal {fatal}')

    def thermal_flags_in_every_status_frame_and_critical_soon_message(s):
        # Dan s11c: msg 3 byte 7 = bit 0 over warn, 1 critical soon (>= 80 - 5), 2 critical; sampled every 100 ms for 1 s
        mid = BASE['A1'] + 2 + 3; res = []; msg = None
        for c, want in ((30.0, 0), (56.0, 1), (76.0, 3), (81.0, 5), (30.0, 0)):
            s._temp('A1', c); s._run(700)
            if c == 76.0: msg = s._info('A1')
            n0 = s._ecun(f'Count {mid:#x}'); samples = []
            for _ in range(10): s._run(100); samples.append(bytes.fromhex(s._ecu(f'Last {mid:#x}'))[7])
            res.append((c, want, samples, s._ecun(f'Count {mid:#x}') - n0))
        s._set_cmd([]); s._run(400)
        bad = [r for r in res if any(x != r[1] for x in r[2]) or not 9 <= r[3] <= 11]
        s._check(not bad, f'(C, want, flags every 100 ms, msg 3 frames in 1 s) wrong: {bad}; all {res}')
        s._check(msg == ('R', 9, 760, 800), f'last message on A1 base ID after reaching 76 C: {msg} (want Warning R, src Overtemp 9, 760, limit 800)')

    # ------------------------------------------------------------------ manual ID / bit-rate change (s1 'option b')
    def manual_id_and_bit_rate_change_survives_a_restart(s):
        ok1 = s._write1(0x500, 0x0000, 0, 0x6A0, reply_base=0x6A0) is not None
        ok2 = s._write1(0x6A0, 0x0000, 1, 1) is not None; ok3 = s._burn(0x6A0)
        s._power_cycle('A1'); s._run(1200); br = s._bitrate('A1'); ver = s._version(0x6A0)
        # put it back so the bench ends in its normal state (the hub has no bit timing, so the board is still reachable)
        r1 = s._write1(0x6A0, 0x0000, 0, 0x500, reply_base=0x500) is not None; r2 = s._write1(0x500, 0x0000, 1, 0) is not None; r3 = s._burn(0x500)
        s._power_cycle('A1'); s._run(1200); br2 = s._bitrate('A1'); ver2 = s._version(0x500)
        s._check(ok1 and ok2 and ok3 and br == 500000 and ver == s.ps.FW_VERSION, f'writes {ok1} {ok2}, saved {ok3}, after restart {br} bit/s, version on 0x6A0 {ver}')
        s._check(r1 and r2 and r3 and br2 == 1000000 and ver2 == s.ps.FW_VERSION, f'restore: {r1} {r2} {r3}, {br2} bit/s, {ver2}')

    # ------------------------------------------------------------------ sleep (Dan s7a) and MCP9808 read failures
    def _pins(s, k, names): return {p: int(s._pin(k, p)) for p in names}
    def _mcp(s, k, prop): return s._x(f'sysbus.i2c1.tempSensor {prop}', MACH[k])
    def _symbol(s, elf, name):
        """Address of a (possibly file-local, LTO) function in a bench ELF, from arm-none-eabi-nm (Renode's symbol
        lookup does not find local symbols)."""
        import re, subprocess
        path = re.search(r'LoadELF @(\S*' + re.escape(elf) + ')', open(s.resc).read()).group(1)
        for ln in subprocess.run(['arm-none-eabi-nm', '-C', path], capture_output=True, text=True).stdout.splitlines():
            f = ln.split(' ', 2)
            if len(f) == 3 and f[2] == name and f[0]: return int(f[0], 16)
        raise AssertionError(f'{name} not in {path}')
    def _a1_lines(s):
        m = s.model['A1']['outputs']
        return sorted({o[1] for o in m}), sorted({o[2] for o in m}), [o[0] for o in m]

    def sleep_drives_every_profet_line_low_and_shuts_the_sensor_down(s):
        den, dsel, ins = s._a1_lines()
        # Renode does not model STOP mode: SysTick keeps running and ends the WFI at once (seen: the board reset and
        # restarted about 620 ms after the request). So the bench halts the CPU where the firmware enters STOP
        # (EnterStopMode, after every sleep step); the pins and the sensor then hold what they hold in STOP mode.
        s._ecu_off(); s._plug('A2', False); s._plug('B', False); s._temp('A1', 33.0); s._run(TIMEOUT_MS + 300)   # policy 'on' output 3 comes on
        s._x(f'sysbus.cpu AddHook {s._symbol("custompdm_a_unit1.elf", "EnterStopMode()"):#x} "self.IsHalted = True"', 'a1')
        before = (s._pins('A1', den), s._a1_on(), s._pins('A1', s.ps.LEDS), s._mcp('A1', 'Shutdown'), s._mcp('A1', 'AlertEnabled'))
        s._ecu(f'Send {BASE["A1"] + 1:#x} "{(bytes([s.ps.CMD["Sleep"]]) + b"QUIT" + bytes(3)).hex()}"'); s._run(200)
        age0 = s._age_ms('A1'); s._run(500); age1 = s._age_ms('A1'); halted = s._x('sysbus.cpu IsHalted', 'a1')
        after = (s._pins('A1', den + dsel + ins), s._pins('A1', s.ps.LEDS), s._mcp('A1', 'Shutdown'), s._mcp('A1', 'AlertEnabled'),
                 int(s._mcp('A1', 'ShutdownWrites'), 0), int(s._mcp('A1', 'RejectedShutdowns'), 0))
        s.slept = age1 - age0 >= 450 and halted == 'True'
        s._check(all(v == 1 for v in before[0].values()) and before[1] == [3] and before[2] == {'PC0': 0, 'PC1': 1} and before[3:] == ('False', 'True'),
                 f'before the request: DEN {before[0]}, A1 outputs on {before[1]}, LEDs {before[2]}, sensor shutdown / alert {before[3:]}')
        s._check(s.slept and all(v == 0 for v in after[0].values()) and after[1] == {'PC0': 0, 'PC1': 0} and after[2:] == ('True', 'False', 1, 0),
                 f'asleep (CPU stopped at EnterStopMode {halted}, status frames {age0:.0f} -> {age1:.0f} ms old): IN / DEN / DSEL {after[0]}, LEDs {after[1]}, sensor shutdown / alert / shutdown writes / rejected {after[2:]}')

    def wake_up_restores_den_and_the_sensor_without_a_stale_reading(s):
        den, dsel, ins = s._a1_lines()
        s._temp('A1', 41.5)                              # warmer now; the sensor still holds 33.0 C from before sleep
        # wake-up: the firmware resets the MCU after STOP (NVIC_SystemReset). EXTI wake from STOP is not emulated, so
        # the bench does that MCU reset itself; the MCP9808 gets no power-on reset (models/PdmI2C.cs)
        s._x('machine Reset', 'a1'); s._x('sysbus.cpu IsHalted false', 'a1'); s._settle_inputs(['A1'])
        temps = []; t = 0; den_first = None
        while t < 1500:
            s._run(20); t += 20
            if s._age_ms('A1') < 30:
                if den_first is None: den_first = s._pins('A1', den)
                temps.append(struct.unpack('<H', bytes.fromhex(s._ecu(f'Last {BASE["A1"] + 2:#x}'))[6:8])[0])
        mcp = (s._mcp('A1', 'Shutdown'), s._mcp('A1', 'AlertEnabled'), s._mcp('A1', 'Locked'), int(s._mcp('A1', 'ShutdownWrites'), 0))
        s._plug('A2', True); s._plug('B', True); s._ecu_on(); s._set_cmd([]); s._temp('A1', 30.0); s._run(600)
        fatal = s._fatal('A1')
        s._check(den_first is not None and all(v == 1 for v in den_first.values()), f'status frames again: {den_first is not None}; DEN at the first one {den_first}')
        s._check(mcp == ('False', 'True', 'False', 1) and not fatal, f'sensor shutdown / alert / locked / shutdown writes {mcp} (no power-on reset in between); fatal {fatal}')
        s._check(temps and set(temps) <= {0, 415} and 415 in temps, f'board temperature x10 in msg 0 after the wake-up (0 = no reading yet; 330 would be the stale pre-sleep value): {temps}')

    def sensor_read_failures_keep_critical_and_send_a_fault_message(s):
        s._set_cmd([1, 2, 4]); s._run(400); before = s._a1_on()
        s._temp('A1', 80.0); s._run(600); crit = (s._a1_on(), s._status('A1', (0,)).dev_state())
        s._mcp('A1', 'Nak true'); s._temp('A1', 40.0); s._run(2000)          # the sensor would read 40 C if it answered
        st = s._status('A1', (0,)); held = (s._a1_on(), st.dev_state(), st.board_temp_x10()); msg = s._info('A1')
        s._mcp('A1', 'Nak false'); t = 0
        while s._a1_on() != before and t < 1000: s._run(STEP); t += STEP
        on_back = s._a1_on(); s._run(200)       # status frame 0 (100 ms period) carries the new state
        back = (on_back, s._status('A1', (0,)).dev_state()); s._set_cmd([]); s._temp('A1', 30.0); s._run(400)
        s._check(before == [1, 2, 4] and crit == ([], 2), f'A1 on {before}; at 80 C {crit}')
        s._check(held == ([], 2, 800) and msg[:3] == ('E', 14, 4), f'2 s of NAKs while it cools to 40 C: outputs / state / msg 0 temp {held}; last message {msg} (E, TempSensor = 14, 4 in a row, I2C flags)')
        s._check(back == ([1, 2, 4], 0) and t <= 600, f'reads back: {back} after {t} ms')

    # ------------------------------------------------------------------ wake-up set (Dan B2): param 0x7F00 sub 5
    # Only the config side runs here: Renode does not emulate STOP mode, so which pins wake the MCU is checked in
    # the host sim (s0 / s1 S6, EXTI model), not in Renode.
    def wake_mask_defaults_to_none_and_a_valid_mask_is_taken(s):
        WI, WS = s.ps.TEMP_INDEX, s.ps.WAKE_SUB
        dflt = {k: s._read1(BASE[k], WI, WS) for k in BASE}
        rep = {k: s._write1(BASE[k], WI, WS, m) for k, m in (('A1', 0x073), ('B', 0x1FE))}
        back = {k: s._read1(BASE[k], WI, WS) for k in ('A1', 'B')}
        s._check(dflt == {'A1': 0, 'A2': 0, 'B': 0}, f'factory default wake mask on every board (0 = no input wakes it): {dflt}')
        s._check(rep['A1'] is not None and struct.unpack('<I', rep['A1'][4:8])[0] == 0x073 and rep['B'] is not None and struct.unpack('<I', rep['B'][4:8])[0] == 0x1FE
                 and back == {'A1': 0x073, 'B': 0x1FE}, f'Write replies {rep}, read back {back}')

    def wake_mask_on_a_shared_or_usb_line_is_refused_with_a_warning(s):
        WI, WS = s.ps.TEMP_INDEX, s.ps.WAKE_SUB; got = {}
        for k, m in (('A1', 0x005), ('A1', 0x008), ('B', 0x101), ('B', 0x200)):
            n0 = s._ecun(f'Count {BASE[k]:#x}'); s._ecu('ClearStats')
            s._ecu(f'QueueRequest {BASE[k] + 1:#x} "{(bytes([s.ps.CMD["Write"], WI & 255, WI >> 8, WS]) + struct.pack("<I", m)).hex()}" {BASE[k]:#x}')
            failed = s._flush(1000); n1 = s._ecun(f'Count {BASE[k]:#x}'); w = s._info(k); wd = bytes.fromhex(s._ecu(f'Last {BASE[k]:#x}'))
            got[(k, m)] = (failed, n1 - n0, w[:2], struct.unpack('<HHH', wd[2:8]), s._read1(BASE[k], WI, WS))
        want = {('A1', 0x005): (1, 3, ('R', s.ps.SRC_CONFIG), (0x005, 0x005, 0x073), 0x073), ('A1', 0x008): (1, 3, ('R', s.ps.SRC_CONFIG), (0x008, 0x008, 0x073), 0x073),
                ('B', 0x101): (1, 3, ('R', s.ps.SRC_CONFIG), (0x101, 0x101, 0x1FE), 0x1FE), ('B', 0x200): (1, 3, ('R', s.ps.SRC_CONFIG), (0x200, 0x200, 0x1FE), 0x1FE)}
        restore = all(s._write1(BASE[k], WI, WS, 0) is not None for k in ('A1', 'B'))
        s._check(got == want and restore, f'(board, mask): (failed = no Write reply after 3 tries, frames on the reply ID = one warning per try, (type, src), (refused, bad inputs, kept), read back): {got}; reset to 0: {restore}')

    # ------------------------------------------------------------------ S7 (w1): the first msg 37 after a power-up
    def first_status_msg_after_a_power_cycle_carries_the_real_inputs(s):
        # the first cyclic round is built in InitCan, before the device thread reads any input: msg 37 skips it (port_boards.py)
        mid = BASE['B'] + 2 + s.ps.STATUS_MSG
        ok = s._write1(BASE['B'], 0x1200 + 2, 0, 1) is not None and s._burn(BASE['B'])     # B input 3 enabled and saved
        s._power_cycle('B'); s._input('B', 2, True); n0 = s._ecun(f'Count {mid:#x}'); t = 10
        while s._ecun(f'Count {mid:#x}') == n0 and t < 2000: s._run(2); t += 2
        d = bytes.fromhex(s._ecu(f'Last {mid:#x}')); s._input('B', 2, False); s._run(300)
        s._check(ok and t < 2000 and (d[0] >> 2) & 1 == 1, f'saved {ok}; first msg 37 {t} ms after the reset (2 ms steps): {d.hex()} (bit 2 = B input 3, held high from 10 ms)')
