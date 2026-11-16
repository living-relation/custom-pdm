using domain.CustomPdm;
using domain.Devices;
using Xunit;

namespace CustomPdm.Tests;

// Route B phase B1: the combined view model behind /pdm (web/Components/CustomPdm/PdmPage.razor).
// Connector labels are checked against docs/box-connectors.md.
public class PdmViewTests
{
    private static List<FwDevice> ThreeBoards() =>
    [
        StockTests.MakeDevice(14, 0x540), // listed first on purpose: A2 by base ID, not by order
        StockTests.MakeDevice(15, 0x580),
        StockTests.MakeDevice(14, 0x500),
    ];

    [Fact]
    public void RolesComeFromTypeAndBaseId()
    {
        var view = PdmView.Build(ThreeBoards());
        Assert.Empty(view.Problems);
        Assert.Equal(["A1", "A2", "B"], view.Boards.Select(b => b.Role));
        Assert.Equal([0x500, 0x540, 0x580], view.Boards.Select(b => b.Device.BaseId));
    }

    [Fact]
    public void TwentyFourOutputsNumberedAndRated()
    {
        var view = PdmView.Build(ThreeBoards());
        Assert.Equal(Enumerable.Range(1, 24), view.Outputs.Select(o => o.Number));
        Assert.Equal(16, view.Outputs.Count(o => o.RatingA == 7.5));
        Assert.Equal(4, view.Outputs.Count(o => o.RatingA == 15.0));
        Assert.Equal(4, view.Outputs.Count(o => o.RatingA == 31.0));
        Assert.Equal([7.5, 7.5, 31.0, 31.0, 15.0, 15.0], new[] { 1, 16, 17, 20, 21, 24 }.Select(n => view.Outputs.Single(o => o.Number == n).RatingA));
        Assert.Equal(24, view.Outputs.Select(o => o.Connector).Distinct().Count());
        Assert.Equal(24, view.Outputs.Select(o => o.Output).Distinct().Count());
    }

    // b2b: a limit above the row's rating is allowed but warned; exactly the rating is fine
    [Theory]
    [InlineData(1, 7.5, false)]
    [InlineData(1, 7.6, true)]
    [InlineData(16, 100.0, true)]
    [InlineData(17, 31.0, false)]
    [InlineData(17, 31.5, true)]
    [InlineData(24, 15.0, false)]
    [InlineData(24, 15.01, true)]
    public void LimitAboveRatingIsWarned(int number, double limit, bool warned)
    {
        var view = PdmView.Build(ThreeBoards());
        foreach (var o in view.Outputs) o.Output.CurrentLimit = 1.0; // stock defaults may sit above our ratings
        Assert.Empty(view.OverRating);
        var row = view.Outputs.Single(o => o.Number == number);
        row.Output.CurrentLimit = limit;
        Assert.Equal(warned, row.OverRating);
        Assert.Equal(warned ? [number] : Array.Empty<int>(), view.OverRating.Select(o => o.Number));
        if (warned) Assert.Equal($"Output {number} ({row.Board} OUT{row.BoardOutput}): current limit {limit:0.##} A is above its {row.RatingA:0.#} A rating.", row.RatingWarning);
        else Assert.Null(row.RatingWarning);
        Assert.Equal(limit, row.Output.CurrentLimit); // warned, not clamped
    }

    [Theory]
    [InlineData(1, "A1", 1, "X1-H")]
    [InlineData(8, "A1", 8, "X1-R")]
    [InlineData(9, "A2", 1, "X1-S")]
    [InlineData(10, "A2", 2, PdmView.FanConnector)]
    [InlineData(15, "A2", 7, "X1-A")]
    [InlineData(16, "A2", 8, "X1-C")]
    [InlineData(17, "B", 1, "Stud OUT1")]
    [InlineData(20, "B", 4, "Stud OUT4")]
    [InlineData(21, "B", 5, "X1-B")]
    [InlineData(24, "B", 8, "X1-G")]
    public void OutputConnectorsMatchTheWireList(int number, string board, int boardOut, string connector)
    {
        var row = PdmView.Build(ThreeBoards()).Outputs.Single(o => o.Number == number);
        Assert.Equal((board, boardOut, connector), (row.Board, row.BoardOutput, row.Connector));
        Assert.Same(row.Device.Outputs[boardOut - 1], row.Output);
    }

    [Theory]
    [InlineData(1, "A1", "Digital", 1, "X2-7")]
    [InlineData(7, "A1", "Digital", 7, "X2-13")]
    [InlineData(8, "A2", "Digital", 1, "X2-15")]
    [InlineData(14, "A2", "Digital", 7, "X2-21")]
    [InlineData(15, "B", "Digital", 1, "X2-23")]
    [InlineData(24, "B", "Digital", 10, "X2-32")]
    [InlineData(25, "A1", "Analog", 1, "X2-14")]
    [InlineData(26, "A2", "Analog", 1, "X2-22")]
    [InlineData(27, "B", "Analog", 1, "X2-33")]
    public void InputConnectorsMatchTheWireList(int number, string board, string kind, int boardIn, string connector)
    {
        var view = PdmView.Build(ThreeBoards());
        Assert.Equal(27, view.Inputs.Count);
        Assert.Equal(27, view.Inputs.Select(i => i.Connector).Distinct().Count());
        var row = view.Inputs.Single(i => i.Number == number);
        Assert.Equal((board, kind, boardIn, connector), (row.Board, row.Kind, row.BoardInput, row.Connector));
    }

    [Fact]
    public void MissingBoardLeavesAGapAndAWarning()
    {
        var view = PdmView.Build([StockTests.MakeDevice(14, 0x500), StockTests.MakeDevice(15, 0x580)]);
        Assert.Single(view.Problems);
        Assert.Contains("A2", view.Problems[0]);
        Assert.Equal(Enumerable.Range(1, 8).Concat(Enumerable.Range(17, 8)), view.Outputs.Select(o => o.Number));
        Assert.DoesNotContain(view.Inputs, i => i.Board == "A2");
        Assert.Equal(15, view.Inputs.First(i => i.Board == "B").Number);
    }

    [Fact]
    public void ExtraBoardsAreReportedNotShown()
    {
        var devices = ThreeBoards();
        devices.Add(StockTests.MakeDevice(14, 0x5C0));
        devices.Add(StockTests.MakeDevice(15, 0x600));
        var view = PdmView.Build(devices);
        Assert.Equal(2, view.Problems.Count);
        Assert.Equal(24, view.Outputs.Count);
        Assert.DoesNotContain(view.Boards, b => b.Device.BaseId is 0x5C0 or 0x600);
    }

    [Theory]
    [InlineData(0)]
    [InlineData(1)]
    public void StockDevicesAreNotPartOfThePdm(int type)
    {
        var view = PdmView.Build([StockTests.MakeDevice(type)]);
        Assert.False(view.Any);
        Assert.Empty(view.Problems);
        Assert.Empty(view.Outputs);
        Assert.Empty(view.Inputs);
    }

    // B2: the page keeps its rows (the cell being edited, the sort order) while the boards stay the same
    [Fact]
    public void SameBoardsUntilADeviceOrARoleChanges()
    {
        var devices = ThreeBoards();
        var view = PdmView.Build(devices);
        devices[1].Outputs[4].Name = "edited";
        devices[1].Outputs[4].CurrentLimit = 12;
        Assert.True(PdmView.Build(devices).SameBoards(view));
        Assert.False(PdmView.Build(devices.Take(2)).SameBoards(view));          // board removed
        Assert.False(PdmView.Build(ThreeBoards()).SameBoards(view));            // other device objects (project reloaded)
        (devices[0].BaseId, devices[2].BaseId) = (0x500, 0x540);                // a read changed the base IDs: A1 / A2 swap
        Assert.False(PdmView.Build(devices).SameBoards(view));
    }

    [Fact]
    public void InputValueColumnIsLive()
    {
        var devices = ThreeBoards();
        var view = PdmView.Build(devices);
        Assert.Equal("OFF", view.Inputs.Single(i => i.Number == 1).Value);
        devices[2].DigitalInputs[0].State = true;                               // A1 IN1
        devices[2].AnalogInputs[0].Millivolts = 1234.4;
        Assert.Equal(("ON", "1234 mV"), (view.Inputs.Single(i => i.Number == 1).Value, view.Inputs.Single(i => i.Number == 25).Value));
    }

    [Fact]
    public void RowsPointAtTheLiveDeviceObjects()
    {
        var devices = ThreeBoards();
        var view = PdmView.Build(devices);
        devices[1].Outputs[4].Name = "fuel pump"; // board B OUT5 = output 21
        Assert.Equal("fuel pump", view.Outputs.Single(o => o.Number == 21).Output.Name);
    }
}
