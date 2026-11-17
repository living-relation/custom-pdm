using System.Globalization;
using System.Text.RegularExpressions;
using domain.Devices;
using domain.Devices.Functions;
using domain.Enums;
using domain.Interfaces;

namespace domain.CustomPdm;

// custom-pdm one-PDM editor, phase 1: the trigger of each output, set on /pdm and written into the stock functions of
// the OUTPUT's board through the conflict engine (PdmEngine). Recipes (proven in firmware/sim s3_features.py F1-F4):
//   input           output trigger = the input                        (NOT: 1 virtual input "NOT a AND always on")
//   AND / OR / NOR  1 virtual input, 2-3 terms, NOT per term         (NOR = "NOT (a OR b [OR c])")
//   threshold       2 conditions (on at >= / <=, off at <= / >=) + 1 latch virtual input "(on OR itself) AND NOT off"
//                   (= the A2 fan recipe, S3 F2 "hysteresis")
//   + timer         1 timer wrapping the above: on-delay, off-delay, pulse (one-shot)          (S3 F3)
//   + flasher       1 flasher wrapping the above (after the timer): on / off ms                 (S3 F4)
//   other board     an input of another board is one CAN input on the output's board on that board's msg 37 (the
//                   PdmLinks 'off' recipe: bit of msg 37, Equal 1, time-out 1 s = off when the message stops)
// Ownership needs no PC-only state: a trigger is read back from the params (Decode), so it survives Read All, an app
// restart and a fresh project. A trigger is the editor's when its whole chain has one of the shapes above; anything
// else is shown in words but is "set by hand" and is only unhooked (never changed) when replaced. Replacing a
// trigger that is not the editor's own asks "already assigned. Overwrite?" first (g1). Set is all-or-nothing.
public enum PdmTriggerKind { None, Input, Logic, Threshold, Link, Hand }

public enum PdmLogicOp { And, Or, Nor }

public enum PdmTimerKind { None, OnDelay, OffDelay, Pulse }

// Input = a PDM digital input number (1-24, any board); 0 = Var, a variable of the output's own board
public record PdmTerm(int Input, int Var = 0, bool Not = false)
{
    public static PdmTerm In(int n, bool not = false) => new(n, 0, not);
    public static PdmTerm Of(int var, bool not = false) => new(0, var, not);
}

// Above: on at >= On, off at <= Off (Off below On). Below: on at <= On, off at >= Off (Off above On).
public record PdmThreshold(int Var, bool Above, double On, double Off);

public record PdmTriggerSpec(PdmTriggerKind Kind, IReadOnlyList<PdmTerm> Terms, PdmLogicOp Op = PdmLogicOp.And,
    PdmThreshold? Threshold = null, PdmTimerKind Timer = PdmTimerKind.None, int TimerMs = 1000,
    bool Flash = false, int FlashOnMs = 500, int FlashOffMs = 500)
{
    public static readonly PdmTriggerSpec None = new(PdmTriggerKind.None, []);
    public static PdmTriggerSpec Input(PdmTerm t) => new(PdmTriggerKind.Input, [t]);
    public static PdmTriggerSpec Logic(PdmLogicOp op, params PdmTerm[] t) => new(PdmTriggerKind.Logic, t, op);
    public static PdmTriggerSpec Level(PdmThreshold th) => new(PdmTriggerKind.Threshold, [], Threshold: th);
    public PdmTriggerSpec WithTimer(PdmTimerKind k, int ms) => this with { Timer = k, TimerMs = ms };
    public PdmTriggerSpec WithFlash(int onMs, int offMs) => this with { Flash = true, FlashOnMs = onMs, FlashOffMs = offMs };

    // value equality for the term list too (tests, "unchanged")
    public virtual bool Equals(PdmTriggerSpec? o) =>
        o is not null && Kind == o.Kind && Terms.SequenceEqual(o.Terms) && Op == o.Op && Threshold == o.Threshold
        && Timer == o.Timer && (Timer == PdmTimerKind.None || TimerMs == o.TimerMs)
        && Flash == o.Flash && (!Flash || (FlashOnMs, FlashOffMs) == (o.FlashOnMs, o.FlashOffMs));

    public override int GetHashCode() => HashCode.Combine(Kind, Terms.Count, Op, Threshold, Timer, Flash);
}

// Spec = null: not the editor's shape (Link with a loss mode other than off, or Hand). Made = what the editor made
// for it on the output's board (CAN inputs for other-board terms, virtual input, conditions, timer, flasher).
public record PdmTrigger(PdmOutputRow Out, PdmTriggerKind Kind, PdmTriggerSpec? Spec, string Words, IReadOnlyList<PdmRes> Made, PdmLink? Link)
{
    public bool Editor => Spec != null;
}

public record PdmChoice(int Var, string Text);

public static class PdmTriggers
{
    public const int AlwaysOnVar = 1;
    public const int MaxTimerMs = 600000, MaxFlashMs = 5000; // stock TimersGrid / FlashersGrid limits

    // ---------------- words ----------------

    private static readonly Regex DefaultName = new("^[a-zA-Z]+[0-9]+$");

    private static string Ms(int ms) => ms >= 1000 && ms % 100 == 0
        ? (ms / 1000.0).ToString("0.#", CultureInfo.InvariantCulture) + " s"
        : $"{ms} ms";

    private static string Num(double x) => x.ToString("0.###", CultureInfo.InvariantCulture);

    // a variable of board `role` in plain words
    public static string VarText(PdmModel m, string role, int var)
    {
        if (var == 0) return "nothing";
        if (var == AlwaysOnVar) return "always on";
        var q = m.Board(role);
        var e = q.Device.VarMap.FirstOrDefault(x => x.VariableIndex == var);
        if (e == null) return $"{role} variable {var} (missing)";
        if (e.Owner == null)
            return e.GetName() switch
            {
                "Temperature" => $"{role} board temperature (C)",
                "Battery Voltage" => $"{role} battery voltage (V)",
                "State" => $"{role} device state",
                var n => $"{role} {n}"
            };
        var first = PdmFactoryDefaults.VarOf(q.Device, e.Owner) == var;
        switch (e.Owner)
        {
            case DigitalInput di:
                var dn = PdmView.DigitalInputNumber(role, q.Device.DigitalInputs.IndexOf(di));
                return first ? $"IN{dn}" : $"IN{dn} {e.PropertyName.ToLowerInvariant()}";
            case AnalogInput:
                var an = PdmView.AnalogInputNumber(role);
                return e.PropertyName switch
                {
                    "Millivolts" => $"IN{an} voltage (mV)",
                    "Pos" => $"IN{an} rotary position",
                    "State" => $"IN{an} as a switch",
                    _ => $"IN{an} raw value"
                };
            case Output o:
                var on = PdmView.OutputNumber(role, q.Device.Outputs.IndexOf(o));
                return $"output {on} {e.PropertyName.ToLowerInvariant()}";
        }
        var r = m.ResOf(e.Owner);
        var name = e.GetName();
        var text = r?.Text ?? name;
        if (!string.IsNullOrWhiteSpace(name) && !DefaultName.IsMatch(name)) text += $" '{name}'";
        return first ? text : $"{text} {e.PropertyName.ToLowerInvariant()}";
    }

    private static string TermText(PdmModel m, string role, PdmTerm t) =>
        (t.Not ? "NOT " : "") + (t.Input > 0 ? $"IN{t.Input}" : VarText(m, role, t.Var));

    public static string Words(PdmModel m, string role, PdmTriggerSpec s)
    {
        var core = s.Kind switch
        {
            PdmTriggerKind.None => "none",
            PdmTriggerKind.Input => TermText(m, role, s.Terms[0]),
            PdmTriggerKind.Logic when s.Op == PdmLogicOp.Nor => $"NOT ({string.Join(" OR ", s.Terms.Select(t => TermText(m, role, t)))})",
            PdmTriggerKind.Logic => string.Join(s.Op == PdmLogicOp.And ? " AND " : " OR ", s.Terms.Select(t => TermText(m, role, t))),
            PdmTriggerKind.Threshold when s.Threshold is { } th => th.Above
                ? $"{VarText(m, role, th.Var)} on at {Num(th.On)} or more, off at {Num(th.Off)} or less"
                : $"{VarText(m, role, th.Var)} on at {Num(th.On)} or less, off at {Num(th.Off)} or more",
            _ => "?"
        };
        if (s.Kind == PdmTriggerKind.None) return core;
        if (s.Timer != PdmTimerKind.None)
            core += s.Timer switch
            {
                PdmTimerKind.OnDelay => $", on-delay {Ms(s.TimerMs)}",
                PdmTimerKind.OffDelay => $", off-delay {Ms(s.TimerMs)}",
                _ => $", pulse {Ms(s.TimerMs)}"
            };
        if (s.Flash) core += $", flashing {s.FlashOnMs} / {s.FlashOffMs} ms";
        return core;
    }

    // ---------------- decode (params -> trigger) ----------------

    private static PdmBoard BoardOf(PdmView v, PdmOutputRow o) => v.Boards.Single(b => ReferenceEquals(b.Device, o.Device));

    public static bool IsFanOutput(PdmOutputRow o) => o.Board == "A2" && o.BoardOutput - 1 == PdmFactoryDefaults.FanOutput;

    // the function whose FIRST (state) variable is var, or null
    private static IDeviceFunction? StateOwner(FwDevice d, int var)
    {
        if (var <= AlwaysOnVar) return null;
        var owner = d.VarMap.FirstOrDefault(x => x.VariableIndex == var)?.Owner;
        return owner != null && PdmFactoryDefaults.VarOf(d, owner) == var ? owner : null;
    }

    private static PdmTimerKind? TimerKind(TimerMode m) => m switch
    {
        TimerMode.OnDelay => PdmTimerKind.OnDelay,
        TimerMode.OffDelay => PdmTimerKind.OffDelay,
        TimerMode.PulseOneShot => PdmTimerKind.Pulse,
        _ => null
    };

    private static TimerMode Mode(PdmTimerKind k) => k switch
    {
        PdmTimerKind.OnDelay => TimerMode.OnDelay,
        PdmTimerKind.OffDelay => TimerMode.OffDelay,
        _ => TimerMode.PulseOneShot
    };

    // a term: an input of this board, an input of another board through a link slot ('off' recipe), or any variable
    private static PdmTerm Term(PdmModel m, PdmBoard q, int var, bool not, List<PdmRes> made)
    {
        var d = q.Device;
        switch (StateOwner(d, var))
        {
            case DigitalInput di when PdmView.DigitalInputNumber(q.Role, d.DigitalInputs.IndexOf(di)) is { } n:
                return PdmTerm.In(n, not);
            case CanInput ci:
                var s = d.CanInputs.IndexOf(ci);
                if (ci.TimeoutEnabled && PdmLinks.RoleOfSlot(m.View, q, s) is { Kind: PdmSlotKind.Link } r
                    && PdmView.DigitalInputNumber(r.Source.Role, r.Bit) is { } pn)
                {
                    made.Add(new PdmRes(q.Role, PdmResKind.CanInput, s));
                    return PdmTerm.In(pn, not);
                }
                break;
        }
        return PdmTerm.Of(var, not);
    }

    private static PdmTriggerSpec? Core(PdmModel m, PdmBoard q, int x, List<PdmRes> made)
    {
        var d = q.Device;
        switch (StateOwner(d, x))
        {
            case DigitalInput:
            case CanInput:
                var t = Term(m, q, x, false, made);
                return t.Input > 0 ? PdmTriggerSpec.Input(t) : null;
            case VirtualInput vi when vi is { Enabled: true, Mode: InputMode.Momentary }:
            {
                var self = PdmFactoryDefaults.VarOf(d, vi);
                var k = d.VirtualInputs.IndexOf(vi);
                var me = new PdmRes(q.Role, PdmResKind.VirtualInput, k);
                // threshold: (on OR itself) AND NOT off, on / off = conditions on the same value with opposite operators
                if (vi is { Not0: false, Cond0: Conditional.Or, Not1: false, Cond1: Conditional.And, Not2: true } && vi.Var1 == self
                    && StateOwner(d, vi.Var0) is Condition a && StateOwner(d, vi.Var2) is Condition b && !ReferenceEquals(a, b)
                    && a is { Enabled: true } && b is { Enabled: true } && a.Input != 0 && a.Input == b.Input
                    && (a.Operator, b.Operator) is (Operator.GreaterThanOrEqual, Operator.LessThanOrEqual) or (Operator.LessThanOrEqual, Operator.GreaterThanOrEqual))
                {
                    made.Add(me);
                    made.Add(new PdmRes(q.Role, PdmResKind.Condition, d.Conditions.IndexOf(a)));
                    made.Add(new PdmRes(q.Role, PdmResKind.Condition, d.Conditions.IndexOf(b)));
                    return PdmTriggerSpec.Level(new PdmThreshold(a.Input, a.Operator == Operator.GreaterThanOrEqual, a.Arg, b.Arg));
                }
                if (vi.Var0 == 0 || vi.Var1 == 0 || vi.Var0 == self || vi.Var1 == self || vi.Var2 == self) return null;
                // NOT a single input: NOT a AND always on
                if (vi is { Not0: true, Cond0: Conditional.And, Not1: false, Var2: 0 } && vi.Var1 == AlwaysOnVar)
                {
                    var tn = Term(m, q, vi.Var0, true, made);
                    made.Add(me);
                    return PdmTriggerSpec.Input(tn);
                }
                PdmLogicOp? op = (vi.Var2 == 0, vi.Cond0, vi.Cond1) switch
                {
                    (true, Conditional.And, _) => PdmLogicOp.And,
                    (true, Conditional.Or, _) => PdmLogicOp.Or,
                    (true, Conditional.Nor, _) => PdmLogicOp.Nor,
                    (false, Conditional.And, Conditional.And) => PdmLogicOp.And,
                    (false, Conditional.Or, Conditional.Or) => PdmLogicOp.Or,
                    (false, Conditional.Or, Conditional.Nor) => PdmLogicOp.Nor,
                    _ => null
                };
                if (op == null) return null;
                var terms = new List<PdmTerm> { Term(m, q, vi.Var0, vi.Not0, made), Term(m, q, vi.Var1, vi.Not1, made) };
                if (vi.Var2 != 0) terms.Add(Term(m, q, vi.Var2, vi.Not2, made));
                made.Add(me);
                return PdmTriggerSpec.Logic(op.Value, terms.ToArray());
            }
        }
        return null;
    }

    public static PdmTrigger Decode(PdmModel m, PdmOutputRow o)
    {
        var v = m.View;
        var q = BoardOf(v, o);
        var d = o.Device;
        if (o.Output.Input == 0) return new PdmTrigger(o, PdmTriggerKind.None, PdmTriggerSpec.None, "none", [], null);
        if (IsFanOutput(o)) return new PdmTrigger(o, PdmTriggerKind.Hand, null, "the fan logic (hottest board temperature)", [], null);
        var link = PdmLinks.LinkOf(v, o);
        if (link is { Loss: not (null or PdmLinkLoss.Off) } || link is { OldRecipe: true })
            return new PdmTrigger(o, PdmTriggerKind.Link, null, $"IN{link.In.Number} (link: {link.LossText})", [], link);

        var made = new List<PdmRes>();
        var x = o.Output.Input;
        var spec = default(PdmTriggerSpec);
        var (flash, fOn, fOff, tk, tms) = (false, 0, 0, PdmTimerKind.None, 0);
        if (StateOwner(d, x) is Flasher f && f is { Enabled: true, Single: false })
        {
            (flash, fOn, fOff) = (true, f.OnTime, f.OffTime);
            made.Add(new PdmRes(q.Role, PdmResKind.Flasher, d.Flashers.IndexOf(f)));
            x = f.Input;
        }
        if (StateOwner(d, x) is DeviceTimer t && t is { Enabled: true, ResetInput: 0 } && TimerKind(t.Mode) is { } k)
        {
            (tk, tms) = (k, t.Time);
            made.Add(new PdmRes(q.Role, PdmResKind.Timer, d.Timers.IndexOf(t)));
            x = t.Input;
        }
        if (Core(m, q, x, made) is { } core)
        {
            spec = core with { Timer = tk, TimerMs = tk == PdmTimerKind.None ? 1000 : tms, Flash = flash,
                FlashOnMs = flash ? fOn : 500, FlashOffMs = flash ? fOff : 500 };
            return new PdmTrigger(o, spec.Kind, spec, Words(m, q.Role, spec), made, link);
        }
        return new PdmTrigger(o, PdmTriggerKind.Hand, null, $"{VarText(m, q.Role, o.Output.Input)} (set by hand)", [], null);
    }

    public static PdmTrigger Of(PdmModel m, int output) => m.Triggers.Single(t => t.Out.Number == output);

    // the made resources only this trigger reads (it may free them)
    private static IReadOnlyList<PdmRes> Exclusive(PdmModel m, PdmTrigger t)
    {
        var outRes = m.ResOf(t.Out.Output);
        var mine = t.Made.ToHashSet();
        return t.Made.Where(r => m.RefsTo(r).All(x => mine.Contains(x.From) || x.From == outRes)
                                 && m.ClaimOf(r) is { Kind: PdmClaimKind.Trigger } c && c.Output == t.Out.Number).ToList();
    }

    private static bool IsOwn(PdmModel m, PdmTrigger t) => t.Editor && Exclusive(m, t).Count == t.Made.Count;

    // ---------------- choices for the editor ----------------

    // on / off signals of the output's board other than its inputs (those are picked as IN1-24): CAN inputs set by
    // hand (e.g. ECU bits), keypad buttons, the analog input as a switch, conditions set by hand, other outputs
    public static IReadOnlyList<PdmChoice> SignalChoices(PdmModel m, string role)
    {
        var q = m.Board(role);
        var list = new List<PdmChoice> { new(AlwaysOnVar, "always on") };
        foreach (var e in q.Device.VarMap.Where(e => e.DataType == "bool" && e.Owner != null))
        {
            var r = m.ResOf(e.Owner!);
            var ok = e.Owner switch
            {
                CanInput or Condition => r != null && m.ClaimOf(r).Kind == PdmClaimKind.Hand,
                AnalogInput or Output => true,
                domain.Devices.Functions.Keypad.KeypadMaster k => k.Enabled,
                _ => false
            };
            if (ok) list.Add(new PdmChoice(e.VariableIndex, VarText(m, role, e.VariableIndex)));
        }
        return list;
    }

    // numbers of the output's board for a threshold: battery voltage, board temperature, analog input, CAN input
    // values set by hand (e.g. ECU coolant temperature), math blocks, counters
    public static IReadOnlyList<PdmChoice> ValueChoices(PdmModel m, string role)
    {
        var q = m.Board(role);
        var list = new List<PdmChoice>();
        foreach (var e in q.Device.VarMap.Where(e => e.DataType is "float" or "int"))
        {
            var ok = e.Owner switch
            {
                null => e.GetName() is "Battery Voltage" or "Temperature",
                AnalogInput => e.PropertyName is "Millivolts" or "Pos",
                CanInput c => e.PropertyName == "Value" && m.ResOf(c) is { } r && m.ClaimOf(r).Kind == PdmClaimKind.Hand,
                MathBlock or Counter => true,
                _ => false
            };
            if (ok) list.Add(new PdmChoice(e.VariableIndex, VarText(m, role, e.VariableIndex)));
        }
        return list;
    }

    // ---------------- cost ----------------

    public static IReadOnlyDictionary<PdmResKind, int> Cost(PdmView v, string role, PdmTriggerSpec s)
    {
        var c = new Dictionary<PdmResKind, int>();
        void Add(PdmResKind k, int n = 1) { if (n > 0) c[k] = c.GetValueOrDefault(k) + n; }
        var other = s.Terms.Count(t => t.Input > 0 && v.Inputs.FirstOrDefault(r => r.Number == t.Input && r.Digital != null)?.Board is { } b && b != role);
        Add(PdmResKind.CanInput, other);
        switch (s.Kind)
        {
            case PdmTriggerKind.Input when s.Terms[0].Not:
            case PdmTriggerKind.Logic:
                Add(PdmResKind.VirtualInput);
                break;
            case PdmTriggerKind.Threshold:
                Add(PdmResKind.Condition, 2);
                Add(PdmResKind.VirtualInput);
                break;
        }
        if (s.Kind != PdmTriggerKind.None && s.Timer != PdmTimerKind.None) Add(PdmResKind.Timer);
        if (s.Kind != PdmTriggerKind.None && s.Flash) Add(PdmResKind.Flasher);
        return c;
    }

    public static string CostText(IReadOnlyDictionary<PdmResKind, int> cost) => cost.Count == 0
        ? "nothing (the output reads the input directly)"
        : string.Join(", ", cost.Select(k => $"{k.Value} {PdmEngine.KindName(k.Key)}{(k.Value == 1 ? "" : "s")}"));

    // ---------------- set ----------------

    private static string What(PdmOutputRow o) => $"Output {o.Number} ({o.Board} OUT{o.BoardOutput})";

    // why this output's trigger cannot be set here, or null
    public static string? Unsettable(PdmOutputRow o)
    {
        if (IsFanOutput(o)) return $"{What(o)} runs the fans: its trigger is the fan logic (PDM settings).";
        if (o.Output.PrimaryOutput >= 0) return $"{What(o)} is paired: it follows {o.Board} OUT{o.Output.PrimaryOutput + 1}.";
        return null;
    }

    public static string? Problem(PdmModel m, PdmOutputRow o, PdmTriggerSpec s)
    {
        var v = m.View;
        var role = o.Board;
        var d = o.Device;
        bool IsBool(int var) => var == AlwaysOnVar || d.VarMap.FirstOrDefault(e => e.VariableIndex == var) is { DataType: "bool" };
        switch (s.Kind)
        {
            case PdmTriggerKind.None:
                return null;
            case PdmTriggerKind.Input when s.Terms.Count != 1:
                return "A single input has exactly one term.";
            case PdmTriggerKind.Logic when s.Terms.Count is < 2 or > 3:
                return "AND / OR / NOR take 2 or 3 terms.";
            case PdmTriggerKind.Threshold when s.Threshold is not { } th:
                return "Pick the value for the threshold.";
            case PdmTriggerKind.Threshold:
                var t = s.Threshold!;
                if (!ValueChoices(m, role).Any(c => c.Var == t.Var)) return $"Pick a value of {role} for the threshold.";
                if (t.Above && t.Off >= t.On) return "Off must be below on (on at or above, off at or below).";
                if (!t.Above && t.Off <= t.On) return "Off must be above on (on at or below, off at or above).";
                break;
            case PdmTriggerKind.Link or PdmTriggerKind.Hand:
                return "Links are set on the Links panel; hand-made triggers on the Advanced screen.";
        }
        foreach (var term in s.Terms)
        {
            if (term.Input > 0 && v.Inputs.All(r => r.Number != term.Input || r.Digital == null))
                return $"IN{term.Input} is not a digital input of this PDM (1-24, its board must be in the project).";
            if (term.Input == 0 && !IsBool(term.Var)) return $"Pick an on / off signal of {role} or an input IN1-24.";
        }
        if (s.Terms.Select(x => (x.Input, x.Var)).Distinct().Count() != s.Terms.Count) return "Each term must be a different signal.";
        if (s.Timer != PdmTimerKind.None && s.TimerMs is < 1 or > MaxTimerMs) return $"The timer time must be 1 to {MaxTimerMs} ms.";
        if (s.Flash && (s.FlashOnMs is < 1 or > MaxFlashMs || s.FlashOffMs is < 1 or > MaxFlashMs)) return $"Flash on / off times must be 1 to {MaxFlashMs} ms.";
        return null;
    }

    // The output's current trigger, when setting a new one would replace something that is not this editor's own
    // trigger of this output: the text for "already assigned. Overwrite?" (g1). null = free, or its own trigger.
    public static string? Conflict(PdmView v, int output)
    {
        var m = PdmModel.Build(v);
        var t = m.Triggers.FirstOrDefault(x => x.Out.Number == output);
        if (t == null || t.Kind == PdmTriggerKind.None) return null;
        if (t.Link is { CrossBoard: true } && t.Editor) return null; // the 'off' link = this editor's other-board input
        if (IsOwn(m, t)) return null;
        var why = t.Editor ? " It shares parts with another output's trigger or with hand-made settings." : "";
        return $"{What(t.Out)} is already assigned to {t.Words}.{why}";
    }

    // Unhook output's trigger: a link is removed (PdmLinks), the editor's own parts go back to fresh-board values,
    // anything else is only unhooked (never changed). The PC model only.
    public static void Release(PdmView v, PdmOutputRow o)
    {
        var m = PdmModel.Build(v);
        var t = m.Triggers.Single(x => ReferenceEquals(x.Out.Output, o.Output));
        if (t.Link is { CrossBoard: true })
        {
            PdmLinks.Remove(v, o.Number);
            return;
        }
        if (t.Editor)
            foreach (var r in Exclusive(m, t))
                PdmEngine.Reset((IDeviceFunction)m.Fn(r));
        o.Output.Input = 0;
    }

    // null = set on the PC (Write All sends it); else why not (nothing changed). overwrite: replace a trigger that
    // Conflict reports (the UI asked first).
    public static string? Set(PdmView v, int output, PdmTriggerSpec spec, bool overwrite = false)
    {
        var o = v.Outputs.FirstOrDefault(r => r.Number == output);
        if (o == null) return $"Output {output} is not in this PDM (1-24, its board must be in the project).";
        if (Unsettable(o) is { } no) return no;
        if (Problem(PdmModel.Build(v), o, spec) is { } bad) return bad;
        if (!overwrite && Conflict(v, output) is { } taken) return taken;

        var q = BoardOf(v, o);
        var restore = PdmSnapshot.Take([q.Device]);
        Release(v, o);
        if (spec.Kind == PdmTriggerKind.None) return null;
        if (Write(v, q, o, spec) is { } why)
        {
            restore.Restore();
            return why;
        }
        return null;
    }

    private static string? Write(PdmView v, PdmBoard q, PdmOutputRow o, PdmTriggerSpec s)
    {
        var d = q.Device;
        var m = PdmModel.Build(v);
        var need = Cost(v, q.Role, s);
        var free = PdmModel.Allocatable.ToDictionary(k => k, k => new Queue<int>(m.FreeOf(q.Role, k)));
        var short_ = need.Where(n => free[n.Key].Count < n.Value).ToList();
        if (short_.Count > 0)
        {
            var use = m.Use(q.Role);
            return $"{q.Role} is full: this trigger needs {CostText(need)}; {q.Role} has " +
                   string.Join(", ", short_.Select(n => $"{free[n.Key].Count} {PdmEngine.KindName(n.Key)}{(free[n.Key].Count == 1 ? "" : "s")} free " +
                                                         $"({UseText(use.Of(n.Key))})")) +
                   ". Nothing changed. Free some on this board (other triggers, links, Advanced) or pick a simpler trigger.";
        }
        var tag = $"OUT{o.BoardOutput} trigger";

        int TermVar(PdmTerm t)
        {
            if (t.Input == 0) return t.Var;
            var row = v.Inputs.Single(r => r.Number == t.Input && r.Digital != null);
            if (row.Board == q.Role) return PdmFactoryDefaults.VarOf(d, row.Digital!);
            var slot = free[PdmResKind.CanInput].Dequeue();
            PdmLinks.MakeTermSlot(v, q, slot, row, tag);
            return PdmFactoryDefaults.CanInState(d, slot);
        }

        VirtualInput NewVi(string name)
        {
            var vi = d.VirtualInputs[free[PdmResKind.VirtualInput].Dequeue()];
            PdmEngine.Reset(vi);
            (vi.Name, vi.Enabled, vi.Mode) = (name, true, InputMode.Momentary);
            return vi;
        }

        int x;
        switch (s.Kind)
        {
            case PdmTriggerKind.Input:
                var t0 = s.Terms[0];
                x = TermVar(t0);
                if (t0.Not)
                {
                    var vi = NewVi($"{tag} (NOT)");
                    (vi.Not0, vi.Var0, vi.Cond0, vi.Not1, vi.Var1, vi.Cond1, vi.Var2) = (true, x, Conditional.And, false, AlwaysOnVar, Conditional.And, 0);
                    x = PdmFactoryDefaults.VarOf(d, vi);
                }
                break;
            case PdmTriggerKind.Logic:
            {
                var vars = s.Terms.Select(TermVar).ToList();
                var vi = NewVi($"{tag} ({s.Op.ToString().ToUpperInvariant()})");
                var three = vars.Count == 3;
                var (c0, c1) = (s.Op, three) switch
                {
                    (PdmLogicOp.And, _) => (Conditional.And, Conditional.And),
                    (PdmLogicOp.Or, _) => (Conditional.Or, Conditional.Or),
                    (PdmLogicOp.Nor, false) => (Conditional.Nor, Conditional.And),
                    _ => (Conditional.Or, Conditional.Nor)
                };
                (vi.Not0, vi.Var0, vi.Cond0, vi.Not1, vi.Var1, vi.Cond1) = (s.Terms[0].Not, vars[0], c0, s.Terms[1].Not, vars[1], c1);
                (vi.Not2, vi.Var2) = three ? (s.Terms[2].Not, vars[2]) : (false, 0);
                x = PdmFactoryDefaults.VarOf(d, vi);
                break;
            }
            case PdmTriggerKind.Threshold:
            {
                var th = s.Threshold!;
                var on = d.Conditions[free[PdmResKind.Condition].Dequeue()];
                var off = d.Conditions[free[PdmResKind.Condition].Dequeue()];
                (on.Name, on.Enabled, on.Input, on.Operator, on.Arg) = ($"{tag} on", true, th.Var, th.Above ? Operator.GreaterThanOrEqual : Operator.LessThanOrEqual, th.On);
                (off.Name, off.Enabled, off.Input, off.Operator, off.Arg) = ($"{tag} off", true, th.Var, th.Above ? Operator.LessThanOrEqual : Operator.GreaterThanOrEqual, th.Off);
                var vi = NewVi($"{tag} (latch)");
                var self = PdmFactoryDefaults.VarOf(d, vi);
                (vi.Not0, vi.Var0, vi.Cond0, vi.Not1, vi.Var1, vi.Cond1, vi.Not2, vi.Var2) =
                    (false, PdmFactoryDefaults.VarOf(d, on), Conditional.Or, false, self, Conditional.And, true, PdmFactoryDefaults.VarOf(d, off));
                x = self;
                break;
            }
            default:
                return "Unknown trigger.";
        }
        if (s.Timer != PdmTimerKind.None)
        {
            var tm = d.Timers[free[PdmResKind.Timer].Dequeue()];
            PdmEngine.Reset(tm);
            (tm.Name, tm.Enabled, tm.Input, tm.ResetInput, tm.Mode, tm.Time) = ($"{tag} ({s.Timer})", true, x, 0, Mode(s.Timer), s.TimerMs);
            x = PdmFactoryDefaults.VarOf(d, tm);
        }
        if (s.Flash)
        {
            var fl = d.Flashers[free[PdmResKind.Flasher].Dequeue()];
            PdmEngine.Reset(fl);
            (fl.Name, fl.Enabled, fl.Input, fl.OnTime, fl.OffTime, fl.Single) = ($"{tag} (flash)", true, x, s.FlashOnMs, s.FlashOffMs, false);
            x = PdmFactoryDefaults.VarOf(d, fl);
        }
        o.Output.Input = x;
        return null;
    }

    private static string UseText(PdmKindUse u)
    {
        var parts = new List<string>();
        if (u.Triggers > 0) parts.Add($"{u.Triggers} by triggers");
        if (u.Links > 0) parts.Add($"{u.Links} by links");
        if (u.Reserved > 0) parts.Add($"{u.Reserved} reserved");
        if (u.Hand > 0) parts.Add($"{u.Hand} set by hand");
        return $"{u.Used} of {u.Total} in use" + (parts.Count > 0 ? ": " + string.Join(", ", parts) : "");
    }
}
