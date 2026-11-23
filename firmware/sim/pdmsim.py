"""custom-pdm host simulation: boards (real dingoFW logic built as shared objects), CAN bus, hardware models.

Hardware models below are written from custom-pdm docs/firmware-pin-map.md (2026-11-10), NOT from the
firmware port, so a wrong pin in the firmware shows up as a failed check."""
import ctypes, shutil, struct, os, math

P = {c: i for i, c in enumerate('ABCDEFGH')}
def pin(name):            # 'PB10' -> (1, 10)
    return P[name[1]], int(name[2:])
def line(name):
    a, b = pin(name); return (a << 4) | b

# ---- drivers: the real part's typ. kILIS from the Infineon data sheet, NOT the firmware constant (port.h), so a wrong
# constant shows up as a wrong reading (s1 S8). BTS7008-2EPA Rev 1.21 Table 22 kILIS16 5450 +-4.0 % at 5.5 A (P_9.7.1.20,
# also kILIS18 at 10 A); BTS70012-1ESP Rev 1.21 Table 21 kILIS22 33700 +-4.8 % at 30 A (P_9.7.26.26, 33700 from 7 A up);
# BTS7004-1EPP Rev 1.11 Table 21 kILIS19 20000 +-5.0 % at 15 A (P_9.7.11.23, 20000 from 2 A up).
KILIS = {'BTS7008-2EPA': 5450, 'BTS70012-1ESP': 33700, 'BTS7004-1EPP': 20000}
# Top of the IS chain (IS -> 1.2k -> 4.7k -> PDZ3.3B -> 4.7k -> TLV9004 follower -> 120R -> ADC, docs/pcb-verification.md):
# the rail-to-rail follower (TI SBOS833R 7.x: input (V-)-0.1 to (V+)+0.1 V, output within 20 mV of the rails) passes
# the zener node up to 3.28 V, so the zener sets the top. PDZ3.3B (NXP PDZ-B series data sheet 2004 Mar 22, Table 2):
# VZ 3.32-3.53 V at 5 mA, rdif up to 1000 Ohm at 0.5 mA, -2.4 mV/K; with IIS(FAULT) 4.4 mA min only about 0.4 mA flows
# in the zener, so a fault reads somewhere from about 2.7 V (min part, low current, hot; an estimate: the low-current
# knee is not specified) to VDDA. Default: VDDA (3.3 V); s3 / s1 also run the low end (IS_CLAMP_LOW).
IS_CLAMP = 3.3
IS_CLAMP_LOW = 2.7
LEDS = ('PC0', 'PC1')     # error (red), status (green), both boards, active high via 120 R (docs/firmware-pin-map.md)
RSENSE = 1200.0
# out: (IN, DEN, DSEL or None, DSEL level for this channel, IS pin, driver)
BOARD_A = dict(
    fw='custompdm_a',
    outputs=[('PB10', 'PB2', 'PC7', 0, 'PA0', 'BTS7008-2EPA'), ('PC8', 'PB2', 'PC7', 1, 'PA0', 'BTS7008-2EPA'),
             ('PC6', 'PB15', 'PB14', 0, 'PC3', 'BTS7008-2EPA'), ('PB12', 'PB15', 'PB14', 1, 'PC3', 'BTS7008-2EPA'),
             ('PB1', 'PB0', 'PC5', 0, 'PA1', 'BTS7008-2EPA'), ('PC4', 'PB0', 'PC5', 1, 'PA1', 'BTS7008-2EPA'),
             ('PA7', 'PA6', 'PA5', 0, 'PA2', 'BTS7008-2EPA'), ('PA4', 'PA6', 'PA5', 1, 'PA2', 'BTS7008-2EPA')],
    # digital inputs in firmware order. kind: 'direct' = board connector, 'ib' = input board channel n
    inputs=[('PA10', 'direct'), ('PC9', 'direct'), ('PC10', 'ib1'), ('PC11', 'ib2'), ('PB4', 'ib3'), ('PC13', 'ib4'), ('PB3', 'ib5')],
    analog='PC2', batt='PA3', limit=7.5, base={1: 0x500, 2: 0x540})
BOARD_B = dict(
    fw='custompdm_b',
    outputs=[('PB14', 'PB13', None, 0, 'PC3', 'BTS70012-1ESP'), ('PC7', 'PC6', None, 0, 'PC2', 'BTS70012-1ESP'),
             ('PB0', 'PC5', None, 0, 'PA0', 'BTS70012-1ESP'), ('PA6', 'PA5', None, 0, 'PA1', 'BTS70012-1ESP'),
             ('PA8', 'PB12', None, 0, 'PA2', 'BTS7004-1EPP'), ('PB10', 'PB12', None, 0, 'PA4', 'BTS7004-1EPP'),
             ('PA15', 'PB15', None, 0, 'PA7', 'BTS7004-1EPP'), ('PC8', 'PB15', None, 0, 'PC4', 'BTS7004-1EPP')],
    inputs=[('PA10', 'direct'), ('PC9', 'direct'), ('PC14', 'ib1'), ('PC15', 'ib2'), ('PC13', 'ib3'), ('PD2', 'ib4'),
            ('PB4', 'ib5'), ('PB5', 'ib6'), ('PC10', 'ib7'), ('PC11', 'ib8')],
    analog='PB1', batt='PA3', limit=None, base={1: 0x580})
# Factory base IDs 0x40 apart: dingoFW development uses base + 0 / + 1 (PC tool) and base + 2 + n for cyclic msgs
# 0..NUM_TX_MSGS-1 = 40 IDs with our 38 msgs (tools_custom/port_boards.py BASE_*). Device types: port_boards.py TYPE_*.
STATUS_MSG = 37                                  # custom-pdm status frame (port_boards.py STATUS_MSG), after upstream's 0-36
NUM_TX_MSGS = STATUS_MSG + 1
DEVICE_TYPE = {'custompdm_a': 14, 'custompdm_b': 15}
FW_VERSION = (0, 6, 2)                           # core/device_config.h MAJOR / MINOR / BUILD (dingoFW development 14084e9)

class Frame:
    __slots__ = ('id', 'ide', 'dlc', 'data', 'src', 't')
    def __init__(s, id, data, ide=0, dlc=None, src=None):
        s.id = id; s.ide = ide; s.data = bytes(data) + bytes(8 - len(data)); s.dlc = len(data) if dlc is None else dlc; s.src = src; s.t = 0

# MCU safety (core/safety.h, MCU_SAFETY): option bytes as FLASH_OPTCR shows them (RM0390 3.8.6). Factory: BOR_LEV
# 11 = BOR off; after the firmware's first start: 00 = BOR level 3. A Board starts with BOR level 3 already set (a
# board that has been powered before) unless opt=OPT_FACTORY is given. RCC_CSR reset flags (RM0390 6.3.21).
OPT_FACTORY = 0x0FFFAAED
OPT_BOR3 = OPT_FACTORY & ~0x0C
RSTF_POR, RSTF_BOR, RSTF_SFT, RSTF_IWDG = 1 << 27, 1 << 25, 1 << 28, 1 << 29
LSI_HZ = (17000, 32000, 47000)                  # STM32F446 DS DocID027107 Rev 2 Table 42: min / typ / max
SAFETY_WDG_MIN_MS = 1000                        # core/safety.h: run timeout at the fastest LSI (>= 2 x the longest gap)

class Board:
    """One simulated board: real firmware logic + the hardware model around it.
    An MCU reset (the firmware's own NVIC_SystemReset, or the watchdog) restarts the firmware in place (run_until):
    FRAM, option bytes, loads, inputs and temperatures stay; every pin is back at its reset state meanwhile."""
    n_inst = 0
    all = []                                        # every Board made in this run (watchdog summary: watchdog_summary)
    def __init__(s, model, name, sodir, fram=None, fram_size=32768, vbat=13.8, unit=1, opt=OPT_BOR3, lsi=32000, reset_flags=RSTF_POR | RSTF_BOR):
        s.model = model; s.name = name; s.connected = True; s.powered = True; s.sodir = sodir; s.unit = unit
        s.fram_size = fram_size; s.vbat = vbat; s.t0 = 0; s.board_c = 30.0; s.die_c = 30.0; s.vdda = None
        s.loads = {}; s.clamps = {}; s.analog_pins = {}; s.lsi = lsi; s.resets = []
        s.dip = {}; s.wire = {}
        s._load(fram, opt, reset_flags); Board.all.append(s)
    def _load(s, fram, opt, reset_flags):
        Board.n_inst += 1; model = s.model
        path = os.path.join(s.sodir, f"inst{Board.n_inst}_{model['fw']}.so")
        shutil.copy(os.path.join(s.sodir, f"{model['fw']}_unit{s.unit}.so"), path)     # own copy = own globals
        L = s.L = ctypes.CDLL(path, mode=ctypes.RTLD_LOCAL)
        L.sim_now.restype = ctypes.c_uint64; L.sim_next_event.restype = ctypes.c_uint64
        L.sim_run_until.argtypes = [ctypes.c_uint64]; L.sim_out_current.restype = ctypes.c_float
        L.sim_var.restype = ctypes.c_float; L.sim_can_bitrate.restype = ctypes.c_uint32
        L.sim_set_pin_volts.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_float]
        L.sim_set_env.argtypes = [ctypes.c_float] * 3
        L.sim_plant_add.argtypes = [ctypes.c_int] * 5 + [ctypes.c_float] * 3
        L.sim_plant_set.argtypes = [ctypes.c_int, ctypes.c_float, ctypes.c_int]; L.sim_plant_clamp.argtypes = [ctypes.c_int, ctypes.c_float]
        L.sim_fram.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_uint32]
        L.sim_opt_set.argtypes = [ctypes.c_uint32]; L.sim_opt_get.restype = ctypes.c_uint32
        L.sim_set_lsi.argtypes = [ctypes.c_uint32]; L.sim_set_reset_flags.argtypes = [ctypes.c_uint32]
        L.sim_halt_at.restype = ctypes.c_uint64; L.sim_stall_thread.argtypes = [ctypes.c_char_p]
        if fram is not None: L.sim_fram(fram, 1, s.fram_size)
        else:
            buf = ctypes.create_string_buffer(b'\xff' * s.fram_size, s.fram_size); L.sim_fram(buf, 1, s.fram_size)
        L.sim_opt_set(opt); L.sim_set_lsi(s.lsi); L.sim_set_reset_flags(reset_flags)
        for o in model['outputs']:
            L.sim_plant_add(line(o[0]), line(o[1]), line(o[2]) if o[2] else -1, o[3], line(o[4]), KILIS[o[5]], RSENSE, IS_CLAMP)
        s.set_vbat(s.vbat)
        if s.vdda is not None: s.set_vdda(s.vdda)
        for o, (ohms, fault) in s.loads.items(): s.set_load(o, ohms, fault)
        for o, v in s.clamps.items(): s.set_is_clamp(o, v)
        for (a, b), v in s.analog_pins.items(): L.sim_set_pin_volts(a, b, v)
        for i in range(len(model['inputs'])): s.set_input(i, s.wire.get(i, 'open'), s.dip.get(i, 'off'))
        L.sim_boot()
    def _mcu_reset(s):
        """The MCU reset itself (software reset or watchdog): start the firmware again from the moment it happened."""
        f = s.L.sim_flags(); at = s.t0 + s.L.sim_halt_at(); kind = 'watchdog' if f & 16 else 'software'
        fram, opt = s.fram(), s.L.sim_opt_get()
        s.resets.append((at, kind)); s.t0 = at
        s._load(fram, opt, RSTF_IWDG if kind == 'watchdog' else RSTF_SFT)
    # --- environment
    def set_vbat(s, v):
        s.vbat = v; s.L.sim_set_env(v, s.board_c, s.die_c)
        a, b = pin(s.model['batt']); s.L.sim_set_pin_volts(a, b, v * 4700.0 / (47000.0 + 4700.0))
    def set_vdda(s, v):
        s.vdda = v; s.L.sim_set_vdda.argtypes = [ctypes.c_float]; s.L.sim_set_vdda(v)
    def set_temp(s, board_c, die_c=None):
        """board_c: MCP9808 reading. die_c: STM32 die (internal sensor), unchanged if None."""
        s.board_c = board_c; s.die_c = s.die_c if die_c is None else die_c; s.L.sim_set_env(s.vbat, s.board_c, s.die_c)
    def set_load(s, out, ohms, fault=0): s.loads[out] = (ohms, fault); s.L.sim_plant_set(out, ohms or 0.0, fault)
    def set_is_clamp(s, out, volts=IS_CLAMP): s.clamps[out] = volts; s.L.sim_plant_clamp(out, volts)   # top of the IS chain (see IS_CLAMP)
    # --- MCP9808 (sim_core.cpp model)
    def mcp_fail(s, n): s.L.sim_mcp_fail(n)                 # next n reads fail on I2C, -1 = all until mcp_fail(0)
    def mcp_carry(s, held): s.L.sim_mcp_carry(ctypes.c_float(held))   # chip left in shutdown by the last sleep, holding 'held'
    def mcp_info(s):
        c = (ctypes.c_uint32 * 6)(); s.L.sim_mcp_info(c)
        return dict(zip(['shutdown', 'alert_on', 'shutdown_calls', 'reads', 'failed', 'fw_fails'], c))
    def set_input(s, i, wire, dip=None):
        """wire: 'open' | 'gnd' | '12v'. dip (input board only): 'up' | 'down' | 'off'."""
        mcu, kind = s.model['inputs'][i]
        if dip is not None: s.dip[i] = dip
        s.wire[i] = wire; d = s.dip.get(i, 'off') if kind != 'direct' else 'off'
        ext = 0 if wire == 'gnd' else 1 if wire == '12v' else (1 if d == 'up' else 0 if d == 'down' else 2)
        a, b = pin(mcu); s.L.sim_set_ext(a, b, ext)
    def set_analog(s, wire_volts):
        a, b = pin(s.model['analog']); v = min(wire_volts * 20.0 / 30.0, 3.3); s.analog_pins[(a, b)] = v; s.L.sim_set_pin_volts(a, b, v)   # 10k / 20k divider + clamp
    # --- pins
    def level(s, name): a, b = pin(name); return s.L.sim_get_level(a, b)
    def watch(s, *names):
        """Log every edge of these output pins from now on (pin-level timing, exact to 1 us)."""
        s.L.sim_watch_pins(len(names), (ctypes.c_int * max(1, len(names)))(*[line(n) for n in names]))
    def edges(s):
        """[(t_us, pin index in watch(), new level)] since the last call."""
        out = []; n = 4096
        t = (ctypes.c_uint64 * n)(); i = (ctypes.c_int * n)(); lv = (ctypes.c_int * n)()
        while True:
            k = s.L.sim_edges(t, i, lv, n)
            out += [(s.t0 + t[j], i[j], lv[j]) for j in range(k)]
            if k < n: return out
    def pin_info(s, name):
        a, b = pin(name); v = s.L.sim_pin_info(a, b)
        return dict(mode=['input', 'output', 'alternate', 'analog'][v & 3], pull=['none', 'up', 'down', '?'][(v >> 2) & 3], odr=(v >> 4) & 1, af=(v >> 8) & 15, event=(v >> 12) & 1)
    def counters(s):
        c = (ctypes.c_uint32 * 16)(); s.L.sim_counters(c)
        k = ['bad_writes', 'last_bad_write', 'float_reads', 'last_float_read', 'rx_overruns', 'tx_timeouts', 'rx_filtered', 'exti_clashes',
             'fram_writes', 'config_bytes', 'n_out', 'n_di', 'n_an', 'var_map', 'filter_on', 'tx_pending']
        return dict(zip(k, c))
    def flags(s):
        f = s.L.sim_flags(); return dict(fatal=bool(f & 1), asleep=bool(f & 2), bootloader=bool(f & 4), restart=bool(f & 8), wdg_reset=bool(f & 16))
    # --- MCU safety (core/safety.h)
    def opt(s): return s.L.sim_opt_get()
    def bor_level_bits(s): return (s.opt() >> 2) & 3                      # 0 = level 3, 3 = off (factory)
    def wdg(s):
        c = (ctypes.c_uint64 * 10)(); s.L.sim_wdg_info(c)
        return dict(zip(['running', 'pr', 'rlr', 'refreshes', 'max_gap_us', 'max_gap_at', 'timeout_us', 'rtc_wut', 'rtc_wakes', 'opt_writes'], c))
    def wdg_gap_reset(s): s.L.sim_wdg_gap_reset()
    def stall(s, thread): return s.L.sim_stall_thread(thread.encode())     # 'DeviceThread', 'SlowThread', 'CAN Rx', ...
    def fram(s):
        buf = ctypes.create_string_buffer(s.fram_size); s.L.sim_fram(buf, 0, s.fram_size); return buf.raw
    # --- var map index (mirrors InitVarMap order in core/device.cpp)
    def var_di(s, i): return 5 + i
    def var_an_mv(s, i=0): return 5 + len(s.model['inputs']) + 4 * i + 1
    def var_canin(s, i): return 5 + len(s.model['inputs']) + 4 + 2 * i          # fOutput
    def var_virt(s, i): return 5 + len(s.model['inputs']) + 4 + 64 + i
    def var_out(s, i): return 5 + len(s.model['inputs']) + 4 + 64 + 16 + 4 * i                # fOutput
    def var_cond(s, i): return 5 + len(s.model['inputs']) + 4 + 64 + 16 + 4 * len(s.model['outputs']) + 4 + i
    # --- bus node interface
    def now(s): return s.t0 + s.L.sim_now()
    def next_event(s): return s.t0 + s.L.sim_next_event() if s.powered else math.inf
    def run_until(s, t):
        if not s.powered: return
        for _ in range(100):
            s.L.sim_run_until(max(0, t - s.t0))
            if not (s.L.sim_flags() & (8 | 16)): return
            s._mcu_reset()                                  # MCU reset: run the rest of the time on the new start
    def bitrate(s): return s.L.sim_can_bitrate() if s.powered else 0
    def tx_peek(s):
        if not s.powered: return None
        i = ctypes.c_uint32(); e = ctypes.c_int(); d = ctypes.c_int(); b = (ctypes.c_uint8 * 8)()
        if not s.L.sim_can_tx_peek(ctypes.byref(i), ctypes.byref(e), ctypes.byref(d), b): return None
        return Frame(i.value, bytes(b), e.value, d.value, s.name)
    def tx_pop(s): s.L.sim_can_tx_pop()
    def rx(s, f):
        if s.powered: s.L.sim_can_rx(f.id, f.ide, f.dlc, (ctypes.c_uint8 * 8)(*f.data))

def watchdog_summary():
    """Over every Board of this run: unexpected watchdog resets and the longest refresh gap (run timeout) in ms."""
    resets = [(b.name, t, k) for b in Board.all for t, k in b.resets if k == 'watchdog']
    gap = max([b.wdg()['max_gap_us'] for b in Board.all] or [0]) / 1000
    return resets, gap, len(Board.all)

class PyNode:
    """A CAN node written in Python (ECU, PC tool)."""
    def __init__(s, name, bitrate=1000000):
        s.name = name; s._bitrate = bitrate; s.q = []; s.connected = True; s.powered = True; s.on_rx = None; s.timers = []
    def bitrate(s): return s._bitrate if s.powered else 0
    def send(s, id, data): s.q.append(Frame(id, data, src=s.name))
    def tx_peek(s): return s.q[0] if (s.q and s.powered) else None
    def tx_pop(s): s.q.pop(0)
    def rx(s, f):
        if s.on_rx and s.powered: s.on_rx(f)
    def every(s, period_us, fn, start=0): s.timers.append([start, period_us, fn])
    def next_event(s): return min([t[0] for t in s.timers], default=math.inf) if s.powered else math.inf
    def run_until(s, t):
        for tm in s.timers:
            while tm[0] <= t:
                if s.powered: tm[2](tm[0])
                tm[0] += tm[1]

class Bus:
    """One CAN bus. Lowest ID wins arbitration; a frame needs another live node at the same bit rate to be acknowledged."""
    def __init__(s): s.nodes = []; s.now = 0; s.cur = None; s.busy_until = 0; s.log = None; s.count = 0; s.busy_us = 0; s.watch = []
    def add(s, *n): s.nodes += n
    def _service(s):
        if s.cur and s.now >= s.busy_until:
            f, src = s.cur; s.cur = None; f.t = s.now; s.count += 1
            for n in s.nodes:
                if n is not src and n.connected and n.bitrate() == src.bitrate(): n.rx(f)
            for w in s.watch: w(f)
            if s.log is not None: s.log.append(f)
        if not s.cur:
            best = None
            for n in s.nodes:
                if not n.connected or not n.bitrate(): continue
                f = n.tx_peek()
                if f is None: continue
                if not any(m is not n and m.connected and m.bitrate() == n.bitrate() for m in s.nodes): continue   # no ACK: stays pending
                if best is None or (f.ide, f.id) < (best[0].ide, best[0].id): best = (f, n)
            if best:
                f, n = best; n.tx_pop(); bits = (47 + 8 * f.dlc) * 1.15 + 3   # frame + average stuffing + interframe space
                dur = int(bits * 1e6 / n.bitrate()); s.cur = (f, n); s.busy_until = s.now + dur; s.busy_us += dur
    def run(s, until_us):
        while s.now < until_us:
            t = min([until_us] + [n.next_event() for n in s.nodes] + ([s.busy_until] if s.cur else []))
            if t <= s.now: t = s.now + 10
            t = int(min(t, until_us))
            for n in s.nodes: n.run_until(t)
            s.now = t; s._service()
    def run_for(s, ms): s.run(s.now + int(ms * 1000))

# ---------------- protocol helpers (what a PC tool does) ----------------
CMD = dict(Read=1, Write=2, WriteAll=20, WriteAllVal=21, WriteAllComplete=22, BurnSettings=30, Version=31, Sleep=32)
def f32(x): return struct.unpack('<I', struct.pack('<f', x))[0]

class Tool(PyNode):
    """Stand-in for the PC configuration layer. Talks the real dingoFW parameter protocol."""
    def __init__(s, bus, bitrate=1000000):
        super().__init__('tool', bitrate); s.bus = bus; s.rxlog = []; s.on_rx = s.rxlog.append
    def _wait(s, base, cmd, ms=100):
        end = s.bus.now + ms * 1000
        while s.bus.now < end:
            s.bus.run(min(end, s.bus.now + 500))
            for f in s.rxlog:
                if f.id == base and f.data[0] == cmd: s.rxlog.clear(); return f
        return None
    def write(s, base, index, sub, value, reply_base=None):
        s.rxlog.clear(); s.send(base + 1, bytes([CMD['Write'], index & 255, index >> 8, sub]) + struct.pack('<I', value & 0xFFFFFFFF))
        return s._wait(base if reply_base is None else reply_base, CMD['Write'])
    def read(s, base, index, sub):
        s.rxlog.clear(); s.send(base + 1, bytes([CMD['Read'], index & 255, index >> 8, sub, 0, 0, 0, 0]))
        f = s._wait(base, CMD['Read']); return None if f is None else struct.unpack('<I', f.data[4:8])[0]
    def burn(s, base):
        s.rxlog.clear(); s.send(base + 1, bytes([CMD['BurnSettings'], 1, 3, 8, 0, 0, 0, 0]))
        f = s._wait(base, CMD['BurnSettings']); return bool(f and f.data[4])
    def sleep(s, base):
        """Sleep request (comms/request_msg.cpp: cmd 32 + 'QUIT' on base + 1). The board posts an acknowledge but
        stops in the same device-thread cycle, so the acknowledge may never leave it: do not wait for it."""
        s.rxlog.clear(); s.send(base + 1, bytes([CMD['Sleep']]) + b'QUIT' + bytes(3)); s.bus.run_for(50)
    def read_all(s, base, ms=3000):
        """Read All (cmd 10): [(index, sub, value)] in the board's table order and the board's CRC, or None."""
        s.rxlog.clear(); s.send(base + 1, bytes([10, 0, 0, 0, 0, 0, 0, 0])); vals = []; end = s.bus.now + ms * 1000
        while s.bus.now < end:
            s.bus.run(s.bus.now + 1000)
            for f in s.rxlog:
                if f.id != base: continue
                if f.data[0] == 11: vals.append((f.data[1] | f.data[2] << 8, f.data[3], struct.unpack('<I', f.data[4:8])[0]))
                if f.data[0] == 12: s.rxlog.clear(); return vals, struct.unpack('<I', f.data[4:8])[0]
            s.rxlog.clear()
        return None
    def write_all(s, base, vals, crc, batch=20, gap_ms=2):
        """Write All as dingoConfig does it (cmd 20, 21 per value, 22 with count + CRC). True = the board applied it."""
        if s._send_wait(base, bytes([20, 0, 0, 0, 0, 0, 0, 0]), 20) is None: return False
        for i, (ix, sub, v) in enumerate(vals):
            s.send(base + 1, bytes([21, ix & 255, ix >> 8, sub]) + struct.pack('<I', v))
            if i % batch == batch - 1: s.bus.run_for(gap_ms)
        s.bus.run_for(20)
        f = s._send_wait(base, bytes([22, len(vals) & 255, len(vals) >> 8, 0]) + struct.pack('<I', crc), 22, ms=500)
        return bool(f and f.data[3] == 1)
    def _send_wait(s, base, payload, cmd, ms=100):
        s.rxlog.clear(); s.send(base + 1, payload); return s._wait(base, cmd, ms)
    def version(s, base):
        s.rxlog.clear(); s.send(base + 1, bytes([CMD['Version'], 0, 0, 0, 0, 0, 0, 0])); f = s._wait(base, CMD['Version'])
        return None if f is None else (f.data[4], f.data[5], (f.data[6] << 8) | f.data[7])

class Status:
    """Decodes the cyclic status frames of one board (base + 2 + n), like a dashboard would."""
    def __init__(s, base): s.base = base; s.m = {}; s.last = -1
    def feed(s, f):
        n = f.id - s.base - 2
        if 0 <= n < NUM_TX_MSGS and not f.ide: s.m[n] = f.data; s.last = f.t
    def di(s): return struct.unpack('<H', s.m[STATUS_MSG][0:2])[0] if STATUS_MSG in s.m else None
    def an_mv(s): return struct.unpack('<H', s.m[STATUS_MSG][2:4])[0] if STATUS_MSG in s.m else None
    def batt(s): return struct.unpack('<H', s.m[0][4:6])[0] / 10 if 0 in s.m else None
    def total(s): return struct.unpack('<H', s.m[0][2:4])[0] if 0 in s.m else None
    def dev_state(s): return s.m[0][1] & 15 if 0 in s.m else None
    def pdm_type(s): return s.m[0][1] >> 4 if 0 in s.m else None
    def current(s, i): return struct.unpack('<H', s.m[1 + i // 4][2 * (i % 4):2 * (i % 4) + 2])[0] if (1 + i // 4) in s.m else None
    def out_state(s, i): return (s.m[3][i // 2] >> (4 * (i % 2))) & 15 if 3 in s.m else None
    def board_temp_x10(s): return struct.unpack('<H', s.m[0][6:8])[0] if 0 in s.m else None          # MCP9808, msg 0
    def die_temp_x10(s): return struct.unpack('<h', s.m[STATUS_MSG][6:8])[0] if STATUS_MSG in s.m else None   # STM32 die, status msg
    def thermal_flags(s): return s.m[3][7] if 3 in s.m else None     # msg 3 byte 7: bit 0 over warn, 1 critical soon, 2 critical
STATE = ['Off', 'On', 'Overcurrent', 'Fault']
# MCU safety messages (core/safety.h): type Warning 'R', src Init (MsgSrc::Init = 16), data 0 = what happened
SRC_INIT = 16
MSG_WDG_RESET, MSG_BOR_RESET, MSG_BOR_LOW_VBAT, MSG_BOR_FAILED = 1, 2, 3, 4

# ---------------- thermal (Dan r5a / r3c / r7a, docs/firmware-thermal-plan.md) ----------------
TEMP_INDEX = 0x7F00                                  # custom-pdm thermal parameter block (core/param_defs.h THERMAL_PARAM_BASE)
TEMP_PARAM = {'warn': 0, 'crit': 1, 'hyst': 2, 'soon': 4}   # sub-index; 3 = critical-exempt output mask
TEMP_EXEMPT_SUB = 3
TEMP_DEFAULT = {'warn': 98, 'crit': 104, 'hyst': 6, 'soon': 5}  # expected factory defaults, board A (port_boards.py: its FEA sensor map, hwtemp; stock 55 / 80)
# board B (ADR-2026-11-20-presim-findings item 1): from its FEA sensor map and part ratings (tools/verify_thermal_box.py)
TEMP_DEFAULT_B = {'warn': 98, 'crit': 104, 'hyst': 6, 'soon': 5}
def temp_default(model): return TEMP_DEFAULT_B if model['fw'] == 'custompdm_b' else TEMP_DEFAULT
FLAG_WARN, FLAG_SOON, FLAG_CRIT = 1, 2, 4            # msg 3 byte 7
# ---------------- wake-up set (Dan B2): param 0x7F00 sub 5, bit i = digital input i may wake; default none ----------------
WAKE_SUB = 5
SRC_CONFIG = 10                                      # MsgSrc::Config (core/enums.h): refused wake mask warning, type 'R'
WRITE_ALL_OUT_OF_RANGE = 26                          # MsgCmd::WriteAllOutOfRange
def exti_lines(b):
    """EXTI line -> pin armed on it ('PC9'), from the sim's EXTI model (one port per line number)."""
    return {p: f'P{"ABCDEFGH"[b.L.sim_exti_port(p)]}{p}' for p in range(16) if b.L.sim_exti_port(p) >= 0}
FAN = ('A2', 1)                                      # fan output: board A unit 2, OUT2 (firmware index 1)
FAN_ON_C, FAN_OFF_C = 45.0, 40.0                     # Dan s12a; source = hottest of A2 / A1 / B (s13a)
FAN_SLOTS = dict(cond0=26, virt0=11, canin0=24)      # port_boards.py FAN_COND0 / FAN_VIRT0 / FAN_CANIN0 (0-based)
SHED = dict(cond0=28, virt0=14, on=(70.0, 75.0), off=(65.0, 70.0))   # prefilled, disabled load-shed example (port.h)
def die_temp_can(c, vdda=3.3, cal30=943, cal110=1199):
    """Die temperature x10 the firmware should send for a die at c deg C: the sensor model (0.76 V at 25 C,
    2.5 mV/C, as in sim_core.cpp and PdmAdcCan.cs), one 12-bit ADC sample, then GetTemperature() in port.cpp."""
    raw = int((0.76 + (c - 25.0) * 0.0025) / vdda * 4095.0 + 0.5)
    return int((30.0 + (raw - cal30) / (cal110 - cal30) * 80.0) * 10.0)
