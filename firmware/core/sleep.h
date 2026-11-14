#pragma once

#include "ch.h"
#include "hal.h"
#include "config.h"
#include "enums.h"

// Sleep management functions extracted from pdm.cpp

bool CheckEnterSleep();
void EnterSleep();
void EnableLineEventWithPull(ioline_t line, InputPull pull);

#if WAKE_INPUT_PARAM
// custom-pdm (Dan B2): inputs of a wake-input mask that cannot be armed as wake sources (bit i = input i)
uint16_t WakeInputMaskBadBits(uint32_t mask);
// true = mask can be used; false = refused, and a CAN warning (type Warning, src Config) has been sent
bool CheckWakeInputMask(uint32_t mask);
#endif