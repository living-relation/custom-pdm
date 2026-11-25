using domain.CustomPdm;
using domain.Devices.Functions;
using domain.Enums;

namespace CustomPdm.Tests;

// carsim (Dan 2026-11-23, "pretend I WANT a PDM now"): the ST185 car config (ui/examples/st185-car.dummy.json, a DUMMY /
// demo config), built from the car map below with the /pdm domain code on a New PDM. The map is a DUMMY COPY of
// st185-link-ecu-config @ a0490839 (sot/fuse-relay-map.csv, sot/channels.csv, docs/harness/circuit-plan.md,
// CAN-BUS-ID-ALLOCATION-TABLE.md, CAN-BUS-MASTER-DESIGN.md; read only) and of the 1992 EWD power source / headlight pages
// (st185-celica-repair-manual @ 66b0f72, read only), written out in docs/st185-car-config.dummy.md.
// Every load of the POWER / LOGIC / trunk boxes and of the kept OEM boxes that fits the 23 car outputs is on the PDM,
// on an output rated for its st185 fuse (fusesize 2026-11-25); what fits no output stays on its OEM switch (OffThePdm).
// Dan 2026-11-23 07:44: what the ECU controls and powers stays OFF the PDM entirely (fuel pump, EPS pump, radiator and
// condenser fans, heater, A/C, ETB, throttle pedal, boost solenoid, injectors, coils): their relays and fuses are
// unchanged, and the PDM needs no CAN frame from the ECU. The EFI main relay K-EFI stays a relay (the ECU's own power
// hold, ETB after-run); what its Bus 2 fed and the PDM now feeds (DRLs, CSB3, cluster) follows IN5 = the K-EFI
// output, never the ignition or a PDM timer, and PDM auto sleep waits for IN5, the tail switch and the hazard switch
// to be off.
// Regenerate the file: $env:CUSTOMPDM_WRITE_CAR_CONFIG='1'; dotnet test --filter St185CarTests
public static class St185Car
{
    public const string Source = "st185-link-ecu-config @ a0490839";
    // battery load shed (docs/st185-car-config.dummy.md "Low battery"): AGM, off after 30 s at <= 11.8 V, back at >= 12.8 V
    public const double ShedOnV = 11.8, ShedOffV = 12.8;
    public const int ShedDelayMs = 30000;
    public const int EfiMain = 5, Tail = 7, Hazard = 9, Ignition = 16;

    // st185 fuse = the fuse that protects that circuit's wiring today (sot/fuse-relay-map.csv, 1992 EWD power source)
    public record Load(int Number, string Name, PdmDeviceKind Kind, double St185FuseA, string Replaces, double? LimitA = null, double? InrushA = null);

    public record Sw(int Number, string Name, bool GroundActive, string Wire, bool Latched = false, bool Wake = false);

    // fusesize (2026-11-25): every output's rating (a paired primary: PdmView.PairRating) >= the circuit's st185 fuse
    // (Dan's fuse boxes are sized from each device's peak / inrush current; docs/pdm-2a-plan.md). 15 A and 30 A circuits
    // sit on board B (OUT1-4 31 A studs, OUT5-8 15 A); the 10 A circuits on board A pairs (12.5 A, one dual chip each).
    public static readonly Load[] Loads =
    [
        new(1, "CAN-Lambda", PdmDeviceKind.Heater, 10, "K-ON relay (LOGIC M7) + LAM 10 A", LimitA: 10, InrushA: 15),
        new(3, "DRLs", PdmDeviceKind.LedLamp, 7.5, "K-DRL relay (LOGIC M8) + RLY-DRL (B5) + DRL 7.5 A"),
        new(7, "CSB3 switchboard", PdmDeviceKind.Module, 5, "CSB 5 A (BUS2-5)"),
        new(8, "Centre cluster", PdmDeviceKind.Module, 5, "DEV 5 A (BUS2-6)"),
        new(11, "Turn left", PdmDeviceKind.Lamp, 10, "OEM turn flasher + J/B No.1 TURN 10 A (hazard: HZ 15 A)", LimitA: 10),
        new(13, "Turn right", PdmDeviceKind.Lamp, 10, "OEM turn flasher + J/B No.1 TURN 10 A (hazard: HZ 15 A)", LimitA: 10),
        new(17, "Power windows", PdmDeviceKind.Motor, 30, "R/B No.2 power main relay (the 30 A POWER fuse stays: it feeds the door locks)", LimitA: 25, InrushA: 60),
        new(18, "Pop-up LH", PdmDeviceKind.Motor, 30, "retract control relay R8 + RTR 30 A (AMI OUT-2) + K-POD (LOGIC M10) + D1 / D2"),
        new(19, "Pop-up RH", PdmDeviceKind.Motor, 30, "retract control relay R8 + RTR 30 A (AMI OUT-2) + K-POD (LOGIC M10) + D1 / D2"),
        new(20, "Rear defogger", PdmDeviceKind.Heater, 30, "defogger relay + J/B No.1 DEFOGGER 30 A", LimitA: 20, InrushA: 30),
        new(21, "Low beams", PdmDeviceKind.LedLamp, 15, "K-HL relay (LOGIC M1) + HL 15 A"),
        new(22, "High beams", PdmDeviceKind.LedLamp, 15, "K-HR relay (LOGIC M2) + HR 15 A"),
        new(23, "Horns", PdmDeviceKind.Horn, 15, "K-HORN relay (LOGIC M3); HZ 15 A"),
        new(24, "Tail / park / licence / dash lights", PdmDeviceKind.Lamp, 15, "taillight relay + J/B No.1 TAIL 15 A (front and rear on one output, as the one fuse)"),
    ];

    // firmware output pairing (output sub 17 PrimaryOutput, functions/profet.cpp: one follower per primary, it mirrors the
    // primary, the primary checks and reports the sum): (primary, follower) PDM numbers, both channels of one BTS7008-2EPA
    // (docs/firmware-pin-map.md: OUT1+2 U8, OUT3+4 U11, OUT5+6 U10, OUT7+8 U13)
    public static readonly (int Primary, int Follower)[] Pairs = [(1, 2), (11, 12), (13, 14)];

    // st185 circuits that stay on their OEM switch / relay and fuse: no PDM output is rated for their fuse (A pairs 12.5 A
    // < 15 / 20 A; the four 15 A and four 31 A board B outputs are full) and the stock st185 way has no relay coil to drive
    // (the switch carries the load current); the harness cost study (ADR-2026-11-23-harness-cost) found these moves
    // (M8-M10) only add wire.
    public static readonly (string Name, double St185FuseA, string StaysOn)[] OffThePdm =
    [
        ("Stop lamps", 15, "stop lamp switch on J/B No.1 STOP 15 A"),
        ("Back-up lamps", 15, "back-up switch on J/B No.1 GAUGE 15 A"),
        ("Wipers (slow / fast)", 20, "OEM wiper switch / relay on J/B No.1 WIPER 20 A"),
        ("Washer pump", 20, "OEM washer switch on J/B No.1 WIPER 20 A"),
    ];

    public static readonly Sw[] Switches =
    [
        new(1, "Head / flash (R-Y)", true, "R-Y IE1-2: light switch HEAD (C15-14) / dimmer FLASH (C15-13) to ground"),
        new(2, "High / flash (R-W)", true, "R-W IE1-18: dimmer HIGH / FLASH to ground", Wake: true),
        new(3, "DRL switch", true, "DRL-SW (the old K-DRL coil 85 wire) to ground"),
        new(4, "Horn switch", true, "G IE1-19: horn switch C15-10 to ground"),
        new(5, "EFI main relay (Bus 2)", false, "K-EFI 87 = LOGIC Bus 2 (12 V while the ECU holds K-EFI on Aux 6: key on and the ECU after-run)", Wake: true),
        new(7, "Light switch TAIL", true, "taillight relay coil wire: light switch TAIL / HEAD to ground", Wake: true),
        new(8, "Turn left", true, "turn switch LEFT (was the flasher's left lamp line) to ground"),
        new(9, "Hazard switch", true, "hazard switch H5 to ground", Wake: true),
        new(10, "Turn right", true, "turn switch RIGHT to ground"),
        new(16, "Ignition (IG2)", false, "B-O J/B1 1H-7 IGN (live at ON and ST), 12 V = on", Wake: true),
        // the pop-up limit contacts are on B, the motors' board (PdmFunctions.SetPopUps: the stop must not wait for CAN)
        new(17, "Pop-up LH at top", true, "retract motor LH up limit contact (TO CHECK on the bench: closed to ground at the top)"),
        new(18, "Pop-up LH at bottom", true, "retract motor LH down limit contact (TO CHECK: closed to ground at the bottom)"),
        new(19, "Pop-up RH at top", true, "retract motor RH up limit contact (TO CHECK: closed to ground at the top)"),
        new(20, "Pop-up RH at bottom", true, "retract motor RH down limit contact (TO CHECK: closed to ground at the bottom)"),
        new(22, "Rear defogger switch", true, "defogger push switch to ground (a press toggles)", Latched: true),
        new(23, "Light switch OFF (pods down)", true, "light control switch OFF contact (was the retract relay R8 'down' input) to ground"),
    ];

    public static Load LoadOf(int n) => Loads.Single(l => l.Number == n);

    private static readonly (int Out, PdmTriggerSpec Spec)[] Triggers =
    [
        (1, PdmTriggerSpec.Input(PdmTerm.In(Ignition))),                                     // CAN-Lambda, as K-ON (IG)
        (3, PdmTriggerSpec.Logic(PdmLogicOp.And, PdmTerm.In(3), PdmTerm.In(EfiMain), PdmTerm.In(1, true))),  // as K-DRL + RLY-DRL, Bus 2
        (7, PdmTriggerSpec.Input(PdmTerm.In(EfiMain))),
        (8, PdmTriggerSpec.Input(PdmTerm.In(EfiMain))),
        (17, PdmTriggerSpec.Input(PdmTerm.In(Ignition))),                                    // as the power main relay (IG)
        (21, PdmTriggerSpec.Input(PdmTerm.In(1))),
        (22, PdmTriggerSpec.Logic(PdmLogicOp.And, PdmTerm.In(2), PdmTerm.In(1))),                     // as K-HR: only with the head lamps on
        (23, PdmTriggerSpec.Input(PdmTerm.In(4))),
        (24, PdmTriggerSpec.Input(PdmTerm.In(Tail))),
    ];

    // wake inputs per board (bit i = board input i): only inputs the firmware can arm (core/sleep.cpp WakeInputMaskBadBits)
    public static int WakeMask(string role) => Switches.Where(s => s.Wake && Role(s.Number) == role).Aggregate(0, (m, s) => m | 1 << BoardIndex(s.Number));
    public static string Role(int input) => input <= 7 ? "A1" : input <= 14 ? "A2" : "B";
    public static int BoardIndex(int input) => input <= 7 ? input - 1 : input <= 14 ? input - 8 : input - 15;

    // ---------------- hand-made blocks (stock functions; the conflict engine's free lists) ----------------
    private static PdmBoard Q(PdmView v, string role) => v.Boards.Single(b => b.Role == role);
    private static int Free(PdmView v, string role, PdmResKind k) => PdmModel.Build(v).FreeOf(role, k).First();
    private static int DiVar(PdmView v, int input) => PdmFactoryDefaults.VarOf(Q(v, Role(input)).Device, Q(v, Role(input)).Device.DigitalInputs[BoardIndex(input)]);

    private const int Self = int.MaxValue;

    // virtual input ((a c0 b) c1 c); a negative var = NOT that var; Self = the virtual input itself (a latch)
    private static int Vi(PdmView v, string role, string name, int a, Conditional c0, int b, Conditional c1 = Conditional.And, int c = 0)
    {
        var d = Q(v, role).Device;
        var vi = d.VirtualInputs[Free(v, role, PdmResKind.VirtualInput)];
        PdmEngine.Reset(vi);
        var self = PdmFactoryDefaults.VarOf(d, vi);
        int V(int x) => Math.Abs(x) == Self ? self : Math.Abs(x);
        (vi.Name, vi.Enabled, vi.Mode) = (name, true, InputMode.Momentary);
        (vi.Not0, vi.Var0, vi.Cond0, vi.Not1, vi.Var1, vi.Cond1) = (a < 0, V(a), c0, b < 0, V(b), c1);
        if (c != 0) (vi.Not2, vi.Var2) = (c < 0, V(c));
        return self;
    }

    // the battery shed on B: off after ShedDelayMs at <= ShedOnV with the key on, back at >= ShedOffV (a latch); returns its variable
    private static int Shed(PdmView v)
    {
        var d = Q(v, "B").Device;
        var batt = d.VarMap.First(x => x.Owner == null && x.GetName() == "Battery Voltage").VariableIndex;
        int Cond(string name, Operator op, double arg)
        {
            var c = d.Conditions[Free(v, "B", PdmResKind.Condition)];
            PdmEngine.Reset(c);
            (c.Name, c.Enabled, c.Input, c.Operator, c.Arg) = (name, true, batt, op, arg);
            return PdmFactoryDefaults.VarOf(d, c);
        }
        var lo = Cond($"battery <= {ShedOnV} V (shed)", Operator.LessThanOrEqual, ShedOnV);
        var hi = Cond($"battery >= {ShedOffV} V (shed back)", Operator.GreaterThanOrEqual, ShedOffV);
        var low = Vi(v, "B", "battery low with the key on", lo, Conditional.And, DiVar(v, Ignition));
        var t = d.Timers[Free(v, "B", PdmResKind.Timer)];
        PdmEngine.Reset(t);
        (t.Name, t.Enabled, t.Input, t.Mode, t.Time) = ($"battery low {ShedDelayMs / 1000} s (shed)", true, low, TimerMode.OnDelay, ShedDelayMs);
        return Vi(v, "B", "battery shed (latch)", PdmFactoryDefaults.VarOf(d, t), Conditional.Or, Self, Conditional.And, -hi);
    }

    // Builds the car config on the boards of v (a New PDM). Throws when any step is refused.
    public static void Build(PdmView v)
    {
        static void Ok(string? why, string what) { if (why != null) throw new InvalidOperationException($"{what}: {why}"); }

        // the pairs first (stock 'Primary output', Advanced screen): the view then rates each primary at its pair rating
        foreach (var (p, f) in Pairs)
        {
            var po = v.Outputs.Single(r => r.Number == p);
            var fo = v.Outputs.Single(r => r.Number == f);
            if (po.Board != fo.Board || (po.Board != "B" && (po.BoardOutput - 1) / 2 != (fo.BoardOutput - 1) / 2))
                throw new InvalidOperationException($"pair {p} + {f}: not two channels of one driver chip");
            (fo.Output.Enabled, fo.Output.Name, fo.Output.PrimaryOutput) = (true, $"{LoadOf(p).Name} (pair)", po.BoardOutput - 1);
        }
        v = PdmView.Build(v.Boards.Select(b => b.Device));

        foreach (var s in Switches)
        {
            var d = v.Inputs.Single(r => r.Number == s.Number && r.Digital != null).Digital!;
            (d.Enabled, d.Name, d.Mode, d.Invert) = (true, s.Name, s.Latched ? InputMode.Latched : InputMode.Momentary, s.GroundActive);
            d.Pull = s.GroundActive ? InputPull.PullUp : InputPull.PullDown;
        }
        foreach (var (o, spec) in Triggers) Ok(PdmTriggers.Set(v, o, spec), $"output {o} trigger");
        Ok(PdmFunctions.SetTurn(v, new PdmTurnSpec(11, 13, PdmTerm.In(8), PdmTerm.In(10), PdmTerm.In(Hazard))), "turn signals");
        var shed = Shed(v);
        Ok(PdmTriggers.Set(v, 20, PdmTriggerSpec.Logic(PdmLogicOp.And, PdmTerm.In(22), PdmTerm.In(Ignition), PdmTerm.Of(shed, true))), "output 20 trigger");
        // pop-ups on B studs (PdmFunctions.SetPopUps): the PDM does what the stalk and the retract relay R8 did
        Ok(PdmFunctions.SetPopUps(v, new PdmPopUpSpec(18, 19, PdmTerm.In(1), PdmTerm.In(23), 17, 18, 19, 20, PdmTerm.In(3), PdmTerm.In(EfiMain))), "pop-ups");
        foreach (var l in Loads)
        {
            Ok(PdmPresets.Apply(v, l.Number, l.Kind), $"output {l.Number} preset");
            var x = v.Outputs.Single(r => r.Number == l.Number).Output;
            (x.Enabled, x.Name) = (true, l.Name);
            if (l.LimitA is { } a) x.CurrentLimit = a;
            if (l.InrushA is { } i) x.InrushCurrentLimit = i;
        }
        Ok(PdmKeyOff.SetAutoSleep(v, EfiMain, PdmKeyOff.MuteDelayMs, Tail, Hazard), "auto sleep");
        foreach (var q in v.Boards) q.Device.CustomPdm!.WakeInputMask = WakeMask(q.Role);
    }

    // every function in words, from the board params only (names left out: they live in the project file)
    public static List<string> Functions(PdmView v)
    {
        var m = PdmModel.Build(v);
        var list = m.Triggers.Select(t => $"{t.Out.Number}: {System.Text.RegularExpressions.Regex.Replace(t.Words, " '[^']*'", "")}").ToList();
        foreach (var o in v.Outputs)
        {
            var x = o.Output;
            var pro = o.Device.CustomPdm!.OutputProtection[o.BoardOutput - 1];
            list.Add($"{o.Number} {o.Board} OUT{o.BoardOutput}: {(x.Enabled ? "on" : "off")}, limit {x.CurrentLimit:0.##} A, inrush {x.InrushCurrentLimit:0.##} A / {x.InrushTime} ms, " +
                     $"trip {pro.TripTime} ms, {PdmPresets.TripsText(x.ResetCountLimit, x.ResetTime)}, soft start {(x.SoftStartEnabled ? $"{x.SoftStartRampTime} ms at {x.Frequency} Hz" : "no")}, " +
                     $"open-load {pro.MinCurrent:0.##} A");
        }
        foreach (var i in v.Inputs.Where(r => r.Digital != null))
            list.Add($"IN{i.Number}: {(i.Digital!.Enabled ? "on" : "off")}, {i.Digital.Pull}, {(i.Digital.Invert ? "inverted" : "not inverted")}, {i.Digital.Mode}, {i.Digital.DebounceTime} ms");
        list.AddRange(PdmValues.All(m).Select(f => $"{f.Board}: {f.Words}"));
        return list;
    }
}
