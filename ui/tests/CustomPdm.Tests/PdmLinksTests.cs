using domain.Common;
using domain.CustomPdm;
using domain.Devices;
using domain.Enums;
using Xunit;

namespace CustomPdm.Tests;

// Route B phase B4 (docs/ui-route-b-plan.md): cross-board links (PdmLinks). Live proof on the firmware: PdmB4LiveSimTests.
// Numbers: outputs A1 1-8, A2 9-16, B 17-24 (B OUT5 = 21); digital inputs A1 1-7, A2 8-14, B 15-24.
public class PdmLinksTests
{
    private static PdmView NewPdm() => PdmLinkedTests.NewPdm();
    private static FwDevice Dev(PdmView v, string role) => v.Boards.Single(b => b.Role == role).Device;
    private static PdmBoard Board(PdmView v, string role) => v.Boards.Single(b => b.Role == role);

    private static List<string> Raw(FwDevice d) =>
        d.Params.Select(p => $"{p.Name}={Convert.ToHexString(ParamCodec.ToFrame(MessageCommand.Write, p, 0).Payload, 4, 4)}").ToList();

    // a CAN input set by hand
    private static void ByHand(FwDevice d, int s, int id = 0x123) => (d.CanInputs[s].Enabled, d.CanInputs[s].Id) = (true, id);

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
        Assert.Equal(PdmFactoryDefaults.CanInState(b, 0), b.Outputs[4].Input);
        Assert.Equal(before["A1"], Raw(Dev(v, "A1"))); // nothing on the source board
        Assert.Equal(before["A2"], Raw(Dev(v, "A2")));
        var changed = before["B"].Zip(Raw(b)).Where(p => p.First != p.Second).Select(p => p.First.Split('=')[0]).ToList();
        Assert.All(changed, n => Assert.True(n.StartsWith("canInput[1].") || n == "output[5].input", n));
        Assert.Contains("output[5].input", changed);

        var link = Assert.Single(PdmLinks.Links(v));
        Assert.Equal((21, 1, PdmLinkLoss.Off, 0, (int?)null), (link.Out.Number, link.In.Number, link.Loss!.Value, link.Slot!.Value, link.Virt));
        Assert.Equal("B CAN input 1", link.SlotText);
    }

    [Fact]
    public void LinkIsReadBackFromBoardParamsAlone()
    {
        var v = NewPdm();
        Assert.Null(PdmLinks.Add(v, 1, 21));
        Assert.Null(PdmLinks.Add(v, 24, 3, PdmLinkLoss.Hold)); // B IN10 (bit 9, byte 1) -> A1 OUT3
        Assert.Null(PdmLinks.Add(v, 9, 12, PdmLinkLoss.On));   // A2 IN2 -> A2 OUT4: same board
        Assert.Null(PdmLinks.Add(v, 15, 13, PdmLinkLoss.On));  // B IN1 -> A2 OUT5
        // a fresh PC (no names, no project file) that only got the param values, as after Read All
        var fresh = v.Boards.Select(b =>
        {
            var d = StockTests.MakeDevice(b.Device.DeviceTypeId, b.Device.BaseId);
            foreach (var (to, from) in d.Params.Zip(b.Device.Params)) to.SetValue(from.GetValue());
            return d;
        }).ToList();
        var v2 = PdmView.Build(fresh);
        string Text(PdmView x) => string.Join("; ", PdmLinks.Links(x).Select(l => $"{l.In.Number}->{l.Out.Number} {l.Loss} {l.Slot} {l.Virt}"));
        Assert.Equal("24->3 Hold 0 ; 9->12   ; 15->13 On 0 0; 1->21 Off 0 ", Text(v2));
        Assert.Equal(Text(v), Text(v2));
        Assert.Equal(9, Dev(v2, "A1").CanInputs[0].StartBit);
        Assert.Equal(0x5A7, Dev(v2, "A1").CanInputs[0].Id);
    }

    [Fact]
    public void SameBoardLinkUsesTheInputDirectly()
    {
        var v = NewPdm();
        Assert.Null(PdmLinks.Add(v, 2, 1)); // A1 IN2 -> A1 OUT1
        var a1 = Dev(v, "A1");
        Assert.Equal(PdmFactoryDefaults.VarOf(a1, a1.DigitalInputs[1]), a1.Outputs[0].Input);
        Assert.DoesNotContain(a1.CanInputs, c => c.Enabled);
        var link = Assert.Single(PdmLinks.Links(v));
        Assert.False(link.CrossBoard);
        Assert.Null(link.Loss);
        Assert.Equal("A same-board link has no CAN message to lose.", PdmLinks.SetLoss(v, 1, PdmLinkLoss.On));
        Assert.Null(PdmLinks.Remove(v, 1));
        Assert.Equal(0, a1.Outputs[0].Input);
    }

    [Fact]
    public void LossOptionsMapToStockSettings()
    {
        var v = NewPdm();
        var b = Dev(v, "B");
        Assert.Null(PdmLinks.Add(v, 1, 21, PdmLinkLoss.Hold));
        Assert.Equal((false, 1.0), (b.CanInputs[0].TimeoutEnabled, b.CanInputs[0].Operand));
        Assert.Equal(PdmFactoryDefaults.CanInState(b, 0), b.Outputs[4].Input);

        Assert.Null(PdmLinks.SetLoss(v, 21, PdmLinkLoss.On));
        var c = b.CanInputs[0];
        Assert.Equal((true, true, Operator.Equal, 0.0), (c.Enabled, c.TimeoutEnabled, c.Operator, c.Operand));
        var vi = b.VirtualInputs[0];
        Assert.Equal((true, true, PdmFactoryDefaults.CanInState(b, 0), Conditional.Or, false, 0, 0), (vi.Enabled, vi.Not0, vi.Var0, vi.Cond0, vi.Not1, vi.Var1, vi.Var2));
        Assert.Equal(PdmFactoryDefaults.VarOf(b, vi), b.Outputs[4].Input);
        Assert.Equal(PdmLinkLoss.On, PdmLinks.Links(v).Single().Loss);

        Assert.Null(PdmLinks.SetLoss(v, 21, PdmLinkLoss.Off));
        Assert.Equal((true, 1.0), (b.CanInputs[0].TimeoutEnabled, b.CanInputs[0].Operand));
        Assert.False(b.VirtualInputs[0].Enabled);
        Assert.Equal(0, b.VirtualInputs[0].Var0);
        Assert.Equal(PdmLinkLoss.Off, PdmLinks.Links(v).Single().Loss);
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
        Assert.Equal(fresh, Raw(b)); // slot, virtual input and output trigger as on a fresh board
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
        var hand = (Raw(b).Where(r => r.StartsWith("canInput[1]") || r.StartsWith("canInput[2]")).ToList());
        Assert.Null(PdmLinks.Add(v, 1, 21));
        Assert.Null(PdmLinks.Add(v, 2, 22));
        Assert.Equal([2, 3], PdmLinks.Links(v).Select(l => l.Slot!.Value));
        Assert.Equal(hand, Raw(b).Where(r => r.StartsWith("canInput[1]") || r.StartsWith("canInput[2]")).ToList());
        Assert.Null(PdmLinks.Remove(v, 21));
        Assert.Null(PdmLinks.Add(v, 3, 23));
        Assert.Equal(2, PdmLinks.LinkOf(v, v.Outputs.Single(o => o.Number == 23))!.Slot); // freed slot reused
        var slots = PdmLinks.Slots(v).Single(s => s.Board == "B");
        Assert.Equal("set by hand (enabled, ID 0x123): never changed here", slots.CanInputs[0].UsedBy);
        Assert.Equal("set by hand (disabled, ID 0x200): never changed here", slots.CanInputs[1].UsedBy);
        Assert.StartsWith("link: A1 IN3 (input 3) -> OUT7 (output 23)", slots.CanInputs[2].UsedBy);
        Assert.Equal((28, 2), (slots.FreeCanInputs, slots.LinkCanInputs));
    }

    [Fact]
    public void FanSlotsAreReservedAndAFullBoardIsRefused()
    {
        var v = NewPdm();
        var a2 = Dev(v, "A2");
        List<string> FanRaw() => a2.CanInputs.Skip(24).Take(4).SelectMany(c => c.Params)
            .Select(p => $"{p.Name}={Convert.ToHexString(ParamCodec.ToFrame(MessageCommand.Write, p, 0).Payload, 4, 4)}").ToList();
        var fan = FanRaw();
        Assert.Equal(4 * 15, fan.Count);
        for (var s = 0; s < 32; s++) if (s is < 24 or > 27 && s != 30) ByHand(a2, s);
        Assert.Null(PdmLinks.Add(v, 1, 9)); // A1 IN1 -> A2 OUT1: the only free slot is 31 (1-based), never a fan slot
        Assert.Equal(30, PdmLinks.Links(v).Single().Slot);
        Assert.Equal("A2 has no free CAN input: all 32 are used (1 by links, the rest by the fan logic or set by hand).", PdmLinks.Add(v, 2, 11));
        Assert.Equal(fan, FanRaw());
        var slots = PdmLinks.Slots(v).Single(s => s.Board == "A2");
        Assert.All(slots.CanInputs.Skip(24).Take(4), u => Assert.Equal("fan logic (A1 / B board temperature), reserved", u.UsedBy));
        Assert.Equal(0, slots.FreeCanInputs);
        // the same-board link needs no slot
        Assert.Null(PdmLinks.Add(v, 8, 11));
    }

    [Fact]
    public void OnLinkNeedsAFreeVirtualInputAndSkipsTheReservedOnes()
    {
        var v = NewPdm();
        var a2 = Board(v, "A2");
        Assert.Equal([11, 12, 13, 14, 15], Enumerable.Range(0, 16).Where(k => PdmLinks.IsReservedVirt(a2, k)));
        Assert.Equal([14, 15], Enumerable.Range(0, 16).Where(k => PdmLinks.IsReservedVirt(Board(v, "B"), k)));
        for (var k = 0; k < 11; k++) a2.Device.VirtualInputs[k].Enabled = true;
        Assert.Equal("A2 has no free virtual input, which an 'on' link needs: choose 'off' or 'hold'.", PdmLinks.Add(v, 1, 9, PdmLinkLoss.On));
        Assert.DoesNotContain(a2.Device.CanInputs.Take(24), c => c.Enabled); // nothing half made
        Assert.Null(PdmLinks.Add(v, 1, 9, PdmLinkLoss.Off));
        Assert.Equal("A2 has no free virtual input, which an 'on' link needs: choose 'off' or 'hold'.", PdmLinks.SetLoss(v, 9, PdmLinkLoss.On));
        Assert.Equal(PdmLinkLoss.Off, PdmLinks.Links(v).Single().Loss); // put back as it was
    }

    [Fact]
    public void Refusals()
    {
        var v = NewPdm();
        var a1 = Dev(v, "A1");
        Assert.Equal("Output 10 (A2 OUT2) runs the fans: its trigger is the fan logic.", PdmLinks.Add(v, 1, 10));
        Assert.Equal("Input 25 is not a digital input of this PDM (1-24, its board must be in the project).", PdmLinks.Add(v, 25, 1));
        Assert.Equal("Output 0 is not in this PDM (1-24, its board must be in the project).", PdmLinks.Add(v, 1, 0));
        a1.Outputs[1].PrimaryOutput = 0;
        Assert.Equal("Output 2 (A1 OUT2) is paired: it follows output 1 of A1.", PdmLinks.Add(v, 15, 2));
        a1.Outputs[2].Input = 1; // ALWAYS_TRUE, by hand
        Assert.Equal("Output 3 (A1 OUT3) already has a trigger set by hand (variable 1): set it to none on A1's page first.", PdmLinks.Add(v, 15, 3));
        Assert.Null(PdmLinks.Add(v, 15, 4));
        Assert.Equal("Output 4 (A1 OUT4) is already linked to input 15: remove that link first.", PdmLinks.Add(v, 16, 4));
        Assert.Equal(1, a1.CanInputs.Count(c => c.Enabled));

        // a board missing from the project: its numbers are refused
        var noB = PdmView.Build(v.Boards.Where(b => b.Role != "B").Select(b => b.Device));
        Assert.Equal("Output 21 is not in this PDM (1-24, its board must be in the project).", PdmLinks.Add(noB, 1, 21));
        Assert.Equal("Input 15 is not a digital input of this PDM (1-24, its board must be in the project).", PdmLinks.Add(noB, 15, 1));
        Assert.DoesNotContain(PdmLinks.Links(noB), l => l.CrossBoard); // A1's slot listens to B, which is not here: not shown as ours
    }

    [Fact]
    public void ATriggerChangedByHandLeavesAnUnusedSlotThatCanBeFreed()
    {
        var v = NewPdm();
        var b = Dev(v, "B");
        Assert.Null(PdmLinks.Add(v, 1, 21));
        b.Outputs[4].Input = 0; // changed on B's own page
        Assert.Empty(PdmLinks.Links(v));
        var u = PdmLinks.Slots(v).Single(s => s.Board == "B");
        Assert.Equal("link slot for A1 IN1, no output uses it (Remove unused)", u.CanInputs[0].UsedBy);
        Assert.False(u.CanInputs[0].Free);
        ByHand(b, 5, 0x700);
        Assert.Equal(1, PdmLinks.RemoveUnused(v));
        Assert.True(PdmLinks.IsFreeSlot(Board(v, "B"), 0));
        Assert.True(b.CanInputs[5].Enabled); // a slot set by hand is not a link slot
    }

    // an inverted slot (Equal 0) with the time-out off is not a link: it would be "on while the input is off"
    [Fact]
    public void InvertedSlotWithoutTimeoutIsNotALink()
    {
        var v = NewPdm();
        var b = Dev(v, "B");
        Assert.Null(PdmLinks.Add(v, 1, 21, PdmLinkLoss.On));
        b.CanInputs[0].TimeoutEnabled = false; // changed by hand
        Assert.Empty(PdmLinks.Links(v));
        Assert.Equal("set by hand (enabled, ID 0x527): never changed here", PdmLinks.Slots(v).Single(s => s.Board == "B").CanInputs[0].UsedBy);
        Assert.Equal(0, PdmLinks.RemoveUnused(v));
    }

    [Fact]
    public void LinkSlotsFollowABaseIdMove()
    {
        var v = NewPdm();
        Assert.Null(PdmLinks.Add(v, 1, 21));  // A1 IN1 -> B OUT5
        Assert.Null(PdmLinks.Add(v, 15, 1));  // B IN1 -> A1 OUT1
        Assert.Empty(PdmLinked.BaseIdWarnings(v, "A1", 0x400));
        var done = PdmLinked.FollowBaseId(v, "A1", 0x400);
        Assert.Contains("B CAN input 1 (link from A1 IN1) -> 0x427", done);
        Assert.Equal(0x427, Dev(v, "B").CanInputs[0].Id);
        Assert.Equal(0x5A7, Dev(v, "A1").CanInputs[0].Id); // the link that listens to B stays
        Dev(v, "A1").BaseId = 0x400;
        Assert.Equal([1, 21], PdmLinks.Links(v).Select(l => l.Out.Number));
    }

    [Fact]
    public void WarningsWhenTheOutputOrInputIsOff()
    {
        var v = NewPdm();
        Assert.Null(PdmLinks.Add(v, 1, 21));
        Assert.Equal(["output 21 is not enabled", "input 1 is not enabled on A1"], PdmLinks.Warnings(PdmLinks.Links(v).Single()));
        Dev(v, "B").Outputs[4].Enabled = true;
        Dev(v, "A1").DigitalInputs[0].Enabled = true;
        Assert.Empty(PdmLinks.Warnings(PdmLinks.Links(v).Single()));
    }
}
