using domain.Common;
using domain.CustomPdm;
using domain.Devices;
using domain.Enums;
using Xunit;

namespace CustomPdm.Tests;

// Route B phase B4 with the w1 recipe (DECISIONS 2026-11-16, proven in firmware/sim s1 S7): cross-board links
// (PdmLinks). Live proof on the firmware: PdmB4LiveSimTests, PdmW1LiveSimTests.
// Numbers: outputs A1 1-8, A2 9-16, B 17-24 (B OUT5 = 21); digital inputs A1 1-7, A2 8-14, B 15-24.
public class PdmLinksTests
{
    private static PdmView NewPdm() => PdmLinkedTests.NewPdm();
    private static FwDevice Dev(PdmView v, string role) => v.Boards.Single(b => b.Role == role).Device;
    private static PdmBoard Board(PdmView v, string role) => v.Boards.Single(b => b.Role == role);
    private static int Ci(FwDevice d, int s) => PdmFactoryDefaults.CanInState(d, s);
    private static int Vi(FwDevice d, int k) => PdmFactoryDefaults.VarOf(d, d.VirtualInputs[k]);
    private static int Di(FwDevice d, int i) => PdmFactoryDefaults.VarOf(d, d.DigitalInputs[i]);

    internal static List<string> Raw(FwDevice d) =>
        d.Params.Select(p => $"{p.Name}={Convert.ToHexString(ParamCodec.ToFrame(MessageCommand.Write, p, 0).Payload, 4, 4)}").ToList();

    // a CAN input set by hand
    private static void ByHand(FwDevice d, int s, int id = 0x123) => (d.CanInputs[s].Enabled, d.CanInputs[s].Id) = (true, id);

    internal static string Text(PdmView v) => string.Join("; ", PdmLinks.Links(v).Select(l =>
        $"{l.In.Number}->{l.Out.Number} {l.Loss}{(l.Critical ? " critical" : "")}{(l.Cond != 0 ? $" if {l.Cond}" : "")}{(l.OldRecipe ? " old" : "")} {l.Slot} {l.Virt}"));

    // The old B4 "on" recipe (before w1), as boards written by it hold it: slot Equal 0 with the time-out on and a
    // virtual input "NOT slot OR false" as the output trigger
    internal static void OldOn(PdmView v, int input, int output, int slot, int virt)
    {
        var i = v.Inputs.Single(r => r.Number == input);
        var o = v.Outputs.Single(r => r.Number == output);
        var d = o.Device;
        var c = d.CanInputs[slot];
        (c.Enabled, c.TimeoutEnabled, c.Timeout, c.Id, c.StartBit, c.BitLength, c.Operator, c.Operand) =
            (true, true, 1000, PdmFactoryDefaults.BaseFor(i.Board) + 0x27, i.BoardInput - 1, 1, Operator.Equal, 0.0);
        var vi = d.VirtualInputs[virt];
        (vi.Enabled, vi.Not0, vi.Var0, vi.Cond0) = (true, true, Ci(d, slot), Conditional.Or);
        o.Output.Input = Vi(d, virt);
    }

    [Fact]
    public void StatusMsgLayoutMatchesFirmware()
    {
        // TxMsg37: base + CYCLIC_TX_OFFSET + 37, bit i of bytes 0-1 = digital input i (both boards, same file)
        foreach (var b in new[] { "custompdm_a", "custompdm_b" })
        {
            var src = File.ReadAllText(Path.Combine(DbcExportTests.RepoRoot(), "firmware", "boards", b, "msg.cpp"));
            var msg37 = src[src.IndexOf("CANTxMsg TxMsg37()", StringComparison.Ordinal)..];
            Assert.Contains("nBaseId + CYCLIC_TX_OFFSET + 37", msg37);
            Assert.Contains("nDi |= (GetDigInputVal(i) ? 1 : 0) << i;", msg37);
            Assert.Contains("stMsg.frame.data16[0] = nDi;", msg37);
            Assert.Contains("stMsg.bSend = !bFirstRound; // then always sent", msg37); // w1: every round but the first (built before inputs are read)
        }
        Assert.Equal(0x27, PdmLinks.StatusOffset);
        Assert.Equal(PdmLinkLoss.Off, PdmLinks.DefaultLoss); // u3c
        Assert.Equal(1000, PdmLinks.TimeoutMs);              // D3a
    }

    [Fact]
    public void CrossBoardLinkIsOneSlotOnTheTargetBoardOnly()
    {
        var v = NewPdm();
        var before = v.Boards.ToDictionary(b => b.Role, b => Raw(b.Device));
        Assert.Null(PdmLinks.Add(v, 1, 21)); // A1 IN1 -> B OUT5
        var b = Dev(v, "B");
        var c = b.CanInputs[0];
        Assert.Equal((true, true, 1000, 0x527, 0, 1), (c.Enabled, c.TimeoutEnabled, c.Timeout, c.Id, c.StartBit, c.BitLength));
        Assert.Equal((1.0, 0.0, ByteOrder.LittleEndian, false, Operator.Equal, 1.0, InputMode.Momentary), (c.Factor, c.Offset, c.ByteOrder, c.Signed, c.Operator, c.Operand, c.Mode));
        Assert.Equal(Ci(b, 0), b.Outputs[4].Input);
        Assert.Equal(before["A1"], Raw(Dev(v, "A1"))); // nothing on the source board
        Assert.Equal(before["A2"], Raw(Dev(v, "A2")));
        var changed = before["B"].Zip(Raw(b)).Where(p => p.First != p.Second).Select(p => p.First.Split('=')[0]).ToList();
        Assert.All(changed, n => Assert.True(n.StartsWith("canInput[1].") || n == "output[5].input", n)); // 'off' needs no ALIVE / SEEN / LOST
        Assert.Contains("output[5].input", changed);
        Assert.Empty(PdmLinks.Shared(v));

        var link = Assert.Single(PdmLinks.Links(v));
        Assert.Equal((21, 1, PdmLinkLoss.Off, 0, (int?)null), (link.Out.Number, link.In.Number, link.Loss!.Value, link.Slot!.Value, link.Virt));
        Assert.Equal("B CAN input 1", link.SlotText);
    }

    // w1: on = LOST OR L, LOST = SEEN AND NOT ALIVE (s1 S7 recipe, field by field)
    [Fact]
    public void OnLinkUsesTheW1Recipe()
    {
        var v = NewPdm();
        var before = v.Boards.ToDictionary(x => x.Role, x => Raw(x.Device));
        Assert.Null(PdmLinks.Add(v, 1, 21, PdmLinkLoss.On)); // A1 IN1 -> B OUT5
        var b = Dev(v, "B");
        foreach (var (c, timeout) in new[] { (b.CanInputs[0], true), (b.CanInputs[1], false) }) // ALIVE, SEEN
        {
            Assert.Equal((true, timeout, 1000, 0x527, 0, 1, false), (c.Enabled, c.TimeoutEnabled, c.Timeout, c.Id, c.StartBit, c.BitLength, c.Ide));
            Assert.Equal((1.0, 0.0, ByteOrder.LittleEndian, false, Operator.GreaterThanOrEqual, 0.0, InputMode.Momentary, 0),
                (c.Factor, c.Offset, c.ByteOrder, c.Signed, c.Operator, c.Operand, c.Mode, c.Bus));
        }
        var l = b.CanInputs[2];
        Assert.Equal((true, true, 1000, 0x527, 0, 1, Operator.Equal, 1.0), (l.Enabled, l.TimeoutEnabled, l.Timeout, l.Id, l.StartBit, l.BitLength, l.Operator, l.Operand));
        var lost = b.VirtualInputs[0];
        Assert.Equal((true, false, Ci(b, 1), Conditional.And, true, Ci(b, 0), false, 0, InputMode.Momentary),
            (lost.Enabled, lost.Not0, lost.Var0, lost.Cond0, lost.Not1, lost.Var1, lost.Not2, lost.Var2, lost.Mode));
        var on = b.VirtualInputs[1];
        Assert.Equal((true, false, Vi(b, 0), Conditional.Or, false, Ci(b, 2), false, 0, InputMode.Momentary),
            (on.Enabled, on.Not0, on.Var0, on.Cond0, on.Not1, on.Var1, on.Not2, on.Var2, on.Mode));
        Assert.Equal(Vi(b, 1), b.Outputs[4].Input);
        Assert.Equal(before["A1"], Raw(Dev(v, "A1")));
        Assert.Equal(before["A2"], Raw(Dev(v, "A2")));

        var link = Assert.Single(PdmLinks.Links(v));
        Assert.Equal((PdmLinkLoss.On, 2, 1, false, false), (link.Loss!.Value, link.Slot!.Value, link.Virt!.Value, link.Critical, link.OldRecipe));
        Assert.Equal("B CAN input 3 + virtual input 2", link.SlotText);
        Assert.Equal("on 1 s after the message stops; off until the first frame", link.LossText);
        var sh = Assert.Single(PdmLinks.Shared(v));
        Assert.Equal(("B", "A1", 0, 1, 0), (sh.Board.Role, sh.Source.Role, sh.Alive, sh.Seen, sh.Lost));
        Assert.Same(sh.Board, link.Shared!.Board);
    }

    // condition = (LOST AND C) OR L; critical = NOT ALIVE in place of LOST
    [Fact]
    public void ConditionAndCriticalForms()
    {
        var v = NewPdm();
        var b = Dev(v, "B");
        var ign = Di(b, 0); // B IN1 (input 15)
        Assert.Null(PdmLinks.Add(v, 1, 17, PdmLinkLoss.Condition, cond: ign));                 // shared 0, 1 / VI 0; L 2 / VI 1
        Assert.Null(PdmLinks.Add(v, 2, 18, PdmLinkLoss.On, critical: true));                   // L 3 / VI 2
        Assert.Null(PdmLinks.Add(v, 3, 19, PdmLinkLoss.Condition, critical: true, cond: ign)); // L 4 / VI 3
        var c = b.VirtualInputs[1];
        Assert.Equal((true, false, Vi(b, 0), Conditional.And, false, ign, Conditional.Or, false, Ci(b, 2)),
            (c.Enabled, c.Not0, c.Var0, c.Cond0, c.Not1, c.Var1, c.Cond1, c.Not2, c.Var2));
        var oc = b.VirtualInputs[2];
        Assert.Equal((true, true, Ci(b, 0), Conditional.Or, false, Ci(b, 3), false, 0), (oc.Enabled, oc.Not0, oc.Var0, oc.Cond0, oc.Not1, oc.Var1, oc.Not2, oc.Var2));
        var cc = b.VirtualInputs[3];
        Assert.Equal((true, true, Ci(b, 0), Conditional.And, false, ign, Conditional.Or, false, Ci(b, 4)),
            (cc.Enabled, cc.Not0, cc.Var0, cc.Cond0, cc.Not1, cc.Var1, cc.Cond1, cc.Not2, cc.Var2));
        Assert.Equal([Vi(b, 1), Vi(b, 2), Vi(b, 3)], b.Outputs.Take(3).Select(o => o.Input));
        Assert.Equal($"1->17 Condition if {ign} 2 1; 2->18 On critical 3 2; 3->19 Condition critical if {ign} 4 3", Text(v));
        var l17 = PdmLinks.Links(v)[0];
        Assert.StartsWith("B IN1 (input 15)", l17.CondText);
        Assert.StartsWith("follows B IN1 (input 15)", l17.LossText);
        Assert.EndsWith("; critical: acts from power-up", PdmLinks.Links(v)[1].LossText);
        Assert.Single(PdmLinks.Shared(v)); // one ALIVE / SEEN / LOST for all three (source A1)
    }

    [Fact]
    public void CriticalOnlyForOnAndConditionAndConditionNeedsAPick()
    {
        var v = NewPdm();
        var before = Raw(Dev(v, "B"));
        const string crit = "Critical changes 'on' and 'condition' only: with 'off' or 'hold' the output is off before the first frame anyway.";
        Assert.Equal(crit, PdmLinks.Add(v, 1, 21, PdmLinkLoss.Hold, critical: true));
        Assert.Equal(crit, PdmLinks.Add(v, 1, 21, PdmLinkLoss.Off, critical: true));
        Assert.Equal("Pick the condition for output 21: one of B's inputs or conditions.", PdmLinks.Add(v, 1, 21, PdmLinkLoss.Condition));
        Assert.Equal("Pick the condition for output 21: one of B's inputs or conditions.", PdmLinks.Add(v, 1, 21, PdmLinkLoss.Condition, cond: 9999));
        Assert.Equal(before, Raw(Dev(v, "B")));
        // same board: no CAN message, the mode does not matter
        Assert.Null(PdmLinks.Add(v, 15, 22, PdmLinkLoss.Hold, critical: true));
        Assert.Equal("15->22   ", Text(v));
    }

    [Fact]
    public void CondChoicesAreTheOutputBoardsInputsAndConditions()
    {
        var v = NewPdm();
        var b = Dev(v, "B");
        var ch = PdmLinks.CondChoices(v, 21);
        Assert.Equal(10 + b.Conditions.Count, ch.Count);
        Assert.Equal(Di(b, 0), ch[0].Var);
        Assert.StartsWith("B IN1 (input 15) ", ch[0].Text);
        Assert.StartsWith("B IN10 (input 24) ", ch[9].Text);
        Assert.Equal(PdmFactoryDefaults.VarOf(b, b.Conditions[0]), ch[10].Var);
        Assert.StartsWith("B condition 1: ", ch[10].Text);
        Assert.Empty(PdmLinks.CondChoices(v, 99));
        var a1 = PdmLinks.CondChoices(v, 1);
        Assert.StartsWith("A1 IN7 (input 7) ", a1[6].Text);
    }

    // ALIVE / SEEN / LOST: one set per source board on each output board, only for on / condition links, freed with
    // the last of them
    [Fact]
    public void SharedSlotsArePerSourceBoardAndFreedWithTheLastLink()
    {
        var v = NewPdm();
        var b = Dev(v, "B");
        var fresh = Raw(b);
        Assert.Null(PdmLinks.Add(v, 1, 17));                                                     // off: slot 0, nothing shared
        Assert.Empty(PdmLinks.Shared(v));
        Assert.Null(PdmLinks.Add(v, 2, 18, PdmLinkLoss.On));                                     // A1 shared 1, 2 / VI 0; L 3 / VI 1
        Assert.Null(PdmLinks.Add(v, 3, 19, PdmLinkLoss.Condition, cond: Di(b, 0)));              // L 4 / VI 2
        Assert.Null(PdmLinks.Add(v, 8, 20, PdmLinkLoss.On));                                     // A2 IN1: A2 shared 5, 6 / VI 3; L 7 / VI 4
        Assert.Equal(["B A1 1 2 0", "B A2 5 6 3"], PdmLinks.Shared(v).Select(s => $"{s.Board.Role} {s.Source.Role} {s.Alive} {s.Seen} {s.Lost}"));
        var u = PdmLinks.Slots(v).Single(s => s.Board == "B");
        Assert.Equal("B: CAN inputs 8 of 32 used (4 by links, 4 shared ALIVE / SEEN), 24 free; virtual inputs 7 of 16 used (3 by links, 2 shared LOST), 9 free", u.Summary);
        Assert.Equal("shared: A1 alive (its message 37 heard in the last 1 s), for 2 on / condition link(s)", u.CanInputs[1].UsedBy);
        Assert.Equal("shared: A1 seen (a message 37 heard since power-up), for 2 on / condition link(s)", u.CanInputs[2].UsedBy);
        Assert.Equal("shared: A2 lost (seen AND NOT alive), for 1 on / condition link(s)", u.VirtualInputs[3].UsedBy);
        Assert.Equal("load-shed example, reserved", u.VirtualInputs[14].UsedBy);
        Assert.StartsWith("link: A1 IN2 (input 2) -> OUT2 (output 18), on 1 s", u.VirtualInputs[1].UsedBy);
        Assert.True(u.CanInputs[1].Shared && u.CanInputs[1].OurLink && !u.CanInputs[3].Shared);

        Assert.Null(PdmLinks.Remove(v, 18));
        Assert.Equal(2, PdmLinks.Shared(v).Count);                // 19 still uses A1's
        Assert.Null(PdmLinks.Remove(v, 19));
        Assert.Equal(["A2"], PdmLinks.Shared(v).Select(s => s.Source.Role)); // A1's freed although the off link from A1 stays
        Assert.True(PdmLinks.IsFreeSlot(Board(v, "B"), 1) && PdmLinks.IsFreeSlot(Board(v, "B"), 2) && PdmLinks.IsFreeVirt(Board(v, "B"), 0));
        Assert.Equal("1->17 Off 0 ; 8->20 On 7 4", Text(v));
        Assert.Null(PdmLinks.Remove(v, 20));
        Assert.Null(PdmLinks.Remove(v, 17));
        Assert.Empty(PdmLinks.Shared(v));
        Assert.Equal(fresh, Raw(b)); // everything back to fresh-board values
        Assert.Equal("canInput2", b.CanInputs[1].Name);
        Assert.Equal("virtualInput1", b.VirtualInputs[0].Name);
    }

    // LOST must run before every non-critical link virtual input that uses it (else a 2.2 ms drop at the time-out, S7)
    [Fact]
    public void LostRunsBeforeEveryNonCriticalLinkVirtualInput()
    {
        var v = NewPdm();
        var b = Dev(v, "B");
        b.VirtualInputs[0].Enabled = true; // set by hand
        b.VirtualInputs[1].Enabled = true;
        Assert.Null(PdmLinks.Add(v, 1, 17, PdmLinkLoss.On));     // LOST 2, link 3
        b.VirtualInputs[0].Enabled = false;                      // freed by hand: below LOST
        Assert.Null(PdmLinks.Add(v, 2, 18, PdmLinkLoss.On));     // 4, not 0
        Assert.Null(PdmLinks.Add(v, 3, 19, PdmLinkLoss.On, critical: true)); // NOT ALIVE: no order rule -> 0
        Assert.Equal([3, 4, 0], PdmLinks.Links(v).Select(l => l.Virt!.Value));
        Assert.Equal(2, PdmLinks.Shared(v).Single().Lost);
        Assert.All(PdmLinks.Links(v), l => Assert.DoesNotContain(PdmLinks.Warnings(l), w => w.Contains("runs before")));
        for (var k = 5; k < 14; k++) b.VirtualInputs[k].Enabled = true;
        b.VirtualInputs[1].Enabled = false;                      // the only free one is below LOST
        var before = Raw(b);
        Assert.Equal("B has no free virtual input after the shared 'A1 lost' (virtual input 3), which a non-critical 'on' link must run after: " +
                     "free one above it, mark the output critical, or choose 'off' / 'hold'.", PdmLinks.Add(v, 4, 20, PdmLinkLoss.On));
        Assert.Equal(before, Raw(b)); // nothing half made
        Assert.Null(PdmLinks.Add(v, 4, 20, PdmLinkLoss.On, critical: true));
        Assert.Equal(1, PdmLinks.LinkOf(v, v.Outputs.Single(o => o.Number == 20))!.Virt);

        // a link virtual input below LOST (made by hand / another tool) is still ours, with a warning
        var v2 = NewPdm();
        var b2 = Dev(v2, "B");
        Assert.Null(PdmLinks.Add(v2, 1, 17, PdmLinkLoss.On)); // LOST 0, link 1
        var (vi0, vi1) = (b2.VirtualInputs[0], b2.VirtualInputs[1]);
        var (sv, av, lv) = (vi0.Var0, vi0.Var1, vi1.Var1);
        (vi1.Not0, vi1.Var0, vi1.Cond0, vi1.Not1, vi1.Var1) = (false, sv, Conditional.And, true, av);        // now LOST
        (vi0.Not0, vi0.Var0, vi0.Cond0, vi0.Not1, vi0.Var1) = (false, Vi(b2, 1), Conditional.Or, false, lv); // now LOST OR L
        b2.Outputs[0].Input = Vi(b2, 0);
        var l = Assert.Single(PdmLinks.Links(v2));
        Assert.Equal((0, 1), (l.Virt!.Value, l.Shared!.Lost));
        Assert.Contains("virtual input 1 runs before the shared 'A1 lost' (virtual input 2): a short drop (about 2 ms) at the time-out", PdmLinks.Warnings(l));
    }

    [Fact]
    public void LinkIsReadBackFromBoardParamsAlone()
    {
        var v = NewPdm();
        var a2 = Dev(v, "A2");
        Assert.Null(PdmLinks.Add(v, 1, 21));
        Assert.Null(PdmLinks.Add(v, 24, 3, PdmLinkLoss.Hold)); // B IN10 (bit 9, byte 1) -> A1 OUT3
        Assert.Null(PdmLinks.Add(v, 9, 12, PdmLinkLoss.On));   // A2 IN2 -> A2 OUT4: same board
        Assert.Null(PdmLinks.Add(v, 15, 13, PdmLinkLoss.On));  // B IN1 -> A2 OUT5
        Assert.Null(PdmLinks.Add(v, 16, 14, PdmLinkLoss.On, critical: true));
        Assert.Null(PdmLinks.Add(v, 17, 15, PdmLinkLoss.Condition, cond: Di(a2, 0)));
        Assert.Null(PdmLinks.Add(v, 18, 16, PdmLinkLoss.Condition, critical: true, cond: PdmFactoryDefaults.VarOf(a2, a2.Conditions[0])));
        OldOn(v, 2, 22, 5, 5); // an old B4 'on' link on B
        // a fresh PC (no names, no project file) that only got the param values, as after Read All
        var fresh = v.Boards.Select(b =>
        {
            var d = StockTests.MakeDevice(b.Device.DeviceTypeId, b.Device.BaseId);
            foreach (var (to, from) in d.Params.Zip(b.Device.Params)) to.SetValue(from.GetValue());
            return d;
        }).ToList();
        var v2 = PdmView.Build(fresh);
        Assert.Equal($"24->3 Hold 0 ; 9->12   ; 15->13 On 2 1; 16->14 On critical 3 2; 17->15 Condition if {Di(a2, 0)} 4 3; " +
                     $"18->16 Condition critical if {PdmFactoryDefaults.VarOf(a2, a2.Conditions[0])} 5 4; 1->21 Off 0 ; 2->22 On old 5 5", Text(v2));
        Assert.Equal(Text(v), Text(v2));
        Assert.Equal(9, Dev(v2, "A1").CanInputs[0].StartBit);
        Assert.Equal(0x5A7, Dev(v2, "A1").CanInputs[0].Id);
        Assert.Equal(["A2 B 0 1 0"], PdmLinks.Shared(v2).Select(s => $"{s.Board.Role} {s.Source.Role} {s.Alive} {s.Seen} {s.Lost}"));
    }

    [Fact]
    public void SameBoardLinkUsesTheInputDirectly()
    {
        var v = NewPdm();
        Assert.Null(PdmLinks.Add(v, 2, 1)); // A1 IN2 -> A1 OUT1
        var a1 = Dev(v, "A1");
        Assert.Equal(Di(a1, 1), a1.Outputs[0].Input);
        Assert.DoesNotContain(a1.CanInputs, c => c.Enabled);
        var link = Assert.Single(PdmLinks.Links(v));
        Assert.False(link.CrossBoard);
        Assert.Null(link.Loss);
        Assert.Equal("A same-board link has no CAN message to lose.", PdmLinks.SetMode(v, 1, PdmLinkLoss.On));
        Assert.Null(PdmLinks.Remove(v, 1));
        Assert.Equal(0, a1.Outputs[0].Input);
    }

    // per output: the loss mode changes in place, what is no longer needed is freed
    [Fact]
    public void ModeChangesKeepTheLinkAndFreeWhatIsNoLongerNeeded()
    {
        var v = NewPdm();
        var b = Dev(v, "B");
        var ign = Di(b, 0);
        Assert.Null(PdmLinks.Add(v, 1, 21, PdmLinkLoss.Hold));
        Assert.Equal((false, 1.0), (b.CanInputs[0].TimeoutEnabled, b.CanInputs[0].Operand));
        Assert.Equal(Ci(b, 0), b.Outputs[4].Input);
        Assert.Null(PdmLinks.SetMode(v, 21, PdmLinkLoss.On));
        Assert.Equal("1->21 On 2 1", Text(v));
        Assert.Null(PdmLinks.SetMode(v, 21, PdmLinkLoss.Condition, cond: ign));
        Assert.Equal($"1->21 Condition if {ign} 2 1", Text(v)); // the shared ones kept
        Assert.Null(PdmLinks.SetMode(v, 21, PdmLinkLoss.On, critical: true));
        Assert.Equal("1->21 On critical 2 1", Text(v));
        Assert.Null(PdmLinks.SetInput(v, 21, 3));               // another source input, the mode kept
        Assert.Equal("3->21 On critical 2 1", Text(v));
        Assert.Null(PdmLinks.SetInput(v, 21, 15));              // B IN1: same board now
        Assert.Equal("15->21   ", Text(v));
        Assert.Empty(PdmLinks.Shared(v));
        Assert.Null(PdmLinks.SetInput(v, 21, 1));               // back across boards: the default mode
        Assert.Equal("1->21 Off 0 ", Text(v));
        Assert.Null(PdmLinks.SetMode(v, 21, PdmLinkLoss.On));
        Assert.Null(PdmLinks.SetMode(v, 21, PdmLinkLoss.Off));
        var v2 = NewPdm();
        Assert.Null(PdmLinks.Add(v2, 1, 21));
        Assert.Equal(Raw(Dev(v2, "B")), Raw(b));                // the same params as a plain 'off' link
        Assert.Equal("Output 22 has no link.", PdmLinks.SetMode(v, 22, PdmLinkLoss.On));
    }

    [Fact]
    public void OnLinkNeedsFreeVirtualInputsAndSkipsTheReservedOnes()
    {
        var v = NewPdm();
        var a2 = Board(v, "A2");
        Assert.Equal([11, 12, 13, 14, 15], Enumerable.Range(0, 16).Where(k => PdmLinks.IsReservedVirt(a2, k)));
        Assert.Equal([14, 15], Enumerable.Range(0, 16).Where(k => PdmLinks.IsReservedVirt(Board(v, "B"), k)));
        for (var k = 0; k < 10; k++) a2.Device.VirtualInputs[k].Enabled = true; // 10 (1-based 11) free
        var before = Raw(a2.Device);
        Assert.Equal("A2 has too few free virtual inputs: this 'on' link needs 2 (the shared 'A1 lost' and its own), 1 free. Choose 'off' or 'hold'.",
            PdmLinks.Add(v, 1, 9, PdmLinkLoss.On));
        Assert.Equal(before, Raw(a2.Device)); // nothing half made
        Assert.Null(PdmLinks.Add(v, 1, 9, PdmLinkLoss.Off));
        Assert.Equal("A2 has too few free virtual inputs: this 'condition' link needs 2 (the shared 'A1 lost' and its own), 1 free. Choose 'off' or 'hold'.",
            PdmLinks.SetMode(v, 9, PdmLinkLoss.Condition, cond: Di(a2.Device, 0)));
        Assert.Equal("1->9 Off 0 ", Text(v)); // put back as it was
        a2.Device.VirtualInputs[9].Enabled = false;
        Assert.Null(PdmLinks.SetMode(v, 9, PdmLinkLoss.On));
        Assert.Equal("1->9 On 2 10", Text(v));
        Assert.Equal(9, PdmLinks.Shared(v).Single().Lost);
        Assert.Equal("A2 has too few free virtual inputs: this 'on' link needs 1, 0 free. Choose 'off' or 'hold'.", PdmLinks.Add(v, 2, 11, PdmLinkLoss.On));
    }

    [Fact]
    public void RemoveFreesTheSlotAndClearsTheTrigger()
    {
        var v = NewPdm();
        var b = Dev(v, "B");
        var fresh = Raw(b);
        Assert.Null(PdmLinks.Add(v, 1, 21, PdmLinkLoss.On));
        Assert.Null(PdmLinks.Add(v, 2, 22));
        Assert.Null(PdmLinks.Remove(v, 21));
        Assert.Null(PdmLinks.Remove(v, 22));
        Assert.Equal(fresh, Raw(b)); // slots, virtual inputs and output triggers as on a fresh board
        Assert.Empty(PdmLinks.Links(v));
        Assert.Equal("Output 21 has no link.", PdmLinks.Remove(v, 21));
        Assert.Equal("canInput1", b.CanInputs[0].Name);
    }

    [Fact]
    public void LowestFreeSlotAndHandSetSlotsAreNeverTouched()
    {
        var v = NewPdm();
        var b = Dev(v, "B");
        ByHand(b, 0);
        b.CanInputs[1].Id = 0x200;                 // disabled but with an ID: not free either
        b.VirtualInputs[0].Enabled = true;         // a virtual input set by hand
        List<string> Hand() => Raw(b).Where(r => r.StartsWith("canInput[1]") || r.StartsWith("canInput[2]") || r.StartsWith("virtualInput[1]")).ToList();
        var hand = Hand();
        Assert.Null(PdmLinks.Add(v, 1, 21));
        Assert.Null(PdmLinks.Add(v, 2, 22, PdmLinkLoss.On));
        Assert.Equal([2, 5], PdmLinks.Links(v).Select(l => l.Slot!.Value)); // shared A1 at 3, 4
        Assert.Equal(hand, Hand());
        Assert.Null(PdmLinks.Remove(v, 21));
        Assert.Null(PdmLinks.Add(v, 3, 23));
        Assert.Equal(2, PdmLinks.LinkOf(v, v.Outputs.Single(o => o.Number == 23))!.Slot); // freed slot reused
        var slots = PdmLinks.Slots(v).Single(s => s.Board == "B");
        Assert.Equal("set by hand (enabled, ID 0x123): never changed here", slots.CanInputs[0].UsedBy);
        Assert.Equal("set by hand (disabled, ID 0x200): never changed here", slots.CanInputs[1].UsedBy);
        Assert.Equal("set by hand: never changed here", slots.VirtualInputs[0].UsedBy);
        Assert.StartsWith("link: A1 IN3 (input 3) -> OUT7 (output 23)", slots.CanInputs[2].UsedBy);
        Assert.Equal((26, 2, 2), (slots.FreeCanInputs, slots.LinkCanInputs, slots.SharedCanInputs));
        Assert.Equal((11, 1, 1), (slots.FreeVirtuals, slots.LinkVirtuals, slots.SharedVirtuals));
    }

    [Fact]
    public void FanSlotsAreReservedAndAFullBoardIsRefused()
    {
        var v = NewPdm();
        var a2 = Dev(v, "A2");
        List<string> FanRaw() => a2.CanInputs.Skip(24).Take(4).Concat<domain.Interfaces.IDeviceFunction>(a2.VirtualInputs.Skip(11).Take(3))
            .SelectMany(c => c.Params).Select(p => $"{p.Name}={Convert.ToHexString(ParamCodec.ToFrame(MessageCommand.Write, p, 0).Payload, 4, 4)}").ToList();
        var fan = FanRaw();
        Assert.Equal(4 * 15 + 3 * 10, fan.Count);
        for (var s = 0; s < 32; s++) if (s is < 24 or > 27 && s is not (28 or 29)) ByHand(a2, s);
        Assert.Equal("A2 has too few free CAN inputs: this link needs 3 (the shared 'A1 alive' and 'A1 seen' and its own), 2 free " +
                     "(0 used by links, the rest by the fan logic or set by hand).", PdmLinks.Add(v, 1, 9, PdmLinkLoss.On));
        Assert.Null(PdmLinks.Add(v, 1, 9)); // A1 IN1 -> A2 OUT1: off needs 1; the lowest free is 29 (1-based), never a fan slot
        Assert.Equal(28, PdmLinks.Links(v).Single().Slot);
        Assert.Null(PdmLinks.Add(v, 2, 11));
        Assert.Equal("A2 has too few free CAN inputs: this link needs 1, 0 free (2 used by links, the rest by the fan logic or set by hand).",
            PdmLinks.Add(v, 3, 12));
        Assert.Equal(fan, FanRaw());
        var slots = PdmLinks.Slots(v).Single(s => s.Board == "A2");
        Assert.All(slots.CanInputs.Skip(24).Take(4), u => Assert.Equal("fan logic (A1 / B board temperature), reserved", u.UsedBy));
        Assert.All(slots.VirtualInputs.Skip(11).Take(3), u => Assert.Equal("fan logic, reserved", u.UsedBy));
        Assert.Equal(0, slots.FreeCanInputs);
        Assert.Null(PdmLinks.Add(v, 8, 12)); // the same-board link needs no slot
    }

    [Fact]
    public void Refusals()
    {
        var v = NewPdm();
        var a1 = Dev(v, "A1");
        Assert.Equal("Output 10 (A2 OUT2) runs the fans: its trigger is the fan logic.", PdmLinks.Add(v, 1, 10));
        Assert.Equal("Output 10 (A2 OUT2) runs the fans: its trigger is the fan logic.", PdmLinks.Add(v, 1, 10, overwrite: true));
        Assert.Equal("Input 25 is not a digital input of this PDM (1-24, its board must be in the project).", PdmLinks.Add(v, 25, 1));
        Assert.Equal("Output 0 is not in this PDM (1-24, its board must be in the project).", PdmLinks.Add(v, 1, 0));
        a1.Outputs[1].PrimaryOutput = 0;
        Assert.Equal("Output 2 (A1 OUT2) is paired: it follows output 1 of A1.", PdmLinks.Add(v, 15, 2, overwrite: true));
        Assert.DoesNotContain(a1.CanInputs, c => c.Enabled);

        // a board missing from the project: its numbers are refused
        Assert.Null(PdmLinks.Add(v, 15, 4, PdmLinkLoss.On));
        var noB = PdmView.Build(v.Boards.Where(b => b.Role != "B").Select(b => b.Device));
        Assert.Equal("Output 21 is not in this PDM (1-24, its board must be in the project).", PdmLinks.Add(noB, 1, 21));
        Assert.Equal("Input 15 is not a digital input of this PDM (1-24, its board must be in the project).", PdmLinks.Add(noB, 15, 1));
        Assert.Empty(PdmLinks.Links(noB));  // A1's slots listen to B, which is not here: not shown as ours
        Assert.Empty(PdmLinks.Shared(noB));
        Assert.Equal(0, PdmLinks.RemoveUnused(noB)); // and never freed
    }

    // DECISIONS g1: an output whose trigger is set by something else is only replaced after "already assigned. Overwrite?"
    [Fact]
    public void AlreadyAssignedIsReplacedOnlyWithOverwrite()
    {
        var v = NewPdm();
        var a1 = Dev(v, "A1");
        Assert.Null(PdmLinks.Conflict(v, 3));
        a1.Outputs[2].Input = 1; // by hand
        var c = PdmLinks.Conflict(v, 3)!;
        Assert.StartsWith("Output 3 (A1 OUT3) is already assigned: its trigger was set elsewhere (", c);
        Assert.EndsWith(", variable 1).", c);
        Assert.Equal(c, PdmLinks.Add(v, 15, 3));
        Assert.Equal(1, a1.Outputs[2].Input);
        Assert.Null(PdmLinks.Add(v, 15, 3, overwrite: true));
        Assert.Equal("15->3 Off 0 ", Text(v));

        // a CAN input set by hand as the trigger: unhooked from the output, never changed itself
        ByHand(a1, 5, 0x7A0);
        a1.Outputs[3].Input = Ci(a1, 5);
        var hand = Raw(a1).Where(r => r.StartsWith("canInput[6]")).ToList();
        Assert.Null(PdmLinks.Add(v, 16, 4, PdmLinkLoss.On, overwrite: true)); // shared B 1, 2; L 3
        Assert.Equal(hand, Raw(a1).Where(r => r.StartsWith("canInput[6]")).ToList());
        Assert.Equal("15->3 Off 0 ; 16->4 On 3 1", Text(v));

        // a linked output: the old link goes (and what it used), the new one is made
        Assert.Equal("Output 4 (A1 OUT4) is already assigned: linked to input 16 (B IN2).", PdmLinks.Conflict(v, 4));
        Assert.Equal("Output 4 (A1 OUT4) is already assigned: linked to input 16 (B IN2).", PdmLinks.Add(v, 8, 4));
        Assert.Null(PdmLinks.Add(v, 8, 4, overwrite: true)); // A2 IN1, off
        Assert.Equal("15->3 Off 0 ; 8->4 Off 1 ", Text(v));
        Assert.Empty(PdmLinks.Shared(v));
        // a refused overwrite changes nothing
        var before = Raw(a1);
        Assert.Equal("Pick the condition for output 4: one of A1's inputs or conditions.", PdmLinks.Add(v, 9, 4, PdmLinkLoss.Condition, overwrite: true));
        Assert.Equal(before, Raw(a1));
    }

    // Old B4 "on" links found after Read All: shown, and converted to the w1 'on' recipe only by Upgrade
    [Fact]
    public void OldRecipeIsShownAndUpgradedOnRequest()
    {
        var v = NewPdm();
        var b = Dev(v, "B");
        OldOn(v, 1, 21, 0, 0);
        OldOn(v, 2, 22, 1, 1);
        Assert.Null(PdmLinks.Add(v, 3, 23));
        Assert.Equal("1->21 On old 0 0; 2->22 On old 1 1; 3->23 Off 2 ", Text(v));
        Assert.Equal([21, 22], PdmLinks.OldLinks(v).Select(l => l.Out.Number));
        var old = PdmLinks.Links(v)[0];
        Assert.Equal("on 1 s after the message stops (old recipe: on at power-up until the first frame)", old.LossText);
        Assert.Contains("old recipe: on at power-up until the first frame (Upgrade)", PdmLinks.Warnings(old));
        Assert.Empty(PdmLinks.Shared(v));
        Assert.Equal("B CAN input 1: link: A1 IN1 (input 1) -> OUT5 (output 21), on 1 s after the message stops (old recipe: on at power-up until the first frame)",
            $"B CAN input 1: {PdmLinks.Slots(v).Single(s => s.Board == "B").CanInputs[0].UsedBy}");

        Assert.Empty(PdmLinks.Upgrade(v));
        Assert.Empty(PdmLinks.OldLinks(v));
        Assert.Equal(["1->21 On", "2->22 On", "3->23 Off"], PdmLinks.Links(v).Select(l => $"{l.In.Number}->{l.Out.Number} {l.Loss}{(l.OldRecipe ? " old" : "")}{(l.Critical ? " critical" : "")}"));
        var sh = PdmLinks.Shared(v).Single();
        Assert.All(PdmLinks.Links(v).Where(l => l.Virt != null), l => Assert.True(l.Virt > sh.Lost));
        Assert.DoesNotContain(b.CanInputs, c => c is { Operator: Operator.Equal, Operand: 0.0, Enabled: true }); // no Equal 0 slot left
        Assert.Equal(0, PdmLinks.RemoveUnused(v));
        Assert.Empty(PdmLinks.Upgrade(v)); // nothing more to do

        // not enough room: that link is kept as it was
        var v2 = NewPdm();
        var b2 = Dev(v2, "B");
        OldOn(v2, 1, 21, 0, 0);
        for (var s = 1; s < 32; s++) ByHand(b2, s);
        var before = Raw(b2);
        Assert.Equal(["Output 21: B has too few free CAN inputs: this link needs 3 (the shared 'A1 alive' and 'A1 seen' and its own), 1 free " +
                      "(0 used by links, the rest by the fan logic or set by hand)."], PdmLinks.Upgrade(v2));
        Assert.Equal(before, Raw(b2));
        Assert.Equal("1->21 On old 0 0", Text(v2));
    }

    [Fact]
    public void ATriggerChangedByHandLeavesUnusedSlotsThatCanBeFreed()
    {
        var v = NewPdm();
        var b = Dev(v, "B");
        var fresh = Raw(b);
        Assert.Null(PdmLinks.Add(v, 1, 21));
        Assert.Null(PdmLinks.Add(v, 2, 22, PdmLinkLoss.On));
        b.Outputs[4].Input = 0; // changed on B's own page
        b.Outputs[5].Input = 0;
        Assert.Empty(PdmLinks.Links(v));
        var u = PdmLinks.Slots(v).Single(s => s.Board == "B");
        Assert.Equal("link slot for A1 IN1, no output uses it (Remove unused)", u.CanInputs[0].UsedBy);
        Assert.Equal("shared ALIVE for A1, no link uses it (Remove unused)", u.CanInputs[1].UsedBy);
        Assert.Equal("shared SEEN for A1, no link uses it (Remove unused)", u.CanInputs[2].UsedBy);
        Assert.Equal("link slot for A1 IN2, no output uses it (Remove unused)", u.CanInputs[3].UsedBy);
        Assert.Equal("shared LOST for A1, no link uses it (Remove unused)", u.VirtualInputs[0].UsedBy);
        Assert.Equal("link virtual input for A1, no output uses it (Remove unused)", u.VirtualInputs[1].UsedBy);
        Assert.True(u.CanInputs[0].Unused && !u.CanInputs[0].Free);
        ByHand(b, 5, 0x700);
        Assert.Equal(6, PdmLinks.RemoveUnused(v));
        Assert.True(b.CanInputs[5].Enabled); // a slot set by hand is not a link slot
        b.CanInputs[5].Enabled = false;
        b.CanInputs[5].Id = 0;
        Assert.Equal(fresh, Raw(b));
    }

    // an inverted slot (Equal 0) with the time-out off is not a link: it would be "on while the input is off"
    [Fact]
    public void InvertedSlotWithoutTimeoutIsNotALink()
    {
        var v = NewPdm();
        var b = Dev(v, "B");
        OldOn(v, 1, 21, 0, 0);
        b.CanInputs[0].TimeoutEnabled = false; // changed by hand
        Assert.Empty(PdmLinks.Links(v));
        Assert.Equal("set by hand (enabled, ID 0x527): never changed here", PdmLinks.Slots(v).Single(s => s.Board == "B").CanInputs[0].UsedBy);
        Assert.Equal(0, PdmLinks.RemoveUnused(v));
        // an 'on' link whose own slot lost its time-out by hand is not ours either (it would hold, not go on)
        var v2 = NewPdm();
        Assert.Null(PdmLinks.Add(v2, 1, 21, PdmLinkLoss.On));
        Dev(v2, "B").CanInputs[2].TimeoutEnabled = false;
        Assert.Empty(PdmLinks.Links(v2));
    }

    [Fact]
    public void LinkSlotsFollowABaseIdMove()
    {
        var v = NewPdm();
        Assert.Null(PdmLinks.Add(v, 1, 21));                   // A1 IN1 -> B OUT5: B slot 0
        Assert.Null(PdmLinks.Add(v, 2, 22, PdmLinkLoss.On));   // B: shared A1 1, 2; L 3
        Assert.Null(PdmLinks.Add(v, 15, 1));                   // B IN1 -> A1 OUT1
        Assert.Empty(PdmLinked.BaseIdWarnings(v, "A1", 0x400));
        var done = PdmLinked.FollowBaseId(v, "A1", 0x400);
        Assert.Contains("B CAN input 1 (link from A1 IN1) -> 0x427", done);
        Assert.Contains("B CAN input 2 (shared alive for A1) -> 0x427", done);
        Assert.Contains("B CAN input 3 (shared seen for A1) -> 0x427", done);
        Assert.Contains("B CAN input 4 (link from A1 IN2) -> 0x427", done);
        Assert.Equal(0x5A7, Dev(v, "A1").CanInputs[0].Id); // the link that listens to B stays
        Dev(v, "A1").BaseId = 0x400;
        Assert.Equal("15->1 Off 0 ; 1->21 Off 0 ; 2->22 On 3 1", Text(v));
    }

    [Fact]
    public void WarningsWhenSomethingIsOff()
    {
        var v = NewPdm();
        var b = Dev(v, "B");
        Assert.Null(PdmLinks.Add(v, 1, 21));
        Assert.Equal(["output 21 is not enabled", "input 1 is not enabled on A1"], PdmLinks.Warnings(PdmLinks.Links(v).Single()));
        b.Outputs[4].Enabled = true;
        Dev(v, "A1").DigitalInputs[0].Enabled = true;
        Assert.Empty(PdmLinks.Warnings(PdmLinks.Links(v).Single()));

        Assert.Null(PdmLinks.Add(v, 1, 22, PdmLinkLoss.Condition, cond: PdmFactoryDefaults.VarOf(b, b.Conditions[2])));
        b.Outputs[5].Enabled = true;
        var l = PdmLinks.LinkOf(v, v.Outputs.Single(o => o.Number == 22))!;
        Assert.Equal([$"the condition {l.CondText} is not enabled"], PdmLinks.Warnings(l));
        b.Conditions[2].Enabled = true;
        Assert.Empty(PdmLinks.Warnings(PdmLinks.LinkOf(v, v.Outputs.Single(o => o.Number == 22))!));
        b.CanInputs[l.Slot!.Value].Timeout = 500; // by hand
        Assert.Equal(["time-out 500 ms differs from the shared 'A1 alive' (1000 ms): the output can blip at loss"],
            PdmLinks.Warnings(PdmLinks.LinkOf(v, v.Outputs.Single(o => o.Number == 22))!));
    }
}
