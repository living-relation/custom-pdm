using domain.Devices;
using domain.Devices.Functions;
using domain.Enums;

namespace domain.CustomPdm;

// custom-pdm route B, phase B3 (docs/ui-route-b-plan.md): settings that are set ONCE for the PDM on /pdm.
// Every change here is a PC edit only: it reaches the boards with the /pdm Write All (PdmOps), and is kept over a
// power cycle only after Burn. Base IDs are the exception, see PdmOpsService.ChangeBaseId.
// - Temperature limits (param block 0x7F00 subs 0-2 and 4): one set for all three boards (u1a, 2026-11-16).
// - Fan on / off thresholds: the fan logic on A2 (port_boards.py, PdmFactoryDefaults) holds each threshold three
//   times: condition FAN_COND0 (A2's own sensor), and the operand of two CAN inputs (A1 and B board temperature).
//   On = condition FAN_COND0 + CAN inputs FAN_CANIN0 / + 2, off = condition FAN_COND0 + 1 + CAN inputs + 1 / + 3.
// - Base IDs: one board uses base .. base + 0x27 (40 IDs: config to / from the PC tool, 38 cyclic msgs); A2's fan
//   CAN inputs listen to A1 / B base + 2 (their msg 0).
public record PdmTempLimits(int Warn, int Crit, int Hyst, int Margin)
{
    public static PdmTempLimits? Of(FwDevice d) =>
        d.CustomPdm is { } c ? new PdmTempLimits(c.TempWarn, c.TempCrit, c.TempCritHyst, c.TempCritSoonMargin) : null;

    // Ranges: firmware core/param_defs.h (as CustomPdmSettings). Warn below critical: the firmware does not check it,
    // but a warning at or above critical would never come first.
    public string? Problem()
    {
        static bool In(int v, int min, int max) => v >= min && v <= max;
        if (!In(Warn, CustomPdmSettings.TempMin, CustomPdmSettings.TempMax)) return $"Warn must be {CustomPdmSettings.TempMin} to {CustomPdmSettings.TempMax} C.";
        if (!In(Crit, CustomPdmSettings.TempMin, CustomPdmSettings.TempMax)) return $"Critical must be {CustomPdmSettings.TempMin} to {CustomPdmSettings.TempMax} C.";
        if (Warn >= Crit) return "Warn must be below critical.";
        if (!In(Hyst, CustomPdmSettings.HystMin, CustomPdmSettings.HystMax)) return $"Recovery hysteresis must be {CustomPdmSettings.HystMin} to {CustomPdmSettings.HystMax} C.";
        if (!In(Margin, CustomPdmSettings.MarginMin, CustomPdmSettings.MarginMax)) return $"Critical-soon margin must be {CustomPdmSettings.MarginMin} to {CustomPdmSettings.MarginMax} C.";
        return null;
    }
}

public record PdmFanThresholds(double On, double Off)
{
    // The firmware takes any float (-1e9..1e9); the board temperature limits are 0-125 C, so are these.
    public const double Min = CustomPdmSettings.TempMin, Max = CustomPdmSettings.TempMax;

    public string? Problem()
    {
        if (On is < Min or > Max) return $"Fan on must be {Min:0} to {Max:0} C.";
        if (Off is < Min or > Max) return $"Fan off must be {Min:0} to {Max:0} C.";
        if (Off >= On) return "Fan off must be below fan on.";
        return null;
    }
}

public static class PdmLinked
{
    public const int BlockSize = 0x28;
    public const int MaxBase = 0x7FF - (BlockSize - 1);

    private static FwDevice? Board(PdmView v, string role) => v.Boards.FirstOrDefault(b => b.Role == role)?.Device;

    // ---------------- temperature limits ----------------

    public static IReadOnlyList<(string Role, PdmTempLimits Limits)> TempLimitsByBoard(PdmView v) =>
        v.Boards.Where(b => b.Device.CustomPdm != null).Select(b => (b.Role, PdmTempLimits.Of(b.Device)!)).ToList();

    public static bool TempLimitsDiffer(PdmView v) => TempLimitsByBoard(v).Select(t => t.Limits).Distinct().Count() > 1;

    // null = set on every board of the view; else why not (nothing changed)
    public static string? SetTempLimits(PdmView v, PdmTempLimits t)
    {
        if (t.Problem() is { } why) return why;
        foreach (var c in v.Boards.Select(b => b.Device.CustomPdm).OfType<CustomPdmSettings>())
            (c.TempWarn, c.TempCrit, c.TempCritHyst, c.TempCritSoonMargin) = (t.Warn, t.Crit, t.Hyst, t.Margin);
        return null;
    }

    // ---------------- fan thresholds (A2) ----------------

    private static (Condition On, Condition Off, CanInput[] Remote) FanParts(FwDevice a2)
    {
        var c0 = PdmFactoryDefaults.FanCond0(a2);
        return (a2.Conditions[c0], a2.Conditions[c0 + 1], a2.CanInputs.Skip(PdmFactoryDefaults.FanCanIn0).Take(4).ToArray());
    }

    // null = the fan logic on A2 has the factory layout (enabled, inputs and operators as port_boards.py); else why
    // the PDM page leaves it alone (changed by hand on A2's own page)
    public static string? FanLayoutProblem(FwDevice a2)
    {
        var (on, off, remote) = FanParts(a2);
        var temp = PdmFactoryDefaults.BoardTempVar(a2);
        var ok = on is { Enabled: true, Operator: Operator.GreaterThanOrEqual } && on.Input == temp
                 && off is { Enabled: true, Operator: Operator.LessThanOrEqual } && off.Input == temp
                 && remote.Select((c, k) => c.Enabled && c.Operator == (k % 2 == 0 ? Operator.GreaterThanOrEqual : Operator.LessThanOrEqual)).All(x => x);
        return ok ? null : "The fan logic on A2 is not the factory layout (changed on A2's own page?): set the fan thresholds there.";
    }

    // The 6 values, for the page (and for "they differ")
    public static IReadOnlyList<string> FanParamsText(FwDevice a2)
    {
        var (on, off, r) = FanParts(a2);
        var n0 = PdmFactoryDefaults.FanCanIn0 + 1;
        return
        [
            $"A2 own on (condition {on.Number}) {on.Arg:0.#}", $"A1 hot (CAN input {n0}) {r[0].Operand:0.#}", $"B hot (CAN input {n0 + 2}) {r[2].Operand:0.#}",
            $"A2 own off (condition {off.Number}) {off.Arg:0.#}", $"A1 cool (CAN input {n0 + 1}) {r[1].Operand:0.#}", $"B cool (CAN input {n0 + 3}) {r[3].Operand:0.#}"
        ];
    }

    // null when the layout is not the factory one or the 6 values do not agree
    public static PdmFanThresholds? FanThresholds(FwDevice a2)
    {
        if (FanLayoutProblem(a2) != null) return null;
        var (on, off, r) = FanParts(a2);
        // the firmware stores floats: compare as floats, as the board would hand them back
        static bool Same(params double[] x) => x.All(v => (float)v == (float)x[0]);
        return Same(on.Arg, r[0].Operand, r[2].Operand) && Same(off.Arg, r[1].Operand, r[3].Operand)
            ? new PdmFanThresholds(on.Arg, off.Arg) : null;
    }

    public static string? SetFanThresholds(FwDevice a2, PdmFanThresholds f)
    {
        if (FanLayoutProblem(a2) is { } layout) return layout;
        if (f.Problem() is { } why) return why;
        var (on, off, r) = FanParts(a2);
        (on.Arg, off.Arg) = (f.On, f.Off);
        (r[0].Operand, r[1].Operand, r[2].Operand, r[3].Operand) = (f.On, f.Off, f.On, f.Off);
        return null;
    }

    // A2's fan CAN inputs and the board they should hear (k = 0..3: A1 hot, A1 cool, B hot, B cool)
    private static IEnumerable<(string Remote, int[] Slots)> FanRemotes() => [("A1", [0, 1]), ("B", [2, 3])];

    private static string FanSlotsText(int[] slots, string remote) =>
        $"A2 CAN inputs {string.Join(", ", slots.Select(k => PdmFactoryDefaults.FanCanIn0 + k + 1))} (fan, {remote} temperature)";

    public static IReadOnlyList<string> FanRemoteIdProblems(PdmView v)
    {
        var a2 = Board(v, "A2");
        if (a2 == null || FanLayoutProblem(a2) != null) return [];
        var list = new List<string>();
        foreach (var (remote, slots) in FanRemotes())
        {
            var dev = Board(v, remote);
            if (dev == null) continue;
            var want = dev.BaseId + PdmFactoryDefaults.CyclicTxOffset;
            var have = slots.Select(k => a2.CanInputs[PdmFactoryDefaults.FanCanIn0 + k].Id).Distinct().ToList();
            if (have.Count != 1 || have[0] != want)
                list.Add($"{FanSlotsText(slots, remote)} listen to {string.Join(" / ", have.Select(h => $"0x{h:X3}"))}, {remote} sends its temperature on 0x{want:X3}.");
        }
        return list;
    }

    public static void PointFanAtBoards(PdmView v)
    {
        var a2 = Board(v, "A2");
        if (a2 == null || FanLayoutProblem(a2) != null) return;
        foreach (var (remote, slots) in FanRemotes())
            if (Board(v, remote) is { } dev)
                foreach (var k in slots) a2.CanInputs[PdmFactoryDefaults.FanCanIn0 + k].Id = dev.BaseId + PdmFactoryDefaults.CyclicTxOffset;
    }

    // ---------------- base IDs ----------------

    private static string Block(int b) => $"0x{b:X3}-0x{b + BlockSize - 1:X3}";

    // null = role may move to newBase
    public static string? BaseIdProblem(PdmView v, string role, int newBase)
    {
        if (newBase < 0 || newBase > MaxBase) return $"Base ID must be 0x000 to 0x{MaxBase:X3} (the board uses base to base + 0x{BlockSize - 1:X2}).";
        if (role == "A1" && Board(v, "A2") is { } a2 && newBase >= a2.BaseId)
            return $"A1 must stay below A2 (0x{a2.BaseId:X3}): the PDM page tells the two A boards apart by base ID.";
        if (role == "A2" && Board(v, "A1") is { } a1 && newBase <= a1.BaseId)
            return $"A2 must stay above A1 (0x{a1.BaseId:X3}): the PDM page tells the two A boards apart by base ID.";
        foreach (var other in v.Boards.Where(b => b.Role != role))
            if (newBase < other.Device.BaseId + BlockSize && other.Device.BaseId < newBase + BlockSize)
                return $"{role} {Block(newBase)} would overlap {other.Role} ({Block(other.Device.BaseId)}).";
        return null;
    }

    // Links into the moved board that the tool does NOT move by itself (only A2's fan inputs are moved), and CAN
    // outputs that would send inside the new block.
    public static IReadOnlyList<string> BaseIdWarnings(PdmView v, string role, int newBase)
    {
        var moved = Board(v, role);
        if (moved == null) return [];
        var old = moved.BaseId;
        var list = new List<string>();
        foreach (var b in v.Boards)
        {
            for (var i = 0; i < b.Device.CanInputs.Count; i++)
            {
                var ci = b.Device.CanInputs[i];
                if (!ci.Enabled || ci.Ide || ci.Id < old || ci.Id >= old + BlockSize) continue;
                if (IsFanSlotFor(v, b, i, role) || PdmLinks.FollowsBoard(v, b, i, role)) continue; // B4: link slots follow too
                list.Add($"{b.Role} CAN input {ci.Number} listens to 0x{ci.Id:X3} ({role}'s old block): change it by hand.");
            }
        }
        foreach (var b in v.Boards)
            foreach (var co in b.Device.CanOutputs)
                if (co.Enabled && co.Id >= newBase && co.Id < newBase + BlockSize)
                    list.Add($"{b.Role} CAN output {co.Number} sends on 0x{co.Id:X3}, inside {role}'s new block {Block(newBase)}.");
        return list;
    }

    private static bool IsFanSlotFor(PdmView v, PdmBoard b, int i, string role) =>
        b.Role == "A2" && FanLayoutProblem(b.Device) == null
        && FanRemotes().Any(r => r.Remote == role && r.Slots.Contains(i - PdmFactoryDefaults.FanCanIn0));

    // Before role moves to newBase: A2's fan CAN inputs that listen to the role's msg 0 follow it, and (B4) every
    // cross-board link slot that listens to the role's msg 37. Returns what moved.
    public static IReadOnlyList<string> FollowBaseId(PdmView v, string role, int newBase)
    {
        var list = new List<string>(PdmLinks.FollowBaseId(v, role, newBase));
        var moved = Board(v, role);
        var a2 = Board(v, "A2");
        if (moved == null || a2 == null || FanLayoutProblem(a2) != null) return list;
        foreach (var (remote, slots) in FanRemotes().Where(r => r.Remote == role))
        {
            var cis = slots.Select(k => a2.CanInputs[PdmFactoryDefaults.FanCanIn0 + k]).ToList();
            if (cis.Any(c => c.Id != moved.BaseId + PdmFactoryDefaults.CyclicTxOffset)) continue; // not on this board now: left alone
            foreach (var c in cis) c.Id = newBase + PdmFactoryDefaults.CyclicTxOffset;
            list.Add($"{FanSlotsText(slots, remote)} -> 0x{newBase + PdmFactoryDefaults.CyclicTxOffset:X3}");
        }
        return list;
    }
}
