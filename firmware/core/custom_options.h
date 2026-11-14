#pragma once

// custom-pdm build options. A board turns one on in its port.h (custompdm_a / _b, made by
// tools_custom/port_boards.py); stock boards leave them out and keep stock behaviour.
//   THERMAL_LIMIT_PARAMS: settable board-temperature limits, self-recovering critical shutdown, a failed MCP9808
//                         read is "no reading" (docs/firmware-thermal-plan.md section 7)
//   SLEEP_LOW_POWER:      PROFET IN / DEN / DSEL low and MCP9808 shutdown in sleep (core/sleep.cpp)
#include "port.h"

#ifndef THERMAL_LIMIT_PARAMS
#define THERMAL_LIMIT_PARAMS 0
#endif
#ifndef SLEEP_LOW_POWER
#define SLEEP_LOW_POWER 0
#endif
