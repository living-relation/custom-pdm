using domain.Devices;
using domain.Enums;
using domain.Interfaces;

namespace domain.CustomPdm;

// custom-pdm route B, phase B3 (u2a, 2026-11-16): a "New PDM" project starts from OUR firmware's built-in defaults,
// not from the stock dingoConfig ones. Source: firmware/tools_custom/port_boards.py (FACTORY / THERMAL blocks, the
// DEFAULT_* macros it writes into firmware/boards/custompdm_*/port.h) plus the stock dingoFW defaults that differ from
// the stock PC defaults (core/param_defs.h: analog switch threshold, rotary step / max position).
// Proof that nothing differs: ui/tests PdmB3LiveSimTests compares EVERY param of a New PDM project with a Read All of
// fresh sim boards (real firmware). PdmLinkedTests checks the constants below against port_boards.py.
// Numbers here count from 0 (firmware / param index); the dingoConfig UI shows them from 1.
public static class PdmFactoryDefaults
{
    public const int BaseA1 = 0x500, BaseA2 = 0x540, BaseB = 0x580;   // port_boards.py BASE_A1, BASE_A2, BASE_B
    public const int CyclicTxOffset = 2;                                 // cyclic msg n = base + 2 + n; msg 0 has the board temperature
    public const double FanOnC = 45.0, FanOffC = 40.0;                   // FAN_ON_C / FAN_OFF_C (s12a)
    public const int FanOutput = 1;                                      // A2 OUT2 (r7a)
    public const int FanCanIn0 = 24;                                     // FAN_CANIN0: A1 hot, A1 cool, B hot, B cool
    public const int TempMsgStartBit = 48, TempMsgBitLength = 16;        // msg 0 bytes 6-7, board temperature x10, signed
    public const double TempMsgFactor = 0.1;
    public const double FanCurrentLimit = 1.0, FanInrushLimit = 2.0;
    public static readonly double[] ShedOnC = [70.0, 75.0], ShedOffC = [65.0, 70.0]; // SHED_ON_C / SHED_OFF_C (r5a, off)
    public const int AnalogSwitchThreshold = 2000, RotaryStep = 100, RotaryMaxPos = 10; // stock dingoFW param_defs.h

    public static readonly (string Role, int Type, int BaseId)[] Boards = [("A1", 14, BaseA1), ("A2", 14, BaseA2), ("B", 15, BaseB)];

    public static int BaseFor(string role) => Boards.Single(b => b.Role == role).BaseId;

    // Factory current limit of output i (0-based) = its rating (Dan w3a; port_boards.py LIMIT_*), the fan output 1 A.
    // Inrush limits are the stock 50 A (the PC default too), the fan 2 A.
    public static double CurrentLimit(string role, int i) => role == "A2" && i == FanOutput ? FanCurrentLimit : PdmView.Rating(role, i);

    // Slot layout of port_boards.py: SHED_COND0 = NUM_CONDITIONS - 4, SHED_VIRT0 = NUM_VIRT_INPUTS - 2,
    // FAN_COND0 = SHED_COND0 - 2, FAN_VIRT0 = SHED_VIRT0 - 3
    public static int ShedCond0(FwDevice d) => d.Conditions.Count - 4;
    public static int ShedVirt0(FwDevice d) => d.VirtualInputs.Count - 2;
    public static int FanCond0(FwDevice d) => ShedCond0(d) - 2;
    public static int FanVirt0(FwDevice d) => ShedVirt0(d) - 3;

    // Variable-map index (the firmware's VAR_* numbers) of a function's first variable (its state / value), from the
    // PC's own map
    public static int VarOf(FwDevice d, IDeviceFunction f) => d.VarMap.First(v => ReferenceEquals(v.Owner, f)).VariableIndex;

    public static int CanInState(FwDevice d, int i) => VarOf(d, d.CanInputs[i]);   // VAR_CANIN(i) = fOutput

    public static int BoardTempVar(FwDevice d) => d.VarMap.First(v => v.Owner == null && v.GetName() == "Temperature").VariableIndex;

    // Sets every value of a fresh PC device that our firmware's factory config has differently. Marks the device
    // FactoryNew: its Write All needs no Read All first (CustomPdmGuards).
    public static void Apply(FwDevice d, string role)
    {
        if (d.CustomPdm == null) throw new ArgumentException($"{d.Name} is not a custom-pdm board");
        d.CustomPdm.FactoryNew = true;
        d.BaseId = BaseFor(role);
        d.BitRate = CanBitRate.BitRate1000K;                       // DEFAULT_CAN_BITRATE
        foreach (var o in d.Outputs) o.ResetMode = ResetMode.Count; // DEFAULT_RESET_MODE
        (d.CustomPdm.TempWarn, d.CustomPdm.TempCrit) =               // DEFAULT_TEMP_WARN / _CRIT (board B: its own, fwsafety)
            (CustomPdmSettings.TempWarnDefault(d.DeviceTypeId), CustomPdmSettings.TempCritDefault(d.DeviceTypeId));
        for (var i = 0; i < d.Outputs.Count; i++) d.Outputs[i].CurrentLimit = CurrentLimit(role, i); // DEFAULT_OUT_CURRENT_LIMIT
        foreach (var a in d.AnalogInputs)
        {
            a.Switch.Threshold = AnalogSwitchThreshold;
            a.Rotary.Step = RotaryStep;
            a.Rotary.MaxPos = RotaryMaxPos;
        }

        var temp = BoardTempVar(d);
        // load-shed example, prefilled and disabled: level l latch = (hot OR itself) AND NOT cool
        for (var l = 0; l < 2; l++)
        {
            var hot = d.Conditions[ShedCond0(d) + 2 * l];
            var cool = d.Conditions[ShedCond0(d) + 2 * l + 1];
            (hot.Input, hot.Operator, hot.Arg) = (temp, Operator.GreaterThanOrEqual, ShedOnC[l]);
            (cool.Input, cool.Operator, cool.Arg) = (temp, Operator.LessThanOrEqual, ShedOffC[l]);
            var vi = d.VirtualInputs[ShedVirt0(d) + l];
            (vi.Var0, vi.Cond0, vi.Var1, vi.Cond1, vi.Not2, vi.Var2) =
                (VarOf(d, hot), Conditional.Or, VarOf(d, vi), Conditional.And, true, VarOf(d, cool));
        }

        if (role != "A2") return;

        d.CustomPdm.CritExemptMask = 1 << FanOutput;               // DEFAULT_CRIT_EXEMPT_MASK (s10b)
        var c0 = FanCond0(d);
        foreach (var (c, op, arg) in new[] { (d.Conditions[c0], Operator.GreaterThanOrEqual, FanOnC), (d.Conditions[c0 + 1], Operator.LessThanOrEqual, FanOffC) })
            (c.Enabled, c.Input, c.Operator, c.Arg) = (true, temp, op, arg);

        for (var k = 0; k < 4; k++)
        {
            var ci = d.CanInputs[FanCanIn0 + k];
            var hot = k % 2 == 0;
            ci.Enabled = true;
            ci.TimeoutEnabled = true;                             // 1 s (stock default time-out)
            ci.Id = (k < 2 ? BaseA1 : BaseB) + CyclicTxOffset;    // FAN_REMOTE_MSG0: A1 / B msg 0
            (ci.StartBit, ci.BitLength, ci.Factor, ci.Signed) = (TempMsgStartBit, TempMsgBitLength, TempMsgFactor, true);
            (ci.Operator, ci.Operand) = hot ? (Operator.GreaterThanOrEqual, FanOnC) : (Operator.LessThanOrEqual, FanOffC);
        }

        // virtual inputs: any hot (OR), all cool (AND), fan latch = (any hot OR itself) AND NOT all cool
        var v0 = FanVirt0(d);
        var anyHot = d.VirtualInputs[v0];
        var allCool = d.VirtualInputs[v0 + 1];
        var latch = d.VirtualInputs[v0 + 2];
        (anyHot.Enabled, anyHot.Var0, anyHot.Cond0, anyHot.Var1, anyHot.Cond1, anyHot.Var2) =
            (true, VarOf(d, d.Conditions[c0]), Conditional.Or, CanInState(d, FanCanIn0), Conditional.Or, CanInState(d, FanCanIn0 + 2));
        (allCool.Enabled, allCool.Var0, allCool.Cond0, allCool.Var1, allCool.Cond1, allCool.Var2) =
            (true, VarOf(d, d.Conditions[c0 + 1]), Conditional.And, CanInState(d, FanCanIn0 + 1), Conditional.And, CanInState(d, FanCanIn0 + 3));
        (latch.Enabled, latch.Var0, latch.Cond0, latch.Var1, latch.Cond1, latch.Not2, latch.Var2) =
            (true, VarOf(d, anyHot), Conditional.Or, VarOf(d, latch), Conditional.And, true, VarOf(d, allCool));

        var fan = d.Outputs[FanOutput];
        (fan.Enabled, fan.Input, fan.CurrentLimit, fan.InrushCurrentLimit) = (true, VarOf(d, latch), FanCurrentLimit, FanInrushLimit);
    }
}
