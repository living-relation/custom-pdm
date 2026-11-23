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
//   PdmEcu SetMode); fuel pump off (ECUMaster: pump default 0 "for safety"), fans off, lamps / modules hold, rest off;
//   an output the ECU commands (PdmEcu) is OFF at ECU loss whatever its preset (EcuLoss; Dan 2026-11-23: the ECU keeps
//   control and does its own shutdown / after-run, and a key off stops the ECU: it must not read as a fault)
// - board B motor PWM (fwsafety, ADR-2026-11-20-presim-findings item 2, docs/system-verification.md 3): in the PWM off
//   time a motor's current freewheels in the output's BYG23M (D13 .. D28, Vishay doc 88962: IF(AV) 1.5 A). The average
//   diode current at the worst duty, I x tau x f x (1 - e^(-toff / tau)) with tau = L x I / 13.5 V (back-EMF ignored, as
//   tools/verify_switching.py), must stay <= 1.5 A: so the PWM frequency of a motor preset on board B is held at or
//   below MaxPwmHz (radiator / condenser fan at their 30 A limit, 1 mH: 22 Hz; at the car-loads 25 A it would be 32 Hz),
//   the fan soft start included. L is ASSUMED (tools/presim_parts.py CAR_LOADS upper end; bench: measure it) until the
//   hardware job changes the diodes; board A has no freewheel diodes (the PROFET clamps each turn-off).
// - a primary output with a follower (pair) uses the pair rating, 52 A on B OUT1-4 (PdmView.PairRating)
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
    public const PdmLinkLoss EcuLoss = PdmLinkLoss.Off;   // configfix: every ECU-commanded output, any preset
    public const double FreewheelIfAvA = 1.5, MotorSupplyV = 13.5;   // BYG23M IF(AV) (Vishay doc 88962); verify_switching.py

    // ASSUMED motor inductance per motor preset (tools/presim_parts.py CAR_LOADS, upper end of the range)
    public static double? MotorInductanceH(PdmDeviceKind k) => k switch
    {
        PdmDeviceKind.RadiatorFan or PdmDeviceKind.CondenserFan => 1.0e-3,
        PdmDeviceKind.FuelPump => 0.5e-3,
        PdmDeviceKind.Motor => 1.5e-3,
        _ => null
    };

    // average freewheel-diode current at the worst duty (5 % steps, as verify_switching.py)
    public static double FreewheelAvgA(double amps, double inductanceH, double hz)
    {
        if (amps <= 0 || inductanceH <= 0) return 0;
        var tau = inductanceH * amps / MotorSupplyV;
        return Enumerable.Range(1, 19).Max(d => amps * tau * hz * (1 - Math.Exp(-((1 - d / 20.0) / hz) / tau)));
    }

    // highest PWM frequency (Hz) the output allows with this preset: board B motor presets keep the freewheel diode within
    // its rating (0 = none, even the lowest PWM frequency overloads it); everything else the stock maximum
    public static int MaxPwmHz(PdmOutputRow o, PdmDeviceKind k)
    {
        if (o.Board != "B" || MotorInductanceH(k) is not { } l) return PdmPwm.MaxFreq;
        var amps = Values(Of(k), o.RatingA).CurrentLimit * (PdmView.IsPairPrimary(o.Device, o.BoardOutput - 1) ? PdmView.PairShareMax : 1.0);
        for (var f = PdmPwm.MaxFreq; f >= PdmPwm.MinFreq; f--)
            if (FreewheelAvgA(amps, l, f) <= FreewheelIfAvA) return f;
        return 0;
    }

    public static readonly IReadOnlyList<PdmPreset> All =
    [
        new(PdmDeviceKind.RadiatorFan, "Radiator fan", 30, 4, 500, 100, true, 1000, 3, 2000, 0, 500, PdmLinkLoss.Off,
            "motor: inrush 3-5 x steady for about 0.5 s (HP Academy: 12 A fan, about 50 A inrush); soft start ramps it; off at loss (the ECU keeps control and runs its own after-run)"),
        new(PdmDeviceKind.CondenserFan, "Condenser fan", 30, 4, 500, 100, true, 1000, 3, 2000, 0, 500, PdmLinkLoss.Off,
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
        return new PdmPresetValues(limit, InrushFor(p, limit), p.InrushMs, p.TripMs, p.SoftStart, p.SoftStartMs, ResetMode.Count, p.Trips, p.RetryMs,
            p.MinCurrentA, p.MinCurrentMs, p.Loss);
    }

    // the preset's inrush rule for a current limit: limit x the inrush factor, at least the limit, at most 100 A
    public static double InrushFor(PdmPreset p, double limit) => p.Kind == PdmDeviceKind.Other
        ? Math.Max(limit, 50.0)
        : Math.Min(MaxInrushA, Math.Max(limit, Math.Round(limit * p.InrushFactor, 1)));

    // configfix (s5 drive cycle, 2026-11-23: the starter's CAN-Lambda had its Module limit raised 5 -> 10 A with the
    // inrush left at 10 A, and tripped at every key-on): when the current limit of an output with a preset is edited
    // and its inrush still follows the preset rule for the old limit, the inrush follows the rule for the new limit.
    // An inrush set by hand (not the rule) is kept. Returns what it did, or null.
    public static string? LimitEdited(PdmView v, PdmOutputRow o, double oldLimit)
    {
        var k = KindOf(v, o);
        if (k is PdmDeviceKind.None or PdmDeviceKind.Other) return null;
        var p = Of(k);
        var x = o.Output;
        if (Math.Abs(x.InrushCurrentLimit - InrushFor(p, oldLimit)) > 0.05) return null;
        var want = InrushFor(p, x.CurrentLimit);
        if (Math.Abs(want - x.InrushCurrentLimit) <= 0.005) return null;
        x.InrushCurrentLimit = want;
        return $"inrush limit {want:0.##} A ({p.Name} preset: {p.InrushFactor:0.##} x the limit)";
    }

    // ---------------- switch limits the presets do not hold (tools/verify_switching.py, WARN rows) ----------------

    // PROFET values (tools/presim_parts.py PROFET: Infineon data sheets): DC rating, RDS(ON) at 150 C, slowest slew rate,
    // IL(OVL0) min at TJ 150 C
    public record PdmSwitch(string Model, double InomA, double Rds150, double DvdtMin, double Ovl0Min150A);

    public static readonly PdmSwitch Bts7008 = new("BTS7008-2EPA", 7.5, 16e-3, 0.3e6, 65);     // Data Sheet Rev 1.20
    public static readonly PdmSwitch Bts7004 = new("BTS7004-1EPP", 15.0, 8e-3, 0.16e6, 88);    // Data Sheet Rev 1.03
    public static readonly PdmSwitch Bts70012 = new("BTS70012-1ESP", 31.3, 2.47e-3, 0.16e6, 146); // Data Sheet Rev 1.21

    public static PdmSwitch SwitchOf(PdmOutputRow o) => o.Board == "B" ? (o.BoardOutput <= 4 ? Bts70012 : Bts7004) : Bts7008;

    public const double SwitchingV = 14.4, HalogenColdFactor = 14.0, HalogenV = 13.2;   // verify_switching.py VBAT, presets()

    // tools/verify_switching.py pwm_loss: the largest current whose PWM conduction + switching loss stays within the DC
    // loss at the rating: I^2 R150 + 2 x E_edge x f <= Inom^2 R150, E_edge = V I t / 6 (resistive / lamp) or / 2 (motor
    // with a freewheel path: hard switching), t = V / slowest dV/dt.
    public static double PwmMaxA(PdmSwitch s, int hz, bool motor)
    {
        var b = hz * SwitchingV * SwitchingV / ((motor ? 1.0 : 3.0) * s.DvdtMin);
        return (-b + Math.Sqrt(b * b + 4 * s.Rds150 * s.InomA * s.InomA * s.Rds150)) / (2 * s.Rds150);
    }

    private static bool IsMotor(PdmDeviceKind k) => k is PdmDeviceKind.RadiatorFan or PdmDeviceKind.CondenserFan or PdmDeviceKind.FuelPump or PdmDeviceKind.Motor;

    // tools/verify_switching.py presets(): a halogen lamp's cold filament draws 14 x its hot current; above the PROFET's
    // IL(OVL0) min at 150 C the switch turns itself off and restarts (5 restarts, P_8.6.1.x) at every switch-on
    public static double HalogenMaxW(PdmSwitch s) => s.Ovl0Min150A / HalogenColdFactor * HalogenV;

    // Warnings for an output that the preset values cannot hold (shown under the output on /pdm); empty = none
    public static IReadOnlyList<string> Warnings(PdmView v, PdmOutputRow o)
    {
        var list = new List<string>();
        var x = o.Output;
        var s = SwitchOf(o);
        var k = KindOf(v, o);
        // PWM for real (not only the soft start's 1 s ramp at full duty)
        var softOnly = x.SoftStartEnabled && !x.VariableDutyCycle && x.FixedDutyCycle == 100;
        if (x is { Enabled: true, PwmEnabled: true } && !softOnly && x.Frequency > 0)
        {
            var max = PwmMaxA(s, x.Frequency, IsMotor(k));
            if (x.CurrentLimit > max + 0.05)
                list.Add($"PWM at {x.Frequency} Hz: above {max:0.0} A the {s.Model} runs hotter than at its {s.InomA:0.#} A DC rating " +
                         $"(switching loss, tools/verify_switching.py PWM loss); keep the load under {max:0.0} A or lower the frequency.");
        }
        if (k == PdmDeviceKind.Lamp && x.CurrentLimit * HalogenV > HalogenMaxW(s) + 0.5)
            list.Add($"Halogen lamp: above {HalogenMaxW(s):0} W the cold filament (14 x) passes the {s.Model} overload limit " +
                     $"({s.Ovl0Min150A:0} A at 150 C): it switches itself off and restarts at every switch-on (tools/verify_switching.py lamp inrush); " +
                     "use an LED lamp or a bigger output.");
        return list;
    }

    public static string TripsText(int trips, int retryMs) => trips <= 1
        ? "1 trip in all (no retry)"
        : $"{trips} trips in all ({trips - 1} retr{(trips - 1 == 1 ? "y" : "ies")}, {PdmLinks.DelayText(retryMs)} apart)";

    private static OutputProtection? Pro(PdmOutputRow o) =>
        o.Device.CustomPdm is { } cp && o.BoardOutput - 1 < cp.OutputProtection.Count ? cp.OutputProtection[o.BoardOutput - 1] : null;

    // the loss mode an output should have: the preset's on a cross-board link, EcuLoss on an ECU command
    private static PdmLinkLoss WantLoss(PdmView v, PdmOutputRow o, PdmLinkLoss preset) =>
        PdmLinks.LinkOf(v, o) is { CrossBoard: true } ? preset : PdmEcu.Of(v, o) != null ? EcuLoss : preset;

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
        var maxHz = MaxPwmHz(o, k);
        if (x.SoftStartEnabled != (want.SoftStart && maxHz > 0) || want.SoftStart && maxHz > 0 && (!x.PwmEnabled || x.SoftStartRampTime != want.SoftStartMs)) c.Add("soft start");
        if (x.PwmEnabled && x.Frequency > maxHz) c.Add("PWM frequency");
        if (Pro(o) is { } pr)
        {
            if (pr.TripTime != want.TripTime) c.Add("trip time");
            if (Math.Abs(pr.MinCurrent - want.MinCurrent) > 0.005 || want.MinCurrent > 0 && pr.MinCurrentTime != want.MinCurrentTime) c.Add("open-load current");
        }
        if (Loss(v, o) is { } l && l != WantLoss(v, o, want.Loss)) c.Add("link loss");
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
        var maxHz = MaxPwmHz(o, k);
        if (w.SoftStart && maxHz > 0)
        {
            if (!x.PwmEnabled) (x.PwmEnabled, x.VariableDutyCycle, x.FixedDutyCycle, x.Frequency) = (true, false, 100, Math.Min(SoftStartFreqHz, maxHz));
            (x.SoftStartEnabled, x.SoftStartRampTime) = (true, w.SoftStartMs);
        }
        else if (x.SoftStartEnabled)
        {
            x.SoftStartEnabled = false;
            // PWM that was only there for the soft start (full duty, no curve): off again
            if (x is { PwmEnabled: true, VariableDutyCycle: false, FixedDutyCycle: 100 }) x.PwmEnabled = false;
        }
        if (w.SoftStart && maxHz == 0) notes?.Add($"no soft start: any PWM overloads the {o.Board} OUT{o.BoardOutput} freewheel diode at this current");
        if (x.PwmEnabled && x.Frequency > maxHz && maxHz > 0)
        {
            notes?.Add($"PWM frequency {x.Frequency} -> {maxHz} Hz: the board B freewheel diode (BYG23M, {FreewheelIfAvA} A) limits motor PWM");
            x.Frequency = maxHz;
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
        else if (PdmEcu.Of(v, o) is { } e && e.Loss != EcuLoss)
        {
            if (PdmEcu.Set(v, output, e.Id, e.Byte, EcuLoss, e.DelayMs, 0, overwrite: true) is { } why)
            {
                restore.Restore();
                return $"ECU loss '{EcuLoss}' could not be set: {why}";
            }
            notes?.Add($"ECU command: {PdmEcu.Of(v, o)!.LossText}");
        }
        else if (Loss(v, o) == null) notes?.Add($"no link or ECU command yet: '{w.Loss.ToString().ToLowerInvariant()}' at loss is used when one is made");
        SetLabel(o, k);
        return null;
    }

    // the loss mode a new link / ECU command of this output should get (its preset's), or the default
    public static PdmLinkLoss DefaultLoss(PdmView v, PdmOutputRow o, bool ecu = false) =>
        ecu ? EcuLoss : KindOf(v, o) is var k && k != PdmDeviceKind.None ? Of(k).Loss : PdmLinks.DefaultLoss;
}
