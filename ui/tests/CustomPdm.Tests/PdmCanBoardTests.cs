using System.Text.RegularExpressions;
using application.Services;
using domain.CustomPdm;
using domain.Devices;
using domain.Devices.Functions;
using domain.Enums;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace CustomPdm.Tests;

// canboard (Dan, 2026-11-22): the CANBoard preset (PdmCanBoard). Live proof: CanBoardLiveSimTests.
// Numbers: outputs A1 1-8, A2 9-16 (10 = fans), B 17-24; digital inputs A1 1-7, A2 8-14, B 15-24.
public class PdmCanBoardTests
{
    private static PdmView NewPdm() => PdmLinkedTests.NewPdm();
    private static FwDevice Dev(PdmView v, string role) => v.Boards.Single(b => b.Role == role).Device;
    private static PdmModel M(PdmView v) => PdmModel.Build(v);
    private static int Free(PdmView v, string role) => M(v).FreeOf(role, PdmResKind.CanInput).Count;
    private static (int, int, int) Free(PdmView v) => (Free(v, "A1"), Free(v, "A2"), Free(v, "B"));
    private static string Fw(params string[] rel) => File.ReadAllText(Path.Combine([DbcExportTests.RepoRoot(), "firmware", .. rel]));
    private static PdmCanBoardInput In(PdmView v, PdmCanBoardKind k, int n, string? role = null) =>
        PdmCanBoard.All(v).Single().Inputs.First(i => i.Signal.Kind == k && i.Signal.Number == n && (role == null || i.Role == role));

    // fill CAN inputs of a board by hand until only `leave` are free
    private static void Fill(PdmView v, string role, int leave)
    {
        var d = Dev(v, role);
        var free = M(v).FreeOf(role, PdmResKind.CanInput);
        foreach (var s in free.Take(free.Count - leave))
            (d.CanInputs[s].Enabled, d.CanInputs[s].Id, d.CanInputs[s].Name) = (true, 0x7A0, "by hand");
    }

    // every protocol number of PdmCanBoard is the one in the CANBoard's firmware source in this repo
    [Fact]
    public void TheProtocolNumbersAreTheFirmwares()
    {
        var port = Fw("boards", "canboard_v2", "port.h");
        var msg = Regex.Replace(Fw("boards", "canboard_v2", "msg.cpp"), @"\s+", " ");
        var cfg = Fw("core", "device_config.h");
        var defs = Fw("core", "param_defs.h");
        Assert.Contains($"#define DEFAULT_BASE_ID 0x{PdmCanBoard.DefaultBaseId:X}", port);
        Assert.Contains($"#define NUM_TX_MSGS {PdmCanBoard.NumTxMsgs}", port);
        Assert.Contains($"#define NUM_DIG_INPUTS {PdmCanBoard.Switches}", port);
        Assert.Contains($"#define NUM_ANALOG_INPUTS {PdmCanBoard.Analogs}", port);
        Assert.Contains($"#define NUM_DIG_OUTPUTS {PdmCanBoard.Outs}", port);
        Assert.Contains("#define NUM_CAN_INPUTS 8", port);                  // enough for its 4 outputs
        Assert.DoesNotContain("DEFAULT_CAN_BITRATE", port);                   // so it starts on the stock 500K
        Assert.Contains("#define DEFAULT_CAN_BITRATE CanBitrate::Bitrate_500K", defs);
        Assert.Contains($"#define CYCLIC_TX_OFFSET {DbcExport.CyclicTxOffset}", cfg);
        Assert.Contains($"#define CAN_TX_CYCLIC_MSG_DELAY {PdmCanBoard.PeriodMs}", cfg);
        Assert.Equal(15, PdmCanBoard.StatusIds);
        // msg 0: analog 1-4 as uint16; msg 1: analog 5 first; msg 2: rotaries in nibbles, inputs in byte 4, outputs in byte 6
        string Body(int n) => Regex.Match(msg, $@"CANTxMsg TxMsg{n}\(\) \{{(.*?)return stMsg;").Groups[1].Value;
        for (var i = 0; i < 4; i++) Assert.Contains($"data16[{i}] = (uint16_t)(GetAnalogInputMv({i}));", Body(0));
        Assert.Contains("data16[0] = (uint16_t)(GetAnalogInputMv(4));", Body(1));
        var m2 = Body(2);
        Assert.Contains("data8[0] = (GetRotarySwitchPos(1) << 4) + GetRotarySwitchPos(0);", m2);
        Assert.Contains("data8[1] = (GetRotarySwitchPos(3) << 4) + GetRotarySwitchPos(2);", m2);
        Assert.Contains("data8[2] = GetRotarySwitchPos(4);", m2);
        Assert.Contains("data8[4] = (GetDigInputVal(7) << 7) + (GetDigInputVal(6) << 6)", m2);
        Assert.Contains("+ (GetDigInputVal(1) << 1) + GetDigInputVal(0);", m2);
        Assert.Contains("data8[6] = (GetDigOutputState(3) << 3) + (GetDigOutputState(2) << 2) + (GetDigOutputState(1) << 1) + GetDigOutputState(0);", m2);
        Assert.Contains("data8[7] = nHeartbeat;", m2);
        foreach (var n in new[] { 0, 1, 2 }) Assert.Contains("stMsg.bSend = true;", Body(n));
        foreach (var n in new[] { 0, 1, 2 }) Assert.Contains($"stConfig.stDevice.nBaseId + CYCLIC_TX_OFFSET + {n})", Body(n));
        // the signals as bits of those frames
        Assert.Equal((4, 34, 1), (PdmCanBoard.Signal(PdmCanBoardKind.Switch, 3).IdOffset, PdmCanBoard.Signal(PdmCanBoardKind.Switch, 3).StartBit, PdmCanBoard.Signal(PdmCanBoardKind.Switch, 3).Length));
        Assert.Equal((2, 16, 16), (PdmCanBoard.Signal(PdmCanBoardKind.Analog, 2).IdOffset, PdmCanBoard.Signal(PdmCanBoardKind.Analog, 2).StartBit, PdmCanBoard.Signal(PdmCanBoardKind.Analog, 2).Length));
        Assert.Equal((3, 0, 16), (PdmCanBoard.Signal(PdmCanBoardKind.Analog, 5).IdOffset, PdmCanBoard.Signal(PdmCanBoardKind.Analog, 5).StartBit, PdmCanBoard.Signal(PdmCanBoardKind.Analog, 5).Length));
        Assert.Equal((4, 4, 4), (PdmCanBoard.Signal(PdmCanBoardKind.Rotary, 2).IdOffset, PdmCanBoard.Signal(PdmCanBoardKind.Rotary, 2).StartBit, PdmCanBoard.Signal(PdmCanBoardKind.Rotary, 2).Length));
        Assert.Equal((4, 16, 4), (PdmCanBoard.Signal(PdmCanBoardKind.Rotary, 5).IdOffset, PdmCanBoard.Signal(PdmCanBoardKind.Rotary, 5).StartBit, PdmCanBoard.Signal(PdmCanBoardKind.Rotary, 5).Length));
        // a dingoFW CAN input with its time-out on reads 0 / off when the frames stop
        Assert.Matches(@"if \(SYS_TIME - nLastRxTime > pConfig->nTimeout\)\s*\{\s*fVal = 0;\s*fOutput = 0;", Fw("functions", "can_input.cpp"));
    }

    [Fact]
    public void AddMakesThirteenNamedInputsOnTheBoardWithTheMostRoomAndTheyReadBack()
    {
        var v = NewPdm();
        Assert.Equal((32, 28, 32), Free(v));
        Assert.Empty(PdmCanBoard.All(v));
        Assert.Equal("CANBoard 1", PdmCanBoard.NextName(v));
        Assert.Null(PdmCanBoard.Add(v, 0x640, null));
        Assert.Equal((19, 28, 32), Free(v));                     // A1 and B tie at 32: board order
        var cb = Assert.Single(PdmCanBoard.All(v));
        Assert.Equal((0x640, "CANBoard 1", 13, false, 1000), (cb.BaseId, cb.Name, cb.Inputs.Count, cb.HasRotary, cb.TimeoutMs));
        var s3 = In(v, PdmCanBoardKind.Switch, 3).Input;
        Assert.True(s3 is { Enabled: true, Id: 0x644, StartBit: 34, BitLength: 1, Operator: Operator.Equal, Operand: 1.0, TimeoutEnabled: true, Timeout: 1000,
            ByteOrder: ByteOrder.LittleEndian, Name: "CANBoard 1 switch 3" });
        var a2 = In(v, PdmCanBoardKind.Analog, 2).Input;
        Assert.True(a2 is { Enabled: true, Id: 0x642, StartBit: 16, BitLength: 16, Operator: Operator.GreaterThanOrEqual, Factor: 1.0, Offset: 0.0, Signed: false,
            TimeoutEnabled: true, Timeout: 1000 });
        Assert.True(In(v, PdmCanBoardKind.Analog, 5).Input is { Id: 0x643, StartBit: 0, BitLength: 16 });
        // in the same pickers as real inputs, by their plain names; anyone may read them (claimed as values)
        var m = M(v);
        Assert.Contains(PdmTriggers.SignalChoices(m, "A1"), c => c.Text == "CANBoard 1 switch 3" && c.Var == In(v, PdmCanBoardKind.Switch, 3).Var);
        Assert.Contains(PdmTriggers.ValueChoices(m, "A1"), c => c.Text == "CANBoard 1 analog 2 (mV)" && c.Var == In(v, PdmCanBoardKind.Analog, 2).Var);
        Assert.DoesNotContain(PdmTriggers.ValueChoices(m, "A1"), c => c.Text.Contains("switch"));     // a switch is on / off only
        Assert.DoesNotContain(PdmTriggers.SignalChoices(m, "A1"), c => c.Text.Contains("analog"));    // an analog input is a number only
        Assert.Equal(8, PdmTriggers.SignalChoices(m, "A1").Count(c => c.Text.StartsWith("CANBoard 1 ")));
        Assert.Equal(5, PdmTriggers.ValueChoices(m, "A1").Count(c => c.Text.StartsWith("CANBoard 1 ")));
        Assert.All(cb.Inputs, i => Assert.Equal(PdmClaimKind.Value, m.ClaimOf(new PdmRes(i.Role, PdmResKind.CanInput, i.Slot)).Kind));
        Assert.Empty(m.Problems);
        Assert.Contains(PdmValues.All(m), f => f.Kind == PdmValueKind.CanBoard && f.Words == "CANBoard 1 switch 3: frame 0x644 of CANBoard 1, reads off 1 s after it goes silent");
        Assert.Contains(PdmValues.All(m), f => f.Kind == PdmValueKind.CanBoard && f.Words == "CANBoard 1 analog 2 (mV): frame 0x642 of CANBoard 1, reads 0 1 s after it goes silent");
        Assert.Contains("remove the CANBoard", PdmValues.Remove(v, new PdmRes("A1", PdmResKind.CanInput, In(v, PdmCanBoardKind.Switch, 3).Slot)));
        // the Simulator panel's own frame fields leave them to the simulated CANBoard
        Assert.Empty(PdmSim.Fields(v));
    }

    [Fact]
    public void RotaryPositionsAreFiveMoreAndTheTimeOutIsTheUsers()
    {
        var v = NewPdm();
        Assert.Null(PdmCanBoard.Add(v, 0x660, "Dash", rotary: true, timeoutMs: 500));
        var cb = Assert.Single(PdmCanBoard.All(v));
        Assert.Equal(("Dash", 18, true, 500), (cb.Name, cb.Inputs.Count, cb.HasRotary, cb.TimeoutMs));
        Assert.True(In(v, PdmCanBoardKind.Rotary, 2).Input is { Id: 0x664, StartBit: 4, BitLength: 4, Operator: Operator.GreaterThanOrEqual, Timeout: 500, Name: "Dash rotary 2" });
        Assert.Contains(PdmTriggers.ValueChoices(M(v), "A1"), c => c.Text == "Dash rotary 2 position");
        Assert.Contains("300 to 10000 ms", PdmCanBoard.Add(v, 0x680, "x", timeoutMs: 299));
        Assert.Contains("300 to 10000 ms", PdmCanBoard.Add(v, 0x680, "x", timeoutMs: 10001));
        Assert.Null(PdmCanBoard.Add(v, 0x680, "x", timeoutMs: 300));
        Assert.Null(PdmCanBoard.Add(v, 0x6A0, "y", timeoutMs: 10000));
    }

    [Fact]
    public void TooFewFreeCanInputsIsSaidInPlainWordsWithTheCountAndNothingChanges()
    {
        var v = NewPdm();
        Fill(v, "A1", 5); Fill(v, "A2", 4); Fill(v, "B", 3);
        var before = Free(v);
        var why = PdmCanBoard.Add(v, 0x640, null);
        Assert.Equal("A CANBoard needs 13 free CAN inputs on the PDM (8 switches, 5 analog inputs); only 12 are free (A1 5, A2 4, B 3). Nothing changed. " +
                     "Free some first (links, triggers that read another board's input, keypad buttons, CAN values).", why);
        Assert.Equal(before, Free(v));
        Assert.Empty(PdmCanBoard.All(v));
        // one more free slot: it fits, spread over the boards (the user never picks one)
        (Dev(v, "B").CanInputs[0].Enabled, Dev(v, "B").CanInputs[0].Id, Dev(v, "B").CanInputs[0].Name) = (false, 0, "canInput1");
        Assert.Contains("needs 18 free CAN inputs on the PDM (8 switches, 5 analog inputs, 5 rotary positions); only 13 are free", PdmCanBoard.Add(v, 0x640, null, rotary: true));
        Assert.Null(PdmCanBoard.Add(v, 0x640, null));
        Assert.Equal((0, 0, 0), Free(v));
        var cb = Assert.Single(PdmCanBoard.All(v));
        Assert.Equal(13, cb.Inputs.Count);
        Assert.Equal(["A1", "A2", "B"], cb.Inputs.Select(i => i.Role).Distinct().Order());
        // with one slot free on a board the count says "is"
        var w = NewPdm();
        Fill(w, "A1", 1); Fill(w, "A2", 0); Fill(w, "B", 0);
        Assert.Contains("only 1 is free (A1 1, A2 0, B 0)", PdmCanBoard.Add(w, 0x640, null));
    }

    [Fact]
    public void ABaseIdThatClashesWithThePdmAnEcuStreamAKeypadACanOutOrAnotherCanBoardIsRefused()
    {
        var v = NewPdm();
        Assert.Equal(0x640, PdmCanBoard.FreeBase(v));
        Assert.Equal("A CANBoard at 0x4F0 uses 0x4F0-0x502: that overlaps board A1's own IDs (0x500-0x53F). Pick another base ID, e.g. 0x640.", PdmCanBoard.Add(v, 0x4F0, null));
        Assert.Contains("overlaps board B's own IDs (0x580-0x5BF)", PdmCanBoard.Add(v, 0x5BF, null));
        Assert.Null(PdmCanBoard.Clash(v, 0x5C0));
        Assert.Null(PdmCanBoard.Clash(v, 0x4ED));                     // 0x4ED-0x4FF: just below A1
        Assert.Contains("0x001 to 0x7ED", PdmCanBoard.Add(v, 0x7EE, null));
        Assert.Contains("0x001 to 0x7ED", PdmCanBoard.Add(v, 0, null));
        Assert.Null(PdmCanBoard.Clash(v, 0x7ED));
        // the ECU stream 0x3F4
        Assert.Null(PdmEcu.Set(v, 17, PdmEcu.DefaultId, 0));
        Assert.Equal("A CANBoard at 0x3F0 uses 0x3F0-0x402: B already listens to 0x3F4 there (the ECU stream). Pick another base ID, e.g. 0x640.", PdmCanBoard.Add(v, 0x3F0, null));
        Assert.Null(PdmCanBoard.Clash(v, 0x3F5));
        Assert.Null(PdmCanBoard.Clash(v, 0x3E1));                     // 0x3E1-0x3F3
        Assert.NotNull(PdmCanBoard.Clash(v, 0x3E2));
        // a keypad button (BlinkMarine node 0x2A: 0x1AA, 0x22A, ... 0x72A) and a CAN output
        PdmValues.AddKeypadButton(v, "B", 0x2A, 3, out var why);
        Assert.Null(why);
        Assert.Contains("keypad node 0x2A uses 0x62A there", PdmCanBoard.Add(v, 0x620, null));
        var temp = PdmFactoryDefaults.BoardTempVar(Dev(v, "B"));
        Assert.Null(PdmValues.AddCanOut(v, new PdmCanOutSpec("B", 0x6A0, 0, 16, temp), out _));
        Assert.Contains("B already sends 0x6A0 there", PdmCanBoard.Add(v, 0x690, null));
        // nothing was added by the refused tries; a good one, then the reverse checks
        Assert.Empty(PdmCanBoard.All(v));
        Assert.Null(PdmCanBoard.Add(v, 0x640, null));
        Assert.Equal("There is already a CANBoard at 0x640.", PdmCanBoard.Add(v, 0x640, "two"));
        Assert.Contains("overlaps CANBoard 1 (0x640-0x652)", PdmCanBoard.Add(v, 0x652, "two"));
        Assert.Contains("overlaps CANBoard 1 (0x640-0x652)", PdmCanBoard.Add(v, 0x62E, "two"));
        Assert.Contains("already a CANBoard named canboard 1", PdmCanBoard.Add(v, 0x660, "canboard 1"));
        Assert.Equal(0x660, PdmCanBoard.FreeBase(v));
        Assert.Contains("e.g. 0x660", PdmCanBoard.Add(v, 0x650, "two"));
        Assert.Contains("inside the ID block of CANBoard 1", PdmValues.AddCanOut(v, new PdmCanOutSpec("B", 0x645, 0, 8, temp), out _));
        Assert.Contains("inside the ID block of CANBoard 1", PdmValues.AddCanOut(v, new PdmCanOutSpec("B", 0x650, 0, 8, temp), out _));   // A1's command frame, not B's
        Assert.Contains("inside the ID block of CANBoard 1", PdmEcu.Set(v, 18, 0x644, 0));
        PdmEcu.AddValue(v, "B", "x", 0x642, 0, 16, ByteOrder.LittleEndian, false, 1, 0, 1000, out why);
        Assert.Contains("inside the ID block of CANBoard 1", why);
        Assert.Null(PdmCanBoard.Add(v, 0x660, "two"));
        Assert.Contains("uses ID 0x668, inside the ID block of two (0x660-0x672)", PdmValues.KeypadClash(v, 0x68));    // 0x600 + 0x68
        Assert.Null(PdmValues.KeypadClash(v, 0x7F));
        Assert.Equal(["CANBoard 1", "two"], PdmCanBoard.All(v).Select(c => c.Name));
        Assert.Empty(M(v).Problems);
    }

    [Fact]
    public void ASwitchTriggersAnOutputOfAnyBoardAndTheCanBoardStaysWhileItIsUsed()
    {
        var v = NewPdm();
        Assert.Null(PdmCanBoard.Add(v, 0x640, null));
        v.Inputs.Single(r => r.Number == 15).Digital!.Enabled = true;
        // output 1 (A1): the switch is on A1 already
        var sw3 = PdmCanBoard.Ensure(v, "A1", 0x640, PdmCanBoard.Signal(PdmCanBoardKind.Switch, 3), out var why);
        Assert.Null(why);
        Assert.Equal(In(v, PdmCanBoardKind.Switch, 3).Var, sw3);
        Assert.Equal(19, Free(v, "A1"));
        Assert.Null(PdmTriggers.Set(v, 1, PdmTriggerSpec.Input(PdmTerm.Of(sw3))));
        var t = PdmTriggers.Of(M(v), 1);
        Assert.Equal((PdmTriggerKind.Input, "CANBoard 1 switch 3", true), (t.Kind, t.Words, t.Editor));
        Assert.Null(PdmTriggers.Conflict(v, 1));                                  // its own trigger: no "overwrite?"
        // output 17 (B): any board can hear the CANBoard, one more CAN input is made on B, once
        var pick = PdmCanBoard.Choices(v, "B", false).Single(c => c.Text == "CANBoard 1 switch 3");
        Assert.Equal(("cb:640:switch3", 0), (pick.Key, pick.Var));
        var onB = PdmCanBoard.Ensure(v, "B", pick.BaseId, pick.Signal, out why);
        Assert.Null(why);
        Assert.Equal(31, Free(v, "B"));
        Assert.Equal(onB, PdmCanBoard.Ensure(v, "B", 0x640, pick.Signal, out _));
        Assert.Equal(31, Free(v, "B"));
        Assert.Equal(onB, PdmCanBoard.Choice(v, "B", "cb:640:switch3")!.Var);
        Assert.True(In(v, PdmCanBoardKind.Switch, 3, "B").Input is { Id: 0x644, StartBit: 34, Timeout: 1000, Name: "CANBoard 1 switch 3" });
        Assert.Null(PdmTriggers.Set(v, 17, PdmTriggerSpec.Logic(PdmLogicOp.And, PdmTerm.Of(onB), PdmTerm.In(15))));
        Assert.Equal("CANBoard 1 switch 3 AND IN15", PdmTriggers.Of(M(v), 17).Words);
        // an analog level on B
        var an2 = PdmCanBoard.Ensure(v, "B", 0x640, PdmCanBoard.Signal(PdmCanBoardKind.Analog, 2), out why);
        Assert.Null(why);
        Assert.Null(PdmTriggers.Set(v, 18, PdmTriggerSpec.Level(new PdmThreshold(an2, true, 2500, 2000))));
        Assert.Equal("CANBoard 1 analog 2 (mV) on at 2500 or more, off at 2000 or less", PdmTriggers.Of(M(v), 18).Words);
        Assert.Empty(M(v).Problems);
        Assert.Equal(15, PdmCanBoard.All(v).Single().Inputs.Count);
        // rotary positions were not asked for
        Assert.Equal(0, PdmCanBoard.Ensure(v, "B", 0x640, PdmCanBoard.Signal(PdmCanBoardKind.Rotary, 1), out why));
        Assert.Equal("CANBoard 1 was added without rotary positions.", why);
        // a full board says so
        Fill(v, "A2", 0);
        Assert.Equal(0, PdmCanBoard.Ensure(v, "A2", 0x640, pick.Signal, out why));
        Assert.StartsWith("A2 is full: CANBoard 1 switch 3 needs 1 CAN input there;", why);
        // in use: it stays
        var no = PdmCanBoard.Remove(v, 0x640);
        Assert.StartsWith("CANBoard 1 is still in use: CANBoard 1 switch 3 is used by ", no);
        Assert.EndsWith("Change that first. Nothing changed.", no);
        Assert.Equal(15, PdmCanBoard.All(v).Single().Inputs.Count);
        foreach (var o in new[] { 1, 17, 18 }) Assert.Null(PdmTriggers.Set(v, o, PdmTriggerSpec.None));
        Assert.Null(PdmCanBoard.Remove(v, 0x640));
        Assert.Empty(PdmCanBoard.All(v));
        Assert.Equal((32, 0, 32), Free(v));
        Assert.Equal("There is no CANBoard at 0x640.", PdmCanBoard.Remove(v, 0x640));
    }

    [Fact]
    public void ItsFourOutputsFollowPdmSignalsThroughTheStockCanOutputs()
    {
        var v = NewPdm();
        Assert.Null(PdmCanBoard.Add(v, 0x640, null));
        var (a1, b) = (Dev(v, "A1"), Dev(v, "B"));
        var in15 = PdmFactoryDefaults.VarOf(b, b.DigitalInputs[0]);
        var in2 = PdmFactoryDefaults.VarOf(a1, a1.DigitalInputs[1]);
        Assert.Contains(PdmCanBoard.OutputSources(M(v), v), c => c.Role == "B" && c.Var == in15 && c.Text == "IN15");
        Assert.DoesNotContain(PdmCanBoard.OutputSources(M(v), v), c => c.Text.Contains("temperature"));
        Assert.Null(PdmCanBoard.SetOutput(v, 0x640, 1, "B", in15));
        Assert.Null(PdmCanBoard.SetOutput(v, 0x640, 4, "B", PdmFactoryDefaults.VarOf(b, b.DigitalInputs[1])));
        Assert.Null(PdmCanBoard.SetOutput(v, 0x640, 2, "A1", in2));
        var cb = PdmCanBoard.All(v).Single();
        Assert.Equal([(1, "B", 0x652, 0), (2, "A1", 0x650, 8), (4, "B", 0x652, 24)], cb.Outputs.Select(o => (o.Number, o.Role, o.Id, o.StartBit)));
        Assert.True(cb.Outputs[0].Out is { Enabled: true, Id: 0x652, StartBit: 0, BitLength: 8, Interval: 100, Factor: 1.0, Offset: 0.0, Name: "CANBoard 1 output 1" } o1 && o1.Input == in15);
        Assert.Equal((0x650, 0x651, 0x652), (PdmCanBoard.CommandId(0x640, "A1"), PdmCanBoard.CommandId(0x640, "A2"), PdmCanBoard.CommandId(0x640, "B")));
        Assert.Contains(PdmValues.All(M(v)), f => f.Words == "CANBoard 1 output 1 follows IN15 (frame 0x652 byte 0, 1 = on, every 100 ms)");
        Assert.Equal(
        [
            "CAN bit rate: 1000K (a new CANBoard is on 500K: connect to it at 500K once, set 1000K, Burn, restart it).",
            "Base ID: 0x640 (its factory value).",
            "Output 1: CAN input 1 = ID 0x652, start bit 0, 8 bits, Equal 1, time-out on, 1000 ms; digital output 1 enabled, input = CAN input 1.",
            "Output 2: CAN input 2 = ID 0x650, start bit 8, 8 bits, Equal 1, time-out on, 1000 ms; digital output 2 enabled, input = CAN input 2.",
            "Output 4: CAN input 4 = ID 0x652, start bit 24, 8 bits, Equal 1, time-out on, 1000 ms; digital output 4 enabled, input = CAN input 4."
        ], PdmCanBoard.SetupSteps(cb));
        // replace output 1's signal: still one CAN output for it
        Assert.Null(PdmCanBoard.SetOutput(v, 0x640, 1, "A1", in2));
        Assert.Equal([(1, "A1", 0x650, 0), (2, "A1", 0x650, 8), (4, "B", 0x652, 24)], PdmCanBoard.All(v).Single().Outputs.Select(o => (o.Number, o.Role, o.Id, o.StartBit)));
        Assert.Equal(31, M(v).FreeOf("B", PdmResKind.CanOutput).Count);
        // refused: not an on / off signal, not an output number; nothing changes
        Assert.Equal("Pick an on / off signal of the PDM for this output.", PdmCanBoard.SetOutput(v, 0x640, 3, "B", PdmFactoryDefaults.BoardTempVar(b)));
        Assert.Equal("Pick an on / off signal of the PDM for this output.", PdmCanBoard.SetOutput(v, 0x640, 3, "B", PdmTriggers.AlwaysOnVar));
        Assert.Equal("A CANBoard has outputs 1 to 4.", PdmCanBoard.SetOutput(v, 0x640, 5, "B", in15));
        Assert.Equal("A CANBoard has outputs 1 to 4.", PdmCanBoard.SetOutput(v, 0x640, 0, "B", in15));
        Assert.Equal(3, PdmCanBoard.All(v).Single().Outputs.Count);
        // a full board: the old signal of that output stays
        foreach (var c in a1.CanOutputs.Where(c => !c.Enabled)) (c.Enabled, c.Id, c.Input) = (true, 0x7B0, in2);
        Assert.Contains("A1 is full", PdmCanBoard.SetOutput(v, 0x640, 4, "A1", in2));
        Assert.Equal((4, "B", 0x652, 24), PdmCanBoard.All(v).Single().Outputs.Select(o => (o.Number, o.Role, o.Id, o.StartBit)).Last());
        Assert.Null(PdmCanBoard.ClearOutput(v, 0x640, 4));
        Assert.Equal([1, 2], PdmCanBoard.All(v).Single().Outputs.Select(o => o.Number));
        Assert.Equal(32, M(v).FreeOf("B", PdmResKind.CanOutput).Count);
        // removing the CANBoard takes its output frames along
        Assert.Null(PdmCanBoard.Remove(v, 0x640));
        Assert.DoesNotContain(a1.CanOutputs, c => c.Id == 0x650);
    }

    [Fact]
    public void RenameKeepsTheUsersOwnInputNames()
    {
        var v = NewPdm();
        Assert.Null(PdmCanBoard.Add(v, 0x640, "Wheel"));
        Assert.Null(PdmCanBoard.SetOutput(v, 0x640, 1, "B", PdmFactoryDefaults.VarOf(Dev(v, "B"), Dev(v, "B").DigitalInputs[0])));
        In(v, PdmCanBoardKind.Switch, 2).Input.Name = "Horn button";
        Assert.Equal("Horn button", PdmCanBoard.Choices(v, "A1", false).Single(c => c.Signal.Number == 2).Text);
        Assert.Equal("Horn button", PdmCanBoard.Choices(v, "B", false).Single(c => c.Signal.Number == 2).Text);   // not on B yet: the same name
        PdmCanBoard.Ensure(v, "B", 0x640, PdmCanBoard.Signal(PdmCanBoardKind.Switch, 2), out _);
        Assert.Equal("Horn button", In(v, PdmCanBoardKind.Switch, 2, "B").Input.Name);
        Assert.Null(PdmCanBoard.Rename(v, 0x640, " Steering wheel "));
        var cb = PdmCanBoard.All(v).Single();
        Assert.Equal("Steering wheel", cb.Name);
        Assert.Equal("Steering wheel switch 3", In(v, PdmCanBoardKind.Switch, 3).Input.Name);
        Assert.Equal("Horn button", In(v, PdmCanBoardKind.Switch, 2).Input.Name);
        Assert.Equal("Steering wheel output 1", cb.Outputs.Single().Out.Name);
        Assert.Contains("1 to 20 characters", PdmCanBoard.Rename(v, 0x640, ""));
        Assert.Contains("1 to 20 characters", PdmCanBoard.Rename(v, 0x640, new string('x', 21)));
        Assert.Null(PdmCanBoard.Rename(v, 0x640, new string('x', 20)));
        Assert.Contains("quote marks", PdmCanBoard.Rename(v, 0x640, "a'b"));
        // a fresh PC that only read the boards has no names: the CANBoard is still there, named by its base ID
        foreach (var i in cb.Inputs) i.Input.Name = "canInput" + i.Input.Number;
        Assert.Equal("CANBoard 0x640", PdmCanBoard.All(v).Single().Name);
        Assert.Contains(PdmTriggers.SignalChoices(M(v), "A1"), c => c.Text == "CANBoard 0x640 switch 3");
    }

    [Fact]
    public void TheDbcExportHoldsTheCanBoardFramesWithTheUsersNames()
    {
        var v = NewPdm();
        var boards = v.Boards.Select(b => new DbcBoard(b.Role, b.Device)).ToList();
        var plain = DbcExport.Build(boards);
        Assert.DoesNotContain("CANBoard", plain);
        Assert.Null(PdmCanBoard.Add(v, 0x640, "Wheel"));
        In(v, PdmCanBoardKind.Switch, 2).Input.Name = "Horn button";
        var b = Dev(v, "B");
        Assert.Null(PdmCanBoard.SetOutput(v, 0x640, 2, "B", PdmFactoryDefaults.VarOf(b, b.DigitalInputs[0])));
        var text = DbcExport.Build(boards);
        Assert.Contains("BU_: A1 A2 B Wheel\n", text);
        Assert.Contains("BO_ 1602 Wheel_Msg0: 8 Wheel\n SG_ Wheel_analog_1_mV : 0|16@1+ (1,0) [0|65535] \"mV\" Vector__XXX\n SG_ Wheel_analog_2_mV : 16|16@1+", text);
        Assert.Contains("BO_ 1603 Wheel_Msg1: 8 Wheel\n SG_ Wheel_analog_5_mV : 0|16@1+ (1,0) [0|65535] \"mV\" Vector__XXX\n SG_ Wheel_Temperature : 48|16@1+", text);
        Assert.Contains("BO_ 1604 Wheel_Msg2: 8 Wheel\n SG_ Wheel_rotary_1_position : 0|4@1+", text);
        Assert.Contains(" SG_ Wheel_switch_1 : 32|1@1+ (1,0) [0|1] \"\" Vector__XXX\n SG_ Horn_button : 33|1@1+", text);
        Assert.Contains(" SG_ Wheel_Output4_State : 51|1@1+", text);
        Assert.Contains(" SG_ Wheel_Heartbeat : 56|8@1+", text);
        Assert.Contains("BO_ 1618 Wheel_Cmd_B: 2 B\n SG_ Wheel_Output2_Cmd : 8|8@1+", text);
        Assert.Contains("CM_ BU_ Wheel \"Dingo Electronics CANBoard 'Wheel' (dingoFW), base ID 0x640", text);
        // the dingoConfig DBC parser reads it back; the PDM's own part is unchanged
        var parsed = DbcExportTests.Parse(text);
        Assert.Single(parsed, p => p.Id == 0x644 && p.Name == "Horn_button" && p.StartBit == 33 && p.Length == 1);
        Assert.Single(parsed, p => p.Id == 0x642 && p.Name == "Wheel_analog_3_mV" && p.StartBit == 32 && p.Length == 16);
        Assert.Equal(DbcExportTests.Parse(plain).Count + 4 + 2 + 5 + 4 + 8 + 5 + 4 + 1 + 1, parsed.Count);
        var cut = text.IndexOf("BO_ 1602", StringComparison.Ordinal);
        Assert.Equal(plain[..plain.IndexOf("\n\n\nCM_", StringComparison.Ordinal)].Replace("BU_: A1 A2 B\n", "BU_: A1 A2 B Wheel\n"), text[..(cut - 2)]);
    }

    [Fact]
    public async Task AProjectFileRoundTripsTheCanBoardAndTheStarterHasNone()
    {
        var files = new ConfigFileManager(NullLogger<ConfigFileManager>.Instance, new FwDeviceDefManager());
        var a = new FakePdm();
        Assert.Null(a.Run(PdmOpKind.ReadAll));
        Assert.Null(PdmCanBoard.Add(a.View, 0x660, "Wheel", rotary: true, timeoutMs: 700));
        In(a.View, PdmCanBoardKind.Switch, 2).Input.Name = "Horn button";
        var bDev = a.Dev("B");
        Assert.Null(PdmCanBoard.SetOutput(a.View, 0x660, 3, "B", PdmFactoryDefaults.VarOf(bDev, bDev.DigitalInputs[2])));
        var sw = PdmCanBoard.Ensure(a.View, "B", 0x660, PdmCanBoard.Signal(PdmCanBoardKind.Switch, 2), out _);
        Assert.Null(PdmTriggers.Set(a.View, 17, PdmTriggerSpec.Input(PdmTerm.Of(sw))));
        string Words(PdmView v)
        {
            var m = PdmModel.Build(v);
            var cb = PdmCanBoard.All(v).Single();
            return string.Join("\n", new[] { $"{cb.Name} 0x{cb.BaseId:X} {cb.TimeoutMs} {cb.HasRotary}" }
                .Concat(cb.Inputs.Select(i => $"{i.Role} {i.Slot} {PdmCanBoard.Label(cb, i.Signal, i.Input)}"))
                .Concat(cb.Outputs.Select(o => PdmCanBoard.OutWords(m, cb, o)))
                .Concat(PdmCanBoard.SetupSteps(cb)).Append(PdmTriggers.Of(m, 17).Words));
        }

        var before = Words(a.View);
        Assert.Contains("Horn button", before);
        Assert.EndsWith("\nHorn button", before);
        var path = Path.Combine(Path.GetTempPath(), $"cpdm-canboard-{Guid.NewGuid():N}.json");
        await files.SaveDevices(a.Mgr.GetDevices(), path);
        var b = new FakePdm();
        b.Open((await files.LoadDevices(path))!);
        File.Delete(path);
        Assert.Equal(before, Words(b.View));
        Assert.Equal(PdmModel.Build(a.View).Problems.Select(p => p.Text), PdmModel.Build(b.View).Problems.Select(p => p.Text));

        // the ST185 starter is unchanged: no CANBoard in it
        var starter = (await files.LoadDevices(PdmStarter.Find(AppContext.BaseDirectory)!))!;
        Assert.Empty(PdmCanBoard.All(PdmView.Build(starter.OfType<FwDevice>())));
    }

    [Fact]
    public void BusLoadOfACanBoardIsItsFramesThePdmsCommandFramesAndThePdmsOwnInputValueFrames()
    {
        // one 8-byte frame: (47 + 64) x 1.15 stuffing + 3 = 130.65 bit times (the sim bus model, pdmsim.py Bus)
        Assert.Equal(130.65, PdmCanBoard.FrameBits(8), 6);
        Assert.Equal(84.65, PdmCanBoard.FrameBits(3), 6);
        // before it is added: 3 CANBoard frames + 7 "CAN input values" frames (13 inputs in pairs) + msg 5 of that board
        Assert.Equal(11 * 130.65, PdmCanBoard.FrameBitsPer100Ms(null), 6);
        Assert.Equal(1.43715, PdmCanBoard.BusLoadPercent(null), 6);
        Assert.Equal(2.8743, PdmCanBoard.BusLoadPercent(null, 500000), 6);
        var v = NewPdm();
        Assert.Equal("One CANBoard adds about 1.4 % bus load (its 3 frames and the PDM's own frames for its inputs, every 100 ms at 1 Mbit/s).", PdmCanBoard.BusLoadText(v));
        Assert.Null(PdmCanBoard.Add(v, 0x640, null));
        Assert.Equal(11 * 130.65, PdmCanBoard.FrameBitsPer100Ms(PdmCanBoard.All(v).Single()), 6);
        Assert.Equal("1 CANBoard: about 1.4 % bus load added (at 1 Mbit/s).", PdmCanBoard.BusLoadText(v));
        // + a 3-byte command frame from B; + one switch brought onto B: one more pair and B's msg 5
        var b = Dev(v, "B");
        Assert.Null(PdmCanBoard.SetOutput(v, 0x640, 3, "B", PdmFactoryDefaults.VarOf(b, b.DigitalInputs[0])));
        Assert.Equal(11 * 130.65 + 84.65, PdmCanBoard.FrameBitsPer100Ms(PdmCanBoard.All(v).Single()), 6);
        PdmCanBoard.Ensure(v, "B", 0x640, PdmCanBoard.Signal(PdmCanBoardKind.Switch, 1), out _);
        Assert.Equal(13 * 130.65 + 84.65, PdmCanBoard.FrameBitsPer100Ms(PdmCanBoard.All(v).Single()), 6);
        b.CanOutputs.Single(o => o.Enabled).Interval = 50;                           // sent twice as often
        Assert.Equal(13 * 130.65 + 2 * 84.65, PdmCanBoard.FrameBitsPer100Ms(PdmCanBoard.All(v).Single()), 6);
        Assert.Null(PdmCanBoard.Add(v, 0x660, null));
        Assert.Equal("2 CANBoards: about 3.3 % bus load added (at 1 Mbit/s).", PdmCanBoard.BusLoadText(v));
    }

    // ---------------- the simulated CANBoard: play lines and what its frames say ----------------

    [Fact]
    public void TheSimulatedCanBoardsPlayLinesCountFromZeroAndRefuseWhatACanBoardCannotBe()
    {
        Assert.Equal(("CB 640 ADD", "CB 640 DEL", "CB 640 LINK on", "CB 66A LINK off"),
            (PdmCanBoardSim.AddLine(0x640), PdmCanBoardSim.RemoveLine(0x640), PdmCanBoardSim.LinkLine(0x640, true), PdmCanBoardSim.LinkLine(0x66A, false)));
        Assert.Equal(("CB 640 SW 0 1", "CB 640 SW 7 0"), (PdmCanBoardSim.SwitchLine(0x640, 1, true), PdmCanBoardSim.SwitchLine(0x640, 8, false)));
        Assert.Null(PdmCanBoardSim.SwitchLine(0x640, 0, true));
        Assert.Null(PdmCanBoardSim.SwitchLine(0x640, 9, true));
        Assert.Equal(("CB 640 AN 0 0", "CB 640 AN 4 5000"), (PdmCanBoardSim.AnalogLine(0x640, 1, 0), PdmCanBoardSim.AnalogLine(0x640, 5, 5000)));
        Assert.Null(PdmCanBoardSim.AnalogLine(0x640, 0, 100));
        Assert.Null(PdmCanBoardSim.AnalogLine(0x640, 6, 100));
        Assert.Null(PdmCanBoardSim.AnalogLine(0x640, 1, -1));
        Assert.Null(PdmCanBoardSim.AnalogLine(0x640, 1, 5001));
        Assert.Equal(("CB 640 ROT 0 0", "CB 640 ROT 4 15"), (PdmCanBoardSim.RotaryLine(0x640, 1, 0), PdmCanBoardSim.RotaryLine(0x640, 5, 15)));
        Assert.Null(PdmCanBoardSim.RotaryLine(0x640, 0, 1));
        Assert.Null(PdmCanBoardSim.RotaryLine(0x640, 6, 1));
        Assert.Null(PdmCanBoardSim.RotaryLine(0x640, 1, -1));
        Assert.Null(PdmCanBoardSim.RotaryLine(0x640, 1, 16));
        Assert.Equal([0x642, 0x643, 0x644], PdmCanBoardSim.WatchIds(0x640));

        var v = NewPdm();
        Assert.Null(PdmCanBoard.Add(v, 0x640, null, timeoutMs: 700));
        var (a1, b) = (Dev(v, "A1"), Dev(v, "B"));
        Assert.Null(PdmCanBoard.SetOutput(v, 0x640, 2, "A1", PdmFactoryDefaults.VarOf(a1, a1.DigitalInputs[1])));
        Assert.Null(PdmCanBoard.SetOutput(v, 0x640, 4, "B", PdmFactoryDefaults.VarOf(b, b.DigitalInputs[0])));
        Assert.Equal(["CB 640 OUT 0 off", "CB 640 OUT 1 650 8 700", "CB 640 OUT 2 off", "CB 640 OUT 3 652 24 700"], PdmCanBoardSim.OutputLines(PdmCanBoard.All(v).Single()));
    }

    [Fact]
    public void TheStatusFramesDecodeToSwitchesMillivoltsRotaryPositionsAndOutputs()
    {
        // msg 0: analog 1-4 = 100, 2600, 0x1234, 5000 mV; msg 1: analog 5 = 4321 mV; msg 2: rotary 1-5 = 1, 2, 3, 4, 15,
        // switches 1 and 8, outputs 2 and 4, heartbeat 0x7B
        var m0 = new byte[] { 100, 0, 0x28, 0x0A, 0x34, 0x12, 0x88, 0x13 };
        var m1 = new byte[] { 0xE1, 0x10, 0, 0, 0, 0, 30, 0 };
        var m2 = new byte[] { 0x21, 0x43, 0x0F, 0, 0x81, 0x02, 0x0A, 0x7B };
        var live = PdmCanBoardSim.Decode(m0, m1, m2, true);
        Assert.True(live.Alive);
        Assert.Equal([true, false, false, false, false, false, false, true], live.Switches);
        Assert.Equal([100, 2600, 0x1234, 5000, 4321], live.Mv);
        Assert.Equal([1, 2, 3, 4, 15], live.Rotary);
        Assert.Equal([false, true, false, true], live.Outputs);
        Assert.Equal(0x7B, live.Heartbeat);
        // every single switch and output bit is its own
        for (var i = 0; i < 8; i++)
            Assert.Equal(Enumerable.Range(0, 8).Select(k => k == i), PdmCanBoardSim.Decode(null, null, [0, 0, 0, 0, (byte)(1 << i), 0, 0, 0], true).Switches);
        for (var i = 0; i < 4; i++)
            Assert.Equal(Enumerable.Range(0, 4).Select(k => k == i), PdmCanBoardSim.Decode(null, null, [0, 0, 0, 0, 0, 0, (byte)(1 << i), 0], true).Outputs);
        // nothing heard yet, or stale: not on the bus, all off
        var none = PdmCanBoardSim.Decode(null, null, null, true);
        Assert.False(none.Alive);
        Assert.Equal((0, 0, 0), (none.Mv.Sum(), none.Rotary.Sum(), none.Switches.Count(x => x) + none.Outputs.Count(x => x)));
        Assert.False(PdmCanBoardSim.Decode(m0, m1, m2, false).Alive);
        Assert.Equal([0, 0, 0, 0, 0], PdmCanBoardSim.Decode([1], [2], m2, true).Mv);     // a short frame is no value
        Assert.Equal(350, PdmCanBoardSim.StaleMs);
    }
}
