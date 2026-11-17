#pragma once

// custom-pdm (T1, docs/feature-parity.md): 1D lookup table, up to 8 points, linear between points, held at the end
// values outside the x range (as an ECUMaster PMU 2D table). Block 0x7E00 + n (core/param_defs.h TABLE_PARAMS).
// A table is used only when it is enabled, has 2 to TABLE_MAX_POINTS points and its x values rise strictly over those
// points; anything else (the factory "empty" table, an unsorted one) gives 0, the value of a disabled math block.
// The order is checked here, at run time, not on each parameter write: Write All and ApplyTempParams write the
// values one at a time, so a per-write check would refuse a good table half-way through the transfer.
#include <cstdint>
#include "port.h"
#include "custom_options.h"

#if PRO_FEATURES

extern float *pVarMap[VAR_MAP_SIZE];

#define TABLE_MAX_POINTS 8

struct Config_Table{
  bool bEnabled;
  uint8_t nPoints;  //2-8 used; 0 = empty (factory default)
  uint16_t nInput;  //var index of the x value
  float fX[TABLE_MAX_POINTS];
  float fY[TABLE_MAX_POINTS];
};

class LookupTable
{
public:
    static const uint16_t nBaseIndex = 0x7E00;

    void SetConfig(Config_Table *config)
    {
        pConfig = config;
        pInput = pVarMap[config->nInput];
    }

    static bool IsValid(const Config_Table *c)
    {
        if (c->nPoints < 2 || c->nPoints > TABLE_MAX_POINTS)
            return false;
        for (uint8_t i = 1; i < c->nPoints; i++)
            if (!(c->fX[i] > c->fX[i - 1]))
                return false;
        return true;
    }

    void Update()
    {
        if (!pConfig->bEnabled || !IsValid(pConfig))
        {
            fVal = 0;
            return;
        }

        const float x = *pInput;
        const uint8_t n = pConfig->nPoints;
        const float *fX = pConfig->fX;
        const float *fY = pConfig->fY;

        if (x <= fX[0])
        {
            fVal = fY[0];
            return;
        }

        for (uint8_t i = 1; i < n; i++)
        {
            if (x < fX[i])
            {
                fVal = fY[i - 1] + (x - fX[i - 1]) * (fY[i] - fY[i - 1]) / (fX[i] - fX[i - 1]);
                return;
            }
        }

        fVal = fY[n - 1]; // at or above the last x (also a NaN input)
    }

    float fVal = 0;

private:
    Config_Table *pConfig;
    float *pInput;
};

#endif
