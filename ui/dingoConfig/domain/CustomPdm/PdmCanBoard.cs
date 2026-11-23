using System.Globalization;
using domain.Devices;
using domain.Devices.Functions;
using domain.Enums;

namespace domain.CustomPdm;

// custom-pdm canboard (Dan, 2026-11-22, c2 = a): a one-click preset for the Dingo Electronics CANBoard (8 ground
// switching digital inputs, 5 analog inputs 0-5 V, 4 low-side outputs 0.5 A, STM32F303K8) = more I/O for the PDM
// over CAN. Protocol facts, all read from the CANBoard's firmware (dingoFW, in this repo as firmware/boards/
// canboard_v2 = corygrant/dingoFW development 14084e9; the same layout in master d594cd7):
//   base ID      param 0x0000 sub 0, default 0x640 (port.h DEFAULT_BASE_ID); set with dingoConfig, not with the
//                board's solder jumpers (those were read by the old CANBoard_FW only, CANBoard_HW README 3126b1a)
//   bit rate     param 0x0000 sub 1, default 500K (core/param_defs.h DEFAULT_CAN_BITRATE): it must be set to 1000K
//                once (dingoConfig, then burn and restart) before it can talk on the PDM's 1 Mbit/s bus
//   frames       base + 0 / + 1 = PC tool; status msg n on base + 2 + n (core/device_config.h CYCLIC_TX_OFFSET 2),
//                every 100 ms (CAN_TX_CYCLIC_MSG_DELAY), 13 msgs (port.h NUM_TX_MSGS) = IDs base .. base + 14
//   msg 0 (+2)   analog inputs 1-4 in mV, uint16 little endian each (msg.cpp TxMsg0), always sent
//   msg 1 (+3)   analog input 5 in mV (bytes 0-1), STM32 temperature in C (bytes 6-7) (TxMsg1), always sent
//   msg 2 (+4)   byte 0 rotary 1 (low nibble) / 2 (high), byte 1 rotary 3 / 4, byte 2 rotary 5, byte 3 flashers,
//                byte 4 digital inputs 1-8 (bit 0 = input 1), byte 5 analog inputs as switches, byte 6 the state of
//                its 4 outputs, byte 7 a heartbeat counter (+1 per frame) (TxMsg2), always sent
//   outputs      there is NO fixed output-control frame: each output follows one variable of the CANBoard
//                (param 0x2100 + i: enabled, input), e.g. one of its 8 CAN inputs (0x1300 + i: ID, start bit,
//                length, operator, operand, time-out). So the PDM sends a frame with its stock CAN outputs and the
//                CANBoard is set ONCE (dingoConfig) to listen to it. (The old CANBoard_FW b95e931 had a fixed
//                frame, base + 3 bytes 0-3, but runs at 500K only and puts its inputs on base + 0 .. + 2.)
//   time-outs    the CANBoard has none of its own for inputs (it just sends every 100 ms); a dingoFW CAN input with
//                its time-out on reads value 0 / off when no frame came for that long (functions/can_input.cpp)
// On the PDM a CANBoard is 13 stock CAN inputs (8 switches: bit, Equal 1; 5 analog values in mV), + 5 for its rotary
// positions when asked for, each with the time-out on (default 1 s, as keypads): no PC-only state, it is read back
// from the board params (the 8 switch inputs of base + 4 are its mark; its name is the start of their names).
public enum PdmCanBoardKind { Switch, Analog, Rotary }

public record PdmCanBoardSignal(PdmCanBoardKind Kind, int Number, int IdOffset, int StartBit, int Length)
{
    public bool IsValue => Kind != PdmCanBoardKind.Switch;
    public string Word => Kind switch { PdmCanBoardKind.Switch => "switch", PdmCanBoardKind.Analog => "analog", _ => "rotary" };
    public string Text => Kind switch
    {
        PdmCanBoardKind.Switch => $"switch {Number}",
        PdmCanBoardKind.Analog => $"analog {Number} (mV)",
        _ => $"rotary {Number} position"
    };
    public string Key => $"{Word}{Number}";
}

// one CAN input of a PDM board that listens to a CANBoard signal
public record PdmCanBoardInput(PdmCanBoardSignal Signal, string Role, int Slot, CanInput Input, int Var);

// the PDM signal that drives CANBoard output Number (1-4): a stock CAN output of board Role
public record PdmCanBoardOut(int Number, string Role, int Index, CanOutput Out, int Id, int StartBit);

public record PdmCanBoardInfo(int BaseId, string Name, IReadOnlyList<PdmCanBoardInput> Inputs, IReadOnlyList<PdmCanBoardOut> Outputs)
{
    public bool HasRotary => Inputs.Any(i => i.Signal.Kind == PdmCanBoardKind.Rotary);
    public int TimeoutMs => Inputs.Select(i => i.Input.Timeout).DefaultIfEmpty(PdmLinks.TimeoutMs).First();
    public int LastId => BaseId + PdmCanBoard.BlockIds - 1;
}

// a signal of a CANBoard for a picker of board Role: Var = its variable there, or 0 = not on that board yet (Ensure)
public record PdmCanBoardChoice(string Key, int BaseId, PdmCanBoardSignal Signal, int Var, string Text);

public static class PdmCanBoard
{
    public const int DefaultBaseId = 0x640;                  // firmware/boards/canboard_v2/port.h DEFAULT_BASE_ID
    public const int NumTxMsgs = 13;                         // port.h NUM_TX_MSGS
    public const int StatusIds = DbcExport.CyclicTxOffset + NumTxMsgs;   // base .. base + 14: the CANBoard's own IDs
    public const int CommandOffset = 0x10;                   // ours: base + 0x10 + n = the frame PDM board n sends to it
    public const int BlockIds = CommandOffset + 3;           // base .. base + 0x12 are kept for one CANBoard
    public const int PeriodMs = 100;                         // core/device_config.h CAN_TX_CYCLIC_MSG_DELAY
    public const int AnalogMsg = 0, Analog5Msg = 1, StateMsg = 2;
    public const int Switches = 8, Analogs = 5, Rotaries = 5, Outs = 4;
    public const int MaxAnalogMv = 5000, MaxRotary = 15;
    public const int MinTimeoutMs = 3 * PeriodMs, MaxTimeoutMs = 10000;   // as the links: one late frame is never a loss
    public const int NameMax = 20;
    public static readonly string[] Roles = ["A1", "A2", "B"];

    public static readonly IReadOnlyList<PdmCanBoardSignal> Signals =
    [
        .. Enumerable.Range(1, Switches).Select(i => new PdmCanBoardSignal(PdmCanBoardKind.Switch, i, 2 + StateMsg, 32 + i - 1, 1)),
        .. Enumerable.Range(1, 4).Select(i => new PdmCanBoardSignal(PdmCanBoardKind.Analog, i, 2 + AnalogMsg, 16 * (i - 1), 16)),
        new PdmCanBoardSignal(PdmCanBoardKind.Analog, 5, 2 + Analog5Msg, 0, 16),
        .. Enumerable.Range(1, Rotaries).Select(i => new PdmCanBoardSignal(PdmCanBoardKind.Rotary, i, 2 + StateMsg, 4 * (i - 1), 4))
    ];

    public static PdmCanBoardSignal Signal(PdmCanBoardKind kind, int number) => Signals.Single(s => s.Kind == kind && s.Number == number);

    private static string Hex(int id) => $"0x{id:X3}";

    // ---------------- read back ----------------

    private static bool Common(CanInput c) =>
        c is { Enabled: true, Ide: false, Factor: 1.0, Offset: 0.0, ByteOrder: ByteOrder.LittleEndian, Signed: false,
            Mode: InputMode.Momentary, Bus: 0, TimeoutEnabled: true };

    private static bool IsSwitchShape(CanInput c) => Common(c) && c is { BitLength: 1, Operator: Operator.Equal, Operand: 1.0 };

    // the CANBoard signal a CAN input reads when its ID is base + off, or null
    public static PdmCanBoardSignal? SignalAt(CanInput c, int off)
    {
        if (!Common(c)) return null;
        if (IsSwitchShape(c)) return Signals.FirstOrDefault(s => !s.IsValue && s.IdOffset == off && s.StartBit == c.StartBit);
        return PdmValues.IsValueShape(c) ? Signals.FirstOrDefault(s => s.IsValue && s.IdOffset == off && s.StartBit == c.StartBit && s.Length == c.BitLength) : null;
    }

    private static string DefaultName(int baseId) => $"CANBoard {Hex(baseId)}";

    public static IReadOnlyList<PdmCanBoardInfo> All(PdmView v)
    {
        // the mark of a CANBoard: all 8 switch inputs of one ID (= base + 4) somewhere on the PDM
        var sw = new Dictionary<int, HashSet<int>>();
        foreach (var b in v.Boards)
        foreach (var c in b.Device.CanInputs)
            if (SignalAt(c, 2 + StateMsg) is { Kind: PdmCanBoardKind.Switch } s)
            {
                if (!sw.TryGetValue(c.Id, out var set)) sw[c.Id] = set = [];
                set.Add(s.Number);
            }

        var list = new List<PdmCanBoardInfo>();
        foreach (var baseId in sw.Where(k => k.Value.Count == Switches).Select(k => k.Key - 2 - StateMsg).Where(b => b > 0).OrderBy(b => b))
        {
            var inputs = new List<PdmCanBoardInput>();
            foreach (var b in v.Boards)
                for (var i = 0; i < b.Device.CanInputs.Count; i++)
                {
                    var c = b.Device.CanInputs[i];
                    if (SignalAt(c, c.Id - baseId) is not { } s) continue;
                    var state = PdmFactoryDefaults.CanInState(b.Device, i);
                    inputs.Add(new PdmCanBoardInput(s, b.Role, i, c, s.IsValue ? state + 1 : state));
                }

            var first = inputs.Where(x => x.Signal is { Kind: PdmCanBoardKind.Switch, Number: 1 }).Select(x => x.Input.Name?.Trim() ?? "").FirstOrDefault() ?? "";
            var name = first.EndsWith(" switch 1", StringComparison.Ordinal) && first.Length > 9 ? first[..^9] : DefaultName(baseId);
            var outs = new List<PdmCanBoardOut>();
            foreach (var b in v.Boards)
                for (var i = 0; i < b.Device.CanOutputs.Count; i++)
                {
                    var o = b.Device.CanOutputs[i];
                    if (o is { Enabled: true, BitLength: 8, ByteOrder: ByteOrder.LittleEndian } && o.Id == CommandId(baseId, b.Role)
                        && o.StartBit % 8 == 0 && o.StartBit / 8 < Outs && outs.All(x => x.Number != o.StartBit / 8 + 1))
                        outs.Add(new PdmCanBoardOut(o.StartBit / 8 + 1, b.Role, i, o, o.Id, o.StartBit));
                }

            list.Add(new PdmCanBoardInfo(baseId, name, inputs, outs.OrderBy(o => o.Number).ToList()));
        }

        return list;
    }

    public static PdmCanBoardInfo? Find(PdmView v, int baseId) => All(v).FirstOrDefault(c => c.BaseId == baseId);

    // the CANBoard input a CAN input of the PDM is, with its plain name ("CANBoard 1 switch 3"), or null.
    // isValue: a number (analog, rotary), not an on / off switch
    public static string? LabelOf(PdmView v, CanInput c, out bool isValue)
    {
        isValue = false;
        if (!Common(c)) return null;
        foreach (var cb in All(v))
            if (cb.Inputs.FirstOrDefault(i => ReferenceEquals(i.Input, c)) is { } inp)
            {
                isValue = inp.Signal.IsValue;
                return Label(cb, inp.Signal, c);
            }

        return null;
    }

    public static string? LabelOf(PdmView v, CanInput c) => LabelOf(v, c, out _);

    // the user's own name of that CAN input when it has one, else "<CANBoard name> switch 3"
    public static string Label(PdmCanBoardInfo cb, PdmCanBoardSignal s, CanInput? c = null)
    {
        var std = $"{cb.Name} {s.Text}";
        var own = c?.Name?.Trim() ?? "";
        return own == "" || own == SlotName(cb.Name, s) || System.Text.RegularExpressions.Regex.IsMatch(own, "^[a-zA-Z]+[0-9]+$") ? std : own;
    }

    private static string SlotName(string name, PdmCanBoardSignal s) => $"{name} {s.Word} {s.Number}";

    // ---------------- IDs ----------------

    public static int CommandId(int baseId, string role) => baseId + CommandOffset + Math.Max(0, Array.IndexOf(Roles, role));

    // the CANBoard whose block (its own IDs and the PDM's command frames to it) holds id, or null
    public static PdmCanBoardInfo? OwnerOf(PdmView v, int id) => All(v).FirstOrDefault(c => id >= c.BaseId && id <= c.LastId);

    // may board role send frame id as a CAN output? Only its own command frame goes into a CANBoard's block
    public static string? CanOutClash(PdmView v, string role, int id) =>
        OwnerOf(v, id) is { } cb && id != CommandId(cb.BaseId, role)
            ? $"{Hex(id)} is inside the ID block of {cb.Name} ({Hex(cb.BaseId)}-{Hex(cb.LastId)}): pick a free ID."
            : null;

    // why a CANBoard cannot sit on baseId (a clash with the PDM's own IDs, another CANBoard, a keypad, the ECU
    // stream, a CAN value or a CAN output of the setup), or null
    public static string? Clash(PdmView v, int baseId)
    {
        var last = baseId + BlockIds - 1;
        if (baseId < 1 || last > 0x7FF) return $"The base ID must be {Hex(1)} to {Hex(0x7FF - BlockIds + 1)} (a CANBoard uses {BlockIds} IDs from it).";
        return ClashWhat(v, baseId) is { } what
            ? $"A CANBoard at {Hex(baseId)} uses {Hex(baseId)}-{Hex(last)}: {what}. Pick another base ID, e.g. {Hex(FreeBase(v))}."
            : null;
    }

    private static string? ClashWhat(PdmView v, int baseId)
    {
        var last = baseId + BlockIds - 1;
        bool In(int id) => id >= baseId && id <= last;
        foreach (var b in v.Boards)
            if (baseId < b.Device.BaseId + 0x40 && last >= b.Device.BaseId)
                return $"that overlaps board {b.Role}'s own IDs ({Hex(b.Device.BaseId)}-{Hex(b.Device.BaseId + 0x3F)})";
        var boards = All(v);
        foreach (var cb in boards)
            if (baseId <= cb.LastId && last >= cb.BaseId)
                return $"that overlaps {cb.Name} ({Hex(cb.BaseId)}-{Hex(cb.LastId)})";
        var mine = boards.SelectMany(c => c.Inputs.Select(i => i.Input)).ToHashSet<CanInput>(ReferenceEqualityComparer.Instance);
        var myOuts = boards.SelectMany(c => c.Outputs.Select(o => o.Out)).ToHashSet<CanOutput>(ReferenceEqualityComparer.Instance);
        foreach (var b in v.Boards)
        {
            foreach (var c in b.Device.CanInputs.Where(c => c.Enabled && !c.Ide && !mine.Contains(c)))
            {
                if (PdmValues.IsKeypadShape(v, c))
                {
                    var node = c.Id - 0x180;
                    if (PdmValues.KeypadOffsets.Where(o => In(o + node)).Select(o => (int?)o).FirstOrDefault() is { } off)
                        return $"keypad node 0x{node:X2} uses {Hex(off + node)} there";
                }
                else if (In(c.Id))
                    return $"{b.Role} already listens to {Hex(c.Id)} there ({(PdmEcu.IsCmdShape(v, c) ? "the ECU stream" : string.IsNullOrWhiteSpace(c.Name) ? "a CAN input" : c.Name.Trim())})";
            }
            foreach (var o in b.Device.CanOutputs.Where(o => o.Enabled && !myOuts.Contains(o) && In(o.Id)))
                return $"{b.Role} already sends {Hex(o.Id)} there";
            foreach (var k in b.Device.Keypads.Where(k => k.Enabled))
                if (PdmValues.KeypadOffsets.Where(o => In(o + k.Id)).Select(o => (int?)o).FirstOrDefault() is { } off)
                    return $"the keypad at node 0x{k.Id:X2} uses {Hex(off + k.Id)} there";
        }

        return null;
    }

    // the first base ID from the firmware default up, in steps of 0x20, that clashes with nothing
    public static int FreeBase(PdmView v)
    {
        for (var b = DefaultBaseId; b + BlockIds - 1 <= 0x7FF; b += 0x20)
            if (ClashWhat(v, b) == null) return b;
        return DefaultBaseId;
    }

    public static string NextName(PdmView v)
    {
        var names = All(v).Select(c => c.Name).ToHashSet(StringComparer.OrdinalIgnoreCase);
        return Enumerable.Range(1, 99).Select(i => $"CANBoard {i}").First(n => !names.Contains(n));
    }

    // ---------------- add / remove ----------------

    public static int Need(bool rotary) => Switches + Analogs + (rotary ? Rotaries : 0);

    private static string? NameProblem(PdmView v, string name, int? except = null)
    {
        if (name.Length is < 1 or > NameMax) return $"Give the CANBoard a name of 1 to {NameMax} characters.";
        if (name.Any(ch => ch < ' ' || ch == '\'' || ch == '"')) return "The name cannot hold quote marks.";
        return All(v).Any(c => c.BaseId != except && string.Equals(c.Name, name, StringComparison.OrdinalIgnoreCase))
            ? $"There is already a CANBoard named {name}: pick another name." : null;
    }

    // null = added on the PC (Write All sends it); else why not (nothing changed). Its inputs go on the boards with
    // the most free CAN inputs; the user never picks a board.
    public static string? Add(PdmView v, int baseId, string? name, bool rotary = false, int timeoutMs = PdmLinks.TimeoutMs)
    {
        if (!v.Any) return "There is no PDM in this project yet (New PDM).";
        name = (name ?? "").Trim();
        if (name == "") name = NextName(v);
        if (NameProblem(v, name) is { } badName) return badName;
        if (timeoutMs is < MinTimeoutMs or > MaxTimeoutMs) return $"The time before a silent CANBoard counts as lost is {MinTimeoutMs} to {MaxTimeoutMs} ms.";
        if (All(v).Any(c => c.BaseId == baseId)) return $"There is already a CANBoard at {Hex(baseId)}.";
        if (Clash(v, baseId) is { } clash) return clash;
        var m = PdmModel.Build(v);
        var free = v.Boards.Select(b => (b, Slots: new Queue<int>(m.FreeOf(b.Role, PdmResKind.CanInput)))).ToList();
        var need = Need(rotary);
        var have = free.Sum(f => f.Slots.Count);
        if (have < need)
            return $"A CANBoard needs {need} free CAN inputs on the PDM ({Switches} switches, {Analogs} analog inputs{(rotary ? $", {Rotaries} rotary positions" : "")}); " +
                   $"only {have} {(have == 1 ? "is" : "are")} free ({string.Join(", ", free.Select(f => $"{f.b.Role} {f.Slots.Count}"))}). Nothing changed. " +
                   "Free some first (links, triggers that read another board's input, keypad buttons, CAN values).";
        var order = free.OrderByDescending(f => f.Slots.Count).ToList();
        foreach (var s in Signals.Where(s => rotary || s.Kind != PdmCanBoardKind.Rotary))
        {
            var (b, slots) = order.First(f => f.Slots.Count > 0);
            Make(b.Device.CanInputs[slots.Dequeue()], baseId, name, s, timeoutMs);
        }

        return null;
    }

    private static void Make(CanInput c, int baseId, string name, PdmCanBoardSignal s, int timeoutMs)
    {
        if (s.IsValue) PdmLinks.SetSlot(c, SlotName(name, s), baseId + s.IdOffset, s.StartBit, Operator.GreaterThanOrEqual, PdmEcu.AnyValue, true, timeoutMs, s.Length);
        else PdmLinks.SetSlot(c, SlotName(name, s), baseId + s.IdOffset, s.StartBit, Operator.Equal, 1.0, true, timeoutMs);
    }

    // The variable of a CANBoard signal on board role, for an output / function of that board. Any board can hear the
    // CANBoard: when the signal is not on role yet, one more CAN input is made there. 0 = refused (why).
    public static int Ensure(PdmView v, string role, int baseId, PdmCanBoardSignal signal, out string? why)
    {
        why = null;
        if (Find(v, baseId) is not { } cb) { why = $"There is no CANBoard at {Hex(baseId)}."; return 0; }
        if (cb.Inputs.FirstOrDefault(i => i.Role == role && i.Signal == signal) is { } have) return have.Var;
        if (signal.Kind == PdmCanBoardKind.Rotary && !cb.HasRotary) { why = $"{cb.Name} was added without rotary positions."; return 0; }
        var q = v.Boards.FirstOrDefault(b => b.Role == role);
        if (q == null) { why = $"{role} is not in this PDM."; return 0; }
        var m = PdmModel.Build(v);
        var free = m.FreeOf(role, PdmResKind.CanInput);
        if (free.Count == 0)
        {
            why = $"{role} is full: {Label(cb, signal)} needs 1 CAN input there; {m.Use(role).Of(PdmResKind.CanInput).Text}. Nothing changed.";
            return 0;
        }

        var c = q.Device.CanInputs[free[0]];
        Make(c, baseId, cb.Name, signal, cb.TimeoutMs);
        // the user's own name of this signal follows it
        if (cb.Inputs.FirstOrDefault(i => i.Signal == signal) is { } other && Label(cb, signal, other.Input) != $"{cb.Name} {signal.Text}")
            c.Name = other.Input.Name;
        var state = PdmFactoryDefaults.CanInState(q.Device, free[0]);
        return signal.IsValue ? state + 1 : state;
    }

    // every signal of every CANBoard for the pickers of board role (switches: on / off; analog, rotary: numbers)
    public static IReadOnlyList<PdmCanBoardChoice> Choices(PdmView v, string role, bool values)
    {
        var list = new List<PdmCanBoardChoice>();
        foreach (var cb in All(v))
        foreach (var s in Signals.Where(s => s.IsValue == values && (s.Kind != PdmCanBoardKind.Rotary || cb.HasRotary)))
        {
            var here = cb.Inputs.FirstOrDefault(i => i.Role == role && i.Signal == s);
            var any = here ?? cb.Inputs.FirstOrDefault(i => i.Signal == s);
            list.Add(new PdmCanBoardChoice($"cb:{cb.BaseId:X}:{s.Key}", cb.BaseId, s, here?.Var ?? 0, Label(cb, s, any?.Input)));
        }

        return list;
    }

    public static PdmCanBoardChoice? Choice(PdmView v, string role, string? key) =>
        key == null || !key.StartsWith("cb:", StringComparison.Ordinal) ? null
            : Choices(v, role, false).Concat(Choices(v, role, true)).FirstOrDefault(c => c.Key == key);

    // what reads a CANBoard's inputs (texts), board by board
    public static IReadOnlyList<string> Readers(PdmView v, PdmCanBoardInfo cb)
    {
        var m = PdmModel.Build(v);
        return cb.Inputs.SelectMany(i => PdmValues.ReadersOf(m, i.Role, i.Var, [new PdmRes(i.Role, PdmResKind.CanInput, i.Slot)])
            .Select(r => $"{Label(cb, i.Signal, i.Input)} is used by {r}")).Distinct().ToList();
    }

    // null = removed (its CAN inputs and its output frames fresh again); refused while something reads one of its inputs
    public static string? Remove(PdmView v, int baseId)
    {
        if (Find(v, baseId) is not { } cb) return $"There is no CANBoard at {Hex(baseId)}.";
        if (Readers(v, cb) is { Count: > 0 } readers)
            return $"{cb.Name} is still in use: {string.Join("; ", readers.Take(3))}{(readers.Count > 3 ? $" and {readers.Count - 3} more" : "")}. Change that first. Nothing changed.";
        foreach (var i in cb.Inputs) PdmLinks.Reset(i.Input);
        foreach (var o in cb.Outputs) ResetOut(o.Out);
        return null;
    }

    public static string? Rename(PdmView v, int baseId, string? name)
    {
        if (Find(v, baseId) is not { } cb) return $"There is no CANBoard at {Hex(baseId)}.";
        name = (name ?? "").Trim();
        if (NameProblem(v, name, baseId) is { } bad) return bad;
        foreach (var i in cb.Inputs.Where(i => (i.Input.Name ?? "").Trim() == SlotName(cb.Name, i.Signal) || i.Signal is { Kind: PdmCanBoardKind.Switch, Number: 1 }))
            i.Input.Name = SlotName(name, i.Signal);
        foreach (var o in cb.Outputs) o.Out.Name = OutName(name, o.Number);
        return null;
    }

    // ---------------- its 4 outputs (driven by PDM signals through the stock CAN outputs) ----------------

    private static string OutName(string name, int n) => $"{name} output {n}";

    private static void ResetOut(CanOutput c)
    {
        var fresh = new CanOutput(c.Number, "canOutput" + c.Number);
        for (var i = 0; i < c.Params.Count; i++) c.Params[i].SetValue(fresh.Params[i].GetValue());
        c.Name = fresh.Name;
    }

    // on / off signals of every board that can drive a CANBoard output
    public static IReadOnlyList<PdmWideChoice> OutputSources(PdmModel m, PdmView v) =>
        PdmWide.Vars(m, v).Where(c => c.Var > PdmTriggers.AlwaysOnVar
                                      && v.Boards.First(b => b.Role == c.Role).Device.VarMap.First(e => e.VariableIndex == c.Var).DataType == "bool").ToList();

    // CANBoard output n (1-4) follows on / off signal var of board role: one CAN output of that board, one byte of
    // its command frame (base + 0x10 + board), 1 = on, every 100 ms. null = set; else why not (nothing changed).
    public static string? SetOutput(PdmView v, int baseId, int n, string role, int var)
    {
        if (Find(v, baseId) is not { } cb) return $"There is no CANBoard at {Hex(baseId)}.";
        if (n is < 1 or > Outs) return $"A CANBoard has outputs 1 to {Outs}.";
        var q = v.Boards.FirstOrDefault(b => b.Role == role);
        if (q == null) return $"{role} is not in this PDM.";
        if (var <= PdmTriggers.AlwaysOnVar || q.Device.VarMap.FirstOrDefault(e => e.VariableIndex == var) is not { DataType: "bool" })
            return "Pick an on / off signal of the PDM for this output.";
        var snap = PdmSnapshot.Take(v);
        if (cb.Outputs.FirstOrDefault(o => o.Number == n) is { } old) ResetOut(old.Out);
        var why = PdmValues.AddCanOut(v, new PdmCanOutSpec(role, CommandId(baseId, role), 8 * (n - 1), 8, var, IntervalMs: PeriodMs), out var index);
        if (why != null)
        {
            snap.Restore();
            return why;
        }

        q.Device.CanOutputs[index].Name = OutName(cb.Name, n);
        return null;
    }

    public static string? ClearOutput(PdmView v, int baseId, int n)
    {
        if (Find(v, baseId) is not { } cb) return $"There is no CANBoard at {Hex(baseId)}.";
        if (cb.Outputs.FirstOrDefault(o => o.Number == n) is { } old) ResetOut(old.Out);
        return null;
    }

    public static string OutWords(PdmModel m, PdmCanBoardInfo cb, PdmCanBoardOut o) =>
        $"{cb.Name} output {o.Number} follows {PdmTriggers.VarText(m, o.Role, o.Out.Input)} (frame {Hex(o.Id)} byte {o.StartBit / 8}, 1 = on, every {o.Out.Interval} ms)";

    // What must be set ONCE on the CANBoard itself with dingoConfig (it is its own device on the bus): plain steps
    public static IReadOnlyList<string> SetupSteps(PdmCanBoardInfo cb)
    {
        var steps = new List<string>
        {
            "CAN bit rate: 1000K (a new CANBoard is on 500K: connect to it at 500K once, set 1000K, Burn, restart it).",
            $"Base ID: {Hex(cb.BaseId)}{(cb.BaseId == DefaultBaseId ? " (its factory value)" : "")}."
        };
        if (cb.HasRotary) steps.Add("Rotary switches: set those analog inputs to rotary on the CANBoard (else their position stays 0).");
        foreach (var o in cb.Outputs)
            steps.Add($"Output {o.Number}: CAN input {o.Number} = ID {Hex(o.Id)}, start bit {o.StartBit}, 8 bits, Equal 1, time-out on, {cb.TimeoutMs} ms; " +
                      $"digital output {o.Number} enabled, input = CAN input {o.Number}.");
        return steps;
    }

    // ---------------- bus load ----------------

    // bits of one frame on the wire: frame + average stuffing + interframe space (firmware/sim/pdmsim.py Bus)
    public static double FrameBits(int dlc) => (47 + 8 * dlc) * 1.15 + 3;

    // The frames one CANBoard adds to the bus every 100 ms: its 3 always-sent status frames, the PDM's command
    // frames to it, and what the PDM boards then send more themselves: a board sends one "CAN input values" frame
    // per pair of enabled CAN inputs (msgs 7-22) and msg 5 once any is enabled (firmware/boards/custompdm_*/msg.cpp
    // bSend; DbcExport.MessageComment). An upper figure: a pair or msg 5 may be on the bus already for another input.
    // Not added yet (null): the 13 inputs on one board = 7 pairs + msg 5.
    public static double FrameBitsPer100Ms(PdmCanBoardInfo? cb)
    {
        var pdm = cb == null ? (Need(false) + 1) / 2 + 1
            : cb.Inputs.Select(i => (i.Role, i.Slot / 2)).Distinct().Count() + cb.Inputs.Select(i => i.Role).Distinct().Count();
        var bits = (3 + pdm) * FrameBits(8);
        if (cb != null)
            foreach (var g in cb.Outputs.GroupBy(o => o.Id))
                bits += FrameBits(g.Max(o => o.StartBit / 8) + 1) * PeriodMs / Math.Max(1, g.Min(o => o.Out.Interval));
        return bits;
    }

    // ... as a share of the bus, in %
    public static double BusLoadPercent(PdmCanBoardInfo? cb, int bitRate = 1000000) => FrameBitsPer100Ms(cb) * (1000.0 / PeriodMs) / bitRate * 100.0;

    public static string BusLoadText(PdmView v)
    {
        var all = All(v);
        if (all.Count == 0) return $"One CANBoard adds about {BusLoadPercent(null).ToString("0.0", CultureInfo.InvariantCulture)} % bus load (its 3 frames and the PDM's own frames for its inputs, every {PeriodMs} ms at 1 Mbit/s).";
        var sum = all.Sum(c => BusLoadPercent(c));
        return $"{all.Count} CANBoard{(all.Count == 1 ? "" : "s")}: about {sum.ToString("0.0", CultureInfo.InvariantCulture)} % bus load added (at 1 Mbit/s).";
    }
}
