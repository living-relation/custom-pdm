using domain.Devices;
using domain.Devices.Functions;
using domain.Devices.Functions.Keypad;
using domain.Enums;
using domain.Interfaces;
using domain.Models;

namespace domain.CustomPdm;

// custom-pdm one-PDM editor, phase 1 (DECISIONS 2026-11-16 "UI treats A1, A2, B as ONE PDM", g1, p1 / p3): the
// conflict engine. ONE model of what reads what on each board, who owns each resource, and what is wrong with it.
// Everything that changes board settings from /pdm (triggers, links) and from the Advanced (per board) screen goes
// through it:
// - Resources: every function of a board (inputs, CAN inputs / outputs, virtual inputs, conditions, timers,
//   counters, flashers, math blocks, outputs incl. their PWM duty input, keypads, wiper, starter block, the device
//   block). References: every variable a function reads (its "input" fields).
// - Claims (owners) of the allocatable kinds (CAN inputs / outputs, virtual inputs, conditions, timers, counters,
//   flashers, math blocks): Reserved (A2 fan logic: CAN inputs 25-28, conditions FAN_COND0 / +1, virtual inputs
//   12-14; load-shed example on every board: its 4 conditions and virtual inputs 15-16), Link / Shared (PdmLinks w1
//   recipe), Trigger (made by the /pdm trigger editor for ONE output, PdmTriggers), Hand (anything else in use) or
//   Free (fresh-board values and nothing reads it). Order: Reserved, links in use, triggers, unused link slots.
// - Problems: an output driven twice, a resource used by two owners, a reference to a disabled / missing resource,
//   a link slot changed by hand, a reserved slot touched.
// - Edit check (Advanced screen): an edit that changes a claimed resource or replaces an output's trigger is
//   "X is already assigned to Y. Overwrite?"; new problems are listed with it; critical settings (base ID, CAN bit
//   rate, critical temperature, exempt outputs) are refused there (they change only on /pdm with Unlock, PdmCritical).
// Numbers count from 0 (param index); texts show them from 1.
public enum PdmResKind
{
    DigitalInput, AnalogInput, CanInput, VirtualInput, Condition, Timer, Counter, Flasher, Math, CanOutput, Output,
    Keypad, Wiper, Starter, Device,
    Table // PRO_FEATURES T1 lookup table (0x7E00 + n, CustomPdmPro.cs); its output var is "Table n" (no owner in the map)
}

public record PdmRes(string Board, PdmResKind Kind, int Index)
{
    public string Text => Kind switch
    {
        PdmResKind.Output => PdmView.OutputNumber(Board, Index) is { } n ? $"output {n} ({Board} OUT{Index + 1})" : $"{Board} OUT{Index + 1}",
        PdmResKind.DigitalInput => PdmView.DigitalInputNumber(Board, Index) is { } n ? $"IN{n} ({Board} IN{Index + 1})" : $"{Board} IN{Index + 1}",
        PdmResKind.Device => $"{Board} device settings",
        PdmResKind.Wiper => $"{Board} wiper",
        PdmResKind.Starter => $"{Board} starter block",
        _ => $"{Board} {PdmEngine.KindName(Kind)} {Index + 1}"
    };
}

// From reads variable Var in its field Field. To = the resource that owns Var (null: a system variable, or Missing)
public record PdmRef(PdmRes From, string Field, int Var, PdmRes? To, bool Missing);

public enum PdmClaimKind { Free, Reserved, Link, Shared, Trigger, Hand }

// Output = the PDM output number for a Trigger claim
// Outputs = the outputs of a function of several outputs (editor2: turn signals, wiper), e.g. ",9,11,"
public record PdmClaim(PdmClaimKind Kind, string Text, int Output = 0, string? Outputs = null);

public enum PdmProblemKind { OutputDrivenTwice, TwoOwners, MissingRef, LinkSlotByHand, ReservedTouched }

public record PdmProblem(PdmProblemKind Kind, string Text);

// Resource use of one kind on one board (allocatable kinds only)
public record PdmKindUse(PdmResKind Kind, int Total, int Free, int Reserved, int Links, int Triggers, int Hand)
{
    public int Used => Total - Free;
    public string Text => $"{PdmEngine.KindName(Kind)}s {Used} of {Total} used, {Free} free";
}

public record PdmBoardUse(string Board, IReadOnlyList<PdmKindUse> Kinds)
{
    public PdmKindUse Of(PdmResKind k) => Kinds.Single(x => x.Kind == k);
    public string Summary => $"{Board}: " + string.Join("; ", Kinds.Select(k => k.Text));
}

public record PdmEditCheck(IReadOnlyList<string> Assigned, IReadOnlyList<PdmProblem> NewProblems, IReadOnlyList<string> Critical)
{
    public bool Clean => Assigned.Count == 0 && NewProblems.Count == 0 && Critical.Count == 0;
    public static readonly PdmEditCheck None = new([], [], []);
}

// All config values (and the names of the functions the editors name) of the boards of a view, to undo an edit
public sealed class PdmSnapshot
{
    private readonly List<(DeviceParameter P, object V)> _vals = [];
    private readonly List<(Action<string> Set, string Name)> _names = [];

    public static PdmSnapshot Take(PdmView v) => Take(v.Boards.Select(b => b.Device));

    public static PdmSnapshot Take(IEnumerable<FwDevice> devices)
    {
        var s = new PdmSnapshot();
        foreach (var d in devices)
        {
            foreach (var p in d.Params) s._vals.Add((p, p.GetValue()));
            foreach (var f in d.CanInputs) s._names.Add((n => f.Name = n, f.Name));
            foreach (var f in d.VirtualInputs) s._names.Add((n => f.Name = n, f.Name));
            foreach (var f in d.Conditions) s._names.Add((n => f.Name = n, f.Name));
            foreach (var f in d.Timers) s._names.Add((n => f.Name = n, f.Name));
            foreach (var f in d.Flashers) s._names.Add((n => f.Name = n, f.Name));
            foreach (var f in d.Outputs) s._names.Add((n => f.Name = n, f.Name));
        }
        return s;
    }

    public void Restore()
    {
        foreach (var (p, v) in _vals)
            if (!Equals(p.GetValue(), v)) p.SetValue(v);
        foreach (var (set, n) in _names) set(n);
    }

    // params whose value differs from the snapshot now
    public IReadOnlyList<(DeviceParameter P, object Before, object Now)> Changed() =>
        _vals.Select(x => (x.P, x.V, Now: x.P.GetValue())).Where(x => !Equals(x.V, x.Now)).Select(x => (x.P, x.V, x.Now)).ToList();
}

public sealed class PdmModel
{
    public PdmView View { get; }
    public IReadOnlyList<PdmRef> Refs => _refs;
    public IReadOnlyDictionary<PdmRes, PdmClaim> Claims => _claims;
    public IReadOnlyList<PdmProblem> Problems => _problems;
    public IReadOnlyList<PdmTrigger> Triggers => _triggers;

    private readonly Dictionary<object, PdmRes> _resOf = new(ReferenceEqualityComparer.Instance);
    private readonly Dictionary<PdmRes, object> _fnOf = [];
    private readonly Dictionary<DeviceParameter, PdmRes> _resOfParam = new(ReferenceEqualityComparer.Instance);
    private readonly List<PdmRef> _refs = [];
    private readonly Dictionary<PdmRes, PdmClaim> _claims = [];
    private readonly List<PdmProblem> _problems = [];
    private readonly List<PdmTrigger> _triggers = [];

    private PdmModel(PdmView v) => View = v;

    public static PdmModel Build(PdmView v)
    {
        var m = new PdmModel(v);
        foreach (var q in v.Boards) m.Index(q);
        foreach (var q in v.Boards) m.CollectRefs(q);
        m.MakeClaims();
        m.FindProblems();
        return m;
    }

    public PdmBoard Board(string role) => View.Boards.Single(b => b.Role == role);
    public object Fn(PdmRes r) => _fnOf[r];
    public PdmRes? ResOf(object fn) => _resOf.GetValueOrDefault(fn);
    public PdmRes? ResOfParam(DeviceParameter p) => _resOfParam.GetValueOrDefault(p);
    public PdmClaim ClaimOf(PdmRes r) => _claims.GetValueOrDefault(r) ?? new PdmClaim(PdmClaimKind.Hand, "in use");

    // the resource that owns variable var of board q (null: a system variable such as "Always On", or not in the map)
    public PdmRes? VarRes(PdmBoard q, int var) =>
        q.Device.VarMap.FirstOrDefault(x => x.VariableIndex == var) is not { } e ? null : e.Owner is { } o ? ResOf(o) : TableOfVar(q, e);

    public IEnumerable<PdmRef> RefsTo(PdmRes r) => _refs.Where(x => x.To == r);

    public bool IsFree(PdmRes r) => _claims.TryGetValue(r, out var c) && c.Kind == PdmClaimKind.Free;

    // the lowest free resources of a kind on a board
    public IReadOnlyList<int> FreeOf(string board, PdmResKind kind) =>
        _claims.Where(c => c.Key.Board == board && c.Key.Kind == kind && c.Value.Kind == PdmClaimKind.Free)
            .Select(c => c.Key.Index).Order().ToList();

    // ---------------- index ----------------

    private void Add(PdmBoard q, PdmResKind k, int i, object fn, IEnumerable<DeviceParameter> ps)
    {
        var r = new PdmRes(q.Role, k, i);
        _resOf[fn] = r;
        _fnOf[r] = fn;
        foreach (var p in ps) _resOfParam[p] = r;
    }

    private void Index(PdmBoard q)
    {
        var d = q.Device;
        for (var i = 0; i < d.DigitalInputs.Count; i++) Add(q, PdmResKind.DigitalInput, i, d.DigitalInputs[i], d.DigitalInputs[i].Params);
        for (var i = 0; i < d.AnalogInputs.Count; i++) Add(q, PdmResKind.AnalogInput, i, d.AnalogInputs[i], d.AnalogInputs[i].Params);
        for (var i = 0; i < d.CanInputs.Count; i++) Add(q, PdmResKind.CanInput, i, d.CanInputs[i], d.CanInputs[i].Params);
        for (var i = 0; i < d.VirtualInputs.Count; i++) Add(q, PdmResKind.VirtualInput, i, d.VirtualInputs[i], d.VirtualInputs[i].Params);
        for (var i = 0; i < d.Conditions.Count; i++) Add(q, PdmResKind.Condition, i, d.Conditions[i], d.Conditions[i].Params);
        for (var i = 0; i < d.Timers.Count; i++) Add(q, PdmResKind.Timer, i, d.Timers[i], d.Timers[i].Params);
        for (var i = 0; i < d.Counters.Count; i++) Add(q, PdmResKind.Counter, i, d.Counters[i], d.Counters[i].Params);
        for (var i = 0; i < d.Flashers.Count; i++) Add(q, PdmResKind.Flasher, i, d.Flashers[i], d.Flashers[i].Params);
        for (var i = 0; i < d.MathBlocks.Count; i++) Add(q, PdmResKind.Math, i, d.MathBlocks[i], d.MathBlocks[i].Params);
        for (var i = 0; i < d.CanOutputs.Count; i++) Add(q, PdmResKind.CanOutput, i, d.CanOutputs[i], d.CanOutputs[i].Params);
        for (var i = 0; i < d.Outputs.Count; i++) Add(q, PdmResKind.Output, i, d.Outputs[i], d.Outputs[i].Params);
        for (var i = 0; i < d.Keypads.Count; i++)
        {
            var k = d.Keypads[i];
            Add(q, PdmResKind.Keypad, i, k, k.BaseParams.Concat(k.ButtonParams).Concat(k.DialParams));
        }
        if (d.Wipers != null) Add(q, PdmResKind.Wiper, 0, d.Wipers, d.Wipers.Params);
        if (d.StarterDisable != null) Add(q, PdmResKind.Starter, 0, d.StarterDisable, d.StarterDisable.Params);
        // PRO_FEATURES (PR #98): 4 lookup tables; trip time / open-load settings belong to their output; master retry
        // (0x7F00 sub 6) to the device block. CustomPdmSettings.GetParams makes new param objects: mapped by name.
        if (d.CustomPdm is { } cp)
            for (var n = 0; n < cp.Tables.Count; n++)
            {
                var r = new PdmRes(q.Role, PdmResKind.Table, n);
                _fnOf[r] = cp.Tables[n];
                _resOf[cp.Tables[n]] = r;
            }
        var dev = new PdmRes(q.Role, PdmResKind.Device, 0);
        _fnOf[dev] = d;
        _resOf[d] = dev;
        foreach (var p in d.Params.Where(p => !_resOfParam.ContainsKey(p))) _resOfParam[p] = ProRes(q, p) ?? dev;
    }

    private static PdmRes? ProRes(PdmBoard q, DeviceParameter p)
    {
        static int? Num(string name, string prefix) =>
            name.StartsWith(prefix) && int.TryParse(name[prefix.Length..name.IndexOf(']')], out var n) ? n - 1 : null;
        if (Num(p.Name, "customPdm.table[") is { } t) return new PdmRes(q.Role, PdmResKind.Table, t);
        if (Num(p.Name, "customPdm.output[") is { } o) return new PdmRes(q.Role, PdmResKind.Output, o);
        return null;
    }

    // the table whose output is variable entry e ("Table n", no owner), or null
    private PdmRes? TableOfVar(PdmBoard q, DeviceVariable e) =>
        e.Owner == null && e.GetName() is var n && n.StartsWith("Table ") && int.TryParse(n[6..], out var k)
            && _fnOf.ContainsKey(new PdmRes(q.Role, PdmResKind.Table, k - 1))
            ? new PdmRes(q.Role, PdmResKind.Table, k - 1) : null;

    // ---------------- references ----------------

    private void Ref(PdmBoard q, PdmRes from, string field, int var)
    {
        if (var == 0) return;
        var entry = q.Device.VarMap.FirstOrDefault(x => x.VariableIndex == var);
        _refs.Add(entry == null
            ? new PdmRef(from, field, var, null, true)
            : new PdmRef(from, field, var, entry.Owner is { } o ? ResOf(o) : TableOfVar(q, entry), false));
    }

    private void CollectRefs(PdmBoard q)
    {
        var d = q.Device;
        PdmRes R(object fn) => _resOf[fn];
        foreach (var o in d.Outputs)
        {
            Ref(q, R(o), "trigger", o.Input);
            if (o.PwmEnabled && o.VariableDutyCycle) Ref(q, R(o), "PWM duty", o.DutyCycleInput);
        }
        foreach (var x in d.VirtualInputs)
        {
            Ref(q, R(x), "term 1", x.Var0);
            Ref(q, R(x), "term 2", x.Var1);
            Ref(q, R(x), "term 3", x.Var2);
        }
        foreach (var x in d.Conditions) Ref(q, R(x), "input", x.Input);
        foreach (var x in d.Timers)
        {
            Ref(q, R(x), "input", x.Input);
            Ref(q, R(x), "reset input", x.ResetInput);
        }
        foreach (var x in d.Counters)
        {
            Ref(q, R(x), "count-up input", x.IncInput);
            Ref(q, R(x), "count-down input", x.DecInput);
            Ref(q, R(x), "reset input", x.ResetInput);
        }
        foreach (var x in d.Flashers) Ref(q, R(x), "input", x.Input);
        foreach (var x in d.MathBlocks)
        {
            Ref(q, R(x), "input A", x.InputA);
            Ref(q, R(x), "input B", x.InputB);
        }
        foreach (var x in d.CanOutputs) Ref(q, R(x), "input", x.Input);
        foreach (var k in d.Keypads)
        {
            Ref(q, R(k), "dimming input", k.DimmingVar);
            foreach (var b in k.Buttons)
            {
                for (var i = 0; i < b.Vars.Length; i++) Ref(q, R(k), $"button {b.Number} LED input {i + 1}", b.Vars[i]);
                Ref(q, R(k), $"button {b.Number} fault input", b.FaultVar);
            }
        }
        if (d.Wipers is { } w)
            foreach (var (f, var) in new[] { ("slow input", w.SlowInput), ("fast input", w.FastInput), ("intermittent input", w.InterInput),
                         ("on input", w.OnInput), ("speed input", w.SpeedInput), ("park input", w.ParkInput), ("swipe input", w.SwipeInput), ("wash input", w.WashInput) })
                Ref(q, R(w), f, var);
        if (d.StarterDisable is { } s) Ref(q, R(s), "input", s.Input);
        var dev = R(d);
        Ref(q, dev, "mute CAN input", d.MuteCanTxInput);
        Ref(q, dev, "force-sleep input", d.ForceSleepInput);
        if (d.CustomPdm is { } cp)
        {
            Ref(q, dev, "master-retry input", cp.MasterRetryInput);           // P3
            for (var i = 0; i < cp.PwmFreqInputs.Count && i < d.Outputs.Count; i++)   // PR #105 tach: frequency from input
                if (cp.PwmFreqInputs[i].Enabled) Ref(q, R(d.Outputs[i]), "PWM frequency input", cp.PwmFreqInputs[i].Input);
            foreach (var t in cp.Tables) Ref(q, R(t), "input", t.Input);      // T1
        }
    }

    // ---------------- claims ----------------

    public static readonly PdmResKind[] Allocatable =
    [
        PdmResKind.CanInput, PdmResKind.VirtualInput, PdmResKind.Condition, PdmResKind.Timer, PdmResKind.Counter,
        PdmResKind.Flasher, PdmResKind.Math, PdmResKind.CanOutput, PdmResKind.Table
    ];

    private readonly List<(PdmRes Res, PdmClaim First, PdmClaim Second)> _collisions = [];

    private void Claim(PdmRes r, PdmClaim c)
    {
        if (_claims.TryGetValue(r, out var had))
        {
            if (had != c) _collisions.Add((r, had, c));
            return;
        }
        _claims[r] = c;
    }

    public const string FanText = "the fan logic (A2 OUT2)";
    public const string ShedText = "the load-shed example";

    private void MakeClaims()
    {
        var v = View;
        foreach (var q in v.Boards)
        {
            var d = q.Device;
            if (q.Role == "A2")
            {
                for (var s = 0; s < 4; s++) Claim(new PdmRes(q.Role, PdmResKind.CanInput, PdmFactoryDefaults.FanCanIn0 + s), new PdmClaim(PdmClaimKind.Reserved, FanText));
                for (var k = 0; k < 3; k++) Claim(new PdmRes(q.Role, PdmResKind.VirtualInput, PdmFactoryDefaults.FanVirt0(d) + k), new PdmClaim(PdmClaimKind.Reserved, FanText));
                for (var c = 0; c < 2; c++) Claim(new PdmRes(q.Role, PdmResKind.Condition, PdmFactoryDefaults.FanCond0(d) + c), new PdmClaim(PdmClaimKind.Reserved, FanText));
            }
            for (var k = 0; k < 2; k++) Claim(new PdmRes(q.Role, PdmResKind.VirtualInput, PdmFactoryDefaults.ShedVirt0(d) + k), new PdmClaim(PdmClaimKind.Reserved, ShedText));
            for (var c = 0; c < 4; c++) Claim(new PdmRes(q.Role, PdmResKind.Condition, PdmFactoryDefaults.ShedCond0(d) + c), new PdmClaim(PdmClaimKind.Reserved, ShedText));
        }

        // links in use (PdmLinks w1 recipe)
        foreach (var l in PdmLinks.Links(v))
        {
            var text = $"the link IN{l.In.Number} -> output {l.Out.Number}";
            if (l.Slot is { } s) Claim(new PdmRes(l.Out.Board, PdmResKind.CanInput, s), new PdmClaim(PdmClaimKind.Link, text));
            if (l.Virt is { } k) Claim(new PdmRes(l.Out.Board, PdmResKind.VirtualInput, k), new PdmClaim(PdmClaimKind.Link, text));
            if (l.Shared is { } sh)
            {
                var st = $"the shared ALIVE / SEEN / LOST of the links from {sh.Source.Role}";
                Claim(new PdmRes(sh.Board.Role, PdmResKind.CanInput, sh.Alive), new PdmClaim(PdmClaimKind.Shared, st));
                Claim(new PdmRes(sh.Board.Role, PdmResKind.CanInput, sh.Seen), new PdmClaim(PdmClaimKind.Shared, st));
                Claim(new PdmRes(sh.Board.Role, PdmResKind.VirtualInput, sh.Lost), new PdmClaim(PdmClaimKind.Shared, st));
            }
        }

        // editor2: ECU-driven outputs (PdmEcu): command slot + on / condition virtual input, shared ALIVE / SEEN / LOST
        foreach (var e in PdmEcu.All(v))
        {
            var text = $"the ECU command {e.Source} -> output {e.Out.Number}";
            Claim(new PdmRes(e.Out.Board, PdmResKind.CanInput, e.Slot), new PdmClaim(PdmClaimKind.Link, text));
            if (e.Virt is { } k) Claim(new PdmRes(e.Out.Board, PdmResKind.VirtualInput, k), new PdmClaim(PdmClaimKind.Link, text));
            if (e.Shared is { } sh)
            {
                var st = $"the shared ALIVE / SEEN / LOST of the ECU stream 0x{e.Id:X3}";
                Claim(new PdmRes(e.Out.Board, PdmResKind.CanInput, sh.Alive), new PdmClaim(PdmClaimKind.Shared, st));
                Claim(new PdmRes(e.Out.Board, PdmResKind.CanInput, sh.Seen), new PdmClaim(PdmClaimKind.Shared, st));
                Claim(new PdmRes(e.Out.Board, PdmResKind.VirtualInput, sh.Lost), new PdmClaim(PdmClaimKind.Shared, st));
            }
        }

        // editor2: functions of several outputs (turn signals, wiper) and PWM duty curves (PdmFunctions, PdmPwm)
        foreach (var f in PdmFunctions.All(this))
            foreach (var r in f.Made) Claim(r, new PdmClaim(PdmClaimKind.Trigger, f.Text, f.Outputs[0], f.OutputsKey));
        foreach (var c in PdmPwm.Curves(this))
            Claim(c.Table, new PdmClaim(PdmClaimKind.Trigger, $"output {c.Out.Number}'s PWM duty curve", c.Out.Number));

        // triggers made by the /pdm editor (one output each)
        foreach (var o in v.Outputs)
        {
            var t = PdmTriggers.Decode(this, o);
            _triggers.Add(t);
            if (!t.Editor || t.Link != null) continue;
            foreach (var r in t.Made) Claim(r, new PdmClaim(PdmClaimKind.Trigger, $"output {o.Number}'s trigger ({t.Words})", o.Number));
        }

        // link-recipe slots / virtual inputs that no link and no trigger uses
        foreach (var q in v.Boards)
        {
            for (var s = 0; s < q.Device.CanInputs.Count; s++)
                if (PdmLinks.RoleOfSlot(v, q, s) is { } role && !_claims.ContainsKey(new PdmRes(q.Role, PdmResKind.CanInput, s)))
                    _claims[new PdmRes(q.Role, PdmResKind.CanInput, s)] = new PdmClaim(PdmClaimKind.Link,
                        $"an unused link slot for {role.Source.Role} (Remove unused on the Links panel)");
            for (var k = 0; k < q.Device.VirtualInputs.Count; k++)
                if (PdmLinks.RoleOfVirt(v, q, k) is { } role && !_claims.ContainsKey(new PdmRes(q.Role, PdmResKind.VirtualInput, k)))
                    _claims[new PdmRes(q.Role, PdmResKind.VirtualInput, k)] = new PdmClaim(PdmClaimKind.Link,
                        $"an unused link virtual input for {role.Source.Role} (Remove unused on the Links panel)");
        }

        // everything else: free (fresh-board values and nothing reads it) or set by hand
        var referenced = _refs.Where(r => r.To != null).Select(r => r.To!).ToHashSet();
        foreach (var (r, fn) in _fnOf)
        {
            if (!Allocatable.Contains(r.Kind) || _claims.ContainsKey(r)) continue;
            _claims[r] = Fresh(fn) && !referenced.Contains(r)
                ? new PdmClaim(PdmClaimKind.Free, "free")
                : new PdmClaim(PdmClaimKind.Hand, $"set by hand ({(Enabled(fn) ? "enabled" : "disabled")})");
        }
    }

    // fresh-board values of the allocatable kinds (what a "New PDM" project or a fresh board has)
    public static bool Fresh(object fn) => fn switch
    {
        CanInput c => !c.Enabled && c.Id == 0,
        VirtualInput x => !x.Enabled && x is { Var0: 0, Var1: 0, Var2: 0 },
        Condition c => !c.Enabled && c.Input == 0,
        DeviceTimer t => !t.Enabled && t.Input == 0 && t.ResetInput == 0,
        Counter c => !c.Enabled && c.IncInput == 0 && c.DecInput == 0 && c.ResetInput == 0,
        Flasher f => !f.Enabled && f.Input == 0,
        MathBlock m => !m.Enabled && m.InputA == 0 && m.InputB == 0,
        CanOutput c => !c.Enabled && c.Input == 0 && c.Id == 0,
        LookupTable t => !t.Enabled && t.Input == 0 && t.Points == 0,
        _ => false
    };

    public static bool Enabled(object fn) => fn switch
    {
        DigitalInput x => x.Enabled,
        AnalogInput x => x.Enabled,
        CanInput x => x.Enabled,
        VirtualInput x => x.Enabled,
        Condition x => x.Enabled,
        DeviceTimer x => x.Enabled,
        Counter x => x.Enabled,
        Flasher x => x.Enabled,
        MathBlock x => x.Enabled,
        CanOutput x => x.Enabled,
        Output x => x.Enabled,
        KeypadMaster x => x.Enabled,
        Wiper x => x.Enabled,
        StarterDisable x => x.Enabled,
        LookupTable x => x.Enabled,
        _ => true
    };

    // ---------------- problems ----------------

    private void P(PdmProblemKind k, string text)
    {
        if (!_problems.Any(p => p.Kind == k && p.Text == text)) _problems.Add(new PdmProblem(k, text));
    }

    private static string Cap(string s) => s.Length == 0 ? s : char.ToUpperInvariant(s[0]) + s[1..];

    private string VarText(PdmRef r) => r.To is { } to ? to.Text : $"variable {r.Var}";

    private void FindProblems()
    {
        var v = View;
        // output driven twice: a paired output (it follows its primary) that also has its own trigger
        foreach (var o in v.Outputs)
            if (o.Output.PrimaryOutput >= 0 && o.Output.Input != 0)
                P(PdmProblemKind.OutputDrivenTwice,
                    $"Output {o.Number} ({o.Board} OUT{o.BoardOutput}) follows {o.Board} OUT{o.Output.PrimaryOutput + 1} (paired) and also has its own trigger ({Words(o)}): the pairing wins, the trigger does nothing.");

        // resource used by two owners
        foreach (var (r, a, b) in _collisions)
            P(PdmProblemKind.TwoOwners, $"{Cap(r.Text)} is part of {a.Text} and of {b.Text}: changing one changes the other.");
        foreach (var x in _refs.Where(x => x.To != null))
        {
            var to = x.To!;
            if (!_claims.TryGetValue(to, out var c) || c.Kind is not (PdmClaimKind.Trigger or PdmClaimKind.Link)) continue;
            if (SameOwner(x.From, c, to)) continue;
            P(PdmProblemKind.TwoOwners, $"{Cap(to.Text)} belongs to {c.Text}, but {x.From.Text} also reads it ({x.Field}): changing or removing that one changes this too.");
        }

        // reference to a disabled / missing resource (from enabled functions only)
        foreach (var x in _refs)
        {
            if (!Enabled(Fn(x.From))) continue;
            if (x.Missing)
                P(PdmProblemKind.MissingRef, $"{Cap(x.From.Text)} ({x.Field}) uses variable {x.Var}, which this board does not have.");
            else if (x.To is { } to && !Enabled(Fn(to)))
                P(PdmProblemKind.MissingRef, $"{Cap(x.From.Text)} ({x.Field}) uses {to.Text}, which is not enabled.");
            // a link slot carries an input of another board: that input must be enabled there
            if (x.To is { Kind: PdmResKind.CanInput } ci && PdmLinks.RoleOfSlot(v, Board(ci.Board), ci.Index) is { Kind: PdmSlotKind.Link } role
                && role.Source.Device.DigitalInputs[role.Bit] is { Enabled: false })
                P(PdmProblemKind.MissingRef, $"{Cap(x.From.Text)} uses IN{PdmView.DigitalInputNumber(role.Source.Role, role.Bit)} of {role.Source.Role} (through {ci.Text}), which is not enabled.");
        }

        // link slot changed by hand: listens to another board's link message (msg 37) but is no longer the recipe
        foreach (var q in v.Boards)
            for (var s = 0; s < q.Device.CanInputs.Count; s++)
            {
                var c = q.Device.CanInputs[s];
                if (!c.Enabled || PdmLinks.IsFanSlot(q, s) || PdmLinks.RoleOfSlot(v, q, s) != null) continue;
                if (v.Boards.FirstOrDefault(p => p.Role != q.Role && p.Device.BaseId + PdmLinks.StatusOffset == c.Id) is { } p)
                    P(PdmProblemKind.LinkSlotByHand,
                        $"{q.Role} CAN input {s + 1} listens to {p.Role}'s link message (0x{c.Id:X3}) but its settings were changed by hand: links and triggers no longer recognise it.");
            }

        // reserved slots touched
        foreach (var q in v.Boards)
        {
            var d = q.Device;
            if (q.Role == "A2")
            {
                if (PdmLinked.FanLayoutProblem(d) is { } why) P(PdmProblemKind.ReservedTouched, why);
                if (!FanVirtsFactory(d)) P(PdmProblemKind.ReservedTouched, $"A2 virtual inputs {PdmFactoryDefaults.FanVirt0(d) + 1}-{PdmFactoryDefaults.FanVirt0(d) + 3} (fan logic, reserved) were changed by hand.");
                var fan = d.Outputs[PdmFactoryDefaults.FanOutput];
                if (fan.Input != PdmFactoryDefaults.VarOf(d, d.VirtualInputs[PdmFactoryDefaults.FanVirt0(d) + 2]))
                    P(PdmProblemKind.ReservedTouched, $"Output {PdmView.OutputNumber("A2", PdmFactoryDefaults.FanOutput)} (A2 OUT2, the fans) is not driven by the fan logic.");
            }
            if (!ShedFactory(d)) P(PdmProblemKind.ReservedTouched, $"{q.Role} load-shed example (conditions {PdmFactoryDefaults.ShedCond0(d) + 1}-{PdmFactoryDefaults.ShedCond0(d) + 4}, virtual inputs {PdmFactoryDefaults.ShedVirt0(d) + 1}-{PdmFactoryDefaults.ShedVirt0(d) + 2}, reserved) was rewired by hand (only its thresholds and Enabled are meant to change).");
        }
    }

    private bool SameOwner(PdmRes from, PdmClaim c, PdmRes to)
    {
        if (_claims.TryGetValue(from, out var fc) && fc == c) return true;
        if (from.Kind != PdmResKind.Output || from.Board != to.Board) return false;
        var n = PdmView.OutputNumber(from.Board, from.Index);
        if (c.Kind == PdmClaimKind.Trigger) return c.Output == n || c.Outputs != null && c.Outputs.Contains($",{n},");
        return c.Text.EndsWith($"-> output {n}"); // a link's own output
    }

    private string Words(PdmOutputRow o) => _triggers.FirstOrDefault(t => t.Out == o)?.Words ?? $"variable {o.Output.Input}";

    private static bool FanVirtsFactory(FwDevice d)
    {
        var v0 = PdmFactoryDefaults.FanVirt0(d);
        var c0 = PdmFactoryDefaults.FanCond0(d);
        int Ci(int k) => PdmFactoryDefaults.CanInState(d, PdmFactoryDefaults.FanCanIn0 + k);
        var (hot, cool, latch) = (d.VirtualInputs[v0], d.VirtualInputs[v0 + 1], d.VirtualInputs[v0 + 2]);
        return hot is { Enabled: true, Not0: false, Cond0: Conditional.Or, Not1: false, Cond1: Conditional.Or, Not2: false }
               && hot.Var0 == PdmFactoryDefaults.VarOf(d, d.Conditions[c0]) && hot.Var1 == Ci(0) && hot.Var2 == Ci(2)
               && cool is { Enabled: true, Not0: false, Cond0: Conditional.And, Not1: false, Cond1: Conditional.And, Not2: false }
               && cool.Var0 == PdmFactoryDefaults.VarOf(d, d.Conditions[c0 + 1]) && cool.Var1 == Ci(1) && cool.Var2 == Ci(3)
               && latch is { Enabled: true, Not0: false, Cond0: Conditional.Or, Not1: false, Cond1: Conditional.And, Not2: true }
               && latch.Var0 == PdmFactoryDefaults.VarOf(d, hot) && latch.Var1 == PdmFactoryDefaults.VarOf(d, latch) && latch.Var2 == PdmFactoryDefaults.VarOf(d, cool);
    }

    private static bool ShedFactory(FwDevice d)
    {
        var temp = PdmFactoryDefaults.BoardTempVar(d);
        for (var l = 0; l < 2; l++)
        {
            var hot = d.Conditions[PdmFactoryDefaults.ShedCond0(d) + 2 * l];
            var cool = d.Conditions[PdmFactoryDefaults.ShedCond0(d) + 2 * l + 1];
            var vi = d.VirtualInputs[PdmFactoryDefaults.ShedVirt0(d) + l];
            if (hot is not { Operator: Operator.GreaterThanOrEqual } || hot.Input != temp) return false;
            if (cool is not { Operator: Operator.LessThanOrEqual } || cool.Input != temp) return false;
            if (vi is not { Not0: false, Cond0: Conditional.Or, Not1: false, Cond1: Conditional.And, Not2: true }
                || vi.Var0 != PdmFactoryDefaults.VarOf(d, hot) || vi.Var1 != PdmFactoryDefaults.VarOf(d, vi) || vi.Var2 != PdmFactoryDefaults.VarOf(d, cool))
                return false;
        }
        return true;
    }

    // ---------------- use per board ----------------

    public PdmBoardUse Use(string board)
    {
        var kinds = new[] { PdmResKind.CanInput, PdmResKind.VirtualInput, PdmResKind.Condition, PdmResKind.Timer, PdmResKind.Flasher,
            PdmResKind.Counter, PdmResKind.Math, PdmResKind.CanOutput, PdmResKind.Table };
        kinds = kinds.Where(k => k != PdmResKind.Table || _fnOf.Keys.Any(r => r.Board == board && r.Kind == k)).ToArray();
        return new PdmBoardUse(board, kinds.Select(k =>
        {
            var mine = _claims.Where(c => c.Key.Board == board && c.Key.Kind == k).Select(c => c.Value.Kind).ToList();
            return new PdmKindUse(k, mine.Count, mine.Count(x => x == PdmClaimKind.Free), mine.Count(x => x == PdmClaimKind.Reserved),
                mine.Count(x => x is PdmClaimKind.Link or PdmClaimKind.Shared), mine.Count(x => x == PdmClaimKind.Trigger),
                mine.Count(x => x == PdmClaimKind.Hand));
        }).ToList());
    }
}

public static class PdmEngine
{
    public static string KindName(PdmResKind k) => k switch
    {
        PdmResKind.DigitalInput => "input",
        PdmResKind.AnalogInput => "analog input",
        PdmResKind.CanInput => "CAN input",
        PdmResKind.VirtualInput => "virtual input",
        PdmResKind.Condition => "condition",
        PdmResKind.Timer => "timer",
        PdmResKind.Counter => "counter",
        PdmResKind.Flasher => "flasher",
        PdmResKind.Math => "math block",
        PdmResKind.CanOutput => "CAN output",
        PdmResKind.Output => "output",
        PdmResKind.Keypad => "keypad",
        PdmResKind.Wiper => "wiper",
        PdmResKind.Starter => "starter block",
        PdmResKind.Table => "lookup table",
        _ => "device settings"
    };

    public static PdmModel Build(PdmView v) => PdmModel.Build(v);

    // Does any function of the board read variable var (virtualInputs false: any but its virtual inputs)? A quick
    // scan without a model, the same fields as PdmModel's references.
    public static bool IsRead(FwDevice d, int var, bool virtualInputs = true)
    {
        if (var == 0) return false;
        return d.Outputs.Any(o => o.Input == var || o.PwmEnabled && o.VariableDutyCycle && o.DutyCycleInput == var)
               || virtualInputs && d.VirtualInputs.Any(x => x.Var0 == var || x.Var1 == var || x.Var2 == var)
               || d.Conditions.Any(x => x.Input == var)
               || d.Timers.Any(x => x.Input == var || x.ResetInput == var)
               || d.Counters.Any(x => x.IncInput == var || x.DecInput == var || x.ResetInput == var)
               || d.Flashers.Any(x => x.Input == var)
               || d.MathBlocks.Any(x => x.InputA == var || x.InputB == var)
               || d.CanOutputs.Any(x => x.Input == var)
               || d.Keypads.Any(k => k.DimmingVar == var || k.Buttons.Any(b => b.FaultVar == var || b.Vars.Contains(var)))
               || d.Wipers is { } w && new[] { w.SlowInput, w.FastInput, w.InterInput, w.OnInput, w.SpeedInput, w.ParkInput, w.SwipeInput, w.WashInput }.Contains(var)
               || d.StarterDisable is { } s && s.Input == var
               || d.MuteCanTxInput == var || d.ForceSleepInput == var
               || d.CustomPdm is { } cp && (cp.MasterRetryInput == var || cp.Tables.Any(t => t.Input == var)
                                            || cp.PwmFreqInputs.Any(f => f.Enabled && f.Input == var));
    }

    // ---------------- critical settings (p1 / p3): never changed on the Advanced screen ----------------

    public static readonly string[] CriticalParams = ["device.baseId", "device.canSpeed", "customPdm.tempCrit", "customPdm.critExemptMask"];

    public static bool IsCritical(DeviceParameter p) => CriticalParams.Contains(p.Name);

    // ---------------- reset to fresh-board values ----------------

    // the stock PC defaults of a new function = a fresh board's values (proven for CAN / virtual inputs in
    // PdmB3LiveSimTests; New PDM = the same for every function the factory config does not set)
    public static void Reset(IDeviceFunction f)
    {
        IDeviceFunction fresh = f switch
        {
            CanInput c => new CanInput(c.Number, "canInput" + c.Number),
            VirtualInput x => new VirtualInput(x.Number, "virtualInput" + x.Number),
            Condition c => new Condition(c.Number, "condition" + c.Number),
            DeviceTimer t => new DeviceTimer(t.Number, "timer" + t.Number),
            Flasher x => new Flasher(x.Number, "flasher" + x.Number),
            Counter c => new Counter(c.Number, "counter" + c.Number),
            MathBlock m => new MathBlock(m.Number, "math" + m.Number),
            _ => throw new ArgumentException($"no reset for {f.GetType().Name}")
        };
        var (ps, fs) = (f.Params, fresh.Params);
        for (var i = 0; i < ps.Count; i++) ps[i].SetValue(fs[i].GetValue());
        switch (f)
        {
            case CanInput c: c.Name = fresh.Name; break;
            case VirtualInput x: x.Name = fresh.Name; break;
            case Condition c: c.Name = fresh.Name; break;
            case DeviceTimer t: t.Name = fresh.Name; break;
            case Flasher x: x.Name = fresh.Name; break;
            case Counter c: c.Name = fresh.Name; break;
            case MathBlock m: m.Name = fresh.Name; break;
        }
    }

    // ---------------- edit check (Advanced screen) ----------------

    // What an edit made since `before` would replace or break. The model holds the edited values when this returns.
    public static PdmEditCheck CheckEdit(PdmView v, PdmSnapshot before)
    {
        var changed = before.Changed();
        if (changed.Count == 0) return PdmEditCheck.None;
        var critical = new List<string>();
        foreach (var (p, was, now) in changed.Where(c => IsCritical(c.P)))
            critical.Add($"{p.ParentName}: {p.Name} {Show(p, was)} -> {Show(p, now)}");

        var after = PdmSnapshot.Take(v);
        var mAfter = PdmModel.Build(v);
        before.Restore();
        var mBefore = PdmModel.Build(v);
        var assigned = new List<string>();
        foreach (var (p, was, _) in changed)
        {
            if (mBefore.ResOfParam(p) is not { } r) continue;
            var fn = mBefore.Fn(r);
            if (fn is Output o && p.Name.EndsWith(".input") && (int)was != 0)
            {
                var row = v.Outputs.FirstOrDefault(x => ReferenceEquals(x.Output, o));
                var words = mBefore.Triggers.FirstOrDefault(t => ReferenceEquals(t.Out.Output, o))?.Words ?? $"variable {was}";
                assigned.Add($"{Cap(r.Text)} is already assigned to its trigger ({words}).");
                continue;
            }
            var c = mBefore.ClaimOf(r);
            if (c.Kind is PdmClaimKind.Reserved or PdmClaimKind.Link or PdmClaimKind.Shared or PdmClaimKind.Trigger)
                assigned.Add($"{Cap(r.Text)} is already assigned to {c.Text}.");
        }
        after.Restore();
        var newProblems = mAfter.Problems.Where(p => !mBefore.Problems.Contains(p)).ToList();
        return new PdmEditCheck(assigned.Distinct().ToList(), newProblems, critical);
    }

    private static string Show(DeviceParameter p, object val) =>
        p.Name == "device.baseId" ? $"0x{Convert.ToInt32(val):X3}" : val.ToString() ?? "";

    private static string Cap(string s) => s.Length == 0 ? s : char.ToUpperInvariant(s[0]) + s[1..];
}
