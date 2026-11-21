using domain.Devices.Functions;

namespace domain.CustomPdm;

// custom-pdm uipolish (2026-11-21, Dan: "the UI treats A1, A2 and B as ONE PDM"): the /pdm "Values and system" panel
// asked "Board for counters / math / levels / values / keypad / CAN out" first. Now the values of all three boards are
// in ONE list (their texts already say where they live: "B board temperature (C)", "A1 analog input mV", "IN15"), and a
// new counter / math block / level / CAN output is made on the board its value lives on. Only the two functions that
// bring something TO a board (a value of another board, a keypad button) still say which outputs will use it.
// The per-board view of every function stays on the Advanced screen.
public record PdmWideChoice(string Key, string Role, int Var, string Text);

public static class PdmWide
{
    public static string Key(string role, int var) => $"{role}:{var}";

    // numbers of every board (PdmTriggers.ValueChoices of each), board order A1, A2, B
    public static IReadOnlyList<PdmWideChoice> Values(PdmModel m, PdmView v) =>
        v.Boards.SelectMany(b => PdmTriggers.ValueChoices(m, b.Role)
            .Select(c => new PdmWideChoice(Key(b.Role, c.Var), b.Role, c.Var, Where(b.Role, c.Text)))).ToList();

    // everything a board can send in a CAN output (its whole var map but "nothing")
    public static IReadOnlyList<PdmWideChoice> Vars(PdmModel m, PdmView v) =>
        v.Boards.SelectMany(b => b.Device.VarMap.Where(e => e.VariableIndex > 0)
            .Select(e => new PdmWideChoice(Key(b.Role, e.VariableIndex), b.Role, e.VariableIndex,
                Where(b.Role, PdmTriggers.VarText(m, b.Role, e.VariableIndex))))).ToList();

    // a text that does not say its board ("always on", "flasher 2") gets it in front; "IN15" and "B ..." stay
    private static string Where(string role, string text) =>
        text.StartsWith(role + " ", StringComparison.Ordinal) || System.Text.RegularExpressions.Regex.IsMatch(text, @"^IN\d+\b")
            ? text : $"{role} {text}";

    public static PdmWideChoice? Find(IEnumerable<PdmWideChoice> list, string? key) =>
        key == null ? null : list.FirstOrDefault(c => c.Key == key);

    // the board a digital input (PDM number 1-24) is on
    public static string? RoleOfInput(PdmView v, int number) =>
        v.Inputs.FirstOrDefault(r => r.Number == number && r.Digital != null)?.Board;

    // Math: (A op B). The block is made on A's board, so a B value must live there too. null = fine.
    public static string? MathProblem(PdmWideChoice? a, PdmWideChoice? b) =>
        a == null ? "Pick the value A."
        : b != null && b.Role != a.Role
            ? $"A is on board {a.Role} and B on board {b.Role}: bring B over first (\"Value of another board\", used by the outputs of {a.Role}), then pick it here."
            : null;

    // Analog input used as a switch: its level in mV, kept in the stock range 0-5000 (AnalogInputsGrid.razor)
    public const int ThresholdMin = 0, ThresholdMax = 5000;

    public static string? SetThreshold(AnalogInput an, int value)
    {
        an.Switch.Threshold = Math.Clamp(value, ThresholdMin, ThresholdMax);
        return value is < ThresholdMin or > ThresholdMax ? $"{an.Name}: the switching level must be {ThresholdMin} to {ThresholdMax} mV" : null;
    }
}
