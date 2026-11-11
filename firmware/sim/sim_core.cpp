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
static void wr(ioline_t l, int v) { Pin &p = pin(l); if (p.mode != 1) { badWrites++; lastBadWrite = l; } p.odr = v ? 1 : 0; }
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
void palSetLineMode(ioline_t l, uint32_t mode) { Pin &p = pin(l); p.mode = 0; p.pupd = mode == PAL_MODE_INPUT_PULLUP ? 1 : mode == PAL_MODE_INPUT_PULLDOWN ? 2 : 0; }
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

//================================================================== CAN
CANDriver CAND1;
static bool canStarted = false; static uint32_t canBtr = 0;
static std::deque<CANRxFrame> rxFifo; static std::deque<CANTxFrame> txMbx;
static uint32_t rxOverruns = 0, txTimeouts = 0, rxFiltered = 0;
static std::vector<uint32_t> filterIds; static bool filterActive = false;
msg_t canStart(CANDriver *, const CANConfig *cfg) { canStarted = true; canBtr = cfg->btr; return MSG_OK; }
void canStop(CANDriver *) { canStarted = false; txMbx.clear(); rxFifo.clear(); }
void canSTM32SetFilters(CANDriver *, uint32_t, uint32_t num, const CANFilter *cfp)
{
    // num == 0: ChibiOS installs one accept-all filter. Otherwise 32-bit identifier-list filters.
    filterIds.clear(); filterActive = num > 0;
    for (uint32_t i = 0; i < num; i++) { filterIds.push_back(cfp[i].register1); filterIds.push_back(cfp[i].register2); }
}
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
msg_t canReceiveTimeout(CANDriver *, int, CANRxFrame *f, sysinterval_t)
{
    if (rxFifo.empty()) return MSG_TIMEOUT;
    *f = rxFifo.front(); rxFifo.pop_front(); return MSG_OK;
}

//================================================================== PWM timers
PWMDriver PWMD1, PWMD2, PWMD3, PWMD4, PWMD5, PWMD8, PWMD9, PWMD10, PWMD11, PWMD12, PWMD13, PWMD14;
static PWMDriver *allPwm[] = {&PWMD1, &PWMD2, &PWMD3, &PWMD4, &PWMD5, &PWMD8, &PWMD9, &PWMD10, &PWMD11, &PWMD12, &PWMD13, &PWMD14};
static uint64_t cntToUs(PWMDriver *p, uint64_t cnt) { return cnt * 1000000ULL / p->config->frequency; }
static void pwmSync(PWMDriver *p)
{
    if (p->state != PWM_READY) return;
    uint64_t c = (nowUs - p->t0) * p->config->frequency / 1000000ULL;
    p->tim->CNT = (uint32_t)(c % p->period);
}
msg_t pwmStart(PWMDriver *p, const PWMConfig *cfg)
{
    p->tim = &p->simTim; p->config = cfg; p->period = cfg->period; p->state = PWM_READY; p->t0 = nowUs; p->enabled = 0;
    p->periodicNotify = false; p->chNotify = 0; return MSG_OK;
}
void pwmChangePeriod(PWMDriver *p, pwmcnt_t period) { p->period = period; p->t0 = nowUs; }
void pwmEnableChannel(PWMDriver *p, uint8_t ch, pwmcnt_t width) { p->enabled |= 1U << ch; p->tim->CCR[ch] = width; }
void pwmDisableChannel(PWMDriver *p, uint8_t ch) { if (p->state != PWM_READY) return; p->enabled &= ~(1U << ch); p->tim->CCR[ch] = 0; p->chNotify &= ~(1U << ch); }
void pwmEnablePeriodicNotification(PWMDriver *p) { p->periodicNotify = true; }
void pwmDisablePeriodicNotification(PWMDriver *p) { p->periodicNotify = false; }
void pwmEnableChannelNotification(PWMDriver *p, uint8_t ch) { p->chNotify |= 1U << ch; }
void pwmDisableChannelNotification(PWMDriver *p, uint8_t ch) { p->chNotify &= ~(1U << ch); }
// Next timer interrupt (period start, or compare match on channel 0) strictly after 'from'.
static uint64_t pwmNextEvent(PWMDriver *p, uint64_t from, int *kind)
{
    if (p->state != PWM_READY || (!p->periodicNotify && !p->chNotify)) return UINT64_MAX;
    uint64_t perUs = cntToUs(p, p->period); if (perUs == 0) return UINT64_MAX;
    uint64_t k = (from - p->t0) / perUs; uint64_t best = UINT64_MAX;
    for (uint64_t n = k; n <= k + 1; n++)
    {
        uint64_t start = p->t0 + n * perUs;
        if (p->periodicNotify && start > from && start < best) { best = start; *kind = 0; }
        uint64_t cmp = start + cntToUs(p, p->tim->CCR[0]);
        if ((p->chNotify & 1) && p->tim->CCR[0] < p->period && cmp > from && cmp < best) { best = cmp; *kind = 1; }
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
        // (dual parts: for the channel picked by DSEL). A fault drives the sense pin to its maximum.
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
bool MCP9808::Init(float, float) { return true; }
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
    if (filterActive)
    {
        uint32_t reg = ide ? ((id << 3) | 0x04) : (id << 21); bool ok = false;
        for (auto f : filterIds) if (f == reg) ok = true;
        if (!ok) { rxFiltered++; return 1; } // acknowledged on the bus, not stored
    }
    if (rxFifo.size() >= 3) { rxOverruns++; return 1; } // bxCAN receive FIFO holds 3 frames
    CANRxFrame f; memset(&f, 0, sizeof(f)); f.IDE = ide; f.DLC = dlc; if (ide) f.EID = id; else f.SID = id;
    memcpy(f.data8, data, 8); rxFifo.push_back(f); return 1;
}
API int sim_can_tx_peek(uint32_t *id, int *ide, int *dlc, uint8_t *data)
{
    if (txMbx.empty()) return 0;
    CANTxFrame &f = txMbx.front(); *ide = f.IDE; *id = f.IDE ? f.EID : f.SID; *dlc = f.DLC; memcpy(data, f.data8, 8); return 1;
}
API void sim_can_tx_pop() { if (!txMbx.empty()) txMbx.pop_front(); }
// pins
API void sim_set_ext(int port, int pad, int state) { pins()[port * 16 + pad].ext = state; }
API int sim_get_level(int port, int pad) { return level(PAL_LINE(port, pad), false); }
API int sim_pin_info(int port, int pad) { Pin &p = pins()[port * 16 + pad]; return p.mode | (p.pupd << 2) | (p.odr << 4) | (p.af << 8) | (p.event << 12); }
API void sim_set_pin_volts(int port, int pad, float v) { pinVolts[port][pad] = v; }
API void sim_set_env(float vbat_, float boardTemp, float dieTemp) { vbat = vbat_; boardTempC = boardTemp; dieTempC = dieTemp; }
API void sim_set_usb(int c) { usbConnected = c; }
API int sim_plant_add(int in, int den, int dsel, int dselLevel, int is, float kilis, float rsense, float vclamp)
{
    PlantCh c; c.in = in; c.den = den; c.dsel = dsel < 0 ? 0 : dsel; c.hasDsel = dsel >= 0; c.dselLevel = dselLevel; c.is = is;
    c.kilis = kilis; c.rsense = rsense; c.loadOhms = 0; c.vclamp = vclamp; c.fault = 0; plant.push_back(c); return (int)plant.size() - 1;
}
API void sim_plant_set(int idx, float loadOhms, int fault) { plant[idx].loadOhms = loadOhms; plant[idx].fault = fault; }
// state for checks
API int sim_flags() { return fatalFlag | (asleepFlag << 1) | (bootloaderFlag << 2); }
API void sim_counters(uint32_t *out)
{
    out[0] = badWrites; out[1] = lastBadWrite; out[2] = floatReads; out[3] = lastFloatRead; out[4] = rxOverruns;
    out[5] = txTimeouts; out[6] = rxFiltered; out[7] = extiClashes; out[8] = framWrites; out[9] = sizeof(DeviceConfig);
    out[10] = NUM_OUTPUTS; out[11] = NUM_DIG_INPUTS; out[12] = NUM_ANALOG_INPUTS; out[13] = VAR_MAP_SIZE; out[14] = filterActive;
    out[15] = (uint32_t)txMbx.size();
}
API void sim_fram(uint8_t *buf, int load, uint32_t size) { framEnsure(); framSize = size; if (load) memcpy(framMem, buf, size); else memcpy(buf, framMem, size); }
API int sim_exti_port(int pad) { return extiPort[pad]; }
// direct firmware state (cross-check only; scenarios use CAN like a real tool would)
API int sim_out_state(int i) { return (int)pf[i].GetState(); }
API float sim_out_current(int i) { return pf[i].GetCurrent(); }
API float sim_var(int i) { extern float *pVarMap[VAR_MAP_SIZE]; return (i < VAR_MAP_SIZE && pVarMap[i]) ? *pVarMap[i] : NAN; }
