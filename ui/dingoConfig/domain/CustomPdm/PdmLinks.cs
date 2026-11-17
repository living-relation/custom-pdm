using domain.Devices;
using domain.Devices.Functions;
using domain.Enums;
using domain.Interfaces;

namespace domain.CustomPdm;

// custom-pdm route B, phase B4 (docs/ui-route-b-plan.md) with the w1 recipe (DECISIONS 2026-11-16, sim-proven in
// firmware/sim s1 "S7", PR #93): any digital input of the PDM as the trigger of any output.
// Nothing is set on the source board: every board sends ALL its digital inputs in cyclic msg 37 (TxMsg37: base + 2 +
// 37, bytes 0-1 little endian, bit i = input i + 1, every 100 ms, real inputs from the first frame on).
// A link "input X on board P -> output Y on board Q":
// - P == Q: output Y's trigger is the input itself (nothing else).
// - P != Q: L = one stock CAN input on Q on bit i of P's msg 37 (length 1, Equal 1). Loss mode per OUTPUT (w1):
//     off       = L, time-out on (1 s)                       -> off 1 s after P's last frame
//     hold      = L, time-out off                            -> keeps its last state (off at power-up)
//     on        = virtual input "LOST OR L"                  -> on 1 s after P's last frame
//     condition = virtual input "(LOST AND C) OR L"          -> follows C (an input / condition of Q) at loss
//   critical (on / condition only) = NOT ALIVE in place of LOST: acts from power-up, no wait for P's first frame.
//   Shared by all on / condition links from P on Q (made with the first, freed with the last):
//     ALIVE = CAN input on P's msg 37, bit 0, '>= 0' (true for every frame), time-out on (= the link time-out)
//     SEEN  = the same with the time-out off (0 until P's first frame after Q powers up)
//     LOST  = virtual input "SEEN AND NOT ALIVE", with a LOWER index than every non-critical link virtual input
//             that uses it (virtual inputs run in index order: else a 2.2 ms drop at the time-out, s1 S7)
//   Non-critical outputs stay off until P's first frame after power-up (SEEN = 0 -> LOST = 0): no start-up blip.
// Cost on Q: per source board 2 CAN inputs + 1 virtual input (only while it has on / condition links); per link 1 CAN
// input, + 1 virtual input for on / condition.
// Ownership: links live only in the boards' params (no PC-only state), so they survive Read All, an app restart and a
// fresh project. A CAN input / virtual input is ours only when ALL its fields match one of the patterns above (ID = the
// msg 37 ID of another board of this PDM); the old B4 "on" recipe (slot Equal 0 with time-out + "NOT slot OR false")
// is recognised as OldRecipe and converted only by Upgrade (the user's OK). Anything else is the user's and is never
// changed. Free = disabled with ID 0 (virtual input: disabled, no variables), never A2's fan CAN inputs 25-28, A2's fan
// virtual inputs 12-14 or the load-shed ones 15-16. The lowest free one is used. Removing a link puts what it used
// back to fresh-board values and the output trigger to none. Edits are all-or-nothing (refused = nothing changed).
// All of it is a PC edit: it reaches the boards with the /pdm Write All (PdmOps), and is kept after Burn.
// Numbers: Slot / Virt count from 0 (param index); the UI shows them from 1.
public enum PdmLinkLoss { Off, Hold, On, Condition }

public enum PdmSlotKind { Link, OldOn, Alive, Seen }

public enum PdmVirtKind { Lost, On, Condition, OldOn }

public record PdmSlotRole(PdmSlotKind Kind, PdmBoard Source, int Bit);

public record PdmVirtRole(PdmVirtKind Kind, PdmBoard Source, int Slot, bool Critical, int Cond);

// ALIVE / SEEN CAN inputs and the LOST virtual input on board Board for the links from Source
public record PdmShared(PdmBoard Board, PdmBoard Source, int Alive, int Seen, int Lost)
{
    public string Text => $"{Board.Role} CAN inputs {Alive + 1} (alive) / {Seen + 1} (seen) + virtual input {Lost + 1} (lost)";
}

public record PdmCondChoice(int Var, string Text);

public record PdmLink(PdmOutputRow Out, PdmInputRow In, PdmLinkLoss? Loss, int? Slot, int? Virt,
    bool Critical = false, int Cond = 0, string? CondText = null, bool OldRecipe = false, PdmShared? Shared = null)
{
    public bool CrossBoard => Slot != null;

    public string LossText => (Loss, OldRecipe) switch
    {
        (PdmLinkLoss.On, true) => "on 1 s after the message stops (old recipe: on at power-up until the first frame)",
        (PdmLinkLoss.Off, _) => "off 1 s after the message stops",
        (PdmLinkLoss.Hold, _) => "keeps its last state (off at power-up)",
        (PdmLinkLoss.On, _) => "on 1 s after the message stops" + CritText,
        (PdmLinkLoss.Condition, _) => $"follows {CondText} 1 s after the message stops" + CritText,
        _ => "same board: no CAN message"
    };

    private string CritText => Critical ? "; critical: acts from power-up" : "; off until the first frame";

    public string SlotText => Slot is { } s
        ? $"{Out.Board} CAN input {s + 1}" + (Virt is { } k ? $" + virtual input {k + 1}" : "")
        : "none (same board)";
}

// Shared: an ALIVE / SEEN / LOST of links (else OurLink = a link's own slot / virtual input)
public record PdmSlotUse(string Board, int Slot, bool Free, bool OurLink, string UsedBy, bool Shared = false)
{
    public bool Unused => UsedBy.EndsWith("(Remove unused)");
}

public record PdmBoardSlots(string Board, IReadOnlyList<PdmSlotUse> CanInputs, IReadOnlyList<PdmSlotUse> VirtualInputs)
{
    public int FreeCanInputs => CanInputs.Count(u => u.Free);
    public int LinkCanInputs => CanInputs.Count(u => u.OurLink && !u.Shared);
    public int SharedCanInputs => CanInputs.Count(u => u.OurLink && u.Shared);
    public int FreeVirtuals => VirtualInputs.Count(u => u.Free);
    public int LinkVirtuals => VirtualInputs.Count(u => u.OurLink && !u.Shared);
    public int SharedVirtuals => VirtualInputs.Count(u => u.OurLink && u.Shared);

    public string Summary =>
        $"{Board}: CAN inputs {CanInputs.Count - FreeCanInputs} of {CanInputs.Count} used ({LinkCanInputs} by links, {SharedCanInputs} shared ALIVE / SEEN), {FreeCanInputs} free; " +
        $"virtual inputs {VirtualInputs.Count - FreeVirtuals} of {VirtualInputs.Count} used ({LinkVirtuals} by links, {SharedVirtuals} shared LOST), {FreeVirtuals} free";
}

public static class PdmLinks
{
    public const int StatusMsg = 37;                                                // TxMsg37: all digital inputs
    public const int StatusOffset = PdmFactoryDefaults.CyclicTxOffset + StatusMsg;  // base + 0x27
    public const int TimeoutMs = 1000;                                              // stock default time-out (D3a)
    public const PdmLinkLoss DefaultLoss = PdmLinkLoss.Off;                          // u3c

    public static readonly PdmLinkLoss[] LossChoices = [PdmLinkLoss.Off, PdmLinkLoss.Hold, PdmLinkLoss.On, PdmLinkLoss.Condition];

    public static string LossName(PdmLinkLoss l) => l switch
    {
        PdmLinkLoss.Off => "Off (1 s after the message stops)",
        PdmLinkLoss.Hold => "Hold (keeps its last state)",
        PdmLinkLoss.On => "On (1 s after the message stops)",
        _ => "Condition (follows a condition 1 s after it stops)"
    };

    // on / condition use the shared ALIVE / SEEN / LOST (and only they can be critical)
    public static bool UsesShared(PdmLinkLoss l) => l is PdmLinkLoss.On or PdmLinkLoss.Condition;

    private static string Word(PdmLinkLoss l) => l.ToString().ToLowerInvariant();

    // ---------------- reserved slots (port_boards.py: FAN_CANIN0, FAN_VIRT0, SHED_VIRT0) ----------------

    public static bool IsFanSlot(PdmBoard q, int s) =>
        q.Role == "A2" && s >= PdmFactoryDefaults.FanCanIn0 && s < PdmFactoryDefaults.FanCanIn0 + 4;

    private static bool IsFanVirt(PdmBoard q, int k) =>
        q.Role == "A2" && k >= PdmFactoryDefaults.FanVirt0(q.Device) && k < PdmFactoryDefaults.FanVirt0(q.Device) + 3;

    public static bool IsReservedVirt(PdmBoard q, int k)
    {
        var d = q.Device;
        return k >= PdmFactoryDefaults.ShedVirt0(d) && k < PdmFactoryDefaults.ShedVirt0(d) + 2 || IsFanVirt(q, k);
    }

    public static bool IsFreeSlot(PdmBoard q, int s)
    {
        var c = q.Device.CanInputs[s];
        return !IsFanSlot(q, s) && !c.Enabled && c.Id == 0;
    }

    public static bool IsFreeVirt(PdmBoard q, int k)
    {
        var vi = q.Device.VirtualInputs[k];
        return !IsReservedVirt(q, k) && !vi.Enabled && vi is { Var0: 0, Var1: 0, Var2: 0 };
    }

    // ---------------- pattern match ----------------

    private static PdmBoard? BoardOf(PdmView v, FwDevice d) => v.Boards.FirstOrDefault(b => ReferenceEquals(b.Device, d));

    private static PdmInputRow? DigitalRow(PdmView v, string role, int i) =>
        v.Inputs.FirstOrDefault(r => r.Digital != null && r.Board == role && r.BoardInput == i + 1);

    private static IDeviceFunction? OwnerOf(FwDevice d, int var)
    {
        var owner = d.VarMap.FirstOrDefault(x => x.VariableIndex == var)?.Owner;
        return owner != null && PdmFactoryDefaults.VarOf(d, owner) == var ? owner : null; // its first (state) variable
    }

    private static int SlotOfVar(FwDevice d, int var) => var != 0 && OwnerOf(d, var) is CanInput c ? d.CanInputs.IndexOf(c) : -1;

    private static string VarName(FwDevice d, int var) => d.VarMap.FirstOrDefault(x => x.VariableIndex == var)?.GetName() ?? "?";

    // What CAN input s on board q is for the links, or null (not ours)
    public static PdmSlotRole? RoleOfSlot(PdmView v, PdmBoard q, int s)
    {
        if (IsFanSlot(q, s)) return null;
        var c = q.Device.CanInputs[s];
        if (c is not { Enabled: true, Ide: false, BitLength: 1, Factor: 1.0, Offset: 0.0, ByteOrder: ByteOrder.LittleEndian,
                Signed: false, Mode: InputMode.Momentary, Bus: 0 }) return null;
        var p = v.Boards.FirstOrDefault(b => b.Role != q.Role && b.Device.BaseId + StatusOffset == c.Id);
        if (p == null) return null;
        PdmSlotKind? kind = (c.Operator, c.Operand) switch
        {
            (Operator.Equal, 1.0) => PdmSlotKind.Link,
            (Operator.Equal, 0.0) when c.TimeoutEnabled => PdmSlotKind.OldOn,
            (Operator.GreaterThanOrEqual, 0.0) when c.StartBit == 0 => c.TimeoutEnabled ? PdmSlotKind.Alive : PdmSlotKind.Seen,
            _ => null
        };
        if (kind is PdmSlotKind.Link or PdmSlotKind.OldOn && DigitalRow(v, p.Role, c.StartBit) == null) return null;
        return kind is { } k ? new PdmSlotRole(k, p, c.StartBit) : null;
    }

    private static PdmSlotRole? RoleOfVar(PdmView v, PdmBoard q, int var)
    {
        var s = SlotOfVar(q.Device, var);
        return s < 0 ? null : RoleOfSlot(v, q, s);
    }

    private static bool IsLostVirt(PdmBoard q, int k, int seenVar, int aliveVar)
    {
        if (IsReservedVirt(q, k)) return false;
        var vi = q.Device.VirtualInputs[k];
        return vi is { Enabled: true, Not0: false, Cond0: Conditional.And, Not1: true, Not2: false, Var2: 0, Mode: InputMode.Momentary }
               && vi.Var0 == seenVar && vi.Var1 == aliveVar;
    }

    // The shared ALIVE / SEEN / LOST on q for the links from p (the lowest of each), or null when one is missing
    public static PdmShared? SharedOf(PdmView v, PdmBoard q, PdmBoard p)
    {
        int alive = -1, seen = -1;
        for (var s = 0; s < q.Device.CanInputs.Count; s++)
            if (RoleOfSlot(v, q, s) is { } r && r.Source.Role == p.Role)
            {
                if (r.Kind == PdmSlotKind.Alive && alive < 0) alive = s;
                if (r.Kind == PdmSlotKind.Seen && seen < 0) seen = s;
            }
        if (alive < 0 || seen < 0) return null;
        var d = q.Device;
        for (var k = 0; k < d.VirtualInputs.Count; k++)
            if (IsLostVirt(q, k, PdmFactoryDefaults.CanInState(d, seen), PdmFactoryDefaults.CanInState(d, alive)))
                return new PdmShared(q, p, alive, seen, k);
        return null;
    }

    public static IReadOnlyList<PdmShared> Shared(PdmView v) =>
        v.Boards.SelectMany(q => v.Boards.Where(p => p.Role != q.Role).Select(p => SharedOf(v, q, p))).OfType<PdmShared>().ToList();

    // What virtual input k on board q is for the links, or null (not ours)
    public static PdmVirtRole? RoleOfVirt(PdmView v, PdmBoard q, int k)
    {
        if (IsReservedVirt(q, k)) return null;
        var d = q.Device;
        var vi = d.VirtualInputs[k];
        if (vi is not { Enabled: true, Mode: InputMode.Momentary, Not2: false }) return null;
        // old B4 'on': NOT slot OR false
        if (vi is { Not0: true, Cond0: Conditional.Or, Not1: false, Var1: 0, Var2: 0 } && RoleOfVar(v, q, vi.Var0) is { Kind: PdmSlotKind.OldOn } ro)
            return new PdmVirtRole(PdmVirtKind.OldOn, ro.Source, SlotOfVar(d, vi.Var0), false, 0);
        // LOST: SEEN AND NOT ALIVE
        if (vi is { Not0: false, Cond0: Conditional.And, Not1: true, Var2: 0 } && RoleOfVar(v, q, vi.Var0) is { Kind: PdmSlotKind.Seen } rs
            && RoleOfVar(v, q, vi.Var1) is { Kind: PdmSlotKind.Alive } ra && rs.Source.Role == ra.Source.Role)
            return new PdmVirtRole(PdmVirtKind.Lost, rs.Source, -1, false, 0);
        if (vi.Not1) return null;
        // on: LOST OR L | condition: (LOST AND C) OR L | critical: NOT ALIVE in place of LOST
        var three = vi.Var2 != 0;
        var ls = SlotOfVar(d, three ? vi.Var2 : vi.Var1);
        if (ls < 0 || RoleOfSlot(v, q, ls) is not { Kind: PdmSlotKind.Link } rl || !d.CanInputs[ls].TimeoutEnabled) return null;
        if (three ? vi.Cond0 != Conditional.And || vi.Cond1 != Conditional.Or || vi.Var1 == 0 : vi.Cond0 != Conditional.Or) return null;
        if (SharedOf(v, q, rl.Source) is not { } sh) return null;
        var want = vi.Not0 ? PdmFactoryDefaults.CanInState(d, sh.Alive) : PdmFactoryDefaults.VarOf(d, d.VirtualInputs[sh.Lost]);
        return vi.Var0 == want
            ? new PdmVirtRole(three ? PdmVirtKind.Condition : PdmVirtKind.On, rl.Source, ls, vi.Not0, three ? vi.Var1 : 0)
            : null;
    }

    // The link that drives this output, or null (no trigger, or one set by something else)
    public static PdmLink? LinkOf(PdmView v, PdmOutputRow o)
    {
        var q = BoardOf(v, o.Device);
        if (q == null || o.Output.Input == 0) return null;
        var d = o.Device;
        switch (OwnerOf(d, o.Output.Input))
        {
            case DigitalInput di:
                return v.Inputs.FirstOrDefault(r => ReferenceEquals(r.Digital, di)) is { } same ? new PdmLink(o, same, null, null, null) : null;
            case CanInput ci:
            {
                var s = d.CanInputs.IndexOf(ci);
                return RoleOfSlot(v, q, s) is { Kind: PdmSlotKind.Link } r
                    ? new PdmLink(o, DigitalRow(v, r.Source.Role, r.Bit)!, ci.TimeoutEnabled ? PdmLinkLoss.Off : PdmLinkLoss.Hold, s, null)
                    : null;
            }
            case VirtualInput vi:
            {
                var k = d.VirtualInputs.IndexOf(vi);
                if (RoleOfVirt(v, q, k) is not { } vr || vr.Kind == PdmVirtKind.Lost) return null;
                var src = RoleOfSlot(v, q, vr.Slot)!;
                var row = DigitalRow(v, src.Source.Role, src.Bit)!;
                if (vr.Kind == PdmVirtKind.OldOn) return new PdmLink(o, row, PdmLinkLoss.On, vr.Slot, k, OldRecipe: true);
                return new PdmLink(o, row, vr.Kind == PdmVirtKind.Condition ? PdmLinkLoss.Condition : PdmLinkLoss.On, vr.Slot, k,
                    vr.Critical, vr.Cond, vr.Cond != 0 ? CondText(v, q, vr.Cond) : null, false, SharedOf(v, q, vr.Source));
            }
            default:
                return null;
        }
    }

    public static IReadOnlyList<PdmLink> Links(PdmView v) =>
        v.Outputs.Select(o => LinkOf(v, o)).OfType<PdmLink>().ToList();

    public static IReadOnlyList<PdmLink> OldLinks(PdmView v) => Links(v).Where(l => l.OldRecipe).ToList();

    // ---------------- condition picker: the inputs and conditions of the output's board ----------------

    public static IReadOnlyList<PdmCondChoice> CondChoices(PdmView v, PdmBoard q)
    {
        var d = q.Device;
        var list = v.Inputs.Where(r => r.Board == q.Role && r.Digital != null)
            .Select(r => new PdmCondChoice(PdmFactoryDefaults.VarOf(d, r.Digital!), $"{r.Board} IN{r.BoardInput} (input {r.Number}) {r.Name}"))
            .ToList();
        for (var i = 0; i < d.Conditions.Count; i++)
            list.Add(new PdmCondChoice(PdmFactoryDefaults.VarOf(d, d.Conditions[i]), $"{q.Role} condition {i + 1}: {d.Conditions[i].Name}"));
        return list;
    }

    public static IReadOnlyList<PdmCondChoice> CondChoices(PdmView v, int output) =>
        v.Outputs.FirstOrDefault(r => r.Number == output) is { } o && BoardOf(v, o.Device) is { } q ? CondChoices(v, q) : [];

    private static string CondText(PdmView v, PdmBoard q, int var) =>
        CondChoices(v, q).FirstOrDefault(c => c.Var == var)?.Text ?? $"{q.Role} variable {var} ({VarName(q.Device, var)})";

    // ---------------- slot / virtual input use per board ----------------

    public static IReadOnlyList<PdmBoardSlots> Slots(PdmView v)
    {
        var links = Links(v);
        var list = new List<PdmBoardSlots>();
        foreach (var q in v.Boards)
        {
            var d = q.Device;
            var mine = links.Where(l => l.Out.Board == q.Role).ToList();
            var shared = v.Boards.Where(p => p.Role != q.Role).Select(p => SharedOf(v, q, p)).OfType<PdmShared>().ToList();
            int Users(PdmShared sh) => mine.Count(l => l.Shared?.Source.Role == sh.Source.Role);
            string LinkText(PdmLink l) =>
                $"link: {l.In.Board} IN{l.In.BoardInput} (input {l.In.Number}) -> OUT{l.Out.BoardOutput} (output {l.Out.Number}), {l.LossText}";

            var cans = new List<PdmSlotUse>();
            for (var s = 0; s < d.CanInputs.Count; s++)
            {
                var c = d.CanInputs[s];
                var link = mine.FirstOrDefault(l => l.Slot == s);
                var sh = shared.FirstOrDefault(x => x.Alive == s || x.Seen == s);
                var role = RoleOfSlot(v, q, s);
                cans.Add(link != null ? new PdmSlotUse(q.Role, s, false, true, LinkText(link))
                    : sh != null && Users(sh) > 0
                        ? new PdmSlotUse(q.Role, s, false, true, sh.Alive == s
                            ? $"shared: {sh.Source.Role} alive (its message 37 heard in the last {c.Timeout / 1000.0:0.##} s), for {Users(sh)} on / condition link(s)"
                            : $"shared: {sh.Source.Role} seen (a message 37 heard since power-up), for {Users(sh)} on / condition link(s)", true)
                    : role is { Kind: PdmSlotKind.Alive or PdmSlotKind.Seen }
                        ? new PdmSlotUse(q.Role, s, false, true, $"shared {role.Kind.ToString().ToUpperInvariant()} for {role.Source.Role}, no link uses it (Remove unused)", true)
                    : role != null
                        ? new PdmSlotUse(q.Role, s, false, true, $"link slot for {role.Source.Role} IN{role.Bit + 1}, no output uses it (Remove unused)")
                    : IsFanSlot(q, s) ? new PdmSlotUse(q.Role, s, false, false, "fan logic (A1 / B board temperature), reserved")
                    : IsFreeSlot(q, s) ? new PdmSlotUse(q.Role, s, true, false, "free")
                    : new PdmSlotUse(q.Role, s, false, false, $"set by hand ({(c.Enabled ? "enabled" : "disabled")}, ID 0x{c.Id:X3}): never changed here"));
            }

            var virts = new List<PdmSlotUse>();
            for (var k = 0; k < d.VirtualInputs.Count; k++)
            {
                var link = mine.FirstOrDefault(l => l.Virt == k);
                var sh = shared.FirstOrDefault(x => x.Lost == k);
                var role = RoleOfVirt(v, q, k);
                virts.Add(link != null ? new PdmSlotUse(q.Role, k, false, true, LinkText(link))
                    : sh != null && Users(sh) > 0
                        ? new PdmSlotUse(q.Role, k, false, true, $"shared: {sh.Source.Role} lost (seen AND NOT alive), for {Users(sh)} on / condition link(s)", true)
                    : role is { Kind: PdmVirtKind.Lost }
                        ? new PdmSlotUse(q.Role, k, false, true, $"shared LOST for {role.Source.Role}, no link uses it (Remove unused)", true)
                    : role != null
                        ? new PdmSlotUse(q.Role, k, false, true, $"link virtual input for {role.Source.Role}, no output uses it (Remove unused)")
                    : IsFanVirt(q, k) ? new PdmSlotUse(q.Role, k, false, false, "fan logic, reserved")
                    : IsReservedVirt(q, k) ? new PdmSlotUse(q.Role, k, false, false, "load-shed example, reserved")
                    : IsFreeVirt(q, k) ? new PdmSlotUse(q.Role, k, true, false, "free")
                    : new PdmSlotUse(q.Role, k, false, false, "set by hand: never changed here"));
            }
            list.Add(new PdmBoardSlots(q.Role, cans, virts));
        }
        return list;
    }

    // ---------------- edits (PC side) ----------------

    private static void Reset(CanInput c)
    {
        var f = new CanInput(c.Number, "canInput" + c.Number); // fresh-board values (proven equal: PdmB3LiveSimTests)
        (c.Name, c.Enabled, c.TimeoutEnabled, c.Timeout, c.Id, c.StartBit, c.BitLength) = (f.Name, f.Enabled, f.TimeoutEnabled, f.Timeout, f.Id, f.StartBit, f.BitLength);
        (c.Factor, c.Offset, c.ByteOrder, c.Signed, c.Operator, c.Operand, c.Mode, c.Bus) = (f.Factor, f.Offset, f.ByteOrder, f.Signed, f.Operator, f.Operand, f.Mode, f.Bus);
    }

    private static void Reset(VirtualInput vi)
    {
        var f = new VirtualInput(vi.Number, "virtualInput" + vi.Number);
        (vi.Name, vi.Enabled, vi.Not0, vi.Var0, vi.Cond0, vi.Not1, vi.Var1) = (f.Name, f.Enabled, f.Not0, f.Var0, f.Cond0, f.Not1, f.Var1);
        (vi.Cond1, vi.Not2, vi.Var2, vi.Mode) = (f.Cond1, f.Not2, f.Var2, f.Mode);
    }

    private static void SetSlot(CanInput c, string name, int id, int bit, Operator op, double operand, bool timeout)
    {
        (c.Name, c.Enabled, c.TimeoutEnabled, c.Timeout, c.Id, c.StartBit, c.BitLength) = (name, true, timeout, TimeoutMs, id, bit, 1);
        (c.Factor, c.Offset, c.ByteOrder, c.Signed, c.Operator, c.Operand, c.Mode, c.Bus) =
            (1.0, 0.0, ByteOrder.LittleEndian, false, op, operand, InputMode.Momentary, 0);
    }

    private static void SetVirt(VirtualInput vi, string name, bool not0, int var0, Conditional c0, bool not1, int var1,
        Conditional c1 = Conditional.And, int var2 = 0)
    {
        (vi.Name, vi.Enabled, vi.Not0, vi.Var0, vi.Cond0, vi.Not1, vi.Var1) = (name, true, not0, var0, c0, not1, var1);
        (vi.Cond1, vi.Not2, vi.Var2, vi.Mode) = (c1, false, var2, InputMode.Momentary);
    }

    // all-or-nothing: the CAN inputs, virtual inputs and outputs of a board as they are now
    private static Action Snapshot(FwDevice d)
    {
        var ps = d.CanInputs.SelectMany(c => c.Params).Concat(d.VirtualInputs.SelectMany(x => x.Params))
            .Concat(d.Outputs.SelectMany(x => x.Params)).ToList();
        var vals = ps.Select(p => p.GetValue()).ToList();
        var names = d.CanInputs.Select(c => c.Name).ToList();
        var vnames = d.VirtualInputs.Select(x => x.Name).ToList();
        return () =>
        {
            for (var i = 0; i < ps.Count; i++) ps[i].SetValue(vals[i]);
            for (var i = 0; i < names.Count; i++) d.CanInputs[i].Name = names[i];
            for (var i = 0; i < vnames.Count; i++) d.VirtualInputs[i].Name = vnames[i];
        };
    }

    // Why this output can never be linked, or null
    private static string? Unlinkable(PdmOutputRow o)
    {
        var what = $"Output {o.Number} ({o.Board} OUT{o.BoardOutput})";
        if (o.Board == "A2" && o.BoardOutput - 1 == PdmFactoryDefaults.FanOutput) return $"{what} runs the fans: its trigger is the fan logic.";
        if (o.Output.PrimaryOutput >= 0) return $"{what} is paired: it follows output {o.Output.PrimaryOutput + 1} of {o.Board}.";
        return null;
    }

    private static string? BadMode(PdmView v, PdmBoard q, PdmInputRow inRow, PdmOutputRow o, PdmLinkLoss loss, bool critical, int cond)
    {
        if (inRow.Board == q.Role) return null; // same board: no CAN message, no loss mode
        if (critical && !UsesShared(loss))
            return "Critical changes 'on' and 'condition' only: with 'off' or 'hold' the output is off before the first frame anyway.";
        if (loss == PdmLinkLoss.Condition && CondChoices(v, q).All(c => c.Var != cond))
            return $"Pick the condition for output {o.Number}: one of {q.Role}'s inputs or conditions.";
        return null;
    }

    // The output already has a trigger (a link or set elsewhere): the text for "already assigned. Overwrite?" (g1)
    public static string? Conflict(PdmView v, int output)
    {
        var o = v.Outputs.FirstOrDefault(r => r.Number == output);
        if (o == null || o.Output.Input == 0) return null;
        var what = $"Output {o.Number} ({o.Board} OUT{o.BoardOutput})";
        return LinkOf(v, o) is { } l
            ? $"{what} is already assigned: linked to input {l.In.Number} ({l.In.Board} IN{l.In.BoardInput})."
            : $"{what} is already assigned: its trigger was set elsewhere ({VarName(o.Device, o.Output.Input)}, variable {o.Output.Input}).";
    }

    // Writes the link (the output has no trigger now). null = made; else why not (the caller restores the board)
    private static string? Make(PdmView v, PdmBoard q, PdmOutputRow o, PdmInputRow inRow, PdmLinkLoss loss, bool critical, int cond)
    {
        var d = q.Device;
        if (inRow.Board == q.Role)
        {
            o.Output.Input = PdmFactoryDefaults.VarOf(d, inRow.Digital!);
            return null;
        }
        var p = v.Boards.Single(b => b.Role == inRow.Board);
        var free = Enumerable.Range(0, d.CanInputs.Count).Where(i => IsFreeSlot(q, i)).ToList();
        var freeV = Enumerable.Range(0, d.VirtualInputs.Count).Where(k => IsFreeVirt(q, k)).ToList();
        var needShared = UsesShared(loss);
        var sh = needShared ? SharedOf(v, q, p) : null;
        var needSlots = needShared && sh == null ? 3 : 1;
        if (free.Count < needSlots)
        {
            var u = Slots(v).Single(b => b.Board == q.Role);
            return $"{q.Role} has too few free CAN inputs: this link needs {(needSlots == 3 ? $"3 (the shared '{p.Role} alive' and '{p.Role} seen' and its own)" : "1")}, " +
                   $"{free.Count} free ({u.LinkCanInputs + u.SharedCanInputs} used by links, the rest by the fan logic or set by hand).";
        }
        var msg = p.Device.BaseId + StatusOffset;
        int? k = null;
        if (needShared)
        {
            var needV = sh == null ? 2 : 1;
            if (freeV.Count < needV)
                return $"{q.Role} has too few free virtual inputs: this '{Word(loss)}' link needs {(needV == 2 ? $"2 (the shared '{p.Role} lost' and its own)" : "1")}, " +
                       $"{freeV.Count} free. Choose 'off' or 'hold'.";
            if (sh == null)
            {
                var (a, s0, l) = (free[0], free[1], freeV[0]);
                SetSlot(d.CanInputs[a], $"{p.Role} alive (links)", msg, 0, Operator.GreaterThanOrEqual, 0.0, true);
                SetSlot(d.CanInputs[s0], $"{p.Role} seen (links)", msg, 0, Operator.GreaterThanOrEqual, 0.0, false);
                SetVirt(d.VirtualInputs[l], $"{p.Role} lost (links)", false, PdmFactoryDefaults.CanInState(d, s0), Conditional.And,
                    true, PdmFactoryDefaults.CanInState(d, a));
                free.RemoveRange(0, 2);
                freeV.RemoveAt(0);
                sh = new PdmShared(q, p, a, s0, l);
            }
            var lost = sh.Lost;
            k = freeV.Where(x => critical || x > lost).Cast<int?>().FirstOrDefault();
            if (k == null)
                return $"{q.Role} has no free virtual input after the shared '{p.Role} lost' (virtual input {lost + 1}), which a non-critical " +
                       $"'{Word(loss)}' link must run after: free one above it, mark the output critical, or choose 'off' / 'hold'.";
        }

        var s = free[0];
        var name = $"Link {inRow.Board} IN{inRow.BoardInput} -> OUT{o.BoardOutput}";
        SetSlot(d.CanInputs[s], name, msg, inRow.BoardInput - 1, Operator.Equal, 1.0, loss != PdmLinkLoss.Hold);
        var lvar = PdmFactoryDefaults.CanInState(d, s);
        if (k is { } kk)
        {
            var vi = d.VirtualInputs[kk];
            var first = critical ? PdmFactoryDefaults.CanInState(d, sh!.Alive) : PdmFactoryDefaults.VarOf(d, d.VirtualInputs[sh!.Lost]);
            if (loss == PdmLinkLoss.On) SetVirt(vi, name + " (on at loss)", critical, first, Conditional.Or, false, lvar);
            else SetVirt(vi, name + " (condition at loss)", critical, first, Conditional.And, false, cond, Conditional.Or, lvar);
            o.Output.Input = PdmFactoryDefaults.VarOf(d, vi);
        }
        else o.Output.Input = lvar;
        return null;
    }

    private static void RemoveLink(PdmLink link)
    {
        link.Out.Output.Input = 0;
        if (link.Slot is { } s) Reset(link.Out.Device.CanInputs[s]);
        if (link.Virt is { } k) Reset(link.Out.Device.VirtualInputs[k]);
    }

    private static string? KeepFor(PdmBoard q, PdmInputRow inRow, PdmLinkLoss loss) =>
        UsesShared(loss) && inRow.Board != q.Role ? inRow.Board : null;

    // a shared ALIVE / SEEN / LOST that no on / condition link uses any more: back to fresh-board values
    private static void FreeUnusedShared(PdmView v, PdmBoard q, string? keep = null)
    {
        var links = Links(v);
        foreach (var p in v.Boards.Where(b => b.Role != q.Role && b.Role != keep))
            if (SharedOf(v, q, p) is { } sh && !links.Any(l => l.Out.Board == q.Role && l.Shared?.Source.Role == p.Role))
            {
                Reset(q.Device.CanInputs[sh.Alive]);
                Reset(q.Device.CanInputs[sh.Seen]);
                Reset(q.Device.VirtualInputs[sh.Lost]);
            }
    }

    // null = link made on the PC; else why not (nothing changed). An output that already has a trigger (Conflict) is
    // only replaced with overwrite (the UI asks "already assigned. Overwrite?" first); a trigger set elsewhere is only
    // unhooked from the output, the function behind it is never changed.
    public static string? Add(PdmView v, int input, int output, PdmLinkLoss loss = DefaultLoss, bool critical = false, int cond = 0,
        bool overwrite = false)
    {
        var inRow = v.Inputs.FirstOrDefault(r => r.Number == input && r.Digital != null);
        if (inRow == null) return $"Input {input} is not a digital input of this PDM (1-24, its board must be in the project).";
        var o = v.Outputs.FirstOrDefault(r => r.Number == output);
        if (o == null) return $"Output {output} is not in this PDM (1-24, its board must be in the project).";
        if (Unlinkable(o) is { } no) return no;
        var q = BoardOf(v, o.Device)!;
        if (BadMode(v, q, inRow, o, loss, critical, cond) is { } bad) return bad;
        if (!overwrite && Conflict(v, output) is { } taken) return taken;

        var restore = Snapshot(o.Device);
        if (LinkOf(v, o) is { } old) RemoveLink(old);
        o.Output.Input = 0;
        FreeUnusedShared(v, q, KeepFor(q, inRow, loss)); // so a mode without them gets the lowest slots
        if (Make(v, q, o, inRow, loss, critical, cond) is { } why)
        {
            restore();
            return why;
        }
        FreeUnusedShared(v, q);
        return null;
    }

    // null = removed on the PC (what it used back to fresh-board values, output trigger none)
    public static string? Remove(PdmView v, int output)
    {
        var o = v.Outputs.FirstOrDefault(r => r.Number == output);
        if (o == null || LinkOf(v, o) is not { } link) return $"Output {output} has no link.";
        RemoveLink(link);
        FreeUnusedShared(v, BoardOf(v, o.Device)!);
        return null;
    }

    // Change a link's source input and / or loss mode (re-made in place; it may move to a lower free slot)
    public static string? Change(PdmView v, int output, int input, PdmLinkLoss loss, bool critical = false, int cond = 0)
    {
        var o = v.Outputs.FirstOrDefault(r => r.Number == output);
        if (o == null || LinkOf(v, o) is not { } link) return $"Output {output} has no link.";
        var inRow = v.Inputs.FirstOrDefault(r => r.Number == input && r.Digital != null);
        if (inRow == null) return $"Input {input} is not a digital input of this PDM (1-24, its board must be in the project).";
        var q = BoardOf(v, o.Device)!;
        if (BadMode(v, q, inRow, o, loss, critical, cond) is { } bad) return bad;
        var restore = Snapshot(o.Device);
        RemoveLink(link);
        FreeUnusedShared(v, q, KeepFor(q, inRow, loss));
        if (Make(v, q, o, inRow, loss, critical, cond) is { } why)
        {
            restore();
            return why;
        }
        FreeUnusedShared(v, q);
        return null;
    }

    public static string? SetMode(PdmView v, int output, PdmLinkLoss loss, bool critical = false, int cond = 0)
    {
        var o = v.Outputs.FirstOrDefault(r => r.Number == output);
        if (o == null || LinkOf(v, o) is not { } link) return $"Output {output} has no link.";
        if (!link.CrossBoard) return "A same-board link has no CAN message to lose.";
        return Change(v, output, link.In.Number, loss, critical, cond);
    }

    // a new source input, the loss mode kept (a new cross-board link gets the default)
    public static string? SetInput(PdmView v, int output, int input)
    {
        var o = v.Outputs.FirstOrDefault(r => r.Number == output);
        if (o == null || LinkOf(v, o) is not { } link) return $"Output {output} has no link.";
        return link.Loss is { } l
            ? Change(v, output, input, l, link.Critical, link.Cond)
            : Change(v, output, input, DefaultLoss);
    }

    // Old B4 "on" links (on at power-up until the first frame) -> the w1 'on' recipe. Returns what could not be done
    // (those links are kept as they were).
    public static IReadOnlyList<string> Upgrade(PdmView v)
    {
        var fails = new List<string>();
        foreach (var l in OldLinks(v))
            if (Change(v, l.Out.Number, l.In.Number, PdmLinkLoss.On) is { } why)
                fails.Add($"Output {l.Out.Number}: {why}");
        return fails;
    }

    // Link slots / virtual inputs and shared ALIVE / SEEN / LOST that no output uses (e.g. the output trigger was
    // changed by hand): back to fresh-board values
    public static int RemoveUnused(PdmView v)
    {
        var links = Links(v);
        var resets = new List<Action>();
        foreach (var q in v.Boards)
        {
            var d = q.Device;
            var mine = links.Where(l => l.Out.Board == q.Role).ToList();
            var usedS = mine.Where(l => l.Slot != null).Select(l => l.Slot!.Value)
                .Concat(mine.Where(l => l.Shared != null).SelectMany(l => new[] { l.Shared!.Alive, l.Shared.Seen })).ToHashSet();
            var usedV = mine.Where(l => l.Virt != null).Select(l => l.Virt!.Value)
                .Concat(mine.Where(l => l.Shared != null).Select(l => l.Shared!.Lost)).ToHashSet();
            for (var s = 0; s < d.CanInputs.Count; s++)
                if (!usedS.Contains(s) && RoleOfSlot(v, q, s) != null)
                {
                    var c = d.CanInputs[s];
                    resets.Add(() => Reset(c));
                }
            for (var k = 0; k < d.VirtualInputs.Count; k++)
                if (!usedV.Contains(k) && RoleOfVirt(v, q, k) != null)
                {
                    var vi = d.VirtualInputs[k];
                    resets.Add(() => Reset(vi));
                }
        }
        foreach (var r in resets) r();
        return resets.Count;
    }

    // Before board `role` moves to newBase: the slots on the other boards that listen to its msg 37 follow it
    public static IReadOnlyList<string> FollowBaseId(PdmView v, string role, int newBase)
    {
        var list = new List<string>();
        foreach (var q in v.Boards.Where(b => b.Role != role))
        {
            var moves = new List<(int Slot, PdmSlotRole Role)>();
            for (var s = 0; s < q.Device.CanInputs.Count; s++)
                if (RoleOfSlot(v, q, s) is { } r && r.Source.Role == role) moves.Add((s, r));
            foreach (var (s, r) in moves)
            {
                q.Device.CanInputs[s].Id = newBase + StatusOffset;
                var what = r.Kind is PdmSlotKind.Alive or PdmSlotKind.Seen
                    ? $"shared {r.Kind.ToString().ToLowerInvariant()} for {role}"
                    : $"link from {role} IN{r.Bit + 1}";
                list.Add($"{q.Role} CAN input {s + 1} ({what}) -> 0x{newBase + StatusOffset:X3}");
            }
        }
        return list;
    }

    // Is slot s on board q one of ours that follows `role`? (PdmLinked.BaseIdWarnings leaves those out)
    public static bool FollowsBoard(PdmView v, PdmBoard q, int s, string role) =>
        RoleOfSlot(v, q, s) is { } r && r.Source.Role == role;

    // Things that make a link do nothing or not do what its mode says (shown next to it; not refused)
    public static IReadOnlyList<string> Warnings(PdmLink l)
    {
        var w = new List<string>();
        var d = l.Out.Device;
        if (!l.Out.Output.Enabled) w.Add($"output {l.Out.Number} is not enabled");
        if (l.In.Digital is { Enabled: false }) w.Add($"input {l.In.Number} is not enabled on {l.In.Board}");
        if (l.Cond != 0)
            switch (OwnerOf(d, l.Cond))
            {
                case Condition { Enabled: false }:
                case DigitalInput { Enabled: false }:
                    w.Add($"the condition {l.CondText} is not enabled");
                    break;
            }
        if (l.OldRecipe) w.Add("old recipe: on at power-up until the first frame (Upgrade)");
        if (l is { Shared: { } sh, Virt: { } k, Critical: false } && k < sh.Lost)
            w.Add($"virtual input {k + 1} runs before the shared '{sh.Source.Role} lost' (virtual input {sh.Lost + 1}): a short drop (about 2 ms) at the time-out");
        if (l is { Shared: { } sh2, Slot: { } s } && d.CanInputs[s].Timeout != d.CanInputs[sh2.Alive].Timeout)
            w.Add($"time-out {d.CanInputs[s].Timeout} ms differs from the shared '{sh2.Source.Role} alive' ({d.CanInputs[sh2.Alive].Timeout} ms): the output can blip at loss");
        return w;
    }
}
