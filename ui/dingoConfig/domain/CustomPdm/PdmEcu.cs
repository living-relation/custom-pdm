using domain.Devices;
using domain.Devices.Functions;
using domain.Enums;

namespace domain.CustomPdm;

// custom-pdm one-PDM editor, phase 2 (editor2): outputs driven by the ECU over CAN (DECISIONS 2026-11-16 k1-k4
// defaults, docs/car-can-dummy/ecu-pdm-control-plan.dummy.md): the ECU sends ONE custom TX stream (default ID 0x3F4,
// every 50 ms), one byte per command (1 = on, 0 = off), and the output is switched by the ECU only.
// Recipe on the OUTPUT's board Q (stock functions only, the same as the PdmLinks w1 recipe with the ECU stream in
// place of another board's msg 37):
//   CMD   = CAN input on the stream: start bit = byte x 8, length 8, LITTLE endian, Equal 1. (A single byte reads the
//           same in both byte orders; LittleEndian is used because the firmware's BigEndian start bit is the DBC
//           Motorola MSB position, byte x 8 + 7 (utils/dbc.cpp DecodeBE), so "byte x 8" with BigEndian would be wrong.)
//   off   = CMD, time-out on (= the loss delay)            -> off after the delay
//   hold  = CMD, time-out off                              -> keeps its last state (off at power-up)
//   on    = virtual input "LOST OR CMD"                    -> on after the delay; off until the first frame
//   condition = "(LOST AND C) OR CMD"                      -> follows C (an input / condition of Q) at loss
//   ALIVE / SEEN / LOST per (stream, delay) on Q, shared by every on / condition ECU output of Q (PdmLinks.MakeShared).
// Loss delay range: 3 x the stream period (150 ms at 50 ms) to 10 s, default 1 s (= 20 missed frames at 50 ms).
// Ownership: read back from the params (no PC-only state). A CAN input is an ECU command when it has the CMD shape
// on an ID that is not one of this PDM's boards and an output reads it (directly or through its on / condition
// virtual input). Cost on Q: 1 CAN input per output (+ 1 virtual input for on / condition), plus per (stream, delay)
// with on / condition outputs 1 ALIVE + 1 LOST, and 1 SEEN per stream.
public record PdmEcuLink(PdmOutputRow Out, int Id, int Byte, PdmLinkLoss Loss, int DelayMs, int Slot, int? Virt,
    int Cond = 0, (int Alive, int Seen, int Lost)? Shared = null)
{
    public string Source => $"ECU 0x{Id:X3} byte {Byte}";

    public string LossText => Loss switch
    {
        PdmLinkLoss.Off => $"off {PdmLinks.DelayText(DelayMs)} after the ECU frames stop",
        PdmLinkLoss.Hold => "keeps its last state (off at power-up)",
        PdmLinkLoss.On => $"on {PdmLinks.DelayText(DelayMs)} after the ECU frames stop; off until the first frame",
        _ => $"follows a condition {PdmLinks.DelayText(DelayMs)} after the ECU frames stop; off until the first frame"
    };

    public string Words => $"{Source} = 1 (ECU only; {LossText})";
}

public static class PdmEcu
{
    public const int DefaultId = 0x3F4, DefaultPeriodMs = 50;   // k1 / k3 (preliminary plan, dummy)
    public const int Bytes = 8;

    public static int StartBit(int byteIndex, ByteOrder order) => order == ByteOrder.BigEndian ? byteIndex * 8 + 7 : byteIndex * 8;

    private static PdmBoard BoardOf(PdmView v, PdmOutputRow o) => v.Boards.Single(b => ReferenceEquals(b.Device, o.Device));

    // an ID used by a board of this PDM (its cyclic / config block base .. base + 0x3F)
    public static bool IsPdmId(PdmView v, int id) => v.Boards.Any(b => id >= b.Device.BaseId && id < b.Device.BaseId + 0x40);

    public static bool IsCmdShape(PdmView v, CanInput c) =>
        c is { Enabled: true, Ide: false, BitLength: 8, Factor: 1.0, Offset: 0.0, ByteOrder: ByteOrder.LittleEndian, Signed: false,
            Operator: Operator.Equal, Operand: 1.0, Mode: InputMode.Momentary, Bus: 0 }
        && c.StartBit % 8 == 0 && c.StartBit < 64 && c.Id is > 0 and <= 0x7FF && !IsPdmId(v, c.Id);

    private static object? StateOwner(FwDevice d, int var)
    {
        if (var <= PdmTriggers.AlwaysOnVar) return null;
        var owner = d.VarMap.FirstOrDefault(x => x.VariableIndex == var)?.Owner;
        return owner != null && PdmFactoryDefaults.VarOf(d, owner) == var ? owner : null;
    }

    // The ECU command that drives this output, or null
    public static PdmEcuLink? Of(PdmView v, PdmOutputRow o)
    {
        var d = o.Device;
        if (o.Output.Input == 0 || v.Boards.All(b => !ReferenceEquals(b.Device, d))) return null;
        var q = BoardOf(v, o);
        switch (StateOwner(d, o.Output.Input))
        {
            case CanInput c when IsCmdShape(v, c):
                return new PdmEcuLink(o, c.Id, c.StartBit / 8, c.TimeoutEnabled ? PdmLinkLoss.Off : PdmLinkLoss.Hold,
                    c.TimeoutEnabled ? c.Timeout : PdmLinks.TimeoutMs, d.CanInputs.IndexOf(c), null);
            case VirtualInput vi when vi is { Enabled: true, Mode: InputMode.Momentary, Not0: false, Not1: false, Not2: false }:
            {
                var three = vi.Var2 != 0;
                if (StateOwner(d, three ? vi.Var2 : vi.Var1) is not CanInput c || !IsCmdShape(v, c) || !c.TimeoutEnabled) return null;
                if (three ? vi.Cond0 != Conditional.And || vi.Cond1 != Conditional.Or || vi.Var1 == 0 : vi.Cond0 != Conditional.Or) return null;
                if (PdmLinks.SharedAt(q, c.Id, c.Timeout) is not { } sh || vi.Var0 != PdmFactoryDefaults.VarOf(d, d.VirtualInputs[sh.Lost])) return null;
                return new PdmEcuLink(o, c.Id, c.StartBit / 8, three ? PdmLinkLoss.Condition : PdmLinkLoss.On, c.Timeout,
                    d.CanInputs.IndexOf(c), d.VirtualInputs.IndexOf(vi), three ? vi.Var1 : 0, sh);
            }
        }
        return null;
    }

    public static IReadOnlyList<PdmEcuLink> All(PdmView v) => v.Outputs.Select(o => Of(v, o)).OfType<PdmEcuLink>().ToList();

    // the ECU frame IDs some output of board q listens to
    private static IEnumerable<int> Streams(PdmView v, PdmBoard q) => All(v).Where(l => l.Out.Board == q.Role).Select(l => l.Id).Distinct();

    // texts for the Links panel's slot list (null: not an ECU slot)
    public static string? SlotText(PdmView v, PdmBoard q, int s)
    {
        foreach (var l in All(v).Where(l => l.Out.Board == q.Role))
        {
            if (l.Slot == s) return $"ECU command: {l.Source} -> output {l.Out.Number}, {l.LossText}";
            if (l.Shared is { } sh && (sh.Alive == s || sh.Seen == s))
                return sh.Alive == s ? $"shared: ECU 0x{l.Id:X3} alive ({PdmLinks.DelayText(l.DelayMs)})" : $"shared: ECU 0x{l.Id:X3} seen";
        }
        return null;
    }

    public static string? VirtText(PdmView v, PdmBoard q, int k)
    {
        foreach (var l in All(v).Where(l => l.Out.Board == q.Role))
        {
            if (l.Virt == k) return $"ECU command: {l.Source} -> output {l.Out.Number}, {l.LossText}";
            if (l.Shared is { } sh && sh.Lost == k) return $"shared: ECU 0x{l.Id:X3} lost ({PdmLinks.DelayText(l.DelayMs)})";
        }
        return null;
    }

    // ---------------- cost ----------------

    public static IReadOnlyDictionary<PdmResKind, int> Cost(PdmView v, PdmOutputRow o, int id, PdmLinkLoss loss, int delayMs)
    {
        var c = new Dictionary<PdmResKind, int> { [PdmResKind.CanInput] = 1 };
        if (!PdmLinks.UsesShared(loss)) return c;
        c[PdmResKind.VirtualInput] = 1;
        var q = BoardOf(v, o);
        if (PdmLinks.SharedAt(q, id, delayMs) == null)
        {
            c[PdmResKind.CanInput] += PdmLinks.SeenAt(q, id) >= 0 ? 1 : 2;
            c[PdmResKind.VirtualInput] += 1;
        }
        return c;
    }

    // ---------------- set / remove ----------------

    public static string? Problem(PdmView v, PdmOutputRow o, int id, int byteIndex, PdmLinkLoss loss, int delayMs, int cond, int periodMs)
    {
        if (PdmTriggers.Unsettable(o) is { } no) return no;
        if (id is < 1 or > 0x7FF) return "The ECU frame ID must be a standard (11-bit) ID, 0x001 to 0x7FF.";
        if (IsPdmId(v, id)) return $"0x{id:X3} is inside a PDM board's own ID block: pick the ECU's stream ID (default 0x{DefaultId:X3}).";
        if (byteIndex is < 0 or >= Bytes) return "The command byte must be 0 to 7.";
        if (periodMs is < 1 or > 5000) return "The ECU stream period must be 1 to 5000 ms.";
        if (loss != PdmLinkLoss.Hold && PdmLinks.BadDelay(delayMs, periodMs) is { } bad) return bad;
        if (loss == PdmLinkLoss.Condition && PdmLinks.CondChoices(v, BoardOf(v, o)).All(c => c.Var != cond))
            return $"Pick the condition for output {o.Number}: one of {o.Board}'s inputs or conditions.";
        return null;
    }

    // null = set on the PC (Write All sends it); else why not (nothing changed). The output's trigger is replaced:
    // something that is not this output's own ECU command asks "already assigned. Overwrite?" first (overwrite).
    public static string? Set(PdmView v, int output, int id, int byteIndex, PdmLinkLoss loss = PdmLinkLoss.Off, int delayMs = PdmLinks.TimeoutMs,
        int cond = 0, bool overwrite = false, int periodMs = DefaultPeriodMs)
    {
        var o = v.Outputs.FirstOrDefault(r => r.Number == output);
        if (o == null) return $"Output {output} is not in this PDM (1-24, its board must be in the project).";
        if (Problem(v, o, id, byteIndex, loss, delayMs, cond, periodMs) is { } bad) return bad;
        if (!overwrite && Conflict(v, output) is { } taken) return taken;
        var q = BoardOf(v, o);
        var d = q.Device;
        var restore = PdmSnapshot.Take([d]);
        PdmTriggers.Release(v, o);
        var free = Enumerable.Range(0, d.CanInputs.Count).Where(i => PdmLinks.IsFreeSlot(q, i)).ToList();
        var freeV = Enumerable.Range(0, d.VirtualInputs.Count).Where(k => PdmLinks.IsFreeVirt(q, k)).ToList();
        var need = Cost(v, o, id, loss, delayMs);
        var haveC = free.Count;
        var haveV = freeV.Count;
        if (haveC < need[PdmResKind.CanInput] || haveV < need.GetValueOrDefault(PdmResKind.VirtualInput))
        {
            restore.Restore();
            return $"{q.Role} is full: this ECU output needs {PdmTriggers.CostText(need)}; {q.Role} has {haveC} CAN inputs and {haveV} virtual inputs free. Nothing changed.";
        }
        int? k = null;
        (int Alive, int Seen, int Lost)? sh = null;
        if (PdmLinks.UsesShared(loss))
        {
            sh = PdmLinks.SharedAt(q, id, delayMs);
            if (sh == null)
            {
                PdmLinks.MakeShared(q, id, delayMs, $"ECU 0x{id:X3}", free, freeV, out var made);
                sh = made;
            }
            var lost = sh.Value.Lost;
            k = freeV.Where(x => x > lost).Cast<int?>().FirstOrDefault();
            if (k == null)
            {
                restore.Restore();
                return $"{q.Role} has no free virtual input after the shared 'ECU lost' (virtual input {lost + 1}), which an '{loss.ToString().ToLowerInvariant()}' output must run after: free one above it, or choose 'off' / 'hold'.";
            }
        }
        var s = free[0];
        var name = $"ECU 0x{id:X3} byte {byteIndex} -> OUT{o.BoardOutput}";
        PdmLinks.SetSlot(d.CanInputs[s], name, id, StartBit(byteIndex, ByteOrder.LittleEndian), Operator.Equal, 1.0, loss != PdmLinkLoss.Hold, delayMs, length: 8);
        var cvar = PdmFactoryDefaults.CanInState(d, s);
        if (k is { } kk)
        {
            var vi = d.VirtualInputs[kk];
            var lostVar = PdmFactoryDefaults.VarOf(d, d.VirtualInputs[sh!.Value.Lost]);
            if (loss == PdmLinkLoss.On) PdmLinks.SetVirt(vi, name + " (on at loss)", false, lostVar, Conditional.Or, false, cvar);
            else PdmLinks.SetVirt(vi, name + " (condition at loss)", false, lostVar, Conditional.And, false, cond, Conditional.Or, cvar);
            o.Output.Input = PdmFactoryDefaults.VarOf(d, vi);
        }
        else o.Output.Input = cvar;
        return null;
    }

    // the output's trigger when it is something other than an ECU command: text for "already assigned. Overwrite?"
    public static string? Conflict(PdmView v, int output)
    {
        var o = v.Outputs.FirstOrDefault(r => r.Number == output);
        if (o == null || o.Output.Input == 0 || Of(v, o) != null) return null;
        return PdmTriggers.Conflict(v, output) ?? $"Output {o.Number} ({o.Board} OUT{o.BoardOutput}) is already assigned to {PdmTriggers.Of(PdmModel.Build(v), output).Words}.";
    }

    // null = removed on the PC (its CAN input / virtual input back to fresh-board values; unused ALIVE / SEEN / LOST too)
    public static string? Remove(PdmView v, int output)
    {
        var o = v.Outputs.FirstOrDefault(r => r.Number == output);
        if (o == null || Of(v, o) is not { } l) return $"Output {output} is not driven by the ECU.";
        var q = BoardOf(v, o);
        var d = q.Device;
        o.Output.Input = 0;
        PdmLinks.Reset(d.CanInputs[l.Slot]);
        if (l.Virt is { } k) PdmLinks.Reset(d.VirtualInputs[k]);
        var left = All(v).Where(x => x.Out.Board == q.Role && x.Id == l.Id && x.Shared != null).ToList();
        PdmLinks.FreeSharedAt(q, l.Id, lostVar => left.Any(x => PdmFactoryDefaults.VarOf(d, d.VirtualInputs[x.Shared!.Value.Lost]) == lostVar));
        return null;
    }

    // ---------------- CAN values (numbers from the ECU / any device, for levels and fan curves) ----------------

    // A CAN input that reads a number (e.g. ECU coolant temperature): ID, first byte, length, byte order, signed,
    // factor / offset (value = raw x factor + offset). Its operator is ">= -1e9" (always true), so the input is
    // "on" whenever frames come; the number is its Value. Set by hand from the PDM's point of view: it shows in the
    // value lists of levels and fan curves. Returns the slot index, or the reason in why.
    public const double AnyValue = -1e9;

    public static int AddValue(PdmView v, string role, string name, int id, int byteIndex, int length, ByteOrder order, bool signed,
        double factor, double offset, int timeoutMs, out string? why)
    {
        if (byteIndex is < 0 or >= Bytes) { why = "The value must fit in the 8 data bytes (first byte 0-7, length 1-32 bits)."; return -1; }
        return AddValueAt(v, role, name, id, StartBit(byteIndex, order), length, order, signed, factor, offset, timeoutMs, false, out why);
    }

    // editor2b: by start bit (DBC rule: little endian = LSB, big endian = MSB); allowPdmId: another board's cyclic signal
    public static int AddValueAt(PdmView v, string role, string name, int id, int startBit, int length, ByteOrder order, bool signed,
        double factor, double offset, int timeoutMs, bool allowPdmId, out string? why)
    {
        why = null;
        var byteIndex = startBit / 8;
        var q = v.Boards.FirstOrDefault(b => b.Role == role);
        if (q == null) { why = $"{role} is not in this PDM."; return -1; }
        if (id is < 1 or > 0x7FF) { why = "The frame ID must be a standard (11-bit) ID, 0x001 to 0x7FF."; return -1; }
        if (IsPdmId(v, id) && !allowPdmId) { why = $"0x{id:X3} is inside a PDM board's own ID block."; return -1; }
        if (startBit is < 0 or > 63 || length is < 1 or > 32 || (startBit + length > 64 && order == ByteOrder.LittleEndian))
        { why = "The value must fit in the 8 data bytes (first byte 0-7, length 1-32 bits)."; return -1; }
        if (factor == 0) { why = "The factor must not be 0."; return -1; }
        var d = q.Device;
        var s = Enumerable.Range(0, d.CanInputs.Count).FirstOrDefault(i => PdmLinks.IsFreeSlot(q, i), -1);
        if (s < 0) { why = $"{role} is full: no free CAN input ({PdmModel.Build(v).Use(role).Of(PdmResKind.CanInput).Text})."; return -1; }
        var c = d.CanInputs[s];
        PdmLinks.SetSlot(c, name, id, startBit, Operator.GreaterThanOrEqual, AnyValue, timeoutMs > 0, Math.Max(timeoutMs, 1), length);
        (c.ByteOrder, c.Signed, c.Factor, c.Offset) = (order, signed, factor, offset);
        return s;
    }
}
