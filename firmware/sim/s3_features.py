"""S3: feature parity with pro PDMs (ECUMaster PMU, MoTeC PDM, Link PDM), proven on the real firmware logic.

Each check is written from what a pro PDM does (vendor manual, cited in docs/feature-parity.md) and drives the
board only the way a car and a PC tool would: CAN frames from an ECU / keypad stand-in, wires on the inputs,
loads on the outputs, parameter writes over CAN. Ground truth is the PROFET IN pin of each output.
XFAIL checks are features our firmware does not have yet: each has a firmware proposal in docs/feature-parity.md
and must fail until that proposal is built (an XPASS means the doc is out of date and counts as a failure).
One board A (unit 1, factory base 0x500) per scenario. ECU stand-in sends 0x4F0 (switch bits) and 0x4F1 (values).
Usage: python3 s3_features.py <so-dir>"""
import sys, json, struct, pdmsim as ps
SO = sys.argv[1] if len(sys.argv) > 1 else '/tmp/simout'
SW_ID, VAL_ID = 0x4F0, 0x4F1
EQ, NE, GT, LT, GE, LE, BAND, BNAND = range(8)            # core/enums.h Operator
AND, OR, NOR = range(3)                                  # BoolOperator
ON_DELAY, OFF_DELAY, PULSE_RETRIG, PULSE_ONESHOT = range(4)   # TimerMode
M_ADD, M_SUB, M_MUL, M_DIV, M_MIN, M_MAX, M_AVG = range(7)    # MathOp
RISING, FALLING, BOTH = range(3)                         # InputEdge
MOMENTARY, LATCHING = 0, 1
res = []; info = {}

def check(name, ok, detail='', xfail=False):
    """xfail: the feature is a gap with a proposal; expected to fail until the proposal is built."""
    ok = bool(ok)
    tag = ('XPASS' if ok else 'XFAIL') if xfail else ('PASS' if ok else 'FAIL')
    res.append((name, tag, str(detail))); print(f'{tag} {name}' + (f' : {detail}' if detail != '' else ''))

class V:
    """Var-map indices of a custompdm_a board, in InitVarMap order (core/device.cpp); checked against VAR_MAP_SIZE."""
    def __init__(s, b):
        m = b.model; n_di = len(m['inputs']); n_out = len(m['outputs'])
        s.FALSE, s.TRUE, s.STATE, s.TEMP, s.BATT = range(5)
        s.di0 = 5; s.an0 = s.di0 + n_di; s.can0 = s.an0 + 4; s.vi0 = s.can0 + 2 * 32; s.out0 = s.vi0 + 16
        s.fl0 = s.out0 + 4 * n_out; s.cond0 = s.fl0 + 4; s.cnt0 = s.cond0 + 32; s.wip0 = s.cnt0 + 4
        s.kp0 = s.wip0 + 6; s.tm0 = s.kp0 + 2 * (20 + 2 + 4); s.math0 = s.tm0 + 2 * 8; s.dipwm0 = s.math0 + 8
        s.size = s.dipwm0 + 2 * n_di
    def di(s, i): return s.di0 + i
    def an_mv(s): return s.an0 + 1
    def an_rot(s): return s.an0 + 2
    def an_sw(s): return s.an0 + 3
    def can(s, k): return s.can0 + 2 * k              # fOutput (operator result)
    def canval(s, k): return s.can0 + 2 * k + 1       # fVal (decoded number)
    def vi(s, k): return s.vi0 + k
    def out(s, o): return s.out0 + 4 * o
    def cur(s, o): return s.out0 + 4 * o + 1
    def fault(s, o): return s.out0 + 4 * o + 3
    def fl(s, k): return s.fl0 + k
    def cond(s, k): return s.cond0 + k
    def cnt(s, k): return s.cnt0 + k
    def wiper(s, name): return s.wip0 + ['slow', 'fast', 'park', 'inter', 'wash', 'swipe'].index(name)
    def kp_btn(s, k, b): return s.kp0 + 26 * k + b
    def tm(s, k): return s.tm0 + 2 * k
    def math(s, k): return s.math0 + k
    def di_duty(s, i): return s.dipwm0 + 2 * i
    def di_freq(s, i): return s.dipwm0 + 2 * i + 1

class Rig:
    """One board A1 + PC tool + ECU stand-in on a 1 Mbit/s bus."""
    def __init__(s, unit=1):
        s.bus = ps.Bus(); s.tool = ps.Tool(s.bus); s.ecu = ps.PyNode('ecu')
        s.b = ps.Board(ps.BOARD_A, 'A1', SO, unit=unit); s.base = ps.BOARD_A['base'][unit]; s.v = V(s.b)
        s.frames = {SW_ID: bytearray(8), VAL_ID: bytearray(8)}; s.rx = []
        s.ecu.every(10000, lambda t: [s.ecu.send(i, bytes(d)) for i, d in s.frames.items()], start=3000)
        s.bus.add(s.tool, s.ecu, s.b); s.bus.watch.append(s.rx.append); s.rx_on = False
        s.bus.run_for(1500)
    def W(s, idx, sub, val):
        if isinstance(val, float): val = ps.f32(val)
        if s.tool.write(s.base, idx, sub, val) is None: raise RuntimeError(f'no reply {idx:#x}/{sub}')
    def run(s, ms): s.bus.run_for(ms)
    def pin(s, o): return s.b.level(s.b.model['outputs'][o][0])
    def var(s, i): return s.b.L.sim_var(i)
    def sw(s, bit, val):
        d = s.frames[SW_ID]; d[bit // 8] = (d[bit // 8] | (1 << (bit % 8))) if val else (d[bit // 8] & ~(1 << (bit % 8)) & 255)
    def val16(s, byte, x, signed=False, be=False):
        s.frames[VAL_ID][byte:byte + 2] = struct.pack(('>' if be else '<') + ('h' if signed else 'H'), int(x))
    def sample(s, outs, ms, step=1.0, vars=()):
        """[(t_ms, (pin levels..., var truth values...))] every step ms for ms."""
        t0 = s.bus.now; out = []
        while s.bus.now < t0 + ms * 1000:
            s.bus.run_for(step); out.append(((s.bus.now - t0) / 1000, tuple(s.pin(o) for o in outs) + tuple(int(bool(s.var(x))) for x in vars)))
        return out
    def ok_bus(s):
        c = s.b.counters(); return c['rx_overruns'] == 0 and c['tx_timeouts'] == 0 and not s.b.flags()['fatal']

# ---- parameter helpers (index / sub numbers: core/param_defs.h)
def canin(r, k, can_id, start, length=1, op=EQ, operand=1.0, factor=1.0, offset=0.0, signed=0, be=0, mode=MOMENTARY, ext=0, timeout_ms=0):
    for sub, val in [(3, ext), (4, can_id), (5, start), (6, length), (7, float(factor)), (8, float(offset)), (9, be), (10, signed),
                     (11, op), (12, float(operand)), (13, mode), (2, timeout_ms or 1000), (1, 1 if timeout_ms else 0), (0, 1)]:
        r.W(0x1300 + k, sub, val)
def switch(r, k, mode=MOMENTARY): canin(r, k, SW_ID, k, mode=mode)        # CAN switch k = bit k of 0x4F0
def value(r, k, byte, **kw): canin(r, k, VAL_ID, 8 * byte, length=16, op=GT, operand=-1e9, **kw)   # 16-bit number
def vi(r, k, v0, op0, v1, op1=AND, v2=0, n=(0, 0, 0), mode=MOMENTARY):
    for sub, val in [(1, n[0]), (2, v0), (3, op0), (4, n[1]), (5, v1), (6, op1), (7, n[2]), (8, v2), (9, mode), (0, 1)]: r.W(0x1400 + k, sub, val)
def cond(r, k, var, op, arg):
    for sub, val in [(1, var), (2, op), (3, float(arg)), (0, 1)]: r.W(0x1500 + k, sub, val)
def timer(r, k, var, mode, ms, reset=0):
    for sub, val in [(1, var), (2, reset), (3, mode), (4, ms), (0, 1)]: r.W(0x1A00 + k, sub, val)
def flasher(r, k, var, on_ms, off_ms, single=0):
    for sub, val in [(1, var), (2, on_ms), (3, off_ms), (4, single), (0, 1)]: r.W(0x1700 + k, sub, val)
def math(r, k, op, a, b=0, const=0.0, factor=1.0, offset=0.0):
    for sub, val in [(1, op), (2, a), (3, b), (4, float(const)), (5, float(factor)), (6, float(offset)), (0, 1)]: r.W(0x1C00 + k, sub, val)
def output(r, o, var, limit=7.5, inrush=15.0, inrush_ms=None, reset_mode=None, reset_ms=None, reset_limit=None, primary=None):
    subs = [(1, var), (2, float(limit)), (3, float(inrush))]
    if inrush_ms is not None: subs.append((4, inrush_ms))
    if reset_mode is not None: subs.append((5, reset_mode))
    if reset_ms is not None: subs.append((6, reset_ms))
    if reset_limit is not None: subs.append((7, reset_limit))
    if primary is not None: subs.append((17, primary & 0xFFFFFFFF))
    for sub, val in subs + [(0, 1)]: r.W(0x1000 + o, sub, val)
def pwm(r, o, duty=None, freq=100, soft_ms=None, var=None, denom=1, min_dc=0):
    subs = [(13, freq), (16, min_dc)]
    if duty is not None: subs += [(12, duty), (10, 0)]
    if var is not None: subs += [(11, var), (15, denom), (10, 1)]
    if soft_ms is not None: subs += [(14, soft_ms), (9, 1)]
    for sub, val in subs + [(8, 1)]: r.W(0x1000 + o, sub, val)

def edges(samples, i=0):
    """(t_ms, new level) for every change of channel i."""
    out = []; last = samples[0][1][i]
    for t, lv in samples:
        if lv[i] != last: out.append((t, lv[i])); last = lv[i]
    return out
def duty_freq(samples, i=0):
    e = edges(samples, i); rises = [t for t, l in e if l == 1]
    if len(rises) < 3: return None, None
    per = (rises[-1] - rises[0]) / (len(rises) - 1)
    span = [lv[i] for t, lv in samples if rises[0] <= t < rises[-1]]
    return round(100.0 * sum(span) / len(span), 1), round(1000.0 / per, 1)

# ====================================================================== F1 logic: AND / OR / NOR / NOT / NAND / XOR
print('--- F1 logic (virtual inputs)')
r = Rig(); v = r.v
check('var-map layout used by this file matches the firmware (VAR_MAP_SIZE)', r.b.counters()['var_map'] == v.size, (r.b.counters()['var_map'], v.size))
switch(r, 0); switch(r, 1); switch(r, 2)                   # A, B, C = CAN switches
A, B, C = v.can(0), v.can(1), v.can(2)
vi(r, 0, A, AND, B)                                        # AND
vi(r, 1, A, OR, B)                                         # OR
vi(r, 2, A, NOR, B)                                        # NOR
vi(r, 3, A, OR, B, n=(1, 1, 0))                            # NAND = !A OR !B
vi(r, 4, A, OR, B, AND, v.vi(0), n=(0, 0, 1))              # XOR = (A OR B) AND NOT (A AND B): one more virtual input
vi(r, 5, A, AND, B, OR, C)                                 # three terms: (A AND B) OR C
vi(r, 6, A, AND, v.TRUE, n=(1, 0, 0))                      # NOT A
for o in range(7): output(r, o, v.vi(o))
want = {0: lambda a, b, c: a and b, 1: lambda a, b, c: a or b, 2: lambda a, b, c: not (a or b), 3: lambda a, b, c: not (a and b),
        4: lambda a, b, c: a != b, 5: lambda a, b, c: (a and b) or c, 6: lambda a, b, c: not a}
bad = []
for a in (0, 1):
    for b_ in (0, 1):
        for c in (0, 1):
            r.sw(0, a); r.sw(1, b_); r.sw(2, c); r.run(40)
            got = [r.pin(o) for o in range(7)]; exp = [int(bool(want[o](a, b_, c))) for o in range(7)]
            if got != exp: bad.append(((a, b_, c), got, exp))
check('logic on output pins, all 8 input combinations: AND, OR, NOR, NAND (NOT inputs), XOR (2 virtual inputs), (A AND B) OR C, NOT', not bad, bad)

# isTrue / compare operators on a CAN value (conditions; vendor: =, !=, <, <=, >, >=, bit test)
value(r, 8, 0)
ops = [EQ, NE, GT, LT, GE, LE, BAND, BNAND]; args = [50, 50, 50, 50, 50, 50, 4, 4]
for k, (op, arg) in enumerate(zip(ops, args)): cond(r, k, v.canval(8), op, arg)
table = {}
for x in (49, 50, 51, 4, 3):
    r.val16(0, x); r.run(40); table[x] = [int(bool(r.var(v.cond(k)))) for k in range(8)]
    if x == 4: info['cond_bitand_raw_at_4'] = r.var(v.cond(6))   # firmware quirk: the masked value (4), not 1; true either way
exp = {49: [0, 1, 0, 1, 0, 1, 0, 1], 50: [1, 0, 0, 0, 1, 1, 0, 1], 51: [0, 1, 1, 0, 1, 0, 0, 1], 4: [0, 1, 0, 1, 0, 1, 1, 0], 3: [0, 1, 0, 1, 0, 1, 0, 1]}
check('conditions on a CAN number: =, !=, >, <, >=, <= at 49 / 50 / 51, bit test (AND / NAND 0x04) at 4 / 3 (true = non-zero)', table == exp, table)
check('F1: no CAN overruns / time-outs, no fatal error', r.ok_bus())

# ====================================================================== F2 toggle, set / reset latch, hysteresis, edges
print('--- F2 toggle, latch, hysteresis, edges')
r = Rig(); v = r.v
switch(r, 0, mode=LATCHING)                                # CAN switch in latching mode: each press toggles
output(r, 0, v.can(0))
seq = []
for _ in range(2):
    r.sw(0, 1); r.run(60); seq.append(r.pin(0)); r.sw(0, 0); r.run(60); seq.append(r.pin(0))
check('toggle (CAN input latching mode): press on, release stays on, press off, release stays off', seq == [1, 1, 0, 0], seq)
# physical input in latching mode (push button on IN_1, 20 ms debounce)
for sub, val in [(1, LATCHING), (4, 0), (0, 1)]: r.W(0x1200 + 0, sub, val)
r.b.set_input(0, 'gnd'); r.run(100); output(r, 1, v.di(0)); seq = []
for _ in range(2):
    r.b.set_input(0, '12v'); r.run(60); seq.append(r.pin(1)); r.b.set_input(0, 'gnd'); r.run(60); seq.append(r.pin(1))
r.b.set_input(0, '12v'); r.run(10); r.b.set_input(0, 'gnd'); r.run(60); seq.append(r.pin(1))   # 10 ms bounce: ignored
check('toggle (digital input latching mode, 20 ms debounce): two presses = on then off; a 10 ms blip is ignored', seq == [1, 1, 0, 0, 0], seq)
# set / reset latch: VI = (SET OR itself) AND NOT RESET (reset wins)
switch(r, 1); switch(r, 2)
vi(r, 0, v.can(1), OR, v.vi(0), AND, v.can(2), n=(0, 0, 1)); output(r, 2, v.vi(0)); seq = []
for s_, rs in [(1, 0), (0, 0), (0, 1), (0, 0), (1, 1), (0, 1), (0, 0)]:
    r.sw(1, s_); r.sw(2, rs); r.run(40); seq.append(r.pin(2))
check('set / reset latch (one virtual input reading itself): set on, holds, reset off, stays off, set + reset = off (reset wins)', seq == [1, 1, 0, 0, 0, 0, 0], seq)
# hysteresis: on at >= 95, off at <= 90 (two conditions + one latch virtual input), like a fan on coolant temperature
value(r, 8, 0); cond(r, 0, v.canval(8), GE, 95); cond(r, 1, v.canval(8), LE, 90)
vi(r, 1, v.cond(0), OR, v.vi(1), AND, v.cond(1), n=(0, 0, 1)); output(r, 3, v.vi(1)); seq = []
for x in (85, 94, 95, 93, 91, 90, 92, 96, 89):
    r.val16(0, x); r.run(40); seq.append((x, r.pin(3)))
check('hysteresis on a CAN value (on >= 95, off <= 90): off to 94, on at 95, stays on 93 / 91, off at 90, stays off at 92, on at 96, off at 89',
      [p for _, p in seq] == [0, 0, 1, 1, 1, 0, 0, 1, 0], seq)
# edges: rising-edge pulse and falling-edge pulse (timer one-shot, 100 ms), counter on both edges
switch(r, 3); timer(r, 0, v.can(3), PULSE_ONESHOT, 100)
vi(r, 2, v.can(3), AND, v.TRUE, n=(1, 0, 0)); timer(r, 1, v.vi(2), PULSE_ONESHOT, 100)
output(r, 4, v.tm(0)); output(r, 5, v.tm(1))
for sub, val in [(1, v.can(3)), (2, 0), (3, 0), (4, 0), (5, 255), (6, BOTH), (0, 1)]: r.W(0x1600, sub, val)
r.run(300); c0 = r.var(v.cnt(0))
r.sw(3, 1); s_on = r.sample([4, 5], 400); r.sw(3, 0); s_off = r.sample([4, 5], 400)
e_r = edges(s_on, 0); e_f = edges(s_off, 1)
pr = e_r[1][0] - e_r[0][0] if len(e_r) == 2 else None; pf = e_f[1][0] - e_f[0][0] if len(e_f) == 2 else None
check('edge pulses: rising edge -> one 100 ms pulse on OUT5, falling edge -> one 100 ms pulse on OUT6 (2 ms cycle tolerance)',
      pr is not None and pf is not None and abs(pr - 100) <= 4 and abs(pf - 100) <= 4 and not any(l[1] for _, l in s_on) and not any(l[0] for _, l in s_off), (e_r, e_f))
check('edge counter (both edges): +2 for one press and release', r.var(v.cnt(0)) - c0 == 2, (c0, r.var(v.cnt(0))))
check('F2: no CAN overruns / time-outs, no fatal error', r.ok_bus())

# ====================================================================== F3 timers
print('--- F3 timers')
r = Rig(); v = r.v
for k in range(5): switch(r, k)
timer(r, 0, v.can(0), ON_DELAY, 500)                       # e.g. fuel pump prime / delayed fan
timer(r, 1, v.can(1), OFF_DELAY, 1000)                     # courtesy light stays on after the door closes
timer(r, 2, v.can(2), PULSE_RETRIG, 300)
timer(r, 3, v.can(3), PULSE_ONESHOT, 300, reset=v.can(4))
for o in range(4): output(r, o, v.tm(o))
r.run(100)
def lag(smp, out_i, var_i):
    """ms from the first edge of the CAN switch (as the firmware saw it) to each edge of the output."""
    ev = edges(smp, var_i); eo = edges(smp, out_i)
    return [(round(t - ev[0][0]), l) for t, l in eo] if ev else None
r.sw(0, 1); s1_ = r.sample([0], 300, vars=[v.can(0)]); r.sw(0, 0); r.run(50)                  # 300 ms press: no output
r.sw(0, 1); s2_ = r.sample([0], 800, vars=[v.can(0)]); r.sw(0, 0); r.run(50); off_ = r.pin(0)
e = lag(s2_, 0, 1)
check('on delay 500 ms: a 300 ms input gives nothing; a held input switches on 500 ms (+0..4 ms) after the switch, off with it',
      not edges(s1_, 0) and len(e) == 1 and 500 <= e[0][0] <= 504 and off_ == 0, (edges(s1_, 0), e))
r.sw(1, 1); r.run(50); on_ = r.pin(1); r.sw(1, 0); s_ = r.sample([1], 1300, vars=[v.can(1)]); e = lag(s_, 0, 1)
check('off delay 1000 ms: on with the input, stays on 1000 ms (+0..4 ms) after it goes off', on_ == 1 and len(e) == 1 and 1000 <= e[0][0] <= 1004, (on_, e))
r.sw(2, 1); r.run(25); r.sw(2, 0); r.run(175); r.sw(2, 1); s_ = r.sample([2], 400, vars=[v.can(2)]); r.sw(2, 0); e = lag(s_, 0, 1)
check('pulse, retriggerable 300 ms: a second edge 200 ms in restarts it (off 300 ms after the second edge, +0..4 ms)', len(e) == 1 and 300 <= e[0][0] <= 304, e)
r.sw(3, 0); r.run(400)
r.sw(3, 1); s_ = r.sample([3], 25, vars=[v.can(3)]); r.sw(3, 0); s_ += [(t + 25, l) for t, l in r.sample([3], 175, vars=[v.can(3)])]
r.sw(3, 1); s_ += [(t + 200, l) for t, l in r.sample([3], 300, vars=[v.can(3)])]; r.sw(3, 0); e = lag(s_, 0, 1)
r.run(300); r.sw(3, 1); r.run(25); r.sw(3, 0); r.run(50); r.sw(4, 1); r.run(25); cut = r.pin(3); r.sw(4, 0); r.run(300)
check('pulse, one-shot 300 ms: a second edge 200 ms in is ignored (off 300 ms after the first edge, +0..4 ms); the reset input cuts a running pulse',
      e is not None and [l for _, l in e] == [1, 0] and e[0][0] <= 4 and 300 <= e[1][0] <= 304 and cut == 0, (e, cut))
check('F3: no CAN overruns / time-outs, no fatal error', r.ok_bus())

# ====================================================================== F4 turn signals and hazards
print('--- F4 turn signals, hazards, lane-change flash')
r = Rig(); v = r.v
L, R_, HAZ, LANE = 0, 1, 2, 3
for k in (L, R_, HAZ): switch(r, k)
switch(r, LANE)
# one shared flasher, so left, right and hazard always flash in step (ECUMaster blinker module: left / right / hazard)
timer(r, 0, v.can(LANE), PULSE_ONESHOT, 1800)              # lane-change tap: 3 flashes (3 periods of 2 x 352 ms - 1 off)
vi(r, 0, v.can(L), OR, v.can(R_), OR, v.can(HAZ))          # any request
vi(r, 1, v.vi(0), OR, v.tm(0))
flasher(r, 0, v.vi(1), 350, 350)
vi(r, 2, v.can(L), OR, v.can(HAZ), AND, v.fl(0))           # left lamps
vi(r, 3, v.can(R_), OR, v.can(HAZ), AND, v.fl(0))          # right lamps
vi(r, 4, v.tm(0), AND, v.fl(0))                            # lane-change flashes go to the left side here
vi(r, 5, v.vi(2), OR, v.vi(4))
output(r, 0, v.vi(5)); output(r, 1, v.vi(3))
r.run(1000)
r.sw(L, 1); s_ = r.sample([0, 1], 3000, vars=[v.can(L)]); r.sw(L, 0); r.run(30); off_now = r.pin(0)
d, f = duty_freq(s_, 0); e = lag(s_, 0, 2)
check('left signal: left lamps flash at about 1.4 Hz, 50 % (350 / 350 ms), first flash within 6 ms of the switch (3 logic cycles); right lamps stay off; off at once with the switch',
      d is not None and 47 <= d <= 53 and 1.35 <= f <= 1.45 and e[0][0] <= 6 and not any(l[1] for _, l in s_) and off_now == 0, (d, f, e[:2]))
info['turn_signal_duty_freq'] = (d, f)
r.run(1000); r.sw(HAZ, 1); s_ = r.sample([0, 1], 3000); r.sw(HAZ, 0); r.run(30)
e0, e1 = edges(s_, 0), edges(s_, 1)
check('hazard: both sides flash, edges on the same 1 ms sample (in step)', len(e0) >= 6 and e0 == e1, (e0[:4], e1[:4]))
r.run(1000); r.sw(HAZ, 1); r.sw(L, 1); s_ = r.sample([0, 1], 2000); r.sw(HAZ, 0); r.sw(L, 0)
check('hazard with the left signal also on: both sides still flash in step', edges(s_, 0) == edges(s_, 1) and len(edges(s_, 0)) >= 4)
r.run(1500); r.sw(LANE, 1); s_ = r.sample([0, 1], 100); r.sw(LANE, 0); s_ += [(t + 100, l) for t, l in r.sample([0, 1], 2900)]
n = len([1 for t, l in edges(s_, 0) if l == 1]) + s_[0][1][0]
check('lane-change tap (100 ms): exactly 3 flashes on the left (vendor "comfort blink"), from a one-shot timer + the flasher; right side dark',
      n == 3 and r.pin(0) == 0 and not any(l[1] for _, l in s_), edges(s_, 0))
check('F4: no CAN overruns / time-outs, no fatal error', r.ok_bus())

# ====================================================================== F5 counters: a multi-position mode button
print('--- F5 counters')
r = Rig(); v = r.v
switch(r, 0); switch(r, 1)
# counter 0: inc on rising edge of switch 0, 0..3 wrap, hold switch 0 for 2 s -> back to 0; switch 1 resets
for sub, val in [(1, v.can(0)), (2, 0), (3, v.can(1)), (4, 0), (5, 3), (6, RISING), (7, RISING), (8, RISING), (9, 1), (10, 1), (11, 2000), (0, 1)]: r.W(0x1600, sub, val)
for k in range(4): cond(r, k, v.cnt(0), EQ, k); output(r, k, v.cond(k))
r.run(100); seq = []
for _ in range(5):
    r.sw(0, 1); r.run(50); r.sw(0, 0); r.run(50); seq.append((int(r.var(v.cnt(0))), [r.pin(o) for o in range(4)]))
check('counter as a 4-position mode button: 1, 2, 3, wrap to 0, 1; exactly one mode output on each time',
      [c for c, _ in seq] == [1, 2, 3, 0, 1] and all(p == [int(o == c) for o in range(4)] for c, p in seq), seq)
r.sw(1, 1); r.run(50); r.sw(1, 0); r.run(50); a = int(r.var(v.cnt(0)))
r.sw(0, 1); r.run(50); r.sw(0, 0); r.run(50); r.sw(0, 1); r.run(2300); b = int(r.var(v.cnt(0))); r.sw(0, 0); r.run(50)
check('counter reset input -> 0; holding the button 2 s (hold-to-reset) -> 0', a == 0 and b == 0, (a, b))
check('F5: no CAN overruns / time-outs, no fatal error', r.ok_bus())

# ====================================================================== F6 math, linear fan PWM from coolant temperature, lookup table (gap)
print('--- F6 math, fan PWM from coolant temperature, lookup table')
r = Rig(); v = r.v
value(r, 8, 0); value(r, 9, 2)                             # A = bytes 0-1, B = bytes 2-3 of 0x4F1
A_, B_ = v.canval(8), v.canval(9)
math(r, 0, M_ADD, A_, B_); math(r, 1, M_SUB, A_, B_); math(r, 2, M_MUL, A_, B_); math(r, 3, M_DIV, A_, B_)
math(r, 4, M_MIN, A_, B_); math(r, 5, M_MAX, A_, B_); math(r, 6, M_AVG, A_, B_); math(r, 7, M_ADD, A_, 0, const=10, factor=0.5, offset=-3)
got = {}
for a, b_ in [(30, 6), (7, 0)]:
    r.val16(0, a); r.val16(2, b_); r.run(40); got[(a, b_)] = [round(r.var(v.math(k)), 3) for k in range(8)]
exp = {(30, 6): [36, 24, 180, 5, 6, 30, 18, 17], (7, 0): [7, 7, 0, 0, 0, 7, 3.5, 5.5]}
check('math blocks on two CAN numbers: + - x / min max average, constant B with factor / offset ((A + 10) x 0.5 - 3); divide by 0 = 0', got == exp, got)
# fan PWM duty from coolant temperature, 2-point linear map: duty = clamp((T - 80) x 5, 20, 100) % at 200 Hz
math(r, 0, M_SUB, A_, 0, const=80, factor=5); math(r, 1, M_MIN, v.math(0), 0, const=100); math(r, 2, M_MAX, v.math(1), 0, const=20)
for k in range(3, 8): r.W(0x1C00 + k, 0, 0)
output(r, 0, v.TRUE); pwm(r, 0, var=v.math(2), denom=1, freq=200)
fan = {}
for t in (70, 85, 90, 96, 110):
    r.val16(0, t); r.run(60); fan[t] = duty_freq(r.sample([0], 30, step=0.05))
check('fan PWM from coolant temperature (linear, math blocks): 70 C -> 20 % (floor), 85 -> 25 %, 90 -> 50 %, 96 -> 80 %, 110 -> 100 % (always on); 200 Hz',
      all(abs(fan[t][0] - d) <= 1.5 and abs(fan[t][1] - 200) <= 2 for t, d in [(70, 20), (85, 25), (90, 50), (96, 80)]) and fan[110] == (None, None) and r.pin(0) == 1, fan)
info['fan_linear_duty'] = fan
# vendor 1D table (ECUMaster 2D table p. 111, a 5-point curve): 80 C 0 %, 85 C 30 %, 90 C 40 %, 95 C 70 %, 100 C 100 %, linear between
# proposal T1 (docs/feature-parity.md): custom table block 0x7E00 + n: sub 0 enable, 1 input var, 2 points, 3..10 x[0..7], 11..18 y[0..7]
tab_ok = r.tool.read(r.base, 0x7E00, 0) is not None
if tab_ok:
    xs, ys = [80, 85, 90, 95, 100], [0, 30, 40, 70, 100]
    for sub, val in [(1, A_), (2, 5)] + [(3 + i, float(x)) for i, x in enumerate(xs)] + [(11 + i, float(y)) for i, y in enumerate(ys)] + [(0, 1)]: r.W(0x7E00, sub, val)
    var_tab = v.size                                       # proposal: the 4 table outputs appended at the end of the var map
    pwm(r, 0, var=var_tab, denom=1, freq=200)
    tab = {}
    for t in (82.5, 92.5, 97):
        r.val16(0, t); r.run(60); tab[t] = duty_freq(r.sample([0], 30, step=0.05))[0]
    tab_ok = all(abs((tab[t] or 0) - d) <= 1.5 for t, d in [(82.5, 15), (92.5, 55), (97, 82)])
check('gap T1: 1D lookup table (5 points, interpolated) drives the fan duty: 82.5 C -> 15 %, 92.5 C -> 55 %, 97 C -> 82 %', tab_ok,
      'no table block 0x7E00 in this firmware', xfail=True)
check('F6: no CAN overruns / time-outs, no fatal error', r.ok_bus())

# ====================================================================== F7 PWM outputs: duty, frequency, soft start, variable duty
print('--- F7 PWM outputs')
r = Rig(); v = r.v
switch(r, 0); value(r, 8, 0)
output(r, 0, v.can(0)); pwm(r, 0, duty=30, freq=100)
output(r, 1, v.can(0)); pwm(r, 1, duty=75, freq=400)
output(r, 2, v.can(0)); pwm(r, 2, var=v.canval(8), denom=1, freq=150, min_dc=10)
r.val16(0, 40); r.sw(0, 1); r.run(100); smp = r.sample([0, 1, 2], 60, step=0.05)
pf = [duty_freq(smp, i) for i in range(3)]
check('fixed duty: OUT1 30 % at 100 Hz, OUT2 75 % at 400 Hz (vendor range 4-400 Hz); OUT3 duty from a CAN value (40 %) at 150 Hz',
      abs(pf[0][0] - 30) <= 1 and abs(pf[0][1] - 100) <= 1 and abs(pf[1][0] - 75) <= 2 and abs(pf[1][1] - 400) <= 4 and abs(pf[2][0] - 40) <= 1 and abs(pf[2][1] - 150) <= 2, pf)
r.val16(0, 65); r.run(50); d65 = duty_freq(r.sample([2], 40, step=0.05))[0]; r.val16(0, 3); r.run(50); d3 = duty_freq(r.sample([2], 40, step=0.05))[0]
check('variable duty follows the CAN value (65 %) and is floored at the minimum duty (3 % asked -> 10 %)', abs(d65 - 65) <= 1 and abs(d3 - 10) <= 1, (d65, d3))
r.sw(0, 0); r.run(100); pwm(r, 0, duty=100, freq=100, soft_ms=1000)
r.sw(0, 1); s_ = r.sample([0], 1300, step=0.05, vars=[v.can(0)])
t_on = edges(s_, 1)[0][0]
win = lambda a, b: [lv[0] for t, lv in s_ if t_on + a <= t < t_on + b]
ramp = [round(100 * sum(win(a, a + 50)) / len(win(a, a + 50))) for a in (200, 450, 700, 1100)]
check('soft start 1000 ms to 100 %: duty about 22 / 47 / 72 % in the windows at 200 / 450 / 700 ms, then fully on after 1000 ms',
      abs(ramp[0] - 22) <= 6 and abs(ramp[1] - 47) <= 6 and abs(ramp[2] - 72) <= 6 and ramp[3] == 100, ramp)
info['soft_start_ramp'] = ramp
check('F7: no CAN overruns / time-outs, no fatal error', r.ok_bus())

# ====================================================================== F8 wiper: slow / fast / park / intermittent / wash
print('--- F8 wiper')
r = Rig(); v = r.v
SLOW, FAST, INT, WASH = 0, 1, 2, 3
for k in (SLOW, FAST, INT, WASH): switch(r, k)
for sub, val in [(1, MOMENTARY), (2, 0), (3, 0), (4, 0), (0, 1)]: r.W(0x1200 + 1, sub, val)    # IN_2 = park switch: no invert, no debounce, no pull (driven both ways)
for sub, val in [(1, 0), (2, v.can(SLOW)), (3, v.can(FAST)), (4, v.can(INT)), (7, v.di(1)), (8, 1), (10, v.can(WASH)), (11, 3), (20, 1500), (0, 1)]:
    r.W(0x1900, sub, val)                                  # DigIn mode; park switch closed (high) in the park zone; 3 wipes after wash; delay 1.5 s
output(r, 0, v.wiper('slow')); output(r, 1, v.wiper('fast')); output(r, 2, v.can(WASH))   # OUT1 motor run, OUT2 high speed, OUT3 washer pump
class Motor:
    """Wiper motor + park cam: one turn = 1.0 s slow / 0.6 s fast; park contact closed for the first 10 % of a turn."""
    def __init__(s, r): s.r = r; s.pos = 0.02; s.turns = 0; s.r.b.set_input(1, '12v')
    def step(s, ms):
        on, fast = s.r.pin(0), s.r.pin(1)
        if on:
            p = s.pos + ms / (600.0 if fast else 1000.0)
            if int(p) > int(s.pos): s.turns += 1
            s.pos = p
        s.r.b.set_input(1, '12v' if (s.pos % 1.0) < 0.10 else 'gnd')
    def run(s, ms, rec=None):
        for _ in range(int(ms)):
            s.r.run(1); s.step(1)
            if rec is not None: rec.append((s.r.pin(0), s.r.pin(1), round(s.pos % 1.0, 3)))
m = Motor(r); m.run(300)
r.sw(SLOW, 1); m.run(2500); t_slow = m.turns; r.sw(SLOW, 0); rec = []; m.run(1500, rec)
check('slow: motor runs (OUT1 on, OUT2 off) about 2.5 turns in 2.5 s; switched off mid-wipe it carries on to park and stops inside the park zone',
      t_slow in (2, 3) and rec[0][0] == 1 and rec[-1][0] == 0 and rec[-1][2] < 0.10 and not any(x[1] for x in rec), (t_slow, rec[0], rec[-1]))
r.sw(FAST, 1); m.turns = 0; rec = []; m.run(1800, rec); r.sw(FAST, 0); m.run(1500)
check('fast: OUT1 + OUT2 on (relay-style speed select), about 3 turns in 1.8 s, parks after the switch is off',
      all(x[0] and x[1] for x in rec[100:]) and m.turns in (2, 3) and r.pin(0) == 0 and (m.pos % 1) < 0.10, (m.turns, round(m.pos % 1, 3)))
r.sw(INT, 1); rec = []; m.run(6000, rec); r.sw(INT, 0); m.run(1500)
starts = [i for i in range(1, len(rec)) if rec[i][0] and not rec[i - 1][0]]
gaps = [starts[i + 1] - starts[i] for i in range(len(starts) - 1)]
check('intermittent (delay 1.5 s): one wipe, park, pause, wipe again: wipe starts about 2.5 s apart (1 s turn + 1.5 s pause), parked at the end',
      len(starts) >= 2 and all(2400 <= g <= 2700 for g in gaps) and r.pin(0) == 0, (starts, gaps))
r.sw(WASH, 1); m.turns = 0; m.run(800); pump = r.pin(2); r.sw(WASH, 0); m.run(5000)
check('wash: washer pump on with the switch, wiper runs and gives 3 more wipes after release, then parks (vendor "wash wipe cycles")',
      pump == 1 and m.turns in (3, 4) and r.pin(0) == 0 and (m.pos % 1) < 0.10, (pump, m.turns, round(m.pos % 1, 3)))
info['wash_turns'] = m.turns
check('F8: no CAN overruns / time-outs, no fatal error', r.ok_bus())

# ====================================================================== F9 starter interlock / master shutdown, load shedding on battery voltage
print('--- F9 starter interlock, battery load shedding')
r = Rig(); v = r.v
switch(r, 0); switch(r, 1)                                 # 0 = crank request (ECU / start switch), 1 = accessories wanted
for o in range(3): output(r, o, v.can(1))
for sub, val in [(1, v.can(0)), (2 + 1, 1), (2 + 2, 1), (0, 1)]: r.W(0x1800, sub, val)   # starter block: OUT2 / OUT3 shed while cranking
r.sw(1, 1); r.run(50); before = [r.pin(o) for o in range(3)]; r.sw(0, 1); r.run(50); crank = [r.pin(o) for o in range(3)]; r.sw(0, 0); r.run(50); after = [r.pin(o) for o in range(3)]
check('starter interlock: while cranking OUT2 / OUT3 are held off (OUT1 stays on), all back after (vendor: shed loads while cranking / master shutdown)',
      before == [1, 1, 1] and crank == [1, 0, 0] and after == [1, 1, 1], (before, crank, after))
for sub in (3, 4): r.W(0x1800, sub, 0)
# battery load shedding: off after 2 s at <= 11.5 V (ignores a crank dip), back at >= 12.5 V
cond(r, 0, v.BATT, LE, 11.5); cond(r, 1, v.BATT, GE, 12.5); timer(r, 0, v.cond(0), ON_DELAY, 2000)
vi(r, 0, v.tm(0), OR, v.vi(0), AND, v.cond(1), n=(0, 0, 1))  # shed latch
vi(r, 1, v.can(1), AND, v.vi(0), n=(0, 1, 0))                # accessory = wanted AND NOT shed
output(r, 2, v.vi(1)); seq = []
for vb, ms in [(13.8, 300), (10.5, 1000), (13.8, 300), (11.2, 1500), (11.2, 800), (12.0, 500), (12.6, 300)]:
    r.b.set_vbat(vb); r.run(ms); seq.append((vb, r.pin(2)))
check('battery load shed: a 1 s dip to 10.5 V does not shed; 11.2 V sheds after 2 s (not at 1.5 s); stays off at 12.0 V; back on at 12.6 V',
      [p for _, p in seq] == [1, 1, 1, 1, 0, 0, 1], seq)
check('F9: no CAN overruns / time-outs, no fatal error', r.ok_bus())

# ====================================================================== F10 CAN inputs (bit masks, signed / big-endian / scaled, extended IDs) and CAN output streams
print('--- F10 CAN in / out')
r = Rig(); v = r.v
canin(r, 0, VAL_ID, 32, length=8, op=BAND, operand=0x10)                                      # byte 4, bit mask 0x10
canin(r, 1, VAL_ID, 47, length=16, op=GT, operand=100.0, factor=0.1, offset=-40, signed=1, be=1)   # bytes 5-6 BE (DBC Motorola: start = MSB, byte 5 bit 7), signed x0.1 - 40, > 100
canin(r, 2, 0x18FF1234, 0, length=8, op=EQ, operand=7, ext=1)                                 # 29-bit ID
r.frames[0x18FF1234] = bytearray(8)
ecu_ext = r.ecu.timers[0]
r.ecu.timers[0][2] = lambda t: [r.ecu.q.append(ps.Frame(i, bytes(d), ide=1 if i > 0x7FF else 0, src='ecu')) for i, d in r.frames.items()]
for o in range(3): output(r, o, v.can(o))
got = []
for byte4, raw, ext in [(0x00, 1300, 0), (0x10, 1500, 7), (0xEF, -1000, 3), (0x3F, 1401, 7)]:
    r.frames[VAL_ID][4] = byte4; r.frames[VAL_ID][5:7] = struct.pack('>h', raw); r.frames[0x18FF1234][0] = ext; r.run(40)
    got.append((byte4, raw, ext, [r.pin(o) for o in range(3)], round(r.var(v.canval(1)), 2)))
check('CAN input decode: bit mask 0x10 on a byte; 16-bit signed big-endian x0.1 - 40 (1300 -> 90.0, 1500 -> 110.0, -1000 -> -140.0, 1401 -> 100.1 > 100); 29-bit ID equal 7',
      [g[3] for g in got] == [[0, 0, 0], [1, 1, 1], [0, 0, 0], [1, 1, 1]] and [g[4] for g in got] == [90.0, 110.0, -140.0, 100.1], got)
# one-byte command, big-endian (DBC Motorola): the start bit is the byte's MSB (byte x 8 + 7); byte x 8 reads across into the next byte
canin(r, 3, VAL_ID, 7 * 8 + 7, length=8, op=GT, operand=-1e9, be=1); canin(r, 4, VAL_ID, 7 * 8, length=8, op=GT, operand=-1e9, be=1)
r.frames[VAL_ID][7] = 0x01; r.run(40); be_ok, be_wrong = r.var(v.canval(3)), r.var(v.canval(4))
check('one-byte big-endian command (byte 7 = 1): start bit 63 (MSB, DBC Motorola) reads 1; start bit 56 (byte x 8, as the ECU control plan dummy says) does not',
      be_ok == 1 and be_wrong != 1, (be_ok, be_wrong))
# CAN output stream (DBC scaling: raw = (value - offset) / factor): OUT1 current at factor 0.1 (16 bit) + OUT1 state (8 bit) + analog input mV in one frame 0x6A0 every 50 ms
r.frames[VAL_ID][4] = 0x10; output(r, 0, v.TRUE); r.b.set_load(0, r.b.vbat / 4.0); r.b.set_analog(2.5)
for sub, val in [(0, 1)]: r.W(0x2200, sub, val)
for k, (var, start, length, factor) in enumerate([(v.cur(0), 0, 16, 0.1), (v.out(0), 16, 8, 1.0), (v.an_mv(), 24, 16, 1.0)]):
    for sub, val in [(1, var), (2, 0), (3, 0x6A0), (4, start), (5, length), (6, factor), (10, 50), (0, 1)]: r.W(0x2000 + k, sub, val)
r.run(200); fr = [f for f in r.rx if f.id == 0x6A0]; r.rx.clear(); r.run(1000); fr = [f for f in r.rx if f.id == 0x6A0]
per = [round((fr[i + 1].t - fr[i].t) / 1000) for i in range(len(fr) - 1)]
cur10, st, mv = struct.unpack('<H', fr[-1].data[0:2])[0], fr[-1].data[2], struct.unpack('<H', fr[-1].data[3:5])[0]
check('CAN output stream 0x6A0 every 50 ms: three channels packed in one frame (OUT1 current x10 ~ 40, OUT1 state 1, analog ~2500 mV)',
      19 <= len(fr) <= 21 and all(49 <= p <= 51 for p in per) and 38 <= cur10 <= 42 and st == 1 and abs(mv - 2500) <= 30 and fr[-1].dlc == 5, (len(fr), sorted(set(per)), cur10, st, mv, fr[-1].dlc))
check('F10: no CAN overruns / time-outs, no fatal error', r.ok_bus())

# ====================================================================== F11 CAN keypad (Blink Marine 12-key, CANopen)
print('--- F11 keypad')
r = Rig(); v = r.v; NODE = 0x20
kp = ps.PyNode('keypad'); r.bus.add(kp); kp_btn = [0]
kp.every(20000, lambda t: kp.send(0x180 + NODE, bytes([kp_btn[0] & 255, kp_btn[0] >> 8, 0, 0, 0, 0, 0, 0])), start=7000)
for sub, val in [(1, NODE), (4, 6), (0, 1)]: r.W(0x3000, sub, val)                       # keypad 1: Blink 12 key at node 0x20
for sub, val in [(1, LATCHING), (2, 2), (7, v.out(0)), (0, 1)]: r.W(0x3100 + 0, sub, val)   # button 1 toggles; LED green while OUT1 is on
output(r, 0, v.kp_btn(0, 0)); r.run(300)
def led_green_b1():
    f = [x for x in r.rx if x.id == 0x200 + NODE]; return ((f[-1].data[1] >> 4) & 1) if f else None   # 12-key: red bits 0-11, green 12-23 (blink_keypad.cpp)
seq = []
for _ in range(2):
    kp_btn[0] = 1; r.run(80); kp_btn[0] = 0; r.rx.clear(); r.run(300); seq.append((r.pin(0), led_green_b1()))
c_before = r.b.counters()['tx_timeouts']
check('keypad button 1 (latching): press toggles OUT1 on then off; the button LED (0x220, green bit 12) follows the output', seq == [(1, 1), (0, 0)], seq)
r.run(2000); c = r.b.counters(); info['keypad_tx_timeouts_at_enable'] = c['tx_timeouts']
check('F11: no CAN overruns, no fatal error; no transmit time-out after the keypad start-up burst (one is seen when the keypad is enabled)',
      c['rx_overruns'] == 0 and not r.b.flags()['fatal'] and c['tx_timeouts'] == c_before, c['tx_timeouts'])

# ====================================================================== F12 output protection
print('--- F12 output protection')
OFF_, ON_, OC_, FAULT_ = range(4)                           # ProfetState
def amps(r, o, a): r.b.set_load(o, r.b.vbat / a if a else 0)
def on_spans(smp, i=0):
    """[(start, end)] ms of each high span of channel i."""
    e = edges(smp, i); spans = []; st = 0 if smp[0][1][i] else None
    for t, l in e:
        if l: st = t
        elif st is not None: spans.append((st, t)); st = None
    if st is not None: spans.append((st, None))
    return spans
r = Rig(); v = r.v
switch(r, 0); switch(r, 1)
output(r, 0, v.can(0), limit=5.0, inrush=10.0, inrush_ms=300, reset_mode=1, reset_ms=1000, reset_limit=3)
# inrush: 8 A for the first 200 ms (above the 5 A limit, below the 10 A inrush limit), then 4 A: no trip
amps(r, 0, 8.0); r.sw(0, 1); r.run(200); amps(r, 0, 4.0); r.run(800)
check('inrush window: 8 A for 200 ms with limit 5 A / inrush 10 A for 300 ms does not trip; 4 A after it runs on', r.pin(0) == 1 and r.b.L.sim_out_state(0) == ON_, r.b.L.sim_out_state(0))
r.sw(0, 0); r.run(100)
# a load stuck at 8 A: trips when the inrush window ends, retries every 1000 ms, latches Fault after the 3rd trip (reset limit 3)
amps(r, 0, 8.0); r.sw(0, 1); s_ = r.sample([0], 5000, vars=[v.can(0)]); sp = on_spans(s_)
t0_ = edges(s_, 1)[0][0]; sp = [(round(a - t0_), round(b - t0_) if b else None) for a, b in sp]
check('stuck 8 A load (limit 5 A, inrush 10 A / 300 ms, retry 1000 ms after each trip, reset limit 3): 3 on spans of 300 ms (-4..+6), 1000 ms apart (+0..6), then Fault',
      len(sp) == 3 and sp[0][0] <= 4 and all(b is not None and 296 <= b - a <= 306 for a, b in sp)
      and all(1000 <= sp[i + 1][0] - sp[i][1] <= 1006 for i in range(2)) and r.b.L.sim_out_state(0) == FAULT_, sp)
info['retry_spans_ms'] = sp
info['note_reset_limit'] = 'reset limit 3 = 3 trips in all (first try + 2 retries); MoTeC "Number of Retries 3" = 3 retries after the first trip'
r.sw(0, 0); r.run(200); r.sw(0, 1); r.run(200); still = r.b.L.sim_out_state(0)
check('Fault stays latched when the input is cycled (stock: needs a power cycle; see gap P3 for a master retry)', still == FAULT_ and r.pin(0) == 0, still)
# gap P3: a master-retry input clears latched Faults without a power cycle (MoTeC Master Retry; Link: until a setting changes)
p3 = r.tool.read(r.base, 0x7F00, 6) is not None
if p3:
    switch(r, 1); r.W(0x7F00, 6, v.can(1)); amps(r, 0, 4.0); r.sw(1, 1); r.run(100); r.sw(1, 0); r.run(400); p3 = r.pin(0) == 1
check('gap P3: master retry input (0x7F00 sub 6 = CAN switch) clears the latched Fault; the output comes back with a good load', p3,
      'no param 0x7F00 sub 6 in this firmware', xfail=True)
# input cycled between trips resets the count (MoTeC: "count reset when the condition goes false then true")
r = Rig(); v = r.v; switch(r, 0)
output(r, 0, v.can(0), limit=5.0, inrush=10.0, inrush_ms=300, reset_mode=1, reset_ms=1000, reset_limit=3)
amps(r, 0, 8.0); r.sw(0, 1); r.run(1800); r.sw(0, 0); r.run(200)        # 2 trips, then the driver switches it off
r.sw(0, 1); s_ = r.sample([0], 4000, vars=[v.can(0)]); n = len(on_spans(s_))
check('switching the input off between trips resets the trip count: 3 more tries before Fault (not 1)', n == 3 and r.b.L.sim_out_state(0) == FAULT_, n)
# endless retry: keeps trying, comes back by itself when the fault goes
r.sw(0, 0); r = Rig(); v = r.v; switch(r, 0)
output(r, 0, v.can(0), limit=5.0, inrush=10.0, inrush_ms=100, reset_mode=2, reset_ms=500)
amps(r, 0, 8.0); r.sw(0, 1); s_ = r.sample([0], 3000); n = len(on_spans(s_)); amps(r, 0, 3.0); r.run(1500)
check('endless retry (reset time 500 ms): 5 or more tries in 3 s with an 8 A load, never Fault; on again by itself once the load is 3 A',
      n >= 5 and r.pin(0) == 1 and r.b.L.sim_out_state(0) == ON_, (n, r.b.L.sim_out_state(0)))
# shorted driver (IS pin at its clamp, PROFET fault signal): seen as a very high current -> overcurrent path (retries, then Fault)
r = Rig(); v = r.v; switch(r, 0)
output(r, 0, v.can(0), limit=5.0, inrush=10.0, inrush_ms=100, reset_mode=1, reset_ms=300, reset_limit=2)
r.b.set_load(0, r.b.vbat / 2.0, fault=1); r.sw(0, 1); s_ = r.sample([0], 1500); sp = on_spans(s_)
check('driver fault (IS at its clamp, about 16 A read): cut at once (no inrush allowance above 10 A), retried per the reset settings, then Fault',
      len(sp) == 2 and all(b is not None and b - a <= 4 for a, b in sp) and r.b.L.sim_out_state(0) == FAULT_, sp)
# gap P1: trip delay / I2t: a 20 ms spike to 8 A on a 5 A output after the inrush window is tolerated (Link: Trip Time; MoTeC: filtered load)
r = Rig(); v = r.v; switch(r, 0)
output(r, 0, v.can(0), limit=5.0, inrush=10.0, inrush_ms=100, reset_mode=0)
p1 = r.tool.read(r.base, 0x7D00, 0) is not None
if p1: r.W(0x7D00, 0, 50)                                  # proposal: custom output block 0x7D00 + o, sub 0 = trip time 50 ms
amps(r, 0, 3.0); r.sw(0, 1); r.run(500); amps(r, 0, 8.0); r.run(20); amps(r, 0, 3.0); r.run(200); spike_ok = r.pin(0) == 1
info['spike_20ms_trips_today'] = not spike_ok
amps(r, 0, 8.0); r.run(200); long_trip = r.pin(0) == 0
check('gap P1: overcurrent trip time 50 ms (0x7D00 sub 0): a 20 ms spike to 8 A on a 5 A output is ridden through, 8 A for 200 ms still trips',
      p1 and spike_ok and long_trip, f'spike tolerated: {spike_ok}', xfail=True)
# gap P2: open load / undercurrent (ECUMaster: Min current -> UNDERCURRENT status, output keeps running)
r = Rig(); v = r.v; output(r, 0, v.TRUE, limit=5.0)
p2 = r.tool.read(r.base, 0x7D00, 1) is not None
if p2:
    r.W(0x7D00, 1, 0.5); amps(r, 0, 0); r.run(500)       # proposal: min current 0.5 A; flag = var v.size + 4 + o (after the 4 table outputs)
    p2 = r.var(v.size + 4) == 1 and r.pin(0) == 1
check('gap P2: open-load / undercurrent flag (min current 0x7D00 sub 1): output on with no load sets the flag and keeps running', p2,
      'no param 0x7D00 sub 1 in this firmware', xfail=True)

# ====================================================================== F13 output pairing (two channels as one load)
print('--- F13 output pairing')
r = Rig(); v = r.v; switch(r, 0)
output(r, 0, v.can(0), limit=12.0, inrush=20.0); output(r, 1, v.FALSE, limit=12.0, inrush=20.0, primary=0)   # OUT2 follows OUT1
amps(r, 0, 4.0); amps(r, 1, 4.0); r.run(100); off_ = (r.pin(0), r.pin(1))
r.sw(0, 1); r.run(100); on_ = (r.pin(0), r.pin(1)); total = r.b.L.sim_out_current(0)
pwm(r, 0, duty=40, freq=100); r.run(100); smp = r.sample([0, 1], 50, step=0.05); pd = (duty_freq(smp, 0), duty_freq(smp, 1))
e0, e1 = edges(smp, 0), edges(smp, 1); in_step = len(e0) == len(e1) > 4 and all(l0 == l1 and abs(t0 - t1) <= 0.11 for (t0, l0), (t1, l1) in zip(e0, e1))
r.sw(0, 0); r.run(100); off2 = (r.pin(0), r.pin(1))
check('pairing: OUT2 (primary = OUT1) switches with OUT1, both pins together; OUT1 reports the sum of both currents (4 + 4 A); PWM 40 % on both, edges within 0.1 ms',
      off_ == (0, 0) and on_ == (1, 1) and 7.4 <= total <= 8.6 and pd[0] == pd[1] and abs(pd[0][0] - 40) <= 1.5 and in_step and off2 == (0, 0), (on_, total, pd, edges(smp, 0)[:3], edges(smp, 1)[:3]))
check('F13: no CAN overruns / time-outs, no fatal error', r.ok_bus())

# ====================================================================== F14 analog input as a switch / rotary, digital input frequency + duty
print('--- F14 analog switch, rotary switch, input PWM / frequency')
r = Rig(); v = r.v
for sub, val in [(1, 1), (4, 2000), (5, 1), (7, 250.0), (8, 1000.0), (9, 4.0), (0, 1)]: r.W(0x2200, sub, val)   # switch > 2000 mV; rotary 5 positions, 1 V steps from 0.25 V
output(r, 0, v.an_sw()); got = []
for volts in (0.1, 1.9, 2.1, 3.3, 4.6):
    r.b.set_analog(volts); r.run(40); got.append((volts, r.pin(0), int(r.var(v.an_rot()))))
check('analog input as a switch (on above 2000 mV) and as a 5-position rotary switch (positions 0-4 at 0.25 V + 1 V steps)',
      [g[1] for g in got] == [0, 0, 1, 1, 1] and [g[2] for g in got] == [0, 1, 1, 3, 4], got)
for sub, val in [(5, 1), (0, 1)]: r.W(0x1200 + 1, sub, val)    # IN_2 measures PWM (e.g. a 50 Hz 25 % signal from another module)
r.run(100)
for _ in range(25):
    r.b.set_input(1, '12v'); r.run(5); r.b.set_input(1, 'gnd'); r.run(15)
dd, ff = r.var(v.di_duty(1)), r.var(v.di_freq(1))
check('digital input PWM measurement: 50 Hz, 25 % signal on IN_2 reads about 50 Hz and 25 %', abs(ff - 50) <= 1 and abs(dd - 25) <= 1.5, (round(dd, 1), round(ff, 1)))
check('F14: no CAN overruns / time-outs, no fatal error', r.ok_bus())

# ====================================================================== F15 sleep on ignition off (force-sleep input)
print('--- F15 sleep on an input')
r = Rig(); v = r.v; switch(r, 0)
r.W(0x0000, 8, v.can(0)); r.run(200); awake = not r.b.flags()['asleep']
r.sw(0, 1); r.run(300)
check('force-sleep input (0x0000 sub 8 = a CAN bit, e.g. ignition off from the ECU): board stays awake while 0, sleeps once it is 1', awake and r.b.flags()['asleep'], r.b.flags())

# ====================================================================== F16 tach-style output: frequency follows a CAN value
print('--- F16 tach output (frequency from a CAN value)')
# Vendors: Link "Tacho" aux output (multiplier 1 = 1 pulse per ignition event, 50 % duty), Haltech tachometer output
# (pulses per engine cycle = cylinders), Adaptronic (4 cyl = 2 pulses / rev, 8 cyl = 4); sources in docs/feature-parity.md.
# Here the ECU sends RPM on CAN and the PDM makes a 50 % square wave of RPM x pulses per rev / 60 Hz on a PROFET output.
TACH = 0x7C00   # custom block 0x7C00 + output (core/param_defs.h OUTPUT_FREQ_PARAMS): sub 0 on, 1 input var, 2 factor
                # (Hz per input unit = pulses per rev / 60 for RPM), 3 minimum Hz (below: no pulses, output low), 4 maximum Hz
def tach(r, o, ppr, fmin=None, fmax=None, var=None):
    r.W(TACH + o, 1, r.v.canval(8) if var is None else var); r.W(TACH + o, 2, float(ppr / 60.0))
    if fmin is not None: r.W(TACH + o, 3, fmin)
    if fmax is not None: r.W(TACH + o, 4, fmax)
    r.W(TACH + o, 0, 1)
def wave(r, outs, ms):
    """Edges of the output pins over the next ms: one [(t_ms, level)] list per output (sim pin log, exact to 1 us)."""
    r.b.watch(*[r.b.model['outputs'][o][0] for o in outs]); r.run(ms); e = r.b.edges()
    return [[(t / 1000.0, l) for t, i, l in e if i == k] for k in range(len(outs))]
def periods(ed):
    """[(rise t_ms, period ms, high ms)] for each full period (rise to rise) in an edge list."""
    rises = [t for t, l in ed if l == 1]; out = []
    for a, b in zip(rises, rises[1:]):
        f = [t for t, l in ed if l == 0 and a < t < b]
        out.append((a, round(b - a, 4), round(f[0] - a, 4) if f else None))
    return out
def hz(ed):
    """(frequency Hz, duty %) over the full periods of an edge list, or (None, None) with under 2 periods."""
    p = periods(ed)
    if len(p) < 2 or any(x[2] is None for x in p): return None, None
    return round(1000.0 * len(p) / sum(x[1] for x in p), 2), round(100.0 * sum(x[2] for x in p) / sum(x[1] for x in p), 2)
def near(f, want, pct): return f is not None and abs(f - want) <= want * pct / 100.0
r = Rig(); v = r.v; value(r, 8, 0)                         # RPM: bytes 0-1 of 0x4F1, unsigned, x1 (ECU stand-in, every 10 ms)
for o in (0, 1): output(r, o, v.TRUE); pwm(r, o, duty=50, freq=100)
present = r.tool.read(r.base, TACH, 0) is not None
dflt = tuple(r.tool.read(r.base, TACH, s) for s in range(5)) if present else None
check('tach params 0x7C00 + output: defaults off, input 0, factor 1.0 Hz per unit, minimum 16 Hz, maximum 1000 Hz',
      dflt == (0, 0, ps.f32(1.0), 16, 1000), dflt if present else 'no param block 0x7C00 in this firmware')
refused = present and all(r.tool.write(r.base, TACH, s, val) is None for s, val in [(3, 15), (4, 1001), (2, ps.f32(-1.0))])
check('tach params refuse a minimum below 16 Hz (16-bit timer at 1 MHz: 65536 counts = 15.3 Hz), a maximum above 1000 Hz, a negative factor',
      refused)
got4 = {}; got8 = {}
if present:
    tach(r, 0, 2); tach(r, 1, 4)                           # OUT1: 4-cylinder tach (2 pulses / rev); OUT2: 8-cylinder (4 pulses / rev)
    for rpm in (600, 3000, 6000, 7500, 9000):
        r.val16(0, rpm); r.run(80); w = wave(r, [0, 1], 320)
        got4[rpm] = hz(w[0]); got8[rpm] = hz(w[1])
ok4 = present and all(near(got4[x][0], x * 2 / 60, 0.2) and abs(got4[x][1] - 50) <= 0.5 for x in got4)
ok8 = present and all(near(got8[x][0], min(x * 4 / 60, 1000), 0.2) and abs(got8[x][1] - 50) <= 0.5 for x in got8)
check('tach 4 cylinder (2 pulses / rev, 50 % duty) from CAN RPM: 600 -> 20 Hz, 3000 -> 100, 6000 -> 200, 7500 -> 250, 9000 -> 300 Hz (within 0.2 %, duty 50 +-0.5 %)',
      ok4, got4)
check('tach 8 cylinder (4 pulses / rev) on a second output at the same time, own timer: 600 -> 40 Hz ... 7500 -> 500, 9000 -> 600 Hz (above the 400 Hz fixed-frequency limit)',
      ok8, got8)
info['tach_4cyl_hz_duty'] = got4; info['tach_8cyl_hz_duty'] = got8
# engine stopped / below the minimum: no pulses, output low (a gauge reads 0); pulses come back with RPM
off = None
if present:
    seq = []
    for rpm in (0, 400, 600):                              # 0 Hz, 13.3 Hz (below 16), 20 Hz
        r.val16(0, rpm); r.run(80); w = wave(r, [0], 300)[0]; seq.append((rpm, len(w), r.pin(0), hz(w)[0]))
    off = seq
check('tach below its minimum (16 Hz): RPM 0 and 400 (13.3 Hz) give no pulses and a low output; 600 RPM gives 20 Hz again',
      off is not None and off[0][1:3] == (0, 0) and off[1][1:3] == (0, 0) and near(off[2][3], 20, 0.2), off)
# clamp at the maximum
clamp = None
if present:
    r.W(TACH, 4, 250); r.val16(0, 9000); r.run(80); clamp = hz(wave(r, [0], 100)[0]); r.W(TACH, 4, 1000)
check('tach maximum (sub 4 = 250 Hz): 9000 RPM (300 Hz) is held at 250 Hz', clamp is not None and near(clamp[0], 250, 0.2), clamp)
# step response: 3000 -> 6000 RPM (100 -> 200 Hz). Budget: ECU frame period 10 ms + one 2 ms logic cycle + the running
# 10 ms period (the timer takes a new period at its next update event) + 1 ms = 23 ms; no runt or missed pulse
step = None
if present:
    r.val16(0, 3000); r.run(100); t_set = r.bus.now / 1000.0; r.val16(0, 6000); w = wave(r, [0], 60)[0]
    p = periods(w); first = next((a for a, per, hi in p if abs(per - 5.0) <= 0.05), None)
    step = (round(first - t_set, 2) if first else None, sorted(set(round(per, 3) for a, per, hi in p)),
            all(hi is not None and abs(hi / per - 0.5) <= 0.01 for a, per, hi in p))
check('tach step 3000 -> 6000 RPM: first 200 Hz period starts within 23 ms of the new CAN value; every period is 10 or 5 ms, all 50 % (no runt, no missed pulse)',
      step is not None and step[0] is not None and step[0] <= 23 and set(step[1]) <= {10.0, 5.0} and step[2], step)
info['tach_step_latency_ms'] = step[0] if step else None
# ramp 1000 -> 7000 RPM in 600 ms (ECU value every 10 ms): frequency tracks, every period between the ramp's end
# periods and never longer than the one before (no missed pulse), each high time 50 % of its period
ramp = None
if present:
    r.val16(0, 1000); r.run(100); r.b.watch(r.b.model['outputs'][0][0]); r.b.edges()
    for k in range(61): r.val16(0, 1000 + 100 * k); r.run(10)
    w = [(t / 1000.0, l) for t, i, l in r.b.edges()]; p = periods(w)
    pers = [per for a, per, hi in p]
    ramp = dict(n=len(p), longest=max(pers), shortest=min(pers),
                grew=[(round(p[i][0]), pers[i], pers[i + 1]) for i in range(len(pers) - 1) if pers[i + 1] > pers[i] + 0.002],
                duty_bad=[(round(a), per, hi) for a, per, hi in p if hi is None or abs(hi / per - 0.5) > 0.01], steps=len(set(pers)))
check('tach ramp 1000 -> 7000 RPM in 600 ms (CAN value every 10 ms): periods stay within 30 .. 4.29 ms, never grow (no missed pulse), all 50 %, 30 or more frequency steps',
      ramp is not None and ramp['longest'] <= 30.0 * 1.001 and ramp['shortest'] >= 60000 / 7000 / 2 * 0.999 and not ramp['grew'] and not ramp['duty_bad'] and ramp['steps'] >= 30, ramp)
info['tach_ramp'] = ramp
# steady state: period spread at 6000 RPM over 1 s (timer-driven edges; jitter = spread of rise-to-rise times)
jit = None
if present:
    r.val16(0, 6000); r.run(100); p = periods(wave(r, [0], 1000)[0]); pers = [per for a, per, hi in p]
    jit = (len(p), round((max(pers) - min(pers)) * 1000, 1))
check('tach steady 6000 RPM (200 Hz) for 1 s: 199 or more periods, rise-to-rise spread under 2 us', jit is not None and jit[0] >= 199 and jit[1] < 2, jit)
info['tach_jitter_us'] = jit
# off again (sub 0 = 0): back to the fixed 100 Hz of the stock PWM settings
back = None
if present:
    r.W(TACH, 0, 0); r.run(100); back = hz(wave(r, [0], 100)[0])
check('tach off (sub 0 = 0): the output is back on its fixed PWM frequency (100 Hz, 50 %)', back is not None and near(back[0], 100, 0.2) and abs(back[1] - 50) <= 0.5, back)
check('F16: no CAN overruns / time-outs, no fatal error', r.ok_bus())
# paired output follows the tach frequency of its primary (custom: the follower copies the primary's timer period)
r = Rig(); v = r.v; value(r, 8, 0); pair = None
output(r, 0, v.TRUE); pwm(r, 0, duty=50, freq=100); output(r, 2, v.FALSE, primary=0)
if present:
    tach(r, 0, 2); r.val16(0, 4500); r.run(100); w = wave(r, [0, 2], 200); pair = (hz(w[0]), hz(w[1]))
check('tach on a paired output (OUT3 follows OUT1): both pins 150 Hz at 4500 RPM, 50 %', pair is not None and all(x[0] is not None and near(x[0], 150, 0.2) and abs(x[1] - 50) <= 0.5 for x in pair), pair)
# found while testing (stock dingoFW, not changed): a fixed PWM frequency below 16 Hz on a 16-bit timer is wrong.
# ARR keeps the low 16 bits of 1 MHz / f - 1 (RM0390 TIM3/4/9-14 are 16-bit); TIM5 (OUT3 on board A) is 32-bit.
# At 10 Hz: ARR = 99999 -> 34463 (29 Hz) and CCR 50000 is above it, so OUT2 (TIM4) stays on with no pulses.
r = Rig(); v = r.v
for o in (1, 2): output(r, o, v.TRUE); pwm(r, o, duty=50, freq=10)
r.run(300); w = wave(r, [1, 2], 600); info['stock_fixed_10hz_out2_tim4_16bit_vs_out3_tim5_32bit'] = (hz(w[0]), r.pin(1), hz(w[1]))

# ====================================================================== summary
cnt = {t: sum(1 for x in res if x[1] == t) for t in ('PASS', 'FAIL', 'XFAIL', 'XPASS')}
print(f"\nS3: {cnt['PASS']} of {cnt['PASS'] + cnt['FAIL']} checks passed, {cnt['XFAIL']} expected failures (gaps with a proposal), {cnt['XPASS']} unexpected passes")
print(json.dumps(info))
json.dump(dict(checks=res, info=info), open('/tmp/s3_results.json', 'w'), indent=1)
sys.exit(1 if cnt['FAIL'] or cnt['XPASS'] else 0)
