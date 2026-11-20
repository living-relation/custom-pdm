// custom-pdm (MCU_SAFETY): STM32F446 register layer for core/safety.cpp. Only custom boards build this file
// (tools_custom/port_boards.py adds it to their board.mk). Sources: RM0390 Rev 6 (3.6.2 option bytes, 3.8.6 FLASH_OPTCR,
// 6.3.21 RCC_CSR, 19 IWDG, 22.3.6 RTC wake-up timer, 22.6.4 RTC_ISR, 5.3.4 STOP), DS DocID027107 Rev 2 (Tables 21, 42).
#include "ch.h"
#include "hal.h"
#include "safety.h"

#if MCU_SAFETY
// RM0390 19.4: key values
#define IWDG_KEY_RELOAD 0xAAAAU
#define IWDG_KEY_ACCESS 0x5555U
#define IWDG_KEY_START 0xCCCCU
// RM0390 3.6.2
#define FLASH_OPT_KEY1 0x08192A3BU
#define FLASH_OPT_KEY2 0x4C5D6E7FU
#define FLASH_SR_ERRORS 0x1F2U          // OPERR, WRPERR, PGAERR, PGPERR, PGSERR, RDERR (rc_w1)
#define OPTION_BYTES_USER (*(volatile uint32_t *)0x1FFFC000U)   // RM0390 Table 9: RDP + USER (bits 3:2 BOR_LEV)
#define RTC_WPR_KEY1 0xCAU
#define RTC_WPR_KEY2 0x53U

uint32_t McuBorLevel()
{
    return (OPTION_BYTES_USER >> 2) & 3U;
}

static bool FlashWaitIdle(uint32_t ms)
{
    for (uint32_t i = 0; (FLASH->SR & FLASH_SR_BSY) != 0; i++)
    {
        if (i >= ms)
            return false;
        IWDG->KR = IWDG_KEY_RELOAD;
        chThdSleepMilliseconds(1);
    }
    return true;
}

// RM0390 3.6.2 "Modifying user option bytes": BSY clear, unlock OPTLOCK (OPTKEY1, OPTKEY2), write FLASH_OPTCR with
// only BOR_LEV changed (the whole user option sector is erased and re-written from FLASH_OPTCR: RDP, nWRP and USER
// must keep their present values), OPTSTRT, wait for BSY, lock again.
bool McuSetBorLevel(uint32_t level)
{
    if (!FlashWaitIdle(1000))
        return false;
    FLASH->SR = FLASH_SR_ERRORS;
    if (FLASH->OPTCR & FLASH_OPTCR_OPTLOCK)
    {
        FLASH->OPTKEYR = FLASH_OPT_KEY1;
        FLASH->OPTKEYR = FLASH_OPT_KEY2;
    }
    if (FLASH->OPTCR & FLASH_OPTCR_OPTLOCK)
        return false;                   // a failed unlock keeps OPTLOCK set until the next reset (3.8.6)
    uint32_t v = FLASH->OPTCR & ~(FLASH_OPTCR_BOR_LEV | FLASH_OPTCR_OPTSTRT | FLASH_OPTCR_OPTLOCK);
    v |= (level & 3U) << 2;
    FLASH->OPTCR = v;
    FLASH->OPTCR = v | FLASH_OPTCR_OPTSTRT;
    const bool done = FlashWaitIdle(2000);
    FLASH->OPTCR |= FLASH_OPTCR_OPTLOCK;
    return done && !(FLASH->SR & FLASH_SR_ERRORS) && McuBorLevel() == (level & 3U);
}

static void WdgWaitUpdate()
{
    // PVU / RVU stay set until the new value reached the LSI domain (up to 5 LSI periods, RM0390 19.4.4)
    for (uint32_t i = 0; (IWDG->SR & (IWDG_SR_PVU | IWDG_SR_RVU)) != 0 && i < 100000U; i++)
        ;
}

void McuWdgSetTimeout(uint32_t pr, uint32_t rlr)
{
    WdgWaitUpdate();
    IWDG->KR = IWDG_KEY_ACCESS;
    IWDG->PR = pr;
    IWDG->RLR = rlr;
    WdgWaitUpdate();                    // so the reload below uses the new values
    IWDG->KR = IWDG_KEY_RELOAD;
}

void McuWdgStart(uint32_t pr, uint32_t rlr)
{
    DBGMCU->APB1FZ |= DBGMCU_APB1_FZ_DBG_IWDG_STOP;   // a debugger halt freezes it (no hardware here yet: harmless)
    IWDG->KR = IWDG_KEY_START;                         // starts the LSI too (RM0390 19.3.1)
    McuWdgSetTimeout(pr, rlr);
}

void McuWdgRefresh()
{
    IWDG->KR = IWDG_KEY_RELOAD;
}

uint32_t McuResetFlags()
{
    const uint32_t f = RCC->CSR & 0xFE000000U;
    RCC->CSR |= RCC_CSR_RMVF;           // clear, so the next boot sees only its own cause
    return f;
}

static void RtcUnlock()
{
    PWR->CR |= PWR_CR_DBP;              // ChibiOS leaves it open (hal_lld_backup_domain_init); set again to be sure
    RTC->WPR = RTC_WPR_KEY1;
    RTC->WPR = RTC_WPR_KEY2;
}

void McuRtcWakeStop()
{
    if (!(RCC->BDCR & RCC_BDCR_RTCEN))
        return;
    RtcUnlock();
    RTC->CR &= ~(RTC_CR_WUTE | RTC_CR_WUTIE);
    RTC->ISR = ~(RTC_ISR_WUTF | RTC_ISR_INIT) | (RTC->ISR & RTC_ISR_INIT);
    RTC->WPR = 0xFFU;
}

// RM0390 22.3.6: WUTE off, wait WUTWF, WUTR and WUCKSEL, then WUTE + WUTIE. RTC clock = LSI (RCC_BDCR RTCSEL 10,
// mcuconf.h STM32_RTCSEL_LSI; the IWDG runs on the same LSI). EXTI line 22 = RTC wake-up, rising edge (RM0390 10.2.5).
static void RtcWakeStart(uint32_t wut)
{
    PWR->CR |= PWR_CR_DBP;
    if ((RCC->BDCR & RCC_BDCR_RTCSEL) != RCC_BDCR_RTCSEL_1)
    {
        RCC->BDCR = RCC_BDCR_BDRST;     // another clock was selected: RTCSEL can only change after a domain reset
        RCC->BDCR = 0;
    }
    RCC->BDCR |= RCC_BDCR_RTCSEL_1 | RCC_BDCR_RTCEN;
    RtcUnlock();
    RTC->CR &= ~(RTC_CR_WUTE | RTC_CR_WUTIE);
    for (uint32_t i = 0; !(RTC->ISR & RTC_ISR_WUTWF) && i < 100000U; i++)
        ;
    RTC->WUTR = wut;
    RTC->CR = (RTC->CR & ~RTC_CR_WUCKSEL) | RTC_CR_WUTE | RTC_CR_WUTIE;   // WUCKSEL 000 = RTC clock / 16
    RTC->ISR = ~(RTC_ISR_WUTF | RTC_ISR_INIT) | (RTC->ISR & RTC_ISR_INIT);
    RTC->WPR = 0xFFU;
    EXTI->IMR |= (1U << 22);
    EXTI->RTSR |= (1U << 22);
    EXTI->PR = (1U << 22);
}

// As EnterStopMode (mcu_utils.cpp) with the RTC wake-up added: SysTick off, every IRQ masked except the EXTI wake
// lines 0-15 and RTC_WKUP, PRIMASK set (WFI returns on a pending enabled IRQ without running it). On each wake: an
// EXTI 0-15 edge = a real wake source: reset as stock; the RTC flag alone: refresh the IWDG and stop again.
void McuEnterStopWithWdg(uint32_t wut)
{
    RtcWakeStart(wut);
    PWR->CR &= ~PWR_CR_PDDS;
    PWR->CR |= PWR_CR_CWUF | PWR_CR_CSBF;
    PWR->CR |= PWR_CR_FPDS | PWR_CR_LPDS;
    SCB->SCR |= SCB_SCR_SLEEPDEEP_Msk;

    __disable_irq();
    SysTick->CTRL = 0;
    for (uint32_t i = 0; i < 8; i++)
    {
        NVIC->ICER[i] = 0xFFFFFFFFu;
        NVIC->ICPR[i] = 0xFFFFFFFFu;
    }
    SCB->ICSR = SCB_ICSR_PENDSTCLR_Msk;
    static const IRQn_Type wake[] = {EXTI0_IRQn, EXTI1_IRQn, EXTI2_IRQn, EXTI3_IRQn, EXTI4_IRQn, EXTI9_5_IRQn, EXTI15_10_IRQn, RTC_WKUP_IRQn};
    for (IRQn_Type n : wake)
        NVIC_EnableIRQ(n);
    IWDG->KR = IWDG_KEY_RELOAD;

    for (;;)
    {
        __WFI();
        if (EXTI->PR & 0xFFFFU)
            break;                      // input / CAN RX / USB edge: wake up (reset, as stock)
        if (RTC->ISR & RTC_ISR_WUTF)
        {
            RTC->ISR = ~(RTC_ISR_WUTF | RTC_ISR_INIT) | (RTC->ISR & RTC_ISR_INIT);   // RTC_ISR[13:8]: not write protected
            EXTI->PR = (1U << 22);
            NVIC_ClearPendingIRQ(RTC_WKUP_IRQn);
            IWDG->KR = IWDG_KEY_RELOAD;
        }
        // anything else (spurious wake): straight back to STOP
    }
    NVIC_SystemReset();
}

void McuSystemReset()
{
    NVIC_SystemReset();
}
#endif
