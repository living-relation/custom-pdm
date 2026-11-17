#include "profet.h"
#include "dbc.h"

#if NUM_OUTPUTS > 0
void Profet::Update(bool bOutEnabled)
{
    eLastState = eState;

    if (!pConfig->bEnabled)
    {
        pwm.Off();
        palClearLine(m_in);
        nOcCount = 0;
        eState = ProfetState::Off;
        fCurrent = 0;
        fOutput = 0;
#if PRO_FEATURES
        bOverLimit = false; // custom-pdm (P1 / P2)
        UpdateUndercurrent();
#endif
        return;
    }

    // DSEL for dual-channel devices is set by the caller, see SelectDsel()

    // Follower device — mirror primary
    if (pPrimary != nullptr)
    {
        FollowerUpdate();
        return;
    }

    if ((*pInput) && bOutEnabled)
        eReqState = ProfetState::On;
    else
        eReqState = ProfetState::Off;

    MeasureCurrent();

    // Sum follower current into primary's reported current
    if (pFollower != nullptr && pFollower->eState != ProfetState::Fault)
        fCurrent += pFollower->fCurrent;

    // Check for fault (device overcurrent/overtemp/short)
    // Raw ADC current reading will be very high
    if (nIS > 30000)
    {
        eState = ProfetState::Fault;
    }

    // Follower hardware fault is permanent — bring down the primary too
    if (pFollower != nullptr && pFollower->eState == ProfetState::Fault)
        eState = ProfetState::Fault;

    bInRushActive = (SYS_TIME - nInRushOnTime) < pConfig->nInrushTime;

    switch (eState)
    {
    case ProfetState::Off:
        pwm.Off();

        palClearLine(m_in);

        nOcCount = 0;

        // Check for turn on
        if (eReqState == ProfetState::On)
        {
            nInRushOnTime = SYS_TIME;
            eState = ProfetState::On;
        }
        break;

    case ProfetState::On:
        if (pwm.IsEnabled())
            pwm.On();
        else
            palSetLine(m_in);

        // Check for turn off
        if (eReqState == ProfetState::Off)
        {
            eState = ProfetState::Off;
        }

#if PRO_FEATURES
        // custom-pdm (P1): the trip-time clock runs only while above the current limit after the inrush window
        if (!(fCurrent > pConfig->fCurrentLimit) || bInRushActive)
            bOverLimit = false;
#endif

        // Overcurrent
        if (fCurrent > pConfig->fCurrentLimit && !bInRushActive
#if PRO_FEATURES
            && TripTimeExpired() // custom-pdm (P1)
#endif
            )
        {
            nOcTriggerTime = SYS_TIME;
            nOcCount++;
            eState = ProfetState::Overcurrent;
        }

        // Inrush overcurrent
        if (fCurrent > pConfig->fInrushLimit && bInRushActive)
        {
            nOcTriggerTime = SYS_TIME;
            nOcCount++;
            eState = ProfetState::Overcurrent;
        }

        break;

    case ProfetState::Overcurrent:
        pwm.Off();

        palClearLine(m_in);

        // No reset, or overcurrent count exceeded - latch fault
        // Checked first so nothing below can override it
        if ((pConfig->eResetMode == ProfetResetMode::None) ||
            (pConfig->eResetMode == ProfetResetMode::Count && nOcCount >= pConfig->nResetLimit))
        {
            eState = ProfetState::Fault;
        }
        // Check for turn off
        else if (eReqState == ProfetState::Off)
        {
            eState = ProfetState::Off;
        }
        // Overcurrent reset time exceeded
        // ResetEndless or ResetCount
        else if ((SYS_TIME - nOcTriggerTime) > pConfig->nResetTime)
        {
            nInRushOnTime = SYS_TIME;
            eState = ProfetState::On;
        }
        break;

    case ProfetState::Fault:
        pwm.Off();

        palClearLine(m_in);
        // Fault requires power cycle, no way out
        break;
    }

    pwm.Update();

    // Set var map values
    fOutput = eState == ProfetState::On ? 1 : 0;
    fOvercurrent = eState == ProfetState::Overcurrent ? 1 : 0;
    fFault = eState == ProfetState::Fault ? 1 : 0;

#if PRO_FEATURES
    // custom-pdm (P1 / P2)
    if (eState != ProfetState::On)
        bOverLimit = false;
    UpdateUndercurrent();
#endif

#ifdef LINE_E2
    palClearLine(LINE_E2);
#endif
}

#if PRO_FEATURES
// custom-pdm (P1, docs/feature-parity.md): called while above the current limit after the inrush window. True = trip
// now: trip time 0 (stock behaviour, one sample), above the inrush limit or IS at the ADC full scale (hard
// overcurrent / PROFET fault signal, PROFET_IS_FULL_SCALE), or above the limit for the whole trip time.
bool Profet::TripTimeExpired()
{
    if (pExt == nullptr || pExt->nTripTime == 0)
        return true;

    if (fCurrent > pConfig->fInrushLimit || nIS >= PROFET_IS_FULL_SCALE)
        return true;

    if (!bOverLimit)
    {
        bOverLimit = true;
        nOverLimitStart = SYS_TIME;
    }

    return (uint32_t)(SYS_TIME - nOverLimitStart) >= pExt->nTripTime;
}

// custom-pdm (P2, ECUMaster PMU "Min current" -> UNDERCURRENT): while the output is On (and its PWM duty is not 0),
// a current below fMinCurrent for nMinCurrentTime sets fUndercurrent; the output keeps running. The flag clears at
// once when the current is back at or above the minimum, or the output is not On.
void Profet::UpdateUndercurrent()
{
    const bool bWatch = (pExt != nullptr) && (pExt->fMinCurrent > 0) && (eState == ProfetState::On) &&
                        !(pwm.IsEnabled() && pwm.GetDutyCycle() == 0);

    if (bWatch && fCurrent < pExt->fMinCurrent)
    {
        if (!bUnderLimit)
        {
            bUnderLimit = true;
            nUnderLimitStart = SYS_TIME;
        }
        if ((uint32_t)(SYS_TIME - nUnderLimitStart) >= pExt->nMinCurrentTime)
            fUndercurrent = 1;
    }
    else
    {
        bUnderLimit = false;
        fUndercurrent = 0;
    }
}
#endif

void Profet::FollowerUpdate()
{
    MeasureCurrent();

    // Hardware fault — independent, permanent
    if (nIS > 30000)
        eState = ProfetState::Fault;

    if (eState == ProfetState::Fault)
    {
        pwm.Off();
        palClearLine(m_in);
        fOutput = 0; 
        fOvercurrent = 0; 
        fFault = 1;
        return;
    }

    // Mirror primary state
    if (pPrimary->eState == ProfetState::On)
    {
        if (pPrimary->IsPwmEnabled())
        {
            pwm.EnsureStarted();
            pwm.OverrideFrequency(pPrimary->GetFrequency());
            pwm.SetDutyCycle(pPrimary->GetDutyCycle());
            // Align follower timer phase to primary on first enable so both switches
            // transition simultaneously. Both timers share the same APB clock so
            // there is no ongoing drift — only the initial phase offset needs fixing.
            if (eLastState != ProfetState::On)
                m_pwmDriver->tim->CNT = pPrimary->m_pwmDriver->tim->CNT;
            pwm.On();
        }
        else
        {
            pwm.Off();
            palSetLine(m_in);
        }
        eState = ProfetState::On;
    }
    else
    {
        pwm.Off();
        palClearLine(m_in);
        eState = pPrimary->eState;
    }

    fOutput = eState == ProfetState::On ? 1 : 0;
    fOvercurrent = eState == ProfetState::Overcurrent ? 1 : 0;
    fFault = 0;
}

#if SLEEP_LOW_POWER
void Profet::Sleep()
{
    // Infineon PROFET+2 12V data sheets: with IN low and DEN high the part draws IGND(STBY) / IGND(OFF_D)
    // 1.2 mA typ, 1.8 mA max (BTS7008-2EPA Table 10 P_6.5.1.5, BTS70012-1ESP P_6.5.25.5, BTS7004-1EPP P_6.5.21.5);
    // with IN and DEN low (BTS7008-2EPA: DSEL low too, section 6.1.3) it is in sleep / OFF mode, under 2.2 uA.
    // IN is already low: EnterSleep calls the upstream ForceOff() (PWM off, IN low) first; this adds DEN / DSEL.
    // No current is read after this: the MCU stops and resets on wake-up (constructor sets DEN high again).
    palClearLine(m_den);
    if (m_model == ProfetModel::BTS7008_2EPA_CH1 || m_model == ProfetModel::BTS7008_2EPA_CH2)
        palClearLine(m_dsel);
}
#endif

void Profet::SelectDsel()
{
    // Select the IS channel on dual-channel devices
    // Caller waits DSEL_SETTLE_US before measuring, once for all outputs in the pass
    if (m_model == ProfetModel::BTS7008_2EPA_CH1)
        palClearLine(m_dsel);
    else if (m_model == ProfetModel::BTS7008_2EPA_CH2)
        palSetLine(m_dsel);
}

void Profet::MeasureCurrent()
{
    if (pwm.IsEnabled() && eState == ProfetState::On)
    {
        // Assign to local vars to prevent CNT rolling over and slipping past check
        // Example:
        // CCR = 2500
        // When checking read delay CNT = 2499
        // Before getting to the CNT < CCR check the CNT has rolled over to 0
        // This will cause an incorrect reading
        // Copying to local var freezes the CNT value
        uint32_t nCCR = m_pwmDriver->tim->CCR[static_cast<uint8_t>(m_pwmChannel)];
        uint32_t nCNT = m_pwmDriver->tim->CNT;

        // Delay for the first 1/3 of the PWM period to allow current to stabilize after switching, or a fixed min delay if the period is very short. 
        // This ensures we don't read during the switching transient
        uint32_t nDelay = (nCCR / 3 > nPwmReadDelay) ? nCCR / 3 : nPwmReadDelay;

        if ((nCCR > nDelay) &&
            (nCNT > nDelay) &&
            (nCNT < nCCR))
        {
            //==============================================================================
            //Trigger E2 on channel 1 for debug purposes to verify timing
#ifdef LINE_E2
            if (m_num == 1)
                palSetLine(LINE_E2);
#endif
            //==============================================================================

            nIS = GetAdcRaw(m_ain);
            nLastIS = nIS;
        }
        else
        {
            nIS = nLastIS;
        }
    }
    else
        nIS = GetAdcRaw(m_ain);

    CalculateCurrent();
}

#ifndef BTS7004_1EPP_KILIS
// custom-pdm: see the Profet constructor (profet.h): no BTS7004_1EPP case on boards without it
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wswitch"
#endif
void Profet::CalculateCurrent()
{
    // Current = (rawVal * (VDDA / 4095)) / 1.2k) * kILIS
    fCurrent = (((float)nIS * (GetVDDA() / 4095)) / 1200) * fKILIS;

    // Noise floor — ignore current below measurable threshold
    switch (m_model)
    {
    case ProfetModel::BTS7002_1EPP:
        if (fCurrent <= 0.5f)
            fCurrent = 0;
        break;
    case ProfetModel::BTS7008_2EPA_CH1:
    case ProfetModel::BTS7008_2EPA_CH2:
        if (fCurrent <= 0.2f)
            fCurrent = 0;
        break;
    case ProfetModel::BTS70012_1ESP:
        if (fCurrent <= 1.0f)
            fCurrent = 0;
        break;
#ifdef BTS7004_1EPP_KILIS
    case ProfetModel::BTS7004_1EPP:
        // custom-pdm: same floor as BTS7002-1EPP (similar kILIS). Not measured. Only on boards that fit it
        // (custompdm_b), so stock builds keep the stock switch.
        if (fCurrent <= 0.5f)
            fCurrent = 0;
        break;
#endif
    }
}
#ifndef BTS7004_1EPP_KILIS
#pragma GCC diagnostic pop
#endif

#endif
