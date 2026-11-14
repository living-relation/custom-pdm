#pragma once

#include "hal.h"
#include "enums.h"

#define PDM_TYPE 1 //1 = PDM-MAX 

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
#define NUM_DIG_INPUTS 10
// Wake-up: DI9 (PC10), DI10 (PC11) lose EXTI 10 / 11 to DI1 (PA10) and USB D- (PA11). DI5 (PC13) is alone on EXTI 13, DI6 (PD2) on EXTI 2
#define WAKE_DIG_INPUT_MASK 0x0FFU
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
    (NUM_CAN_INPUTS * 2) + \
    (NUM_ANALOG_INPUTS * 4) + \
    (NUM_DIG_OUTPUTS * 1) + \
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
#define DEFAULT_BASE_ID 0x540
#define DEFAULT_CAN_BITRATE CanBitrate::Bitrate_1000K
#define DEFAULT_RESET_MODE ProfetResetMode::Count // 3 tries (nResetLimit), 1 s apart, then Fault
// Board temperature limits are config params (device 0x0000 sub 5-7) and critical recovers by itself
// (core/device.cpp). Defaults in core/param_defs.h: stock 55 / 80 deg C, recovery 6 deg C below critical.
#define THERMAL_LIMIT_PARAMS 1
// Fans (r3c, r7a): the fans are on board A unit 2 (see custompdm_a/port.h); none on this board
#define FAN_OUTPUT -1
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

#define ADC1_NUM_CHANNELS 12
#define ADC1_BUF_DEPTH 1

#define BTS7002_1EPP_KILIS 22950
#define BTS7008_2EPA_KILIS 5950
#define BTS70012_1ESP_KILIS 35000
#define BTS7004_1EPP_KILIS 20000 // Infineon BTS7004-1EPP datasheet, typ. at IL(NOM)

#define SLEEP_TIMEOUT 30000

#define SYS_TIME TIME_I2MS(chVTGetSystemTimeX())

static const float ALWAYS_FALSE = 0.0f;
static const float ALWAYS_TRUE = 1.0f;

enum class AnalogChannel
{
    IS1 = 0,
    IS2,
    IS3,
    IS4,
    IS5,
    IS6,
    IS7,
    IS8,
    BattVolt,
    AnIn1, // PB1, ADC1_IN9
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