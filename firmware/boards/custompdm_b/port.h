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