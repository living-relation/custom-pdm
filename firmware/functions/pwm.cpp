#include "pwm.h"
#include "dbc.h"

#if NUM_OUTPUTS > 0
void Pwm::Update()
{
    bChannelEnabled = (bool)(m_pwm->enabled & (1 << static_cast<uint8_t>(m_pwmCh)));

    if (!pConfig->bEnabled || !bChannelEnabled) {
        bLastChannelEnabled = bChannelEnabled;
        bSoftStartComplete = false;
        nDutyCycle = 0;
    }

    if (!pConfig->bSoftStart) {
        nDutyCycle = GetTargetDutyCycle();
    }
    else
    {
        // Initialize soft start
        if (bChannelEnabled != bLastChannelEnabled) {
            InitSoftStart();
        }
        
        // Update soft start
        if (!bSoftStartComplete) {
            UpdateSoftStart();
        }
        // After soft start completes, continue updating duty cycle if variable
        else if (pConfig->bVariableDutyCycle) {
            nDutyCycle = GetTargetDutyCycle();
        }
    }

    UpdateFrequency();
#if PWM_FREQ_INPUT
    // custom-pdm: variable frequency below its minimum = no pulses (output low)
    if (bFreqOff)
        nDutyCycle = 0;
#endif
    
    bLastChannelEnabled = bChannelEnabled;
}

uint8_t Pwm::GetTargetDutyCycle() {
    if (pConfig->bVariableDutyCycle && pConfig->nDutyCycleInputDenom > 0) {
        // Clamp duty cycle to 100% and minimum duty cycle
        float fDc = (*pInput) / pConfig->nDutyCycleInputDenom;
        if (fDc > 100.0f)
            fDc = 100.0f;
        if (!(fDc >= pConfig->nMinDutyCycle))
            fDc = pConfig->nMinDutyCycle;
        return (uint8_t)fDc;
    }
    return pConfig->nFixedDutyCycle;
}

void Pwm::InitSoftStart() {
    nSoftStartTime = SYS_TIME;

    // No ramp time configured - go straight to target instead of dividing by zero
    if (pConfig->nSoftStartRampTime == 0) {
        nDutyCycle = GetTargetDutyCycle();
        bSoftStartComplete = true;
        return;
    }

    fSoftStartStep = GetTargetDutyCycle() / (float)pConfig->nSoftStartRampTime;
    bSoftStartComplete = false;
}

void Pwm::UpdateSoftStart() {
    uint8_t targetDuty = GetTargetDutyCycle();
    // Compare in float - the ramp can overshoot 255 in one step on short ramps
    float fDuty = (fSoftStartStep * (SYS_TIME - nSoftStartTime)) + pConfig->nMinDutyCycle;

    if (fDuty >= targetDuty) {
        nDutyCycle = targetDuty;
        bSoftStartComplete = true;
    }
    else {
        nDutyCycle = (uint8_t)fDuty;
    }
}

void Pwm::UpdateFrequency()
{
    // Outputs can share a timer, so only the Ch1 output sets its frequency
    if (m_pwmCh != PwmChannel::Ch1 || m_pwm->state != PWM_READY)
        return;

#if PWM_FREQ_INPUT
    if (pConfig->bVariableFreq)
    {
        UpdateVariableFrequency();
        return;
    }
    bFreqOff = false;
#endif

    // Frequency within range and
    // (Frequency setting has changed or
    // PWM driver frequency != Frequency setting)
    if (((pConfig->nFreq <= 400) && (pConfig->nFreq > 0)) &&
        ((pConfig->nFreq != nLastFreq) ||
        (m_pwm->period != (m_pwmCfg->frequency / pConfig->nFreq))))
    {
        pwmChangePeriod(m_pwm, m_pwmCfg->frequency / pConfig->nFreq);
    }

    nLastFreq = pConfig->nFreq;
}

#if PWM_FREQ_INPUT
void Pwm::UpdateVariableFrequency()
{
    // custom-pdm: frequency = input x factor, e.g. engine RPM x pulses per rev / 60 for a tachometer.
    // NaN or below the minimum (engine stopped, signal lost): no pulses, see Update()
    float fFreq = (*pFreqInput) * pConfig->fFreqFactor;
    if (!(fFreq >= pConfig->nFreqMin))
    {
        bFreqOff = true;
        return;
    }
    bFreqOff = false;
    if (fFreq > pConfig->nFreqMax)
        fFreq = pConfig->nFreqMax;

    // Timer counts per period, rounded: 1 us steps at 1 MHz (0.1 % at 1000 Hz); at most 62500 (16 Hz), fits 16 bits
    pwmcnt_t nPeriod = (pwmcnt_t)((float)m_pwmCfg->frequency / fFreq + 0.5f);
    pwmcnt_t nOldPeriod = m_pwm->period;
    if (nPeriod == nOldPeriod)
        return;

    // ARR and CCR1 are both preloaded (ChibiOS pwm_lld_start sets CR1.ARPE and CCMR1.OC1PE): the timer takes them at
    // its next update event, so the running period is never cut short. The duty is written for the new period here
    // (On() would only do it next cycle), in the order that keeps the compare value inside whichever period runs if the
    // update event falls between the two writes: shorter period = compare value first, longer period = period first.
    uint8_t nCh = static_cast<uint8_t>(m_pwmCh);
    bool bOn = (m_pwm->enabled & (1 << nCh)) != 0;
    pwmcnt_t nWidth = (pwmcnt_t)(((uint32_t)nPeriod * nDutyCycle * 100U) / 10000U); // PWM_PERCENTAGE_TO_WIDTH
    if (bOn && (nPeriod < nOldPeriod))
        pwmEnableChannel(m_pwm, nCh, nWidth);
    pwmChangePeriod(m_pwm, nPeriod);
    if (bOn && (nPeriod > nOldPeriod))
        pwmEnableChannel(m_pwm, nCh, nWidth);
}

void Pwm::OverridePeriod(pwmcnt_t nPeriod)
{
    if (m_pwmCh == PwmChannel::Ch1 && m_pwm->state == PWM_READY && nPeriod > 0 && m_pwm->period != nPeriod)
        pwmChangePeriod(m_pwm, nPeriod);
}
#endif

msg_t Pwm::Init()
{
    return pwmStart(m_pwm, m_pwmCfg);
}

void Pwm::EnsureStarted()
{
    if (m_pwm->state != PWM_READY)
        Init();
}

void Pwm::OverrideFrequency(uint16_t nFreq)
{
    if (m_pwmCh == PwmChannel::Ch1 && m_pwm->state == PWM_READY &&
        nFreq > 0 && nFreq <= 400 &&
        m_pwm->period != (m_pwmCfg->frequency / nFreq))
    {
        pwmChangePeriod(m_pwm, m_pwmCfg->frequency / nFreq);
    }
}

void Pwm::On()
{
    // PWM duty cycle is 0-10000
    //  100% = 10000
    //  50% = 5000
    //  0% = 0
    pwmEnableChannel(m_pwm, static_cast<uint8_t>(m_pwmCh), PWM_PERCENTAGE_TO_WIDTH(m_pwm, nDutyCycle * 100));
    pwmEnablePeriodicNotification(m_pwm);
    pwmEnableChannelNotification(m_pwm, static_cast<uint8_t>(m_pwmCh));
}

void Pwm::Off()
{
    pwmDisableChannel(m_pwm, static_cast<uint8_t>(m_pwmCh));
    // Period callback is shared by every channel on the timer
    if (m_pwm->enabled == 0)
        pwmDisablePeriodicNotification(m_pwm);
}
#endif