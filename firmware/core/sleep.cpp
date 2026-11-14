#include "sleep.h"
#include "device.h"
#include "port.h"
#include "can.h"
#include "usb.h"
#include "status.h"
#include "mcu_utils.h"
#include "device_config.h"
#if SLEEP_LOW_POWER
#include "hw_devices.h"
#endif

#if CAN_SLEEP
// Static variables that were in pdm.cpp
static uint8_t nNumOutputsOn;
static uint8_t nLastNumOutputsOn;
static uint32_t nAllOutputsOffTime;
static bool bLastUsbConnected;
static uint32_t nUsbDisconnectedTime;

// External variables from pdm.cpp that we need access to
extern DeviceConfig stConfig;
extern bool bSleepRequest;
extern Profet pf[NUM_OUTPUTS];

bool CheckEnterSleep()
{
    bool bEnterSleep = false;

    // Count number of outputs on
    nNumOutputsOn = 0;
    for (int i = 0; i < NUM_OUTPUTS; i++)
    {
        if (GetOutputState(i) != ProfetState::Off)
            nNumOutputsOn++;
    }

    // All outputs just turned off, save time - wait SLEEP_TIMEOUT before sleep
    if ((nNumOutputsOn == 0) && (nLastNumOutputsOn > 0))
    {
        nAllOutputsOffTime = SYS_TIME;
    }
    nLastNumOutputsOn = nNumOutputsOn;

    //USB disconnected, save time - wait SLEEP_TIMEOUT before sleep
    if (!GetUsbConnected() && bLastUsbConnected)
        nUsbDisconnectedTime = SYS_TIME;

    bLastUsbConnected = GetUsbConnected();

    // Had issue with SYS_TIME being < GetLastCanRxTime when msgs come in quickly
    // Check that SYS_TIME is greater than or equal to GetLastCanRxTime
    uint32_t sys = SYS_TIME;
    uint32_t canLast = GetLastCanRxTime();
    uint32_t nCanRxIdleTime;
    if (sys >= canLast)
        nCanRxIdleTime = sys - canLast;
    else
        nCanRxIdleTime = 0;

    // No outputs on, no CAN msgs received and no USB connected
    // Go to sleep after timeout
    bEnterSleep = stConfig.stDevice.bSleepEnabled &&
                  (nNumOutputsOn == 0) &&
                  (nLastNumOutputsOn == 0) &&
                  !GetUsbConnected() &&
                  ((SYS_TIME - nUsbDisconnectedTime) > SLEEP_TIMEOUT) &&
                  ((SYS_TIME - nAllOutputsOffTime) > SLEEP_TIMEOUT) &&
                  (nCanRxIdleTime > SLEEP_TIMEOUT);

    if (nCanRxIdleTime > SLEEP_TIMEOUT)
    {
        nCanRxIdleTime = SYS_TIME - GetLastCanRxTime();
    }

    return bEnterSleep || bSleepRequest;
}

void EnableLineEventWithPull(ioline_t line, InputPull pull) 
{
    uint32_t eventMode = PAL_EVENT_MODE_BOTH_EDGES;
    
    switch(pull) {
        case InputPull::Up:
            eventMode |= PAL_STM32_PUPDR_PULLUP;
            break;
        case InputPull::Down:
            eventMode |= PAL_STM32_PUPDR_PULLDOWN;
            break;
        default:
            eventMode |= PAL_STM32_PUPDR_FLOATING;
            break;
    }
    
    palEnableLineEvent(line, eventMode);
}

#if SLEEP_LOW_POWER
// custom-pdm (Dan s7a): lowest standby draw. Every PROFET to sleep / OFF mode (IN, DEN, DSEL low), MCP9808 alert
// output off and shutdown (0.1 uA typ instead of 200 uA, DS25095A Table 1-1). The status and error LEDs (PC1, PC0)
// are already switched off by States() (core/device.cpp) before EnterSleep. Nothing is restored here: the MCU
// resets on wake-up (EnterStopMode), and the normal start-up sets DEN high again (Profet constructor) and puts the
// MCP9808 back in continuous conversion (MCP9808::Init) before any current or temperature is read.
static void EnterLowPower()
{
    for (uint8_t i = 0; i < NUM_OUTPUTS; i++)
        pf[i].Sleep();

    // Result not needed: if it fails (I2C error, or a chip still locked by older firmware) the sensor stays on
    tempSensor.EnterShutdown();
}
#endif

void EnterSleep()
{
    #if SLEEP_LOW_POWER
    EnterLowPower();
    #endif

    // Set wakeup sources

    // Digital inputs change detection, with configured pullup or pulldown
    // custom-pdm: an EXTI line serves one port only, so a board may leave inputs out of the wake-up set
    // (bit i = digital input i may wake the device). Default: all inputs, as stock.
#ifndef WAKE_DIG_INPUT_MASK
#define WAKE_DIG_INPUT_MASK 0xFFFFFFFFU
#endif
    for(uint8_t i = 0; i < NUM_DIG_INPUTS; i++)
    {
        if (WAKE_DIG_INPUT_MASK & (1U << i))
            EnableLineEventWithPull(digIn[i].GetLine(), stConfig.stDigInput[i].ePull);
    }

    // CAN receive detection
    palSetLineMode(LINE_CAN_RX, PAL_MODE_INPUT);
    palEnableLineEvent(LINE_CAN_RX, PAL_EVENT_MODE_BOTH_EDGES | PAL_STM32_PUPDR_FLOATING);

    // USB detection
    palSetLineMode(LINE_USB_DP, PAL_MODE_INPUT);
    palEnableLineEvent(LINE_USB_DP, PAL_EVENT_MODE_BOTH_EDGES | PAL_STM32_PUPDR_FLOATING);
    palSetLineMode(LINE_USB_DM, PAL_MODE_INPUT);
    palEnableLineEvent(LINE_USB_DM, PAL_EVENT_MODE_BOTH_EDGES | PAL_STM32_PUPDR_FLOATING);

    EnterStopMode();
}

#endif