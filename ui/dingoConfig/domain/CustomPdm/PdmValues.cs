using System.Globalization;
using domain.Devices;
using domain.Devices.Functions;
using domain.Enums;
using domain.Interfaces;

namespace domain.CustomPdm;

// custom-pdm one-PDM editor, phase 2b (editor2b): values and system functions on /pdm, in plain words, through the
// conflict engine. Each is read back from the board params (no PC-only state) and claimed as a VALUE: anything may
// read it (levels, AND / OR terms, curves, CAN outputs), nothing else may rewrite it. Kinds (firmware / sim proof):
//   counter   1 counter: up / down / reset inputs, min-max, wrap, hold-to-reset (s3 F5 "4-position mode button")
//   math      1 math block: value = (A op B) x factor + offset, B a value or a constant (s3 F6 "math blocks")
//   level     2 conditions + 1 latch virtual input "(on OR itself) AND NOT off" = an on / off SIGNAL with hysteresis
//             that AND / OR triggers can use as a term (the trigger editor's level recipe, s3 F2)
//   CAN value 1 CAN input reading a number (PdmEcu.AddValue); a value of ANOTHER board = its cyclic signal (DbcExport,
//             the frames the app decodes) read on this board (not msg 37: that is the links' message)
//   keypad    1 CAN input per button: BlinkMarine button frame 0x180 + node, bit = button - 1, Equal 1, time-out 1 s;
//             the keypad node is refused when one of its CANopen IDs (0x180-0x700 + node) is inside a PDM board's block
//   starter   the board's starter block: while the crank input is on, the chosen outputs of that board are held off
//             (s3 F9); one PDM function = the starter block of every board that has a chosen output
//   retry     PRO P3 master retry (0x7F00 sub 6): a rising edge of the input clears the faults of every output; set on
//             all three boards (s3 "P3")
//   CAN out   1 CAN output per signal (any value / flag, ID, start bit, length, byte order, factor / offset, rate);
//             signals with one ID share one frame (firmware can_outputs.cpp); the 8 open-load flags of a board as one
//             frame = 8 one-bit outputs (msg 37 is full)
// An input of another board inside a counter / starter / retry is one CAN input on msg 37 (the links 'off' recipe).
// configfix: AutoSleep = the key-off mute timer of a board (+ its ignition CAN input), PdmKeyOff
public enum PdmValueKind { Counter, Math, Level, CanValue, Keypad, Starter, Retry, CanOut, AutoSleep }

public record PdmValueFn(PdmValueKind Kind, string Board, PdmRes Main, IReadOnlyList<PdmRes> Made, string Words, int Var);

public record PdmCounterSpec(string Board, PdmTerm Up, PdmTerm? Down = null, PdmTerm? Reset = null, int Min = 0, int Max = 3,
    bool Wrap = true, int HoldResetMs = 0);

public record PdmMathSpec(string Board, MathOp Op, int A, int B = 0, double ConstB = 0, double Factor = 1, double Offset = 0);

public record PdmCanOutSpec(string Board, int Id, int StartBit, int Length, int Var, ByteOrder Order = ByteOrder.LittleEndian,
    bool Signed = false, double Factor = 1, double Offset = 0, int IntervalMs = 100);

public static class PdmValues
{
    public const int KeypadButtons = 20, MaxCount = 1000;
    public static readonly int[] KeypadOffsets = [0x180, 0x200, 0x280, 0x300, 0x380, 0x400, 0x480, 0x500, 0x580, 0x600, 0x700];

    private static string Num(double x) => x.ToString("0.###", CultureInfo.InvariantCulture);

    private static IDeviceFunction? StateOwner(FwDevice d, int var)
    {
        if (var <= PdmTriggers.AlwaysOnVar) return null;
        var owner = d.VarMap.FirstOrDefault(x => x.VariableIndex == var)?.Owner;
        return owner != null && PdmFactoryDefaults.VarOf(d, owner) == var ? owner : null;
    }

    // a var of q as words (inputs of other boards through their link-recipe slot); made gets that slot
    private static string T(PdmModel m, PdmBoard q, int var, List<PdmRes> made)
    {
        var d = q.Device;
        if (StateOwner(d, var) is CanInput ci && d.CanInputs.IndexOf(ci) is var s && ci.TimeoutEnabled
            && PdmLinks.RoleOfSlot(m.View, q, s) is { Kind: PdmSlotKind.Link } r && PdmView.DigitalInputNumber(r.Source.Role, r.Bit) is { } pn)
        {
            made.Add(new PdmRes(q.Role, PdmResKind.CanInput, s));
            return $"IN{pn}";
        }
        return PdmTriggers.VarText(m, q.Role, var);
    }

    // ---------------- read back ----------------

    public static bool IsLevelLatch(FwDevice d, VirtualInput vi, out Condition on, out Condition off)
    {
        on = off = null!;
        if (vi is not { Enabled: true, Mode: InputMode.Momentary, Not0: false, Cond0: Conditional.Or, Not1: false, Cond1: Conditional.And, Not2: true }
            || vi.Var1 != PdmFactoryDefaults.VarOf(d, vi)) return false;
        if (StateOwner(d, vi.Var0) is not Condition a || StateOwner(d, vi.Var2) is not Condition b || ReferenceEquals(a, b)) return false;
        if (a is not { Enabled: true } || b is not { Enabled: true } || a.Input == 0 || a.Input != b.Input) return false;
        if ((a.Operator, b.Operator) is not ((Operator.GreaterThanOrEqual, Operator.LessThanOrEqual) or (Operator.LessThanOrEqual, Operator.GreaterThanOrEqual))) return false;
        (on, off) = (a, b);
        return true;
    }

    public static string LevelWords(PdmModel m, string role, Condition on, Condition off) =>
        on.Operator == Operator.GreaterThanOrEqual
            ? $"{PdmTriggers.VarText(m, role, on.Input)} on at {Num(on.Arg)} or more, off at {Num(off.Arg)} or less"
            : $"{PdmTriggers.VarText(m, role, on.Input)} on at {Num(on.Arg)} or less, off at {Num(off.Arg)} or more";

    public static bool IsValueShape(CanInput c) =>
        c is { Enabled: true, Operator: Operator.GreaterThanOrEqual, Mode: InputMode.Momentary } && c.Operand <= PdmEcu.AnyValue + 1;

    public static bool IsKeypadShape(PdmView v, CanInput c) =>
        c is { Enabled: true, Ide: false, BitLength: 1, Factor: 1.0, Offset: 0.0, ByteOrder: ByteOrder.LittleEndian, Signed: false,
            Operator: Operator.Equal, Operand: 1.0, Mode: InputMode.Momentary, Bus: 0, TimeoutEnabled: true }
        && c.Id is > 0x180 and < 0x200 && c.StartBit < KeypadButtons;

    public static IReadOnlyList<PdmValueFn> All(PdmModel m)
    {
        var v = m.View;
        var list = new List<PdmValueFn>();
        var levelOuts = v.Outputs.Select(o => o.Output.Input).ToHashSet();
        foreach (var q in v.Boards)
        {
            var d = q.Device;
            var r = q.Role;
            for (var i = 0; i < d.Counters.Count; i++)
            {
                var c = d.Counters[i];
                if (!c.Enabled || c.IncInput == 0) continue;
                var made = new List<PdmRes>();
                var w = $"counter: up on {T(m, q, c.IncInput, made)}" + (c.DecInput != 0 ? $", down on {T(m, q, c.DecInput, made)}" : "") +
                        (c.ResetInput != 0 ? $", reset on {T(m, q, c.ResetInput, made)}" : "") + $", {c.MinCount} to {c.MaxCount}" +
                        (c.WrapAround ? " (wraps)" : "") + (c.HoldToReset ? $", hold {PdmLinks.DelayText(c.ResetTime)} to reset" : "");
                var me = new PdmRes(r, PdmResKind.Counter, i);
                list.Add(new PdmValueFn(PdmValueKind.Counter, r, me, [me, .. made], w, PdmFactoryDefaults.VarOf(d, c)));
            }
            for (var i = 0; i < d.MathBlocks.Count; i++)
            {
                var x = d.MathBlocks[i];
                if (!x.Enabled || x.InputA == 0) continue;
                var b = x.InputB != 0 ? PdmTriggers.VarText(m, r, x.InputB) : Num(x.ConstB);
                var core = x.Operation switch
                {
                    MathOp.Add => $"{PdmTriggers.VarText(m, r, x.InputA)} + {b}",
                    MathOp.Sub => $"{PdmTriggers.VarText(m, r, x.InputA)} - {b}",
                    MathOp.Mul => $"{PdmTriggers.VarText(m, r, x.InputA)} x {b}",
                    MathOp.Div => $"{PdmTriggers.VarText(m, r, x.InputA)} / {b}",
                    MathOp.Min => $"the lower of {PdmTriggers.VarText(m, r, x.InputA)} and {b}",
                    MathOp.Max => $"the higher of {PdmTriggers.VarText(m, r, x.InputA)} and {b}",
                    _ => $"the average of {PdmTriggers.VarText(m, r, x.InputA)} and {b}"
                };
                var w = $"math: ({core})" + (x.Factor != 1 ? $" x {Num(x.Factor)}" : "") + (x.Offset != 0 ? $" {(x.Offset < 0 ? "-" : "+")} {Num(Math.Abs(x.Offset))}" : "");
                var me = new PdmRes(r, PdmResKind.Math, i);
                list.Add(new PdmValueFn(PdmValueKind.Math, r, me, [me], w, PdmFactoryDefaults.VarOf(d, x)));
            }
            for (var k = 0; k < d.VirtualInputs.Count; k++)
            {
                var vi = d.VirtualInputs[k];
                var var = PdmFactoryDefaults.VarOf(d, vi);
                // not an output's own level trigger (direct, or wrapped by its timer / flasher)
                if (levelOuts.Contains(var) || PdmLinks.IsReservedVirt(q, k) || d.Timers.Any(t => t.Enabled && t.Input == var)
                    || d.Flashers.Any(f => f.Enabled && f.Input == var) || !IsLevelLatch(d, vi, out var on, out var off)) continue;
                var me = new PdmRes(r, PdmResKind.VirtualInput, k);
                list.Add(new PdmValueFn(PdmValueKind.Level, r, me,
                    [me, new PdmRes(r, PdmResKind.Condition, d.Conditions.IndexOf(on)), new PdmRes(r, PdmResKind.Condition, d.Conditions.IndexOf(off))],
                    $"level: {LevelWords(m, r, on, off)}", var));
            }
            for (var s = 0; s < d.CanInputs.Count; s++)
            {
                var c = d.CanInputs[s];
                if (PdmLinks.IsFanSlot(q, s)) continue;
                var me = new PdmRes(r, PdmResKind.CanInput, s);
                if (IsValueShape(c))
                {
                    var src = v.Boards.FirstOrDefault(p => p.Role != r && c.Id >= p.Device.BaseId && c.Id < p.Device.BaseId + 0x40);
                    var from = src != null ? $"{src.Role}'s frame 0x{c.Id:X3}" : $"frame 0x{c.Id:X3}";
                    list.Add(new PdmValueFn(PdmValueKind.CanValue, r, me, [me],
                        $"CAN value: {from}, start bit {c.StartBit}, {c.BitLength} bits {(c.ByteOrder == ByteOrder.BigEndian ? "big" : "little")} endian{(c.Signed ? " signed" : "")}, x {Num(c.Factor)} + {Num(c.Offset)}",
                        PdmFactoryDefaults.CanInState(d, s) + 1));
                }
                else if (IsKeypadShape(v, c))
                    list.Add(new PdmValueFn(PdmValueKind.Keypad, r, me, [me], $"keypad node 0x{c.Id - 0x180:X2} button {c.StartBit + 1}", PdmFactoryDefaults.CanInState(d, s)));
            }
            if (d.StarterDisable is { Enabled: true } st && st.Input != 0 && st.OutputsDisabled.Any(x => x))
            {
                var made = new List<PdmRes>();
                var outs = st.OutputsDisabled.Select((x, i) => (x, i)).Where(t => t.x).Select(t => PdmView.OutputNumber(r, t.i)).OfType<int>();
                var me = new PdmRes(r, PdmResKind.Starter, 0);
                list.Add(new PdmValueFn(PdmValueKind.Starter, r, me, [me, .. made],
                    $"starter interlock: while {T(m, q, st.Input, made)} is on, outputs {string.Join(", ", outs)} are held off", 0));
                list[^1] = list[^1] with { Made = [me, .. made] };
            }
            // configfix: auto sleep after the key off (PdmKeyOff): the mute timer and its ignition CAN input
            if (d.SleepEnabled && PdmKeyOff.SleepTimer(d) is { Enabled: true } kt)
            {
                var made = new List<PdmRes>();
                var me = new PdmRes(r, PdmResKind.Timer, d.Timers.IndexOf(kt));
                var w = $"auto sleep: CAN TX muted {PdmLinks.DelayText(kt.Time)} after {T(m, q, kt.ResetInput, made)} goes off, then the board sleeps 30 s after the bus is quiet";
                list.Add(new PdmValueFn(PdmValueKind.AutoSleep, r, me, [me, .. made], w, 0));
            }
            if (d.CustomPdm is { MasterRetryInput: > 0 } cp)
            {
                var made = new List<PdmRes>();
                var w = $"master retry: {T(m, q, cp.MasterRetryInput, made)} switching on clears the faults of every {r} output";
                var me = new PdmRes(r, PdmResKind.Device, 0);
                list.Add(new PdmValueFn(PdmValueKind.Retry, r, me, [.. made], w, 0));
            }
            for (var i = 0; i < d.CanOutputs.Count; i++)
            {
                var c = d.CanOutputs[i];
                if (!c.Enabled || c.Id == 0) continue;
                var me = new PdmRes(r, PdmResKind.CanOutput, i);
                list.Add(new PdmValueFn(PdmValueKind.CanOut, r, me, [me],
                    $"CAN out: {PdmTriggers.VarText(m, r, c.Input)} on 0x{c.Id:X3} start bit {c.StartBit}, {c.BitLength} bits{(c.ByteOrder == ByteOrder.BigEndian ? " big endian" : "")}" +
                    (c.Factor != 1 || c.Offset != 0 ? $", raw = (value - {Num(c.Offset)}) / {Num(c.Factor)}" : "") + $", every {c.Interval} ms", 0));
            }
        }
        return list;
    }

    // ---------------- helpers ----------------

    private static PdmBoard? Board(PdmView v, string role) => v.Boards.FirstOrDefault(b => b.Role == role);

    private static string? TermProblem(PdmView v, PdmBoard q, PdmTerm? t, string what)
    {
        if (t == null) return null;
        if (t.Not) return $"The {what} input cannot be inverted here (invert the input itself).";
        if (t.Input > 0) return v.Inputs.Any(r => r.Number == t.Input && r.Digital != null) ? null : $"IN{t.Input} is not a digital input of this PDM.";
        return q.Device.VarMap.FirstOrDefault(e => e.VariableIndex == t.Var) is { DataType: "bool" } || t.Var == PdmTriggers.AlwaysOnVar
            ? null : $"Pick an on / off signal of {q.Role} for the {what} input.";
    }

    private static int OtherBoard(PdmView v, string role, IEnumerable<PdmTerm?> terms) =>
        terms.OfType<PdmTerm>().Where(t => t.Input > 0).Select(t => t.Input).Distinct()
            .Count(n => v.Inputs.FirstOrDefault(r => r.Number == n && r.Digital != null)?.Board is { } b && b != role);

    private static int TermVar(PdmView v, PdmBoard q, PdmTerm t, Queue<int> free, string tag)
    {
        if (t.Input == 0) return t.Var;
        var row = v.Inputs.Single(r => r.Number == t.Input && r.Digital != null);
        if (row.Board == q.Role) return PdmFactoryDefaults.VarOf(q.Device, row.Digital!);
        // the same input of that board may already come in for another value: reuse its slot
        for (var s = 0; s < q.Device.CanInputs.Count; s++)
            if (PdmLinks.RoleOfSlot(v, q, s) is { Kind: PdmSlotKind.Link } r && r.Source.Role == row.Board && r.Bit == row.BoardInput - 1 && q.Device.CanInputs[s].TimeoutEnabled
                && q.Device.CanInputs[s].Timeout == PdmLinks.TimeoutMs)
                return PdmFactoryDefaults.CanInState(q.Device, s);
        var slot = free.Dequeue();
        PdmLinks.MakeTermSlot(v, q, slot, row, tag);
        return PdmFactoryDefaults.CanInState(q.Device, slot);
    }

    private static string Full(PdmModel m, string role, PdmResKind k, int need) =>
        $"{role} is full: this needs {need} {PdmEngine.KindName(k)}{(need == 1 ? "" : "s")}; {m.Use(role).Of(k).Text}. Nothing changed.";

    private static string? NeedFree(PdmModel m, string role, IReadOnlyDictionary<PdmResKind, int> need) =>
        need.Where(n => m.FreeOf(role, n.Key).Count < n.Value).Select(n => Full(m, role, n.Key, n.Value)).FirstOrDefault();

    // the functions that read var on q, other than the given resources (texts)
    public static IReadOnlyList<string> ReadersOf(PdmModel m, string role, int var, IEnumerable<PdmRes> except)
    {
        var ex = except.ToHashSet();
        return m.Refs.Where(x => x.From.Board == role && x.Var == var && !ex.Contains(x.From)).Select(x => $"{x.From.Text} ({x.Field})").Distinct().ToList();
    }

    // ---------------- counters ----------------

    public static IReadOnlyDictionary<PdmResKind, int> CounterCost(PdmView v, PdmCounterSpec s)
    {
        var c = new Dictionary<PdmResKind, int> { [PdmResKind.Counter] = 1 };
        if (OtherBoard(v, s.Board, [s.Up, s.Down, s.Reset]) is > 0 and var n) c[PdmResKind.CanInput] = n;
        return c;
    }

    // null = made; index = the counter (0-based)
    public static string? AddCounter(PdmView v, PdmCounterSpec s, out int index)
    {
        index = -1;
        if (Board(v, s.Board) is not { } q) return $"{s.Board} is not in this PDM.";
        foreach (var (t, w) in new[] { (s.Up, "up"), (s.Down, "down"), (s.Reset, "reset") })
            if (TermProblem(v, q, t, w) is { } bad) return bad;
        if (s.Min < 0 || s.Max > MaxCount || s.Max <= s.Min) return $"The counter runs from a minimum to a higher maximum, 0 to {MaxCount}.";
        if (s.HoldResetMs is < 0 or > 60000) return "Hold-to-reset is 0 (off) to 60000 ms.";
        var m = PdmModel.Build(v);
        if (NeedFree(m, q.Role, CounterCost(v, s)) is { } full) return full;
        var d = q.Device;
        var freeC = new Queue<int>(m.FreeOf(q.Role, PdmResKind.CanInput));
        index = m.FreeOf(q.Role, PdmResKind.Counter)[0];
        var c = d.Counters[index];
        PdmEngine.Reset(c);
        (c.Name, c.Enabled, c.IncInput) = ($"counter {index + 1}", true, TermVar(v, q, s.Up, freeC, "counter up"));
        if (s.Down != null) c.DecInput = TermVar(v, q, s.Down, freeC, "counter down");
        if (s.Reset != null) c.ResetInput = TermVar(v, q, s.Reset, freeC, "counter reset");
        (c.MinCount, c.MaxCount, c.WrapAround, c.IncEdge, c.DecEdge, c.ResetEdge) = (s.Min, s.Max, s.Wrap, InputEdge.Rising, InputEdge.Rising, InputEdge.Rising);
        (c.HoldToReset, c.ResetTime) = (s.HoldResetMs > 0, s.HoldResetMs > 0 ? s.HoldResetMs : 2000);
        return null;
    }

    // ---------------- math ----------------

    public static string? AddMath(PdmView v, PdmMathSpec s, out int index)
    {
        index = -1;
        if (Board(v, s.Board) is not { } q) return $"{s.Board} is not in this PDM.";
        var m = PdmModel.Build(v);
        var vals = PdmTriggers.ValueChoices(m, s.Board);
        if (vals.All(c => c.Var != s.A)) return $"Pick a value of {s.Board} for A.";
        if (s.B != 0 && vals.All(c => c.Var != s.B)) return $"Pick a value of {s.Board} for B, or a constant.";
        if (s.Factor == 0) return "The factor must not be 0.";
        if (NeedFree(m, q.Role, new Dictionary<PdmResKind, int> { [PdmResKind.Math] = 1 }) is { } full) return full;
        index = m.FreeOf(q.Role, PdmResKind.Math)[0];
        var x = q.Device.MathBlocks[index];
        PdmEngine.Reset(x);
        (x.Name, x.Enabled, x.Operation, x.InputA, x.InputB, x.ConstB, x.Factor, x.Offset) =
            ($"math {index + 1}", true, s.Op, s.A, s.B, s.ConstB, s.Factor, s.Offset);
        return null;
    }

    // ---------------- level as a signal ----------------

    public static string? AddLevel(PdmView v, string role, PdmThreshold th, out int var)
    {
        var = 0;
        if (Board(v, role) is not { } q) return $"{role} is not in this PDM.";
        var m = PdmModel.Build(v);
        if (PdmTriggers.ValueChoices(m, role).All(c => c.Var != th.Var)) return $"Pick a value of {role} for the level.";
        if (th.Above && th.Off >= th.On) return "Off must be below on (on at or above, off at or below).";
        if (!th.Above && th.Off <= th.On) return "Off must be above on (on at or below, off at or above).";
        if (NeedFree(m, role, new Dictionary<PdmResKind, int> { [PdmResKind.Condition] = 2, [PdmResKind.VirtualInput] = 1 }) is { } full) return full;
        var d = q.Device;
        var conds = m.FreeOf(role, PdmResKind.Condition);
        var (on, off) = (d.Conditions[conds[0]], d.Conditions[conds[1]]);
        (on.Name, on.Enabled, on.Input, on.Operator, on.Arg) = ("level on", true, th.Var, th.Above ? Operator.GreaterThanOrEqual : Operator.LessThanOrEqual, th.On);
        (off.Name, off.Enabled, off.Input, off.Operator, off.Arg) = ("level off", true, th.Var, th.Above ? Operator.LessThanOrEqual : Operator.GreaterThanOrEqual, th.Off);
        var vi = d.VirtualInputs[m.FreeOf(role, PdmResKind.VirtualInput)[0]];
        PdmEngine.Reset(vi);
        var self = PdmFactoryDefaults.VarOf(d, vi);
        (vi.Name, vi.Enabled, vi.Mode, vi.Not0, vi.Var0, vi.Cond0, vi.Not1, vi.Var1, vi.Cond1, vi.Not2, vi.Var2) =
            ("level", true, InputMode.Momentary, false, PdmFactoryDefaults.VarOf(d, on), Conditional.Or, false, self, Conditional.And, true, PdmFactoryDefaults.VarOf(d, off));
        var = self;
        return null;
    }

    // ---------------- values of another board ----------------

    // the cyclic signals of board p another board can read (not msg 37: the links' message)
    public static IReadOnlyList<DbcExport.Signal> RemoteSignals(PdmView v, string fromRole, out int[] ids)
    {
        var p = Board(v, fromRole);
        var list = new List<DbcExport.Signal>();
        var idl = new List<int>();
        if (p != null)
            foreach (var msg in DbcExport.Messages(new DbcBoard(p.Role, p.Device)).Where(x => x.MsgNumber != PdmLinks.StatusMsg))
                foreach (var s in msg.Signals.Where(s => s.Length > 1))
                {
                    list.Add(s);
                    idl.Add(msg.Id);
                }
        ids = idl.ToArray();
        return list;
    }

    // a value of board fromRole (by its signal name, e.g. "A1_AnalogInput1_Millivolts") on board role: 1 CAN input
    public static int AddRemoteValue(PdmView v, string role, string fromRole, string signal, out string? why)
    {
        why = null;
        if (role == fromRole) { why = "That value is on the same board: pick it directly."; return -1; }
        var sigs = RemoteSignals(v, fromRole, out var ids);
        var i = sigs.ToList().FindIndex(s => s.Name == signal);
        if (i < 0) { why = $"{fromRole} has no signal {signal}."; return -1; }
        var s = sigs[i];
        return PdmEcu.AddValueAt(v, role, $"{fromRole} {s.PdmName ?? s.Name}", ids[i], s.StartBit, s.Length, ByteOrder.LittleEndian, s.IsSigned,
            s.Factor, s.Offset, PdmLinks.TimeoutMs, allowPdmId: true, out why);
    }

    // ---------------- keypads ----------------

    // the IDs a board really uses: its base (config) .. base + 2 + 37 (msg 37), docs/car-can-dummy bus table 0x500-0x527
    public const int UsedIds = 2 + PdmLinks.StatusMsg + 1;
    private static bool Used(PdmBoard b, int id) => id >= b.Device.BaseId && id < b.Device.BaseId + UsedIds;

    // A BlinkMarine keypad (CANopen) sends on 0x180 / 0x280 / 0x380 / 0x480 / 0x580 / 0x700 + node and listens on
    // 0x200 / 0x300 / 0x400 / 0x500 / 0x600 + node (BlinkMarineKeypadDevice MessageId): none may be a PDM frame
    public static string? KeypadClash(PdmView v, int node)
    {
        if (node is < 1 or > 127) return "A keypad node ID is 1 to 127 (0x01-0x7F).";
        foreach (var off in KeypadOffsets)
            if (v.Boards.FirstOrDefault(b => Used(b, off + node)) is { } b)
            {
                var ok = Enumerable.Range(1, 127).FirstOrDefault(n => KeypadOffsets.All(o => v.Boards.All(x => !Used(x, o + n))));
                return $"Keypad node 0x{node:X2} uses ID 0x{off + node:X3}, inside {b.Role}'s block (0x{b.Device.BaseId:X3}-0x{b.Device.BaseId + UsedIds - 1:X3}): set the keypad to another node, e.g. 0x{ok:X2}.";
            }
        return null;
    }

    public static int AddKeypadButton(PdmView v, string role, int node, int button, out string? why)
    {
        why = KeypadClash(v, node);
        if (why != null) return -1;
        if (button is < 1 or > KeypadButtons) { why = $"Buttons are 1 to {KeypadButtons}."; return -1; }
        var q = Board(v, role);
        if (q == null) { why = $"{role} is not in this PDM."; return -1; }
        var m = PdmModel.Build(v);
        var free = m.FreeOf(role, PdmResKind.CanInput);
        if (free.Count == 0) { why = Full(m, role, PdmResKind.CanInput, 1); return -1; }
        var c = q.Device.CanInputs[free[0]];
        PdmLinks.SetSlot(c, $"keypad 0x{node:X2} button {button}", 0x180 + node, button - 1, Operator.Equal, 1.0, true);
        return free[0];
    }

    // ---------------- starter interlock ----------------

    // while crank is on, the given outputs (any board) are held off; replaces the interlock on every board
    public static string? SetStarter(PdmView v, PdmTerm crank, IReadOnlyCollection<int> outputs)
    {
        var rows = outputs.Select(n => v.Outputs.FirstOrDefault(o => o.Number == n)).ToList();
        if (rows.Any(r => r == null)) return "Pick outputs of this PDM.";
        if (rows.Any(r => PdmTriggers.IsFanOutput(r!))) return "The PDM's own fans are never shed.";
        foreach (var q in v.Boards)
            if (TermProblem(v, q, crank, "crank") is { } bad) return bad;
        var snaps = v.Boards.Select(b => PdmSnapshot.Take([b.Device])).ToList();
        foreach (var q in v.Boards)
        {
            var st = q.Device.StarterDisable;
            if (st == null) continue;
            var mine = rows.Where(r => r!.Board == q.Role).Select(r => r!.BoardOutput - 1).ToList();
            var old = st.Input;
            (st.Enabled, st.Input) = (false, 0);
            for (var i = 0; i < st.OutputsDisabled.Count; i++) st.OutputsDisabled[i] = false;
            FreeTermSlot(v, q, old);
            if (mine.Count == 0) continue;
            var m = PdmModel.Build(v);
            var free = new Queue<int>(m.FreeOf(q.Role, PdmResKind.CanInput));
            if (OtherBoard(v, q.Role, [crank]) > free.Count)
            {
                foreach (var s in snaps) s.Restore();
                return Full(m, q.Role, PdmResKind.CanInput, 1);
            }
            (st.Enabled, st.Input) = (true, TermVar(v, q, crank, free, "starter"));
            foreach (var i in mine) st.OutputsDisabled[i] = true;
        }
        return null;
    }

    // ---------------- master retry (P3) ----------------

    public static string? SetRetry(PdmView v, PdmTerm? input)
    {
        if (input != null)
            foreach (var q in v.Boards)
                if (TermProblem(v, q, input, "retry") is { } bad) return bad;
        var snaps = v.Boards.Select(b => PdmSnapshot.Take([b.Device])).ToList();
        foreach (var q in v.Boards)
        {
            if (q.Device.CustomPdm is not { } cp) continue;
            var old = cp.MasterRetryInput;
            cp.MasterRetryInput = 0;
            FreeTermSlot(v, q, old);
            if (input == null) continue;
            var m = PdmModel.Build(v);
            var free = new Queue<int>(m.FreeOf(q.Role, PdmResKind.CanInput));
            if (OtherBoard(v, q.Role, [input]) > free.Count)
            {
                foreach (var s in snaps) s.Restore();
                return Full(m, q.Role, PdmResKind.CanInput, 1);
            }
            cp.MasterRetryInput = TermVar(v, q, input, free, "master retry");
        }
        return null;
    }

    // a link-recipe slot made for a value / system function that nothing reads any more: fresh again
    private static void FreeTermSlot(PdmView v, PdmBoard q, int var)
    {
        var d = q.Device;
        if (var == 0 || StateOwner(d, var) is not CanInput c) return;
        var s = d.CanInputs.IndexOf(c);
        if (PdmLinks.RoleOfSlot(v, q, s) is { Kind: PdmSlotKind.Link } && !PdmEngine.IsRead(d, var)) PdmLinks.Reset(c);
    }

    // ---------------- CAN outputs ----------------

    public static string? CanOutProblem(PdmView v, PdmCanOutSpec s)
    {
        if (Board(v, s.Board) is not { } q) return $"{s.Board} is not in this PDM.";
        if (s.Id is < 1 or > 0x7FF) return "The frame ID must be a standard (11-bit) ID, 0x001 to 0x7FF.";
        if (PdmEcu.IsPdmId(v, s.Id)) return $"0x{s.Id:X3} is inside a PDM board's own ID block: pick a free ID (the car's CAN ID table).";
        if (s.Length is < 1 or > 32) return "A signal is 1 to 32 bits.";
        var lastBit = s.Order == ByteOrder.LittleEndian ? s.StartBit + s.Length - 1 : (s.StartBit / 8) * 8 + 7 + 8 * ((s.Length - 1 - s.StartBit % 8 + 7) / 8);
        if (s.StartBit is < 0 or > 63 || s.Order == ByteOrder.LittleEndian && lastBit > 63) return "The signal must fit in the 8 data bytes.";
        if (s.Factor == 0) return "The factor must not be 0.";
        if (s.IntervalMs is < 10 or > 60000) return "Send every 10 to 60000 ms.";
        if (q.Device.VarMap.All(e => e.VariableIndex != s.Var) || s.Var == 0) return $"Pick a value or flag of {s.Board} to send.";
        // overlapping bits of the same frame on this board
        foreach (var o in q.Device.CanOutputs.Where(o => o.Enabled && o.Id == s.Id && o.ByteOrder == ByteOrder.LittleEndian && s.Order == ByteOrder.LittleEndian))
            if (s.StartBit < o.StartBit + o.BitLength && o.StartBit < s.StartBit + s.Length)
                return $"Bits {s.StartBit}-{s.StartBit + s.Length - 1} of 0x{s.Id:X3} overlap a signal already sent there (bits {o.StartBit}-{o.StartBit + o.BitLength - 1}).";
        return null;
    }

    public static string? AddCanOut(PdmView v, PdmCanOutSpec s, out int index)
    {
        index = -1;
        if (CanOutProblem(v, s) is { } bad) return bad;
        var m = PdmModel.Build(v);
        if (NeedFree(m, s.Board, new Dictionary<PdmResKind, int> { [PdmResKind.CanOutput] = 1 }) is { } full) return full;
        index = m.FreeOf(s.Board, PdmResKind.CanOutput)[0];
        var c = Board(v, s.Board)!.Device.CanOutputs[index];
        (c.Name, c.Enabled, c.Id, c.StartBit, c.BitLength, c.ByteOrder, c.Signed) = ($"send 0x{s.Id:X3}", true, s.Id, s.StartBit, s.Length, s.Order, s.Signed);
        (c.Factor, c.Offset, c.Interval, c.Input, c.Bus) = (s.Factor, s.Offset, s.IntervalMs, s.Var, 0);
        return null;
    }

    // the open-load (undercurrent) flags of the board's 8 outputs as bits 0-7 of one frame: 8 CAN outputs
    public static string? AddOpenLoadFrame(PdmView v, string role, int id, int intervalMs)
    {
        if (Board(v, role) is not { } q) return $"{role} is not in this PDM.";
        var d = q.Device;
        var flags = d.Outputs.Select(o => d.VarMap.FirstOrDefault(e => ReferenceEquals(e.Owner, o) && e.PropertyName == "Undercurrent")?.VariableIndex).ToList();
        if (flags.Any(f => f == null)) return $"{role} has no open-load flags (PRO_FEATURES).";
        var m = PdmModel.Build(v);
        if (NeedFree(m, role, new Dictionary<PdmResKind, int> { [PdmResKind.CanOutput] = flags.Count }) is { } full) return full;
        var snap = PdmSnapshot.Take([d]);
        for (var i = 0; i < flags.Count; i++)
            if (AddCanOut(v, new PdmCanOutSpec(role, id, i, 1, flags[i]!.Value, IntervalMs: intervalMs), out _) is { } why)
            {
                snap.Restore();
                return why;
            }
        return null;
    }

    // ---------------- remove ----------------

    // null = removed (its parts fresh); refused while something else reads the value (nothing changed)
    public static string? Remove(PdmView v, PdmRes main)
    {
        var m = PdmModel.Build(v);
        if (All(m).FirstOrDefault(f => f.Main == main) is not { } f) return $"{main.Text} is not a /pdm value.";
        var q = Board(v, f.Board)!;
        var d = q.Device;
        if (f.Var != 0 && ReadersOf(m, f.Board, f.Var, f.Made) is { Count: > 0 } readers)
            return $"{main.Text} is used by {string.Join(", ", readers)}: change that first.";
        switch (f.Kind)
        {
            case PdmValueKind.Starter: SetStarter(v, PdmTerm.Of(PdmTriggers.AlwaysOnVar), []); return null;
            case PdmValueKind.Retry:
                var old = d.CustomPdm!.MasterRetryInput;
                d.CustomPdm.MasterRetryInput = 0;
                FreeTermSlot(v, q, old);
                return null;
        }
        foreach (var r in f.Made)
            switch (m.Fn(r))
            {
                case CanInput c: PdmLinks.Reset(c); break;
                case CanOutput c:
                    var fresh = new CanOutput(c.Number, "canOutput" + c.Number);
                    for (var i = 0; i < c.Params.Count; i++) c.Params[i].SetValue(fresh.Params[i].GetValue());
                    c.Name = fresh.Name;
                    break;
                case IDeviceFunction fn: PdmEngine.Reset(fn); break;
            }
        return null;
    }
}
