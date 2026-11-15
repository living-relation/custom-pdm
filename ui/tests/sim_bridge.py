"""custom-pdm: connect dingoConfig to the host simulation of our boards (real dingoFW logic, firmware/sim).

Boards on one CAN bus at 1 Mbit/s (factory defaults): A1 = custompdm_a unit 1 (base 0x500), A2 = custompdm_a unit 2
(0x540), B = custompdm_b (0x580). Build the shared objects first (firmware/sim/build.sh, see ui/README.md).

  python3 sim_bridge.py <so dir> --stdio            lock-step line protocol for the ui/tests C# tests
  python3 sim_bridge.py <so dir> --slcan-tcp 3333   real time, SLCAN over TCP: dingoConfig adapter "SLCAN TCP",
                                                    port localhost:3333, bit rate 1000K

stdio commands (one per line, every reply ends with a line "OK"):
  T <id hex> <data hex>       PC tool sends a standard frame
  RUN <ms>                    run the bus; prints "F <id hex> <data hex>" for every frame the boards sent
  TX <gap ms> <id>:<hex> ...  send frames, running the bus <gap> ms after each; prints frames like RUN
  IN <board> <i> <open|gnd|12v> [up|down|off]   digital input i (0-based) wire / input-board DIP
  TEMP <board> <board C> [die C]                MCP9808 reading (and STM32 die temperature)
  AN <board> <volts>          analog input wire voltage
  QUIT
"""
import os, sys, time, socket, select

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'firmware', 'sim'))
import pdmsim as ps   # noqa: E402

BOARDS = {'A1': (ps.BOARD_A, 1), 'A2': (ps.BOARD_A, 2), 'B': (ps.BOARD_B, 1)}


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
        else:
            sys.stdout.write(f'ERR {raw.strip()}\n')
        sys.stdout.write('OK\n'); sys.stdout.flush()


def slcan_tcp(so, port):
    bus, tool, boards, out = make_bus(so)
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
                        conn.sendall(b'\r')
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
