#pragma once

// custom-pdm build options. A board turns one on in its port.h (custompdm_a / _b, made by
// tools_custom/port_boards.py); stock boards leave them out and keep stock behaviour.
//   THERMAL_LIMIT_PARAMS: settable board-temperature limits, self-recovering critical shutdown, a failed MCP9808
//                         read is "no reading" (docs/firmware-thermal-plan.md section 7)
//   SLEEP_LOW_POWER:      PROFET IN / DEN / DSEL low and MCP9808 shutdown in sleep (core/sleep.cpp)
//   WAKE_INPUT_PARAM:     per-input "may wake" setting, param 0x7F00 sub 5, checked for shared wake lines (core/sleep.cpp)
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
#if WAKE_INPUT_PARAM && !(THERMAL_LIMIT_PARAMS && CAN_SLEEP)
#error "WAKE_INPUT_PARAM needs THERMAL_LIMIT_PARAMS (param block 0x7F00, custom CONFIG_VERSION) and CAN_SLEEP"
#endif
