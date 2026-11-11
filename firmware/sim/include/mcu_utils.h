#pragma once
// Factory calibration values (typical, STM32F446 datasheet): VREFINT 1.21 V at 3.3 V
#define STM32_TEMP_3V3_30C ((uint16_t)943)
#define STM32_TEMP_3V3_110C ((uint16_t)1199)
#define STM32_VREF_INT_CAL ((uint16_t)1502)
void EnterStopMode();
void RequestBootloader();
