"""S4: a 'default ON' output at power-up while the ECU is already commanding it OFF. Is there an ON pulse?"""
import sys, pdmsim as ps
SO = sys.argv[1] if len(sys.argv) > 1 else '/tmp/simout'
bus = ps.Bus(); tool = ps.Tool(bus, 1000000); b = ps.Board(ps.BOARD_A, 'A1', SO); bus.add(tool, b); bus.run_for(1200)
W = lambda i, s, v: tool.write(0x500, i, s, v)
for sub, val in [(4, 0x4F0), (5, 2), (6, 1), (11, 0), (12, ps.f32(1.0)), (2, 500), (1, 1), (0, 1)]: W(0x1300 + 2, sub, val)       # command bit 2
for sub, val in [(4, 0x4F0), (5, 24), (6, 8), (11, 0), (12, ps.f32(165.0)), (2, 500), (1, 1), (0, 1)]: W(0x1300 + 31, sub, val)   # link alive
for sub, val in [(2, b.var_canin(2)), (3, 1), (4, 1), (5, b.var_canin(31)), (0, 1)]: W(0x1400, sub, val)                            # cmd OR NOT alive
for sub, val in [(1, b.var_virt(0)), (0, 1)]: W(0x1000 + 2, sub, val)
tool.burn(0x500); fr = b.fram()
for ecu_period_ms, phase in ((20, 3), (20, 13), (50, 30), (100, 60), (100, 99)):
    bus = ps.Bus(); ecu = ps.PyNode('ecu', 1000000); b = ps.Board(ps.BOARD_A, 'A1', SO, fram=fr); bus.add(ecu, b, ps.PyNode('another node', 1000000))   # another node acknowledges ECU frames, as the other boards do
    ecu.every(ecu_period_ms * 1000, lambda t: ecu.send(0x4F0, bytes([0, 0, 0, 0xA5, 0, 0, 0, 0])), phase * 1000)
    on_t = off_t = None
    while bus.now < 1_500_000:
        bus.run_for(0.2); lv = b.level('PC6')
        if lv and on_t is None: on_t = bus.now
        if on_t and not lv and off_t is None: off_t = bus.now
    print(f'ECU frame every {ecu_period_ms} ms (phase {phase}), command OFF: output 3 pulses ON at {on_t/1000:.1f} ms after power-up for {(off_t - on_t)/1000:.1f} ms' if on_t else f'ECU every {ecu_period_ms} ms: no pulse')
