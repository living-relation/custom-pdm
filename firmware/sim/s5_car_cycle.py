"""S5 car: a day in the ST185 with the FULL car config on the whole PDM (carsim, Dan 2026-11-23: "pretend I WANT a PDM
now ... simulate it with more loads"). Boards A1, A2 and B (real dingoFW logic, host sim) on one 1 Mbit/s bus with a
dummy Link ECU (its EFI main relay K-EFI output on A1 IN5 and its CAN traffic; the ECU controls and powers its own
loads - pump, EPS, fans, heater, A/C - so it sends the PDM no command, Dan 2026-11-23 07:44), the dummy car traffic
of docs/car-can-dummy/bus-load.dummy.md and the PC tool, with the DUMMY car config
ui/examples/st185-car.dummy.json written by Write All exactly as the app writes it
(firmware/sim/data/st185-car.params.dummy.tsv, made and checked by ui/tests St185CarTests).

Script: parked (auto sleep by itself), key on (wake on the ignition input), ECU boot, crank (6 V dip), idle, power
windows, tail / head / high / flash, DRL with the pods up, pop-ups up and down (the motors and their limit contacts
modelled), turn signals and hazard, horn, stop lamps, back-up lamps, wipers with the park cam + washer wipes, rear
defogger (push on / push off), night rain with every load on (current export for the thermal model), the ECU's CAN
silent while driving (nothing on the PDM changes), low battery with the engine off (defogger shed after 30 s, nothing
ECU-held), key off with the ECU's after-run hold (a low battery during the hold: nothing shed, no mute, no sleep), ECU
release (no fault, every output off), auto sleep, parking lights and hazards with the key off (wake on the tail /
hazard switch), sleep again.

Ground truth: every PROFET IN pin of the 24 outputs, every 1 ms, against an independent logic model written from the
car map's own words (docs/st185-car-config.dummy.md, the /pdm trigger texts in St185CarTests) - not from the firmware.
A pin may differ from the model only inside the latency window of a change; every change is timed. The pop-up motors
and the wiper are checked by their mechanical models (position, limit contacts, park cam).

usage: python3 firmware/sim/s5_car_cycle.py <sim out dir> [--out dir] [--json file] [--mutate N] [--mutants]
(exit 1 on any FAIL). --mutants runs every one-line config mutation in MUTATIONS (each must turn RED)."""
import json, math, os, random, re, struct, subprocess, sys, shutil, tempfile, zlib

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default
SO = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith('--') else '/tmp/simout'
import pdmsim as ps
sys.path.insert(0, os.path.join(REPO, 'tools'))
import presim_parts as PP

OUT_DIR = arg('--out', os.path.join(SO, 's5car'))
MUTATE = int(arg('--mutate', '-1'))
SLEEP_TIMEOUT_MS = 30000                                   # firmware/boards/custompdm_*/port.h SLEEP_TIMEOUT
MUTE_MS = 10000                                            # ui PdmKeyOff.MuteDelayMs
SHED_ON, SHED_OFF, SHED_MS = 11.8, 12.8, 30000             # St185Car.ShedOnV / ShedOffV / ShedDelayMs
res, info = [], {}
def check(name, ok, detail='', xfail=False):
    ok = bool(ok); tag = ('XPASS' if ok else 'XFAIL') if xfail else ('PASS' if ok else 'FAIL')
    res.append((name, tag, str(detail))); print(f'{tag} {name}' + (' : ' + str(detail) if detail != '' else ''), flush=True)

# ------------------------------------------------------------------ the car config as the app writes it
def load_params():
    P = {'A1': [], 'A2': [], 'B': []}
    for ln in open(os.path.join(HERE, 'data', 'st185-car.params.dummy.tsv'), encoding='utf-8'):
        if ln.startswith('#') or not ln.strip(): continue
        role, ix, sub, hx, name = ln.rstrip('\n').split('\t')
        P[role].append([int(ix, 16), int(sub), bytes.fromhex(hx), name])
    return P
PARAMS = load_params()
def u32(b): return struct.unpack('<I', b)[0]
def pset(role, name, value):
    for p in PARAMS[role]:
        if p[3] == name: p[2] = struct.pack('<I', value & 0xFFFFFFFF); return
    raise KeyError(f'{role} {name}')
def pget(role, name): return next(u32(p[2]) for p in PARAMS[role] if p[3] == name)
def pfind(role, pattern, value):
    """the first param of role whose name matches pattern and whose value is value"""
    for p in PARAMS[role]:
        if re.fullmatch(pattern, p[3]) and u32(p[2]) == value: return p[3]
    raise KeyError(f'{role} {pattern} = {value}')
def sibling(name, field): return re.sub(r'\.[A-Za-z0-9]+$', '.' + field, name)

# mutations: one config value each, every one must turn the run RED (found by value, so a config change cannot move them)
def _mut():
    shed_c = pfind('B', r'condition\[\d+\]\.arg', ps.f32(SHED_ON))
    shed_t = pfind('B', r'timer\[\d+\]\.time', SHED_MS)
    return [
        ('B', shed_c, ps.f32(10.5), 'battery shed at 10.5 V, not 11.8 V'),
        ('B', shed_t, 500, 'battery shed after 0.5 s (a crank dip sheds)'),
        ('B', 'input[10].invert', 1, 'reverse switch inverted (back-up lamps on in every gear)'),
        ('B', 'output[1].input', 1, 'power windows always on (not with the key)'),
        ('A1', 'output[7].input', 1, 'CSB3 always on (does not follow the EFI main relay)'),
        ('A2', 'input[4].invert', 0, 'pop-up LH top limit contact not inverted'),
        ('A2', pfind('A2', r'flasher\[\d+\]\.onTime', 350), 500, 'turn signal on time 350 -> 500 ms'),
        ('A1', 'device.muteCanTxInput', 1, 'A1 mutes its CAN TX whatever the key / ECU hold'),
        ('B', 'wiper.parkStopLevel', 0, 'wiper park level inverted'),
        ('A1', 'input[6].invert', 1, 'brake switch inverted (stop lamps on without the pedal)'),
        ('B', 'input[8].mode', 0, 'defogger switch momentary (no push on / push off)'),
        ('A1', 'customPdm.wakeInputMask', 0, 'A1 wakes on no input (parking lights dead with the key off)'),
        ('B', sibling(shed_c, 'operator'), 4, 'shed condition >= instead of <='),
    ]
MUTATIONS = _mut()
if MUTATE >= 0:
    r_, n_, v_, why = MUTATIONS[MUTATE]; pset(r_, n_, v_); print(f'MUTATION {MUTATE}: {r_} {n_} = {v_} ({why})')

if '--mutants' in sys.argv:
    from concurrent.futures import ThreadPoolExecutor
    def one(k):
        d = tempfile.mkdtemp(prefix=f's5car{k}_')
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
        red += bool(rc != 0 and fails)
        print(f"{'RED  ' if rc and fails else 'GREEN'} mutant {k}: {MUTATIONS[k][3]} ({len(fails)} FAIL)" + (f": {fails[0][5:140]}" if fails else ''))
    print(f'S5 car mutants: {red} of {len(MUTATIONS)} RED')
    sys.exit(0 if red == len(MUTATIONS) else 1)

# ------------------------------------------------------------------ outputs and loads
BOARDS = ('A1', 'A2', 'B')
OUT = {g: (BOARDS[(g - 1) // 8], (g - 1) % 8) for g in range(1, 25)}
# name, steady A at 13.5 V, inrush x, inrush s, kind, (L low, L high) H. Sources: tools/presim_parts.py CAR_LOADS where it
# has the load (marked C), else ASSUMED from the st185 fuse (steady <= 0.75 x fuse) and typical lamp / motor data (A).
LOADS = {
    1: ('Low beams (LED) C', 2.0, 3.0, 0.01, 'electronic', (0, 0)), 2: ('High beams + dash LED C', 2.5, 3.0, 0.01, 'electronic', (0, 0)),
    3: ('DRLs A (A34 0.5 A)', 0.5, 3.0, 0.005, 'electronic', (0, 0)),
    4: ('Stop lamps A (2 x 21 W + 18 W halogen)', 4.4, 8.0, 0.02, 'lamp', (0, 0)),
    5: ('Horn pair C', 5.0, 1.0, 0.0, 'coil', (5e-3, 30e-3)),
    7: ('CSB3 A', 2.0, 3.0, 0.01, 'electronic', (0, 0)), 8: ('Centre cluster A', 1.5, 3.0, 0.01, 'electronic', (0, 0)),
    9: ('Turn L A (2 x 21 W + LED lead)', 3.3, 8.0, 0.02, 'lamp', (0, 0)), 11: ('Turn R A', 3.3, 8.0, 0.02, 'lamp', (0, 0)),
    12: ('Pop-up motor LH A', 5.0, 4.0, 0.3, 'motor', (0.3e-3, 1.0e-3)), 13: ('Pop-up motor RH A', 5.0, 4.0, 0.3, 'motor', (0.3e-3, 1.0e-3)),
    14: ('Tail / park front A (2 x 5 W + 2 x 3.8 W)', 1.3, 8.0, 0.02, 'lamp', (0, 0)),
    15: ('Tail / licence / dash A (about 47 W)', 3.5, 8.0, 0.02, 'lamp', (0, 0)),
    16: ('Washer pump C', 3.0, 4.0, 0.2, 'motor', (0.2e-3, 1.0e-3)),
    17: ('Power windows A (one window moving 10 A; switches 0.05 A)', 10.0, 2.0, 0.3, 'motor', (0.3e-3, 1.0e-3)),
    20: ('Rear defogger A (about 200 W grid)', 15.0, 1.3, 1.0, 'lamp', (0, 0)),
    21: ('CAN-Lambda C', 8.1, 1.5, 0.1, 'electronic', (0, 1e-6)), 22: ('Back-up lamps A (2 x 21 W)', 3.2, 8.0, 0.02, 'lamp', (0, 0)),
    23: ('Wiper motor C', 6.0, 4.0, 0.3, 'motor', (0.3e-3, 1.5e-3)),
}
LOADS[24] = LOADS[23]
NAME = {g: LOADS[g][0].rsplit(' ', 1)[0] if LOADS.get(g) else '' for g in OUT}; NAME[10] = 'box fan'
def gname(g): k, o = OUT[g]; return f'{k} OUT{o + 1} {NAME.get(g, "")}'
V_NOM = 13.5
class Load:
    """motor / lamp: steady x (1 + (k-1) e^(-3 t / t_inrush)) from switch-on (a lamp's cold filament the same way, ASSUMED);
    electronic: k x steady for t_inrush; coil: steady x (1 - e^(-t / tau)), tau = L x steady / 13.5 V. x battery / 13.5 V."""
    def __init__(s, spec):
        s.name, s.i, s.k, s.t, s.kind, (l0, l1) = spec; s.L = (l0 + l1) / 2; s.t_on = None; s.t_off = -1e9; s.on = False
    def current(s, on, t, vbat):
        if not on:
            if s.on: s.t_off = t; s.on = False
            if s.t_on is not None and t - s.t_off > 0.2: s.t_on = None
            return 0.0
        s.on = True
        if s.t_on is None: s.t_on = t
        dt = t - s.t_on; sc = vbat / V_NOM
        if s.kind in ('motor', 'lamp'): return s.i * (1 + (s.k - 1) * math.exp(-3 * dt / max(s.t, 1e-3))) * sc
        if s.kind == 'coil': tau = s.L * s.i / V_NOM; return s.i * (1 - math.exp(-dt / tau)) * sc if tau > 0 else s.i * sc
        return s.i * (s.k if dt < s.t else 1.0) * sc
RDS = {dn: (d['rds25'], d['rds150']) for dn, d in PP.PROFET.items()}
def rds(driver, board_c):
    r25, r150 = RDS[driver]; tj = board_c + 15.0                 # TJ = board sensor + 15 K (ASSUMED, as s5)
    return r25 + (r150 - r25) * (tj - 25.0) / 125.0
DRIVER = {g: (ps.BOARD_A if OUT[g][0] != 'B' else ps.BOARD_B)['outputs'][OUT[g][1]][5] for g in OUT}

# ------------------------------------------------------------------ bus: boards, PC tool, ECU, car traffic
random.seed(20261123)
bus = ps.Bus(); tool = ps.Tool(bus)
B = {'A1': ps.Board(ps.BOARD_A, 'A1', SO, unit=1), 'A2': ps.Board(ps.BOARD_A, 'A2', SO, unit=2), 'B': ps.Board(ps.BOARD_B, 'B', SO)}
BASE = {'A1': 0x500, 'A2': 0x540, 'B': 0x580}
for b in B.values(): b.set_vbat(12.6); b.set_temp(25.0, 28.0)
carn = ps.PyNode('car'); carn.powered = False
S = dict(ign=0, efi=0, win=0, rev=0, light='off', flash=0, high=0, drl=0, horn=0, brake=0, turnL=0, turnR=0,
         hazard=0, wlo=0, whi=0, wint=0, wash=0, defog_sw=0, defog=0, vbat=12.6, shed=False, wiper=False, tail_seen=0,
         awake={k: True for k in BOARDS}, temp={k: 25.0 for k in BOARDS}, boxfan=0)
rows = []
for ln in open(os.path.join(REPO, 'docs', 'car-can-dummy', 'bus-load.dummy.md'), encoding='utf-8'):
    m = re.match(r'\| (0x[0-9A-Fa-f]{3})\s*\| ([^|]+)\| (\d) \| ([\d.]+) \| ([\d.]+) \|', ln)
    if m and float(m.group(5)) > 0:
        rows.append((int(m.group(1), 16), int(m.group(3)), float(m.group(5))))
for i_, d_, fps in rows:
    carn.every(int(1e6 / fps), (lambda i, d: lambda t: carn.send(i, bytes(d)))(i_, d_), start=random.randint(0, int(1e6 / fps)))
info['dummy_car_frames'] = len(rows)
wake_req = set(); LAST_TX = {}; FAULTS = []
stat = {k: ps.Status(BASE[k]) for k in B}
def on_frame(f):
    LAST_TX[f.src] = f.t / 1000.0
    for k, b in B.items():
        if k != f.src and b.connected and b.flags()['asleep']: wake_req.add(k)
    for k in BOARDS:                                               # every output state any board reports (msg 3)
        if f.id == BASE[k] + 2 + 3:
            for i in range(8):
                st = (f.data[i // 2] >> (4 * (i % 2))) & 15
                if st in (2, 3): FAULTS.append((round(f.t / 1000.0), PHASE[0], k, i + 1, ps.STATE[st]))
bus.watch.append(on_frame)
for s_ in stat.values(): bus.watch.append(s_.feed)
bus.add(tool, carn, *B.values())

# ------------------------------------------------------------------ inputs: the wires (PDM input number -> board, index)
def where(n): return ('A1', n - 1) if n <= 7 else ('A2', n - 8) if n <= 14 else ('B', n - 15)
GND_ACTIVE = {1, 2, 3, 4, 7, 8, 9, 10, 11, 12, 13, 14, 15, 17, 18, 19, 21, 22, 23}   # IN24 reverse, IN20 cam, IN5 / 6 / 16: 12 V
WAKE = {2, 5, 6, 7, 9, 16}                                         # St185Car.Switches Wake
LEVEL = {}
def wire(n, on):
    """switch n on / off: a ground-switched input goes to ground (open = the input-board DIP pull-up), a 12 V one to 12 V
    (off = the DIP pull-down / MCU pull-down). A board asleep with n in its wake set wakes on the edge (EXTI = MCU reset)."""
    k, i = where(n)
    if n in GND_ACTIVE: B[k].set_input(i, 'gnd' if on else 'open', 'up')
    else: B[k].set_input(i, '12v' if on else 'open', 'down')
    # wake only where the FIRMWARE armed the input's EXTI line before STOP (sim EXTI model, pdmsim.exti_lines): the
    # car map's wake set (WAKE) is what the logic model expects, the firmware's wake mask is what is checked
    if LEVEL.get(n) != bool(on) and B[k].flags()['asleep'] and B[k].model['inputs'][i][0] in ps.exti_lines(B[k]).values(): wake_req.add(k)
    LEVEL[n] = bool(on)

# ------------------------------------------------------------------ mechanical models: pop-up motors, wiper
class Pod:
    """A one-way crank motor: half a turn (1.0 s, ASSUMED) from bottom (0.0) to top (0.5) and on to bottom (1.0 = 0).
    Its limit contacts close to ground at the top (0.47-0.53) and at the bottom (0.97-0.03) (TO CHECK on the bench)."""
    HALF_S = 1.0
    def __init__(s, g, top, bottom): s.g, s.top, s.bottom = g, top, bottom; s.pos = 0.0; s.runs = []; s.was = False
    def at_top(s): return 0.47 <= s.pos % 1.0 <= 0.53
    def at_bottom(s): p = s.pos % 1.0; return p <= 0.03 or p >= 0.97
    def step(s, on, t):
        if on: s.pos += 0.5 / (s.HALF_S * 1000.0)
        if on and not s.was: s.runs.append([t, None])
        if not on and s.was and s.runs: s.runs[-1][1] = t
        s.was = on
        wire(s.top, s.at_top()); wire(s.bottom, s.at_bottom())
PODS = [Pod(12, 11, 12), Pod(13, 13, 14)]
class Wiper:
    """Wiper motor + park cam (s3 F8): one turn 1.0 s slow / 0.6 s fast; cam 12 V on B IN6 (IN20) for the first 10 %."""
    def __init__(s): s.pos = 0.02; s.turns = 0; s.starts = []; s.was_on = False
    def step(s, slow, fast, t):
        on = slow or fast
        if on:
            p = s.pos + 1.0 / (600.0 if fast else 1000.0)
            if int(p) > int(s.pos): s.turns += 1
            s.pos = p
        if on and not s.was_on: s.starts.append(t)
        s.was_on = on
        wire(20, (s.pos % 1.0) < 0.10)
    def parked(s): return (s.pos % 1.0) < 0.10
WIP = Wiper()
LD = {g: Load(LOADS[g]) for g in LOADS if g != 24}
PIN = {g: 0 for g in OUT}; EDGES = {g: [] for g in OUT}; IMOD = {g: 0.0 for g in OUT}; OHMS = {}
def now_ms(): return bus.now / 1000.0
def read_pins():
    for g, (k, o) in OUT.items():
        b = B[k]; v = b.level(b.model['outputs'][o][0]) if b.powered else 0
        if v != PIN[g]: EDGES[g].append((now_ms(), v)); PIN[g] = v
def set_ohms(g, ohms):
    k, o = OUT[g]
    if OHMS.get(g) is None or abs(OHMS[g] - ohms) > 0.003 * max(ohms, 1e-6): OHMS[g] = ohms; B[k].set_load(o, ohms)
def update_loads():
    t = now_ms() / 1000.0; vb = S['vbat']
    for g, ld in LD.items():
        if g == 23:
            on = PIN[23] or PIN[24]; i = ld.current(on, t, vb)
            IMOD[23], IMOD[24] = ((0.2 * vb / V_NOM if PIN[23] else 0.0), i) if PIN[24] else (i, 0.0)
            for gg in (23, 24): set_ohms(gg, vb / IMOD[gg] if IMOD[gg] > 1e-3 else vb / (ld.i * ld.k * vb / V_NOM))
            continue
        if g == 17:                               # power windows: the switches 0.05 A, a window motor only while one moves
            i = ld.current(PIN[17] and S['win'], t, vb) + (0.05 * vb / V_NOM if PIN[17] else 0.0); IMOD[17] = i
            set_ohms(17, vb / i if i > 1e-3 else vb / 0.05); continue
        i = ld.current(PIN[g], t, vb); IMOD[g] = i
        if i > 1e-3: set_ohms(g, vb / i)
        else: set_ohms(g, vb / max(ld.i * (ld.k if ld.kind != 'coil' else 0.05) * vb / V_NOM, 1e-3))

# ------------------------------------------------------------------ the independent logic model (the car map's words)
def heard(dst, src): return S['awake'][dst] and S['awake'][src] and not MUTED.get(src)
def head(): return S['light'] == 'head' or S['flash']                 # R-Y: light switch HEAD or dimmer FLASH
def tail(): return S['light'] in ('tail', 'head')
def hi(): return (S['high'] and S['light'] == 'head') or S['flash']   # R-W: dimmer HIGH (with HEAD) or FLASH
def logic():
    E = {g: 0 for g in OUT}
    E[12] = E[13] = 'free'                                              # pop-ups: the motor model checks them
    a1, a2, b = S['awake']['A1'], S['awake']['A2'], S['awake']['B']
    if a1:
        E[1] = int(head())                                              # IN1
        E[2] = int(hi() and head())                                     # IN2 AND IN1
        E[3] = int(S['drl'] and S['efi'] and not head())                # IN3 AND IN5 AND NOT IN1 (DRL off with the head lamps)
        E[4] = int(S['brake'])                                          # IN6
        E[5] = int(S['horn'])                                           # IN4
        E[7] = E[8] = int(S['efi'])                                     # IN5: the EFI main relay (Bus 2)
    if a2:
        E[9] = 'flash' if (S['turnL'] or S['hazard']) else 0
        E[11] = 'flash' if (S['turnR'] or S['hazard']) else 0
        if heard('A2', 'A1'): S['tail_seen'] = int(tail())                # lamps hold their last state at link loss
        E[14] = E[15] = S['tail_seen']
        E[16] = int(S['wash']) if heard('A2', 'B') else 0               # IN21 over CAN, off at loss
        if S['temp']['A2'] < 40: E[10] = 0
    if b:
        E[17] = int(S['ign'])                                           # IN16: power windows (as the power main relay)
        E[20] = int(S['defog'] and S['ign'] and not S['shed'])          # IN22 (latched) AND IN16 AND NOT shed
        E[21] = int(S['ign'])                                           # IN16
        E[22] = int(S['rev'])                                           # IN24: back-up lamps
        E[23] = E[24] = 'free' if S['wiper'] else 0
    return E
MUTED = {}
LAT = {g: (15, 32, 0) for g in OUT}                                     # a wire input: 20 ms debounce, 2 ms loop
LAT.update({14: (15, 140, 0), 15: (15, 140, 0), 16: (15, 140, 0), 10: (0, 450, 0)})   # over CAN (msg 37, 100 ms)
EXP = {g: dict(v=0, t=0.0, lo=0, hi=0, grace=0, pend=False, hit=0.0, old=0) for g in OUT}
VIOL = []; TIMES = []; PHASE = ['boot']; PH_T = {}; MISMATCH = {}
def expect(g, v, lo, hi_, grace=0):
    e = EXP[g]
    if e['v'] == v and not e['pend']: return
    if e['pend'] and e['v'] == v: return
    if e['pend'] and v == e['old']: e.update(v=v, pend=False, hit=now_ms()); return
    e.update(old=e['v'], v=v, t=now_ms(), lo=lo, hi=hi_, grace=grace, pend=v not in ('flash', 'free') and e['v'] != v, hit=now_ms())
def update(lat=None):
    E = logic()
    for g, v in E.items():
        lo, hi_, gr = (tuple((lat or {}).get(g, LAT[g])) + (LAT[g][2],))[:3]
        expect(g, v, lo, hi_, gr)
def check_pins():
    t = now_ms()
    for g, e in EXP.items():
        v = e['v']
        if v in ('flash', 'free'): continue
        p = PIN[g]
        if e['pend']:
            if p == v:
                dt = t - e['t']
                if dt < e['lo'] - 1e-6: VIOL.append((PHASE[0], g, 'early', round(dt, 1), f"{e['old']}->{v} window {e['lo']}..{e['hi']} ms"))
                TIMES.append((PHASE[0], gname(g), v, round(dt, 1))); e['pend'] = False; e['hit'] = t
            elif t - e['t'] > e['hi']:
                VIOL.append((PHASE[0], g, 'late', round(t - e['t'], 1), f"{e['old']}->{v} window {e['lo']}..{e['hi']} ms")); e['pend'] = False; e['hit'] = t
            continue
        if t < e['hit'] + e['grace']: continue
        if p != v:
            k = (PHASE[0], g); MISMATCH[k] = MISMATCH.get(k, 0) + 1
            if MISMATCH[k] == 1: VIOL.append((PHASE[0], g, 'wrong', round(t, 1), f'pin {p}, logic {v}'))

# ------------------------------------------------------------------ time
POW_ROWS = []; TRACE = []; _acc = {'E': {k: 0.0 for k in BOARDS}, 'I': {g: 0.0 for g in OUT}, 'n': 0}
ENERGY = {k: 0.0 for k in BOARDS}; PEAK = {k: 0.0 for k in BOARDS}; WAKES = []; ASLEEP_AT = {}; RMS = {}
def wake(k):
    b = B[k]; fram, opt = b.fram(), b.L.sim_opt_get(); held = b.board_c
    b.resets.append((bus.now, 'wake')); b.t0 = bus.now; b._load(fram, opt, ps.RSTF_SFT); b.mcp_carry(held)
    S['awake'][k] = True; MUTED.pop(k, None)
    if k == 'A2': S['tail_seen'] = 0                                  # a link-held lamp is off at power-up
def tick():
    bus.run_for(1); t = now_ms()
    for k in BOARDS + ('car',):                                  # bus wake-up: a frame nobody acknowledges still puts dominant
        if (carn.powered and carn.tx_peek() is not None) if k == 'car' else (S['awake'][k] and B[k].tx_peek() is not None):          # bits (and error frames) on the bus; the MCP2562FD of a board
            for j in BOARDS:                                      # in standby wakes on that bus activity (wake-up pattern, DS20005284A)
                if j != k and B[j].flags()['asleep']: wake_req.add(j)
    for k in list(wake_req):
        wake_req.discard(k)
        if B[k].flags()['asleep']: wake(k); WAKES.append((k, t)); ASLEEP_AT.pop(k, None); update(lat={g: (0, 900) for g in OUT})
    for k in BOARDS:
        if S['awake'][k] and k not in ASLEEP_AT and B[k].flags()['asleep']: ASLEEP_AT[k] = t; S['awake'][k] = False; update()
        muted = S['awake'][k] and t - LAST_TX.get(k, t) > 300
        if muted != bool(MUTED.get(k)):
            MUTED[k] = muted; update(lat={g: (0, 1200) for g in OUT})
    read_pins()
    for p in PODS: p.step(PIN[p.g], t)
    WIP.step(PIN[23], PIN[24], t)
    update_loads()
    check_pins()
    for g, (k, o) in OUT.items():
        i = IMOD[g] if PIN[g] else 0.0
        if i:
            pw = i * i * rds(DRIVER[g], B[k].board_c); _acc['E'][k] += pw * 1e-3; ENERGY[k] += pw * 1e-3
        _acc['I'][g] += i
        if 'rms' in RMS: RMS['rms'][g] += i * i
    if 'rms' in RMS: RMS['n'] += 1
    _acc['n'] += 1
    if _acc['n'] >= 500:
        POW_ROWS.append([round(t / 1000, 3), PHASE[0].replace(',', ';'), round(S['vbat'], 2)] + [round(_acc['E'][k] / 0.5, 3) for k in BOARDS] +
                        [round(_acc['I'][g] / _acc['n'], 3) for g in OUT])
        for k in BOARDS: PEAK[k] = max(PEAK[k], _acc['E'][k] / 0.5)
        _acc.update(E={k: 0.0 for k in BOARDS}, I={g: 0.0 for g in OUT}, n=0)
    if int(t) % 10 == 0:
        TRACE.append([round(t, 1), PHASE[0].replace(',', ';'), round(S['vbat'], 2)] + [round(IMOD[g] if PIN[g] else 0.0, 3) for g in OUT] +
                     [round(B[k].L.sim_out_current(o), 3) for g, (k, o) in OUT.items()])
def run(ms):
    for _ in range(int(ms)): tick()
def phase(name): PHASE[0] = name; PH_T[name] = now_ms(); print(f'--- {name} (t = {now_ms() / 1000:.1f} s)', flush=True)
def phase_ok(name, extra=''):
    v = [x for x in VIOL if x[0] == name]
    check(f'{name}: all 24 output pins match the logic model every 1 ms, every change inside its window', not v, (v[:4] if v else '') or extra)
def edges_in(g, t0, t1): return [(t, v) for t, v in EDGES[g] if t0 <= t <= t1]
def spans(g, t0, t1, level=1):
    out = []; st = None
    for t, v in edges_in(g, t0, t1):
        if v == level: st = t
        elif st is not None: out.append(round(t - st, 1)); st = None
    return out
def sw(name, val, lat=None):
    S[name] = val
    n = dict(drl=3, horn=4, brake=6, turnL=8, hazard=9, turnR=10, wlo=17, whi=18, wint=19, wash=21, defog_sw=22, rev=24).get(name)
    if n: wire(n, val)
    if name == 'defog_sw' and val: S['defog'] = 1 - S['defog']       # push on / push off (latched input)
    update(lat)
def light(pos=None, flash=None, high=None, lat=None):
    """the light control switch (OFF / TAIL / HEAD) and the dimmer (HIGH, FLASH): R-Y = HEAD or FLASH, R-W = HIGH (at HEAD) or FLASH"""
    if pos is not None: S['light'] = pos
    if flash is not None: S['flash'] = flash
    if high is not None: S['high'] = high
    wire(1, head()); wire(2, hi()); wire(7, tail()); wire(23, S['light'] == 'off')
    update(lat)
def set_vbat(v):
    S['vbat'] = v
    for b in B.values(): b.set_vbat(v)
def ecu_power(on):
    """the Link ECU: K-EFI (its own main relay on Aux 6, A1 IN5 reads its output) and the car's CAN traffic, together"""
    S['efi'] = on; wire(5, on); carn.powered = bool(on); update()
def pods_at(where_):
    return all((p.at_top() if where_ == 'top' else p.at_bottom()) for p in PODS) and not PIN[12] and not PIN[13]

# ================================================================== 0. the car config onto three fresh boards
phase('load the ST185 car config (Write All + Burn, as the app)')
bus.run_for(1500)
wa = {}
for k in BOARDS:
    r = tool.read_all(BASE[k], ms=20000)
    order = [(ix, sub) for ix, sub, _ in r[0]] if r else []
    dump = {(ix, sub): bv for ix, sub, bv, _ in PARAMS[k]}
    same = sorted(order) == sorted(dump) and len(order) == len(PARAMS[k])
    vals = [(ix, sub, u32(dump[(ix, sub)])) for ix, sub in order if (ix, sub) in dump]
    crc = zlib.crc32(b''.join(dump[(ix, sub)] for ix, sub in order if (ix, sub) in dump)) & 0xFFFFFFFF
    ok = same and tool.write_all(BASE[k], vals, crc); burned = ok and tool.burn(BASE[k])
    back = tool.read_all(BASE[k], ms=20000)
    wa[k] = (len(order), same, ok, burned, bool(back) and [v for _, _, v in back[0]] == [v for _, _, v in vals])
check("car config: each board's own param table is exactly the app's file; Write All applied, burned, Read All gives it back",
      all(v[1:] == (True, True, True, True) for v in wa.values()), wa)
for k, b in B.items():
    fr, opt = b.fram(), b.L.sim_opt_get(); b.resets.append((bus.now, 'restart')); b.t0 = bus.now; b._load(fr, opt, ps.RSTF_POR | ps.RSTF_BOR)
tool.powered = False                                               # the PC goes away: nothing else on the bus
for n in range(1, 25): wire(n, False)
light('off')
for p in PODS: p.step(False, 0)

# ================================================================== 1. parked: auto sleep by itself
phase('parked, key off: auto sleep')
read_pins(); update(); t_p = now_ms(); run(MUTE_MS + SLEEP_TIMEOUT_MS + 3000)
phase_ok('parked, key off: auto sleep')
check('parked: every board mutes 10 s after start (IN5, IN7, IN9 off) and sleeps 30 s after the bus went quiet, no output on',
      sorted(ASLEEP_AT) == list(BOARDS) and all(MUTE_MS + SLEEP_TIMEOUT_MS - 500 <= v - t_p <= MUTE_MS + SLEEP_TIMEOUT_MS + 1500 for v in ASLEEP_AT.values())
      and not any(PIN.values()), {k: round((v - t_p) / 1000, 2) for k, v in ASLEEP_AT.items()})

# ================================================================== 2. key on: wake, ECU boot, prime
phase('key on: wake, ECU boot')
t_k = now_ms(); n_w = len(WAKES); S['ign'] = 1; wire(16, 1); update(lat={g: (0, 900) for g in OUT}); run(150)
ecu_power(1); run(3000)
phase_ok('key on: wake, ECU boot')
woke = {k: round(t - t_k, 1) for k, t in WAKES[n_w:]}
check('key on: B wakes on its ignition input (wake set), A1 / A2 on the bus activity or their own wake input (<= 0.6 s); CAN-Lambda, windows, CSB3 and cluster on',
      sorted(woke) == sorted(BOARDS) and woke.get('B', 99) <= 5 and all(v <= 600 for v in woke.values()) and PIN[21] and PIN[17] and PIN[7] and PIN[8], woke)

# ================================================================== 3. crank
phase('crank (6 V dip)')
r0 = {k: len(b.resets) for k, b in B.items()}
run(100)
set_vbat(6.0); update(); run(80); set_vbat(9.6); update(); run(1200); set_vbat(14.2); update(); run(2500)
phase_ok('crank (6 V dip)')
check('crank: no MCU reset on any board (6.0 V 80 ms, 9.6 V 1.2 s), nothing switches, no shed', all(len(b.resets) == r0[k] for k, b in B.items()) and not S['shed'],
      {k: b.resets[r0[k]:] for k, b in B.items()})

# ================================================================== 4. idle, EPS enable
phase('idle: power windows, back-up lamps')
S['win'] = 1; update(); run(2500); S['win'] = 0; update(); sw('rev', 1); run(800); sw('rev', 0); run(500)
phase_ok('idle: power windows, back-up lamps')

# ================================================================== 5. lights and pop-ups
phase('lights and pop-ups')
PT = {}
def pods_wait(where_, ms=2500):
    t0 = now_ms()
    for _ in range(ms):
        tick()
        if pods_at(where_): break
    return round(now_ms() - t0)
light('tail'); run(500)
PT['tail: pods stay down'] = pods_at('bottom')
sw('drl', 1); PT['DRL + key: pods up ms'] = pods_wait('top'); run(300)
PT['DRLs on with the pods up'] = bool(PIN[3])
light('head'); run(500); PT['head: low on, DRL off'] = bool(PIN[1]) and not PIN[3] and pods_at('top')
light(high=1); run(500); light(high=0); run(300)
light('off'); run(1500); PT['OFF with DRL on: pods stay up'] = pods_at('top')
sw('drl', 0); PT['OFF, DRL off: pods down ms'] = pods_wait('bottom'); run(300)
light(flash=1); PT['flash at OFF: pods up ms'] = pods_wait('top'); run(300); light(flash=0); PT['flash released: down ms'] = pods_wait('bottom'); run(500)
phase_ok('lights and pop-ups')
runs = [(round(b_ - a_)) for p in PODS for a_, b_ in p.runs if b_]
check('pop-ups: up on DRL + key and on head / flash, down at OFF only when nothing asks up; each motor stops at its own limit contact '
      '(half turn 1.0 s + up to 40 ms), both in step', PT['tail: pods stay down'] and PT['DRLs on with the pods up'] and PT['head: low on, DRL off']
      and PT['OFF with DRL on: pods stay up'] and all(900 <= x <= 1060 for x in runs) and all(v <= 1200 for k, v in PT.items() if k.endswith('ms')),
      dict(PT, runs_ms=runs))

# ================================================================== 6. turn signals, hazard
phase('turn signals + hazard')
FL = {}
for name, gs in (('turnL', (9,)), ('turnR', (11,)), ('hazard', (9, 11))):
    t0 = now_ms(); sw(name, 1); run(3000); t1 = now_ms(); sw(name, 0, lat={9: (0, 40), 11: (0, 40)}); run(800)
    FL[name] = {g: dict(first=round(edges_in(g, t0, t1)[0][0] - t0, 1) if edges_in(g, t0, t1) else None, on=spans(g, t0, t1, 1), off=spans(g, t0, t1, 0)) for g in gs}
phase_ok('turn signals + hazard')
check('turn signals: first flash <= 32 ms, then 350 / 350 ms (+-5 ms); hazard both sides',
      all(f['first'] is not None and f['first'] <= 32 and len(f['on']) >= 4 and all(abs(x - 350) <= 5 for x in f['on'][:-1] + f['off'][:-1])
          for n in FL for f in FL[n].values()), {n: {g: (f['first'], sorted(set(f['on']))) for g, f in FL[n].items()} for n in FL})

# ================================================================== 7. horn, stop lamps
phase('horn + stop lamps'); sw('horn', 1); run(400); sw('horn', 0); run(300); sw('brake', 1); run(600); sw('brake', 0); run(300); phase_ok('horn + stop lamps')

# ================================================================== 8. wipers + washer
phase('wipers + washer')
WP = {}
def wipe(name, ms):
    S['wiper'] = True; update(); turns0 = WIP.turns; t0 = now_ms(); sw(name, 1); run(ms); t1 = now_ms(); sw(name, 0)
    for _ in range(3000):
        tick()
        if not PIN[23] and not PIN[24] and WIP.parked(): break
    run(300); WP[name] = dict(turns=WIP.turns - turns0, parked=WIP.parked() and not PIN[23] and not PIN[24], starts=[round(t - t0) for t in WIP.starts if t >= t0])
    S['wiper'] = False; update(lat={23: (0, 5), 24: (0, 5)})
wipe('wlo', 3300); wipe('whi', 2000); wipe('wint', 9500)
S['wiper'] = True; update(); tw = WIP.turns; sw('wash', 1); run(600); sw('wash', 0)
for _ in range(6000):
    tick()
    if not PIN[23] and WIP.parked() and now_ms() > PH_T['wipers + washer'] + 1000: break
run(300); wash_turns = WIP.turns - tw; S['wiper'] = False; update(lat={23: (0, 5), 24: (0, 5)})
phase_ok('wipers + washer')
gaps = [b_ - a_ for a_, b_ in zip(WP['wint']['starts'], WP['wint']['starts'][1:])]
check('wipers: LO about 3 turns, HI about 3 turns, INT one wipe every 4.0 s; each parks in the cam zone; washer: pump on its switch (A2 over CAN) and 3 wipes',
      WP['wlo']['turns'] in (3, 4) and WP['whi']['turns'] in (3, 4) and all(w['parked'] for w in WP.values()) and len(gaps) >= 2
      and all(3850 <= g_ <= 4150 for g_ in gaps) and wash_turns in (3, 4), dict({k: (v['turns'], v['parked']) for k, v in WP.items()}, int_gaps=gaps, wash_turns=wash_turns))

# ================================================================== 9. rear defogger, A/C clutch, ECU fans
phase('rear defogger')
sw('defog_sw', 1); run(200); sw('defog_sw', 0); run(1500); on_d = PIN[20]
sw('defog_sw', 1); run(200); sw('defog_sw', 0); run(500); off_d = not PIN[20]
phase_ok('rear defogger')
check('rear defogger: one push on, the next push off (latched input)', on_d and off_d)

# ================================================================== 10. night rain: every load on (current export for the thermal model)
phase('night rain, everything on')
light('head'); sw('defog_sw', 1); run(200); sw('defog_sw', 0); sw('brake', 1); S['win'] = 1
S['wiper'] = True; sw('whi', 1); update(); run(3000)
RMS.update(rms={g: 0.0 for g in OUT}, n=0); run(20000)
rms = {g: math.sqrt(RMS['rms'][g] / RMS['n']) for g in OUT}; RMS.clear()
phase_ok('night rain, everything on')
info['night_rain_rms_A'] = {gname(g): round(v, 2) for g, v in rms.items() if v > 0.01}
info['night_rain_total_A'] = round(sum(rms.values()), 1)

# ================================================================== 11. ECU frames lost while driving
phase('ECU CAN silent while driving')
t_l = now_ms(); f0 = len(FAULTS); n_e = sum(len(e) for e in EDGES.values()); before = dict(PIN)
carn.powered = False; update(); run(3000); carn.powered = True; update(); run(1000)
phase_ok('ECU CAN silent while driving')
steady = [g for g in OUT if g not in (9, 11, 23, 24) and before[g] != PIN[g]]
check('ECU CAN silent 3 s while driving (the ECU keeps its relays): no PDM output changes (the PDM reads no ECU frame), no fault',
      not steady and len(FAULTS) == f0, (steady, FAULTS[f0:f0 + 3]))
sw('brake', 0); S['win'] = 0; update(); sw('whi', 0); S['wiper'] = False; update(lat={23: (0, 2000), 24: (0, 2000)}); run(2500)
sw('defog_sw', 1); run(200); sw('defog_sw', 0); light('off'); pods_wait('bottom'); run(500)

# ================================================================== 12. low battery, engine off, key on
phase('low battery, engine off')
sw('defog_sw', 1); run(200); sw('defog_sw', 0); run(1500)
t_s = now_ms(); set_vbat(11.6); S['shed'] = True; update(lat={20: (SHED_MS, SHED_MS + 300)}); run(SHED_MS + 3000)
held = [g for g in (7, 8, 17, 21) if EXP[g]['v'] and not PIN[g]]
set_vbat(12.4); update(); run(2000); still = not PIN[20]
set_vbat(13.9); S['shed'] = False; update(lat={20: (0, 300)}); run(1500)
phase_ok('low battery, engine off')
shed = {g: [round(t - t_s) for t, v in edges_in(g, t_s, now_ms()) if v == 0][:1] for g in (20,)}
check(f'battery shed: defogger off {SHED_MS / 1000:.0f}-{SHED_MS / 1000 + 0.3:.1f} s after 11.6 V (<= {SHED_ON} V), still off at 12.4 V, back at 13.9 V (>= {SHED_OFF} V); '
      'nothing ECU-held (CSB3, cluster), CAN-Lambda or windows shed', all(v and SHED_MS <= v[0] <= SHED_MS + 300 for v in shed.values()) and still and not held, (shed, held))
sw('defog_sw', 1); run(200); sw('defog_sw', 0); run(500)

# ================================================================== 13. key off: ECU after-run hold, low battery during it, release
phase('key off: ECU after-run hold')
sw('drl', 1); run(1500)                                               # DRLs on (Bus 2): they follow the ECU's hold too
t_off = now_ms(); f0 = len(FAULTS); S['ign'] = 0; wire(16, 0); update()
run(2000); set_vbat(11.5); update(); run(SHED_MS + 5000)              # the ECU holds K-EFI 37 s (ETB park, its fans on its own relays), the battery sags
hold_ok = PIN[7] and PIN[8] and PIN[3] and not any(MUTED.values()) and not ASLEEP_AT
txq = {k: round(now_ms() - LAST_TX.get(k, 0)) for k in BOARDS}
phase_ok('key off: ECU after-run hold')
check('after-run hold: with the key off and the ECU holding its main relay (IN5) for 37 s, CSB3, cluster and DRLs stay on (Bus 2), '
      'no board mutes or sleeps, a 11.5 V battery sheds nothing (the shed needs the key), no fault', hold_ok and len(FAULTS) == f0,
      dict(csb3=PIN[7], cluster=PIN[8], drl=PIN[3], muted=dict(MUTED), asleep=dict(ASLEEP_AT), last_tx_ms=txq))
phase('ECU releases its hold')
set_vbat(12.5); t_r = now_ms()
ecu_power(0); run(2000); sw('drl', 0); run(MUTE_MS + SLEEP_TIMEOUT_MS + 1000)
phase_ok('ECU releases its hold')
mute = {k: round(LAST_TX.get(k, 0) - t_r) for k in BOARDS}
slept = {k: round((v - t_r) / 1000, 2) for k, v in ASLEEP_AT.items()}
check('ECU release: every output off (CSB3 / cluster / DRLs with IN5), no output fault from the ECU going quiet, '
      'mute 10 s after IN5 went off (last frame within one 100 ms status period of it; never during the hold), every board asleep 30 s after the bus went quiet',
      not any(PIN.values()) and len(FAULTS) == f0 and all(MUTE_MS - 100 <= m <= MUTE_MS + 300 for m in mute.values()) and sorted(slept) == list(BOARDS)
      and all(MUTE_MS / 1000 + 29 <= s <= MUTE_MS / 1000 + 31.5 for s in slept.values()), dict(mute_ms=mute, asleep_s=slept, faults=FAULTS[f0:f0 + 3]))

# ================================================================== 14. parking lights and hazards with the key off
phase('key off: parking lights, hazards')
t_w = now_ms(); n_w = len(WAKES); light('tail', lat={g: (0, 900) for g in OUT}); run(3000)
woke = {k: round(t - t_w, 1) for k, t in WAKES[n_w:]}
park_ok = PIN[14] and PIN[15]
sw('hazard', 1); run(3000); haz = len(spans(9, now_ms() - 3000, now_ms())) >= 3 and len(spans(11, now_ms() - 3000, now_ms())) >= 3
light('off'); run(MUTE_MS - 2000); still_haz = bool(spans(9, now_ms() - 1500, now_ms()))   # hazards keep A2 / A1 / B awake
sw('hazard', 0, lat={9: (0, 40), 11: (0, 40)}); t_h = now_ms(); n_s = len(ASLEEP_AT); run(MUTE_MS + SLEEP_TIMEOUT_MS + 3000)
phase_ok('key off: parking lights, hazards')
check('key off: the tail switch wakes A1 (its wake set) and A1 wakes A2 / B (CAN): parking lamps on (A2 over CAN); hazards flash and keep the PDM '
      'awake; all off -> asleep again', woke.get('A1', 99) <= 5 and park_ok and haz and still_haz and sorted(ASLEEP_AT) == list(BOARDS),
      dict(woke=woke, parking=park_ok, hazard=haz, asleep_s={k: round((v - t_h) / 1000, 1) for k, v in ASLEEP_AT.items()}))

# ================================================================== whole cycle
phase('end')
wd, gap, n = ps.watchdog_summary()
other = {k: [(round(t / 1e6, 3), kind) for t, kind in b.resets if kind not in ('restart', 'wake')] for k, b in B.items()}
check('whole cycle: no watchdog reset, no MCU reset but the planned restart / wakes, no board in fatal error',
      not wd and not any(other.values()) and not any(b.flags()['fatal'] for b in B.values()), (wd, other, f'longest refresh gap {gap:.0f} ms'))
c = {k: B[k].counters() for k in BOARDS}
check('whole cycle: no CAN receive overrun on any board', all(v['rx_overruns'] == 0 for v in c.values()), {k: v['rx_overruns'] for k, v in c.items()})
check('whole cycle: no output fault or overcurrent reported by any board (status msg 3)', not FAULTS, FAULTS[:5])
errs = {}
for j in range(20, len(TRACE)):
    for n_, g in enumerate(OUT):
        im, fw = TRACE[j][3 + n_], TRACE[j][27 + n_]
        if im >= 2.0 and all(abs(TRACE[j - d][3 + n_] - im) <= 0.01 * im for d in range(1, 21)):
            errs[g] = max(errs.get(g, 0.0), abs(fw - im) / im)
check('current readings: every steady load >= 2 A reads within 8 % of the model current', errs and max(errs.values()) <= 0.08,
      {gname(g): f'{e * 100:.1f} %' for g, e in sorted(errs.items())})
info['cycle_s'] = round(now_ms() / 1000, 1)
info['energy_J'] = {k: round(v, 1) for k, v in ENERGY.items()}
info['mean_W'] = {k: round(v / (now_ms() / 1000), 2) for k, v in ENERGY.items()}
info['peak_W_500ms'] = {k: round(v, 2) for k, v in PEAK.items()}
lat_by = {}
for ph_, nm, v, dt in TIMES: lat_by.setdefault(nm, []).append(dt)
info['latency_ms'] = {k: (min(v), max(v), len(v)) for k, v in lat_by.items()}

os.makedirs(OUT_DIR, exist_ok=True)
hdr = ['t_s', 'phase', 'vbat_V'] + [f'{k}_W' for k in BOARDS] + [f'I{g}_{OUT[g][0]}_OUT{OUT[g][1] + 1}_A' for g in OUT]
with open(os.path.join(OUT_DIR, 's5_car_board_power.csv'), 'w') as f:
    f.write('# s5_car_cycle.py (DUMMY car config st185-car.dummy.json): switch conduction loss per board (I^2 x RDS(ON) at TJ = board + 15 K ASSUMED) '
            'and mean current per output, each over 500 ms; loads: the LOADS table in the script (C = presim CAR_LOADS, A = ASSUMED)\n')
    f.write(','.join(hdr) + '\n')
    for r in POW_ROWS: f.write(','.join(str(x) for x in r) + '\n')
cur = {k: [0.0] * 8 for k in BOARDS}
for g, v in rms.items(): cur[OUT[g][0]][OUT[g][1]] = round(v, 2)
json.dump({'_DUMMY': 'DUMMY TEST DATA - s5_car_cycle.py night-rain phase (every car load on), RMS current per output in A, '
                     'from the DUMMY car config and ASSUMED loads; read by tools/thermal_a.py / thermal_board_b.py --case carfull',
           'A1': cur['A1'], 'A2': cur['A2'], 'B': cur['B']}, open(os.path.join(OUT_DIR, 's5_car_currents.dummy.json'), 'w'), indent=1)
with open(os.path.join(OUT_DIR, 's5_car_current_trace.csv'), 'w') as f:
    f.write(','.join(['t_ms', 'phase', 'vbat_V'] + [f'model_{g}' for g in OUT] + [f'fw_{g}' for g in OUT]) + '\n')
    for r in TRACE: f.write(','.join(str(x) for x in r) + '\n')
print(f'wrote {OUT_DIR}/s5_car_board_power.csv ({len(POW_ROWS)} rows), s5_car_currents.dummy.json, s5_car_current_trace.csv')
bad = [r for r in res if r[1] in ('FAIL', 'XPASS')]; nx = sum(r[1] == 'XFAIL' for r in res)
print(f'S5 car: {sum(r[1] == "PASS" for r in res)} of {len(res) - nx} checks passed, {nx} XFAIL')
print(json.dumps(info))
if '--json' in sys.argv: json.dump(dict(checks=res, info=info, violations=VIOL[:60]), open(arg('--json'), 'w'), indent=1)
sys.exit(0 if not bad else 1)
