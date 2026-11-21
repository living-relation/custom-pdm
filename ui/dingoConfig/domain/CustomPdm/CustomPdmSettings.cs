using System.Text.Json.Serialization;
using domain.Devices;
using domain.Models;

namespace domain.CustomPdm;

// custom-pdm (not upstream): settings our firmware adds for device types 14 (board A) and 15 (board B).
// Param block 0x7F00, in the firmware's order, types, ranges and defaults (firmware/core/param_defs.h
// DEVICE_THERMAL_PARAMS / DEVICE_WAKE_PARAMS). The firmware lists the block right after the device block 0x0000
// (firmware/core/param_registry.cpp stParams), so FwDevice.InitParams adds it at the same place: the CRC config check
// runs over the params in list order. Stock device types never get this object.
public class CustomPdmSettings
{
    [JsonIgnore] public const int BaseIndex = 0x7F00;

    public static bool IsCustomType(int deviceType) => deviceType is 14 or 15;

    // Ranges: firmware param_defs.h (min, max). Masks: bit i = output / digital input i.
    public const int TempMin = 0, TempMax = 125;            // sub 0 warn, sub 1 critical (deg C, UInt8)
    public const int HystMin = 1, HystMax = 30;             // sub 2 recovery hysteresis (UInt8)
    public const int MarginMin = 0, MarginMax = 30;         // sub 4 critical-soon margin (UInt8, 0 = off)
    // Defaults: core/device_config.h BOARD_TEMP_WARN / BOARD_TEMP_CRIT, param_defs.h DEFAULT_TEMP_CRIT_HYST /
    // DEFAULT_TEMP_CRIT_SOON_MARGIN / DEFAULT_WAKE_INPUT_MASK. Exempt mask default is 0 except board A unit 2
    // (fan output, 0x0002): one device type covers both units, so the PC default is 0.
    public const int DefaultTempWarn = 55, DefaultTempCrit = 80, DefaultTempCritHyst = 6;
    // custom-pdm (fwsafety, ADR-2026-11-20-presim-findings item 1): board B (type 15) ships with its own limits, from its
    // FEA sensor map (tools/verify_thermal_box.py) and the 105 C MCU / FRAM rating: firmware port_boards.py DEFAULT_TEMP_*
    public const int DefaultTempWarnB = 98, DefaultTempCritB = 104;
    public static int TempWarnDefault(int deviceType) => deviceType == 15 ? DefaultTempWarnB : DefaultTempWarn;
    public static int TempCritDefault(int deviceType) => deviceType == 15 ? DefaultTempCritB : DefaultTempCrit;
    public const int DefaultCritExemptMask = 0, DefaultTempCritSoonMargin = 5, DefaultWakeInputMask = 0;

    [JsonPropertyName("tempWarn")] public int TempWarn { get; set; } = DefaultTempWarn;
    [JsonPropertyName("tempCrit")] public int TempCrit { get; set; } = DefaultTempCrit;
    [JsonPropertyName("tempCritHyst")] public int TempCritHyst { get; set; } = DefaultTempCritHyst;
    [JsonPropertyName("critExemptMask")] public int CritExemptMask { get; set; } = DefaultCritExemptMask;
    [JsonPropertyName("tempCritSoonMargin")] public int TempCritSoonMargin { get; set; } = DefaultTempCritSoonMargin;
    [JsonPropertyName("wakeInputMask")] public int WakeInputMask { get; set; } = DefaultWakeInputMask;

    // PRO_FEATURES (docs/feature-parity.md): P3 master retry var (0x7F00 sub 6, 0 = off), P1 / P2 per output
    // (0x7D00 + o, CustomPdmPro.cs), T1 tables (0x7E00 + n). The firmware registers them right after sub 5, in this
    // order (firmware/core/param_registry.cpp), so GetParams keeps the CRC order.
    [JsonIgnore] public const int OutputExtBaseIndex = 0x7D00, TableBaseIndex = 0x7E00, MasterRetrySub = 6;
    [JsonIgnore] public const int NumTables = 4;     // firmware port.h NUM_TABLES
    [JsonPropertyName("masterRetryInput")] public int MasterRetryInput { get; set; }
    [JsonPropertyName("outputProtection")] public List<OutputProtection> OutputProtection { get; set; } = [];
    [JsonPropertyName("tables")] public List<LookupTable> Tables { get; set; } = [];
    // editor2: the device preset picked per output on /pdm (PdmPresets, a PdmDeviceKind name or ""). A PC-side label
    // saved in the project file only (not a board setting); without it /pdm shows the preset whose values match.
    [JsonPropertyName("outputPresets")] public List<string> OutputPresets { get; set; } = [];
    // var map size of this device (FwDevice.InitVarMap): range of the var-index settings
    [JsonIgnore] public int VarMapSize { get; set; }

    // PWM frequency from a variable (tach-style output), one per output: firmware block 0x7C00 + output
    // (core/param_defs.h OUTPUT_FREQ_PARAMS), listed after the PRO_FEATURES blocks (param_registry.cpp stParams).
    [JsonIgnore] public const int FreqBaseIndex = 0x7C00;
    [JsonPropertyName("pwmFreqInputs")] public List<PwmFreqInput> PwmFreqInputs { get; set; } = [];

    // B3 (u2a): the PC values were set by "New PDM" (PdmFactoryDefaults) = our firmware's factory config, proven equal
    // against the sim. Not saved: a project loaded from a file counts as not read.
    [JsonIgnore] public bool FactoryNew { get; set; }

    // uipolish (PdmProjectFile.cs): saved with the project: the values of this board were a complete set (read from a
    // board, New PDM, starter, or loaded from such a file). null = a file from before this marker.
    [JsonPropertyName("completeSettings")] public bool? CompleteSettings { get; set; }
    // this board came from a project file with a complete set: writable without a Read All, asked about on connect
    [JsonIgnore] public bool FromFile { get; set; }

    [JsonIgnore] public int DeviceType { get; private set; }
    [JsonIgnore] public int NumOutputs { get; private set; }
    [JsonIgnore] public int NumDigitalInputs { get; private set; }
    [JsonIgnore] public int CritExemptMaskMax => (1 << NumOutputs) - 1;
    [JsonIgnore] public int WakeInputMaskMax => (1 << NumDigitalInputs) - 1;

    // Status (cyclic frames, custompdm_*/msg.cpp): msg 3 byte 7 flags, msg 37 raw ADC and STM32 die temperature
    [JsonIgnore] public int ThermalFlags { get; set; }
    [JsonIgnore] public bool OverWarn => (ThermalFlags & 1) != 0;
    [JsonIgnore] public bool CriticalSoon => (ThermalFlags & 2) != 0;
    [JsonIgnore] public bool Critical => (ThermalFlags & 4) != 0;
    [JsonIgnore] public double DieTempC { get; set; }
    [JsonIgnore] public double AnalogRaw { get; set; }

    public void Configure(FwDeviceDef def)
    {
        DeviceType = def.DeviceType;
        NumOutputs = def.NumOutputs;
        NumDigitalInputs = def.NumDigitalInputs;
        // one OutputProtection per output, 4 tables of 8 points (a project file of another size is padded / cut)
        while (OutputProtection.Count < NumOutputs) OutputProtection.Add(new OutputProtection());
        if (OutputProtection.Count > NumOutputs) OutputProtection.RemoveRange(NumOutputs, OutputProtection.Count - NumOutputs);
        while (Tables.Count < NumTables) Tables.Add(new LookupTable());
        if (Tables.Count > NumTables) Tables.RemoveRange(NumTables, Tables.Count - NumTables);
        foreach (var t in Tables) t.Normalize();
        while (PwmFreqInputs.Count < NumOutputs) PwmFreqInputs.Add(new PwmFreqInput());
        if (PwmFreqInputs.Count > NumOutputs) PwmFreqInputs.RemoveRange(NumOutputs, PwmFreqInputs.Count - NumOutputs);
    }

    public void ClearStatus()
    {
        ThermalFlags = 0;
        DieTempC = 0;
        AnalogRaw = 0;
    }

    public List<DeviceParameter> GetParams(string parentName) =>
    [
        Param(parentName, "customPdm.tempWarn", 0, () => TempWarn, v => TempWarn = v, TempWarnDefault(DeviceType)),
        Param(parentName, "customPdm.tempCrit", 1, () => TempCrit, v => TempCrit = v, TempCritDefault(DeviceType)),
        Param(parentName, "customPdm.tempCritHyst", 2, () => TempCritHyst, v => TempCritHyst = v, DefaultTempCritHyst),
        Param(parentName, "customPdm.critExemptMask", 3, () => CritExemptMask, v => CritExemptMask = v, DefaultCritExemptMask),
        Param(parentName, "customPdm.tempCritSoonMargin", 4, () => TempCritSoonMargin, v => TempCritSoonMargin = v, DefaultTempCritSoonMargin),
        Param(parentName, "customPdm.wakeInputMask", 5, () => WakeInputMask, v => WakeInputMask = v, DefaultWakeInputMask),
        Param(parentName, "customPdm.masterRetryInput", MasterRetrySub, () => MasterRetryInput, v => MasterRetryInput = v, 0),
        ..OutputProtection.SelectMany((o, i) => o.GetParams(parentName, i)),
        ..Tables.SelectMany((t, i) => t.GetParams(parentName, i)),
        .. PwmFreqInputs.SelectMany((f, i) => f.GetParams(parentName, FreqBaseIndex + i, i + 1))
    ];

    // Var map entries the firmware appends at the very end (port.h VAR_MAP_PRO_VARS, core/device.cpp InitVarMap):
    // the 4 table outputs, then one undercurrent (open-load) flag per output. Owner of a flag = its output.
    public List<DeviceVariable> GetVarMap(ref int index, IReadOnlyList<domain.Interfaces.IDeviceFunction> outputs)
    {
        var vars = new List<DeviceVariable>();
        for (var n = 0; n < NumTables; n++)
        {
            var name = $"Table {n + 1}";
            vars.Add(new DeviceVariable { GetName = () => name, PropertyName = "Value", DataType = "float", VariableIndex = index++, SingleVariable = true });
        }
        for (var o = 0; o < NumOutputs; o++)
        {
            var output = outputs[o];
            vars.Add(new DeviceVariable { GetName = () => output.Name, PropertyName = "Undercurrent", DataType = "bool", VariableIndex = index++, SingleVariable = false, Owner = output });
        }
        return vars;
    }

    private static DeviceParameter Param(string parentName, string name, int subIndex, Func<int> get, Action<int> set,
        int defaultValue) => new()
    {
        ParentName = parentName, Name = name, Index = BaseIndex, SubIndex = subIndex,
        GetValue = () => get(), SetValue = val => set(Convert.ToInt32(val)),
        ValueType = typeof(int), // UInt8 / UInt16 on the wire, unsigned
        DefaultValue = defaultValue
    };

    // ------------------------------------------------------------------
    // Wake-input rule, same as firmware core/sleep.cpp WakeInputMaskBadBits: one wake source per EXTI line (= pin
    // number), so an input is refused when it sits on the CAN RX / USB D+ / USB D- line number, or when another
    // selected input has the same pin number. Pin numbers: firmware/boards/custompdm_*/board.h LINE_DI1.. (digIn order,
    // hw_devices.cpp), LINE_CAN_RX PB8, LINE_USB_DM PA11, LINE_USB_DP PA12 on both boards.
    // ------------------------------------------------------------------
    private static readonly int[] PadsA = [10, 9, 10, 11, 4, 13, 3];            // PA10 PC9 PC10 PC11 PB4 PC13 PB3
    private static readonly int[] PadsB = [10, 9, 14, 15, 13, 2, 4, 5, 10, 11]; // PA10 PC9 PC14 PC15 PC13 PD2 PB4 PB5 PC10 PC11
    private const int OtherWakeLines = (1 << 8) | (1 << 11) | (1 << 12);       // CAN RX PB8, USB D- PA11, USB D+ PA12

    public static IReadOnlyList<int> DigInPads(int deviceType) => deviceType switch
    {
        14 => PadsA,
        15 => PadsB,
        _ => []
    };

    public static int WakeInputMaskBadBits(int deviceType, int mask)
    {
        var pads = DigInPads(deviceType);
        var bad = 0;
        for (var i = 0; i < pads.Count; i++)
        {
            if ((mask & (1 << i)) == 0) continue;
            if ((OtherWakeLines & (1 << pads[i])) != 0) bad |= 1 << i;
            for (var j = 0; j < pads.Count; j++)
                if (j != i && (mask & (1 << j)) != 0 && pads[j] == pads[i]) bad |= 1 << i;
        }
        return bad;
    }

    // Input i can never wake (it is on the CAN RX / USB line)
    public bool WakeInputNeverAllowed(int i) => WakeInputMaskBadBits(DeviceType, 1 << i) != 0;

    // Input i cannot be added to the current mask (never allowed, or a shared-line partner is already selected)
    public bool WakeInputBlocked(int i) =>
        (WakeInputMask & (1 << i)) == 0 && WakeInputMaskBadBits(DeviceType, WakeInputMask | (1 << i)) != 0;

    public bool IsValid() =>
        TempWarn is >= TempMin and <= TempMax && TempCrit is >= TempMin and <= TempMax &&
        TempCritHyst is >= HystMin and <= HystMax && TempCritSoonMargin is >= MarginMin and <= MarginMax &&
        CritExemptMask >= 0 && CritExemptMask <= CritExemptMaskMax &&
        WakeInputMask >= 0 && WakeInputMask <= WakeInputMaskMax && WakeInputMaskBadBits(DeviceType, WakeInputMask) == 0 &&
        MasterRetryInput >= 0 && (VarMapSize == 0 || MasterRetryInput < VarMapSize) &&
        OutputProtection.Count == NumOutputs && OutputProtection.All(o => o.IsValid()) &&
        Tables.Count == NumTables && Tables.All(t => t.IsValid(VarMapSize)) &&
        PwmFreqInputs.Count == NumOutputs && PwmFreqInputs.All(f => f.IsValid() && f.Input >= 0 && (VarMapSize == 0 || f.Input < VarMapSize));

    // Reset-limit wording (docs/feature-parity.md row 29): our reset limit counts every trip, the first one included
    public static string ResetLimitText(int limit) =>
        $"{limit} {(limit == 1 ? "trip" : "trips")} in all (first try + {Math.Max(limit - 1, 0)} {(limit - 1 == 1 ? "retry" : "retries")})";
}
