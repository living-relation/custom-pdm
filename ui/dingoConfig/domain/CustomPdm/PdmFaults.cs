using System.Text.RegularExpressions;
using domain.Devices;
using domain.Devices.Functions;
using domain.Enums;
using domain.Models;

namespace domain.CustomPdm;

// custom-pdm uipolish (2026-11-21): faults in plain words.
// 1. Lines: what is wrong on the PDM right now, for the top of /pdm, from the live values the boards send
//    (output state + trip count, the three thermal flags, board temperature). Before: only the small FAULT chip in the
//    output's row and the stock log line "B ID: 1408, Src: OverCurrent 2 39 0".
// 2. Reset: the firmware has no "clear faults" command. What it has (read in firmware/core/device.cpp and
//    functions/profet.h, PRO_FEATURES P3): the rising edge of the var picked by param 0x7F00 sub 6 (master retry
//    input) takes every output out of Overcurrent / Fault; a latched Fault has no other way out but a power cycle
//    (functions/profet.cpp "Fault requires power cycle"). The button makes that edge with three live single-param
//    writes (stock MsgCmd::Write, applied at once, nothing burned): sub 6 = 0 (always false), = 1 (always true: the
//    edge), = the value it had. Proven on the sim boards in FaultLiveSimTests.
// 3. LogWords: words added to the stock log lines of our boards (firmware/comms/infomsg.cpp: what each line's three
//    numbers are).
public record PdmFaultLine(string Text, bool Reset);   // Reset: the Reset faults button clears it

public static partial class PdmFaults
{
    public const int AlwaysFalseVar = 0, AlwaysTrueVar = 1;   // firmware/core/device.cpp InitVarMap: the first two vars
    public const string ResetButton = "Reset faults";

    [GeneratedRegex(@"^output\d+$", RegexOptions.IgnoreCase)]
    private static partial Regex StockOutputName();

    // "Fuel pump (B OUT5)"; an output that still has its stock name: "Output 21 (B OUT5)"
    public static string OutputLabel(PdmOutputRow row) =>
        $"{Named(row.Output.Name, $"Output {row.Number}")} ({row.Board} OUT{row.BoardOutput})";

    private static string Named(string? name, string fallback) =>
        string.IsNullOrWhiteSpace(name) || StockOutputName().IsMatch(name.Trim()) ? fallback : name.Trim();

    private static string Trips(int n) => n == 1 ? "1 trip" : $"{n} trips";

    // The state of one output in words (null = nothing wrong)
    public static string? OutputFault(Output o) => o.State switch
    {
        // latched: profet.cpp goes to Fault at once with reset mode None, and at the reset limit with mode Count
        OutState.Fault => $"overcurrent, {Trips(Math.Max(o.ResetCount, 1))}, off until reset",
        OutState.Overcurrent => o.ResetMode == ResetMode.Count
            ? $"overcurrent, trip {Math.Max(o.ResetCount, 1)} of {o.ResetCountLimit}, off for {Seconds(o.ResetTime)} then it tries again"
            : $"overcurrent, {Trips(Math.Max(o.ResetCount, 1))}, off for {Seconds(o.ResetTime)} then it tries again",
        _ => null
    };

    private static string Seconds(int ms) => FormattableString.Invariant($"{ms / 1000.0:0.##} s");
    private static string Temp(double c) => FormattableString.Invariant($"{c:0} C");

    public static IReadOnlyList<PdmFaultLine> Lines(PdmView view, Func<FwDevice, bool>? isConnected = null)
    {
        isConnected ??= d => d.Connected;
        var lines = new List<PdmFaultLine>();
        foreach (var b in view.Boards.Where(b => isConnected(b.Device)))
        {
            var c = b.Device.CustomPdm;
            if (c == null) continue;
            var limits = FormattableString.Invariant($"sensor {b.Device.BoardTempC:0} C, critical at {c.TempCrit} C");
            if (c.Critical)
                lines.Add(new($"Board {b.Role}: over temperature ({limits}): its outputs are off until it has cooled by {c.TempCritHyst} C", false));
            else if (c.CriticalSoon)
                lines.Add(new($"Board {b.Role}: close to its critical temperature ({limits}): its outputs go off there", false));
            else if (c.OverWarn)
                lines.Add(new($"Board {b.Role}: hot ({Temp(b.Device.BoardTempC)}, warning from {c.TempWarn} C)", false));
        }

        foreach (var row in view.Outputs.Where(r => isConnected(r.Device)))
            if (OutputFault(row.Output) is { } what)
                lines.Add(new($"{OutputLabel(row)}: {what}", true));
        return lines;
    }

    // ---------------- Reset faults ----------------

    private static DeviceCanFrame RetryWrite(FwDevice dev, int var) => new()
    {
        DeviceBaseId = dev.BaseId,
        SendOnly = true,
        Frame = Common.ParamCodec.ToFrame(MessageCommand.Write, new DeviceParameter
        {
            Index = CustomPdmSettings.BaseIndex, SubIndex = CustomPdmSettings.MasterRetrySub,
            GetValue = () => var, ValueType = typeof(int)
        }, dev.BaseId + FwDevice.ConfigTxOffset),
        Name = $"Reset faults: master retry input = {var}"
    };

    // The three writes of one board, in order. The caller waits ResetStepGap after each, so the board's logic loop
    // sees every value (FaultLiveSimTests runs it with 10 / 50 / 200 ms between them).
    public static IReadOnlyList<DeviceCanFrame> ResetFrames(FwDevice dev, int keep) =>
        [RetryWrite(dev, AlwaysFalseVar), RetryWrite(dev, AlwaysTrueVar), RetryWrite(dev, keep)];

    public static readonly TimeSpan ResetStepGap = TimeSpan.FromMilliseconds(50);

    // ---------------- stock log lines in words ----------------

    // null = no words for this line (it stays as it is). Numbers: firmware/comms/infomsg.cpp.
    public static string? LogWords(FwDevice dev, MessageType type, MessageSrc src, int d0, int d1, int d2)
    {
        string Out(int i) => i >= 0 && i < dev.Outputs.Count
            ? $"{Named(dev.Outputs[i].Name, $"output {i + 1}")} (OUT{i + 1})"
            : $"output {i + 1}";
        var t0 = FormattableString.Invariant($"{d0 / 10.0:0.#} C");
        return (type, src) switch
        {
            (MessageType.Warning, MessageSrc.OverCurrent) => $"{Out(d0)}: overcurrent trip at {d1} A (it tries again by its reset setting)",
            (MessageType.Error, MessageSrc.OverCurrent) => $"{Out(d0)}: overcurrent fault at {d1} A, off until reset (Reset faults on the PDM page, the master retry input, or a power cycle)",
            (MessageType.Error, MessageSrc.StateOvertemp) => $"over temperature: board at {t0}",
            (MessageType.Error, MessageSrc.OverTemp) => FormattableString.Invariant($"critical temperature: board at {t0}, limit {d1 / 10.0:0.#} C, outputs off (but the ones kept on at critical)"),
            (MessageType.Warning, MessageSrc.OverTemp) => FormattableString.Invariant($"close to critical temperature: board at {t0}, critical at {d1 / 10.0:0.#} C (warned {d2} C before)"),
            (MessageType.Error, MessageSrc.TempSensor) => $"board temperature sensor not answering ({d0} failed reads in a row, {d1} in all)",
            (MessageType.Error, MessageSrc.StateError) => "the board stopped in its error state",
            (MessageType.Warning, MessageSrc.BatteryVoltage) => FormattableString.Invariant($"battery voltage {d0 / 10.0:0.0} V is {(d0 > 130 ? "above 16 V" : "below 10 V")}"),
            (MessageType.Info, MessageSrc.StateRun) => "running",
            (MessageType.Info, MessageSrc.StateSleep) => "going to sleep",
            _ => null
        };
    }
}
