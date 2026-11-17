#pragma once

#include "hal.h"
#include <cstdint>
#include "port.h"
#include "custom_options.h"

#define PWM_UPDATE_TIME 2.0 //ms

#if PWM_FREQ_INPUT
// custom-pdm: frequency from a variable (tach-style output), param block 0x7C00 + output (core/param_defs.h).
// The output timers count at 1 MHz (port_pwm.h PWMConfig.frequency) and most are 16-bit (TIM3/4/9-13; RM0390), so the
// longest period is 65536 counts = 15.3 Hz: 16 Hz is the lowest setting. 1000 Hz: PROFET+2 switching times are well
// inside a 500 us half period (BTS7008-2EPA tON / tOFF max 110 / 100 us, P_7.4.1.3 / .4) and a V12 at 9000 RPM needs 900 Hz.
#define OUTPUT_FREQ_BASE 0x7C00 // param block, + output index (core/param_defs.h, config_handler.cpp ApplyConfig)
#define PWM_FREQ_MIN_HZ 16
#define PWM_FREQ_MAX_HZ 1000
#endif

#if NUM_OUTPUTS > 0

extern float *pVarMap[VAR_MAP_SIZE];

struct Config_PwmOutput{
  bool bEnabled;
  bool bSoftStart;
  bool bVariableDutyCycle;
  uint16_t nDutyCycleInput;
  uint8_t nFixedDutyCycle;
  uint16_t nFreq;
  uint16_t nSoftStartRampTime; //ms
  uint16_t nDutyCycleInputDenom;
  uint16_t nMinDutyCycle;
#if PWM_FREQ_INPUT
  bool bVariableFreq;   // custom-pdm: frequency = input x factor (else nFreq)
  uint16_t nFreqInput;  // var map index, e.g. a CAN input carrying engine RPM
  float fFreqFactor;    // Hz per input unit: pulses per rev / 60 for RPM
  uint16_t nFreqMin;    // Hz: below it no pulses, output low (engine stopped, signal lost)
  uint16_t nFreqMax;    // Hz: above it held at this frequency
#endif
};

class Pwm
{
public:
    Pwm(PWMDriver *pwm, const PWMConfig *pwmCfg, PwmChannel pwmCh)
        : m_pwm(pwm), m_pwmCfg(pwmCfg), m_pwmCh(pwmCh)
    {
    }

    static const uint16_t nBaseIndex = 0x1100;

    void SetConfig(Config_PwmOutput *config)
    {
        pConfig = config;
        pInput = pVarMap[config->nDutyCycleInput];
#if PWM_FREQ_INPUT
        pFreqInput = pVarMap[config->nFreqInput];
#endif

        if ((pConfig->bEnabled) && (m_pwm->state != PWM_READY))
            Init();
    }

    void Update();

    bool IsEnabled(){return pConfig->bEnabled;};

    uint8_t GetDutyCycle()
    {
        if (pConfig->bEnabled)
            return nDutyCycle;

        return 0;
    };

    void SetDutyCycle(uint16_t nDC)
    {
        if (nDC > 100)
            nDC = 100;

        if (nDC < pConfig->nMinDutyCycle)
            nDC = pConfig->nMinDutyCycle;

        nDutyCycle = nDC;
    };

    
    void On();
    void Off();
    void EnsureStarted();
    void OverrideFrequency(uint16_t nFreq);
#if PWM_FREQ_INPUT
    // custom-pdm: a paired follower copies the primary's timer period (fixed or variable frequency)
    pwmcnt_t GetPeriod() { return m_pwm->period; }
    void OverridePeriod(pwmcnt_t nPeriod);
#endif

private:
    PWMDriver *m_pwm;
    const PWMConfig *m_pwmCfg;
    PwmChannel m_pwmCh;

    float *pInput;

    Config_PwmOutput *pConfig;

    msg_t Init();
    uint8_t GetTargetDutyCycle();
    void InitSoftStart();
    void UpdateSoftStart();
    void UpdateFrequency();
#if PWM_FREQ_INPUT
    void UpdateVariableFrequency();
    float *pFreqInput;
    bool bFreqOff = false; // variable frequency below its minimum: duty 0 (no pulses)
#endif

    volatile uint16_t nDutyCycle;
    uint16_t nLastFreq;

    bool bChannelEnabled;
    bool bLastChannelEnabled;
    bool bSoftStartComplete;
    float fSoftStartStep;
    
    uint32_t nSoftStartTime;
    uint32_t nSoftStartEndTime;
};
#endif