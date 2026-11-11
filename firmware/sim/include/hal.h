// custom-pdm host simulation: minimal ChibiOS RT + HAL stand-in.
// Only what dingoFW uses. Behaviour notes are next to each part.
#pragma once
#include <cstdint>
#include <cstddef>
#include <cstring>
#include <deque>

#ifndef TRUE
#define TRUE 1
#define FALSE 0
#endif

typedef int32_t msg_t;
typedef uint32_t systime_t;
typedef uint32_t sysinterval_t;
typedef uint32_t ioline_t;
typedef uint16_t adcsample_t;
typedef uint16_t i2caddr_t;
typedef uint32_t i2cflags_t;

#define MSG_OK 0
#define MSG_TIMEOUT -1
#define MSG_RESET -2
#define HAL_RET_SUCCESS MSG_OK

//------------------------------------------------------------------ time
// Same tick as the real chconf.h: 10 kHz (100 us per tick).
#define CH_CFG_ST_FREQUENCY 10000
#define TIME_IMMEDIATE ((sysinterval_t)0)
#define TIME_INFINITE ((sysinterval_t)-1)
#define TIME_MS2I(ms) ((sysinterval_t)((ms) * (CH_CFG_ST_FREQUENCY / 1000)))
#define TIME_I2MS(t) ((uint32_t)((t) / (CH_CFG_ST_FREQUENCY / 1000)))
systime_t chVTGetSystemTimeX();
void chThdSleepMilliseconds(uint32_t ms);
void chThdSleepMicroseconds(uint32_t us);

//------------------------------------------------------------------ threads
#define NORMALPRIO 128
struct thread_t;
typedef void (*tfunc_t)(void *);
#define THD_WORKING_AREA(name, size) uint8_t name[1]
thread_t *chThdCreateStatic(void *wa, size_t size, int prio, tfunc_t fn, void *arg);
void chRegSetThreadName(const char *name);
bool chThdShouldTerminateX();
void chThdExit(msg_t msg);
void chThdTerminate(thread_t *t);
msg_t chThdWait(thread_t *t);
#define osalDbgAssert(c, r) do { } while (0)

//------------------------------------------------------------------ PAL
#define GPIOA 0U
#define GPIOB 1U
#define GPIOC 2U
#define GPIOD 3U
#define GPIOE 4U
#define GPIOF 5U
#define GPIOG 6U
#define GPIOH 7U
#define PAL_LINE(port, pad) ((ioline_t)(((port) << 4) | (pad)))
#define PAL_MODE_INPUT 0x00U
#define PAL_MODE_INPUT_PULLUP 0x20U
#define PAL_MODE_INPUT_PULLDOWN 0x40U
#define PAL_EVENT_MODE_BOTH_EDGES 3U
#define PAL_STM32_PUPDR_FLOATING 0x00U
#define PAL_STM32_PUPDR_PULLUP 0x20U
#define PAL_STM32_PUPDR_PULLDOWN 0x40U
void palSetLine(ioline_t l);
void palClearLine(ioline_t l);
void palToggleLine(ioline_t l);
void palWriteLine(ioline_t l, int v);
bool palReadLine(ioline_t l);
void palSetLineMode(ioline_t l, uint32_t mode);
void palEnableLineEvent(ioline_t l, uint32_t mode);

//------------------------------------------------------------------ CAN (bxCAN)
#define CAN_IDE_STD 0
#define CAN_IDE_EXT 1
#define CAN_RTR_DATA 0
#define CAN_ANY_MAILBOX 0
#define CAN_MCR_ABOM (1U << 6)
#define CAN_MCR_AWUM (1U << 5)
#define CAN_MCR_TXFP (1U << 2)
#define CAN_BTR_BRP(n) (n)
#define CAN_BTR_TS1(n) ((n) << 16)
#define CAN_BTR_TS2(n) ((n) << 20)
#define CAN_BTR_SJW(n) ((n) << 24)
#define STM32_CAN_MAX_FILTERS 28
struct CANTxFrame
{
    struct { uint8_t DLC : 4; uint8_t RTR : 1; uint8_t IDE : 1; };
    union { struct { uint32_t SID : 11; }; struct { uint32_t EID : 29; }; };
    union { uint8_t data8[8]; uint16_t data16[4]; uint32_t data32[2]; uint64_t data64[1]; };
};
struct CANRxFrame
{
    struct { uint8_t FMI; uint16_t TIME; };
    struct { uint8_t DLC : 4; uint8_t RTR : 1; uint8_t IDE : 1; };
    union { struct { uint32_t SID : 11; }; struct { uint32_t EID : 29; }; };
    union { uint8_t data8[8]; uint16_t data16[4]; uint32_t data32[2]; uint64_t data64[1]; };
};
struct CANConfig { uint32_t mcr; uint32_t btr; };
struct CANFilter
{
    uint32_t filter : 16; uint32_t mode : 1; uint32_t scale : 1; uint32_t assignment : 1;
    uint32_t register1; uint32_t register2;
};
struct CANDriver { int dummy; };
extern CANDriver CAND1;
msg_t canStart(CANDriver *c, const CANConfig *cfg);
void canStop(CANDriver *c);
msg_t canTransmitTimeout(CANDriver *c, int mb, const CANTxFrame *f, sysinterval_t timeout);
msg_t canReceiveTimeout(CANDriver *c, int mb, CANRxFrame *f, sysinterval_t timeout);
void canSTM32SetFilters(CANDriver *c, uint32_t can2sb, uint32_t num, const CANFilter *cfp);

//------------------------------------------------------------------ PWM (timers used as software PWM)
struct PWMDriver;
typedef void (*pwmcallback_t)(PWMDriver *pwmp);
typedef uint32_t pwmcnt_t;
#define PWM_OUTPUT_DISABLED 0
#define PWM_OUTPUT_ACTIVE_HIGH 1
enum { PWM_UNINIT = 0, PWM_STOP = 1, PWM_READY = 2 };
struct PWMChannelConfig { uint32_t mode; pwmcallback_t callback; };
struct PWMConfig
{
    uint32_t frequency; pwmcnt_t period; pwmcallback_t callback;
    PWMChannelConfig channels[4];
    uint32_t cr2; uint32_t bdtr; uint32_t dier;
};
struct SimTim { uint32_t CNT; uint32_t CCR[4]; };
struct PWMDriver
{
    int state; const PWMConfig *config; pwmcnt_t period; uint32_t enabled;
    SimTim *tim;
    // simulation only
    SimTim simTim; uint64_t t0; bool periodicNotify; uint32_t chNotify; int num;
};
extern PWMDriver PWMD1, PWMD2, PWMD3, PWMD4, PWMD5, PWMD8, PWMD9, PWMD10, PWMD11, PWMD12, PWMD13, PWMD14;
#define PWM_PERCENTAGE_TO_WIDTH(pwmp, percentage) ((pwmcnt_t)((((pwmcnt_t)(pwmp)->period) * (pwmcnt_t)(percentage)) / (pwmcnt_t)10000))
msg_t pwmStart(PWMDriver *p, const PWMConfig *cfg);
void pwmChangePeriod(PWMDriver *p, pwmcnt_t period);
void pwmEnableChannel(PWMDriver *p, uint8_t ch, pwmcnt_t width);
void pwmDisableChannel(PWMDriver *p, uint8_t ch);
void pwmEnablePeriodicNotification(PWMDriver *p);
void pwmDisablePeriodicNotification(PWMDriver *p);
void pwmEnableChannelNotification(PWMDriver *p, uint8_t ch);
void pwmDisableChannelNotification(PWMDriver *p, uint8_t ch);

//------------------------------------------------------------------ ADC (ADCv2, register macros copied from ChibiOS)
#include "sim_adc_regs.h"
struct ADCDriver { int dummy; };
typedef void (*adccallback_t)(ADCDriver *);
struct ADCConversionGroup
{
    bool circular; uint16_t num_channels; adccallback_t end_cb; void *error_cb;
    uint32_t cr1; uint32_t cr2; uint32_t smpr1; uint32_t smpr2;
    uint16_t htr; uint16_t ltr; uint32_t sqr1; uint32_t sqr2; uint32_t sqr3;
};
extern ADCDriver ADCD1;
msg_t adcStart(ADCDriver *a, void *cfg);
void adcStop(ADCDriver *a);
void adcStartConversion(ADCDriver *a, const ADCConversionGroup *g, adcsample_t *samples, size_t depth);
void adcStopConversion(ADCDriver *a);
void adcSTM32EnableTSVREFE();

//------------------------------------------------------------------ I2C (devices are modelled at class level)
#define OPMODE_I2C 1
#define FAST_DUTY_CYCLE_2 2
struct I2CConfig { int op_mode; uint32_t clock_speed; int duty_cycle; };
struct I2CDriver { int dummy; };
extern I2CDriver I2CD1;
msg_t i2cStart(I2CDriver *d, const I2CConfig *cfg);

#include "board.h"
