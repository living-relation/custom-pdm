using domain.Devices;
using domain.Devices.Functions;
using domain.Enums;
using domain.Interfaces;

namespace domain.CustomPdm;

// custom-pdm one-PDM editor, phase 2 (editor2): functions that drive SEVERAL outputs, in plain words, through the
// conflict engine. Read back from the params (no PC-only state); both outputs must be on one board.
// Turn signals + hazards (a2a: they move to the PDM; recipe proven in firmware/sim s3 F4, ECUMaster blinker module):
//   any   = virtual input "L OR R OR H"
//   FL    = ONE flasher on "any" (on / off ms, default 350 / 350 = 1.4 Hz: ECE R48 / FMVSS 108 ask 60-120 flashes
//           a minute)                                         -> left and right always flash in step (one flasher)
//   left  = virtual input "(L OR H) AND FL"  -> left output;  right = "(R OR H) AND FL" -> right output
//   Cost: 3 virtual inputs + 1 flasher (+ 1 CAN input per input of another board, the links 'off' recipe).
// Wiper (a2a; the firmware wiper function, one per board, digital-input mode; proven in s3 F8 "park cam"): the
//   board's wiper reads slow / fast / intermittent / wash inputs and the park cam (a digital input of the SAME
//   board: the stop must be exact); the motor-run output = the wiper's slow state, the high-speed output = its fast
//   state. Intermittent pause (intermittent 1 time), wipes after a wash. Cost: the board's wiper (+ 1 CAN input per
//   switch input of another board).
public record PdmFunction(string Kind, string Board, int[] Outputs, string Text, IReadOnlyList<PdmRes> Made, IReadOnlyList<string> PerOutput)
{
    public string OutputsKey => "," + string.Join(",", Outputs) + ",";
    public string Words(int output) => PerOutput[Array.IndexOf(Outputs, output)];
}

public record PdmTurnSpec(int LeftOut, int RightOut, PdmTerm Left, PdmTerm Right, PdmTerm Hazard, int OnMs = 350, int OffMs = 350);

public record PdmWiperSpec(int SlowOut, int FastOut, PdmTerm Slow, PdmTerm? Fast, PdmTerm? Inter, int ParkInput, bool ParkHigh = true,
    PdmTerm? Wash = null, int WashWipes = 3, int InterMs = 3000);

// carsim (Dan 2026-11-23: "why can't the PDM do what the stalk switch does?"): pop-up headlamps driven straight from the
// PDM, no retract relay. Each motor turns one way only (a crank: one half turn up, the next half turn down), so one
// high-side output per motor runs it until ITS OWN limit contact says it has arrived (like the wiper park cam):
//   up    = (UpAlso AND UpAlsoWith) OR Up      (ST185: DRL switch AND EFI main, or head / flash)
//   down  = Down AND NOT up                     (ST185: the light switch OFF contact; flash wins)
//   run   = (up AND NOT at top) OR (down AND NOT at bottom)        one per motor, its own limit inputs
// The limit inputs must be on the motors' board (the stop must not wait for CAN). Cost: 6 virtual inputs (+ 1 CAN
// input per command input of another board). Proven in firmware/sim s5_drive_cycle.py --car (pop-up phases).
public record PdmPopUpSpec(int LeftOut, int RightOut, PdmTerm Up, PdmTerm Down, int LeftTop, int LeftBottom, int RightTop, int RightBottom,
    PdmTerm? UpAlso = null, PdmTerm? UpAlsoWith = null);

public static class PdmFunctions
{
    public const string Turn = "turn signals", WiperKind = "wiper"; public const string PopUpsKind = "pop-ups";   // carsim
    public const int DefaultFlashMs = 350;

    private static PdmBoard BoardOf(PdmView v, PdmOutputRow o) => v.Boards.Single(b => ReferenceEquals(b.Device, o.Device));

    private static IDeviceFunction? StateOwner(FwDevice d, int var)
    {
        if (var <= PdmTriggers.AlwaysOnVar) return null;
        var owner = d.VarMap.FirstOrDefault(x => x.VariableIndex == var)?.Owner;
        return owner != null && PdmFactoryDefaults.VarOf(d, owner) == var ? owner : null;
    }

    // a var of board q as a term: its own input, an input of another board through a link-recipe slot, or the var
    private static PdmTerm Term(PdmView v, PdmBoard q, int var, List<PdmRes> made)
    {
        var d = q.Device;
        switch (StateOwner(d, var))
        {
            case DigitalInput di when PdmView.DigitalInputNumber(q.Role, d.DigitalInputs.IndexOf(di)) is { } n:
                return PdmTerm.In(n);
            case CanInput ci:
                var s = d.CanInputs.IndexOf(ci);
                if (ci.TimeoutEnabled && PdmLinks.RoleOfSlot(v, q, s) is { Kind: PdmSlotKind.Link } r && PdmView.DigitalInputNumber(r.Source.Role, r.Bit) is { } pn)
                {
                    made.Add(new PdmRes(q.Role, PdmResKind.CanInput, s));
                    return PdmTerm.In(pn);
                }
                break;
        }
        return PdmTerm.Of(var);
    }

    private static string T(PdmModel m, string role, PdmTerm t) => t.Input > 0 ? $"IN{t.Input}" : PdmTriggers.VarText(m, role, t.Var);

    // ---------------- read back ----------------

    public static IReadOnlyList<PdmFunction> All(PdmModel m)
    {
        var v = m.View;
        var list = new List<PdmFunction>();
        foreach (var q in v.Boards)
        {
            list.AddRange(Turns(m, q));
            if (WiperOf(m, q) is { } w) list.Add(w);
            list.AddRange(PopUpsOf(m, q));   // carsim
        }
        return list;
    }

    public static PdmFunction? Of(PdmModel m, PdmOutputRow o) => All(m).FirstOrDefault(f => f.Board == o.Board && f.Outputs.Contains(o.Number));

    private static bool Plain(VirtualInput vi) => vi is { Enabled: true, Mode: InputMode.Momentary, Not0: false, Not1: false, Not2: false };

    private static IEnumerable<PdmFunction> Turns(PdmModel m, PdmBoard q)
    {
        var v = m.View;
        var d = q.Device;
        var outs = v.Outputs.Where(o => o.Board == q.Role).ToList();
        for (var f = 0; f < d.Flashers.Count; f++)
        {
            var fl = d.Flashers[f];
            if (fl is not { Enabled: true, Single: false } || StateOwner(d, fl.Input) is not VirtualInput any || !Plain(any)
                || any is not { Cond0: Conditional.Or, Cond1: Conditional.Or } || any.Var0 == 0 || any.Var1 == 0 || any.Var2 == 0) continue;
            var flVar = PdmFactoryDefaults.VarOf(d, fl);
            // side output: (X OR H) AND FL with X = term 1 (left) or 2 (right) of "any", H = term 3
            PdmOutputRow? Side(int x) => outs.FirstOrDefault(o => StateOwner(d, o.Output.Input) is VirtualInput s && Plain(s)
                && s is { Cond0: Conditional.Or, Cond1: Conditional.And } && s.Var0 == x && s.Var1 == any.Var2 && s.Var2 == flVar);
            if (Side(any.Var0) is not { } lo || Side(any.Var1) is not { } ro || lo == ro) continue;
            var made = new List<PdmRes>();
            var (l, r, h) = (Term(v, q, any.Var0, made), Term(v, q, any.Var1, made), Term(v, q, any.Var2, made));
            made.AddRange([
                new PdmRes(q.Role, PdmResKind.VirtualInput, d.VirtualInputs.IndexOf(any)),
                new PdmRes(q.Role, PdmResKind.Flasher, f),
                new PdmRes(q.Role, PdmResKind.VirtualInput, d.VirtualInputs.IndexOf((VirtualInput)StateOwner(d, lo.Output.Input)!)),
                new PdmRes(q.Role, PdmResKind.VirtualInput, d.VirtualInputs.IndexOf((VirtualInput)StateOwner(d, ro.Output.Input)!))]);
            var rate = $"{fl.OnTime} / {fl.OffTime} ms";
            yield return new PdmFunction(Turn, q.Role, [lo.Number, ro.Number],
                $"the turn signals (outputs {lo.Number} / {ro.Number})", made,
                [$"turn signal LEFT: {T(m, q.Role, l)} or hazard {T(m, q.Role, h)}, flashing {rate} in step with output {ro.Number}",
                 $"turn signal RIGHT: {T(m, q.Role, r)} or hazard {T(m, q.Role, h)}, flashing {rate} in step with output {lo.Number}"]);
        }
    }

    private static int? WiperVar(FwDevice d, string prop) =>
        d.Wipers == null ? null : d.VarMap.FirstOrDefault(e => ReferenceEquals(e.Owner, d.Wipers) && e.PropertyName == prop)?.VariableIndex;

    private static PdmFunction? WiperOf(PdmModel m, PdmBoard q)
    {
        var v = m.View;
        var d = q.Device;
        if (d.Wipers is not { Enabled: true, Mode: WiperMode.DigIn } w || WiperVar(d, "Slow Output") is not { } sv) return null;
        var slow = v.Outputs.FirstOrDefault(o => o.Board == q.Role && o.Output.Input == sv);
        if (slow == null) return null;
        var fv = WiperVar(d, "Fast Output");
        var fast = v.Outputs.FirstOrDefault(o => o.Board == q.Role && fv != null && o.Output.Input == fv);
        var made = new List<PdmRes>();
        string? Sw(string what, int var) => var == 0 ? null : $"{what} {T(m, q.Role, Term(v, q, var, made))}";
        var sw = new[] { Sw("slow", w.SlowInput), Sw("fast", w.FastInput), Sw("intermittent", w.InterInput), Sw("wash", w.WashInput) }.OfType<string>();
        var park = Term(v, q, w.ParkInput, []);
        var desc = $"wiper on {q.Role}: switches {string.Join(", ", sw)}; park cam {T(m, q.Role, park)} ({(w.ParkStopLevel ? "on" : "off")} in the park zone)" +
                   (w.InterInput != 0 ? $", intermittent pause {PdmLinks.DelayText(w.IntermitTime[0])}" : "") +
                   (w.WashInput != 0 ? $", {w.WashWipeCycles} wipes after a wash" : "");
        made.Add(new PdmRes(q.Role, PdmResKind.Wiper, 0));
        var outs = fast != null ? new[] { slow.Number, fast.Number } : [slow.Number];
        var per = fast != null ? new[] { $"wiper motor run ({desc})", $"wiper high speed (output {slow.Number}'s wiper)" } : [$"wiper motor run ({desc})"];
        return new PdmFunction(WiperKind, q.Role, outs, $"the wiper of {q.Role} (outputs {string.Join(" / ", outs)})", made, per);
    }

    // ---------------- pop-ups (carsim) ----------------

    private static bool Shape(VirtualInput? vi, Conditional c0, bool not1, Conditional? c1) => vi != null && vi is { Enabled: true, Mode: InputMode.Momentary, Not0: false, Not2: false }
        && vi.Cond0 == c0 && vi.Not1 == not1 && (c1 == null ? vi.Var2 == 0 : vi.Cond1 == c1 && vi.Var2 != 0);

    private static IEnumerable<PdmFunction> PopUpsOf(PdmModel m, PdmBoard q)
    {
        var v = m.View;
        var d = q.Device;
        VirtualInput? V(int var) => StateOwner(d, var) as VirtualInput;
        bool OwnDi(int var) => StateOwner(d, var) is DigitalInput;
        var motors = new List<(PdmOutputRow O, VirtualInput Run, VirtualInput X, VirtualInput Up, VirtualInput Down)>();
        foreach (var o in v.Outputs.Where(o => o.Board == q.Role))
        {
            var run = V(o.Output.Input);
            if (!Shape(run, Conditional.And, true, Conditional.Or) || !OwnDi(run!.Var1)) continue;
            var x = V(run.Var2);
            if (!Shape(x, Conditional.And, true, null) || !OwnDi(x!.Var1)) continue;
            var down = V(x.Var0);
            if (!Shape(down, Conditional.And, true, null) || down!.Var1 != run.Var0) continue;
            var up = V(run.Var0);
            if (!(Shape(up, Conditional.And, false, Conditional.Or) || Shape(up, Conditional.And, false, null) && up!.Var1 == PdmTriggers.AlwaysOnVar)) continue;
            motors.Add((o, run, x, up!, down));
        }
        foreach (var g in motors.GroupBy(x => (x.Up, x.Down)).Where(g => g.Count() == 2))
        {
            var (l, r) = (g.OrderBy(x => x.O.Number).First(), g.OrderBy(x => x.O.Number).Last());
            var made = new List<PdmRes>();
            var up = g.Key.Up;
            var upText = up.Var2 != 0
                ? $"({T(m, q.Role, Term(v, q, up.Var0, made))} and {T(m, q.Role, Term(v, q, up.Var1, made))}) or {T(m, q.Role, Term(v, q, up.Var2, made))}"
                : T(m, q.Role, Term(v, q, up.Var0, made));
            var downText = T(m, q.Role, Term(v, q, g.Key.Down.Var0, made));
            foreach (var vi in new[] { up, g.Key.Down, l.X, l.Run, r.X, r.Run }) made.Add(new PdmRes(q.Role, PdmResKind.VirtualInput, d.VirtualInputs.IndexOf(vi)));
            string Per(string side, VirtualInput run, VirtualInput x) =>
                $"pop-up {side} motor: up on {upText}, down on {downText} (not while up); stops at its own limit contacts {T(m, q.Role, Term(v, q, run.Var1, []))} (top) / {T(m, q.Role, Term(v, q, x.Var1, []))} (bottom)";
            yield return new PdmFunction(PopUpsKind, q.Role, [l.O.Number, r.O.Number], $"the pop-up headlamps (outputs {l.O.Number} / {r.O.Number})", made,
                [Per("LH", l.Run, l.X), Per("RH", r.Run, r.X)]);
        }
    }

    public static IReadOnlyDictionary<PdmResKind, int> PopUpCost(PdmView v, string role, PdmPopUpSpec s)
    {
        var c = new Dictionary<PdmResKind, int> { [PdmResKind.VirtualInput] = 6 };
        if (OtherBoard(v, role, [s.Up, s.Down, s.UpAlso, s.UpAlsoWith]) is > 0 and var n) c[PdmResKind.CanInput] = n;
        return c;
    }

    public static string? SetPopUps(PdmView v, PdmPopUpSpec s, bool overwrite = false)
    {
        if ((s.UpAlso == null) != (s.UpAlsoWith == null)) return "The second 'up' condition needs both of its inputs (or neither).";
        if (Begin(v, PopUpsKind, [s.LeftOut, s.RightOut], overwrite, out var q, out var restore) is { } why) return why;
        string? Fail(string msg) { restore.Restore(); return msg; }
        foreach (var (t, w) in new[] { (s.Up, "up"), (s.Down, "down"), (s.UpAlso, "up (also)"), (s.UpAlsoWith, "up (also, with)") })
            if (TermProblem(v, q.Role, t, w) is { } bad) return Fail(bad);
        var limits = new[] { s.LeftTop, s.LeftBottom, s.RightTop, s.RightBottom };
        if (limits.Distinct().Count() != 4) return Fail("The four limit contacts must be four different inputs.");
        if (limits.Any(n => v.Inputs.FirstOrDefault(r => r.Number == n && r.Digital != null)?.Board != q.Role))
            return Fail($"The pop-up limit contacts must be digital inputs of {q.Role} (the motors' board): the stop must not wait for CAN.");
        var need = PopUpCost(v, q.Role, s);
        if (!Fits(v, q.Role, need)) return Fail(Full(v, q.Role, need));
        var m = PdmModel.Build(v);
        var d = q.Device;
        var freeC = new Queue<int>(m.FreeOf(q.Role, PdmResKind.CanInput));
        var freeV = new Queue<int>(m.FreeOf(q.Role, PdmResKind.VirtualInput));
        VirtualInput Vi(string name)
        {
            var vi = d.VirtualInputs[freeV.Dequeue()];
            PdmEngine.Reset(vi);
            (vi.Name, vi.Enabled, vi.Mode) = (name, true, InputMode.Momentary);
            return vi;
        }
        int Var(VirtualInput x) => PdmFactoryDefaults.VarOf(d, x);
        int Di(int n) => PdmFactoryDefaults.VarOf(d, v.Inputs.Single(r => r.Number == n && r.Digital != null).Digital!);
        var upT = TermVar(v, q, s.Up, freeC, "pop-ups up");
        var downT = TermVar(v, q, s.Down, freeC, "pop-ups down");
        var up = Vi("pop-ups up");
        if (s.UpAlso != null)
            (up.Var0, up.Cond0, up.Var1, up.Cond1, up.Var2) = (TermVar(v, q, s.UpAlso, freeC, "pop-ups up"), Conditional.And,
                TermVar(v, q, s.UpAlsoWith!, freeC, "pop-ups up"), Conditional.Or, upT);
        else (up.Var0, up.Cond0, up.Var1) = (upT, Conditional.And, PdmTriggers.AlwaysOnVar);
        var down = Vi("pop-ups down");
        (down.Var0, down.Cond0, down.Not1, down.Var1) = (downT, Conditional.And, true, Var(up));
        foreach (var (o, top, bottom, side) in new[] { (s.LeftOut, s.LeftTop, s.LeftBottom, "LH"), (s.RightOut, s.RightTop, s.RightBottom, "RH") })
        {
            var x = Vi($"pop-up {side}: down, not at the bottom");
            (x.Var0, x.Cond0, x.Not1, x.Var1) = (Var(down), Conditional.And, true, Di(bottom));
            var run = Vi($"pop-up {side}: run");
            (run.Var0, run.Cond0, run.Not1, run.Var1, run.Cond1, run.Var2) = (Var(up), Conditional.And, true, Di(top), Conditional.Or, Var(x));
            v.Outputs.Single(r => r.Number == o).Output.Input = Var(run);
        }
        return null;
    }

    // ---------------- cost ----------------

    private static int OtherBoard(PdmView v, string role, IEnumerable<PdmTerm?> terms) =>
        terms.OfType<PdmTerm>().Where(t => t.Input > 0).Select(t => t.Input).Distinct()
            .Count(n => v.Inputs.FirstOrDefault(r => r.Number == n && r.Digital != null)?.Board is { } b && b != role);

    public static IReadOnlyDictionary<PdmResKind, int> TurnCost(PdmView v, string role, PdmTurnSpec s)
    {
        var c = new Dictionary<PdmResKind, int> { [PdmResKind.VirtualInput] = 3, [PdmResKind.Flasher] = 1 };
        if (OtherBoard(v, role, [s.Left, s.Right, s.Hazard]) is > 0 and var n) c[PdmResKind.CanInput] = n;
        return c;
    }

    public static IReadOnlyDictionary<PdmResKind, int> WiperCost(PdmView v, string role, PdmWiperSpec s)
    {
        var c = new Dictionary<PdmResKind, int> { [PdmResKind.Wiper] = 1 };
        if (OtherBoard(v, role, [s.Slow, s.Fast, s.Inter, s.Wash]) is > 0 and var n) c[PdmResKind.CanInput] = n;
        return c;
    }

    // ---------------- set / remove ----------------

    private static string? OutProblem(PdmView v, int n, out PdmOutputRow? o)
    {
        o = v.Outputs.FirstOrDefault(r => r.Number == n);
        if (o == null) return $"Output {n} is not in this PDM (1-24, its board must be in the project).";
        return PdmTriggers.Unsettable(o);
    }

    private static string? TermProblem(PdmView v, string role, PdmTerm? t, string what)
    {
        if (t == null) return null;
        var d = v.Boards.Single(b => b.Role == role).Device;
        if (t.Not) return $"The {what} input cannot be inverted here (invert the input itself).";
        if (t.Input > 0 && v.Inputs.All(r => r.Number != t.Input || r.Digital == null)) return $"IN{t.Input} is not a digital input of this PDM.";
        if (t.Input == 0 && (t.Var == 0 || d.VarMap.FirstOrDefault(e => e.VariableIndex == t.Var) is not { DataType: "bool" }))
            return $"Pick an input for the {what} switch.";
        return null;
    }

    // what the given outputs are assigned to now, other than this kind of function: text for "Overwrite?"
    public static string? Conflict(PdmView v, string kind, params int[] outputs)
    {
        var m = PdmModel.Build(v);
        var taken = new List<string>();
        foreach (var n in outputs.Where(n => n > 0).Distinct())
        {
            var t = m.Triggers.FirstOrDefault(x => x.Out.Number == n);
            if (t == null || t.Kind == PdmTriggerKind.None) continue;
            if (t.Kind == PdmTriggerKind.Function && Of(m, t.Out) is { } f && f.Kind == kind) continue;
            taken.Add($"output {n} ({t.Words})");
        }
        return taken.Count == 0 ? null : $"Already assigned: {string.Join("; ", taken)}. Overwrite?";
    }

    private static int TermVar(PdmView v, PdmBoard q, PdmTerm t, Queue<int> free, string tag)
    {
        if (t.Input == 0) return t.Var;
        var row = v.Inputs.Single(r => r.Number == t.Input && r.Digital != null);
        if (row.Board == q.Role) return PdmFactoryDefaults.VarOf(q.Device, row.Digital!);
        var slot = free.Dequeue();
        PdmLinks.MakeTermSlot(v, q, slot, row, tag);
        return PdmFactoryDefaults.CanInState(q.Device, slot);
    }

    // shared prelude: outputs on one board, replace what they had (asked first), all-or-nothing
    private static string? Begin(PdmView v, string kind, int[] outs, bool overwrite, out PdmBoard q, out PdmSnapshot restore)
    {
        q = null!;
        restore = null!;
        var rows = new List<PdmOutputRow>();
        foreach (var n in outs.Where(n => n > 0))
        {
            if (OutProblem(v, n, out var o) is { } no) return no;
            rows.Add(o!);
        }
        if (rows.Select(r => r.Board).Distinct().Count() != 1) return $"The {kind} outputs must be on one board (one flasher / one wiper per board).";
        if (outs.Where(n => n > 0).Distinct().Count() != rows.Count) return $"Pick different outputs for the {kind}.";
        if (!overwrite && Conflict(v, kind, outs) is { } taken) return taken;
        q = BoardOf(v, rows[0]);
        restore = PdmSnapshot.Take([q.Device]);
        foreach (var r in rows) PdmTriggers.Release(v, r);
        foreach (var r in rows) r.Output.Input = 0;
        return null;
    }

    private static string Full(PdmView v, string role, IReadOnlyDictionary<PdmResKind, int> need)
    {
        var m = PdmModel.Build(v);
        var u = m.Use(role);
        var short_ = need.Where(n => n.Key != PdmResKind.Wiper && m.FreeOf(role, n.Key).Count < n.Value).Select(n => u.Of(n.Key).Text);
        return $"{role} is full: this needs {PdmTriggers.CostText(need)}; {string.Join("; ", short_)}. Nothing changed.";
    }

    private static bool Fits(PdmView v, string role, IReadOnlyDictionary<PdmResKind, int> need)
    {
        var m = PdmModel.Build(v);
        return need.Where(n => n.Key != PdmResKind.Wiper).All(n => m.FreeOf(role, n.Key).Count >= n.Value);
    }

    public static string? SetTurn(PdmView v, PdmTurnSpec s, bool overwrite = false)
    {
        if (s.OnMs is < 1 or > PdmTriggers.MaxFlashMs || s.OffMs is < 1 or > PdmTriggers.MaxFlashMs) return $"Flash on / off times must be 1 to {PdmTriggers.MaxFlashMs} ms.";
        if (Begin(v, Turn, [s.LeftOut, s.RightOut], overwrite, out var q, out var restore) is { } why) return why;
        foreach (var (t, w) in new[] { (s.Left, "left"), (s.Right, "right"), (s.Hazard, "hazard") })
            if (TermProblem(v, q.Role, t, w) is { } bad) { restore.Restore(); return bad; }
        if (new[] { s.Left, s.Right, s.Hazard }.Distinct().Count() != 3) { restore.Restore(); return "Left, right and hazard must be three different inputs."; }
        var need = TurnCost(v, q.Role, s);
        if (!Fits(v, q.Role, need)) { var f = Full(v, q.Role, need); restore.Restore(); return f; }
        var m = PdmModel.Build(v);
        var d = q.Device;
        var freeC = new Queue<int>(m.FreeOf(q.Role, PdmResKind.CanInput));
        var freeV = new Queue<int>(m.FreeOf(q.Role, PdmResKind.VirtualInput));
        var fl = d.Flashers[m.FreeOf(q.Role, PdmResKind.Flasher)[0]];
        var (l, r, h) = (TermVar(v, q, s.Left, freeC, "turn L"), TermVar(v, q, s.Right, freeC, "turn R"), TermVar(v, q, s.Hazard, freeC, "hazard"));
        VirtualInput Vi(string name)
        {
            var vi = d.VirtualInputs[freeV.Dequeue()];
            PdmEngine.Reset(vi);
            (vi.Name, vi.Enabled, vi.Mode) = (name, true, InputMode.Momentary);
            return vi;
        }
        var any = Vi("turn signals (any)");
        (any.Var0, any.Cond0, any.Var1, any.Cond1, any.Var2) = (l, Conditional.Or, r, Conditional.Or, h);
        PdmEngine.Reset(fl);
        (fl.Name, fl.Enabled, fl.Input, fl.OnTime, fl.OffTime, fl.Single) = ("turn signals", true, PdmFactoryDefaults.VarOf(d, any), s.OnMs, s.OffMs, false);
        var flVar = PdmFactoryDefaults.VarOf(d, fl);
        foreach (var (x, n, name) in new[] { (l, s.LeftOut, "turn LEFT"), (r, s.RightOut, "turn RIGHT") })
        {
            var vi = Vi(name);
            (vi.Var0, vi.Cond0, vi.Var1, vi.Cond1, vi.Var2) = (x, Conditional.Or, h, Conditional.And, flVar);
            v.Outputs.Single(o => o.Number == n).Output.Input = PdmFactoryDefaults.VarOf(d, vi);
        }
        return null;
    }

    public static string? SetWiper(PdmView v, PdmWiperSpec s, bool overwrite = false)
    {
        if (s.InterMs is < 100 or > 60000) return "The intermittent pause must be 100 to 60000 ms.";
        if (s.WashWipes is < 0 or > 20) return "Wipes after a wash: 0 to 20.";
        var outs = s.FastOut > 0 ? new[] { s.SlowOut, s.FastOut } : [s.SlowOut];
        if (Begin(v, WiperKind, outs, overwrite, out var q, out var restore) is { } why) return why;
        var d = q.Device;
        string? Fail(string msg) { restore.Restore(); return msg; }
        if (d.Wipers == null || WiperVar(d, "Slow Output") == null) return Fail($"{q.Role} has no wiper function.");
        foreach (var (t, what) in new[] { (s.Slow, "slow"), (s.Fast, "fast"), (s.Inter, "intermittent"), (s.Wash, "wash") })
            if (TermProblem(v, q.Role, t, what) is { } bad) return Fail(bad);
        var park = v.Inputs.FirstOrDefault(r => r.Number == s.ParkInput && r.Digital != null);
        if (park == null || park.Board != q.Role) return Fail($"The park cam must be a digital input of {q.Role} (the wiper's board): the stop must not wait for CAN.");
        // the wiper itself: if it is in use for something that is not this function, it was asked about in Conflict only
        // through its outputs; a wiper set by hand without outputs is replaced here (it drove nothing)
        var need = WiperCost(v, q.Role, s);
        if (!Fits(v, q.Role, need)) return Fail(Full(v, q.Role, need));
        var freeC = new Queue<int>(PdmModel.Build(v).FreeOf(q.Role, PdmResKind.CanInput));
        var w = d.Wipers;
        ResetWiper(w);
        (w.Enabled, w.Mode, w.SlowInput) = (true, WiperMode.DigIn, TermVar(v, q, s.Slow, freeC, "wiper slow"));
        if (s.Fast != null) w.FastInput = TermVar(v, q, s.Fast, freeC, "wiper fast");
        if (s.Inter != null) w.InterInput = TermVar(v, q, s.Inter, freeC, "wiper intermittent");
        if (s.Wash != null) w.WashInput = TermVar(v, q, s.Wash, freeC, "wiper wash");
        (w.ParkInput, w.ParkStopLevel, w.WashWipeCycles) = (PdmFactoryDefaults.VarOf(d, park.Digital!), s.ParkHigh, s.WashWipes);
        w.IntermitTime[0] = s.InterMs;
        v.Outputs.Single(o => o.Number == s.SlowOut).Output.Input = WiperVar(d, "Slow Output")!.Value;
        if (s.FastOut > 0) v.Outputs.Single(o => o.Number == s.FastOut).Output.Input = WiperVar(d, "Fast Output")!.Value;
        return null;
    }

    private static void ResetWiper(Wiper w)
    {
        var f = new Wiper(w.Name);
        var (ps, fs) = (w.Params, f.Params);
        for (var i = 0; i < ps.Count; i++) ps[i].SetValue(fs[i].GetValue());
    }

    // null = the whole function of this output removed (its outputs' triggers none, its parts fresh)
    public static string? Remove(PdmView v, int output)
    {
        var m = PdmModel.Build(v);
        var o = v.Outputs.FirstOrDefault(r => r.Number == output);
        if (o == null || Of(m, o) is not { } f) return $"Output {output} is not part of a function.";
        var d = o.Device;
        foreach (var n in f.Outputs) v.Outputs.Single(r => r.Number == n).Output.Input = 0;
        foreach (var r in f.Made)
            switch (r.Kind)
            {
                case PdmResKind.Wiper: ResetWiper(d.Wipers); break;
                case PdmResKind.VirtualInput: PdmEngine.Reset(d.VirtualInputs[r.Index]); break;
                case PdmResKind.Flasher: PdmEngine.Reset(d.Flashers[r.Index]); break;
            }
        // the CAN inputs it made for inputs of other boards, once nothing reads them
        foreach (var r in f.Made.Where(r => r.Kind == PdmResKind.CanInput))
            if (!PdmEngine.IsRead(d, PdmFactoryDefaults.CanInState(d, r.Index))) PdmLinks.Reset(d.CanInputs[r.Index]);
        return null;
    }
}
