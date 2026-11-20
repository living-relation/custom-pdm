// custom-pdm host simulation core: cooperative scheduler, GPIO, CAN, PWM timers, ADC, plant, stubs.
// One shared object = one board. All firmware code above this layer is the real dingoFW source.
#include "hal.h"
#include "ch.hpp"
#include "port.h"
#include "hw_devices.h"
#include "config.h"
#include "device.h"
#include "mcu_utils.h"
#include "hardware/mb85rc.h"
#include "usb.h"
#include <ucontext.h>
#include <vector>
#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <cstdio>

#define API extern "C" __attribute__((visibility("default")))
static const uint64_t TICK_US = 1000000 / CH_CFG_ST_FREQUENCY;

//================================================================== scheduler
struct thread_t
{
    ucontext_t ctx; void *stack; tfunc_t fn; void *arg; chibios_rt::BaseThread *obj;
    uint64_t wake; int prio; bool done; bool terminate; bool parked; uint64_t spins;
};
static std::vector<thread_t *> threads;
static thread_t *cur = nullptr;
static ucontext_t schedCtx;
static uint64_t nowUs = 0;
static int fatalFlag = 0, asleepFlag = 0, bootloaderFlag = 0;
static uint64_t sysTimeCalls = 0;

static void yieldToSched() { swapcontext(&cur->ctx, &schedCtx); }
static void park() { cur->parked = true; for (;;) yieldToSched(); }
static void trampoline(unsigned lo, unsigned hi)
{
    thread_t *t = (thread_t *)(((uint64_t)hi << 32) | lo);
    if (t->obj) t->obj->main(); else t->fn(t->arg);
    t->done = true; for (;;) yieldToSched();
}
static thread_t *spawn(tfunc_t fn, void *arg, chibios_rt::BaseThread *obj, int prio)
{
    thread_t *t = new thread_t(); t->fn = fn; t->arg = arg; t->obj = obj; t->prio = prio; t->wake = nowUs;
    t->stack = malloc(512 * 1024); getcontext(&t->ctx);
    t->ctx.uc_stack.ss_sp = t->stack; t->ctx.uc_stack.ss_size = 512 * 1024; t->ctx.uc_link = &schedCtx;
    uint64_t p = (uint64_t)t; makecontext(&t->ctx, (void (*)())trampoline, 2, (unsigned)p, (unsigned)(p >> 32));
    threads.push_back(t); return t;
}
thread_t *chThdCreateStatic(void *, size_t, int prio, tfunc_t fn, void *arg) { return spawn(fn, arg, nullptr, prio); }
chibios_rt::ThreadReference chibios_rt::BaseThread::start(int prio) { ThreadReference r; r.t = spawn(nullptr, nullptr, this, prio); return r; }
void chRegSetThreadName(const char *) {}
bool chThdShouldTerminateX() { return cur && cur->terminate; }
void chThdExit(msg_t) { cur->done = true; for (;;) yieldToSched(); }
void chThdTerminate(thread_t *t) { if (t) t->terminate = true; }
static void sleepTicks(uint64_t ticks)
{
    // Real ChibiOS rounds a sleep up to whole system ticks (100 us), minimum one tick.
    if (ticks < 1) ticks = 1;
    cur->wake = (nowUs / TICK_US + ticks) * TICK_US; cur->spins = 0; yieldToSched();
}
msg_t chThdWait(thread_t *t) { while (t && !t->done) sleepTicks(1); return MSG_OK; }
void chThdSleepMilliseconds(uint32_t ms) { sleepTicks((uint64_t)ms * 1000 / TICK_US); }
void chThdSleepMicroseconds(uint32_t us) { sleepTicks(((uint64_t)us + TICK_US - 1) / TICK_US); }
systime_t chVTGetSystemTimeX()
{
    sysTimeCalls++;
    // A thread that polls the clock for ever without sleeping is the firmware's fatal-error loop
    // (Error::SetFatalError). Record it and stop that thread, as the real loop never returns.
    if (cur && ++cur->spins > 2000000) { fatalFlag = 1; park(); }
    return (systime_t)(nowUs / TICK_US);
}
systimestamp_t chVTGetTimeStamp()
{
    sysTimeCalls++;
    if (cur && ++cur->spins > 2000000) { fatalFlag = 1; park(); } // as chVTGetSystemTimeX (SYS_TIME uses this one)
    return (systimestamp_t)(nowUs / TICK_US);
}
rtcnt_t chSysGetRealtimeCounterX() { return (rtcnt_t)(nowUs * (STM32_HCLK / 1000000U)); }

//================================================================== mutex, objects FIFO (blocking, like ChibiOS)
static void blockUntil(uint64_t wake) { cur->wake = wake; cur->spins = 0; yieldToSched(); }
static void wakeThread(thread_t *t) { if (t && t->wake > nowUs) t->wake = nowUs; }
uint64_t simDeadline(sysinterval_t timeout) { return timeout == TIME_INFINITE ? UINT64_MAX : nowUs + (uint64_t)timeout * TICK_US; }
bool simWaitUntil(uint64_t deadline, thread_t **waiter)
{
    if (!cur || nowUs >= deadline) return false;
    *waiter = cur; blockUntil(deadline); if (*waiter == cur) *waiter = nullptr;
    return true;
}
void simWake(thread_t **waiter) { if (*waiter) { wakeThread(*waiter); *waiter = nullptr; } }
void chMtxLock(mutex_t *m)
{
    while (m->owner && m->owner != cur)
    {
        if (m->nWaiters < 8) m->waiters[m->nWaiters++] = cur;
        blockUntil(UINT64_MAX);
    }
    m->owner = cur;
}
void chMtxUnlock(mutex_t *m)
{
    m->owner = nullptr;
    for (int i = 0; i < m->nWaiters; i++) wakeThread(m->waiters[i]);
    m->nWaiters = 0;
}
void chFifoObjectInit(objects_fifo_t *f, size_t objsize, size_t n, void *objbuf, msg_t *)
{
    f->objsize = objsize; f->n = n; f->objbuf = (uint8_t *)objbuf; f->free.clear(); f->full.clear(); f->waiter = nullptr;
    for (size_t i = 0; i < n; i++) f->free.push_back(f->objbuf + i * objsize);
}
void *chFifoTakeObjectTimeout(objects_fifo_t *f, sysinterval_t)
{
    // only used with TIME_IMMEDIATE (comms/can.cpp -> RouteParamFrame)
    if (f->free.empty()) return nullptr;
    void *o = f->free.front(); f->free.pop_front(); return o;
}
void chFifoSendObject(objects_fifo_t *f, void *obj) { f->full.push_back(obj); wakeThread(f->waiter); }
msg_t chFifoReceiveObjectTimeout(objects_fifo_t *f, void **obj, sysinterval_t timeout)
{
    uint64_t deadline = timeout == TIME_INFINITE ? UINT64_MAX : nowUs + (uint64_t)timeout * TICK_US;
    while (f->full.empty())
    {
        if (timeout == TIME_IMMEDIATE || nowUs >= deadline) return MSG_TIMEOUT;
        f->waiter = cur; blockUntil(deadline); f->waiter = nullptr;
    }
    *obj = f->full.front(); f->full.pop_front(); return MSG_OK;
}
void chFifoReturnObject(objects_fifo_t *f, void *obj) { f->free.push_back(obj); }

//================================================================== NVIC / EXTI
uint32_t simExtiPending = 0;
static uint32_t nvicClears = 0;
void NVIC_ClearPendingIRQ(IRQn_Type) { nvicClears++; }
static int restartFlag = 0;
void NVIC_SystemReset() { restartFlag = 1; park(); } // real MCU resets here

//================================================================== GPIO
struct Pin { uint8_t mode; uint8_t pupd; uint8_t odr; uint8_t ext; uint8_t af; uint8_t event; };
static Pin *pins()
{
    static Pin p[8][16]; static bool init = false;
    if (!init)
    {
        init = true;
        static const uint32_t moder[8] = {VAL_GPIOA_MODER, VAL_GPIOB_MODER, VAL_GPIOC_MODER, VAL_GPIOD_MODER, VAL_GPIOE_MODER, VAL_GPIOF_MODER, VAL_GPIOG_MODER, VAL_GPIOH_MODER};
        static const uint32_t pupdr[8] = {VAL_GPIOA_PUPDR, VAL_GPIOB_PUPDR, VAL_GPIOC_PUPDR, VAL_GPIOD_PUPDR, VAL_GPIOE_PUPDR, VAL_GPIOF_PUPDR, VAL_GPIOG_PUPDR, VAL_GPIOH_PUPDR};
        static const uint32_t odr[8] = {VAL_GPIOA_ODR, VAL_GPIOB_ODR, VAL_GPIOC_ODR, VAL_GPIOD_ODR, VAL_GPIOE_ODR, VAL_GPIOF_ODR, VAL_GPIOG_ODR, VAL_GPIOH_ODR};
        static const uint32_t afrl[8] = {VAL_GPIOA_AFRL, VAL_GPIOB_AFRL, VAL_GPIOC_AFRL, VAL_GPIOD_AFRL, VAL_GPIOE_AFRL, VAL_GPIOF_AFRL, VAL_GPIOG_AFRL, VAL_GPIOH_AFRL};
        static const uint32_t afrh[8] = {VAL_GPIOA_AFRH, VAL_GPIOB_AFRH, VAL_GPIOC_AFRH, VAL_GPIOD_AFRH, VAL_GPIOE_AFRH, VAL_GPIOF_AFRH, VAL_GPIOG_AFRH, VAL_GPIOH_AFRH};
        for (int g = 0; g < 8; g++) for (int i = 0; i < 16; i++)
        {
            p[g][i].mode = (moder[g] >> (2 * i)) & 3; p[g][i].pupd = (pupdr[g] >> (2 * i)) & 3;
            p[g][i].odr = (odr[g] >> i) & 1; p[g][i].ext = 2;
            p[g][i].af = i < 8 ? (afrl[g] >> (4 * i)) & 15 : (afrh[g] >> (4 * (i - 8))) & 15;
        }
    }
    return &p[0][0];
}
static Pin &pin(ioline_t l) { return pins()[((l >> 4) & 7) * 16 + (l & 15)]; }
static uint32_t badWrites = 0, floatReads = 0; static ioline_t lastBadWrite = 0, lastFloatRead = 0;
// Edge log for pin-level timing (sim_watch_pins / sim_edges): every change of a watched output line, in us
struct EdgeRec { uint64_t t; int idx; int level; };
static std::vector<ioline_t> watchLines; static std::vector<EdgeRec> edgeLog;
static void wr(ioline_t l, int v)
{
    Pin &p = pin(l); if (p.mode != 1) { badWrites++; lastBadWrite = l; }
    int before = p.odr; p.odr = v ? 1 : 0;
    if (before != p.odr && edgeLog.size() < 1000000)
        for (size_t i = 0; i < watchLines.size(); i++) if (watchLines[i] == l) edgeLog.push_back({nowUs, (int)i, p.odr});
}
void palSetLine(ioline_t l) { wr(l, 1); }
void palClearLine(ioline_t l) { wr(l, 0); }
void palToggleLine(ioline_t l) { wr(l, !pin(l).odr); }
void palWriteLine(ioline_t l, int v) { wr(l, v); }
static int level(ioline_t l, bool count)
{
    Pin &p = pin(l);
    if (p.mode == 1) return p.odr;
    if (p.ext != 2) return p.ext;
    if (p.pupd == 1) return 1;
    if (p.pupd == 2) return 0;
    if (count) { floatReads++; lastFloatRead = l; }
    return 0; // floating input, nothing driving it: undefined on real hardware
}
bool palReadLine(ioline_t l) { return level(l, true); }
void palSetLineMode(ioline_t l, uint32_t mode)
{
    Pin &p = pin(l);
    if (mode == PAL_MODE_OUTPUT_PUSHPULL) { p.mode = 1; p.pupd = 0; return; } // sleep entry: CAN TX as GPIO, recessive
    p.mode = 0; p.pupd = mode == PAL_MODE_INPUT_PULLUP ? 1 : mode == PAL_MODE_INPUT_PULLDOWN ? 2 : 0;
}
// Line callbacks (digital input PWM meter): called on every edge of an armed line, as the EXTI interrupt would
static palcallback_t lineCb[8][16]; static void *lineCbArg[8][16];
void palSetLineCallbackI(ioline_t l, palcallback_t cb, void *arg) { lineCb[(l >> 4) & 7][l & 15] = cb; lineCbArg[(l >> 4) & 7][l & 15] = arg; }
// EXTI: one line number serves one port only. A later enable of the same pad number re-points the line
// (ChibiOS GPIOv2 hal_pal_lld.c, asserts off in this firmware), so the earlier pin stops being a wake source.
static int extiPort[16] = {-1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1};
static uint32_t extiClashes = 0;
void palEnableLineEvent(ioline_t l, uint32_t mode)
{
    int port = (l >> 4) & 7, pad = l & 15;
    if (extiPort[pad] >= 0 && extiPort[pad] != port) { extiClashes++; pins()[extiPort[pad] * 16 + pad].event = 0; }
    extiPort[pad] = port; Pin &p = pin(l); p.event = 1; p.mode = 0;
    p.pupd = (mode & PAL_STM32_PUPDR_PULLUP) ? 1 : (mode & PAL_STM32_PUPDR_PULLDOWN) ? 2 : 0;
}
void simEnableLineEventKeepPull(ioline_t l)
{
    int port = (l >> 4) & 7, pad = l & 15;
    if (extiPort[pad] >= 0 && extiPort[pad] != port) { extiClashes++; pins()[extiPort[pad] * 16 + pad].event = 0; }
    extiPort[pad] = port; pin(l).event = 1;
}
void palDisableLineEvent(ioline_t l)
{
    int port = (l >> 4) & 7, pad = l & 15;
    pin(l).event = 0; lineCb[port][pad] = nullptr;
    if (extiPort[pad] == port) extiPort[pad] = -1;
}

//================================================================== CAN
static CAN_TypeDef simCanRegs;
CANDriver CAND1 = {CAN_STOP, &simCanRegs};
static bool canStarted = false; static uint32_t canBtr = 0;
static std::deque<CANRxFrame> rxFifo; static std::deque<CANTxFrame> txMbx;
static uint32_t rxOverruns = 0, txTimeouts = 0, rxFiltered = 0;
msg_t canStart(CANDriver *c, const CANConfig *cfg)
{
    // ChibiOS can_lld_start leaves the filters it set at init: one 32-bit mask bank that accepts everything
    if (simCanRegs.FA1R == 0) { simCanRegs.FS1R = 1; simCanRegs.FA1R = 1; simCanRegs.sFilterRegister[0] = {0, 0}; }
    canStarted = true; canBtr = cfg->btr; c->state = CAN_READY; return MSG_OK;
}
void canStop(CANDriver *c) { canStarted = false; c->state = CAN_STOP; txMbx.clear(); rxFifo.clear(); }
// Acceptance as bxCAN does it from the filter registers dingoFW writes (comms/can.cpp WriteFilters, RM0390 32.7.4):
// active banks (FA1R), list mode (FM1R bit set) = FR1 or FR2 equal, mask mode = bits set in FR2 must match FR1.
// All filters here are 32-bit scale (FS1R), as dingoFW sets them.
static bool canFilterAccepts(uint32_t reg)
{
    const CAN_TypeDef &r = simCanRegs;
    for (int b = 0; b < 28; b++)
    {
        if (!(r.FA1R & (1U << b))) continue;
        const CAN_FilterRegister_TypeDef &f = r.sFilterRegister[b];
        if (r.FM1R & (1U << b)) { if (reg == f.FR1 || reg == f.FR2) return true; }
        else if (((reg ^ f.FR1) & f.FR2) == 0) return true;
    }
    return false;
}
// true when the registers accept only listed IDs (not the single accept-all mask bank)
static bool canFilterListOnly()
{
    const CAN_TypeDef &r = simCanRegs;
    for (int b = 0; b < 28; b++)
        if ((r.FA1R & (1U << b)) && !(r.FM1R & (1U << b)) && r.sFilterRegister[b].FR2 == 0) return false;
    return r.FA1R != 0;
}
void canSTM32SetFilters(CANDriver *, uint32_t, uint32_t, const CANFilter *) {} // not used by dingoFW development on bxCAN
msg_t canTransmitTimeout(CANDriver *, int, const CANTxFrame *f, sysinterval_t timeout)
{
    uint64_t deadline = nowUs + (uint64_t)timeout * TICK_US;
    while (txMbx.size() >= 3) // bxCAN has 3 transmit mailboxes
    {
        if (nowUs >= deadline) { txTimeouts++; return MSG_TIMEOUT; }
        sleepTicks(1);
    }
    txMbx.push_back(*f); return MSG_OK;
}
static thread_t *canRxWaiter = nullptr;
msg_t canReceiveTimeout(CANDriver *, int, CANRxFrame *f, sysinterval_t timeout)
{
    // blocks like the ChibiOS driver: dingoFW development's CAN Rx thread waits here (100 ms time-out)
    uint64_t deadline = simDeadline(timeout);
    while (rxFifo.empty())
        if (timeout == TIME_IMMEDIATE || !canStarted || !simWaitUntil(deadline, &canRxWaiter)) return MSG_TIMEOUT;
    *f = rxFifo.front(); rxFifo.pop_front(); return MSG_OK;
}

//================================================================== PWM timers
PWMDriver PWMD1, PWMD2, PWMD3, PWMD4, PWMD5, PWMD8, PWMD9, PWMD10, PWMD11, PWMD12, PWMD13, PWMD14;
static PWMDriver *allPwm[] = {&PWMD1, &PWMD2, &PWMD3, &PWMD4, &PWMD5, &PWMD8, &PWMD9, &PWMD10, &PWMD11, &PWMD12, &PWMD13, &PWMD14};
static uint64_t cntToUs(PWMDriver *p, uint64_t cnt) { return cnt * 1000000ULL / p->config->frequency; }
// Counts per period the timer really runs for a ChibiOS period value: ARR = period - 1, cut to the timer's width.
// STM32F446 (RM0390 sections 17-19): TIM2 / TIM5 have 32-bit counters, the other timers 16-bit, so a period above
// 65536 on a 16-bit timer runs short (ARR keeps the low 16 bits), as the real register does.
static uint32_t pwmTimerPeriod(PWMDriver *p, pwmcnt_t period)
{
    uint32_t mask = (p == &PWMD2 || p == &PWMD5) ? 0xFFFFFFFFU : 0xFFFFU;
    return ((uint32_t)(period - 1) & mask) + 1;
}
// ARR and CCR1 preload (ChibiOS pwm_lld_start sets CR1.ARPE and CCMR1.OC1PE): a period or compare value written
// while the timer runs is taken at the next update event (end of the running period), so a running period is never
// cut short and a duty change starts with a new period. Each write remembers the update event it waits for.
static uint64_t pwmNextUpdate(PWMDriver *p, uint64_t at)
{
    uint64_t perUs = cntToUs(p, p->actPer);
    return perUs ? p->t0 + ((at - p->t0) / perUs + 1) * perUs : at;
}
static void pwmCatchUp(PWMDriver *p, uint64_t at)
{
    if (p->state != PWM_READY) return;
    // The firmware wrote CNT (paired follower phase alignment, functions/profet.cpp): the counter runs on from that
    // value, no update event, so the period grid moves and waiting preload values wait for the new next update event.
    // A thread writes at nowUs and the scheduler calls this before any timer event after it.
    if (p->tim->CNT != p->lastCnt)
    {
        p->t0 = nowUs - cntToUs(p, p->tim->CNT % p->actPer); p->lastCnt = p->tim->CNT;
        if (p->pendPer) p->pendAt = pwmNextUpdate(p, nowUs);
        if (p->pendCcr) p->ccrAt = pwmNextUpdate(p, nowUs);
    }
    if (p->pendPer && at >= p->pendAt) { p->t0 = p->pendAt; p->actPer = p->pendPer; p->pendPer = 0; }
    if (p->pendCcr && at >= p->ccrAt) { p->actCcr = p->tim->CCR[0]; p->pendCcr = false; }
}
static void pwmSync(PWMDriver *p)
{
    if (p->state != PWM_READY) return;
    pwmCatchUp(p, nowUs);
    uint64_t c = (nowUs - p->t0) * p->config->frequency / 1000000ULL;
    p->tim->CNT = p->lastCnt = (uint32_t)(c % p->actPer);
}
msg_t pwmStart(PWMDriver *p, const PWMConfig *cfg)
{
    // pwm_lld_start loads ARR / CCR with an update event (EGR.UG): the start values are in use at once
    p->tim = &p->simTim; p->config = cfg; p->period = cfg->period; p->state = PWM_READY; p->t0 = nowUs; p->enabled = 0;
    p->actPer = pwmTimerPeriod(p, cfg->period); p->pendPer = 0; p->tim->CCR[0] = 0; p->actCcr = 0; p->pendCcr = false;
    p->tim->CNT = p->lastCnt = 0;
    p->periodicNotify = false; p->chNotify = 0; return MSG_OK;
}
void pwmChangePeriod(PWMDriver *p, pwmcnt_t period)
{
    // ChibiOS: pwmp->period = period at once (PWM_PERCENTAGE_TO_WIDTH uses it); the timer takes ARR at the next update
    pwmCatchUp(p, nowUs);
    p->period = period; p->pendPer = pwmTimerPeriod(p, period); p->pendAt = pwmNextUpdate(p, nowUs);
    if (p->pendPer == p->actPer) p->pendPer = 0;
}
static void pwmWriteCcr(PWMDriver *p, uint8_t ch, pwmcnt_t width)
{
    pwmCatchUp(p, nowUs);
    p->tim->CCR[ch] = width;
    if (ch == 0) { p->pendCcr = true; p->ccrAt = pwmNextUpdate(p, nowUs); }
}
void pwmEnableChannel(PWMDriver *p, uint8_t ch, pwmcnt_t width) { p->enabled |= 1U << ch; pwmWriteCcr(p, ch, width); }
void pwmDisableChannel(PWMDriver *p, uint8_t ch) { if (p->state != PWM_READY) return; p->enabled &= ~(1U << ch); pwmWriteCcr(p, ch, 0); p->chNotify &= ~(1U << ch); }
void pwmEnablePeriodicNotification(PWMDriver *p) { p->periodicNotify = true; }
void pwmDisablePeriodicNotification(PWMDriver *p) { p->periodicNotify = false; }
void pwmEnableChannelNotification(PWMDriver *p, uint8_t ch) { p->chNotify |= 1U << ch; }
void pwmDisableChannelNotification(PWMDriver *p, uint8_t ch) { p->chNotify &= ~(1U << ch); }
// Next timer interrupt (period start, or compare match on channel 0) strictly after 'from'.
static uint64_t pwmNextEvent(PWMDriver *p, uint64_t from, int *kind)
{
    if (p->state != PWM_READY || (!p->periodicNotify && !p->chNotify)) return UINT64_MAX;
    pwmCatchUp(p, from);
    uint64_t perUs = cntToUs(p, p->actPer); if (perUs == 0) return UINT64_MAX;
    uint64_t k = (from - p->t0) / perUs; uint64_t best = UINT64_MAX;
    for (uint64_t n = k; n <= k + 1; n++)
    {
        uint64_t start = p->t0 + n * perUs;
        // pending values (preload) are in use from their update event on (= the period start k + 1)
        uint32_t per = (p->pendPer && start >= p->pendAt) ? p->pendPer : p->actPer;
        uint32_t ccr = (p->pendCcr && start >= p->ccrAt) ? p->tim->CCR[0] : p->actCcr;
        if (p->periodicNotify && start > from && start < best) { best = start; *kind = 0; }
        uint64_t cmp = start + cntToUs(p, ccr);
        if ((p->chNotify & 1) && ccr < per && cmp > from && cmp < best) { best = cmp; *kind = 1; }
    }
    return best;
}

//================================================================== ADC + plant
ADCDriver ADCD1; I2CDriver I2CD1;
static const ADCConversionGroup *adcGrp = nullptr; static adcsample_t *adcBuf = nullptr;
static float pinVolts[8][16]; static float vdda = 3.3f, vbat = 13.8f, dieTempC = 30.0f;
struct PlantCh { ioline_t in, den, dsel, is; int hasDsel, dselLevel; float kilis, rsense, loadOhms, vclamp; int fault; };
static std::vector<PlantCh> plant;
msg_t adcStart(ADCDriver *, void *) { return MSG_OK; }
void adcStop(ADCDriver *) {}
void adcStopConversion(ADCDriver *) { adcGrp = nullptr; }
void adcSTM32EnableTSVREFE() {}
static int adcChanOfSlot(int slot) // decode the regular sequence registers exactly as the ADC does
{
    if (slot < 6) return (adcGrp->sqr3 >> (5 * slot)) & 31;
    if (slot < 12) return (adcGrp->sqr2 >> (5 * (slot - 6))) & 31;
    return (adcGrp->sqr1 >> (5 * (slot - 12))) & 31;
}
static float chanVolts(int ch)
{
    // STM32F446 ADC1 channel to pin (DS10693 Table 10): IN0-7 = PA0-7, IN8-9 = PB0-1, IN10-15 = PC0-5
    int port, pad;
    if (ch <= 7) { port = 0; pad = ch; } else if (ch <= 9) { port = 1; pad = ch - 8; } else if (ch <= 15) { port = 2; pad = ch - 10; }
    else if (ch == ADC_CHANNEL_SENSOR) return 0.76f + (dieTempC - 25.0f) * 0.0025f;
    else if (ch == ADC_CHANNEL_VREFINT) return 1.21f;
    else return 0;
    ioline_t l = PAL_LINE(port, pad);
    float v = pinVolts[port][pad];
    for (auto &c : plant)
    {
        if (c.is != l) continue;
        // PROFET sense: IS sources IL / kILIS into the sense resistor when DEN is high
        // (dual parts: for the channel picked by DSEL). A fault (IIS(FAULT) 4.4 mA min x 1.2k = 5.3 V) drives the sense
        // pin past the top of the chain, so it reads vclamp, the same as a load current above the measurable range.
        if (!level(c.den, false)) continue;
        if (c.hasDsel && level(c.dsel, false) != c.dselLevel) continue;
        float il = (level(c.in, false) && c.loadOhms > 0) ? vbat / c.loadOhms : 0;
        float vis = c.fault ? c.vclamp : il / c.kilis * c.rsense;
        if (vis > c.vclamp) vis = c.vclamp;
        v += vis;
    }
    return v;
}
static void adcRefresh()
{
    if (!adcGrp || !adcBuf) return;
    for (int s = 0; s < adcGrp->num_channels; s++)
    {
        float v = chanVolts(adcChanOfSlot(s)); if (v < 0) v = 0; if (v > vdda) v = vdda;
        adcBuf[s] = (adcsample_t)lroundf(v / vdda * 4095.0f);
    }
}
void adcStartConversion(ADCDriver *, const ADCConversionGroup *g, adcsample_t *samples, size_t) { adcGrp = g; adcBuf = samples; adcRefresh(); }

//================================================================== device stubs (class level)
msg_t i2cStart(I2CDriver *, const I2CConfig *) { return MSG_OK; }
static uint8_t framMem[32768]; static uint32_t framSize = 32768; static uint32_t framWrites = 0; static bool framInit = false;
static void framEnsure() { if (!framInit) { memset(framMem, 0xFF, sizeof(framMem)); framInit = true; } }
bool MB85RC::CheckId() { return true; }
bool MB85RC::GetId(uint16_t *m, uint16_t *p) { *m = MB85RC_MANUF_ID; *p = MB85RC_PROD_ID; return true; }
bool MB85RC::Read(uint16_t a, uint8_t *d, uint16_t n) { framEnsure(); for (uint32_t i = 0; i < n; i++) d[i] = framMem[(a + i) % framSize]; return true; }
bool MB85RC::Write(uint16_t a, uint8_t *d, uint16_t n) { framEnsure(); framWrites++; for (uint32_t i = 0; i < n; i++) framMem[(a + i) % framSize] = d[i]; return true; }
static float boardTempC = 30.0f;
// MCP9808 (Microchip DS25095A) at register-behaviour level: Init writes the config with SHDN = 0 (continuous);
// the ambient register keeps the value from before a shutdown until the first new conversion, tCONV 30 ms typ at
// 0.5 C (Table 1-1); in shutdown no conversions; EnterShutdown turns the alert output off, then sets SHDN.
// mcpFail: the next n reads fail on I2C (-1 = every read until cleared).
static int mcpShutdown = 0, mcpAlertOn = 0, mcpFail = 0; static uint32_t mcpShutdownCalls = 0, mcpReads = 0, mcpFailed = 0;
static float mcpHeld = NAN; static uint64_t mcpFreshAt = 0;
bool MCP9808::Init(float, float) { mcpShutdown = 0; mcpAlertOn = 1; mcpFreshAt = nowUs + 30000; return true; }
bool MCP9808::ReadTemp(float *t)
{
    mcpReads++;
    if (mcpFail) { if (mcpFail > 0) mcpFail--; mcpFailed++; return false; }
    bool held = !std::isnan(mcpHeld) && (mcpShutdown || nowUs < mcpFreshAt);
    *t = held ? mcpHeld : boardTempC; return true;
}
bool MCP9808::EnterShutdown() { mcpShutdownCalls++; mcpAlertOn = 0; mcpShutdown = 1; mcpHeld = boardTempC; return true; }
float MCP9808::GetTemp() { return boardTempC; }
bool MCP9808::OverTempLimit() { return boardTempC > BOARD_TEMP_WARN; }
bool MCP9808::CritTempLimit() { return boardTempC > BOARD_TEMP_CRIT; }
static bool usbConnected = false;
msg_t InitUsb() { return MSG_OK; }
bool GetUsbConnected() { return usbConnected; }
void EnterStopMode() { asleepFlag = 1; park(); }   // real MCU stops here and resets on wake-up
void RequestBootloader() { bootloaderFlag = 1; park(); }

//================================================================== scheduler loop + C API
static void mainThread(void *)
{
    chThdSleepMilliseconds(500); // as main.cpp
    InitDevice();
    while (true) chThdSleepMilliseconds(500);
}
static uint64_t nextEvent()
{
    uint64_t t = UINT64_MAX;
    for (auto th : threads) if (!th->done && !th->parked && th->wake < t) t = th->wake;
    for (auto p : allPwm) { int k; uint64_t e = pwmNextEvent(p, nowUs, &k); if (e < t) t = e; }
    return t;
}
API void sim_boot() { pins(); framEnsure(); spawn(mainThread, nullptr, nullptr, NORMALPRIO); }
API uint64_t sim_now() { return nowUs; }
API uint64_t sim_next_event() { uint64_t t = nextEvent(); return t < nowUs ? nowUs : t; }
API void sim_run_until(uint64_t target)
{
    for (;;)
    {
        // run every thread that is due (higher priority first, then creation order)
        for (;;)
        {
            thread_t *best = nullptr;
            for (auto th : threads) if (!th->done && !th->parked && th->wake <= nowUs && (!best || th->prio > best->prio)) best = th;
            if (!best || asleepFlag || bootloaderFlag) break;
            cur = best; best->wake = UINT64_MAX; swapcontext(&schedCtx, &best->ctx); cur = nullptr;
            adcRefresh();
        }
        if (asleepFlag || bootloaderFlag) { nowUs = target; return; }
        uint64_t t = nextEvent();
        if (t > target) { nowUs = target; for (auto p : allPwm) pwmSync(p); adcRefresh(); return; }
        // timer interrupts due at t
        uint64_t prev = nowUs; nowUs = t;
        for (auto p : allPwm)
        {
            int kind = 0; uint64_t e = pwmNextEvent(p, prev, &kind);
            while (e <= nowUs)
            {
                if (kind == 0 && p->config->callback) p->config->callback(p);
                if (kind == 1 && p->config->channels[0].callback) p->config->channels[0].callback(p);
                e = pwmNextEvent(p, e, &kind);
            }
            pwmSync(p);
        }
        adcRefresh();
    }
}
// CAN bus side
API int sim_can_started() { return canStarted; }
API uint32_t sim_can_bitrate()
{
    if (!canStarted) return 0;
    uint32_t brp = (canBtr & 0x3FF) + 1, ts1 = ((canBtr >> 16) & 15) + 1, ts2 = ((canBtr >> 20) & 7) + 1;
    return 36000000U / (brp * (1 + ts1 + ts2)); // APB1 = 36 MHz (port.cpp comment)
}
API int sim_can_rx(uint32_t id, int ide, int dlc, const uint8_t *data)
{
    if (!canStarted || asleepFlag) return 0;
    {
        uint32_t reg = ide ? ((id << 3) | 0x04) : (id << 21);
        if (!canFilterAccepts(reg)) { rxFiltered++; return 1; } // acknowledged on the bus, not stored
    }
    if (rxFifo.size() >= 3) { rxOverruns++; return 1; } // bxCAN receive FIFO holds 3 frames
    CANRxFrame f; memset(&f, 0, sizeof(f)); f.IDE = ide; f.DLC = dlc; if (ide) f.EID = id; else f.SID = id;
    memcpy(f.data8, data, 8); rxFifo.push_back(f); simWake(&canRxWaiter); return 1;
}
API int sim_can_tx_peek(uint32_t *id, int *ide, int *dlc, uint8_t *data)
{
    if (txMbx.empty()) return 0;
    CANTxFrame &f = txMbx.front(); *ide = f.IDE; *id = f.IDE ? f.EID : f.SID; *dlc = f.DLC; memcpy(data, f.data8, 8); return 1;
}
API void sim_can_tx_pop() { if (!txMbx.empty()) txMbx.pop_front(); }
// pins
API void sim_set_ext(int port, int pad, int state)
{
    ioline_t l = PAL_LINE(port, pad); int before = level(l, false);
    pins()[port * 16 + pad].ext = state;
    if (pins()[port * 16 + pad].event && lineCb[port][pad] && level(l, false) != before) lineCb[port][pad](lineCbArg[port][pad]);
}
API int sim_get_level(int port, int pad) { return level(PAL_LINE(port, pad), false); }
// pin-level timing: watch up to n output lines (port << 4 | pad), then read and clear their edges (us, index, level)
API void sim_watch_pins(int n, const int *lines) { watchLines.assign(lines, lines + n); edgeLog.clear(); }
API int sim_edges(uint64_t *t, int *idx, int *lv, int max)
{
    int n = (int)std::min(edgeLog.size(), (size_t)max);
    for (int i = 0; i < n; i++) { t[i] = edgeLog[i].t; idx[i] = edgeLog[i].idx; lv[i] = edgeLog[i].level; }
    edgeLog.erase(edgeLog.begin(), edgeLog.begin() + n); return n;
}
API int sim_pin_info(int port, int pad) { Pin &p = pins()[port * 16 + pad]; return p.mode | (p.pupd << 2) | (p.odr << 4) | (p.af << 8) | (p.event << 12); }
API void sim_set_pin_volts(int port, int pad, float v) { pinVolts[port][pad] = v; }
API void sim_set_env(float vbat_, float boardTemp, float dieTemp) { vbat = vbat_; boardTempC = boardTemp; dieTempC = dieTemp; }
API void sim_set_usb(int c) { usbConnected = c; }
API void sim_set_vdda(float v) { vdda = v; }   // presim: VDDA off 3.3 V (TLV1117LV +-1.5 %); VREFINT / TS follow
API int sim_plant_add(int in, int den, int dsel, int dselLevel, int is, float kilis, float rsense, float vclamp)
{
    PlantCh c; c.in = in; c.den = den; c.dsel = dsel < 0 ? 0 : dsel; c.hasDsel = dsel >= 0; c.dselLevel = dselLevel; c.is = is;
    c.kilis = kilis; c.rsense = rsense; c.loadOhms = 0; c.vclamp = vclamp; c.fault = 0; plant.push_back(c); return (int)plant.size() - 1;
}
API void sim_plant_set(int idx, float loadOhms, int fault) { plant[idx].loadOhms = loadOhms; plant[idx].fault = fault; }
// top of the IS chain in volts (zener node, rail-to-rail buffer): a fault or an IS current above the measurable range reads
// this (pdmsim.py Board.set_is_clamp)
API void sim_plant_clamp(int idx, float vclamp) { plant[idx].vclamp = vclamp; }
// state for checks
API int sim_flags() { return fatalFlag | (asleepFlag << 1) | (bootloaderFlag << 2) | (restartFlag << 3); }
API void sim_counters(uint32_t *out)
{
    out[0] = badWrites; out[1] = lastBadWrite; out[2] = floatReads; out[3] = lastFloatRead; out[4] = rxOverruns;
    out[5] = txTimeouts; out[6] = rxFiltered; out[7] = extiClashes; out[8] = framWrites; out[9] = sizeof(DeviceConfig);
    out[10] = NUM_OUTPUTS; out[11] = NUM_DIG_INPUTS; out[12] = NUM_ANALOG_INPUTS; out[13] = VAR_MAP_SIZE; out[14] = canFilterListOnly();
    out[15] = (uint32_t)txMbx.size();
}
API void sim_fram(uint8_t *buf, int load, uint32_t size) { framEnsure(); framSize = size; if (load) memcpy(framMem, buf, size); else memcpy(buf, framMem, size); }
API int sim_exti_port(int pad) { return extiPort[pad]; }
// direct firmware state (cross-check only; scenarios use CAN like a real tool would)
API int sim_out_state(int i) { return (int)pf[i].GetState(); }
API float sim_out_current(int i) { return pf[i].GetCurrent(); }
// MCP9808: fail reads; chip state carried over an MCU reset (no power-on reset): left in shutdown holding 'held'
API void sim_mcp_fail(int n) { mcpFail = n; }
API void sim_mcp_carry(float held) { mcpShutdown = 1; mcpAlertOn = 0; mcpHeld = held; }
API void sim_mcp_info(uint32_t *out)
{
    out[0] = mcpShutdown; out[1] = mcpAlertOn; out[2] = mcpShutdownCalls; out[3] = mcpReads; out[4] = mcpFailed;
    out[5] = GetTempSensorFails();
}
API float sim_var(int i) { extern float *pVarMap[VAR_MAP_SIZE]; return (i < VAR_MAP_SIZE && pVarMap[i]) ? *pVarMap[i] : NAN; }
