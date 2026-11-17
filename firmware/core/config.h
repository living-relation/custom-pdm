#pragma once

#include <cstdint>
#include "port.h"
#include "enums.h"
#include "dbc.h"
#include "virtual_input.h"
#include "flasher.h"
#include "can_input.h"
#include "can_output.h"
#include "counter.h"
#include "condition.h"
#include "timer.h"
#include "math_block.h"
#if NUM_OUTPUTS > 0
#include "profet.h"
#endif
#if HAS_WIPERS > 0
#include "wiper.h"
#endif
#if HAS_STARTER_DISABLE > 0
#include "starter.h"
#endif
#if NUM_KEYPADS > 0
#include "keypad.h"
#endif
#if NUM_DIG_INPUTS > 0
#include "digital_input.h"
#endif
#if NUM_DIG_OUTPUTS > 0
#include "digital_output.h"
#endif
#if NUM_ANALOG_INPUTS > 0
#include "analog_input.h"
#endif  

// custom-pdm: THERMAL_LIMIT_PARAMS / SLEEP_LOW_POWER / WAKE_INPUT_PARAM (off unless a board's port.h sets them)
#include "custom_options.h"

#if PRO_FEATURES
#include "lookup_table.h" // custom-pdm (T1)
#endif

#if PRO_FEATURES
// custom-pdm: 0x030A = 0x020A + master retry input (Config_Device), output protection extras (Config_OutputExt) and
// lookup tables (Config_Table), all at the end of their structs. A FRAM holding 0x020A falls back to the defaults.
#define CONFIG_VERSION 0x030A //custom-pdm: + P1 trip time, P2 min current, P3 master retry, T1 tables
#elif THERMAL_LIMIT_PARAMS
// custom-pdm: high byte = custom-pdm layout revision (counts up when our fields change), low byte = the upstream
// version it extends (development 0x000A). 0x010A: thermal fields; 0x020A: + wake-input mask (B2). Upstream counts
// up from 0x000A in the low byte, our older builds used 0x0106-0x0108 and 0x010A, so no stored config of another
// layout can match it and such a FRAM falls back to the defaults.
#define CONFIG_VERSION 0x020A //custom-pdm: upstream 0x000A + board temperature limits, critical-exempt outputs, critical-soon margin, wake-input mask in Config_Device
#else
#define CONFIG_VERSION 0x000A //Increment when config structure changes
#endif

struct Config_Device{
  uint16_t nConfigVersion;
  uint16_t nBaseId;
  CanBitrate eCanSpeed[2]; // per bus, [1] unused on single bus boards
  bool bCanFilterEnabled;

  //Not used by all devices
  bool bSleepEnabled;
  bool bDisableDigInWake;
  bool bDisableCanWake;
  bool bConnectUsbToCan;
  uint16_t nMuteCanTxInput;
  uint16_t nForceSleepInput;

  #if THERMAL_LIMIT_PARAMS
  uint8_t nTempWarn;      //deg C: above it, state OverTemp (outputs unchanged)
  uint8_t nTempCrit;      //deg C: at or above it, all outputs off
  uint8_t nTempCritHyst;  //deg C: outputs come back below nTempCrit - nTempCritHyst
  uint16_t nCritExemptMask; //bit i = output i keeps following its input during critical (Dan s10b: the fan output)
  uint8_t nTempCritSoonMargin; //deg C: "critical soon" from nTempCrit - margin up to critical (0 = off; Dan s11c)
  #endif
  #if WAKE_INPUT_PARAM
  uint16_t nWakeInputMask; //bit i = digital input i may wake the device from sleep (Dan B2; default none, CAN and USB only)
  #endif
  #if PRO_FEATURES
  uint16_t nMasterRetryInput; //custom-pdm (P3): var index; its rising edge clears Overcurrent / Fault on every output (0 = off)
  #endif
};

struct DeviceConfig{
  Config_Device stDevice;
  Config_VirtualInput stVirtualInput[NUM_VIRT_INPUTS];
  Config_Flasher stFlasher[NUM_FLASHERS];
  Config_CanInput stCanInput[NUM_CAN_INPUTS];
  Config_CanOutput stCanOutput[NUM_CAN_OUTPUTS];
  Config_Counter stCounter[NUM_COUNTERS];
  Config_Condition stCondition[NUM_CONDITIONS];
  #if NUM_TIMERS > 0
  Config_Timer stTimer[NUM_TIMERS];
  #endif
  #if NUM_MATH > 0
  Config_Math stMath[NUM_MATH];
  #endif

  #if NUM_DIG_INPUTS > 0
  Config_DigInput stDigInput[NUM_DIG_INPUTS];
  #endif
  #if NUM_OUTPUTS > 0
  Config_Output stOutput[NUM_OUTPUTS];
  #endif
  #if HAS_WIPERS 
  Config_Wiper stWiper;
  #endif
  #if HAS_STARTER_DISABLE
  Config_Starter stStarter;
  #endif
  #if NUM_KEYPADS > 0
  Config_Keypad stKeypad[NUM_KEYPADS];
  #endif
  #if NUM_DIG_OUTPUTS > 0
  Config_DigOutput stDigOutput[NUM_DIG_OUTPUTS];
  #endif
  #if NUM_ANALOG_INPUTS > 0
  Config_AnalogInput stAnalogInput[NUM_ANALOG_INPUTS];
  #endif
  #if PRO_FEATURES
  Config_OutputExt stOutputExt[NUM_OUTPUTS]; //custom-pdm (P1 / P2): block 0x7D00 + output
  Config_Table stTable[NUM_TABLES];          //custom-pdm (T1): block 0x7E00 + table
  #endif
};

#if PRO_FEATURES
// custom-pdm: config + its CRC (config_ext.cpp) must fit the board's MB85RC64 FRAM (64 Kbit = 8192 bytes)
static_assert(sizeof(DeviceConfig) + sizeof(uint32_t) <= 8192, "config does not fit the 8 KB FRAM");
#endif

extern DeviceConfig stConfig;
extern DeviceConfig stConfigTemp; // Used for staging new config before applying

void InitConfig();
bool WriteConfig();