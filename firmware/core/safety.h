#pragma once

// custom-pdm (MCU_SAFETY, ADR-2026-11-20-presim-findings item 3; docs/system-verification.md 2 / 4):
//   1. Brown-out reset level 3 (VBOR3 2.75-2.88 V falling, DS DocID027107 Table 21), set by the firmware itself
//      from the option bytes once (RM0390 Rev 6 3.6.2 / 3.8.6), only with outputs off and a healthy supply.
//   2. Independent watchdog (RM0390 section 19), started at the top of InitDevice, refreshed by the device thread only
//      when every essential thread checked in since the last refresh; a reset starts with every output off.
//   3. Sleep (STOP) with the watchdog running: the F446 has no IWDG freeze in STOP (option bytes: RM0390 Table 9
//      lists only BOR_LEV, WDG_SW, nRST_STOP, nRST_STDBY, RDP, nWRP), so before STOP the timeout is set to its sleep
//      value and the RTC wake-up timer (clocked by the same LSI) wakes the MCU for a refresh at a quarter of it.
// The decision logic is here (host sim + target); the register code is in boards/stm32f446/mcu_safety.cpp (target)
// and firmware/sim/sim_core.cpp (host sim models of the option bytes, IWDG, RTC wake-up and reset flags).
// Stock boards leave MCU_SAFETY at 0: every hook below compiles to nothing.
#include <cstdint>
#include "port.h"

#ifndef MCU_SAFETY
#define MCU_SAFETY 0
#endif

#if MCU_SAFETY
// Essential threads; each checks in once per loop. The device thread is the one that refreshes.
enum class SafetyTask : uint8_t { Device = 0, Slow, CanCyclicTx, CanTx, CanRx, Count };

// ---- brown-out (option bytes, FLASH_OPTCR bits 3:2): 00 = level 3, 01 = level 2, 10 = level 1, 11 = off (factory)
#define SAFETY_BOR_LEVEL3 0U
// Supply needed before the option bytes are written (battery volts): an option byte write erases and re-writes
// the user option sector (RM0390 3.6.2 note); power lost in the middle leaves RDP at Level 1 (3.6.3). 10.0 V is
// above a cranking dip (6 V, docs/system-verification.md 2) and far above the 5.2 V where +3V3 stops regulating.
#define SAFETY_BOR_MIN_VBAT 10.0f

// ---- watchdog. LSI 17 / 32 / 47 kHz min / typ / max (DS DocID027107 Table 42); IWDG counter = LSI / prescaler.
#define SAFETY_LSI_MIN_HZ 17000U
#define SAFETY_LSI_TYP_HZ 32000U
#define SAFETY_LSI_MAX_HZ 47000U
// Run timeout: at least SAFETY_WDG_MIN_MS with the fastest LSI. The longest gap between two refreshes measured in the
// host sim (s0 / s1, every feature on, Write All, Burn, sleep entry) and Renode (real I2C / FRAM timing): see
// firmware/sim/RESULTS.md 2026-11-20 fwsafety; 1000 ms is > 2 x that.
#define SAFETY_WDG_MIN_MS 1000U
#define SAFETY_WDG_PR 3U                                   // IWDG_PR 3 = LSI / 32
#define SAFETY_WDG_DIV (4U << SAFETY_WDG_PR)
#define SAFETY_WDG_RLR ((SAFETY_WDG_MIN_MS * SAFETY_LSI_MAX_HZ / 1000U + SAFETY_WDG_DIV - 1U) / SAFETY_WDG_DIV - 1U)
// Sleep timeout: LSI / 64, reload 4095 = 262144 LSI cycles (5.6 / 8.2 / 15.4 s); RTC wake-up every 65536 LSI cycles
// (RTC clock / 16, WUT 4095): a quarter of the timeout whatever the LSI frequency (one oscillator drives both).
#define SAFETY_SLEEP_WDG_PR 4U
#define SAFETY_SLEEP_WDG_RLR 4095U
#define SAFETY_RTC_WUT 4095U                               // RTC_WUTR, WUCKSEL = 000 (RTC clock / 16)

// ---- what the board reports once after boot (type Warning, src Init, on base + CONFIG_TX_OFFSET), data 0 =
#define SAFETY_MSG_WDG_RESET 1U        // the last reset came from the watchdog (= FatalErrorType::ErrIWDG)
#define SAFETY_MSG_BOR_RESET 2U        // the last reset was a brown-out (BORRSTF without PORRSTF)
#define SAFETY_MSG_BOR_LOW_VBAT 3U     // BOR level not set yet: battery below SAFETY_BOR_MIN_VBAT (data 1 = V x 10)
#define SAFETY_MSG_BOR_FAILED 4U       // BOR level write did not take (data 1 = level read back)

void SafetyWdgStart();                 // top of InitDevice
void SafetyBoot(float (*battVolt)()); // after InitAdc, before InitCan: sets BOR level 3 once (then resets the MCU)
void SafetyReportBoot();               // after InitCan: the messages above
void SafetyCheckIn(SafetyTask t);
void SafetyService();                  // device thread, every loop
void SafetyBeforeSleep();              // EnterSleep, before its waits: sleep timeout
void SafetyEnterStop();                // EnterSleep, instead of EnterStopMode: STOP with RTC refreshes

// register layer (boards/stm32f446/mcu_safety.cpp, or the host sim)
uint32_t McuBorLevel();                // option bytes BOR_LEV as programmed (0x1FFFC000 bits 3:2)
bool McuSetBorLevel(uint32_t level);   // unlock, write, OPTSTRT, wait, lock; true = read back as asked
void McuWdgStart(uint32_t pr, uint32_t rlr);
void McuWdgSetTimeout(uint32_t pr, uint32_t rlr);
void McuWdgRefresh();
uint32_t McuResetFlags();              // RCC_CSR bits 31:24 at boot (flags then cleared)
void McuRtcWakeStop();                 // RTC wake-up timer off (left on in the backup domain by the last sleep)
void McuEnterStopWithWdg(uint32_t wut); // STOP; RTC wake-ups refresh the watchdog; any other wake resets the MCU
void McuSystemReset();
#define MCU_RSTF_POR (1U << 27)        // RCC_CSR PORRSTF
#define MCU_RSTF_BOR (1U << 25)        // RCC_CSR BORRSTF (also set on a power-on reset)
#define MCU_RSTF_IWDG (1U << 29)       // RCC_CSR IWDGRSTF

#define SAFETY_CHECKIN(t) SafetyCheckIn(SafetyTask::t)
#else
#define SAFETY_CHECKIN(t) do { } while (0)
#endif
