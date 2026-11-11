#pragma once
// Copied verbatim from ChibiOS ../ChibiOS/os/hal/ports/STM32/LLD/ADCv2/hal_adc_lld.h
#define ADC_CHANNEL_IN0         0
#define ADC_CHANNEL_IN1         1
#define ADC_CHANNEL_IN2         2
#define ADC_CHANNEL_IN3         3
#define ADC_CHANNEL_IN4         4
#define ADC_CHANNEL_IN5         5
#define ADC_CHANNEL_IN6         6
#define ADC_CHANNEL_IN7         7
#define ADC_CHANNEL_IN8         8
#define ADC_CHANNEL_IN9         9
#define ADC_CHANNEL_IN10        10
#define ADC_CHANNEL_IN11        11
#define ADC_CHANNEL_IN12        12
#define ADC_CHANNEL_IN13        13
#define ADC_CHANNEL_IN14        14
#define ADC_CHANNEL_IN15        15
#define ADC_CHANNEL_SENSOR      16
#define ADC_CHANNEL_VREFINT     17
#define ADC_CHANNEL_VBAT        18
#define ADC_SAMPLE_3            0
#define ADC_SAMPLE_15           1
#define ADC_SAMPLE_28           2
#define ADC_SAMPLE_56           3
#define ADC_SAMPLE_84           4
#define ADC_SAMPLE_112          5
#define ADC_SAMPLE_144          6
#define ADC_SAMPLE_480          7
#define ADC_SQR1_NUM_CH(n)      (((n) - 1) << 20)
#define ADC_SQR3_SQ1_N(n)       ((n) << 0)
#define ADC_SQR3_SQ2_N(n)       ((n) << 5)
#define ADC_SQR3_SQ3_N(n)       ((n) << 10)
#define ADC_SQR3_SQ4_N(n)       ((n) << 15)
#define ADC_SQR3_SQ5_N(n)       ((n) << 20)
#define ADC_SQR3_SQ6_N(n)       ((n) << 25)
#define ADC_SQR2_SQ7_N(n)       ((n) << 0)
#define ADC_SQR2_SQ8_N(n)       ((n) << 5)
#define ADC_SQR2_SQ9_N(n)       ((n) << 10)
#define ADC_SQR2_SQ10_N(n)      ((n) << 15)
#define ADC_SQR2_SQ11_N(n)      ((n) << 20)
#define ADC_SQR2_SQ12_N(n)      ((n) << 25)
#define ADC_SQR1_SQ13_N(n)      ((n) << 0)
#define ADC_SQR1_SQ14_N(n)      ((n) << 5)
#define ADC_SQR1_SQ15_N(n)      ((n) << 10)
#define ADC_SQR1_SQ16_N(n)      ((n) << 15)
#define ADC_SMPR2_SMP_AN0(n)    ((n) << 0)
#define ADC_SMPR2_SMP_AN1(n)    ((n) << 3)
#define ADC_SMPR2_SMP_AN2(n)    ((n) << 6)
#define ADC_SMPR2_SMP_AN3(n)    ((n) << 9)
#define ADC_SMPR2_SMP_AN4(n)    ((n) << 12)
#define ADC_SMPR2_SMP_AN5(n)    ((n) << 15)
#define ADC_SMPR2_SMP_AN6(n)    ((n) << 18)
#define ADC_SMPR2_SMP_AN7(n)    ((n) << 21)
#define ADC_SMPR2_SMP_AN8(n)    ((n) << 24)
#define ADC_SMPR2_SMP_AN9(n)    ((n) << 27)
#define ADC_SMPR1_SMP_AN10(n)   ((n) << 0)
#define ADC_SMPR1_SMP_AN11(n)   ((n) << 3)
#define ADC_SMPR1_SMP_AN12(n)   ((n) << 6)
#define ADC_SMPR1_SMP_AN13(n)   ((n) << 9)
#define ADC_SMPR1_SMP_AN14(n)   ((n) << 12)
#define ADC_SMPR1_SMP_AN15(n)   ((n) << 15)
#define ADC_SMPR1_SMP_SENSOR(n) ((n) << 18)
#define ADC_SMPR1_SMP_VREF(n)   ((n) << 21)
#define ADC_SMPR1_SMP_VBAT(n)   ((n) << 24)
#define ADC_CR2_SWSTART (1U << 30)
#define ADC_CR2_CONT (1U << 1)
