using System.Text.RegularExpressions;
using domain.Devices;
using domain.Enums;
using domain.Models;

namespace domain.CustomPdm;

// custom-pdm uifix2 (2026-11-23): the /pdm "Output test" for real hardware. ONE output is switched on for a short time
// through live single-param writes (stock MsgCmd::Write: applied at once by the firmware, firmware/core/param_protocol.cpp
// "case MsgCmd::Write" -> WriteParam + ApplyConfig; nothing is burned): output[n].input = var 1 (always true,
// firmware/core/device.cpp InitVarMap, as PdmFaults uses it) and output[n].enabled = true. At the end the board gets the
// EXACT two values it held before (the PC values, which must equal the board: see Refused), in the opposite order.
// A power cycle also brings the burned values back. The timing, Stop, adapter disconnect and app close are in
// application/Services/PdmOutputTestService.cs. Proof: OutputTestTests, OutputTestLiveSimTests.
public record PdmOutputTestSaved(bool Enabled, int Input);

public enum PdmOutputTestState { On, Restoring, Settling, Done }

public static partial class PdmOutputTest
{
    public const double DefaultSeconds = 2, MinSeconds = 0.5, MaxSeconds = 10;

    public static double Seconds(double s) => double.IsNaN(s) ? DefaultSeconds : Math.Clamp(s, MinSeconds, MaxSeconds);

    [GeneratedRegex(@"fuel|pump|\beps\b|steer|starter|\bstart\b|crank", RegexOptions.IgnoreCase)]
    private static partial Regex SafetyName();

    // The safety-related function an output runs (fuel pump, EPS enable, starter), by its preset or its name; null = none.
    // The test of such an output needs a tick in the confirm box (Refused).
    public static string? SafetyFunction(PdmView v, PdmOutputRow row)
    {
        if (PdmPresets.KindOf(v, row) == PdmDeviceKind.FuelPump) return "fuel pump";
        var m = SafetyName().Match(row.Output.Name ?? "");
        if (!m.Success) return null;
        return m.Value.ToLowerInvariant() switch
        {
            "fuel" or "pump" => "fuel pump",
            "eps" or "steer" => "EPS / power steering",
            _ => "starter"
        };
    }

    public const string AdapterOff = "CAN adapter not connected.";
    public const string Running = "A Read All / Write All / Burn is running: the output test waits until it ends.";

    // Why this output must not be tested now (null = it may). inSync: the PC values of the output's board are what the
    // board was last seen to hold (PdmAutoRead.InSync): only then the values put back are the board's own.
    public static string? Refused(PdmView v, PdmOutputRow? row, bool adapterConnected, bool busy, bool inSync,
        Func<FwDevice, bool> isConnected, bool safetyConfirmed)
    {
        if (!adapterConnected) return AdapterOff;
        if (busy) return Running;
        if (v.Blocking.Count > 0) return string.Join(" ", v.Blocking);
        if (row == null) return "Pick an output of the PDM.";
        var label = PdmFaults.OutputLabel(row);
        if (!isConnected(row.Device)) return $"{row.Board} is offline: the board must hear the test.";
        if (row.Output.PrimaryOutput >= 0)
            return $"{label} follows {row.Board} OUT{row.Output.PrimaryOutput + 1} (paired outputs): test OUT{row.Output.PrimaryOutput + 1}, it switches both.";
        if (!inSync)
            return $"The PC holds settings for {row.Board} that are not on the board (or the board was not read or written in this session): " +
                   "Write All or Read All first, so the test can put the board's own values back.";
        if (SafetyFunction(v, row) is { } f && !safetyConfirmed)
            return $"{label} runs the {f}: tick the box to say it is safe to switch it on now.";
        return null;
    }

    private static DeviceCanFrame Write(FwDevice dev, int i, string param, object value, string what)
    {
        var p = dev.Outputs[i].Params.Single(x => x.Name.EndsWith($".{param}"));
        return new DeviceCanFrame
        {
            DeviceBaseId = dev.BaseId,
            SendOnly = true,
            Frame = Common.ParamCodec.ToFrame(MessageCommand.Write, new DeviceParameter
            {
                Index = p.Index, SubIndex = p.SubIndex, GetValue = () => value, ValueType = p.ValueType
            }, dev.BaseId + FwDevice.ConfigTxOffset),
            Name = $"Output test: OUT{i + 1} {what}"
        };
    }

    // trigger first (always true), then enabled: an output that was off never runs its old trigger on the way
    public static IReadOnlyList<DeviceCanFrame> OnFrames(FwDevice dev, int i) =>
        [Write(dev, i, "input", PdmFaults.AlwaysTrueVar, "input = always on"), Write(dev, i, "enabled", true, "enabled")];

    // enabled back first (an output that was disabled is off at once), then its own trigger
    public static IReadOnlyList<DeviceCanFrame> RestoreFrames(FwDevice dev, int i, PdmOutputTestSaved s) =>
        [Write(dev, i, "enabled", s.Enabled, $"enabled = {s.Enabled} (put back)"), Write(dev, i, "input", s.Input, $"input = {s.Input} (put back)")];

    private static string A(double a) => FormattableString.Invariant($"{a:0.0} A");
    private static string S(double s) => FormattableString.Invariant($"{s:0.0} s");

    public static string OnText(string label, double nowA, double peakA, OutState state, double leftS) =>
        $"{label} is ON for the test: {A(nowA)} now, peak {A(peakA)}, state {state}, {S(Math.Max(0, leftS))} left.";

    public static string DoneText(string label, double onS, double lastA, double peakA, string why) =>
        $"{label}: tested {S(onS)} ({why}): {A(lastA)} at the end, peak {A(peakA)}. Its own settings are back on the board; nothing was burned.";
}
