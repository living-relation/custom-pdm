using domain.Devices;
using domain.Devices.Functions;

namespace domain.CustomPdm;

// custom-pdm route B, phase B1 (docs/ui-route-b-plan.md): the three boards shown as one PDM.
// Roles: the type 14 boards sorted by base ID are A1 then A2; the type 15 board is B.
// Numbers are fixed (outputs A1 1-8, A2 9-16, B 17-24; digital inputs A1 1-7, A2 8-14, B 15-24), so a missing board
// leaves a gap instead of renumbering. Connector labels and ratings: docs/box-connectors.md.
public record PdmBoard(string Role, FwDevice Device);

public record PdmOutputRow(int Number, string Board, int BoardOutput, double RatingA, string Connector,
    FwDevice Device, Output Output)
{
    // b2b (Dan, 2026-11-15): a current limit above the row's rating is allowed (as in stock dingoConfig, 0-100 A)
    // but warned about. Live: it follows the edited value.
    public bool OverRating => Output.CurrentLimit > RatingA;

    public string? RatingWarning => OverRating
        ? $"Output {Number} ({Board} OUT{BoardOutput}): current limit {Output.CurrentLimit:0.##} A is above its {RatingA:0.#} A rating."
        : null;
}

public record PdmInputRow(int Number, string Board, string Kind, int BoardInput, string Connector,
    FwDevice Device, DigitalInput? Digital, AnalogInput? Analog)
{
    public string Name => Digital?.Name ?? Analog?.Name ?? "";
    public bool Enabled => Digital?.Enabled ?? Analog?.Enabled ?? false;
    public string Value => Digital != null ? (Digital.State ? "ON" : "OFF") : $"{Analog?.Millivolts:F0} mV"; // live
}

public class PdmView
{
    public const string FanConnector = "Fans (inside the box)";

    private static readonly string[] A1Cavities = ["H", "J", "K", "L", "M", "N", "P", "R"];
    private static readonly string?[] A2Cavities = ["S", null, "U", "V", "W", "X", "A", "C"]; // OUT2 = fans (r7a)
    private static readonly string[] BCavities = ["B", "D", "E", "G"];                        // OUT5-8, size 12

    public List<PdmBoard> Boards { get; } = [];
    public List<string> Problems { get; } = [];
    public List<PdmOutputRow> Outputs { get; } = [];
    public List<PdmInputRow> Inputs { get; } = [];

    public double TotalCurrent => Boards.Sum(b => b.Device.TotalCurrent);
    public List<PdmOutputRow> OverRating => Outputs.Where(o => o.OverRating).ToList();
    public bool Any => Boards.Count > 0;

    // B2: true when both views hold the same device objects in the same roles. The /pdm page then keeps its rows
    // through the live refresh, so a cell that is being edited (and the sort order) is not thrown away 10 times a second.
    public bool SameBoards(PdmView other) =>
        Boards.Count == other.Boards.Count
        && Boards.Zip(other.Boards).All(p => p.First.Role == p.Second.Role && ReferenceEquals(p.First.Device, p.Second.Device))
        && Problems.SequenceEqual(other.Problems);

    public static PdmView Build(IEnumerable<FwDevice> devices)
    {
        var view = new PdmView();
        var custom = devices.Where(d => d.CustomPdm != null).ToList();
        var a = custom.Where(d => d.DeviceTypeId == 14).OrderBy(d => d.BaseId).ToList();
        var b = custom.Where(d => d.DeviceTypeId == 15).OrderBy(d => d.BaseId).ToList();
        if (custom.Count == 0) return view;

        if (a.Count > 0) view.Boards.Add(new PdmBoard("A1", a[0])); else view.Problems.Add("No board A1 (custom-pdm A) in the project.");
        if (a.Count > 1) view.Boards.Add(new PdmBoard("A2", a[1])); else view.Problems.Add("No board A2 (second custom-pdm A) in the project.");
        if (b.Count > 0) view.Boards.Add(new PdmBoard("B", b[0])); else view.Problems.Add("No board B (custom-pdm B) in the project.");
        if (a.Count > 2) view.Problems.Add($"{a.Count - 2} extra custom-pdm A device(s) not shown (only the two lowest base IDs are used).");
        if (b.Count > 1) view.Problems.Add($"{b.Count - 1} extra custom-pdm B device(s) not shown (only the lowest base ID is used).");

        foreach (var board in view.Boards)
        {
            var dev = board.Device;
            for (var i = 0; i < dev.Outputs.Count && OutputNumber(board.Role, i) is { } n; i++)
                view.Outputs.Add(new PdmOutputRow(n, board.Role, i + 1, Rating(board.Role, i),
                    OutputConnector(board.Role, i), dev, dev.Outputs[i]));

            for (var i = 0; i < dev.DigitalInputs.Count && DigitalInputNumber(board.Role, i) is { } n; i++)
                view.Inputs.Add(new PdmInputRow(n, board.Role, "Digital", i + 1,
                    $"X2-{DigitalCavity(board.Role, i)}", dev, dev.DigitalInputs[i], null));
        }

        // analog inputs after the 24 digital ones: 25 (A1), 26 (A2), 27 (B)
        foreach (var board in view.Boards)
        {
            if (board.Device.AnalogInputs.Count == 0 || AnalogInputNumber(board.Role) is not { } n) continue;
            var cav = board.Role switch { "A1" => 14, "A2" => 22, _ => 33 };
            view.Inputs.Add(new PdmInputRow(n, board.Role, "Analog", 1, $"X2-{cav}", board.Device, null,
                board.Device.AnalogInputs[0]));
        }

        return view;
    }

    // The PDM-wide numbers (also used for the DBC PDM-wide names, d2b): board output i (0-based) of a role, board
    // digital input i, the role's analog input; null when the role has no such row.
    public static int? OutputNumber(string role, int i) =>
        i is >= 0 and < 8 && role is "A1" or "A2" or "B" ? role switch { "A1" => 0, "A2" => 8, _ => 16 } + i + 1 : null;

    public static int? DigitalInputNumber(string role, int i) =>
        role is "A1" or "A2" or "B" && i >= 0 && i < (role == "B" ? 10 : 7)
            ? role switch { "A1" => 0, "A2" => 7, _ => 14 } + i + 1 : null;

    public static int? AnalogInputNumber(string role) => role switch { "A1" => 25, "A2" => 26, "B" => 27, _ => null };

    private static double Rating(string role, int i) => role == "B" ? (i < 4 ? 31.0 : 15.0) : 7.5;

    private static string OutputConnector(string role, int i) => role switch
    {
        "A1" => $"X1-{A1Cavities[i]}",
        "A2" => A2Cavities[i] is { } c ? $"X1-{c}" : FanConnector,
        _ => i < 4 ? $"Stud OUT{i + 1}" : $"X1-{BCavities[i - 4]}"
    };

    // X2 cavities: A1 IN1-7 = 7-13, A2 IN1-7 = 15-21, B IN1-10 = 23-32
    private static int DigitalCavity(string role, int i) => role switch { "A1" => 7, "A2" => 15, _ => 23 } + i;
}
