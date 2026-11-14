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

// custom-pdm: THERMAL_LIMIT_PARAMS / SLEEP_LOW_POWER (off unless a board's port.h sets them)
#include "custom_options.h"

#if THERMAL_LIMIT_PARAMS
#define CONFIG_VERSION 0x0108 //custom-pdm: stock 0x0006 + board temperature limits + critical-exempt outputs + critical-soon margin in Config_Device
#else
#define CONFIG_VERSION 0x0006 //Increment when config structure changes
#endif

struct Config_Device{
  uint16_t nConfigVersion;
  uint16_t nBaseId;
  CanBitrate eCanSpeed;
  bool bCanFilterEnabled;

  //Not used by all devices
  bool bSleepEnabled;
  bool bConnectUsbToCan;

  #if THERMAL_LIMIT_PARAMS
  uint8_t nTempWarn;      //deg C: above it, state OverTemp (outputs unchanged)
  uint8_t nTempCrit;      //deg C: at or above it, all outputs off
  uint8_t nTempCritHyst;  //deg C: outputs come back below nTempCrit - nTempCritHyst
  uint16_t nCritExemptMask; //bit i = output i keeps following its input during critical (Dan s10b: the fan output)
  uint8_t nTempCritSoonMargin; //deg C: "critical soon" from nTempCrit - margin up to critical (0 = off; Dan s11c)
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
};

extern DeviceConfig stConfig;
extern DeviceConfig stConfigTemp; // Used for staging new config before applying

void InitConfig();
bool WriteConfig();