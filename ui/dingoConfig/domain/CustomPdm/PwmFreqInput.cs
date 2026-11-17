using System.Text.Json.Serialization;
using domain.Models;

namespace domain.CustomPdm;

// custom-pdm (not upstream): PWM frequency from a variable on one output (tach-style output: a 50 % square wave whose
// frequency follows e.g. engine RPM from the ECU on CAN). Firmware param block 0x7C00 + output, in the firmware's
// order, types, ranges and defaults (firmware/core/param_defs.h OUTPUT_FREQ_PARAMS, functions/pwm.h PWM_FREQ_MIN_HZ /
// PWM_FREQ_MAX_HZ). frequency Hz = input x factor; below MinHz no pulses (output low), above MaxHz held at MaxHz. The
// duty is the output's normal PWM duty (PWM on, fixed duty 50 % for a tachometer).
public class PwmFreqInput
{
    public const int MinHzLimit = 16, MaxHzLimit = 1000;        // 16-bit timer at 1 MHz: 65536 counts = 15.3 Hz
    public const double FactorMin = 0.0, FactorMax = 1000.0;
    public const double DefaultFactor = 1.0;

    [JsonPropertyName("enabled")] public bool Enabled { get; set; }
    [JsonPropertyName("input")] public int Input { get; set; }
    [JsonPropertyName("factor")] public double Factor { get; set; } = DefaultFactor;   // Hz per input unit
    [JsonPropertyName("minHz")] public int MinHz { get; set; } = MinHzLimit;
    [JsonPropertyName("maxHz")] public int MaxHz { get; set; } = MaxHzLimit;

    // Tachometer from engine RPM: factor = pulses per revolution / 60 (4-stroke: cylinders / 2 pulses per rev)
    [JsonIgnore]
    public double PulsesPerRev
    {
        get => Factor * 60.0;
        set => Factor = value / 60.0;
    }

    public bool IsValid() =>
        Factor is >= FactorMin and <= FactorMax && MinHz is >= MinHzLimit and <= MaxHzLimit &&
        MaxHz is >= MinHzLimit and <= MaxHzLimit;

    public List<DeviceParameter> GetParams(string parentName, int index, int number) =>
    [
        new()
        {
            ParentName = parentName, Name = $"customPdm.output[{number}].freqFromInput", Index = index, SubIndex = 0,
            GetValue = () => Enabled, SetValue = val => Enabled = (bool)val, ValueType = typeof(bool), DefaultValue = false
        },
        new()
        {
            ParentName = parentName, Name = $"customPdm.output[{number}].freqInput", Index = index, SubIndex = 1,
            GetValue = () => Input, SetValue = val => Input = Convert.ToInt32(val), ValueType = typeof(int), DefaultValue = 0
        },
        new()
        {
            ParentName = parentName, Name = $"customPdm.output[{number}].freqFactor", Index = index, SubIndex = 2,
            GetValue = () => Factor, SetValue = val => Factor = Convert.ToDouble(val), ValueType = typeof(double),
            DefaultValue = DefaultFactor
        },
        new()
        {
            ParentName = parentName, Name = $"customPdm.output[{number}].freqMin", Index = index, SubIndex = 3,
            GetValue = () => MinHz, SetValue = val => MinHz = Convert.ToInt32(val), ValueType = typeof(int), DefaultValue = MinHzLimit
        },
        new()
        {
            ParentName = parentName, Name = $"customPdm.output[{number}].freqMax", Index = index, SubIndex = 4,
            GetValue = () => MaxHz, SetValue = val => MaxHz = Convert.ToInt32(val), ValueType = typeof(int), DefaultValue = MaxHzLimit
        }
    ];
}
