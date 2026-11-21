using System.Text.RegularExpressions;
using application.Services;
using domain.CustomPdm;
using domain.Devices;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace CustomPdm.Tests;

// uipolish (2026-11-21): one-PDM gaps of /pdm: the Values panel asks for no board (PdmWide), analog inputs are set on
// /pdm, and the project's output / input names go into the DBC export.
public class OnePdmTests
{
    private static FakePdm NewPdm()
    {
        var pdm = new FakePdm();
        foreach (var b in pdm.View.Boards) PdmFactoryDefaults.Apply(b.Device, b.Role);
        return pdm;
    }

    private static object[] Snapshot(FwDevice d) => d.Params.Select(p => p.GetValue()).ToArray();

    [Fact]
    public void TheValuesOfAllBoardsAreOneListThatSaysWhereEachLives()
    {
        var pdm = NewPdm();
        var v = pdm.View;
        var m = PdmModel.Build(v);
        var wide = PdmWide.Values(m, v);
        Assert.Equal(wide.Count, wide.Select(c => c.Key).Distinct().Count());
        Assert.Equal(["A1", "A2", "B"], wide.Select(c => c.Role).Distinct());
        foreach (var role in PdmOps.Roles)
        {
            Assert.Equal(PdmTriggers.ValueChoices(m, role).Select(c => PdmWide.Key(role, c.Var)),
                wide.Where(c => c.Role == role).Select(c => c.Key));
            Assert.Contains(wide, c => c.Text == $"{role} battery voltage (V)");
            Assert.Contains(wide, c => c.Text == $"{role} board temperature (C)");
        }
        Assert.All(wide, c => Assert.Matches($@"^({c.Role} |IN\d+\b)", c.Text));   // every value text says where it lives

        var vars = PdmWide.Vars(m, v);
        Assert.Equal(v.Boards.Sum(b => b.Device.VarMap.Count(e => e.VariableIndex > 0)), vars.Count);
        Assert.All(vars, c => Assert.Matches($@"^({c.Role} |IN\d+\b)", c.Text));
        Assert.DoesNotContain(vars, c => c.Var == 0);
        Assert.Equal(("B", 5), (PdmWide.Find(vars, "B:5")!.Role, PdmWide.Find(vars, "B:5")!.Var));
        Assert.Null(PdmWide.Find(vars, null));
        Assert.Null(PdmWide.Find(vars, "C:1"));
        Assert.Null(PdmWide.Find(vars, ""));
    }

    [Fact]
    public void ANewFunctionGoesOnTheBoardItsValueOrInputLivesOn()
    {
        var pdm = NewPdm();
        var v = pdm.View;
        Assert.All(v.Inputs.Where(r => r.Digital != null), r => Assert.Equal(r.Board, PdmWide.RoleOfInput(v, r.Number)));
        Assert.Null(PdmWide.RoleOfInput(v, 25));   // an analog input is not a counter input
        Assert.Null(PdmWide.RoleOfInput(v, 99));

        var before = pdm.View.Boards.ToDictionary(b => b.Role, b => Snapshot(b.Device));
        var temp = PdmWide.Values(PdmModel.Build(v), v).Single(c => c.Text == "A2 board temperature (C)");
        Assert.Null(PdmValues.AddLevel(v, temp.Role, new PdmThreshold(temp.Var, true, 60, 50), out _));
        Assert.Null(PdmValues.AddMath(v, new PdmMathSpec(temp.Role, domain.Enums.MathOp.Mul, temp.Var, 0, 2), out _));
        Assert.NotEqual(before["A2"], Snapshot(pdm.Dev("A2")));   // made on A2, where the value is ...
        Assert.Equal(before["A1"], Snapshot(pdm.Dev("A1")));      // ... and nowhere else
        Assert.Equal(before["B"], Snapshot(pdm.Dev("B")));

        var b = PdmWide.Values(PdmModel.Build(v), v).First(c => c.Role == "B");
        Assert.Equal("Pick the value A.", PdmWide.MathProblem(null, b));
        Assert.Null(PdmWide.MathProblem(temp, null));              // B = a constant
        Assert.Null(PdmWide.MathProblem(temp, temp));
        Assert.Equal("A is on board A2 and B on board B: bring B over first (\"Value of another board\", used by the outputs of A2), then pick it here.",
            PdmWide.MathProblem(temp, b));
    }

    [Fact]
    public async Task AnalogInputsAreSetOnThePdmPageWrittenAndSaved()
    {
        var pdm = new FakePdm();
        Assert.Null(pdm.Run(PdmOpKind.ReadAll));
        var an = pdm.View.Inputs.Single(r => r.Number == 26).Analog!;   // A2's analog input, as the /pdm row gives it
        Assert.Same(pdm.Dev("A2").AnalogInputs[0], an);
        (an.Enabled, an.Name, an.Switch.Enabled, an.Switch.Invert) = (true, "Fuel level", true, true);
        Assert.Null(PdmWide.SetThreshold(an, 2500));
        Assert.Equal(2500, an.Switch.Threshold);
        Assert.Equal("Fuel level: the switching level must be 0 to 5000 mV", PdmWide.SetThreshold(an, 5001));
        Assert.Equal(5000, an.Switch.Threshold);
        Assert.Equal("Fuel level: the switching level must be 0 to 5000 mV", PdmWide.SetThreshold(an, -1));
        Assert.Equal(0, an.Switch.Threshold);
        Assert.Null(PdmWide.SetThreshold(an, 0));
        Assert.Null(PdmWide.SetThreshold(an, 5000));
        Assert.Null(PdmWide.SetThreshold(an, 1800));

        Assert.Null(pdm.Run(PdmOpKind.WriteAll));
        Assert.All(pdm.States, s => Assert.Equal(PdmStepState.Ok, s));
        ProjectFileTests.AssertBoardHoldsThePcValues(pdm, "A2");

        var files = new ConfigFileManager(NullLogger<ConfigFileManager>.Instance, new FwDeviceDefManager());
        var path = Path.Combine(Path.GetTempPath(), $"cpdm-analog-{Guid.NewGuid():N}.json");
        await files.SaveDevices(pdm.Mgr.GetDevices(), path);
        var again = (await files.LoadDevices(path))!.OfType<FwDevice>().Single(d => d.Name == "A2").AnalogInputs[0];
        Assert.Equal((true, "Fuel level", true, true, 1800), (again.Enabled, again.Name, again.Switch.Enabled, again.Switch.Invert, again.Switch.Threshold));
    }

    // ---------------- DBC export: the project's names ----------------

    private static List<string> PdmNames(string dbc) =>
        Regex.Matches(dbc, "BA_ \"PdmName\" SG_ \\d+ \\S+ \"([^\"]+)\";").Select(x => x.Groups[1].Value).ToList();

    private static string Export(FakePdm pdm) => DbcExport.Build(pdm.View.Boards.Select(b => new DbcBoard(b.Role, b.Device)));

    [Fact]
    public void OutputAndInputNamesOfTheProjectGoIntoTheDbcExport()
    {
        var pdm = new FakePdm();
        var stock = Export(pdm);
        var pump = PdmView.OutputNumber("B", 4)!.Value;
        var ign = PdmView.DigitalInputNumber("A1", 2)!.Value;
        var level = PdmView.AnalogInputNumber("A2")!.Value;
        pdm.Dev("B").Outputs[4].Name = "Fuel pump";
        pdm.Dev("A1").DigitalInputs[2].Name = "Ignition";
        pdm.Dev("A2").AnalogInputs[0].Name = "Fuel level (tank)";
        var named = Export(pdm);

        string Swap(string n) => n.Replace($"PDM_Out{pump}_", "Fuel_pump_").Replace($"PDM_In{ign}_", "Ignition_").Replace($"PDM_In{level}_", "Fuel_level_tank_");
        var before = PdmNames(stock);
        var after = PdmNames(named);
        Assert.Equal(before.Select(Swap), after);
        Assert.Contains("Fuel_pump_Current", after);
        Assert.Contains("Fuel_pump_State", after);
        Assert.True(after.Count(n => n.StartsWith("Ignition_")) >= 2);          // msg 0 and msg 37 both carry the input
        Assert.Contains(after, n => n.StartsWith("Fuel_level_tank_"));
        Assert.DoesNotContain(after, n => n.StartsWith($"PDM_Out{pump}_") || n.StartsWith($"PDM_In{ign}_") || n.StartsWith($"PDM_In{level}_"));
        Assert.Equal(before.Count - after.Count(n => !n.StartsWith("PDM_")), after.Count(n => n.StartsWith("PDM_")));   // the rest keep their numbers
        Assert.Equal(after.Count, after.Distinct().Count());
        Assert.Contains($"\"PDM-wide name Fuel_pump_Current", named);          // the signal comment follows

        // the signals themselves (per-board names, bits, scaling) are untouched: only attribute and comment lines differ
        static List<string> Signals(string dbc) => dbc.Split('\n').Where(l => l.StartsWith(" SG_") || l.StartsWith("BO_")).ToList();
        Assert.Equal(Signals(stock), Signals(named));
    }

    [Fact]
    public void ANameUsedTwiceGetsThePdmNumberAndStockNamesKeepTheirs()
    {
        var pdm = new FakePdm();
        pdm.Dev("A1").Outputs[0].Name = "Lamp";
        pdm.Dev("A1").Outputs[2].Name = "lamp";          // the same word for an ECU
        pdm.Dev("B").DigitalInputs[0].Name = "Lamp";     // and an input with it
        pdm.Dev("A2").Outputs[3].Name = "Horn";
        var names = DbcExport.ProjectNames(pdm.View.Boards.Select(b => new DbcBoard(b.Role, b.Device)));
        var (o1, o3, i) = (PdmView.OutputNumber("A1", 0), PdmView.OutputNumber("A1", 2), PdmView.DigitalInputNumber("B", 0));
        Assert.Equal(4, names.Count);
        Assert.Equal(($"Lamp_Out{o1}", $"lamp_Out{o3}", $"Lamp_In{i}", "Horn"),
            (names[$"PDM_Out{o1}"], names[$"PDM_Out{o3}"], names[$"PDM_In{i}"], names[$"PDM_Out{PdmView.OutputNumber("A2", 3)}"]));
        var after = PdmNames(Export(pdm));
        Assert.Equal(after.Count, after.Distinct().Count());
        Assert.Contains($"Lamp_Out{o1}_Current", after);
        Assert.Contains("Horn_Current", after);

        Assert.Empty(DbcExport.ProjectNames(new FakePdm().View.Boards.Select(b => new DbcBoard(b.Role, b.Device))));   // stock names only
    }

    [Theory]
    [InlineData("Fuel pump", "Fuel_pump")]
    [InlineData("  12V feed (rear)! ", "_12V_feed_rear")]
    [InlineData("A/C  clutch", "A_C_clutch")]
    [InlineData("Öl-Pumpe", "l_Pumpe")]
    [InlineData("already_ok_9", "already_ok_9")]
    [InlineData("output7", null)]
    [InlineData("Output12", null)]
    [InlineData("digitalInput5", null)]
    [InlineData("analogInput1", null)]
    [InlineData("output7 spare", "output7_spare")]
    [InlineData("", null)]
    [InlineData("   ", null)]
    [InlineData("***", null)]
    [InlineData(null, null)]
    public void NamesAreMadeDbcSafe(string? name, string? safe) => Assert.Equal(safe, DbcExport.Sanitise(name));

    [Fact]
    public void ALongNameIsCut()
    {
        var s = DbcExport.Sanitise(new string('a', 39) + " bcdef")!;
        Assert.Equal(new string('a', 39), s);            // cut at 40, the trailing "_" dropped
        Assert.Equal(40, DbcExport.Sanitise(new string('x', 70))!.Length);
        Assert.Equal(40, DbcExport.NameMax);
    }
}
