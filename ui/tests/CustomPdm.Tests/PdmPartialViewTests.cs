using domain.CustomPdm;
using Xunit;

namespace CustomPdm.Tests;

// uifix (BACKLOG 2026-11-21): /pdm with a view that lacks a board. Found: the 10 Hz refresh of another /pdm tab (its
// own Blazor circuit, the same DeviceManager) builds its view while "New PDM" is still adding A1, A2 and B one by one
// (A1 only, then A1 + A2); the Values panel asked for its default board "B" and PdmModel.Board threw "Sequence
// contains no matching element" (PdmValuesPanel.razor line 23). A project without B (B deleted on the Devices page)
// is the same view. The panel itself: PdmValuesPanelTests (bUnit).
public class PdmPartialViewTests
{
    // the New PDM boards of these roles, our factory defaults
    internal static PdmView View(params string[] roles) => PdmView.Build(PdmFactoryDefaults.Boards
        .Where(b => roles.Contains(b.Role))
        .Select(b =>
        {
            var d = StockTests.MakeDevice(b.Type, b.BaseId);
            PdmFactoryDefaults.Apply(d, b.Role);
            return d;
        }).ToList());

    [Fact]
    public void ValuesPanelDefaultBoardIsMissingWhileNewPdmAddsTheBoards()
    {
        var v = View("A1", "A2");                 // what another tab sees after New PDM added A1 and A2
        var m = PdmModel.Build(v);
        Assert.Throws<InvalidOperationException>(() => PdmTriggers.ValueChoices(m, "B"));   // the crash
        Assert.Equal("A1", v.RoleOr("B"));       // the fix: the panel keeps its board inside the view
        Assert.NotEmpty(PdmTriggers.ValueChoices(m, v.RoleOr("B")!));
    }

    [Theory]
    [InlineData("A1")]
    [InlineData("A1,A2")]
    [InlineData("B")]
    [InlineData("A1,A2,B")]
    public void ValuesPanelChoicesBuildForEveryBoardSet(string roles)
    {
        var v = View(roles.Split(','));
        var m = PdmModel.Build(v);
        var board = v.RoleOr("B")!;               // the panel's defaults: board B, values from A1
        var from = v.RoleOr("A1", not: board);
        Assert.Contains(v.Boards, b => b.Role == board);
        // what PdmValuesPanel renders for its board
        Assert.NotEmpty(PdmTriggers.ValueChoices(m, board));
        Assert.NotEmpty(m.Use(board).Kinds);
        foreach (var e in m.Board(board).Device.VarMap.Where(e => e.VariableIndex > 0))
            Assert.NotEmpty(PdmTriggers.VarText(m, board, e.VariableIndex));
        if (v.Boards.Count == 1)
        {
            Assert.Null(from);
            return;
        }
        Assert.NotEqual(board, from);
        Assert.Contains(v.Boards, b => b.Role == from);
        Assert.NotEmpty(PdmValues.RemoteSignals(v, from!, out _));
    }

    [Fact]
    public void RoleOrKeepsAPresentBoardAndSkipsNot()
    {
        var v = View("A1", "A2", "B");
        Assert.Equal("B", v.RoleOr("B"));
        Assert.Equal("A2", v.RoleOr("A2", not: "B"));
        Assert.Equal("A1", v.RoleOr("B", not: "B"));
        Assert.Equal("A2", v.RoleOr("A1", not: "A1"));
        Assert.Null(new PdmView().RoleOr("B"));
        Assert.Null(View("A1").RoleOr("A1", not: "A1"));
    }
}
