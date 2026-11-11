"""Write bench.resc: three boards (A unit 1, A unit 2, B) and a test CAN node on one Renode CAN hub.
Pin tables come from firmware/sim/pdmsim.py (written from docs/firmware-pin-map.md, not from the firmware),
so a wrong pin in the firmware shows up as a failed test, as in the host simulation.
usage: gen_bench.py <work dir with repl + models> <folder with the .elf files> <firmware/sim dir> <output .resc>"""
import sys, os
work, fw, simdir, out = sys.argv[1:5]
sys.path.insert(0, simdir)
import pdmsim as ps

VBAT = 13.8
# Factory calibration words the firmware reads from system memory (boards/cortex-m4/mcu_utils.h).
# Values as in firmware/sim/include/mcu_utils.h: VREFINT 1.21 V at 3.3 V = 1502 counts; TS_CAL1 / TS_CAL2 example values.
CAL = {0x1FFF7A2A: 1502, 0x1FFF7A2C: 943, 0x1FFF7A2E: 1199}
BOARDS = [('a1', ps.BOARD_A, 'custompdm_a_unit1.elf'), ('a2', ps.BOARD_A, 'custompdm_a_unit2.elf'), ('b', ps.BOARD_B, 'custompdm_b_unit1.elf')]

L = [f'include @{work}/models/PdmNvicFix.cs', f'include @{work}/models/STM32DMA_Circ.cs', f'include @{work}/models/PdmI2C.cs', f'include @{work}/models/PdmAdcCan.cs',
     'emulation CreateCANHub "bus"', '']
for name, model, elf in BOARDS:
    L += [f'mach create "{name}"', f'machine LoadPlatformDescription @{work}/stm32f446re.repl',
          'macro reset', '"""', f'    sysbus LoadELF @{fw}/{elf}']
    L += [f'    sysbus WriteWord {a:#x} {v}' for a, v in CAL.items()]
    L += ['"""', 'runMacro $reset', 'connector Connect sysbus.can1 bus']
    # the DMA model warns on every write of the error-interrupt enable / clear bits it does not implement
    L += ['logLevel 3 sysbus.dma1', 'logLevel 3 sysbus.dma2', 'sysbus.rettobaseFix Install']
    for o in model['outputs']:
        L.append(f'sysbus.adc1 AddOutput "{o[0]}" "{o[1]}" "{o[2] or ""}" {o[3]} "{o[4]}" {ps.KILIS[o[5]]}')
    L += [f'sysbus.adc1 Vbat {VBAT}', f'sysbus.adc1 SenseResistor {ps.RSENSE}',
          f'sysbus.adc1 SetPinVolts "{model["batt"]}" {VBAT * 4700.0 / (47000.0 + 4700.0):.5f}', '']
L += ['mach create "ecu"', 'machine LoadPlatformDescriptionFromString "ecu: CAN.PDM_CanNode @ sysbus 0x40006400"',
      'connector Connect sysbus.ecu bus', '']
open(out, 'w', newline='\n').write('\n'.join(L))
print('wrote', out)
