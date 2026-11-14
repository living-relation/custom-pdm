#pragma once

#include "hal.h"
#include "enums.h"

#define PDM_TYPE 0 //0 = PDM

#define PROCESS_STACK 0x1000

#define HAS_SE_LEDS TRUE
#define HAS_USB TRUE
#define HAS_I2C TRUE
#define HAS_EXT_TEMP_SENSOR TRUE
#define HAS_EXT_MEMORY TRUE
#define HAS_BATT_VOLT_SENSE TRUE
#define CAN_SLEEP TRUE

#define NUM_OUTPUTS 8
#define NUM_DIG_OUTPUTS 0
#define NUM_DIG_INPUTS 7
// Wake-up: DI3 (PC10) and DI4 (PC11) share EXTI 10 / 11 with DI1 (PA10) and USB D- (PA11), which keep them
#define WAKE_DIG_INPUT_MASK 0x73U
#define NUM_ANALOG_INPUTS 1
#define ANALOG_IN_DIVIDER 1.5f // input board 10k/20k: 0-5 V -> 0-3.33 V
#define NUM_VIRT_INPUTS 16
#define NUM_CAN_INPUTS 32
#define NUM_CAN_OUTPUTS 32
#define NUM_FLASHERS 4
#define NUM_WIPER_INTER_DELAYS 6
#define NUM_WIPER_SPEED_MAP 8
#define NUM_COUNTERS 4
#define NUM_CONDITIONS 32
#define NUM_KEYPADS 2
#define HAS_WIPERS TRUE
#define HAS_STARTER_DISABLE TRUE

#define KEYPAD_MAX_BUTTONS 20
#define KEYPAD_MAX_ANALOG_INPUTS 4
#define KEYPAD_MAX_DIALS 2

#define HAS_NEOPIXELS FALSE

#define VAR_MAP_SYS_VARS 5
#define VAR_MAP_WIPER_VARS 6

#define VAR_MAP_SIZE ( \
    VAR_MAP_SYS_VARS + \
    (NUM_DIG_INPUTS * 1) + \
    (NUM_ANALOG_INPUTS * 4) + \
    (NUM_DIG_OUTPUTS * 1) + \
    (NUM_CAN_INPUTS * 2) + \
    (NUM_VIRT_INPUTS * 1) + \
    (NUM_OUTPUTS * 4) + \
    (NUM_FLASHERS * 1) + \
    (NUM_CONDITIONS * 1) + \
    (NUM_COUNTERS * 1) + \
    VAR_MAP_WIPER_VARS + \
    (NUM_KEYPADS * (KEYPAD_MAX_BUTTONS + KEYPAD_MAX_DIALS + KEYPAD_MAX_ANALOG_INPUTS)) \
)

#define MAILBOX_SIZE 128
#define DEVICE_THREAD_STACK 2048

#define NUM_TX_MSGS 28
// Factory defaults (used only when the FRAM holds no valid config). All can be changed over CAN/USB later.
#ifndef PDM_UNIT
#define PDM_UNIT 1
#endif
#define DEFAULT_BASE_ID (PDM_UNIT == 2 ? 0x520 : 0x500)
#define DEFAULT_CAN_BITRATE CanBitrate::Bitrate_1000K
#define DEFAULT_RESET_MODE ProfetResetMode::Count // 3 tries (nResetLimit), 1 s apart, then Fault
// Board temperature limits are config params (device 0x0000 sub 5-7) and critical recovers by itself
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
// Fans (r3c, r7a): board A unit 2 (A2) OUT2 (index 1) is always on and wired inside the box to both fans; its X1 cavity T is spare.
// A2 is the board at the fan end (enclosure v2b F1 fan bay, east end); OUT2 has the east-most J3 pad (tied with OUT5)
// and the east-most driver (U8). Other units: -1 = no fan output
#define FAN_OUTPUT (PDM_UNIT == 2 ? 1 : -1)
// Dan s10b: the fan output keeps running through a critical shutdown (device param 0x0000 sub 8, bit i = output i)
#define DEFAULT_CRIT_EXEMPT_MASK (FAN_OUTPUT >= 0 ? (1U << (FAN_OUTPUT & 15)) : 0U)
#define DEFAULT_OUT_ENABLED(i) ((int)(i) == FAN_OUTPUT ? 1 : 0)
#define DEFAULT_OUT_INPUT(i) ((int)(i) == FAN_OUTPUT ? 1 : 0) // var 1 = always true: on whenever the board is awake
#define DEFAULT_OUT_CURRENT_LIMIT(i) ((int)(i) == FAN_OUTPUT ? F(1.0f) : F(20.0f)) // two Sunon MF30101V1 = 0.13 A max
#define DEFAULT_OUT_INRUSH_LIMIT(i) ((int)(i) == FAN_OUTPUT ? F(2.0f) : F(50.0f))
// Load-shed example (r5a), NOT active: conditions 29-32 and virtual inputs 15-16 (1-based) come prefilled but
// disabled. Level l (0 sheds first): latch VI = (temp >= SHED_ON_C OR itself) AND NOT (temp <= SHED_OFF_C).
// How to enable: docs/firmware-thermal-plan.md section 7. Var-map indices follow InitVarMap (core/device.cpp).
#define VAR_BOARD_TEMP 3
#define VAR_VIRT(i) (VAR_MAP_SYS_VARS + NUM_DIG_INPUTS + NUM_DIG_OUTPUTS + NUM_ANALOG_INPUTS * 4 + NUM_CAN_INPUTS * 2 + (i))
#define VAR_COND(i) (VAR_VIRT(NUM_VIRT_INPUTS) + NUM_OUTPUTS * 4 + NUM_FLASHERS + (i))
#define SHED_COND0 (NUM_CONDITIONS - 4)       // level l: hot = SHED_COND0 + 2 l, cool = SHED_COND0 + 2 l + 1
#define SHED_VIRT0 (NUM_VIRT_INPUTS - 2)      // level l: latch = SHED_VIRT0 + l
#define SHED_ON_C(l) ((l) ? 75.0f : 70.0f)    // example values; real ones after the bench measurements (r6c)
#define SHED_OFF_C(l) ((l) ? 70.0f : 65.0f)
#define IS_SHED_COND(i) ((int)(i) >= SHED_COND0)
#define SHED_COND_HOT(i) (((int)(i) - SHED_COND0) % 2 == 0)
#define SHED_COND_LEVEL(i) (((int)(i) - SHED_COND0) / 2)
#define DEFAULT_COND_INPUT(i) (IS_SHED_COND(i) ? VAR_BOARD_TEMP : 0)
#define DEFAULT_COND_OPERATOR(i) static_cast<uint32_t>(!IS_SHED_COND(i) ? Operator::Equal : SHED_COND_HOT(i) ? Operator::GreaterThanOrEqual : Operator::LessThanOrEqual)
#define DEFAULT_COND_ARG(i) (!IS_SHED_COND(i) ? F(0.0f) : F(SHED_COND_HOT(i) ? SHED_ON_C(SHED_COND_LEVEL(i)) : SHED_OFF_C(SHED_COND_LEVEL(i))))
#define IS_SHED_VIRT(i) ((int)(i) >= SHED_VIRT0)
#define DEFAULT_VIRT_VAR(i, n) (!IS_SHED_VIRT(i) ? 0 : (n) == 0 ? VAR_COND(SHED_COND0 + 2 * ((i) - SHED_VIRT0)) : (n) == 1 ? VAR_VIRT(i) : VAR_COND(SHED_COND0 + 2 * ((i) - SHED_VIRT0) + 1))
#define DEFAULT_VIRT_COND(i, n) static_cast<uint32_t>(IS_SHED_VIRT(i) && (n) == 0 ? BoolOperator::Or : BoolOperator::And)
#define DEFAULT_VIRT_NOT(i, n) (IS_SHED_VIRT(i) && (n) == 2 ? 1 : 0)

#define ADC1_NUM_CHANNELS 8
#define ADC1_BUF_DEPTH 1

#define BTS7002_1EPP_KILIS 22950
#define BTS7008_2EPA_KILIS 5950
#define BTS70012_1ESP_KILIS 35000

#define SLEEP_TIMEOUT 30000

#define SYS_TIME TIME_I2MS(chVTGetSystemTimeX())

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