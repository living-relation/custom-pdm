using System.Globalization;
using domain.Devices;
using domain.Devices.Functions;

namespace domain.CustomPdm;

// custom-pdm one-PDM editor, phase 2 (editor2): PWM outputs in plain words, through the conflict engine.
// Stock output PWM (0x1000 + o sub 8-16, firmware functions/pwm.cpp): frequency 1-400 Hz (ECUMaster PMU 4-400 Hz),
// a fixed duty 0-100 %, or a variable duty read from a value (duty % = value / denominator; we use denominator 1, so
// the value IS the duty in %), soft start (ramp from the minimum duty to the target over the ramp time) and a minimum
// duty. Fan curve (PRO_FEATURES T1, docs/feature-parity.md row 14): duty from a 1D lookup table (2-8 points,
// interpolated, held at the ends) of any value of the output's board (CAN value such as ECU coolant temperature,
// analog input mV, board temperature, math, counter). Proven in firmware/sim s3 F6 / F7 ("T1 ... drives the fan duty",
// "fan PWM from coolant temperature", "soft start 1000 ms"). The trigger (when the output is on at all) stays the
// output's trigger: the curve only sets how hard it runs.
// Cost: fixed / value 0; curve 1 lookup table of the output's board (4 per board). Read back from the params.
public enum PdmDutyKind { Fixed, Value, Curve }

public record PdmPwmSpec(bool Enabled, int FreqHz = 100, PdmDutyKind Duty = PdmDutyKind.Fixed, int FixedDuty = 100, int Var = 0,
    IReadOnlyList<(double X, double Y)>? Points = null, bool SoftStart = false, int SoftStartMs = 1000, int MinDuty = 0)
{
    public static readonly PdmPwmSpec Off = new(false);

    public virtual bool Equals(PdmPwmSpec? o) =>
        o is not null && Enabled == o.Enabled && (!Enabled || FreqHz == o.FreqHz && Duty == o.Duty
            && (Duty != PdmDutyKind.Fixed || FixedDuty == o.FixedDuty) && (Duty == PdmDutyKind.Fixed || Var == o.Var)
            && (Duty != PdmDutyKind.Curve || (Points ?? []).SequenceEqual(o.Points ?? []))
            && SoftStart == o.SoftStart && (!SoftStart || SoftStartMs == o.SoftStartMs) && MinDuty == o.MinDuty);

    public override int GetHashCode() => HashCode.Combine(Enabled, FreqHz, Duty, FixedDuty, Var);
}

public record PdmPwmCurve(PdmOutputRow Out, PdmRes Table, LookupTable T);

public static class PdmPwm
{
    public const int MaxFreq = 400, DefaultFreq = 100, MaxSoftMs = 10000;

    private static string Num(double x) => x.ToString("0.###", CultureInfo.InvariantCulture);

    private static PdmBoard BoardOf(PdmView v, PdmOutputRow o) => v.Boards.Single(b => ReferenceEquals(b.Device, o.Device));

    // var index of lookup table n's output on d (null: no tables)
    public static int? TableVar(FwDevice d, int n) =>
        d.VarMap.FirstOrDefault(e => e.Owner == null && e.GetName() == $"Table {n + 1}")?.VariableIndex;

    private static int? TableOfVar(FwDevice d, int var) =>
        d.CustomPdm is { } cp ? Enumerable.Range(0, cp.Tables.Count).Cast<int?>().FirstOrDefault(n => TableVar(d, n!.Value) == var) : null;

    // outputs whose PWM duty is a lookup table that only they read: their duty curve
    public static IReadOnlyList<PdmPwmCurve> Curves(PdmModel m)
    {
        var list = new List<PdmPwmCurve>();
        foreach (var o in m.View.Outputs)
        {
            var d = o.Device;
            var x = o.Output;
            if (!x.PwmEnabled || !x.VariableDutyCycle || x.DutyCycleDenominator != 1 || TableOfVar(d, x.DutyCycleInput) is not { } n) continue;
            var t = d.CustomPdm!.Tables[n];
            if (!t.Enabled || !t.IsUsable) continue;
            var var = x.DutyCycleInput;
            var readers = d.Outputs.Count(oo => oo.PwmEnabled && oo.VariableDutyCycle && oo.DutyCycleInput == var);
            if (readers != 1 || OtherReads(d, var)) continue;
            list.Add(new PdmPwmCurve(o, new PdmRes(o.Board, PdmResKind.Table, n), t));
        }
        return list;
    }

    // something other than an output's PWM duty reads var
    private static bool OtherReads(FwDevice d, int var)
    {
        var duty = d.Outputs.Where(o => o.PwmEnabled && o.VariableDutyCycle && o.DutyCycleInput == var).Select(o => o.DutyCycleInput).ToList();
        var saved = d.Outputs.Select(o => o.VariableDutyCycle).ToList();
        try
        {
            foreach (var o in d.Outputs.Where(o => o.DutyCycleInput == var)) o.VariableDutyCycle = false;
            return PdmEngine.IsRead(d, var);
        }
        finally
        {
            for (var i = 0; i < d.Outputs.Count; i++) d.Outputs[i].VariableDutyCycle = saved[i];
        }
    }

    // the output's PWM settings as a spec (read back from the params)
    public static PdmPwmSpec Of(PdmModel m, PdmOutputRow o)
    {
        var x = o.Output;
        if (!x.PwmEnabled) return PdmPwmSpec.Off;
        var curve = Curves(m).FirstOrDefault(c => c.Out.Number == o.Number);
        var duty = curve != null ? PdmDutyKind.Curve : x.VariableDutyCycle ? PdmDutyKind.Value : PdmDutyKind.Fixed;
        var pts = curve != null ? Enumerable.Range(0, curve.T.Points).Select(i => (curve.T.X[i], curve.T.Y[i])).ToList() : null;
        return new PdmPwmSpec(true, x.Frequency, duty, x.FixedDutyCycle, curve?.T.Input ?? (duty == PdmDutyKind.Value ? x.DutyCycleInput : 0), pts,
            x.SoftStartEnabled, x.SoftStartEnabled ? x.SoftStartRampTime : 1000, x.MinDutyCycle);
    }

    public static string Words(PdmModel m, PdmOutputRow o)
    {
        var s = Of(m, o);
        if (!s.Enabled) return "full on (no PWM)";
        var w = s.Duty switch
        {
            PdmDutyKind.Fixed => $"PWM {s.FreqHz} Hz, {s.FixedDuty} %",
            PdmDutyKind.Value => $"PWM {s.FreqHz} Hz, duty = {PdmTriggers.VarText(m, o.Board, s.Var)} (%)",
            _ => $"PWM {s.FreqHz} Hz, duty from {PdmTriggers.VarText(m, o.Board, s.Var)}: " +
                 string.Join(", ", s.Points!.Select(p => $"{Num(p.X)} -> {Num(p.Y)} %"))
        };
        if (o.Output.VariableDutyCycle && o.Output.DutyCycleDenominator != 1 && s.Duty == PdmDutyKind.Value)
            w += $" / {o.Output.DutyCycleDenominator}";
        if (s.MinDuty > 0) w += $", at least {s.MinDuty} %";
        if (s.SoftStart) w += $", soft start {PdmLinks.DelayText(s.SoftStartMs)}";
        return w;
    }

    // values of the output's board a curve / variable duty can read (not the lookup tables themselves)
    public static IReadOnlyList<PdmChoice> ValueChoices(PdmModel m, string role) =>
        PdmTriggers.ValueChoices(m, role).Where(c => !c.Text.Contains("lookup table")).ToList();

    public static IReadOnlyDictionary<PdmResKind, int> Cost(PdmPwmSpec s) =>
        s is { Enabled: true, Duty: PdmDutyKind.Curve } ? new Dictionary<PdmResKind, int> { [PdmResKind.Table] = 1 } : new Dictionary<PdmResKind, int>();

    public static string? Problem(PdmModel m, PdmOutputRow o, PdmPwmSpec s)
    {
        if (PdmTriggers.IsFanOutput(o)) return $"Output {o.Number} runs the PDM's own fans (1 A): leave it full on.";
        if (o.Output.PrimaryOutput >= 0) return $"Output {o.Number} is paired: it follows {o.Board} OUT{o.Output.PrimaryOutput + 1}.";
        if (!s.Enabled) return null;
        if (s.FreqHz is < 1 or > MaxFreq) return $"The PWM frequency must be 1 to {MaxFreq} Hz (firmware limit; ECUMaster PMU: 4-400 Hz).";
        if (s.FixedDuty is < 0 or > 100 || s.MinDuty is < 0 or > 100) return "Duty values are 0 to 100 %.";
        if (s.SoftStart && s.SoftStartMs is < 1 or > MaxSoftMs) return $"The soft start time must be 1 to {MaxSoftMs} ms.";
        if (s.Duty != PdmDutyKind.Fixed && !ValueChoices(m, o.Board).Any(c => c.Var == s.Var)) return $"Pick a value of {o.Board} for the duty.";
        if (s.Duty == PdmDutyKind.Curve)
        {
            var p = s.Points ?? [];
            if (o.Device.CustomPdm == null) return $"{o.Board} has no lookup tables.";
            if (p.Count is < 2 or > LookupTable.MaxPoints) return $"A curve has 2 to {LookupTable.MaxPoints} points.";
            if (Enumerable.Range(1, p.Count - 1).Any(i => p[i].X <= p[i - 1].X)) return "The curve's values must rise from point to point.";
            if (p.Any(x => x.Y is < 0 or > 100)) return "Curve duties are 0 to 100 %.";
            if (p.Any(x => Math.Abs(x.X) > LookupTable.ValueLimit)) return "Curve values must be within +-1e9.";
        }
        return null;
    }

    private static void ResetTable(LookupTable t)
    {
        (t.Enabled, t.Input, t.Points) = (false, 0, 0);
        for (var i = 0; i < LookupTable.MaxPoints; i++) (t.X[i], t.Y[i]) = (0, 0);
    }

    // null = set on the PC; else why not (nothing changed)
    public static string? Set(PdmView v, int output, PdmPwmSpec s)
    {
        var o = v.Outputs.FirstOrDefault(r => r.Number == output);
        if (o == null) return $"Output {output} is not in this PDM (1-24, its board must be in the project).";
        var m = PdmModel.Build(v);
        if (Problem(m, o, s) is { } bad) return bad;
        var d = o.Device;
        var x = o.Output;
        var restore = PdmSnapshot.Take([d]);
        // the old curve's table goes back to fresh values
        if (Curves(m).FirstOrDefault(c => c.Out.Number == output) is { } old) ResetTable(old.T);
        if (!s.Enabled)
        {
            (x.PwmEnabled, x.VariableDutyCycle, x.DutyCycleInput, x.SoftStartEnabled) = (false, false, 0, false);
            return null;
        }
        (x.PwmEnabled, x.Frequency, x.MinDutyCycle, x.SoftStartEnabled) = (true, s.FreqHz, s.MinDuty, s.SoftStart);
        if (s.SoftStart) x.SoftStartRampTime = s.SoftStartMs;
        switch (s.Duty)
        {
            case PdmDutyKind.Fixed:
                (x.VariableDutyCycle, x.DutyCycleInput, x.FixedDutyCycle) = (false, 0, s.FixedDuty);
                break;
            case PdmDutyKind.Value:
                (x.VariableDutyCycle, x.DutyCycleInput, x.DutyCycleDenominator) = (true, s.Var, 1);
                break;
            default:
                var free = PdmModel.Build(v).FreeOf(o.Board, PdmResKind.Table);
                if (free.Count == 0)
                {
                    restore.Restore();
                    return $"{o.Board} is full: a duty curve needs 1 lookup table; {PdmModel.Build(v).Use(o.Board).Of(PdmResKind.Table).Text}. Nothing changed.";
                }
                var n = free[0];
                var t = d.CustomPdm!.Tables[n];
                ResetTable(t);
                (t.Enabled, t.Input, t.Points) = (true, s.Var, s.Points!.Count);
                for (var i = 0; i < s.Points.Count; i++) (t.X[i], t.Y[i]) = (s.Points[i].X, s.Points[i].Y);
                (x.VariableDutyCycle, x.DutyCycleInput, x.DutyCycleDenominator) = (true, TableVar(d, n)!.Value, 1);
                break;
        }
        return null;
    }
}
