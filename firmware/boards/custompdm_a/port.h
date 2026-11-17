#pragma once

#include "hal.h"
#include "enums.h"

#define DEVICE_TYPE 14 // custom-pdm board A (stock dingoPDM = 0)

#define PROCESS_STACK 0x1000

#define HAS_SE_LEDS TRUE
#define HAS_USB TRUE
#define HAS_I2C1 TRUE
#define HAS_I2C2 FALSE
#define HAS_EXT_TEMP_SENSOR TRUE
#define HAS_EXT_MEMORY TRUE
#define EXT_MEMORY_I2C I2CD1
#define HAS_BATT_VOLT_SENSE TRUE
#define CAN_SLEEP TRUE

#define NUM_OUTPUTS 8
#define NUM_DIG_OUTPUTS 0
#define NUM_DIG_INPUTS 7
// Wake-up (Dan B2): no input wakes by default (CAN and USB do); per-input "may wake" mask = param 0x7F00 sub 5.
// One wake source per EXTI line, so the firmware refuses a mask with both inputs of a pair or the USB one: DI1 (PA10) / DI3 (PC10) share EXTI 10, DI4 (PC11) shares EXTI 11 with USB D- (PA11).
#define WAKE_INPUT_PARAM 1
#define DEFAULT_WAKE_INPUT_MASK 0
#define NUM_ANALOG_INPUTS 1
#define ANALOG_IN_DIVIDER 1.5f // input board 10k/20k: 0-5 V -> 0-3.33 V
#define NUM_VIRT_INPUTS 16
#define NUM_CAN_INPUTS 32
#define NUM_CAN_OUTPUTS 32
#define NUM_CAN_BUSES 1
#define NUM_FLASHERS 4
#define NUM_WIPER_INTER_DELAYS 6
#define NUM_WIPER_SPEED_MAP 8
#define NUM_COUNTERS 4
#define NUM_CONDITIONS 32
#define NUM_MATH 8
#define NUM_TIMERS 8
#define NUM_KEYPADS 2
#define HAS_WIPERS TRUE
#define HAS_STARTER_DISABLE TRUE

#define KEYPAD_MAX_BUTTONS 20
#define KEYPAD_MAX_ANALOG_INPUTS 4
#define KEYPAD_MAX_DIALS 2

#define HAS_NEOPIXELS FALSE

//Always false
//Always true
//State
//Temperature sensor
//Battery voltage
#define VAR_MAP_SYS_VARS 5

#define VAR_MAP_WIPER_VARS 6

#define VAR_MAP_SIZE ( \
    VAR_MAP_SYS_VARS + \
    (NUM_DIG_INPUTS * 3) + \
    (NUM_ANALOG_INPUTS * 4) + \
    (NUM_DIG_OUTPUTS * 1) + \
    (NUM_CAN_INPUTS * 2) + \
    (NUM_VIRT_INPUTS * 1) + \
    (NUM_OUTPUTS * 4) + \
    (NUM_FLASHERS * 1) + \
    (NUM_CONDITIONS * 1) + \
    (NUM_COUNTERS * 1) + \
    (NUM_TIMERS * 2) + \
    (NUM_MATH * 1) + \
    VAR_MAP_WIPER_VARS + \
    (NUM_KEYPADS * (KEYPAD_MAX_BUTTONS + KEYPAD_MAX_DIALS + KEYPAD_MAX_ANALOG_INPUTS)) \
)

#define MAILBOX_SIZE 256
#define DEVICE_THREAD_STACK 2048
#define CAN_THREAD_STACK 512

#define NUM_TX_MSGS 38 // custom-pdm: + msg 37
// Factory defaults (used only when the FRAM holds no valid config). All can be changed over CAN/USB later.
#ifndef PDM_UNIT
#define PDM_UNIT 1
#endif
#define DEFAULT_BASE_ID (PDM_UNIT == 2 ? 0x540 : 0x500)
#define DEFAULT_CAN_BITRATE CanBitrate::Bitrate_1000K
#define DEFAULT_RESET_MODE ProfetResetMode::Count // 3 tries (nResetLimit), 1 s apart, then Fault
// Board temperature limits are config params (0x7F00 sub 0-2, core/param_defs.h) and critical recovers by itself
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
// Fans (r7a): board A unit 2 (A2) OUT2 (index 1) is wired inside the box to both fans; its X1 cavity T is spare.
// A2 is the board at the fan end (enclosure v2b F1 fan bay, east end); OUT2 has the east-most J3 pad (tied with OUT5)
// and the east-most driver (U8). Other units: -1 = no fan output
#define FAN_OUTPUT (PDM_UNIT == 2 ? 1 : -1)
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
#define DEFAULT_OUT_CURRENT_LIMIT(i) ((int)(i) == FAN_OUTPUT ? F(1.0f) : F(7.5f))
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
#define FAN_REMOTE_MSG0(r) ((r) ? 0x582 : 0x502)   // B / A1 factory base ID (0x580 / 0x500) + 2 = cyclic msg 0 (made by port_boards.py)
#define IS_FAN_COND(i) (HAS_FAN && ((int)(i) == FAN_COND0 || (int)(i) == FAN_COND0 + 1))
#define IS_FAN_VIRT(i) (HAS_FAN && (int)(i) >= FAN_VIRT0 && (int)(i) < FAN_VIRT0 + 3)
#define FAN_VJ(i) ((int)(i) - FAN_VIRT0)
#define IS_FAN_CANIN(i) (FAN_REMOTE && (int)(i) >= FAN_CANIN0 && (int)(i) < FAN_CANIN0 + 4)
#define FAN_CANIN_HOT(i) (((int)(i) - FAN_CANIN0) % 2 == 0)
#define DEFAULT_COND_ENABLED(i) (IS_FAN_COND(i) ? 1 : 0)
#define DEFAULT_COND_INPUT(i) ((IS_SHED_COND(i) || IS_FAN_COND(i)) ? VAR_BOARD_TEMP : 0)
#define DEFAULT_COND_OPERATOR(i) static_cast<uint32_t>(IS_FAN_COND(i) ? ((int)(i) == FAN_COND0 ? Operator::GreaterThanOrEqual : Operator::LessThanOrEqual) : \
    !IS_SHED_COND(i) ? Operator::Equal : SHED_COND_HOT(i) ? Operator::GreaterThanOrEqual : Operator::LessThanOrEqual)
#define DEFAULT_COND_ARG(i) (IS_FAN_COND(i) ? F((int)(i) == FAN_COND0 ? FAN_ON_C : FAN_OFF_C) : \
    !IS_SHED_COND(i) ? F(0.0f) : F(SHED_COND_HOT(i) ? SHED_ON_C(SHED_COND_LEVEL(i)) : SHED_OFF_C(SHED_COND_LEVEL(i))))
#define DEFAULT_VIRT_ENABLED(i) (IS_FAN_VIRT(i) ? 1 : 0)
#define DEFAULT_FAN_VIRT_VAR(j, n) ( \
    (j) == 0 ? ((n) == 0 ? VAR_COND(FAN_COND0) : !FAN_REMOTE ? 0 : VAR_CANIN(FAN_CANIN0 + 2 * ((n) - 1))) : \
    (j) == 1 ? ((n) == 0 ? VAR_COND(FAN_COND0 + 1) : !FAN_REMOTE ? ((n) == 1 ? 1 : 0) : VAR_CANIN(FAN_CANIN0 + 1 + 2 * ((n) - 1))) : \
               ((n) == 0 ? VAR_VIRT(FAN_VIRT0) : (n) == 1 ? VAR_VIRT(FAN_VIRT0 + 2) : VAR_VIRT(FAN_VIRT0 + 1)))
#define DEFAULT_VIRT_VAR(i, n) (IS_FAN_VIRT(i) ? DEFAULT_FAN_VIRT_VAR(FAN_VJ(i), n) : \
    !IS_SHED_VIRT(i) ? 0 : (n) == 0 ? VAR_COND(SHED_COND0 + 2 * ((i) - SHED_VIRT0)) : (n) == 1 ? VAR_VIRT(i) : VAR_COND(SHED_COND0 + 2 * ((i) - SHED_VIRT0) + 1))
#define DEFAULT_VIRT_COND(i, n) static_cast<uint32_t>(IS_FAN_VIRT(i) ? (FAN_VJ(i) == 0 || (FAN_VJ(i) == 2 && (n) == 0) ? BoolOperator::Or : BoolOperator::And) : \
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
#define DEFAULT_CANIN_OPERAND(i) (!IS_FAN_CANIN(i) ? F(0.0f) : F(FAN_CANIN_HOT(i) ? FAN_ON_C : FAN_OFF_C))

#define ADC1_NUM_CHANNELS 8
#define ADC1_BUF_DEPTH 1

#define BTS7002_1EPP_KILIS 22950
#define BTS7008_2EPA_KILIS 5950
#define BTS70012_1ESP_KILIS 35000

#define SLEEP_TIMEOUT 30000

// Milliseconds from the 64-bit timestamp, truncated to 32 bits so it wraps cleanly
// every ~49.7 days. Always compare as (SYS_TIME - start), never as absolute times.
#define SYS_TIME ((uint32_t)(chVTGetTimeStamp() / (CH_CFG_ST_FREQUENCY / 1000)))

static const float ALWAYS_FALSE = 0.0f;
static const float ALWAYS_TRUE = 1.0f;
 
enum class AnalogChannel
{
    IS1_2 = 0,
    AnIn1, // PC2, ADC1_IN12 (old IS2 slot)
    IS3_4,
    IS5_6,
    IS7_8,
    BattVolt,
    TempSensor,
    VRefInt
};

enum class LedType
{
    Status,
    Error
};

const CANConfig &GetCanConfig(CanBitrate bitrate);

const I2CConfig i2cConfig = {
    OPMODE_I2C,
    400000,
    FAST_DUTY_CYCLE_2,
};

msg_t InitAdc();
void DeInitAdc();
uint16_t GetAdcRaw(AnalogChannel channel);
float GetAdcVolts(AnalogChannel channel);
float GetBattVolt();
float GetTemperature();
float GetVDDA();