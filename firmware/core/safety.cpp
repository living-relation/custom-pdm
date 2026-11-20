// custom-pdm (MCU_SAFETY): brown-out level, independent watchdog, watchdog-safe sleep. See core/safety.h.
#include "safety.h"

#if MCU_SAFETY
#include "device_config.h"
#include "config.h"
#include "infomsg.h"
#include "ch.h"

extern DeviceConfig stConfig;

static volatile uint8_t nCheckIn[static_cast<uint8_t>(SafetyTask::Count)];
static bool bWdgOn;
static uint32_t nResetFlags;
static uint16_t nBorMsg, nBorData;

void SafetyWdgStart()
{
    nResetFlags = McuResetFlags();
    McuRtcWakeStop();
    McuWdgStart(SAFETY_WDG_PR, SAFETY_WDG_RLR);
    bWdgOn = true;
}

// Option bytes BOR_LEV must be 00 (level 3). The factory value is 11 (BOR off, RM0390 3.8.6). Written once: the
// next boot reads 00 and does nothing. Called before the CAN driver and the device thread start, so every output is
// still off (IN low from board init) and no frame is on the bus; after a good write the MCU resets so the option
// bytes are loaded again ("loaded with values from Flash memory at reset release", RM0390 3.8.6).
void SafetyBoot(float (*battVolt)())
{
    const uint32_t lev = McuBorLevel();
    if (lev == SAFETY_BOR_LEVEL3)
        return;                              // every start after the first: no delay, nothing written
    chThdSleepMilliseconds(5);               // the battery reading needs a few ADC sequences (45.6 / 57.6 us each)
    const float fBattVolt = battVolt();
    if (!(fBattVolt >= SAFETY_BOR_MIN_VBAT))
    {
        nBorMsg = SAFETY_MSG_BOR_LOW_VBAT;   // try again at the next start
        nBorData = (uint16_t)(fBattVolt > 0.0f ? fBattVolt * 10.0f : 0.0f);
        return;
    }
    McuWdgRefresh();
    if (McuSetBorLevel(SAFETY_BOR_LEVEL3))
        McuSystemReset();                    // does not return
    nBorMsg = SAFETY_MSG_BOR_FAILED;
    nBorData = (uint16_t)McuBorLevel();
}

void SafetyReportBoot()
{
    const uint16_t id = stConfig.stDevice.nBaseId;
    if (nResetFlags & MCU_RSTF_IWDG)
        SendInfoMsg(MsgType::Warning, MsgSrc::Init, id, SAFETY_MSG_WDG_RESET, 0, 0);
    else if ((nResetFlags & MCU_RSTF_BOR) && !(nResetFlags & MCU_RSTF_POR))
        SendInfoMsg(MsgType::Warning, MsgSrc::Init, id, SAFETY_MSG_BOR_RESET, 0, 0);
    if (nBorMsg)
        SendInfoMsg(MsgType::Warning, MsgSrc::Init, id, nBorMsg, nBorData, (uint16_t)McuBorLevel());
}

void SafetyCheckIn(SafetyTask t)
{
    nCheckIn[static_cast<uint8_t>(t)] = 1;
}

// Device thread, after CyclicUpdate / States: refresh only when every essential thread has run since the last
// refresh. A thread that stops (stuck loop, dead I2C read, blocked CAN) stops the refreshes; the IWDG then resets the
// MCU after SAFETY_WDG_MIN_MS .. 2.8 s and every output starts off.
void SafetyService()
{
    nCheckIn[static_cast<uint8_t>(SafetyTask::Device)] = 1;
    if (!bWdgOn)
        return;
    for (uint8_t i = 0; i < static_cast<uint8_t>(SafetyTask::Count); i++)
        if (!nCheckIn[i])
            return;
    for (uint8_t i = 0; i < static_cast<uint8_t>(SafetyTask::Count); i++)
        nCheckIn[i] = 0;
    McuWdgRefresh();
}

// Sleep entry waits 120 ms (CAN quiet + transceiver) with the CAN threads stopping: from here the long timeout.
void SafetyBeforeSleep()
{
    if (!bWdgOn)
        return;
    McuWdgSetTimeout(SAFETY_SLEEP_WDG_PR, SAFETY_SLEEP_WDG_RLR);
    McuWdgRefresh();
}

void SafetyEnterStop()
{
    McuEnterStopWithWdg(SAFETY_RTC_WUT);
}
#endif
