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
#if WAKE_INPUT_PARAM
#include "infomsg.h"
#endif
#include "safety.h" // custom-pdm (MCU_SAFETY)

#if CAN_SLEEP
// Static variables that were in pdm.cpp
static uint8_t nNumOutputsOn;
static uint8_t nLastNumOutputsOn;
static uint32_t nAllOutputsOffTime;
static bool bLastUsbConnected;
static uint32_t nUsbDisconnectedTime;

// External variables from pdm.cpp that we need access to
extern DeviceConfig stConfig;
bool bSleepRequest;
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

    // CAN Rx thread can stamp a time slightly after SYS_TIME was read here,
    // so treat a negative (signed) difference as 0. Wrap-safe.
    int32_t nCanRxDiff = static_cast<int32_t>(SYS_TIME - GetLastCanRxTime());
    uint32_t nCanRxIdleTime = (nCanRxDiff > 0) ? nCanRxDiff : 0;

    // No outputs on, no CAN msgs received and no USB connected
    // Go to sleep after timeout
    bEnterSleep = stConfig.stDevice.bSleepEnabled &&
                  (nNumOutputsOn == 0) &&
                  (nLastNumOutputsOn == 0) &&
                  !GetUsbConnected() &&
                  ((SYS_TIME - nUsbDisconnectedTime) > SLEEP_TIMEOUT) &&
                  ((SYS_TIME - nAllOutputsOffTime) > SLEEP_TIMEOUT) &&
                  (nCanRxIdleTime > SLEEP_TIMEOUT);

    return bEnterSleep || bSleepRequest || *pVarMap[stConfig.stDevice.nForceSleepInput];
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

#if WAKE_INPUT_PARAM
// custom-pdm (Dan B2). An EXTI line number serves one port only: arming a second pin with the same pin number
// moves the line to it and the first pin stops waking (ChibiOS 879cf757 hal_pal_lld.c, asserts off). EnterSleep
// arms the inputs first and CAN RX / USB D+ / D- after them, so an input on one of those line numbers would never
// wake. Refused (bit i = input i): an input on the CAN RX, USB D+ or USB D- line number, and every input of a pair
// that shares a line number. Custom boards: A IN_1 PA10 / IN_3 PC10, IN_4 PC11 = USB D- PA11; B IN_1 PA10 /
// B_IN9 PC10, B_IN10 PC11 = USB D- PA11. The CAN RX line counts even while CAN wake is off (no custom input uses it).
uint16_t WakeInputMaskBadBits(uint32_t mask)
{
    const uint32_t nOtherWake = (1U << PAL_PAD(LINE_CAN_RX)) | (1U << PAL_PAD(LINE_USB_DP)) | (1U << PAL_PAD(LINE_USB_DM));
    uint16_t nBad = 0;
    for (uint8_t i = 0; i < NUM_DIG_INPUTS; i++)
    {
        if (!(mask & (1U << i)))
            continue;
        uint32_t nPad = PAL_PAD(digIn[i].GetLine());
        if (nOtherWake & (1U << nPad))
            nBad |= (1U << i);
        for (uint8_t j = 0; j < NUM_DIG_INPUTS; j++)
        {
            if ((j != i) && (mask & (1U << j)) && (PAL_PAD(digIn[j].GetLine()) == nPad))
                nBad |= (1U << i);
        }
    }
    return nBad;
}

// Warning on the config reply ID (base + CONFIG_TX_OFFSET, like every info message): type Warning 'R', src Config;
// data 0 = refused mask, data 1 = its inputs that cannot wake (bit i = input i), data 2 = the mask still in use
bool CheckWakeInputMask(uint32_t mask)
{
    uint16_t nBad = WakeInputMaskBadBits(mask);
    if (nBad == 0)
        return true;
    SendInfoMsg(MsgType::Warning, MsgSrc::Config, stConfig.stDevice.nBaseId, static_cast<uint16_t>(mask), nBad,
                stConfig.stDevice.nWakeInputMask);
    return false;
}
#endif

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
    // Clear CAN sleep request so we don't immediately re-enter sleep after waking up
    bSleepRequest = false;

    #if MCU_SAFETY
    SafetyBeforeSleep(); // custom-pdm: long watchdog timeout for the waits below and STOP
    #endif

    // Forced sleep can arrive with outputs on - shut them off, no current protection while stopped
    #if NUM_OUTPUTS > 0
    for (uint8_t i = 0; i < NUM_OUTPUTS; i++)
        pf[i].ForceOff();
    #endif

    #if SLEEP_LOW_POWER
    EnterLowPower(); // custom-pdm: after ForceOff (IN low): DEN / DSEL low, MCP9808 shutdown
    #endif

    // Stop transmitting before the transceiver goes to standby. A frame still
    // going out while another device on the bus falls asleep wakes it up again.
    // Frames already in the CAN mailboxes finish during the wait below.
    SetCanTxQuiet(true);
    chThdSleepMilliseconds(100);

    // Stop the CAN controller before its pins change. Left running, it sees the
    // RX pin taken away from it and answers with an error frame, and the error
    // flag the other nodes send back arrives just after the transceiver went to
    // standby - which wakes this device straight back up whenever anything else
    // is on the bus.
    StopCan();
    palSetLineMode(LINE_CAN_TX, PAL_MODE_OUTPUT_PUSHPULL);
    palSetLine(LINE_CAN_TX); // Recessive

    palSetLine(LINE_CAN_STANDBY); // CAN disabled

    // Let the transceiver settle in standby before any wake source is armed
    chThdSleepMilliseconds(20);

    // A PWM input's edge event would wake it, and the wake event below needs the same EXTI line
    for(uint8_t i = 0; i < NUM_DIG_INPUTS; i++)
        digIn[i].StopPwm();

    // Set wakeup sources

    // Digital inputs change detection, with configured pullup or pulldown
    // Can be disabled in config
    // custom-pdm (Dan B2): only the inputs in the wake-input mask (param 0x7F00 sub 5, default none) are armed, and
    // only while DisableDigInWake is off. WriteParam keeps shared-line pairs and the USB / CAN lines out of the mask
    // (CheckWakeInputMask above). Stock boards: every input, stock code.
    if(!stConfig.stDevice.bDisableDigInWake)
    {
        for(uint8_t i = 0; i < NUM_DIG_INPUTS; i++)
        {
            #if WAKE_INPUT_PARAM
            if (stConfig.stDevice.nWakeInputMask & (1U << i))
            #endif
                EnableLineEventWithPull(digIn[i].GetLine(), stConfig.stDigInput[i].ePull);
        }
    }

    // CAN receive detection - can be disabled in config
    if(!stConfig.stDevice.bDisableCanWake)
    {
        palSetLineMode(LINE_CAN_RX, PAL_MODE_INPUT);
        palEnableLineEvent(LINE_CAN_RX, PAL_EVENT_MODE_BOTH_EDGES | PAL_STM32_PUPDR_FLOATING);
    }

    // USB detection - always active
    palSetLineMode(LINE_USB_DP, PAL_MODE_INPUT);
    palEnableLineEvent(LINE_USB_DP, PAL_EVENT_MODE_BOTH_EDGES | PAL_STM32_PUPDR_FLOATING);
    palSetLineMode(LINE_USB_DM, PAL_MODE_INPUT);
    palEnableLineEvent(LINE_USB_DM, PAL_EVENT_MODE_BOTH_EDGES | PAL_STM32_PUPDR_FLOATING);

    // Arming a line can latch an edge from the pin changing mode. Clear those so
    // only a real wake source ends the stop. One arriving from here on is still
    // pending at the WFI and wakes the MCU as it should.
    EXTI_PENDING = 0x0000FFFF;
    NVIC_ClearPendingIRQ(EXTI0_IRQn);
    NVIC_ClearPendingIRQ(EXTI1_IRQn);
    NVIC_ClearPendingIRQ(EXTI2_IRQn);
    NVIC_ClearPendingIRQ(EXTI3_IRQn);
    NVIC_ClearPendingIRQ(EXTI4_IRQn);
    NVIC_ClearPendingIRQ(EXTI9_5_IRQn);
    NVIC_ClearPendingIRQ(EXTI15_10_IRQn);

    #if MCU_SAFETY
    SafetyEnterStop(); // custom-pdm: STOP with RTC wake-ups that refresh the watchdog (core/safety.h)
    #else
    EnterStopMode();
    #endif
}

#endif