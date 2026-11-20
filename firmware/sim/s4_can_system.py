"""S4 (presim item 5): the whole car bus at 1 Mbit/s - three PDM boards (real firmware, host sim) plus the dummy ECU,
CAN-Lambda and CSB3 traffic of docs/car-can-dummy/bus-load.dummy.md (a DUMMY TEST COPY, worst cycle times, random
phases), then a board unplugged and plugged back in. Also a worst-case response-time analysis (RTA) of every frame
with worst-case bit stuffing, and the firmware's bus-off settings.
usage: python3 firmware/sim/s4_can_system.py <sim out dir> [--json file]      (exit 1 on any FAIL)
RTA: Davis, Burns, Bril, Lukkien, "Controller Area Network (CAN) schedulability analysis: refuted, revisited and
revised", Real-Time Systems 35 (2007), eq. 7-9, non-preemptive fixed priority; bxCAN TXFP (port.cpp) sends each
board's own queue in request order, so each PDM board is taken as one stream of its 100 ms burst."""
import json, os, random, re, sys
import pdmsim as ps

SO = sys.argv[1] if len(sys.argv) > 1 else '/tmp/simout'
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
res, info = [], {}
def check(name, ok, detail=''):
    res.append((name, bool(ok), str(detail))); print(('PASS ' if ok else 'FAIL ') + name + (' : ' + str(detail) if detail != '' else ''))

# ------------------------------------------------------------------ dummy car traffic (worst cycle times)
rows = []
for line in open(os.path.join(REPO, 'docs', 'car-can-dummy', 'bus-load.dummy.md'), encoding='utf-8'):
    m = re.match(r'\| (0x[0-9A-Fa-f]{3})\s*\| ([^|]+)\| (\d) \| ([\d.]+) \| ([\d.]+) \|', line)
    if m and float(m.group(5)) > 0:
        rows.append((int(m.group(1), 16), m.group(2).strip(), int(m.group(3)), float(m.group(5))))
info['dummy_frames'] = len(rows)
def bits(dlc, worst=True): return 47 + 8 * dlc + ((34 + 8 * dlc - 1) // 4 if worst else 0)

# ------------------------------------------------------------------ 1. RTA (analytic)
BASES = {'A1': 0x500, 'A2': 0x540, 'B': 0x580}
NMSG = 38
tbit = 1e-6
streams = [(i, f'{hex(i)} {n}', bits(d) * tbit, 1.0 / fps, 'car') for i, n, d, fps in rows]
for k, b in BASES.items():   # each board: its 38 frames back to back every 100 ms (FIFO in the node), priority = its lowest ID
    streams.append((b + 2, f'PDM {k} burst', NMSG * bits(8) * tbit, 0.100, 'pdm'))
streams.sort()
worst = {}
for idx, (pid, name, c, t, kind) in enumerate(streams):
    hp = streams[:idx]; lp = streams[idx + 1:]
    blk = max([bits(8) * tbit if x[4] == 'pdm' else x[2] for x in lp], default=0)   # one frame blocks, not a burst
    w = blk
    for _ in range(200):
        w2 = blk + sum(((w + tbit) // x[3] + 1) * x[2] for x in hp)
        if abs(w2 - w) < 1e-9: break
        w = w2
    r = w + c
    worst[name] = (pid, r, t)
ok = all(r <= t for _, r, t in worst.values())
late = [k for k, (_, r, t) in worst.items() if r > t]
wp = max((v for k, v in worst.items() if k.startswith('PDM')), key=lambda v: v[1])
we = max((v for k, v in worst.items() if not k.startswith('PDM')), key=lambda v: v[1])
check('RTA: every frame (dummy car traffic + 3 x 38 PDM msgs, worst stuffing) meets its period', ok,
      f'worst PDM burst done {wp[1] * 1e3:.2f} ms after release (period 100 ms); worst car frame {hex(we[0])} {we[1] * 1e3:.2f} ms' + (f'; late: {late}' if late else ''))
info['rta_ms'] = {k: round(v[1] * 1e3, 3) for k, v in worst.items()}
util = sum(x[2] / x[3] for x in streams)
check('RTA: worst-case bus utilisation (worst stuffing, every planned row)', util < 0.5, f'{util * 100:.1f} % (rule of thumb: < 50 % on a car bus)')
info['util_worst_pct'] = round(util * 100, 2)
ecu_cmd = [v for k, v in worst.items() if v[0] == 0x3F4]
if ecu_cmd:
    check('RTA: ECU -> PDM command frame 0x3F4 worst response time', ecu_cmd[0][1] < 0.002, f'{ecu_cmd[0][1] * 1e3:.2f} ms (< 2 ms; then the PDM 2 ms loop)')

# ------------------------------------------------------------------ 2. bus-off settings (static)
for b in ('custompdm_a', 'custompdm_b'):
    pc = open(os.path.join(REPO, 'firmware', 'boards', b, 'port.cpp'), encoding='utf-8').read()
    cfgs = re.findall(r'CAN_MCR_[A-Z_|\s]+,', pc)
    abom = all('ABOM' in c for c in cfgs) and cfgs
    nart = any('NART' in c for c in cfgs)
    check(f'{b}: bus-off recovers by itself (bxCAN ABOM in every bit-rate config), frames retransmitted (no NART)',
          abom and not nart, f'{len(cfgs)} configs; recovery after 128 x 11 recessive bits = {128 * 11 * tbit * 1e3:.2f} ms at 1 Mbit/s (ISO 11898-1)')

# ------------------------------------------------------------------ 3. sim: 3 boards + dummy traffic, unplug / replug
random.seed(20261120)
bus = ps.Bus(); tool = ps.Tool(bus)
boards = {'A1': ps.Board(ps.BOARD_A, 'A1', SO, unit=1), 'A2': ps.Board(ps.BOARD_A, 'A2', SO, unit=2), 'B': ps.Board(ps.BOARD_B, 'B', SO)}
car = ps.PyNode('car'); lat = []
pend = {}
def mk(i, dlc):
    def tx(t):
        car.send(i, bytes(dlc)); pend.setdefault(i, []).append(t)
    return tx
for i, n, d, fps in rows:
    car.every(int(1e6 / fps), mk(i, d), start=random.randint(0, int(1e6 / fps)))
arr = {}
def watch(f):
    if f.src == 'car' and pend.get(f.id): lat.append((f.id, f.t - pend[f.id].pop(0)))
    arr.setdefault(f.id, []).append(f.t)
bus.watch.append(watch)
bus.add(tool, car, *boards.values())
bus.run_for(2000)
t0, busy0 = bus.now, bus.busy_us
bus.run_for(5000)
load = (bus.busy_us - busy0) / (bus.now - t0) * 100
check('sim: bus load with 3 PDM boards + the dummy car traffic (sim average stuffing)', load < 50, f'{load:.1f} %')
info['sim_load_pct'] = round(load, 2)
mx = max(l for _, l in lat) / 1e3
check('sim: worst car-frame queueing + transmit time measured', mx < 2.0, f'{mx:.2f} ms over {len(lat)} frames')
gaps = {}
for k, b in BASES.items():
    ts = [t for t in arr.get(b + 2, []) if t >= t0]
    gaps[k] = max(b2 - a for a, b2 in zip(ts, ts[1:])) / 1e3 if len(ts) > 2 else None
check('sim: every board\'s msg 0 keeps its 100 ms period under the full load (max gap)',
      all(g is not None and g < 110 for g in gaps.values()), {k: round(v, 2) for k, v in gaps.items()})
# unplug board B for 3 s, then plug it back in
boards['B'].connected = False; tu = bus.now
bus.run_for(3000)
missing = [t for t in arr.get(BASES['B'] + 2, []) if t > tu]
others = all(any(t > tu + 2500e3 for t in arr.get(BASES[k] + 2, [])) for k in ('A1', 'A2'))
boards['B'].connected = True; tr = bus.now
bus.run_for(1000)
back = [t for t in arr.get(BASES['B'] + 2, []) if t > tr]
check('sim: board B unplugged 3 s: its frames stop, A1 / A2 keep sending; plugged back: B is back within 150 ms',
      not missing and others and back and (back[0] - tr) / 1e3 < 150, f'first B msg 0 {((back[0] - tr) / 1e3) if back else None} ms after replug')
check('sim: B answers the tool after the replug (no lock-up, no bus-off left behind)', tool.version(BASES['B']) == ps.FW_VERSION)
print(f'S4: {sum(r[1] for r in res)} of {len(res)} checks passed')
print(json.dumps(info))
if '--json' in sys.argv: json.dump({'res': res, 'info': info}, open(sys.argv[sys.argv.index('--json') + 1], 'w'), indent=1)
sys.exit(0 if all(r[1] for r in res) else 1)
