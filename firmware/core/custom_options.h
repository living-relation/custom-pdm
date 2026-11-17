#pragma once

// custom-pdm build options. A board turns one on in its port.h (custompdm_a / _b, made by
// tools_custom/port_boards.py); stock boards leave them out and keep stock behaviour.
//   THERMAL_LIMIT_PARAMS: settable board-temperature limits, self-recovering critical shutdown, a failed MCP9808
//                         read is "no reading" (docs/firmware-thermal-plan.md section 7)
//   SLEEP_LOW_POWER:      PROFET IN / DEN / DSEL low and MCP9808 shutdown in sleep (core/sleep.cpp)
//   WAKE_INPUT_PARAM:     per-input "may wake" setting, param 0x7F00 sub 5, checked for shared wake lines (core/sleep.cpp)
//   PRO_FEATURES:         pro-PDM parity gaps (docs/feature-parity.md P1 P2 P3 T1): overcurrent trip time and
//                         open-load flag per output (block 0x7D00 + o), master retry (0x7F00 sub 6), 1D lookup
//                         tables (0x7E00 + n); new vars at the end of the var map (VAR_MAP_PRO_VARS in port.h)
//   PWM_FREQ_INPUT:       PWM frequency taken from a variable (tach-style output: RPM x pulses per rev / 60), param
//                         block 0x7C00 + output (functions/pwm.cpp UpdateVariableFrequency)
#include "port.h"

#ifndef THERMAL_LIMIT_PARAMS
#define THERMAL_LIMIT_PARAMS 0
#endif
#ifndef SLEEP_LOW_POWER
#define SLEEP_LOW_POWER 0
#endif
#ifndef WAKE_INPUT_PARAM
#define WAKE_INPUT_PARAM 0
#endif
#ifndef PRO_FEATURES
#define PRO_FEATURES 0
#endif
#if PRO_FEATURES && !(THERMAL_LIMIT_PARAMS && WAKE_INPUT_PARAM && defined(NUM_TABLES) && defined(VAR_MAP_PRO_VARS))
#error "PRO_FEATURES needs THERMAL_LIMIT_PARAMS + WAKE_INPUT_PARAM (block 0x7F00 sub 0-5, custom CONFIG_VERSION), NUM_TABLES and VAR_MAP_PRO_VARS"
#endif
#ifndef PWM_FREQ_INPUT
#define PWM_FREQ_INPUT 0
#endif
#if PWM_FREQ_INPUT && !PRO_FEATURES
#error "PWM_FREQ_INPUT needs PRO_FEATURES (CONFIG_VERSION 0x040A = the 0x030A layout + its fields)"
#endif
#if WAKE_INPUT_PARAM && !(THERMAL_LIMIT_PARAMS && CAN_SLEEP)
#error "WAKE_INPUT_PARAM needs THERMAL_LIMIT_PARAMS (param block 0x7F00, custom CONFIG_VERSION) and CAN_SLEEP"
#endif
