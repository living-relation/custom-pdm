using domain.Devices;
using domain.Devices.Functions;
using domain.Enums;
using domain.Interfaces;

namespace domain.CustomPdm;

// custom-pdm route B, phase B4 (docs/ui-route-b-plan.md): any digital input of the PDM as the trigger of any output.
// Nothing is mirrored and nothing is set on the source board: every board already sends ALL its digital inputs in
// cyclic msg 37 (firmware/boards/custompdm_*/msg.cpp TxMsg37: base + 2 + 37, bytes 0-1 little endian, bit i = input
// i + 1, always sent). A link "input X on board P -> output Y on board Q":
// - P == Q: output Y's trigger is the input itself (no slot).
// - P != Q: ONE stock CAN input slot on Q listens to bit i of P's msg 37 (length 1, Equal 1), and output Y's trigger is
//   that slot. Loss behaviour (u3c, per link, default Off) uses only stock options (firmware functions/can_input.cpp:
//   with the time-out on, a silent ID sets the slot to 0; with it off, the slot keeps its last value):
//     Off  = time-out on (1 s): output goes off 1 s after P's frames stop.
//     Hold = time-out off: output keeps its last state.
//     On   = time-out on, the slot inverted (Equal 0) and output Y driven by a virtual input "NOT slot": output goes on
//            1 s after P's frames stop (same behaviour as the s1 "on" policy, firmware/sim/RESULTS.md; one virtual
//            input per such link). Before P's first frame after a power-up it is on, as RESULTS.md s2 notes for "on".
// Ownership: links live only in the boards' params (no PC-only state), so they survive Read All, an app restart and a
// fresh project. A slot belongs to a link when ALL its fields match the link pattern above (ID = the msg 37 ID of
// another board of this PDM); a virtual input when it is exactly "NOT <link slot> OR false". Anything else is the
// user's and is never changed. A slot is free only when it is disabled with ID 0 (as on a fresh board), and is not one
// of A2's fan CAN inputs 25-28; a virtual input only when disabled with no variables, and not a fan (A2 12-14) or
// load-shed example (15-16) one. New links take the lowest free slot. Removing a link puts its slot (and virtual input)
// back to the fresh-board values and the output trigger to none.
// All of it is a PC edit: it reaches the boards with the /pdm Write All (PdmOps), and is kept after Burn.
// Numbers: Slot / Virt count from 0 (param index); the UI shows them from 1.
public enum PdmLinkLoss { Off, Hold, On }

public record PdmLink(PdmOutputRow Out, PdmInputRow In, PdmLinkLoss? Loss, int? Slot, int? Virt)
{
    public bool CrossBoard => Slot != null;

    public string LossText => Loss switch
    {
        PdmLinkLoss.Off => "off after 1 s",
        PdmLinkLoss.Hold => "keeps its last state",
        PdmLinkLoss.On => "on after 1 s",
        _ => "same board: no CAN message"
    };

    public string SlotText => Slot is { } s
        ? $"{Out.Board} CAN input {s + 1}" + (Virt is { } k ? $" + virtual input {k + 1}" : "")
        : "none (same board)";
}

public record PdmSlotUse(string Board, int Slot, bool Free, bool OurLink, string UsedBy);

public record PdmBoardSlots(string Board, IReadOnlyList<PdmSlotUse> CanInputs, int FreeCanInputs, int LinkCanInputs,
    int FreeVirtuals, IReadOnlyList<int> LinkVirtuals)
{
    public string Summary =>
        $"{Board}: CAN inputs {CanInputs.Count - FreeCanInputs} of {CanInputs.Count} used ({LinkCanInputs} by links), {FreeCanInputs} free; " +
        $"virtual inputs free for 'on' links: {FreeVirtuals}" + (LinkVirtuals.Count > 0 ? $" ({LinkVirtuals.Count} used by links)" : "");
}

public static class PdmLinks
{
    public const int StatusMsg = 37;                                                // TxMsg37: all digital inputs
    public const int StatusOffset = PdmFactoryDefaults.CyclicTxOffset + StatusMsg;  // base + 0x27
    public const int TimeoutMs = 1000;                                              // stock default time-out
    public const PdmLinkLoss DefaultLoss = PdmLinkLoss.Off;                          // u3c

    public static readonly PdmLinkLoss[] LossChoices = [PdmLinkLoss.Off, PdmLinkLoss.Hold, PdmLinkLoss.On];

    public static string LossName(PdmLinkLoss l) => l switch
    {
        PdmLinkLoss.Off => "Output off (1 s after the message stops)",
        PdmLinkLoss.Hold => "Output keeps its last state",
        _ => "Output on (1 s after the message stops)"
    };

    // ---------------- reserved slots (port_boards.py: FAN_CANIN0, FAN_VIRT0, SHED_VIRT0) ----------------

    public static bool IsFanSlot(PdmBoard q, int s) =>
        q.Role == "A2" && s >= PdmFactoryDefaults.FanCanIn0 && s < PdmFactoryDefaults.FanCanIn0 + 4;

    public static bool IsReservedVirt(PdmBoard q, int k)
    {
        var d = q.Device;
        if (k >= PdmFactoryDefaults.ShedVirt0(d) && k < PdmFactoryDefaults.ShedVirt0(d) + 2) return true;
        return q.Role == "A2" && k >= PdmFactoryDefaults.FanVirt0(d) && k < PdmFactoryDefaults.FanVirt0(d) + 3;
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

    // The input that slot s on board q listens to (link pattern), or null. inverted: Equal 0 (the 'on' link).
    public static PdmInputRow? SourceOfSlot(PdmView v, PdmBoard q, int s, out bool inverted)
    {
        inverted = false;
        if (IsFanSlot(q, s)) return null;
        var c = q.Device.CanInputs[s];
        if (c is not { Enabled: true, Ide: false, BitLength: 1, Factor: 1.0, Offset: 0.0, ByteOrder: ByteOrder.LittleEndian,
                Signed: false, Operator: Operator.Equal, Mode: InputMode.Momentary, Bus: 0 }) return null;
        if (c.Operand is not (0.0 or 1.0)) return null;
        inverted = c.Operand == 0.0;
        if (inverted && !c.TimeoutEnabled) return null;
        var p = v.Boards.FirstOrDefault(b => b.Role != q.Role && b.Device.BaseId + StatusOffset == c.Id);
        return p == null ? null : DigitalRow(v, p.Role, c.StartBit);
    }

    // The link slot behind virtual input k ("NOT slot OR false"), or null
    private static int? SlotOfVirt(PdmView v, PdmBoard q, int k)
    {
        if (IsReservedVirt(q, k)) return null;
        var vi = q.Device.VirtualInputs[k];
        if (vi is not { Enabled: true, Not0: true, Cond0: Conditional.Or, Not1: false, Var1: 0, Not2: false, Var2: 0,
                Mode: InputMode.Momentary }) return null;
        for (var s = 0; s < q.Device.CanInputs.Count; s++)
            if (PdmFactoryDefaults.CanInState(q.Device, s) == vi.Var0)
                return SourceOfSlot(v, q, s, out var inv) != null && inv ? s : null;
        return null;
    }

    private static IDeviceFunction? OwnerOf(FwDevice d, int var)
    {
        var owner = d.VarMap.FirstOrDefault(x => x.VariableIndex == var)?.Owner;
        return owner != null && PdmFactoryDefaults.VarOf(d, owner) == var ? owner : null; // its first (state) variable
    }

    // The link that drives this output, or null (no trigger, or one set by hand)
    public static PdmLink? LinkOf(PdmView v, PdmOutputRow o)
    {
        var q = BoardOf(v, o.Device);
        if (q == null || o.Output.Input == 0) return null;
        switch (OwnerOf(o.Device, o.Output.Input))
        {
            case DigitalInput di:
                return v.Inputs.FirstOrDefault(r => ReferenceEquals(r.Digital, di)) is { } same ? new PdmLink(o, same, null, null, null) : null;
            case CanInput ci:
            {
                var s = o.Device.CanInputs.IndexOf(ci);
                var src = SourceOfSlot(v, q, s, out var inv);
                return src == null || inv ? null : new PdmLink(o, src, ci.TimeoutEnabled ? PdmLinkLoss.Off : PdmLinkLoss.Hold, s, null);
            }
            case VirtualInput vi:
            {
                var k = o.Device.VirtualInputs.IndexOf(vi);
                if (SlotOfVirt(v, q, k) is not { } s) return null;
                var src = SourceOfSlot(v, q, s, out _)!;
                return new PdmLink(o, src, PdmLinkLoss.On, s, k);
            }
            default:
                return null;
        }
    }

    public static IReadOnlyList<PdmLink> Links(PdmView v) =>
        v.Outputs.Select(o => LinkOf(v, o)).OfType<PdmLink>().ToList();

    // ---------------- slot use per board ----------------

    public static IReadOnlyList<PdmBoardSlots> Slots(PdmView v)
    {
        var links = Links(v);
        var list = new List<PdmBoardSlots>();
        foreach (var q in v.Boards)
        {
            var d = q.Device;
            var uses = new List<PdmSlotUse>();
            for (var s = 0; s < d.CanInputs.Count; s++)
            {
                var c = d.CanInputs[s];
                var link = links.FirstOrDefault(l => l.Out.Board == q.Role && l.Slot == s);
                var src = SourceOfSlot(v, q, s, out _);
                uses.Add(link != null
                    ? new PdmSlotUse(q.Role, s, false, true, $"link: {link.In.Board} IN{link.In.BoardInput} (input {link.In.Number}) -> OUT{link.Out.BoardOutput} (output {link.Out.Number}), {link.LossText}")
                    : src != null
                        ? new PdmSlotUse(q.Role, s, false, true, $"link slot for {src.Board} IN{src.BoardInput}, no output uses it (Remove unused)")
                        : IsFanSlot(q, s)
                            ? new PdmSlotUse(q.Role, s, false, false, "fan logic (A1 / B board temperature), reserved")
                            : IsFreeSlot(q, s)
                                ? new PdmSlotUse(q.Role, s, true, false, "free")
                                : new PdmSlotUse(q.Role, s, false, false, $"set by hand ({(c.Enabled ? "enabled" : "disabled")}, ID 0x{c.Id:X3}): never changed here"));
            }
            var freeVirt = Enumerable.Range(0, d.VirtualInputs.Count).Count(k => IsFreeVirt(q, k));
            var linkVirt = links.Where(l => l.Out.Board == q.Role && l.Virt != null).Select(l => l.Virt!.Value).ToList();
            list.Add(new PdmBoardSlots(q.Role, uses, uses.Count(u => u.Free), uses.Count(u => u.OurLink), freeVirt, linkVirt));
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

    // null = link made on the PC; else why not (nothing changed)
    public static string? Add(PdmView v, int input, int output, PdmLinkLoss loss = DefaultLoss)
    {
        var inRow = v.Inputs.FirstOrDefault(r => r.Number == input && r.Digital != null);
        if (inRow == null) return $"Input {input} is not a digital input of this PDM (1-24, its board must be in the project).";
        var o = v.Outputs.FirstOrDefault(r => r.Number == output);
        if (o == null) return $"Output {output} is not in this PDM (1-24, its board must be in the project).";
        var q = BoardOf(v, o.Device)!;
        var what = $"output {output} ({o.Board} OUT{o.BoardOutput})";
        if (q.Role == "A2" && o.BoardOutput - 1 == PdmFactoryDefaults.FanOutput)
            return $"{char.ToUpper(what[0])}{what[1..]} runs the fans: its trigger is the fan logic.";
        if (o.Output.PrimaryOutput >= 0)
            return $"{char.ToUpper(what[0])}{what[1..]} is paired: it follows output {o.Output.PrimaryOutput + 1} of {o.Board}.";
        if (LinkOf(v, o) is { } old)
            return $"{char.ToUpper(what[0])}{what[1..]} is already linked to input {old.In.Number}: remove that link first.";
        if (o.Output.Input != 0)
            return $"{char.ToUpper(what[0])}{what[1..]} already has a trigger set by hand (variable {o.Output.Input}): set it to none on {o.Board}'s page first.";

        var d = o.Device;
        if (inRow.Board == q.Role)
        {
            o.Output.Input = PdmFactoryDefaults.VarOf(d, inRow.Digital!);
            return null;
        }

        var s = Enumerable.Range(0, d.CanInputs.Count).Cast<int?>().FirstOrDefault(i => IsFreeSlot(q, i!.Value));
        if (s == null)
        {
            var u = Slots(v).Single(b => b.Board == q.Role);
            return $"{q.Role} has no free CAN input: all {u.CanInputs.Count} are used ({u.LinkCanInputs} by links, the rest by the fan logic or set by hand).";
        }
        int? k = null;
        if (loss == PdmLinkLoss.On)
        {
            k = Enumerable.Range(0, d.VirtualInputs.Count).Cast<int?>().FirstOrDefault(i => IsFreeVirt(q, i!.Value));
            if (k == null) return $"{q.Role} has no free virtual input, which an 'on' link needs: choose 'off' or 'hold'.";
        }

        var p = v.Boards.Single(b => b.Role == inRow.Board);
        var name = $"Link {inRow.Board} IN{inRow.BoardInput} -> OUT{o.BoardOutput}";
        var c = d.CanInputs[s.Value];
        (c.Name, c.Enabled, c.TimeoutEnabled, c.Timeout, c.Id, c.StartBit, c.BitLength) =
            (name, true, loss != PdmLinkLoss.Hold, TimeoutMs, p.Device.BaseId + StatusOffset, inRow.BoardInput - 1, 1);
        (c.Factor, c.Offset, c.ByteOrder, c.Signed, c.Operator, c.Operand, c.Mode, c.Bus) =
            (1.0, 0.0, ByteOrder.LittleEndian, false, Operator.Equal, loss == PdmLinkLoss.On ? 0.0 : 1.0, InputMode.Momentary, 0);
        if (k is { } kk)
        {
            var vi = d.VirtualInputs[kk];
            (vi.Name, vi.Enabled, vi.Not0, vi.Var0, vi.Cond0, vi.Not1, vi.Var1) =
                (name + " (on at loss)", true, true, PdmFactoryDefaults.CanInState(d, s.Value), Conditional.Or, false, 0);
            (vi.Cond1, vi.Not2, vi.Var2, vi.Mode) = (Conditional.And, false, 0, InputMode.Momentary);
            o.Output.Input = PdmFactoryDefaults.VarOf(d, vi);
        }
        else o.Output.Input = PdmFactoryDefaults.CanInState(d, s.Value);
        return null;
    }

    // null = removed on the PC (slot and virtual input back to fresh-board values, output trigger none)
    public static string? Remove(PdmView v, int output)
    {
        var o = v.Outputs.FirstOrDefault(r => r.Number == output);
        if (o == null || LinkOf(v, o) is not { } link) return $"Output {output} has no link.";
        o.Output.Input = 0;
        if (link.Slot is { } s) Reset(o.Device.CanInputs[s]);
        if (link.Virt is { } k) Reset(o.Device.VirtualInputs[k]);
        return null;
    }

    // Change the loss behaviour: remove, then add again (the slot may move to a lower free one)
    public static string? SetLoss(PdmView v, int output, PdmLinkLoss loss)
    {
        var o = v.Outputs.FirstOrDefault(r => r.Number == output);
        if (o == null || LinkOf(v, o) is not { } link) return $"Output {output} has no link.";
        if (!link.CrossBoard) return "A same-board link has no CAN message to lose.";
        if (link.Loss == loss) return null;
        var old = link.Loss!.Value;
        Remove(v, output);
        if (Add(v, link.In.Number, output, loss) is { } why)
        {
            Add(v, link.In.Number, output, old); // its slot was just freed: always fits
            return why;
        }
        return null;
    }

    // Link slots that no output uses (e.g. the output trigger was changed by hand): back to fresh-board values
    public static int RemoveUnused(PdmView v)
    {
        var used = Links(v).Where(l => l.Slot != null).Select(l => (l.Out.Board, l.Slot!.Value)).ToHashSet();
        var n = 0;
        foreach (var q in v.Boards)
            for (var s = 0; s < q.Device.CanInputs.Count; s++)
                if (!used.Contains((q.Role, s)) && SourceOfSlot(v, q, s, out _) != null)
                {
                    Reset(q.Device.CanInputs[s]);
                    n++;
                }
        return n;
    }

    // Before board `role` moves to newBase: link slots on the other boards that listen to its msg 37 follow it
    public static IReadOnlyList<string> FollowBaseId(PdmView v, string role, int newBase)
    {
        var list = new List<string>();
        foreach (var q in v.Boards.Where(b => b.Role != role))
            for (var s = 0; s < q.Device.CanInputs.Count; s++)
                if (SourceOfSlot(v, q, s, out _) is { } src && src.Board == role)
                {
                    q.Device.CanInputs[s].Id = newBase + StatusOffset;
                    list.Add($"{q.Role} CAN input {s + 1} (link from {role} IN{src.BoardInput}) -> 0x{newBase + StatusOffset:X3}");
                }
        return list;
    }

    // Is slot s on board q a link slot that follows `role`? (PdmLinked.BaseIdWarnings leaves those out)
    public static bool FollowsBoard(PdmView v, PdmBoard q, int s, string role) =>
        SourceOfSlot(v, q, s, out _) is { } src && src.Board == role;

    // Things that make a link do nothing (shown next to it; not refused)
    public static IReadOnlyList<string> Warnings(PdmLink l)
    {
        var w = new List<string>();
        if (!l.Out.Output.Enabled) w.Add($"output {l.Out.Number} is not enabled");
        if (l.In.Digital is { Enabled: false }) w.Add($"input {l.In.Number} is not enabled on {l.In.Board}");
        return w;
    }
}
