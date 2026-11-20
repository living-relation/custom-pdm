using domain.Devices.Functions;
using domain.Enums;

namespace domain.CustomPdm;

// custom-pdm one-PDM editor, phase 2 (editor2, DECISIONS 2026-11-16 a2a "per-output device presets"): pick what is
// wired to an output and the protection / behaviour values are filled in; every value stays editable and the output
// shows "preset changed: ..." once one differs. Sources and the table: ui/README.md "Device presets".
// Rules:
// - current limit = min(the output's rating, the device's usual steady maximum) (never above the rating; car-loads
//   dummy: the st185 fuse of that load is the upper bound of its steady current)
// - inrush limit = limit x the device's inrush factor, at least the limit, at most 100 A (stock / firmware range)
// - trip time (PRO P1): 50 ms (firmware default, below the ISO 8820-3 blade-fuse 350 % minimum opening time of 80 ms)
//   for lamps / coils / feeds, 100 ms for motors (still below the 150 ms at 200 %), so the PDM opens before the
//   wiring's fuse would
// - retries: stock Count mode, "N trips in all" (reset count limit N = N trips, N - 1 retries; DECISIONS 2026-11-16)
// - soft start (stock PWM soft start at 100 %, 100 Hz) for the radiator / condenser fans only (ECUMaster: soft start
//   for devices with a high start-up current); turned off again by the other presets when it was only for the soft start
// - open-load min current (PRO P2) where a dead load matters and the current is steady: fuel pump, halogen lamp,
//   A/C clutch; off for PWM fans (a low duty reads as low current) and loads that are often idle
// - link-loss behaviour: applied to the output's cross-board link or ECU command when it has one (PdmLinks /
//   PdmEcu SetMode); fuel pump off (ECUMaster: pump default 0 "for safety"), fans on, lamps / modules hold, rest off
// The chosen preset is a PC-side label (project file, CustomPdmSettings.OutputPresets); without one (a fresh PC after
// Read All) the preset whose values all match is shown.
public enum PdmDeviceKind { None, RadiatorFan, CondenserFan, FuelPump, Lamp, LedLamp, Horn, AcClutch, Solenoid, Motor, Heater, Module, Tacho, Other }

public record PdmPreset(PdmDeviceKind Kind, string Name, double MaxSteadyA, double InrushFactor, int InrushMs, int TripMs,
    bool SoftStart, int SoftStartMs, int Trips, int RetryMs, double MinCurrentA, int MinCurrentMs, PdmLinkLoss Loss, string Why);

// the values a preset gives one output (its rating applied)
public record PdmPresetValues(double CurrentLimit, double InrushLimit, int InrushTime, int TripTime, bool SoftStart, int SoftStartMs,
    ResetMode ResetMode, int Trips, int RetryMs, double MinCurrent, int MinCurrentTime, PdmLinkLoss Loss);

public static class PdmPresets
{
    public const double MaxInrushA = 100.0;          // stock InrushCurrentLimit clamp (PdmPage / OutputsGrid)
    public const int SoftStartFreqHz = 100;

    public static readonly IReadOnlyList<PdmPreset> All =
    [
        new(PdmDeviceKind.RadiatorFan, "Radiator fan", 30, 4, 500, 100, true, 1000, 3, 2000, 0, 500, PdmLinkLoss.On,
            "motor: inrush 3-5 x steady for about 0.5 s (HP Academy: 12 A fan, about 50 A inrush); soft start ramps it; on at loss (cooling)"),
        new(PdmDeviceKind.CondenserFan, "Condenser fan", 30, 4, 500, 100, true, 1000, 3, 2000, 0, 500, PdmLinkLoss.On,
            "as the radiator fan"),
        new(PdmDeviceKind.FuelPump, "Fuel pump", 25, 4, 500, 100, false, 1000, 3, 1000, 1.0, 500, PdmLinkLoss.Off,
            "motor (3-5 x, HP Academy); st185 pump up to 25 A; open-load 1 A flags a dead pump; off at loss (ECUMaster: pump default 0 for safety)"),
        new(PdmDeviceKind.Lamp, "Lamp / headlight (halogen)", 15, 10, 100, 50, false, 1000, 5, 1000, 0.5, 500, PdmLinkLoss.Hold,
            "cold filament: 13-15 x for a few ms (Infineon PROFET+ lamp note: 21 W = 25.9 A peak at 1.9 A, tau 4.6 ms; TI SLVAF91: 35-65 W up to 74 A); open-load 0.5 A = bulb out; holds at loss"),
        new(PdmDeviceKind.LedLamp, "LED lamp", 5, 3, 100, 50, false, 1000, 5, 1000, 0, 500, PdmLinkLoss.Hold,
            "LED driver input capacitor (HP Academy: capacitive inrush, small); current too low for a reliable open-load flag on board A; holds at loss"),
        new(PdmDeviceKind.Horn, "Horn", 15, 3, 200, 50, false, 1000, 3, 1000, 0, 500, PdmLinkLoss.Off,
            "electromechanical (HP Academy electromotive, 3-5 x); st185 horn fuse 15 A; off at loss"),
        new(PdmDeviceKind.AcClutch, "A/C clutch", 10, 2, 200, 50, false, 1000, 3, 1000, 1.0, 500, PdmLinkLoss.Off,
            "coil: current rises with L / R, no inrush above steady (2 x margin); st185 ACC fuse 10 A; open-load 1 A; off at loss"),
        new(PdmDeviceKind.Solenoid, "Solenoid / valve", 5, 2, 100, 50, false, 1000, 3, 1000, 0, 500, PdmLinkLoss.Off,
            "coil (as the clutch); off at loss"),
        new(PdmDeviceKind.Motor, "Motor (wiper / pop-up)", 15, 4, 500, 100, false, 1000, 3, 2000, 0, 500, PdmLinkLoss.Off,
            "motor (3-5 x, HP Academy); st185 wiper run under 15 A; no soft start (park timing); off at loss"),
        new(PdmDeviceKind.Heater, "Heater / resistive", double.MaxValue, 1.5, 500, 100, false, 1000, 3, 1000, 0, 500, PdmLinkLoss.Off,
            "resistive: I = V / R (HP Academy), cold element a little higher; off at loss"),
        new(PdmDeviceKind.Module, "ECU / module feed", 5, 2, 100, 50, false, 1000, 5, 1000, 0, 500, PdmLinkLoss.Hold,
            "electronics: small inrush (HP Academy); st185 module fuses 5 A; holds at loss"),
        new(PdmDeviceKind.Tacho, "Tachometer output", 1, 2, 100, 50, false, 1000, 3, 1000, 0, 500, PdmLinkLoss.Off,
            "signal to a gauge, about 1 A: the gauge needs a pull-down; a 0-5 V input needs a 4.7 k series resistor + 5.1 V zener; " +
            "set the frequency from engine RPM in PWM (pulses per rev = cylinders / 2), 50 % duty"),
        new(PdmDeviceKind.Other, "Other", double.MaxValue, 0, 1000, 50, false, 1000, 3, 1000, 0, 500, PdmLinkLoss.Off,
            "the stock values: limit = rating, inrush 50 A for 1 s (DECISIONS o1), 3 trips")
    ];

    public static PdmPreset Of(PdmDeviceKind k) => All.Single(p => p.Kind == k);

    public static PdmPresetValues Values(PdmPreset p, double ratingA)
    {
        var limit = Math.Round(Math.Min(ratingA, p.MaxSteadyA), 2);
        var inrush = p.Kind == PdmDeviceKind.Other
            ? Math.Max(limit, 50.0)
            : Math.Min(MaxInrushA, Math.Max(limit, Math.Round(limit * p.InrushFactor, 1)));
        return new PdmPresetValues(limit, inrush, p.InrushMs, p.TripMs, p.SoftStart, p.SoftStartMs, ResetMode.Count, p.Trips, p.RetryMs,
            p.MinCurrentA, p.MinCurrentMs, p.Loss);
    }

    public static string TripsText(int trips, int retryMs) => trips <= 1
        ? "1 trip in all (no retry)"
        : $"{trips} trips in all ({trips - 1} retr{(trips - 1 == 1 ? "y" : "ies")}, {PdmLinks.DelayText(retryMs)} apart)";

    private static OutputProtection? Pro(PdmOutputRow o) =>
        o.Device.CustomPdm is { } cp && o.BoardOutput - 1 < cp.OutputProtection.Count ? cp.OutputProtection[o.BoardOutput - 1] : null;

    // the output's loss behaviour, when it has one (a cross-board link or an ECU command)
    private static PdmLinkLoss? Loss(PdmView v, PdmOutputRow o) =>
        PdmLinks.LinkOf(v, o) is { CrossBoard: true, Loss: { } l } ? l : PdmEcu.Of(v, o)?.Loss;

    // what differs from the preset now (empty = the preset's values)
    public static IReadOnlyList<string> Changed(PdmView v, PdmOutputRow o, PdmDeviceKind k)
    {
        var p = Of(k);
        var want = Values(p, o.RatingA);
        var x = o.Output;
        var c = new List<string>();
        if (Math.Abs(x.CurrentLimit - want.CurrentLimit) > 0.005) c.Add("current limit");
        if (Math.Abs(x.InrushCurrentLimit - want.InrushLimit) > 0.005) c.Add("inrush limit");
        if (x.InrushTime != want.InrushTime) c.Add("inrush time");
        if (x.ResetMode != want.ResetMode || x.ResetCountLimit != want.Trips) c.Add("trips");
        if (x.ResetTime != want.RetryMs) c.Add("retry time");
        if (x.SoftStartEnabled != want.SoftStart || want.SoftStart && (!x.PwmEnabled || x.SoftStartRampTime != want.SoftStartMs)) c.Add("soft start");
        if (Pro(o) is { } pr)
        {
            if (pr.TripTime != want.TripTime) c.Add("trip time");
            if (Math.Abs(pr.MinCurrent - want.MinCurrent) > 0.005 || want.MinCurrent > 0 && pr.MinCurrentTime != want.MinCurrentTime) c.Add("open-load current");
        }
        if (Loss(v, o) is { } l && l != want.Loss) c.Add("link loss");
        return c;
    }

    // the label kept in the project file, else the preset whose values all match
    public static PdmDeviceKind KindOf(PdmView v, PdmOutputRow o)
    {
        if (Label(o) is { } k) return k;
        return All.FirstOrDefault(p => p.Kind != PdmDeviceKind.Other && Changed(v, o, p.Kind).Count == 0)?.Kind ?? PdmDeviceKind.None;
    }

    private static PdmDeviceKind? Label(PdmOutputRow o)
    {
        var list = o.Device.CustomPdm?.OutputPresets;
        var i = o.BoardOutput - 1;
        return list != null && i < list.Count && Enum.TryParse<PdmDeviceKind>(list[i], out var k) && k != PdmDeviceKind.None ? k : null;
    }

    private static void SetLabel(PdmOutputRow o, PdmDeviceKind k)
    {
        if (o.Device.CustomPdm is not { } cp) return;
        while (cp.OutputPresets.Count < o.Device.Outputs.Count) cp.OutputPresets.Add("");
        cp.OutputPresets[o.BoardOutput - 1] = k == PdmDeviceKind.None ? "" : k.ToString();
    }

    // Fill the output with the preset (PC only; Write All sends it). Returns null, or why not (nothing changed).
    // notes: what else it did / could not do (e.g. "no link: link-loss mode used when one is made").
    public static string? Apply(PdmView v, int output, PdmDeviceKind k, List<string>? notes = null)
    {
        var o = v.Outputs.FirstOrDefault(r => r.Number == output);
        if (o == null) return $"Output {output} is not in this PDM (1-24, its board must be in the project).";
        if (PdmTriggers.IsFanOutput(o)) return $"Output {o.Number} runs the PDM's own fans: its 1 A / 2 A limits are fixed by the factory settings.";
        if (o.Output.PrimaryOutput >= 0) return $"Output {o.Number} is paired: set its primary ({o.Board} OUT{o.Output.PrimaryOutput + 1}).";
        if (k == PdmDeviceKind.None)
        {
            SetLabel(o, k);
            return null;
        }
        var w = Values(Of(k), o.RatingA);
        var x = o.Output;
        var restore = PdmSnapshot.Take([o.Device]);
        (x.CurrentLimit, x.InrushCurrentLimit, x.InrushTime) = (w.CurrentLimit, w.InrushLimit, w.InrushTime);
        (x.ResetMode, x.ResetCountLimit, x.ResetTime) = (w.ResetMode, w.Trips, w.RetryMs);
        if (w.SoftStart)
        {
            if (!x.PwmEnabled) (x.PwmEnabled, x.VariableDutyCycle, x.FixedDutyCycle, x.Frequency) = (true, false, 100, SoftStartFreqHz);
            (x.SoftStartEnabled, x.SoftStartRampTime) = (true, w.SoftStartMs);
        }
        else if (x.SoftStartEnabled)
        {
            x.SoftStartEnabled = false;
            // PWM that was only there for the soft start (full duty, no curve): off again
            if (x is { PwmEnabled: true, VariableDutyCycle: false, FixedDutyCycle: 100 }) x.PwmEnabled = false;
        }
        if (Pro(o) is { } pr) (pr.TripTime, pr.MinCurrent, pr.MinCurrentTime) = (w.TripTime, w.MinCurrent, w.MinCurrentTime);
        if (PdmLinks.LinkOf(v, o) is { CrossBoard: true, Loss: { } l } link && l != w.Loss)
        {
            if (PdmLinks.SetMode(v, output, w.Loss) is { } why)
            {
                restore.Restore();
                return $"Link loss '{w.Loss}' could not be set: {why}";
            }
            notes?.Add($"link from IN{link.In.Number}: {PdmLinks.LinkOf(v, o)!.LossText}");
        }
        else if (PdmEcu.Of(v, o) is { } e && e.Loss != w.Loss)
        {
            if (PdmEcu.Set(v, output, e.Id, e.Byte, w.Loss, e.DelayMs, 0, overwrite: true) is { } why)
            {
                restore.Restore();
                return $"ECU loss '{w.Loss}' could not be set: {why}";
            }
            notes?.Add($"ECU command: {PdmEcu.Of(v, o)!.LossText}");
        }
        else if (Loss(v, o) == null) notes?.Add($"no link or ECU command yet: '{w.Loss.ToString().ToLowerInvariant()}' at loss is used when one is made");
        SetLabel(o, k);
        return null;
    }

    // the loss mode a new link / ECU command of this output should get (its preset's), or the default
    public static PdmLinkLoss DefaultLoss(PdmView v, PdmOutputRow o) =>
        KindOf(v, o) is var k && k != PdmDeviceKind.None ? Of(k).Loss : PdmLinks.DefaultLoss;
}
