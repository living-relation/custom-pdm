#!/usr/bin/env python3
"""Create custompdm_a / custompdm_b board folders from stock dingoFW boards.
Source of pin truth: custom-pdm docs/firmware-pin-map.md (2026-11-10)."""
import re, shutil, sys, pathlib
FW = pathlib.Path(sys.argv[1]); B = FW/'boards'

# Factory CAN base IDs (Dan D4a 2026-11-10: user-editable, param 0x0000 sub 0). dingoFW development uses base + 0
# (to PC tool), base + 1 (from PC tool) and base + 2 + n for cyclic msgs n = 0..NUM_TX_MSGS-1: 40 IDs per board with
# our 38 msgs, so boards sit 0x40 apart (0x20 overlapped; s15a port, 2026-11-14).
BASE_A1, BASE_A2, BASE_B = 0x500, 0x540, 0x580
CYCLIC_TX_OFFSET = 2          # core/device_config.h
# Device type in msg 0 byte 1 bits 4-7 (4 bits, 0-15). Upstream uses 0-4 (dingoPDM, Max, PT-DPDM, CANBoard, v8)
# and counts up; ours sit at the top of the range (dingoConfig looks types up by value, not position).
TYPE_A, TYPE_B = 14, 15
STATUS_MSG = 37               # custom-pdm status frame: first free cyclic msg after upstream's 0-36
NUM_TX = STATUS_MSG + 1
# Factory output current limit = each output's rating (Dan w3a, 2026-11-16; ratings: docs/box-connectors.md), amps:
# board A OUT1-8, board B OUT1-4 (studs, BTS70012), board B OUT5-8 (BTS7004), the fan output A2 OUT2 (two Sunon
# MF30101V1 = 0.13 A max). Inrush limits stay 50 A (fan 2 A): above every rating; during the inrush time (1 s) only the
# inrush limit is checked, after it only the current limit (functions/profet.cpp), so neither needs the other.
LIMIT_A, LIMIT_B_STUD, LIMIT_B, LIMIT_FAN = 7.5, 31.0, 15.0, 1.0
fl = lambda v: f'F({v:.1f}f)'

def rep(s, old, new, n=1):
    assert s.count(old) == n, (old, s.count(old))
    return s.replace(old, new)

def clone(src, dst):
    d = B/dst
    if d.exists(): shutil.rmtree(d)
    shutil.copytree(B/src, d)
    (d/f'{src}.ld').rename(d/f'{dst}.ld')
    mk = (d/'board.mk').read_text().replace(src, dst); (d/'board.mk').write_text(mk)
    return d

def pin_name(txt, port, pin):
    m = re.search(rf'#define (GPIO{port}_\w+)\s+{pin}U\n', txt)
    return m.group(1)

def set_pin(txt, port, pin, mode, pupd, odr='LOW', speed='LOW', af=0):
    n = pin_name(txt, port, pin)
    def sub(pat, rep):
        nonlocal txt
        txt, k = re.subn(pat, rep, txt)
        assert k == 1, (port, pin, pat, k)
    sub(rf'PIN_MODE_\w+\({n}\)', f'PIN_MODE_{mode}({n})')
    sub(rf'PIN_PUPDR_\w+\({n}\)', f'PIN_PUPDR_{pupd}({n})')
    sub(rf'PIN_ODR_\w+\({n}\)', f'PIN_ODR_{odr}({n})')
    sub(rf'PIN_OSPEED_\w+\({n}\)', f'PIN_OSPEED_{speed}({n})')
    sub(rf'PIN_AFIO_AF\({n}, \d+U\)', f'PIN_AFIO_AF({n}, {af}U)')
    sub(rf'PIN_OTYPE_\w+\({n}\)', f'PIN_OTYPE_PUSHPULL({n})')
    return txt

def set_lines(txt, lines, name):
    a = txt.index('/*\n * IO lines assignments.'); b = txt.index('/*====', a)
    body = '/*\n * IO lines assignments.\n */\n' + ''.join(
        f'#define {k:<27} PAL_LINE(GPIO{v[0]}, {v[1:]}U)\n' for k, v in lines) + '\n\n'
    txt = txt[:a] + body + txt[b:]
    return re.sub(r'#define BOARD_NAME\s+".*"', f'#define BOARD_NAME                  "{name}"', txt)

FACTORY = '''// Factory defaults (used only when the FRAM holds no valid config). All can be changed over CAN/USB later.
#ifndef PDM_UNIT
#define PDM_UNIT 1
#endif
#define DEFAULT_BASE_ID %s
#define DEFAULT_CAN_BITRATE CanBitrate::Bitrate_1000K
#define DEFAULT_RESET_MODE ProfetResetMode::Count // 3 tries (nResetLimit), 1 s apart, then Fault'''
# Thermal protection + fans + load-shed example (Dan r5a, r3c, r7a, 2026-11-13; docs/firmware-thermal-plan.md)
THERMAL = '''// Board temperature limits are config params (0x7F00 sub 0-2, core/param_defs.h) and critical recovers by itself
// (core/device.cpp). Defaults in core/param_defs.h: stock 55 / 80 deg C, recovery 6 deg C below critical.
#define THERMAL_LIMIT_PARAMS 1
// MCP9808 reading (core/device.cpp UpdateBoardTemp): a failed I2C read is "no reading" (last valid temperature and
// warn / critical state kept). 4 failures in a row (1 s at the 250 ms read period) = one CAN error message, src
// TempSensor. Readings in the first 100 ms after the sensor starts are skipped (> 3 x tCONV 30 ms typ at 0.5 C).
#define TEMP_SENSOR_FAIL_LIMIT 4
#define TEMP_SENSOR_SETTLE_MS 100
// Sleep (Dan s7a, core/sleep.cpp EnterLowPower): every PROFET IN / DEN / DSEL low, MCP9808 alert off + shutdown
// (status / error LEDs: already off, stock States()). So the MCP9808 limits are not locked: SHDN cannot be set
// while a lock bit is set (DS25095A Register 5-2).
#define SLEEP_LOW_POWER 1
// Fans (r7a): @FAN_NOTE@
#define FAN_OUTPUT @FAN_OUTPUT@
// Fan switching (Dan 2026-11-14, replaces r3c "always on"): OFF at power-up, ON when the hottest board reaches FAN_ON_C,
// OFF again when every board is at or below FAN_OFF_C (set / reset latch, docs/firmware-thermal-plan.md section 3a).
// Factory defaults (Dan 2026-11-14: s12a on 45 / off 40 C, s13a hottest of the three boards) - change them here:
#define FAN_ON_C 45.0f        // s12a
#define FAN_OFF_C 40.0f       // s12a
#define FAN_REMOTE_TEMPS 1    // s13a: 1 = hottest of A2's own MCP9808 and A1 / B board temperature (their msg 0 over CAN); 0 = A2 only (s13b)
// Dan s10b: the fan output keeps running through a critical shutdown (param 0x7F00 sub 3, bit i = output i)
#define DEFAULT_CRIT_EXEMPT_MASK (FAN_OUTPUT >= 0 ? (1U << (FAN_OUTPUT & 15)) : 0U)
#define DEFAULT_OUT_ENABLED(i) ((int)(i) == FAN_OUTPUT ? 1 : 0)
#define DEFAULT_OUT_INPUT(i) ((int)(i) == FAN_OUTPUT ? VAR_VIRT(FAN_VIRT0 + 2) : 0) // the fan latch virtual input
// Factory current limit = the output's rating (w3a, port_boards.py LIMIT_*); the fan output 1 A
#define DEFAULT_OUT_CURRENT_LIMIT(i) ((int)(i) == FAN_OUTPUT ? @LIMIT_FAN@ : @OUT_LIMIT@)
#define DEFAULT_OUT_INRUSH_LIMIT(i) ((int)(i) == FAN_OUTPUT ? F(2.0f) : F(50.0f))
// Load-shed example (r5a), NOT active: conditions 29-32 and virtual inputs 15-16 (1-based) come prefilled but
// disabled. Level l (0 sheds first): latch VI = (temp >= SHED_ON_C OR itself) AND NOT (temp <= SHED_OFF_C).
// How to enable: docs/firmware-thermal-plan.md section 7. Var-map indices follow InitVarMap (core/device.cpp).
#define VAR_BOARD_TEMP 3
#define VAR_VIRT(i) (VAR_MAP_SYS_VARS + NUM_DIG_INPUTS + NUM_DIG_OUTPUTS + NUM_ANALOG_INPUTS * 4 + NUM_CAN_INPUTS * 2 + (i))
#define VAR_COND(i) (VAR_VIRT(NUM_VIRT_INPUTS) + NUM_OUTPUTS * 4 + NUM_FLASHERS + (i))
#define VAR_CANIN(i) (VAR_MAP_SYS_VARS + NUM_DIG_INPUTS + NUM_DIG_OUTPUTS + NUM_ANALOG_INPUTS * 4 + 2 * (i)) // fOutput (fVal = + 1)
#define SHED_COND0 (NUM_CONDITIONS - 4)       // level l: hot = SHED_COND0 + 2 l, cool = SHED_COND0 + 2 l + 1
#define SHED_VIRT0 (NUM_VIRT_INPUTS - 2)      // level l: latch = SHED_VIRT0 + l
#define SHED_ON_C(l) ((l) ? 75.0f : 70.0f)    // example values; real ones after the bench measurements (r6c)
#define SHED_OFF_C(l) ((l) ? 70.0f : 65.0f)
#define IS_SHED_COND(i) ((int)(i) >= SHED_COND0)
#define SHED_COND_HOT(i) (((int)(i) - SHED_COND0) % 2 == 0)
#define SHED_COND_LEVEL(i) (((int)(i) - SHED_COND0) / 2)
#define IS_SHED_VIRT(i) ((int)(i) >= SHED_VIRT0)
// Fan latch (board with FAN_OUTPUT only), enabled by default. Numbers count from 0 (firmware / parameter index).
//   conditions FAN_COND0 = A2 temp >= FAN_ON_C, FAN_COND0 + 1 = A2 temp <= FAN_OFF_C
//   CAN inputs FAN_CANIN0 + 0 / 1 = A1 hot / cool, + 2 / 3 = B hot / cool: msg 0 bytes 6-7 (board temp x10, signed),
//     >= FAN_ON_C / <= FAN_OFF_C, 1 s time-out. On a time-out (or before the first frame) both read 0: that board can
//     neither turn the fans on nor let them turn off, so a lost reading is never "cool"; A2's own sensor always counts.
//   virtual inputs FAN_VIRT0 = any hot (OR), + 1 = all cool (AND), + 2 = fan latch = (any hot OR itself) AND NOT all cool
#define HAS_FAN (FAN_OUTPUT >= 0)
#define FAN_REMOTE (HAS_FAN && FAN_REMOTE_TEMPS)
#define FAN_COND0 (SHED_COND0 - 2)
#define FAN_VIRT0 (SHED_VIRT0 - 3)
#define FAN_CANIN0 24                          // slots 25-28 (1-based); the S2 "one PDM" recipe uses 1-8 and 32
#define FAN_REMOTE_MSG0(r) ((r) ? @FAN_MSG0_B@ : @FAN_MSG0_A1@)   // B / A1 factory base ID (@BASE_B@ / @BASE_A1@) + 2 = cyclic msg 0 (made by port_boards.py)
#define IS_FAN_COND(i) (HAS_FAN && ((int)(i) == FAN_COND0 || (int)(i) == FAN_COND0 + 1))
#define IS_FAN_VIRT(i) (HAS_FAN && (int)(i) >= FAN_VIRT0 && (int)(i) < FAN_VIRT0 + 3)
#define FAN_VJ(i) ((int)(i) - FAN_VIRT0)
#define IS_FAN_CANIN(i) (FAN_REMOTE && (int)(i) >= FAN_CANIN0 && (int)(i) < FAN_CANIN0 + 4)
#define FAN_CANIN_HOT(i) (((int)(i) - FAN_CANIN0) % 2 == 0)
#define DEFAULT_COND_ENABLED(i) (IS_FAN_COND(i) ? 1 : 0)
#define DEFAULT_COND_INPUT(i) ((IS_SHED_COND(i) || IS_FAN_COND(i)) ? VAR_BOARD_TEMP : 0)
#define DEFAULT_COND_OPERATOR(i) static_cast<uint32_t>(IS_FAN_COND(i) ? ((int)(i) == FAN_COND0 ? Operator::GreaterThanOrEqual : Operator::LessThanOrEqual) : \\
    !IS_SHED_COND(i) ? Operator::Equal : SHED_COND_HOT(i) ? Operator::GreaterThanOrEqual : Operator::LessThanOrEqual)
#define DEFAULT_COND_ARG(i) (IS_FAN_COND(i) ? F((int)(i) == FAN_COND0 ? FAN_ON_C : FAN_OFF_C) : \\
    !IS_SHED_COND(i) ? F(0.0f) : F(SHED_COND_HOT(i) ? SHED_ON_C(SHED_COND_LEVEL(i)) : SHED_OFF_C(SHED_COND_LEVEL(i))))
#define DEFAULT_VIRT_ENABLED(i) (IS_FAN_VIRT(i) ? 1 : 0)
#define DEFAULT_FAN_VIRT_VAR(j, n) ( \\
    (j) == 0 ? ((n) == 0 ? VAR_COND(FAN_COND0) : !FAN_REMOTE ? 0 : VAR_CANIN(FAN_CANIN0 + 2 * ((n) - 1))) : \\
    (j) == 1 ? ((n) == 0 ? VAR_COND(FAN_COND0 + 1) : !FAN_REMOTE ? ((n) == 1 ? 1 : 0) : VAR_CANIN(FAN_CANIN0 + 1 + 2 * ((n) - 1))) : \\
               ((n) == 0 ? VAR_VIRT(FAN_VIRT0) : (n) == 1 ? VAR_VIRT(FAN_VIRT0 + 2) : VAR_VIRT(FAN_VIRT0 + 1)))
#define DEFAULT_VIRT_VAR(i, n) (IS_FAN_VIRT(i) ? DEFAULT_FAN_VIRT_VAR(FAN_VJ(i), n) : \\
    !IS_SHED_VIRT(i) ? 0 : (n) == 0 ? VAR_COND(SHED_COND0 + 2 * ((i) - SHED_VIRT0)) : (n) == 1 ? VAR_VIRT(i) : VAR_COND(SHED_COND0 + 2 * ((i) - SHED_VIRT0) + 1))
#define DEFAULT_VIRT_COND(i, n) static_cast<uint32_t>(IS_FAN_VIRT(i) ? (FAN_VJ(i) == 0 || (FAN_VJ(i) == 2 && (n) == 0) ? BoolOperator::Or : BoolOperator::And) : \\
    IS_SHED_VIRT(i) && (n) == 0 ? BoolOperator::Or : BoolOperator::And)
#define DEFAULT_VIRT_NOT(i, n) ((IS_SHED_VIRT(i) || (IS_FAN_VIRT(i) && FAN_VJ(i) == 2)) && (n) == 2 ? 1 : 0)
#define DEFAULT_CANIN_ENABLED(i) (IS_FAN_CANIN(i) ? 1 : 0)
#define DEFAULT_CANIN_TIMEOUT_ENABLED(i) (IS_FAN_CANIN(i) ? 1 : 0)
#define DEFAULT_CANIN_ID(i) (IS_FAN_CANIN(i) ? FAN_REMOTE_MSG0(((int)(i) - FAN_CANIN0) / 2) : 0)
#define DEFAULT_CANIN_START_BIT(i) (IS_FAN_CANIN(i) ? 48 : 0)
#define DEFAULT_CANIN_BIT_LENGTH(i) (IS_FAN_CANIN(i) ? 16 : 8)
#define DEFAULT_CANIN_FACTOR(i) (IS_FAN_CANIN(i) ? F(0.1f) : F(1.0f))
#define DEFAULT_CANIN_SIGNED(i) (IS_FAN_CANIN(i) ? 1 : 0)
#define DEFAULT_CANIN_OPERATOR(i) static_cast<uint32_t>(!IS_FAN_CANIN(i) ? Operator::Equal : FAN_CANIN_HOT(i) ? Operator::GreaterThanOrEqual : Operator::LessThanOrEqual)
#define DEFAULT_CANIN_OPERAND(i) (!IS_FAN_CANIN(i) ? F(0.0f) : F(FAN_CANIN_HOT(i) ? FAN_ON_C : FAN_OFF_C))'''
# Wake-up from sleep (Dan B2, 2026-11-10): CAN and USB only by default; each input can be made a wake source in the
# config (param 0x7F00 sub 5, bit i = input i). The firmware refuses a mask with both inputs of a shared EXTI line or
# an input on the USB / CAN line (core/sleep.cpp WakeInputMaskBadBits).
WAKE = '''// Wake-up (Dan B2): no input wakes by default (CAN and USB do); per-input "may wake" mask = param 0x7F00 sub 5.
// One wake source per EXTI line, so the firmware refuses a mask with both inputs of a pair or the USB one: %s.
#define WAKE_INPUT_PARAM 1
#define DEFAULT_WAKE_INPUT_MASK 0'''
# Pro-PDM parity gaps (docs/feature-parity.md P1 P2 P3 T1; DECISIONS 2026-11-16 product goal): one build option, so
# stock dingoFW boards stay byte-identical. New vars at the END of the var map (every existing var index unchanged).
PRO = '''// Pro-PDM parity gaps (docs/feature-parity.md, core/custom_options.h PRO_FEATURES): overcurrent trip time and
// open-load flag per output (block 0x7D00 + o), master retry input (0x7F00 sub 6), 4 lookup tables (0x7E00 + n).
#define PRO_FEATURES 1
#define NUM_TABLES 4
#define VAR_MAP_PRO_VARS (NUM_TABLES + NUM_OUTPUTS) // var map end: table outputs 1-4, then undercurrent flag per output'''
VARMAP_END = '    (NUM_KEYPADS * (KEYPAD_MAX_BUTTONS + KEYPAD_MAX_DIALS + KEYPAD_MAX_ANALOG_INPUTS)) \\\n'
VARMAP_PRO = ('    (NUM_KEYPADS * (KEYPAD_MAX_BUTTONS + KEYPAD_MAX_DIALS + KEYPAD_MAX_ANALOG_INPUTS)) + \\\n'
              '    VAR_MAP_PRO_VARS /* custom-pdm: PRO_FEATURES vars */ \\\n')
def thermal(note, fan, out_limit):
    t = THERMAL.replace('@FAN_NOTE@', note).replace('@FAN_OUTPUT@', fan)
    t = t.replace('@LIMIT_FAN@', fl(LIMIT_FAN)).replace('@OUT_LIMIT@', out_limit)
    for k, v in {'@FAN_MSG0_B@': BASE_B + CYCLIC_TX_OFFSET, '@FAN_MSG0_A1@': BASE_A1 + CYCLIC_TX_OFFSET,
                 '@BASE_B@': BASE_B, '@BASE_A1@': BASE_A1}.items():
        t = t.replace(k, f'0x{v:03X}')
    return t
FAN_A = thermal('board A unit 2 (A2) OUT2 (index 1) is wired inside the box to both fans; its X1 cavity T is spare.\n'
                '// A2 is the board at the fan end (enclosure v2b F1 fan bay, east end); OUT2 has the east-most J3 pad (tied with OUT5)\n'
                '// and the east-most driver (U8). Other units: -1 = no fan output', '(PDM_UNIT == 2 ? 1 : -1)', fl(LIMIT_A))
FAN_B = thermal('the fans are on board A unit 2 (see custompdm_a/port.h); none on this board', '-1',
                f'((int)(i) < 4 ? {fl(LIMIT_B_STUD)} : {fl(LIMIT_B)})')
COMMON = [('LED_ERROR','C0'),('LED_STATUS','C1'),('BATT_SENSE','A3'),('USB_VBUS','A9'),
          ('CAN_STANDBY','C12'),('I2C1_SCL','B6'),('I2C1_SDA','B7'),('CAN_RX','B8'),('CAN_TX','B9'),
          ('USB_DM','A11'),('USB_DP','A12'),('SWDIO','A13'),('SWCLK','A14')]
L = lambda items: [('LINE_'+k, v) for k, v in items]

# ---------------- Board A (base dingopdm_v7) ----------------
d = clone('dingopdm_v7', 'custompdm_a')
t = (d/'board.h').read_text()
t = set_lines(t, L([
    ('PF1_2_IS','A0'),('PF1_IN','B10'),('PF2_IN','C8'),('PF1_2_DSEL','C7'),('PF1_2_DEN','B2'),
    ('PF3_4_IS','C3'),('PF3_IN','C6'),('PF4_IN','B12'),('PF3_4_DSEL','B14'),('PF3_4_DEN','B15'),
    ('PF5_6_IS','A1'),('PF5_IN','B1'),('PF6_IN','C4'),('PF5_6_DSEL','C5'),('PF5_6_DEN','B0'),
    ('PF7_8_IS','A2'),('PF7_IN','A7'),('PF8_IN','A4'),('PF7_8_DSEL','A5'),('PF7_8_DEN','A6'),
    ('DI1','A10'),('DI2','C9'),('DI3','C10'),('DI4','C11'),('DI5','B4'),('DI6','C13'),('DI7','B3'),
    ('AIN1','C2')] + COMMON + [('UNUSED','A15')]), 'custom-pdm board A (dingoPDM v7.5 based)')
for port, pin in [('C',10),('C',11),('C',13),('B',3),('B',4)]:   # new digital inputs (ex E1-E3, SWO)
    t = set_pin(t, port, pin, 'INPUT', 'FLOATING')
t = set_pin(t, 'C', 2, 'ANALOG', 'FLOATING')                      # AIN (ex PF2_IS)
t = set_pin(t, 'C', 7, 'OUTPUT', 'PULLDOWN')                      # DSEL1_2 (ex DEN2)
# GPIOx setup comment blocks: stock v7 text, rewritten where it is wrong for board A (u5a): names = the LINE_ defines
# above (docs/firmware-pin-map.md section 3), modes = the VAL_GPIOx_* register values. Comment lines only.
def pin_comment(txt, pin, name, mode):
    txt, k = re.subn(rf'^ \* {pin} +- .*$', f' * {pin:<4} - {name:<25} ({mode}).', txt, flags=re.M)
    assert k == 1, (pin, k)
    return txt
for pin, name, mode in [
        ('PA0', 'PF1_2_IS', 'analog in'), ('PA5', 'PF7_8_DSEL', 'output pushpull pulldown'),
        ('PA9', 'USB_VBUS', 'input floating'), ('PA10', 'DI1', 'input pullup'), ('PA15', 'UNUSED', 'input pullup'),
        ('PB0', 'PF5_6_DEN', 'output pushpull pulldown'), ('PB2', 'PF1_2_DEN', 'output pushpull pulldown'),
        ('PB3', 'DI7', 'input floating'), ('PB4', 'DI5', 'input floating'),     # PB3: stock SWO, board A has no LINE_SWO
        ('PC2', 'AIN1', 'analog input'), ('PC7', 'PF1_2_DSEL', 'output pushpull pulldown'), ('PC9', 'DI2', 'input pullup'),
        ('PC10', 'DI3', 'input floating'), ('PC11', 'DI4', 'input floating'), ('PC13', 'DI6', 'input floating'),
        ('PF0', 'PIN0', 'input pullup'), ('PF1', 'PIN1', 'input pullup'),           # stock: Nucleo ARD_D7 / D8 names
        ('PH0', 'OSC_IN', 'input pullup, HSE crystal'), ('PH1', 'OSC_OUT', 'input pullup, HSE crystal')]:
    t = pin_comment(t, pin, name, mode)
(d/'board.h').write_text(t)

p = (d/'port.h').read_text()
p = p.replace('#define NUM_DIG_INPUTS 2', '#define NUM_DIG_INPUTS 7\n' + WAKE % 'DI1 (PA10) / DI3 (PC10) share EXTI 10, DI4 (PC11) shares EXTI 11 with USB D- (PA11)')
p = rep(p, '#define DEFAULT_BASE_ID 0x0DE', FACTORY % (f'(PDM_UNIT == 2 ? 0x{BASE_A2:03X} : 0x{BASE_A1:03X})') + '\n' + FAN_A + '\n' + PRO)
p = rep(p, VARMAP_END, VARMAP_PRO)
p = p.replace('#define NUM_ANALOG_INPUTS 0', '#define NUM_ANALOG_INPUTS 1\n#define ANALOG_IN_DIVIDER 1.5f // input board 10k/20k: 0-5 V -> 0-3.33 V')
p = rep(p, '#define NUM_TX_MSGS 37', f'#define NUM_TX_MSGS {NUM_TX} // custom-pdm: + msg {STATUS_MSG}')
p = rep(p, '#define DEVICE_TYPE 0', f'#define DEVICE_TYPE {TYPE_A} // custom-pdm board A (stock dingoPDM = 0)')
p = p.replace('    IS1 = 0,\n    IS2,\n', '    IS1_2 = 0,\n    AnIn1, // PC2, ADC1_IN12 (old IS2 slot)\n')
p = p.replace('uint16_t GetAdcRaw(AnalogChannel channel);', 'uint16_t GetAdcRaw(AnalogChannel channel);\nfloat GetAdcVolts(AnalogChannel channel);')
(d/'port.h').write_text(p)

c = (d/'port.cpp').read_text()
c += '\n\nfloat GetAdcVolts(AnalogChannel channel)\n{\n    // Volts at the input-board wire (before the 10k/20k divider)\n    return (GetVDDA() / 4095) * GetAdcRaw(channel) * ANALOG_IN_DIVIDER;\n}\n'
(d/'port.cpp').write_text(c)

h = (d/'hw_devices.cpp').read_text()
h = h.replace('Profet(1, ProfetModel::BTS7002_1EPP, LINE_PF1_IN, LINE_PF1_DEN, LINE_UNUSED, AnalogChannel::IS1,',
              'Profet(1, ProfetModel::BTS7008_2EPA_CH1, LINE_PF1_IN, LINE_PF1_2_DEN, LINE_PF1_2_DSEL, AnalogChannel::IS1_2,')
h = h.replace('Profet(2, ProfetModel::BTS7002_1EPP, LINE_PF2_IN, LINE_PF2_DEN, LINE_UNUSED, AnalogChannel::IS2,',
              'Profet(2, ProfetModel::BTS7008_2EPA_CH2, LINE_PF2_IN, LINE_PF1_2_DEN, LINE_PF1_2_DSEL, AnalogChannel::IS1_2,')
h = h.replace('    Digital_Input(LINE_DI2)};', '    Digital_Input(LINE_DI2),\n' + ''.join(f'    Digital_Input(LINE_DI{i}),\n' for i in range(3,7)) +
              '    Digital_Input(LINE_DI7)};\n\nAnalog_Input analogIn[NUM_ANALOG_INPUTS] = {\n    Analog_Input(AnalogChannel::AnIn1)};')
assert 'IS1_2' in h and 'DI7' in h
(d/'hw_devices.cpp').write_text(h)

def params(d, n_di, outputs8=None):
    q = (d/'params.h').read_text()
    q, k = re.subn(r'// Digital Inputs \(2\)\n#define ALL_DIGITAL_INPUT_PARAMS \\\n.*\n',
        f'// Digital Inputs ({n_di})\n#define ALL_DIGITAL_INPUT_PARAMS \\\n    ' +
        ', '.join(f'DIGITAL_INPUT_PARAMS({i})' for i in range(n_di)) +
        '\n\n// Analog Inputs (1)\n#define ALL_ANALOG_INPUT_PARAMS \\\n    ANALOG_INPUT_PARAMS(0)\n', q)
    assert k == 1
    if outputs8:
        q, k = re.subn(r'#define ALL_OUTPUT_PARAMS \\\n.*\n', '#define ALL_OUTPUT_PARAMS \\\n    ' +
            ', '.join(f'OUTPUT_PARAMS({i})' for i in range(8)) + '\n', q); assert k == 1
    (d/'params.h').write_text(q)
params(d, 7)

def msg(d):
    m = (d/'msg.cpp').read_text()
    old = '    stMsg.frame.data8[0] = (GetDigInputVal(1) << 1) + GetDigInputVal(0);'
    assert old in m
    m = m.replace(old, f'    // Byte 0: digital inputs 1-8 (stock layout for 1-2). Inputs 9+ are in msg {STATUS_MSG}.\n'
        '    uint8_t nDi = 0;\n    for (uint8_t i = 0; (i < NUM_DIG_INPUTS) && (i < 8); i++)\n        nDi |= (GetDigInputVal(i) ? 1 : 0) << i;\n    stMsg.frame.data8[0] = nDi;')
    # Msg 3 byte 7 (stock: always 0, no DBC signal): board temperature flags, in every 100 ms frame (Dan s11c)
    old3 = '                           (GetFlasherVal(1) << 1) + GetFlasherVal(0);\n    stMsg.frame.data8[7] = 0;'
    assert m.count(old3) == 1
    m = m.replace(old3, '                           (GetFlasherVal(1) << 1) + GetFlasherVal(0);\n'
        '    stMsg.frame.data8[7] = GetThermalFlags(); // custom-pdm: bit 0 over warn, bit 1 critical soon, bit 2 critical')
    m += '''

CANTxMsg TxMsg@N@()
{
    CANTxMsg stMsg;
    //=======================================================
    // Build Msg @N@ (custom-pdm: all digital inputs, analog input, STM32 die temperature)
    //=======================================================
    CanSetId(stMsg.frame, stConfig.stDevice.nBaseId + CYCLIC_TX_OFFSET + @N@);
    stMsg.frame.DLC = 8; // Bytes to send
    uint16_t nDi = 0;
    for (uint8_t i = 0; i < NUM_DIG_INPUTS; i++)
        nDi |= (GetDigInputVal(i) ? 1 : 0) << i;
    stMsg.frame.data16[0] = nDi;
    stMsg.frame.data16[1] = (uint16_t)analogIn[0].fValMillivolts;
    stMsg.frame.data16[2] = (uint16_t)analogIn[0].fVal;
    stMsg.frame.data16[3] = (uint16_t)(int16_t)(GetTemperature() * 10.0f); // deg C x 10, signed (r5a)

    // custom-pdm (w1): not in the first round. That round is built in InitCan, before the device thread has read any
    // input, so it would show every input OFF and cross-board links would see OFF for 100 ms at key on.
    static bool bFirstRound = true;
    stMsg.bSend = !bFirstRound; // then always sent
    bFirstRound = false;

    return stMsg;
}
'''.replace('@N@', str(STATUS_MSG))
    (d/'msg.cpp').write_text(m)
    last = STATUS_MSG - 1
    mh = (d/'msg.h').read_text()
    mh = rep(mh, f'CANTxMsg TxMsg{last}();', f'CANTxMsg TxMsg{last}();\nCANTxMsg TxMsg{STATUS_MSG}();')
    mh = rep(mh, f'    TxMsg{last}}};', f'    TxMsg{last},\n    TxMsg{STATUS_MSG}}};')
    (d/'msg.h').write_text(mh)
msg(d)
hh = (d/'hw_devices.h').read_text()
if 'analogIn' not in hh:
    hh = hh.replace('extern Digital_Input digIn[NUM_DIG_INPUTS];', 'extern Digital_Input digIn[NUM_DIG_INPUTS];\nextern Analog_Input analogIn[NUM_ANALOG_INPUTS];')
    (d/'hw_devices.h').write_text(hh)

# ---------------- Board B (base dingopdmmax_v1) ----------------
d = clone('dingopdmmax_v1', 'custompdm_b')
t = (d/'board.h').read_text()
t = set_lines(t, L([
    ('PF1_IS','C3'),('PF1_IN','B14'),('PF1_DEN','B13'),('PF2_IS','C2'),('PF2_IN','C7'),('PF2_DEN','C6'),
    ('PF3_IS','A0'),('PF3_IN','B0'),('PF3_DEN','C5'),('PF4_IS','A1'),('PF4_IN','A6'),('PF4_DEN','A5'),
    ('PF5_IS','A2'),('PF5_IN','A8'),('PF6_IS','A4'),('PF6_IN','B10'),('PF5_6_DEN','B12'),
    ('PF7_IS','A7'),('PF7_IN','A15'),('PF8_IS','C4'),('PF8_IN','C8'),('PF7_8_DEN','B15'),
    ('DI1','A10'),('DI2','C9'),('DI3','C14'),('DI4','C15'),('DI5','C13'),('DI6','D2'),('DI7','B4'),
    ('DI8','B5'),('DI9','C10'),('DI10','C11'),('AIN1','B1')] + COMMON +
    [('SWO','B3'),('UNUSED','B2')]), 'custom-pdm board B (dingoPDM-Max based)')
for port, pin in [('A',8),('B',10),('A',15),('C',8),('B',12),('B',15)]:   # IN5-8, DEN5_6, DEN7_8
    t = set_pin(t, port, pin, 'OUTPUT', 'PULLDOWN')
for port, pin in [('A',2),('A',4),('A',7),('C',4),('B',1)]:                # IS5-8, AIN
    t = set_pin(t, port, pin, 'ANALOG', 'FLOATING')
for port, pin in [('C',14),('C',15),('C',13),('D',2),('B',4),('B',5),('C',10),('C',11)]:
    t = set_pin(t, port, pin, 'INPUT', 'FLOATING')
# PB2 (BOOT1) is the only MCU pin with nothing on it = LINE_UNUSED. Input, never an output; pull-down = the BOOT1 level
# the system bootloader needs (the pull only acts while the firmware runs, not during reset).
t = set_pin(t, 'B', 2, 'INPUT', 'PULLDOWN')
(d/'board.h').write_text(t)

p = (d/'port.h').read_text()
p = p.replace('#define NUM_OUTPUTS 4', '#define NUM_OUTPUTS 8')
p = p.replace('#define NUM_DIG_INPUTS 2', '#define NUM_DIG_INPUTS 10\n' + WAKE % 'DI1 (PA10) / DI9 (PC10) share EXTI 10, DI10 (PC11) shares EXTI 11 with USB D- (PA11)')
p = rep(p, '#define DEFAULT_BASE_ID 0x0DE', FACTORY % f'0x{BASE_B:03X}' + '\n' + FAN_B + '\n' + PRO)
p = rep(p, VARMAP_END, VARMAP_PRO)
p = p.replace('#define NUM_ANALOG_INPUTS 0', '#define NUM_ANALOG_INPUTS 1\n#define ANALOG_IN_DIVIDER 1.5f // input board 10k/20k: 0-5 V -> 0-3.33 V')
# Max sends msgs 0-34; board B uses the v7 msg layout (0-36, copied below) plus our status msg
p = rep(p, '#define NUM_TX_MSGS 35', f'#define NUM_TX_MSGS {NUM_TX} // custom-pdm: v7 msgs 0-36 + msg {STATUS_MSG}')
p = rep(p, '#define DEVICE_TYPE 1', f'#define DEVICE_TYPE {TYPE_B} // custom-pdm board B (stock dingoPDM-Max = 1)')
p = p.replace('#define ADC1_NUM_CHANNELS 7', '#define ADC1_NUM_CHANNELS 12')
p = p.replace('#define BTS70012_1ESP_KILIS 35000', '#define BTS70012_1ESP_KILIS 35000\n#define BTS7004_1EPP_KILIS 20000 // Infineon BTS7004-1EPP datasheet, typ. at IL(NOM)')
p = p.replace('    IS3,\n    IS4,\n', '    IS3,\n    IS4,\n    IS5,\n    IS6,\n    IS7,\n    IS8,\n')
p = p.replace('    BattVolt,\n', '    BattVolt,\n    AnIn1, // PB1, ADC1_IN9\n')
p = p.replace('uint16_t GetAdcRaw(AnalogChannel channel);', 'uint16_t GetAdcRaw(AnalogChannel channel);\nfloat GetAdcVolts(AnalogChannel channel);')
assert 'IS8' in p and 'AnIn1' in p
(d/'port.h').write_text(p)

c = (d/'port.cpp').read_text()
a = c.index('adcsample_t adc1_samples'); b = c.index('msg_t InitAdc()')
c = c[:a] + '''adcsample_t adc1_samples[ADC1_NUM_CHANNELS] = {0};
// 0 = OutIS1 - ADC1_IN13 (PC3)
// 1 = OutIS2 - ADC1_IN12 (PC2)
// 2 = OutIS3 - ADC1_IN0  (PA0)
// 3 = OutIS4 - ADC1_IN1  (PA1)
// 4 = OutIS5 - ADC1_IN2  (PA2)
// 5 = OutIS6 - ADC1_IN4  (PA4)
// 6 = OutIS7 - ADC1_IN7  (PA7)
// 7 = OutIS8 - ADC1_IN14 (PC4)
// 8 = BattVolt - ADC1_IN3 (PA3)
// 9 = AnIn1 - ADC1_IN9 (PB1)
// 10 = TempSensor
// 11 = VRefInt

static const ADCConversionGroup adc1_cfg = {
    .circular = true,
    .num_channels = ADC1_NUM_CHANNELS,
    .end_cb = NULL,
    .error_cb = NULL,
    .cr1 = 0,
    .cr2 = ADC_CR2_SWSTART | ADC_CR2_CONT,
    .smpr1 = ADC_SMPR1_SMP_AN12(ADC_SAMPLE_15) |
             ADC_SMPR1_SMP_AN13(ADC_SAMPLE_15) |
             ADC_SMPR1_SMP_AN14(ADC_SAMPLE_15) |
             ADC_SMPR1_SMP_SENSOR(ADC_SAMPLE_15) |
             ADC_SMPR1_SMP_VREF(ADC_SAMPLE_15),
    .smpr2 = ADC_SMPR2_SMP_AN0(ADC_SAMPLE_15) |
             ADC_SMPR2_SMP_AN1(ADC_SAMPLE_15) |
             ADC_SMPR2_SMP_AN2(ADC_SAMPLE_15) |
             ADC_SMPR2_SMP_AN3(ADC_SAMPLE_15) |
             ADC_SMPR2_SMP_AN4(ADC_SAMPLE_15) |
             ADC_SMPR2_SMP_AN7(ADC_SAMPLE_15) |
             ADC_SMPR2_SMP_AN9(ADC_SAMPLE_15),
    .htr = 0,
    .ltr = 0,
    .sqr1 = 0,
    .sqr2 = ADC_SQR2_SQ7_N(ADC_CHANNEL_IN7) |
            ADC_SQR2_SQ8_N(ADC_CHANNEL_IN14) |
            ADC_SQR2_SQ9_N(ADC_CHANNEL_IN3) |
            ADC_SQR2_SQ10_N(ADC_CHANNEL_IN9) |
            ADC_SQR2_SQ11_N(ADC_CHANNEL_SENSOR) |
            ADC_SQR2_SQ12_N(ADC_CHANNEL_VREFINT),
    .sqr3 = ADC_SQR3_SQ1_N(ADC_CHANNEL_IN13) |
            ADC_SQR3_SQ2_N(ADC_CHANNEL_IN12) |
            ADC_SQR3_SQ3_N(ADC_CHANNEL_IN0) |
            ADC_SQR3_SQ4_N(ADC_CHANNEL_IN1) |
            ADC_SQR3_SQ5_N(ADC_CHANNEL_IN2) |
            ADC_SQR3_SQ6_N(ADC_CHANNEL_IN4)};

''' + c[b:]
c += '\n\nfloat GetAdcVolts(AnalogChannel channel)\n{\n    // Volts at the input-board wire (before the 10k/20k divider)\n    return (GetVDDA() / 4095) * GetAdcRaw(channel) * ANALOG_IN_DIVIDER;\n}\n'
(d/'port.cpp').write_text(c)

shutil.copy(B/'dingopdm_v7'/'port_pwm.h', d/'port_pwm.h')   # all 8 software-PWM timers (TIM3,4,5,9,10,11,12,13)
h = (d/'hw_devices.cpp').read_text()
old4 = '    Profet(4, ProfetModel::BTS70012_1ESP, LINE_PF4_IN, LINE_PF4_DEN, LINE_UNUSED, AnalogChannel::IS4, &PWMD9, &pwm9Cfg, PwmChannel::Ch1)};'
assert old4 in h
new = old4[:-2] + ',\n' + ''.join(
    f'    Profet({n}, ProfetModel::BTS7004_1EPP, LINE_PF{n}_IN, LINE_PF{den}_DEN, LINE_UNUSED, AnalogChannel::IS{n}, &PWMD{tim}, &pwm{tim}Cfg, PwmChannel::Ch1){end}\n'
    for n, den, tim, end in [(5,'5_6',10,','),(6,'5_6',11,','),(7,'7_8',12,','),(8,'7_8',13,'};')])
h = h.replace(old4, new)
h = h.replace('    Digital_Input(LINE_DI2)};', '    Digital_Input(LINE_DI2),\n' + ''.join(f'    Digital_Input(LINE_DI{i}),\n' for i in range(3,10)) +
              '    Digital_Input(LINE_DI10)};\n\nAnalog_Input analogIn[NUM_ANALOG_INPUTS] = {\n    Analog_Input(AnalogChannel::AnIn1)};')
(d/'hw_devices.cpp').write_text(h)
shutil.copy(B/'dingopdm_v7'/'params.h', d/'params.h')   # 8 outputs, 8 starter-disable entries
params(d, 10)
shutil.copy(B/'dingopdm_v7'/'msg.cpp', d/'msg.cpp'); shutil.copy(B/'dingopdm_v7'/'msg.h', d/'msg.h')  # 8-output status layout
msg(d)
hh = (d/'hw_devices.h').read_text()
if 'analogIn' not in hh:
    hh = hh.replace('extern Digital_Input digIn[NUM_DIG_INPUTS];', 'extern Digital_Input digIn[NUM_DIG_INPUTS];\nextern Analog_Input analogIn[NUM_ANALOG_INPUTS];')
    (d/'hw_devices.h').write_text(hh)
for b in ('custompdm_a', 'custompdm_b'):
    f = B/b/'hw_devices.h'; s = f.read_text()
    if 'analog_input.h' not in s: f.write_text(s.replace('#include "digital_input.h"', '#include "digital_input.h"\n#include "analog_input.h"'))
    f = B/b/'board.mk'; s = f.read_text()
    if 'functions/analog_input.cpp' not in s: f.write_text(s.replace('functions/profet.cpp \\\n', 'functions/profet.cpp \\\n\t\t\t\tfunctions/analog_input.cpp \\\n'))
print('ok')
