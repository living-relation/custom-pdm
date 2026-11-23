"""custom-pdm: connect dingoConfig to the host simulation of our boards (real dingoFW logic, firmware/sim).

Boards on one CAN bus at 1 Mbit/s (factory defaults): A1 = custompdm_a unit 1 (base 0x500), A2 = custompdm_a unit 2
(0x540), B = custompdm_b (0x580). Build the shared objects first (firmware/sim/build.sh, see ui/README.md).

  python3 sim_bridge.py <so dir> --stdio            lock-step line protocol for the ui/tests C# tests
  python3 sim_bridge.py <so dir> --slcan-tcp 3333   real time, SLCAN over TCP: dingoConfig adapter "SLCAN TCP",
                                                    port localhost:3333, bit rate 1000K; play lines (IN, LINK,
                                                    LOAD, TEMP, AN, RESTART, T, TXP: see play_ctl) written to
                                                    <so dir>/ctl<port> act while a PC is connected; the app's /pdm
                                                    Simulator panel sends the same lines in band as "!<line>\r"
                                                    ("!HELLO" is answered "!SIM custom-pdm", a play line "!OK ..."
                                                    or "!ERR ...")

stdio commands (one per line, every reply ends with a line "OK"):
  T <id hex> <data hex>       PC tool sends a standard frame
  RUN <ms>                    run the bus; prints "F <id hex> <data hex>" for every frame the boards sent
  TX <gap ms> <id>:<hex> ...  send frames, running the bus <gap> ms after each; prints frames like RUN
  IN <board> <i> <open|gnd|12v> [up|down|off]   digital input i (0-based) wire / input-board DIP
  TEMP <board> <board C> [die C]                MCP9808 reading (and STM32 die temperature)
  AN <board> <volts>          analog input wire voltage
  LINK <board> <on|off>       CAN wires of one board (off = silent: it neither hears nor sends; it keeps running)
  PIN <board> <o>             output o (0-based): prints "P 1" when its PROFET IN pin is high, else "P 0"
  RESTART <board> ...         power-cycle boards at the bus time (config kept: FRAM; wires and LINK state kept);
                              prints "T0 <bus ms>"
  TRACE <ms> <step> <ids|-> <board>:<o> ...   run <ms> in <step> ms steps; prints "E <board>:<o> <bus ms> <0|1>" at
                              the start and at every change of those output pins, then "FRAME <id> <first ms> <last ms>
                              <count>" for each listed ID (hex, comma separated) seen
  CB <base hex> <verb> ...    a simulated Dingo Electronics CANBoard (see CanBoard below): ADD | DEL | SW <i> <0|1> |
                              AN <i> <mV> | ROT <i> <pos> | LINK <on|off> | OUT <n> <id hex> <start bit> [time-out ms] |
                              OUT <n> off (i, n count from 0); also a play line of the real-time bridge
  CBOUT <base hex>            prints "C <o1><o2><o3><o4>": the CANBoard's 4 outputs now (its own state, not a frame)
  BUSLOAD <ms>                run the bus <ms>; prints "B <busy us> <frames>" for that time
  QUIT
"""
import os, sys, time, socket, select, struct

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'firmware', 'sim'))
import pdmsim as ps   # noqa: E402

BOARDS = {'A1': (ps.BOARD_A, 1), 'A2': (ps.BOARD_A, 2), 'B': (ps.BOARD_B, 1)}


class CanBoard(ps.PyNode):
    """canboard (2026-11-22): a stand-in for a Dingo Electronics CANBoard running dingoFW. NOT its firmware: a model
    written from firmware/boards/canboard_v2/msg.cpp (TxMsg0-2, always sent), core/device_config.h (status msg n on
    base + 2 + n, every 100 ms) and functions/can_input.cpp + digital_output.cpp (an output follows a CAN input:
    value == 1, off when no frame came for the time-out). 1 Mbit/s (the board must be set to it: 500K from factory).
      base + 2   analog inputs 1-4 in mV (uint16 LE)          base + 3   analog input 5 in mV, bytes 6-7 temperature
      base + 4   byte 0-2 rotary positions (nibbles), byte 4 digital inputs 1-8, byte 5 analog inputs as switches
                 (over 2.5 V, the firmware default), byte 6 the 4 output states, byte 7 heartbeat (+1 per frame)
    OUT <n> <id> <start bit> [ms] is what the user sets on the real CANBoard for output n: CAN input n = that ID,
    start bit, 8 bits, Equal 1, time-out on; digital output n = CAN input n."""
    def __init__(s, base, now):
        super().__init__(f'canboard{base:X}'); s.base = base; s.sw = [0] * 8; s.an = [0] * 5; s.rot = [0] * 5; s.hb = 0
        s.cfg = {}; s.val = {}; s.temp = 30; s.now = now; s.on_rx = s._rx; s.every(100000, s._tick, now + 1000)
    def _rx(s, f):
        for n, (i, bit, _) in s.cfg.items():
            if f.id == i and not f.ide: s.val[n] = ((int.from_bytes(f.data, 'little') >> bit) & 0xFF, f.t)
    def outs(s, now):
        return [int(n in s.cfg and n in s.val and s.val[n][0] == 1 and now - s.val[n][1] <= s.cfg[n][2]) for n in range(4)]
    def _tick(s, t):
        s.now = t
        if not s.connected: s.q.clear(); return     # unplugged: nothing queued for later
        o = s.outs(t)
        s.send(s.base + 2, struct.pack('<4H', *s.an[:4]))
        s.send(s.base + 3, struct.pack('<4H', s.an[4], 0, 0, s.temp))
        s.send(s.base + 4, bytes([s.rot[1] << 4 | s.rot[0], s.rot[3] << 4 | s.rot[2], s.rot[4], 0,
                                  sum(b << i for i, b in enumerate(s.sw)), sum((mv > 2500) << i for i, mv in enumerate(s.an)),
                                  sum(b << i for i, b in enumerate(o)), s.hb]))
        s.hb = (s.hb + 1) & 255


CANBOARDS = {}   # base ID -> CanBoard (one bus per bridge process)


def canboard_cmd(a, bus):
    """CB <base hex> <verb> ...: True when done, False for a line it does not know (raises on a bad number)."""
    if len(a) < 3: return False
    base = int(a[1], 16); verb = a[2].upper(); cb = CANBOARDS.get(base)
    if verb == 'ADD':
        if cb is None: cb = CANBOARDS[base] = CanBoard(base, bus.now); bus.add(cb)
        return True
    if cb is None: return False
    if verb == 'DEL' and len(a) == 3: bus.nodes.remove(cb); del CANBOARDS[base]
    elif verb == 'SW' and len(a) == 5 and a[4] in ('0', '1'): cb.sw[int(a[3])] = int(a[4])
    elif verb == 'AN' and len(a) == 5 and 0 <= int(float(a[4])) <= 5000: cb.an[int(a[3])] = int(float(a[4]))
    elif verb == 'ROT' and len(a) == 5 and 0 <= int(a[4]) <= 15: cb.rot[int(a[3])] = int(a[4])
    elif verb == 'LINK' and len(a) == 4 and a[3].lower() in ('on', 'off'): cb.connected = a[3].lower() == 'on'
    elif verb == 'OUT' and len(a) == 5 and a[4].lower() == 'off' and 0 <= int(a[3]) < 4: cb.cfg.pop(int(a[3]), None); cb.val.pop(int(a[3]), None)
    elif verb == 'OUT' and len(a) in (6, 7) and 0 <= int(a[3]) < 4 and 0 <= int(a[5]) <= 56:
        cb.cfg[int(a[3])] = (int(a[4], 16), int(a[5]), int(float(a[6]) * 1000) if len(a) == 7 else 1000000); cb.val.pop(int(a[3]), None)
    else: return False
    return True


def make_bus(so):
    bus = ps.Bus(); tool = ps.Tool(bus)
    boards = {k: ps.Board(m, k, so, unit=u) for k, (m, u) in BOARDS.items()}
    bus.add(tool, *boards.values())
    out = []
    bus.watch.append(lambda f: out.append(f) if f.src != 'tool' and not f.ide else None)
    return bus, tool, boards, out


def stdio(so):
    bus, tool, boards, out = make_bus(so)
    for raw in sys.stdin:
        a = raw.split()
        if not a:
            continue
        c = a[0].upper()
        if c == 'QUIT':
            break
        if c == 'T':
            tool.send(int(a[1], 16), bytes.fromhex(a[2]))
        elif c == 'RUN':
            out.clear(); bus.run_for(float(a[1]))
            sys.stdout.write(''.join(f'F {f.id:X} {f.data[:f.dlc].hex()}\n' for f in out))
        elif c == 'TX':   # TX <gap ms> <id>:<hex> ...: send each frame, run <gap> ms after each (dingoConfig paces 2 ms)
            out.clear()
            for tok in a[2:]:
                i, h = tok.split(':'); tool.send(int(i, 16), bytes.fromhex(h)); bus.run_for(float(a[1]))
            sys.stdout.write(''.join(f'F {f.id:X} {f.data[:f.dlc].hex()}\n' for f in out))
        elif c == 'IN':
            boards[a[1]].set_input(int(a[2]), a[3], a[4] if len(a) > 4 else None)
        elif c == 'TEMP':
            boards[a[1]].set_temp(float(a[2]), float(a[3]) if len(a) > 3 else None)
        elif c == 'AN':
            boards[a[1]].set_analog(float(a[2]))
        elif c == 'LOAD':   # editor2: LOAD <board> <o> <amps>: a resistive load drawing <amps> at the battery voltage (0 = open)
            b = boards[a[1]]; amps = float(a[3]); b.set_load(int(a[2]), b.vbat / amps if amps else 0)
        elif c == 'LINK':
            boards[a[1]].connected = a[2].lower() == 'on'
        elif c == 'CB':   # canboard: a simulated CANBoard
            if not canboard_cmd(a, bus): sys.stdout.write(f'ERR {raw.strip()}\n')
        elif c == 'CBOUT':
            sys.stdout.write('C ' + ''.join(str(x) for x in CANBOARDS[int(a[1], 16)].outs(bus.now)) + '\n')
        elif c == 'BUSLOAD':
            b0, n0 = bus.busy_us, bus.count; bus.run_for(float(a[1])); out.clear()
            sys.stdout.write(f'B {bus.busy_us - b0} {bus.count - n0}\n')
        elif c == 'PIN':   # B4: ground truth of an output, its PROFET IN pin (as s1_system.py pins_on)
            b = boards[a[1]]; sys.stdout.write(f'P {int(bool(b.level(b.model["outputs"][int(a[2])][0])))}\n')
        elif c == 'RESTART':   # w1: power-cycle boards (config kept: FRAM; wires, input DIPs and CAN wires kept)
            for k in a[1:]:
                old = boards[k]; m, u = BOARDS[k]
                nb = ps.Board(m, k, so, fram=old.fram(), unit=u); nb.t0 = bus.now; nb.connected = old.connected
                for i, w in old.wire.items(): nb.set_input(i, w, old.dip.get(i))
                bus.nodes[bus.nodes.index(old)] = nb; boards[k] = nb
            sys.stdout.write(f'T0 {bus.now / 1000}\n')
        elif c == 'TRACE':   # w1: TRACE <ms> <step ms> <ids hex,..|-> <board>:<o> ...
            ms, step = float(a[1]), float(a[2]); ids = [] if a[3] == '-' else [int(x, 16) for x in a[3].split(',')]
            pins = [(p, boards[p.split(':')[0]], int(p.split(':')[1])) for p in a[4:]]; seen = {}; last = {}
            def w(f):
                if f.id in ids: r = seen.setdefault(f.id, [f.t, f.t, 0]); r[1] = f.t; r[2] += 1
            bus.watch.append(w); end = bus.now + int(ms * 1000)
            try:
                while True:
                    for key, bd, o in pins:
                        lv = int(bool(bd.level(bd.model['outputs'][o][0])))
                        if last.get(key) != lv: last[key] = lv; sys.stdout.write(f'E {key} {bus.now / 1000} {lv}\n')
                    if bus.now >= end: break
                    bus.run(min(end, bus.now + int(step * 1000)))
            finally:
                bus.watch.remove(w); out.clear()
            for i in ids:
                if i in seen: sys.stdout.write(f'FRAME {i:X} {seen[i][0] / 1000} {seen[i][1] / 1000} {seen[i][2]}\n')
        else:
            sys.stdout.write(f'ERR {raw.strip()}\n')
        sys.stdout.write('OK\n'); sys.stdout.flush()


def play_ctl(a, so, bus, tool, boards, periodic):
    """uiwalk: one line of <so dir>/ctl<port> (real-time bridge), so the play UI can be exercised without the tests:
    IN <board> <i> <open|gnd|12v> [dip]   LINK <board> <on|off>   LOAD <board> <o> <amps>   TEMP <board> <C> [die C]
    AN <board> <volts>   RESTART <board> ...   T <id hex> <data hex>   TXP <id hex> <data hex|off> [period ms]
    CB <base hex> ADD | DEL | SW <i> <0|1> | AN <i> <mV> | ROT <i> <pos> | LINK <on|off> | OUT <n> <id hex> <start bit> [ms] | OUT <n> off
    (i and o count from 0, as in the --stdio protocol). Returns False for a line it does not know."""
    if not a: return False
    c = a[0].upper()
    if c == 'CB': return canboard_cmd(a, bus)   # canboard: a simulated CANBoard
    if c == 'IN' and len(a) >= 4: boards[a[1]].set_input(int(a[2]), a[3], a[4] if len(a) > 4 else None)
    elif c == 'LINK' and len(a) == 3: boards[a[1]].connected = a[2].lower() == 'on'
    elif c == 'LOAD' and len(a) == 4:
        b = boards[a[1]]; amps = float(a[3]); b.set_load(int(a[2]), b.vbat / amps if amps else 0)
    elif c == 'TEMP' and len(a) >= 3: boards[a[1]].set_temp(float(a[2]), float(a[3]) if len(a) > 3 else None)
    elif c == 'AN' and len(a) == 3: boards[a[1]].set_analog(float(a[2]))
    elif c == 'RESTART' and len(a) >= 2:
        for k in a[1:]:
            old = boards[k]; m, u = BOARDS[k]
            nb = ps.Board(m, k, so, fram=old.fram(), unit=u); nb.t0 = bus.now; nb.connected = old.connected
            for i, w in old.wire.items(): nb.set_input(i, w, old.dip.get(i))
            bus.nodes[bus.nodes.index(old)] = nb; boards[k] = nb
    elif c == 'T' and len(a) == 3: tool.send(int(a[1], 16), bytes.fromhex(a[2]))
    elif c == 'TXP' and len(a) >= 3:
        if a[2].lower() == 'off': periodic.pop(int(a[1], 16), None)
        else: periodic[int(a[1], 16)] = [bytes.fromhex(a[2]), int(float(a[3]) * 1000) if len(a) > 3 else 50000, bus.now]
    else: return False
    return True


def slcan_tcp(so, port):
    bus, tool, boards, out = make_bus(so)
    periodic = {}   # id -> [data, period us, next time us]
    ctl = os.path.join(so, f'ctl{port}')
    srv = socket.socket(); srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(('0.0.0.0', port)); srv.listen(1)
    print(f'SLCAN TCP on port {port}: dingoConfig adapter "SLCAN TCP", port localhost:{port}, 1000K', flush=True)
    rates = {'3': 100000, '4': 125000, '5': 250000, '6': 500000, '8': 1000000}
    while True:
        conn, addr = srv.accept(); conn.setblocking(False); buf = b''; t0 = time.monotonic(); s0 = bus.now
        print(f'connected {addr}', flush=True)
        try:
            while True:
                r, _, _ = select.select([conn], [], [], 0.005)
                if r:
                    d = conn.recv(4096)
                    if not d:
                        break
                    buf += d
                    while b'\r' in buf:
                        line, buf = buf.split(b'\r', 1); line = line.decode(errors='replace').strip()
                        if line[:1] == 't' and len(line) >= 5:
                            n = int(line[4], 16); tool.send(int(line[1:4], 16), bytes.fromhex(line[5:5 + 2 * n]))
                        elif line[:1] == 'S' and line[1:] in rates:
                            tool._bitrate = rates[line[1:]]
                        elif line[:1] == '!':   # uipolish: a play line from the app's /pdm Simulator panel, in band
                            a = line[1:].split()
                            if a and a[0].upper() == 'HELLO':
                                conn.sendall(b'!SIM custom-pdm\r'); continue
                            try: ok = play_ctl(a, so, bus, tool, boards, periodic)
                            except (KeyError, ValueError, IndexError, ZeroDivisionError): ok = False
                            print(f'app {line[1:]} {"at" if ok else "refused at"} {bus.now / 1000:.1f} ms', flush=True)
                            conn.sendall((('!OK ' if ok else '!ERR ') + line[1:] + '\r').encode()); continue
                        conn.sendall(b'\r')
                if os.path.exists(ctl):   # w1: IN / LINK lines written to <so dir>/ctl<port> act at once (browser checks)
                    with open(ctl) as fh: lines = fh.read().splitlines()
                    os.remove(ctl)
                    for raw in lines:
                        a = raw.split()
                        try:
                            if not play_ctl(a, so, bus, tool, boards, periodic): continue
                        except (KeyError, ValueError, IndexError) as e:   # a typo in a ctl line must not stop the bridge
                            print(f'ctl {raw} refused: {e!r}', flush=True); continue
                        print(f'ctl {raw} at {bus.now / 1000:.1f} ms', flush=True)
                for i, p in periodic.items():   # uiwalk: TXP frames (an ECU stand-in) on the bus clock
                    while bus.now >= p[2]: tool.send(i, p[0]); p[2] += p[1]
                # real time: run the bus up to the wall clock (it lags if the PC is slower)
                out.clear(); bus.run(s0 + int((time.monotonic() - t0) * 1e6))
                if out:
                    conn.sendall(''.join(f't{f.id:03X}{f.dlc}{f.data[:f.dlc].hex().upper()}\r' for f in out).encode())
        except (ConnectionError, OSError):
            pass
        conn.close(); print('disconnected', flush=True)


if __name__ == '__main__':
    so_dir = sys.argv[1]
    if '--slcan-tcp' in sys.argv:
        slcan_tcp(so_dir, int(sys.argv[sys.argv.index('--slcan-tcp') + 1]))
    else:
        stdio(so_dir)
