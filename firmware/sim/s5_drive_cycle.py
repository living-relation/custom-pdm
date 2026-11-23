"""S5: a day in the car on the whole PDM - boards A1, A2 and B (real firmware logic, host sim) on one 1 Mbit/s bus with a
dummy ECU (0x3F4 pump / condenser fan bytes, 0x3F5 coolant x 0.1), a dummy keypad (0x1A8), the dummy car traffic of
docs/car-can-dummy/bus-load.dummy.md and the PC tool, with the ST185 starter (ui/examples/st185-starter.json, a DUMMY
starter) written by Write All exactly as the app writes it (firmware/sim/data/st185-starter.params.dummy.tsv, made and
checked by ui/tests StarterParamsExportTests).

Script: park, key on, ECU prime, crank (6 V dip), idle, lights low / high, turn signals and hazard, horn, wipers slow /
fast / intermittent with the park cam, coolant 80 -> 105 -> 85 C (radiator fan from the CAN value, condenser fan from the
ECU byte), A/C clutch from the keypad, hot-day board temperatures (thermal model), ECU frames lost and back, board B
unplugged and back, an overcurrent fault + Reset faults (master retry, as the /pdm button), load shed at low battery,
key off, sleep, wake.

Ground truth: every PROFET IN pin of the 24 outputs, every 1 ms, against an independent logic model of the car written
from the starter's own words (ui/examples/README.md, the /pdm trigger texts in UiWalkTests) - not from the firmware.
A pin may differ from the model only inside the latency window of a change (debounce, CAN periods, time-outs); every
change is timed. Loads: steady current, inrush and kind from tools/presim_parts.py CAR_LOADS (the thermal / switching
jobs' table), the rest ASSUMED below. Per-board switch dissipation over the cycle -> CSV for the thermal job.

usage: python3 firmware/sim/s5_drive_cycle.py <sim out dir> [--out dir] [--json file] [--mutate N] [--mutants] [--hot-a C]
(exit 1 on any FAIL). --mutants runs every one-line config mutation in MUTATIONS (each must turn RED)."""
import json, math, os, random, re, struct, subprocess, sys, shutil, tempfile, zlib
import pdmsim as ps

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, 'tools'))
import presim_parts as PP                                  # CAR_LOADS, RDS(ON) per driver

def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default
SO = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith('--') else '/tmp/simout'
OUT_DIR = arg('--out', os.path.join(SO, 's5'))
MUTATE = int(arg('--mutate', '-1'))
# Hot day (docs/system-verification.md section 6, tools/verify_thermal_box.py, 60 C cabin, car loads, fans on):
# board B's own MCP9808 U6 93.4 C (FEA sensor map); board A has no map: sink 69.6 C + 15 K (DT_BOARD_A, ASSUMED) = 84.6 C
HOT_B = 93.4
HOT_A = float(arg('--hot-a', '84.6'))
res, info = [], {}
def check(name, ok, detail='', xfail=False):
    """xfail (as s3): a known gap with a proposal (docs/simulation-index.md); must fail until fixed - an XPASS is a failure."""
    ok = bool(ok); tag = ('XPASS' if ok else 'XFAIL') if xfail else ('PASS' if ok else 'FAIL')
    res.append((name, tag, str(detail))); print(f'{tag} {name}' + (' : ' + str(detail) if detail != '' else ''), flush=True)
# Known gaps (XFAIL): the output is checked on its own, not in the per-phase checks, so the other 23 stay strict
XFAIL_OUT = {21: 'B OUT5 CAN-Lambda: starter limit 10 A = inrush limit 10 A / 100 ms ("Module" preset), but the load starts at '
                 '8.1 A x 1.5 for 100 ms (tools/presim_parts.py CAR_LOADS): it trips at key-on above about 11.1 V and latches '
                 'after 5 tries. Proposal: inrush limit 20 A / 200 ms on B OUT5 (Module preset inrush 2 x limit)'}

# ------------------------------------------------------------------ mutations (each one line of config; must turn RED)
MUTATIONS = [
    ('A2', 'flasher[1].onTime', 500, 'turn-signal on time 350 -> 500 ms'),
    ('A1', 'timer[1].time', 1000, 'cluster off-delay 5 s -> 1 s'),
    ('B', 'condition[1].arg', ps.f32(98.0), 'radiator fan on at 98 C, not 92 C'),
    ('A1', 'virtualInput[1].cond0', 1, 'high beams IN2 OR IN1 (was AND)'),
    ('B', 'canInput[1].timeoutEnabled', 0, 'fuel-pump CAN input without time-out (pump stays on at loss)'),
    ('A1', 'input[5].invert', 0, 'horn input not inverted'),
    ('A2', 'customPdm.critExemptMask', 0, 'box fan not exempt at critical'),
    ('B', 'wiper.parkStopLevel', 0, 'wiper park level inverted'),
    ('B', 'canInput[6].sid', 0x1A9, 'A/C keypad frame ID 0x1A9'),
    ('A1', 'output[1].resetCountLimit', 2, 'low beams: 2 tries before latching (was 5)'),
    ('B', 'timer[1].time', 500, 'battery shed after 0.5 s (a crank dip sheds)'),
    ('A1', 'customPdm.tempCrit', 90, 'board A1 critical 90 C (was 80)'),
]

# ------------------------------------------------------------------ the starter as the app writes it
def load_params():
    P = {'A1': [], 'A2': [], 'B': []}
    for ln in open(os.path.join(HERE, 'data', 'st185-starter.params.dummy.tsv'), encoding='utf-8'):
        if ln.startswith('#') or not ln.strip(): continue
        role, ix, sub, hx, name = ln.rstrip('\n').split('\t')
        P[role].append([int(ix, 16), int(sub), bytes.fromhex(hx), name])
    return P
PARAMS = load_params()
def pset(role, name, value):
    for p in PARAMS[role]:
        if p[3] == name: p[2] = struct.pack('<I', value & 0xFFFFFFFF); return
    raise KeyError(f'{role} {name}')
def pget(role, name):
    return next(struct.unpack('<I', p[2])[0] for p in PARAMS[role] if p[3] == name)

class V:
    """Var-map indices (InitVarMap order, core/device.cpp), as s3_features.V, for board A or B."""
    def __init__(s, model):
        n_di = len(model['inputs']); n_out = len(model['outputs'])
        s.BATT = 4; s.di0 = 5; s.an0 = s.di0 + n_di; s.can0 = s.an0 + 4; s.vi0 = s.can0 + 2 * 32; s.out0 = s.vi0 + 16
        s.fl0 = s.out0 + 4 * n_out; s.cond0 = s.fl0 + 4; s.cnt0 = s.cond0 + 32; s.wip0 = s.cnt0 + 4; s.kp0 = s.wip0 + 6; s.tm0 = s.kp0 + 52
    def can(s, k): return s.can0 + 2 * k
    def vi(s, k): return s.vi0 + k
    def cond(s, k): return s.cond0 + k
    def tm(s, k): return s.tm0 + k * 2
VB = V(ps.BOARD_B); VA = V(ps.BOARD_A)
# The starter's own var numbers, read back so a starter change cannot silently move them (ui/examples/README.md)
assert pget('B', 'output[6].input') == VB.can(5), 'A/C clutch = B CAN input 6 (keypad 0x28 button 1)'
assert pget('B', 'wiper.slowInput') == VB.di0 + 1 and pget('B', 'output[7].input') == VB.wip0
# s5 addition on top of the starter (the starter has no battery load shed; ECUMaster / MoTeC do, s3 F9 proves the recipe):
# A/C clutch off after 2 s at <= 11.5 V (a crank dip does not shed), back at >= 12.5 V. B cond 3 / 4, timer 1, VI 4 / 5.
SHED_VI = VB.vi(3)
ADDITIONS = [('B', 'condition[3].input', VB.BATT), ('B', 'condition[3].operator', 5), ('B', 'condition[3].arg', ps.f32(11.5)), ('B', 'condition[3].enabled', 1),
             ('B', 'condition[4].input', VB.BATT), ('B', 'condition[4].operator', 4), ('B', 'condition[4].arg', ps.f32(12.5)), ('B', 'condition[4].enabled', 1),
             ('B', 'timer[1].input', VB.cond(2)), ('B', 'timer[1].mode', 0), ('B', 'timer[1].time', 2000), ('B', 'timer[1].enabled', 1),
             ('B', 'virtualInput[4].var0', VB.tm(0)), ('B', 'virtualInput[4].cond0', 1), ('B', 'virtualInput[4].var1', VB.vi(3)),
             ('B', 'virtualInput[4].cond1', 0), ('B', 'virtualInput[4].not2', 1), ('B', 'virtualInput[4].var2', VB.cond(3)), ('B', 'virtualInput[4].enabled', 1),
             ('B', 'virtualInput[5].var0', VB.can(5)), ('B', 'virtualInput[5].cond0', 0), ('B', 'virtualInput[5].not1', 1),
             ('B', 'virtualInput[5].var1', VB.vi(3)), ('B', 'virtualInput[5].enabled', 1), ('B', 'output[6].input', VB.vi(4))]
for r_, n_, v_ in ADDITIONS: pset(r_, n_, v_)
# --proposals: the starter fixes proposed for the XFAIL items below (each XFAIL must then XPASS, everything else PASS)
PROPOSALS = [('B', 'output[5].inrushCurrentLimit', ps.f32(20.0)), ('B', 'output[5].inrushTime', 200)]
if '--proposals' in sys.argv:
    for r_, n_, v_ in PROPOSALS: pset(r_, n_, v_)
if MUTATE >= 0:
    r_, n_, v_, why = MUTATIONS[MUTATE]; pset(r_, n_, v_); print(f'MUTATION {MUTATE}: {r_} {n_} = {v_} ({why})')

# ------------------------------------------------------------------ outputs (global numbers as the /pdm page: A1 1-8, A2 9-16, B 17-24)
BOARDS = ('A1', 'A2', 'B')
OUT = {g: (('A1', 'A2', 'B')[(g - 1) // 8], (g - 1) % 8) for g in range(1, 25)}
NAME = {1: 'low beams', 2: 'high beams', 5: 'horn', 7: 'switchboard', 8: 'cluster', 9: 'turn L', 10: 'box fan', 11: 'turn R',
        17: 'radiator fan', 18: 'condenser fan', 19: 'fuel pump', 21: 'CAN-Lambda', 22: 'A/C clutch', 23: 'wiper slow', 24: 'wiper fast'}
def gname(g): k, o = OUT[g]; return f'{k} OUT{o + 1} {NAME.get(g, "(unused)")}'

# ------------------------------------------------------------------ load models
CAR = {(b, o): (n, i, k, t, kind, l) for n, b, o, drv, i, l, k, t, kind in PP.CAR_LOADS}
def car(board, out): return CAR[(board, out)]
# (name, kind, steady A at 13.5 V, inrush x, inrush s, L H)
LOADS = {1: car('A1', 1), 2: car('A1', 2), 5: car('A1', 5), 10: car('A2', 2), 17: car('B', 1), 18: car('B', 2), 19: car('B', 3),
         21: car('B', 5), 22: car('B', 6), 23: car('B', 7),
         # ASSUMED (not in CAR_LOADS): CSB3 switchboard, centre cluster, LED turn lamps (verify_thermal_box a7 0.2 A)
         7: ('Switchboard CSB3', 2.0, 3.0, 0.01, 'electronic', (0, 0)), 8: ('Centre cluster', 1.5, 3.0, 0.01, 'electronic', (0, 0)),
         9: ('Turn L (LED)', 0.2, 3.0, 0.005, 'electronic', (0, 0)), 11: ('Turn R (LED)', 0.2, 3.0, 0.005, 'electronic', (0, 0))}
LOADS[24] = LOADS[23]                                       # one wiper motor: the run winding on OUT7, the fast brush on OUT8
V_NOM = 13.5
class Load:
    """motor: on-current = steady x (1 + (k-1) e^(-3 t / t_inrush)) from switch-on (PWM / flashing keep the start time
    unless off > 200 ms); electronic: k x steady for t_inrush (input capacitors), then steady; coil: steady x (1 - e^(-t / tau)),
    tau = L x steady / 13.5 V (L = middle of the CAR_LOADS range). Currents scale with battery / 13.5 V."""
    def __init__(s, spec):
        s.name, s.i, s.k, s.t, s.kind, (l0, l1) = spec; s.L = (l0 + l1) / 2; s.t_on = None; s.t_off = -1e9; s.on = False
    def current(s, on, t, vbat, active=True):
        if not on or not active:
            if s.on: s.t_off = t; s.on = False
            if s.t_on is not None and t - s.t_off > 0.2: s.t_on = None
            return 0.0
        s.on = True
        if s.t_on is None: s.t_on = t
        dt = t - s.t_on; sc = vbat / V_NOM
        if s.kind == 'motor': return s.i * (1 + (s.k - 1) * math.exp(-3 * dt / max(s.t, 1e-3))) * sc
        if s.kind == 'coil': tau = s.L * s.i / V_NOM; return s.i * (1 - math.exp(-dt / tau)) * sc if tau > 0 else s.i * sc
        return s.i * (s.k if dt < s.t else 1.0) * sc
# RDS(ON) per driver (tools/presim_parts.py: 25 / 150 C), linear in TJ; TJ = board sensor + 15 K (ASSUMED)
RDS = {dn: (d['rds25'], d['rds150']) for dn, d in PP.PROFET.items()}
TJ_OVER_SENSOR = 15.0
def rds(driver, board_c):
    r25, r150 = RDS[driver]; tj = board_c + TJ_OVER_SENSOR
    return r25 + (r150 - r25) * (tj - 25.0) / 125.0
DRIVER = {g: (ps.BOARD_A if OUT[g][0] != 'B' else ps.BOARD_B)['outputs'][OUT[g][1]][5] for g in OUT}

# ------------------------------------------------------------------ mutation runner (each mutant in its own process and .so copies)
if '--mutants' in sys.argv:
    from concurrent.futures import ThreadPoolExecutor
    def one(k):
        d = tempfile.mkdtemp(prefix=f's5mut{k}_')
        for f in os.listdir(SO):
            if re.match(r'custompdm_[ab]_unit\d\.so$', f): shutil.copy(os.path.join(SO, f), d)
        p = subprocess.run([sys.executable, os.path.abspath(__file__), d, '--mutate', str(k), '--out', os.path.join(d, 'out')],
                           capture_output=True, text=True)
        fails = [l for l in p.stdout.splitlines() if l.startswith('FAIL ')]
        shutil.rmtree(d, ignore_errors=True)
        return k, p.returncode, fails
    with ThreadPoolExecutor(max_workers=min(len(MUTATIONS), os.cpu_count() or 4)) as ex:
        out = list(ex.map(one, range(len(MUTATIONS))))
    red = 0
    for k, rc, fails in out:
        red += rc != 0
        print(f"{'RED  ' if rc else 'GREEN'} mutant {k}: {MUTATIONS[k][3]} ({len(fails)} FAIL)" + (f": {fails[0][5:120]}" if fails else ''))
    print(f'S5 mutants: {red} of {len(MUTATIONS)} RED')
    sys.exit(0 if red == len(MUTATIONS) else 1)

# ------------------------------------------------------------------ the bus: boards, PC tool, ECU, keypad, car traffic
random.seed(20261123)
bus = ps.Bus(); tool = ps.Tool(bus)
B = {'A1': ps.Board(ps.BOARD_A, 'A1', SO, unit=1), 'A2': ps.Board(ps.BOARD_A, 'A2', SO, unit=2), 'B': ps.Board(ps.BOARD_B, 'B', SO)}
BASE = {'A1': 0x500, 'A2': 0x540, 'B': 0x580}
for b in B.values(): b.set_vbat(12.6); b.set_temp(25.0, 28.0)
ECU_CMD, ECU_CLT, KP_ID = 0x3F4, 0x3F5, 0x1A8
ecu = ps.PyNode('ecu'); ecu.powered = False
kp = ps.PyNode('keypad'); kp.powered = False
carn = ps.PyNode('car'); carn.powered = False
S = dict(ign=0, head=0, high=0, horn=0, turnL=0, turnR=0, hazard=0, pump=0, fan=0, coolant=80.0, ac=0, vbat=12.6,
         temp={'A1': 25.0, 'A2': 25.0, 'B': 25.0}, link={'A1': True, 'A2': True, 'B': True}, awake={'A1': True, 'A2': True, 'B': True},
         crit={'A1': False, 'A2': False, 'B': False}, boxfan=0, rad=0, b_seen_ecu=False, shed=False, fault_low=False,
         fault_free=False, wiper=False, cluster_hold=False, sw_can=False)
ecu_frames = []                                                  # times (us) of every ECU command frame on the bus
def ecu_tx(t):
    ecu.send(ECU_CMD, bytes([S['pump'], S['fan'], 0, 0, 0, 0, 0, 0])); ecu.send(ECU_CLT, struct.pack('<H', int(round(S['coolant'] * 10))) + bytes(6))
ecu.every(50000, ecu_tx, start=7000)
kp.every(100000, lambda t: kp.send(KP_ID, bytes([S['ac'], 0, 0, 0, 0, 0, 0, 0])), start=23000)
rows = []
for ln in open(os.path.join(REPO, 'docs', 'car-can-dummy', 'bus-load.dummy.md'), encoding='utf-8'):
    m = re.match(r'\| (0x[0-9A-Fa-f]{3})\s*\| ([^|]+)\| (\d) \| ([\d.]+) \| ([\d.]+) \|', ln)
    if m and float(m.group(5)) > 0 and int(m.group(1), 16) not in (ECU_CMD, ECU_CLT, KP_ID):
        rows.append((int(m.group(1), 16), int(m.group(3)), float(m.group(5))))
for i_, d_, fps in rows:
    carn.every(int(1e6 / fps), (lambda i, d: lambda t: carn.send(i, bytes(d)))(i_, d_), start=random.randint(0, int(1e6 / fps)))
info['dummy_car_frames'] = len(rows)
wake_req = set()
def on_frame(f):
    if f.src == 'ecu' and f.id == ECU_CMD: ecu_frames.append(f.t)
    for k, b in B.items():                                       # CAN RX is armed in sleep (DisableCanWake off): any frame wakes
        if k != f.src and b.connected and b.flags()['asleep']: wake_req.add(k)
bus.watch.append(on_frame)
stat = {k: ps.Status(BASE[k]) for k in B}
for s_ in stat.values(): bus.watch.append(s_.feed)
bus.add(tool, ecu, kp, carn, *B.values())

# ------------------------------------------------------------------ loads, wiper motor + park cam, pins
LD = {g: Load(LOADS[g]) for g in LOADS if g != 24}
class Wiper:
    """Wiper motor + park cam (s3 F8): one turn 1.0 s slow / 0.6 s fast; cam closed (12 V on B IN4) for the first 10 %."""
    def __init__(s): s.pos = 0.02; s.turns = 0; s.starts = []; s.was_on = False
    def step(s, slow, fast, t):
        on = slow or fast
        if on:
            p = s.pos + 1.0 / (600.0 if fast else 1000.0)
            if int(p) > int(s.pos): s.turns += 1
            s.pos = p
        if on and not s.was_on: s.starts.append(t)
        s.was_on = on
        B['B'].set_input(3, '12v' if (s.pos % 1.0) < 0.10 else 'gnd')
    def parked(s): return (s.pos % 1.0) < 0.10
WIP = Wiper()
SHORT = {}
PIN = {g: 0 for g in OUT}; EDGES = {g: [] for g in OUT}; IMOD = {g: 0.0 for g in OUT}; OHMS = {}
def read_pins():
    for g, (k, o) in OUT.items():
        b = B[k]; v = b.level(b.model['outputs'][o][0]) if b.powered else 0
        if v != PIN[g]: EDGES[g].append((now_ms(), v)); PIN[g] = v
def now_ms(): return bus.now / 1000.0
def set_ohms(g, ohms):
    k, o = OUT[g]
    if OHMS.get(g) is None or abs(OHMS[g] - ohms) > 0.003 * max(ohms, 1e-6): OHMS[g] = ohms; B[k].set_load(o, ohms)
def update_loads():
    t = now_ms() / 1000.0; vb = S['vbat']
    for g, ld in LD.items():
        if g in SHORT:                                        # a short at the load (the overcurrent step)
            IMOD[g] = vb / SHORT[g] if PIN[g] else 0.0; set_ohms(g, SHORT[g]); continue
        if g == 23:                                           # the wiper motor: run winding (OUT7) unless the fast brush (OUT8) is on
            on = PIN[23] or PIN[24]; i = ld.current(on, t, vb)
            IMOD[23], IMOD[24] = ((0.2 * vb / V_NOM if PIN[23] else 0.0), i) if PIN[24] else (i, 0.0)   # 0.2 A ASSUMED: run feed while fast
            for gg in (23, 24): set_ohms(gg, vb / IMOD[gg] if IMOD[gg] > 1e-3 else vb / (ld.i * ld.k * vb / V_NOM))
            continue
        i = ld.current(PIN[g], t, vb); IMOD[g] = i
        if i > 1e-3: set_ohms(g, vb / i)
        else: set_ohms(g, vb / max(ld.i * (ld.k if ld.kind != 'coil' else 0.05) * vb / V_NOM, 1e-3))

# ------------------------------------------------------------------ the independent logic model of the car (starter's own words)
def hears(dst, src):
    """dst board receives src board's frames: both on the bus (CAN plugged) and awake."""
    return S['link'][dst] and S['link'][src] and S['awake'][dst] and S['awake'][src]
def ecu_to_b(): return ecu.powered and S['link']['B'] and S['awake']['B']
def kp_to_b(): return kp.powered and S['link']['B'] and S['awake']['B']
def logic():
    """The 24 outputs as the starter says (ui/examples/README.md, UiWalkTests trigger words); 'flash' / 'free' = checked apart."""
    E = {g: 0 for g in OUT}
    if ecu_to_b(): S['b_seen_ecu'] = True
    sw_can = bool(S['ign'] and hears('A1', 'B'))
    if S['sw_can'] and not sw_can: S['cluster_hold'] = True        # cluster: off-delay 5 s from the CAN ignition (A1 timer 1)
    if sw_can: S['cluster_hold'] = False
    S['sw_can'] = sw_can
    a1 = S['awake']['A1'] and not S['crit']['A1']; a2 = S['awake']['A2'] and not S['crit']['A2']; b = S['awake']['B'] and not S['crit']['B']
    if a1:
        E[1] = 'free' if S['fault_free'] else int(S['head'] and not S['fault_low'])      # low beams = IN1
        E[2] = int(S['high'] and S['head'])                                              # high beams = IN2 AND IN1
        E[5] = int(S['horn'])                                                            # horn = IN5 (to ground, inverted)
        E[7] = int(sw_can)                                                               # switchboard = B IN15 over CAN
        E[8] = int(sw_can or S['cluster_hold'])                                          # cluster = same, off-delay 5 s
    if a2:
        E[9] = 'flash' if (S['turnL'] or S['hazard']) else 0                             # IN8 or hazard IN10, 350 / 350 ms
        E[11] = 'flash' if (S['turnR'] or S['hazard']) else 0
    # box fan (A2 OUT2): on at >= 45 C on the hottest board, off when all three are <= 40 C (lost board: no vote)
    t = S['temp']; seen = {k: (k == 'A2' and S['awake']['A2']) or (k != 'A2' and hears('A2', k)) for k in BOARDS}
    if any(seen[k] and t[k] >= 45.0 for k in BOARDS): S['boxfan'] = 1
    elif all(seen[k] and t[k] <= 40.0 for k in BOARDS): S['boxfan'] = 0
    if S['awake']['A2']: E[10] = S['boxfan']                                             # exempt from A2's critical cut
    if b:
        clt = S['coolant'] if ecu_to_b() else 0.0                                        # a timed-out CAN value reads 0
        if clt >= 92.0: S['rad'] = 1
        elif clt <= 88.0: S['rad'] = 0
        E[17] = S['rad']                                                                 # radiator fan: on 92 / off 88 C
        E[18] = int(S['fan']) if ecu_to_b() else int(S['b_seen_ecu'])                  # condenser fan: byte 1, ON at loss
        E[19] = int(S['pump']) if ecu_to_b() else 0                                      # fuel pump: byte 0, OFF at loss
        E[21] = int(S['ign'])                                                            # CAN-Lambda = IN15
        E[22] = int(S['ac'] and kp_to_b() and not S['shed'])                             # A/C = keypad button 1 (s5: battery shed)
        E[23] = E[24] = 'free' if S['wiper'] else 0
    return E

# ------------------------------------------------------------------ expectations: every pin, every ms
LAT = {g: (0, 30, 0) for g in OUT}                                   # (earliest, latest change after the stimulus ms, grace ms)
LAT.update({1: (15, 32, 0), 2: (15, 32, 0), 5: (15, 32, 0), 21: (15, 32, 0),     # wire input, 20 ms debounce, 2 ms loop
            7: (15, 140, 0), 8: (15, 140, 0),                                    # B input -> msg 37 (100 ms) -> A1
            10: (0, 450, 0), 17: (0, 100, 1100), 18: (0, 100, 1100), 19: (0, 70, 0),  # temps; ECU frames 50 ms (+ the first 22 Hz PWM pulse of the 1 s soft start)
            22: (0, 110, 0)})                                                    # keypad frame every 100 ms
EXP = {g: dict(v=0, t=0.0, lo=0, hi=0, grace=0, pend=False, hit=0.0, old=0) for g in OUT}
VIOL = []; TIMES = []; PHASE = ['boot']; PH_T = {}; MISMATCH_MS = {}
def expect(g, v, lo, hi, grace=0, label=None):
    e = EXP[g]
    if e['v'] == v and not e['pend']: return
    if e['pend'] and e['v'] == v: return
    if e['pend'] and v == e['old']: e.update(v=v, pend=False, hit=now_ms()); return     # changed back before it happened
    e.update(old=e['v'], v=v, t=now_ms(), lo=lo, hi=hi, grace=grace, pend=v not in ('flash', 'free') and e['v'] != v, hit=now_ms(),
             label=label or PHASE[0])
def update(lat=None, only=None):
    """Recompute the logic model and expect every changed output within its window (lat: {g: (lo, hi[, grace])} overrides)."""
    E = logic()
    for g, v in E.items():
        if only and g not in only: continue
        lo, hi, gr = (tuple((lat or {}).get(g, LAT[g])) + (LAT[g][2],))[:3]
        expect(g, v, lo, hi, gr)
VIOL_X = []
def check_pins():
    t = now_ms()
    for g, e in EXP.items():
        v = e['v']
        if v in ('flash', 'free'): continue
        p = PIN[g]
        VIOL_ = VIOL_X if g in XFAIL_OUT else VIOL
        if e['pend']:
            if p == v:
                dt = t - e['t']
                if dt < e['lo'] - 1e-6: VIOL_.append((PHASE[0], g, 'early', round(dt, 1), f"{e['old']}->{v} window {e['lo']}..{e['hi']} ms"))
                TIMES.append((PHASE[0], gname(g), v, round(dt, 1), e['lo'], e['hi'])); e['pend'] = False; e['hit'] = t
            elif t - e['t'] > e['hi']:
                VIOL_.append((PHASE[0], g, 'late', round(t - e['t'], 1), f"{e['old']}->{v} window {e['lo']}..{e['hi']} ms")); e['pend'] = False; e['hit'] = t
            continue
        if t < e['hit'] + e['grace']: continue
        if p != v:
            k = (PHASE[0], g); MISMATCH_MS[k] = MISMATCH_MS.get(k, 0) + 1
            if MISMATCH_MS[k] == 1: VIOL_.append((PHASE[0], g, 'wrong', round(t, 1), f'pin {p}, logic {v}'))

# ------------------------------------------------------------------ time: one 1 ms tick, power and current logs
SCHED = []; POW_ROWS = []; TRACE = []; _acc = {'t0': 0.0, 'E': {k: 0.0 for k in BOARDS}, 'I': {g: 0.0 for g in OUT}, 'n': 0}
ENERGY = {k: 0.0 for k in BOARDS}; PEAK = {k: 0.0 for k in BOARDS}
def at(t_ms, fn): SCHED.append((t_ms, fn)); SCHED.sort(key=lambda x: x[0])
def wake(k):
    """EXTI wake from STOP = an MCU reset (core/sleep.cpp; not emulated in the sim core): the firmware starts again from FRAM."""
    b = B[k]; fram, opt = b.fram(), b.L.sim_opt_get(); held = b.board_c
    b.resets.append((bus.now, 'wake')); b.t0 = bus.now; b._load(fram, opt, ps.RSTF_SFT); b.mcp_carry(held)
    S['awake'][k] = True
    if k == 'B': S['b_seen_ecu'] = False
def tick():
    bus.run_for(1); t = now_ms()
    for k in list(wake_req):
        wake_req.discard(k)
        if B[k].flags()['asleep']: wake(k); WAKES.append((k, t))
    read_pins()
    WIP.step(PIN[23], PIN[24], t)
    update_loads()
    while SCHED and SCHED[0][0] <= t: SCHED.pop(0)[1]()
    check_pins()
    dt = 1e-3
    for g, (k, o) in OUT.items():
        i = IMOD[g] if PIN[g] else 0.0
        if i:
            p = i * i * rds(DRIVER[g], B[k].board_c); _acc['E'][k] += p * dt; ENERGY[k] += p * dt
        _acc['I'][g] += i
    _acc['n'] += 1
    if _acc['n'] >= 500:                                             # one CSV row per 500 ms: mean W per board, mean A per output
        row = [round(t / 1000, 3), PHASE[0].replace(',', ';'), round(S['vbat'], 2)] + [round(_acc['E'][k] / 0.5, 3) for k in BOARDS] + \
              [round(_acc['I'][g] / _acc['n'], 3) for g in OUT]
        POW_ROWS.append(row)
        for k in BOARDS: PEAK[k] = max(PEAK[k], _acc['E'][k] / 0.5)
        _acc.update(E={k: 0.0 for k in BOARDS}, I={g: 0.0 for g in OUT}, n=0)
    if int(t) % 10 == 0 or g_dbg:
        TRACE.append([round(t, 1), PHASE[0].replace(',', ';'), round(S['vbat'], 2)] + [round(IMOD[g] if PIN[g] else 0.0, 3) for g in OUT] +
                     [round(B[k].L.sim_out_current(o), 3) for g, (k, o) in OUT.items()])
WAKES = []
g_dbg = '--trace-1ms' in sys.argv                                    # current trace every 1 ms (debugging)
def run(ms):
    for _ in range(int(ms)): tick()
def phase(name):
    PHASE[0] = name; PH_T[name] = now_ms(); print(f'--- {name} (t = {now_ms() / 1000:.1f} s)', flush=True)
def phase_ok(name, extra=''):
    v = [x for x in VIOL if x[0] == name]
    check(f'{name}: all 24 output pins match the logic model every 1 ms, every change inside its window', not v,
          (v[:4] if v else '') or extra)
def edges_in(g, t0, t1): return [(t, v) for t, v in EDGES[g] if t0 <= t <= t1]
def spans(g, t0, t1, level=1):
    e = edges_in(g, t0, t1); out = []; st = None
    for t, v in e:
        if v == level: st = t
        elif st is not None: out.append(round(t - st, 1)); st = None
    return out

# ------------------------------------------------------------------ inputs (wires), as the starter names them
WIRE = dict(ign=('B', 0), head=('A1', 0), high=('A1', 1), turnL=('A2', 0), turnR=('A2', 1), hazard=('A2', 2),
            wslow=('B', 1), wfast=('B', 2), wint=('B', 4))
def sw(name, val, lat=None, only=None):
    """A switch on a wire (12 V when on); the horn switches to ground (IN5, input-board DIP pull-up, inverted in the starter)."""
    if name == 'horn': B['A1'].set_input(4, 'gnd' if val else 'open', 'up')
    else: k, i = WIRE[name]; B[k].set_input(i, '12v' if val else 'gnd')
    if name in S: S[name] = val
    update(lat, only)
def set_vbat(v):
    S['vbat'] = v
    for b in B.values(): b.set_vbat(v)
def set_temps(a1, a2, b, lat=None):
    for k, c in (('A1', a1), ('A2', a2), ('B', b)):
        S['temp'][k] = c; B[k].set_temp(c, c + 3.0)
        lim, hy = ((ps.TEMP_DEFAULT_B if k == 'B' else ps.TEMP_DEFAULT)['crit'], 6.0)
        if c >= lim: S['crit'][k] = True
        elif c < lim - hy: S['crit'][k] = False
    update(lat or {g: (0, 450) for g in OUT})
HOLD = [0]
def cluster_timer():
    """A1 timer 1 (off-delay 5 s) starts when A1's CAN ignition input falls = the switchboard (A1 OUT7) falling edge."""
    if S['cluster_hold'] and HOLD[0] == 0 and EDGES[7] and EDGES[7][-1][1] == 0 and EDGES[7][-1][0] >= PH_T[PHASE[0]]:
        HOLD[0] = 1; tok = len(EDGES[7]); t_edge = EDGES[7][-1][0]
        def expire():
            HOLD[0] = 0
            if S['cluster_hold'] and len(EDGES[7]) == tok: S['cluster_hold'] = False; update(lat={8: (0, 20)})
        at(t_edge + 4995, expire)
    if not S['cluster_hold']: HOLD[0] = 0
_tick = tick
def tick():
    _tick(); cluster_timer()
def send_write(k, index, sub, value):
    """A live Write (cmd 2) as the app sends it (SendOnly): the board's reply is not waited for, time runs on."""
    tool.send(BASE[k] + 1, bytes([ps.CMD['Write'], index & 255, index >> 8, sub]) + struct.pack('<I', value & 0xFFFFFFFF))
FINDINGS = []

# ================================================================== 0. the starter onto three fresh boards (Write All + Burn)
phase('load the ST185 starter (Write All + Burn, as the app)')
bus.run_for(1500)
wa = {}
for k in BOARDS:
    r = tool.read_all(BASE[k], ms=20000)
    order = [(ix, sub) for ix, sub, _ in r[0]] if r else []
    crc_ok = bool(r) and (zlib.crc32(b''.join(struct.pack('<I', v) for _, _, v in r[0])) & 0xFFFFFFFF) == r[1]
    dump = {(ix, sub): bv for ix, sub, bv, _ in PARAMS[k]}
    same_set = sorted(order) == sorted(dump) and len(order) == len(PARAMS[k])
    vals = [(ix, sub, struct.unpack('<I', dump[(ix, sub)])[0]) for ix, sub in order if (ix, sub) in dump]
    crc = zlib.crc32(b''.join(dump[(ix, sub)] for ix, sub in order if (ix, sub) in dump)) & 0xFFFFFFFF
    ok = same_set and tool.write_all(BASE[k], vals, crc); burned = ok and tool.burn(BASE[k])
    back = tool.read_all(BASE[k], ms=20000)
    wa[k] = (len(order), crc_ok, same_set, ok, burned, bool(back) and [v for _, _, v in back[0]] == [v for _, _, v in vals])
check('starter: each board\'s own param table (Read All, its CRC = CRC-32 of the values) is exactly the app\'s file; Write All applied, burned, Read All gives it back',
      all(v[1:] == (True, True, True, True, True) for v in wa.values()), wa)
# first key-on next morning: every board starts again from its FRAM (the starter as saved)
for k, b in B.items():
    fr, opt = b.fram(), b.L.sim_opt_get(); b.resets.append((bus.now, 'restart')); b.t0 = bus.now; b._load(fr, opt, ps.RSTF_POR | ps.RSTF_BOR)
B['A1'].set_input(4, 'open', 'up')
for k, i in WIRE.values(): B[k].set_input(i, 'gnd')
phase('parked, key off')
read_pins(); update(); run(1500)
phase_ok('parked, key off')

# ================================================================== 1. key on, ECU prime
phase('key on, ECU prime')
kp.powered = carn.powered = True; sw('ign', 1); run(300)
S['pump'] = 1; ecu.powered = True; update(); run(2000)          # ECU prime: pump 2 s (ECU logic, dummy)
S['pump'] = 0; update(); run(1000)
phase_ok('key on, ECU prime')

# ================================================================== 2. crank (6 V dip)
phase('crank (6 V dip)')
resets0 = {k: len(b.resets) for k, b in B.items()}; shed_seen = [0.0]
def crank_watch():
    shed_seen[0] = max(shed_seen[0], B['B'].L.sim_var(SHED_VI))
S['pump'] = 1; update(); run(100)
set_vbat(6.0); update()
for _ in range(80): tick(); crank_watch()
set_vbat(9.6); update()
for _ in range(1200): tick(); crank_watch()
set_vbat(14.2); update()
for _ in range(2500): tick(); crank_watch()
phase_ok('crank (6 V dip)')
check('crank: no MCU reset on any board (6.0 V for 80 ms, 9.6 V for 1.2 s), the battery shed latch never set (ignores dips < 2 s)',
      all(len(b.resets) == resets0[k] for k, b in B.items()) and shed_seen[0] == 0, ({k: b.resets[resets0[k]:] for k, b in B.items()}, shed_seen[0]))

# ================================================================== 3. idle
phase('idle 14.2 V'); run(2000); phase_ok('idle 14.2 V')

# ================================================================== 4. lights
phase('lights low / high')
sw('head', 1); run(800); sw('high', 1); run(800); sw('head', 0); run(800); sw('head', 1); run(800); sw('high', 0); run(800)
phase_ok('lights low / high')

# ================================================================== 5. turn signals, hazard
phase('turn signals + hazard')
FL = {}
for name, gs in (('turnL', (9,)), ('turnR', (11,)), ('hazard', (9, 11))):
    t0 = now_ms(); sw(name, 1); run(3000); t1 = now_ms(); sw(name, 0, lat={9: (0, 40), 11: (0, 40)}); run(800)
    FL[name] = {g: dict(first=round(edges_in(g, t0, t1)[0][0] - t0, 1) if edges_in(g, t0, t1) else None,
                        on=spans(g, t0, t1, 1), off=spans(g, t0, t1, 0)) for g in gs}
    if name == 'hazard':
        rl = [t for t, v in edges_in(9, t0, t1) if v]; rr = [t for t, v in edges_in(11, t0, t1) if v]
        FL['hazard_in_step'] = len(rl) == len(rr) and all(abs(a - b) <= 2 for a, b in zip(rl, rr))
phase_ok('turn signals + hazard')
fl_ok = all(f['first'] is not None and f['first'] <= 32 and len(f['on']) >= 4 and all(abs(x - 350) <= 5 for x in f['on'][:-1] + f['off'][:-1])
            for n in ('turnL', 'turnR', 'hazard') for f in FL[n].values())
check('turn signals: first flash <= 32 ms after the switch, then 350 ms on / 350 ms off (+-5 ms); hazard: left and right in step (<= 2 ms)',
      fl_ok and FL['hazard_in_step'], {n: {g: (f['first'], sorted(set(f['on'])), sorted(set(f['off']))) for g, f in FL[n].items()} for n in ('turnL', 'turnR', 'hazard')})

# ================================================================== 6. horn
phase('horn'); sw('horn', 1); run(400); sw('horn', 0); run(300); phase_ok('horn')

# ================================================================== 7. wipers
phase('wipers slow / fast / intermittent')
WP = {}
def wipe(name, ms):
    S['wiper'] = True; update(); turns0 = WIP.turns; t0 = now_ms(); sw('w' + name, 1); run(ms); t1 = now_ms(); sw('w' + name, 0)
    on_while = (sum(1 for t, v in edges_in(23, t0, t1)), PIN[23], PIN[24])
    for _ in range(3000):
        tick()
        if not PIN[23] and not PIN[24] and WIP.parked(): break
    run(300); WP[name] = dict(turns=WIP.turns - turns0, parked=WIP.parked() and not PIN[23] and not PIN[24], stop_ms=round(now_ms() - t1),
                              starts=[round(t - t0) for t in WIP.starts if t >= t0], o8=spans(24, t0, now_ms(), 1))
    S['wiper'] = False; update(lat={23: (0, 5), 24: (0, 5)})
wipe('slow', 3300); wipe('fast', 2000); wipe('int', 9500)
phase_ok('wipers slow / fast / intermittent')
gaps = [b - a for a, b in zip(WP['int']['starts'], WP['int']['starts'][1:])]
check('wipers: slow about 3 turns in 3.3 s (OUT8 never on), fast about 3 turns in 2 s (OUT7 + OUT8), each parks inside the cam zone after the switch is off',
      WP['slow']['turns'] in (3, 4) and not WP['slow']['o8'] and WP['fast']['turns'] in (3, 4) and WP['fast']['o8'] and WP['slow']['parked'] and WP['fast']['parked'],
      {k: (v['turns'], v['parked'], v['stop_ms']) for k, v in WP.items()})
check('wiper intermittent: one wipe, park, 3 s pause (starter intermitTime[0]), wipe again: starts 4.0 s apart (+-0.15 s), parked at the end',
      len(gaps) >= 2 and all(3850 <= g_ <= 4150 for g_ in gaps) and WP['int']['parked'], (WP['int']['starts'], gaps))

# ================================================================== 8. coolant 80 -> 105 -> 85 C
phase('coolant 80 -> 105 -> 85 C, fans')
def coolant_to(c1, rate_c_s, ecu_fan=None):
    while abs(S['coolant'] - c1) > 1e-6:
        S['coolant'] = round(S['coolant'] + max(-0.1, min(0.1, c1 - S['coolant'])) * (1 if rate_c_s >= 1 else rate_c_s), 2)
        if ecu_fan: ecu_fan()
        update(); run(100)
def ecu_fan_logic():                                             # dummy ECU: condenser fan on at >= 98, off at <= 95 C
    if S['coolant'] >= 98.0 and not S['fan']: S['fan'] = 1
    elif S['coolant'] <= 95.0 and S['fan']: S['fan'] = 0
t_c = now_ms(); coolant_to(105.0, 1, ecu_fan_logic); run(3000); coolant_to(85.0, 1, ecu_fan_logic); run(1500)
phase_ok('coolant 80 -> 105 -> 85 C, fans')
def duty(g, t0, ms): return round(sum(1 for t in range(int(t0), int(t0 + ms)) if level_at(g, t)) / ms, 2)
def level_at(g, t):
    v = 0
    for te, lv in EDGES[g]:
        if te > t: break
        v = lv
    return v
rise = [t for t, v in edges_in(17, t_c, now_ms()) if v][:1]
ramp = [duty(17, rise[0] + a, 200) for a in (0, 300, 600, 1100)] if rise else []
check('radiator fan soft start (22 Hz PWM, 1 s ramp): duty rises over the first second, then fully on', len(ramp) == 4 and ramp[0] < ramp[1] < ramp[2] < 1.0 and ramp[3] == 1.0, ramp)

# ================================================================== 9. A/C clutch from the keypad
phase('A/C clutch (keypad 0x28 button 1)')
S['ac'] = 1; update(); run(5000); S['ac'] = 0; update(); run(500)
phase_ok('A/C clutch (keypad 0x28 button 1)')

# ================================================================== 10. hot day (thermal model temperatures)
phase('hot day: board temperatures from the thermal model')
t_h = now_ms()
before_hot = dict(PIN)
for n in range(1, 41): set_temps(25 + (HOT_A - 25) * n / 40, 25 + (HOT_A - 25) * n / 40, 25 + (HOT_B - 25) * n / 40); run(500)
run(5000); at_hot = dict(PIN)
for n in range(1, 21): set_temps(HOT_A + (60 - HOT_A) * n / 20, HOT_A + (60 - HOT_A) * n / 20, HOT_B + (60 - HOT_B) * n / 20); run(500)
run(3000)
for n in range(1, 11): set_temps(60 - 25 * n / 10, 60 - 25 * n / 10, 60 - 25 * n / 10); run(500)
run(3000)
phase_ok('hot day: board temperatures from the thermal model')
cut = [g for g in OUT if before_hot[g] and not at_hot[g]]
if HOT_A >= ps.TEMP_DEFAULT['crit']:
    FINDINGS.append(f'hot day (60 C cabin, car loads, fans on): board A at {HOT_A:.1f} C (sink + 15 K, ASSUMED) is over its 80 C critical: '
                    f'A1 and A2 cut every output but the box fan ({", ".join(gname(g) for g in cut)}) until < 74 C; board B at {HOT_B} C runs on (warn 98)')
info['hot_day_cut'] = [gname(g) for g in cut]

# ================================================================== 11. ECU frames lost 3 s and back
phase('ECU frames lost 3 s and back')
S['coolant'] = 95.0; S['fan'] = 0; S['pump'] = 1; update(); run(2500)       # radiator fan on (95 C), condenser off, pump on
t_l = now_ms(); ecu.powered = False
update(lat={17: (940, 1060, 1100), 18: (940, 1060, 1100), 19: (940, 1060)}); run(3000)
last = max(t for t in ecu_frames if t / 1000 <= t_l) / 1000
pump_off = [t for t, v in edges_in(19, t_l, now_ms()) if v == 0][:1]
ecu.powered = True; update(); t_b = now_ms(); run(2500)
first = min((t for t in ecu_frames if t / 1000 > t_b), default=None)
pump_on = [t for t, v in edges_in(19, t_b, now_ms()) if v == 1][:1]
phase_ok('ECU frames lost 3 s and back')
lo = round(pump_off[0] - last, 1) if pump_off else None; bk = round(pump_on[0] - first / 1000, 1) if pump_on and first else None
check('ECU loss: fuel pump off 1000-1010 ms after the last ECU frame (1 s time-out), back within 5 ms of the first frame after it', lo is not None and 1000 <= lo <= 1010 and bk is not None and 0 <= bk <= 5, (lo, bk))
FINDINGS.append('ECU frames lost with a hot engine (95 C): the radiator fan goes OFF 1 s later (the coolant CAN value times out to 0, '
                'so "off at 88 C or less" is true) while the condenser fan goes ON (its "on at loss")')

# ================================================================== 12. board B unplugged 3 s and back
phase('board B unplugged 3 s and back')
t_u = now_ms(); B['B'].connected = False; S['link']['B'] = False
update(lat={7: (880, 1060), 17: (940, 1060, 1100), 18: (940, 1060, 1100), 19: (940, 1060), 22: (900, 1110), 10: (0, 450)}); run(3000)
B['B'].connected = True; S['link']['B'] = True; t_r = now_ms(); update(lat={7: (0, 140), 8: (0, 140)}); run(2500)
phase_ok('board B unplugged 3 s and back')
sw_off = [round(t - t_u) for t, v in edges_in(7, t_u, t_r) if v == 0]; cl = [t for t, v in edges_in(8, t_u, t_r) if v == 0]
check('board B unplugged: A1 switchboard (ignition over CAN) off after its 1 s time-out, cluster kept by its 5 s off-delay; B pump off at its ECU time-out; all back after the replug',
      sw_off and 890 <= sw_off[0] <= 1060 and not cl and PIN[7] and PIN[8] and PIN[19], (sw_off, len(cl), PIN[7], PIN[8], PIN[19]))
FINDINGS.append('board B unplugged (its CAN only) while driving: the fuel pump stops after 1 s (B no longer hears the ECU) - the "pump off at loss" '
                'policy, so a loose B connector stalls the engine; A1 switchboard drops after 1 s (ignition comes from B over CAN)')

# ================================================================== 13. overcurrent fault + Reset faults (master retry)
phase('overcurrent on the low beams + Reset faults')
S['fault_free'] = True; update(); t_f = now_ms(); SHORT[1] = 0.25; run(7500)
on = spans(1, t_f, now_ms(), 1); starts = [t for t, v in edges_in(1, t_f, now_ms()) if v == 1]
first_cut = [round(t - t_f, 1) for t, v in edges_in(1, t_f, now_ms()) if v == 0][:1]
st_gap = [round(b - a) for a, b in zip(starts, starts[1:])]
latched = not PIN[1] and (not starts or now_ms() - starts[-1] > 1500)
S['fault_free'] = False; S['fault_low'] = True; update(lat={1: (0, 5)})
del SHORT[1]; run(1000); still_off = not PIN[1]
t_rf = now_ms()
for step, var in enumerate((0, 1, 0)):                         # the /pdm Reset faults button: master retry input = 0, 1, back (50 ms apart)
    for k in BOARDS: send_write(k, ps.TEMP_INDEX, 6, var)
    if step == 1: S['fault_low'] = False; update(lat={1: (0, 60)})
    run(50)
run(1000)
back_on = [round(t - t_rf, 1) for t, v in edges_in(1, t_rf, now_ms()) if v == 1][:1]
phase_ok('overcurrent on the low beams + Reset faults')
nmax = 5                                                       # the starter: low beams reset count 5, reset time 1000 ms, inrush 100 ms
# a short while on: cut at once; each retry is a fresh switch-on whose full-scale reading (about 10.5-12.3 A on board A) is
# under the 15 A inrush limit, so the firmware waits the 100 ms inrush window (the PROFET protects itself meanwhile; s3 F12)
check('overcurrent (0.25 Ohm short on A1 OUT1 while on): cut <= 8 ms, then 4 retries (5 trips = reset count 5) 1000 ms after each cut, '
      'each cut at the end of the 100 ms inrush window; then latched off, still off with the short gone; Reset faults turns it back on <= 110 ms',
      first_cut and first_cut[0] <= 8 and len(on) == nmax - 1 and all(99 <= x <= 106 for x in on) and all(1095 <= g_ <= 1112 for g_ in st_gap)
      and latched and still_off and back_on and back_on[0] <= 110,
      dict(first_cut_ms=first_cut, retry_on_ms=on, retry_gaps=st_gap, latched=latched, still_off=still_off, back_on_ms=back_on))

# ================================================================== 14. low battery load shed (s5 addition)
phase('low battery: A/C clutch shed')
S['ac'] = 1; update(); run(1500)
t_s = now_ms(); set_vbat(11.2); S['shed'] = True; update(lat={22: (2000, 2400)}); run(4000)
set_vbat(12.0); update(); run(1500)
set_vbat(12.6); S['shed'] = False; update(lat={22: (0, 400)}); run(1500)
S['ac'] = 0; update(); set_vbat(14.2); run(500)
phase_ok('low battery: A/C clutch shed')
shed_ms = [round(t - t_s) for t, v in edges_in(22, t_s, now_ms()) if v == 0][:1]
check('battery shed: A/C clutch off 2.0-2.4 s after the battery falls to 11.2 V, stays off at 12.0 V, back at 12.6 V', shed_ms and 2000 <= shed_ms[0] <= 2400, shed_ms)

# ================================================================== 15. key off
phase('key off')
sw('head', 0); run(500)
t_k = now_ms(); kp.powered = carn.powered = False; S['pump'] = 0; S['fan'] = 0; sw('ign', 0); run(2000)    # ECU holds itself 2 s (dummy)
ecu.powered = False; t_e = now_ms(); update(lat={17: (940, 1060, 1100), 18: (940, 1060, 1100), 19: (940, 1060)}); run(6000)
phase_ok('key off')
cl_off = [round(t - t_k) for t, v in edges_in(8, t_k, now_ms()) if v == 0][:1]
sw_off = [round(t - t_k) for t, v in edges_in(7, t_k, now_ms()) if v == 0][:1]
check('key off: switchboard off <= 140 ms (ignition over CAN), cluster off 5.0 s after it (off-delay), CAN-Lambda off <= 32 ms',
      sw_off and sw_off[0] <= 140 and cl_off and 0 <= cl_off[0] - sw_off[0] - 5000 <= 20, (sw_off, cl_off))
if PIN[18]:
    FINDINGS.append('key off: once the ECU stops sending, the condenser fan comes ON (its "on at loss" is not tied to the ignition) and '
                    'runs until the PDM sleeps; the starter has auto-sleep off (device.sleepEnabled 0 on all three)')

# ================================================================== 16. sleep (the app's sleep request to each board)
phase('sleep')
for k in BOARDS: tool.send(BASE[k] + 1, bytes([ps.CMD['Sleep']]) + b'QUIT' + bytes(3))
for k in BOARDS: S['awake'][k] = False
update(lat={g: (0, 400) for g in OUT}); t_z = now_ms(); n_wakes = len(WAKES)
cnt = {'n': 0}
def quiet(f):
    if f.src in BOARDS and f.t / 1000 > t_z + 500: cnt['n'] += 1
bus.watch.append(quiet); run(15000); bus.watch.remove(quiet)
asleep = {k: B[k].flags()['asleep'] for k in BOARDS}
phase_ok('sleep')
check('sleep: all three boards asleep (requests sent back to back), every output off, no board frame on the bus, none woke the others',
      all(asleep.values()) and cnt['n'] == 0 and len(WAKES) == n_wakes, (asleep, cnt['n'], WAKES[n_wakes:]))

# ================================================================== 17. wake (key on, ECU frames)
phase('wake: key on, ECU frames')
S['coolant'] = 85.0; t_w = now_ms(); kp.powered = carn.powered = True; ecu.powered = True
for k in BOARDS: S['awake'][k] = True
sw('ign', 1, lat={g: (0, 900) for g in OUT}); run(4000)
phase_ok('wake: key on, ECU frames')
woke = {k: round(t - t_w, 1) for k, t in WAKES[n_wakes:]}
check('wake: every board wakes on the first CAN frame (CAN RX armed in sleep, MCU reset, starter from FRAM) and its outputs follow the logic again',
      sorted(woke) == sorted(BOARDS) and all(v <= 60 for v in woke.values()) and PIN[7] and PIN[8], woke)

# ================================================================== whole cycle
phase('end')
wd, gap, n = ps.watchdog_summary()
other = {k: [(round(t / 1e6, 3), kind) for t, kind in b.resets if kind not in ('restart', 'wake')] for k, b in B.items()}
check('whole cycle: no watchdog reset, no other MCU reset than the planned restart / wakes, no board in fatal error',
      not wd and not any(other.values()) and not any(b.flags()['fatal'] for b in B.values()), (wd, other, f'longest refresh gap {gap:.0f} ms'))
c = {k: B[k].counters() for k in BOARDS}
check('whole cycle: no CAN receive overrun on any board', all(v['rx_overruns'] == 0 for v in c.values()), {k: (v['rx_overruns'], v['tx_timeouts']) for k, v in c.items()})
check('starter still on every board after sleep / wake (A2 flasher on time, A1 cluster off-delay, B radiator-fan limit read back)',
      tool.read(BASE['A2'], 0x1700, 2) == pget('A2', 'flasher[1].onTime') and tool.read(BASE['A1'], 0x1A00, 4) == pget('A1', 'timer[1].time')
      and tool.read(BASE['B'], 0x1500, 3) == pget('B', 'condition[1].arg'))
# firmware current readings vs the load model, steady loads >= 2 A (on and unchanged for 200 ms)
errs = {}
for j in range(20, len(TRACE)):
    for n_, g in enumerate(OUT):
        im, fw = TRACE[j][3 + n_], TRACE[j][27 + n_]
        if im >= 2.0 and all(abs(TRACE[j - d][3 + n_] - im) <= 0.01 * im for d in range(1, 21)):
            errs[g] = max(errs.get(g, 0.0), abs(fw - im) / im)
check('current readings: every steady load >= 2 A reads within 8 % of the model current (IS chain, kILIS, DSEL)', errs and max(errs.values()) <= 0.08,
      {gname(g): f'{e * 100:.1f} %' for g, e in sorted(errs.items())})
viol = [x for x in VIOL]
info['violations'] = viol[:40]; info['timing'] = TIMES; info['wakes'] = WAKES; info['findings'] = FINDINGS
lat_by = {}
for ph_, nm, v, dt, lo_, hi_ in TIMES: lat_by.setdefault(nm, []).append(dt)
info['latency_ms'] = {k: (min(v), max(v), len(v)) for k, v in lat_by.items()}
info['cycle_s'] = round(now_ms() / 1000, 1)
info['energy_J'] = {k: round(v, 1) for k, v in ENERGY.items()}
info['mean_W'] = {k: round(v / (now_ms() / 1000), 2) for k, v in ENERGY.items()}
info['peak_W_500ms'] = {k: round(v, 2) for k, v in PEAK.items()}

# ------------------------------------------------------------------ outputs: power CSV (thermal job), current trace
os.makedirs(OUT_DIR, exist_ok=True)
hdr = ['t_s', 'phase', 'vbat_V'] + [f'{k}_W' for k in BOARDS] + [f'I{g}_{OUT[g][0]}_OUT{OUT[g][1] + 1}_A' for g in OUT]
with open(os.path.join(OUT_DIR, 's5_board_power.csv'), 'w') as f:
    f.write('# s5_drive_cycle.py: switch conduction loss per board (I^2 x RDS(ON) at TJ = board sensor + 15 K ASSUMED, presim_parts.py 25 / 150 C values) '
            'and mean current per output, each over 500 ms; loads tools/presim_parts.py CAR_LOADS (DUMMY car loads) + s5 ASSUMED; '
            f'run options: {" ".join(a for a in sys.argv[2:] if a in ("--proposals",) or a.startswith("--hot")) or "none"}\n')
    f.write(','.join(hdr) + '\n')
    for r in POW_ROWS: f.write(','.join(str(x) for x in r) + '\n')
with open(os.path.join(OUT_DIR, 's5_current_trace.csv'), 'w') as f:
    f.write(','.join(['t_ms', 'phase', 'vbat_V'] + [f'model_{g}' for g in OUT] + [f'fw_{g}' for g in OUT]) + '\n')
    for r in TRACE: f.write(','.join(str(x) for x in r) + '\n')
json.dump({g: EDGES[g] for g in OUT}, open(os.path.join(OUT_DIR, 's5_edges.json'), 'w'))
print(f'wrote {OUT_DIR}/s5_board_power.csv ({len(POW_ROWS)} rows), s5_current_trace.csv ({len(TRACE)} rows)')
for x in FINDINGS: print('FINDING ' + x)
for g, why in XFAIL_OUT.items():
    v = [x for x in VIOL_X if x[1] == g]
    check(f'{gname(g)} follows the starter logic through the whole cycle', not v, f'{why}; first: {v[:2]}', xfail=True)
bad = [r for r in res if r[1] in ('FAIL', 'XPASS')]; nx = sum(r[1] == 'XFAIL' for r in res)
print(f'S5: {sum(r[1] == "PASS" for r in res)} of {len(res) - nx} checks passed, {nx} XFAIL'); print(json.dumps({k: v for k, v in info.items() if k not in ('timing', 'violations')}))
if '--json' in sys.argv: json.dump(dict(checks=res, info=info), open(arg('--json'), 'w'), indent=1)
sys.exit(0 if not bad else 1)
