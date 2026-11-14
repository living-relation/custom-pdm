#pragma once
#include <cstdint>
// Factory calibration values (typical, STM32F446 datasheet): VREFINT 1.21 V at 3.3 V
#define STM32_TEMP_3V3_30C ((uint16_t)943)
#define STM32_TEMP_3V3_110C ((uint16_t)1199)
#define STM32_VREF_INT_CAL ((uint16_t)1502)
// dingoFW development names (boards/stm32f446/mcu_utils.h): same typical values, taken at VDDA = 3.3 V
#define STM32_TS_CAL1 STM32_TEMP_3V3_30C
#define STM32_TS_CAL2 STM32_TEMP_3V3_110C
#define STM32_TS_CAL1_TEMP 30.0
#define STM32_TS_CAL2_TEMP 110.0
#define STM32_CAL_VDDA 3.3
// F4 has a single EXTI pending register (EXTI->PR); the sim keeps it as a plain variable (sim_core.cpp)
extern uint32_t simExtiPending;
#define EXTI_PENDING simExtiPending
void EnterStopMode();
void RequestBootloader();
void CheckBootloaderRequest(void);
