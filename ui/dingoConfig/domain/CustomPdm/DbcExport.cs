using System.Globalization;
using System.Text;
using domain.Devices;
using domain.Enums;
using domain.Models;

namespace domain.CustomPdm;

// custom-pdm route B, phase B5 (docs/ui-route-b-plan.md, Dan u4c): DBC files for the ECU.
// ONE generator for both outputs, so they cannot differ:
//   - the repo files firmware/dbc/custompdm_*.dbc (written by ui/tools/DbcGen, checked by ui/tests DbcExportTests),
//   - the /pdm "Export DBC" button (the boards of the current project at their own base IDs).
// Source of truth: the cyclic signals the app itself decodes (FwDevice.GetCyclicSigs, from
// web/Definitions/custompdm-*-signals.json), checked against the firmware TX code (firmware/boards/custompdm_*/msg.cpp)
// by DbcExportTests. DBC-only presentation: names get the board prefix ("A1_Output1_Current"), msg 3 byte 7 is
// written as its three flag bits, value tables for device state / board type / output state.
public record DbcBoard(string Node, FwDevice Device);

public record DbcRepoBoard(string Node, int DeviceType, int BaseId);

public static class DbcExport
{
    public const int CyclicTxOffset = 2;          // firmware core/device_config.h CYCLIC_TX_OFFSET (msg n = base + 2 + n)
    public const string Receiver = "Vector__XXX";
    public const string PdmFileName = "custompdm_PDM.dbc";

    // Base IDs of the PDM (STATE.md): A1 0x500, A2 0x540, B 0x580
    public static readonly DbcRepoBoard[] RepoBoards = [new("A1", 14, 0x500), new("A2", 14, 0x540), new("B", 15, 0x580)];

    public static string FileName(DbcRepoBoard b) => $"custompdm_{b.Node}_0x{b.BaseId:X3}.dbc";

    // The files under firmware/dbc: one per board plus the whole PDM (= what the button gives for a default project)
    public static List<(string FileName, string Text)> RepoFiles(Func<int, FwDeviceDef?> defs, Func<int, CyclicSigsConfig?> sigs)
    {
        var boards = RepoBoards.Select(b =>
        {
            var def = defs(b.DeviceType) ?? throw new InvalidOperationException($"no device type {b.DeviceType}");
            var cfg = sigs(b.DeviceType) ?? throw new InvalidOperationException($"no cyclic signals for type {b.DeviceType}");
            return (Repo: b, Board: new DbcBoard(b.Node, new FwDevice(b.Node, b.BaseId, def, cfg)));
        }).ToList();
        var files = boards.Select(x => (FileName(x.Repo), Build([x.Board]))).ToList();
        files.Add((PdmFileName, Build(boards.Select(x => x.Board))));
        return files;
    }

    public record Signal(string Name, int StartBit, int Length, bool IsSigned, double Factor, double Offset, string Unit,
        string? Comment = null, string? ValueTable = null);

    public record Message(int Id, int MsgNumber, string Name, string Node, List<Signal> Signals);

    private static readonly string OutStateTable = Table(Enum.GetNames<OutState>());
    private static readonly string DeviceStateTable = Table(Enum.GetNames<DeviceState>());
    private const string PdmTypeTable = "14 \"custom-pdm A\" 15 \"custom-pdm B\"";

    private static string Table(string[] names) => string.Join(" ", names.Select((n, i) => $"{i} \"{n}\""));

    // The messages of one board, exactly as the app decodes them (same IDs, bits, sign, factor, unit)
    public static List<Message> Messages(DbcBoard board)
    {
        var dev = board.Device;
        var used = new HashSet<string>();
        var list = new List<Message>();
        foreach (var group in dev.GetCyclicSigs().GroupBy(s => s.MessageId).OrderBy(g => g.Key))
        {
            var msgNumber = group.Key - dev.BaseId - CyclicTxOffset;
            var signals = new List<Signal>();
            foreach (var (_, s) in group.OrderBy(x => x.Signal.StartBit))
            {
                if (s.Name == "ThermalFlags" && s.Length == 8)
                {
                    // firmware core/device.cpp GetThermalFlags: bit 0 over warn, bit 1 critical soon, bit 2 critical
                    signals.Add(new Signal("ThermalOverWarn", s.StartBit, 1, false, 1, 0, "",
                        "1 = board temperature above the warn limit (msg 3 byte 7 bit 0)"));
                    signals.Add(new Signal("ThermalCritSoon", s.StartBit + 1, 1, false, 1, 0, "",
                        "1 = board temperature within the critical-soon margin of the critical limit (bit 1)"));
                    signals.Add(new Signal("ThermalCritical", s.StartBit + 2, 1, false, 1, 0, "",
                        "1 = critical: all outputs held off except the exempt ones (bit 2)"));
                    continue;
                }
                signals.Add(new Signal(s.Name.Replace('.', '_'), s.StartBit, s.Length, s.IsSigned, s.Factor, s.Offset, s.Unit,
                    Comment(s.Name), ValueTable(s.Name)));
            }

            // Names: board prefix (one file can hold the whole PDM); a name the board already used in an earlier
            // message (digital inputs are in msg 0 and msg 37) gets the message number
            for (var i = 0; i < signals.Count; i++)
            {
                var name = $"{board.Node}_{signals[i].Name}";
                if (!used.Add(name)) { name += $"_M{msgNumber}"; used.Add(name); }
                signals[i] = signals[i] with { Name = name };
            }
            list.Add(new Message(group.Key, msgNumber, $"{board.Node}_Msg{msgNumber}", board.Node, signals));
        }
        return list;
    }

    private static string? ValueTable(string name) =>
        name == "DeviceState" ? DeviceStateTable
        : name == "PdmType" ? PdmTypeTable
        : name.StartsWith("Output") && name.EndsWith(".State") ? OutStateTable
        : null;

    private static string? Comment(string name) => name switch
    {
        "BoardTemp" => "MCP9808 board temperature; unsigned (stock dingoFW uint16), so a reading below 0 degC is not sent correctly",
        "DieTemp" => "STM32 die temperature, signed (msg 37)",
        "AnalogInput1.Raw" => "analog input raw ADC value (msg 37)",
        _ => null
    };

    // When the firmware sends each message (firmware/boards/custompdm_*/msg.cpp bSend), for ECU timeouts
    public static string MessageComment(int msgNumber) => msgNumber switch
    {
        <= 4 => "always sent",
        5 => "sent when any CAN input or virtual input is enabled",
        6 => "sent when any counter or condition is enabled",
        >= 7 and <= 22 => "sent when one of its two CAN inputs is enabled; values are encoded with each CAN input's own " +
                          "factor / offset, this file uses factor 1, offset 0 as dingoConfig does",
        23 => "sent when any output has PWM enabled",
        >= 27 and <= 29 => "sent when any timer is enabled",
        >= 30 and <= 33 => "sent when one of its two math blocks is enabled",
        >= 34 and <= 36 => "sent when one of its two digital inputs is in PWM mode",
        37 => "custom-pdm: always sent; all digital inputs, analog input, STM32 die temperature",
        _ => ""
    };

    private static readonly string[] NewSymbols =
    [
        "NS_DESC_", "CM_", "BA_DEF_", "BA_", "VAL_", "CAT_DEF_", "CAT_", "FILTER", "BA_DEF_DEF_", "EV_DATA_",
        "ENVVAR_DATA_", "SGTYPE_", "SGTYPE_VAL_", "BA_DEF_SGTYPE_", "BA_SGTYPE_", "SIG_TYPE_REF_", "VAL_TABLE_",
        "SIG_GROUP_", "SIG_VALTYPE_", "SIGTYPE_VALTYPE_", "BO_TX_BU_", "BA_DEF_REL_", "BA_REL_", "BA_DEF_DEF_REL_",
        "BU_SG_REL_", "BU_EV_REL_", "BU_BO_REL_", "SG_MUL_VAL_"
    ];

    // One DBC text for the given boards (LF line ends, invariant number format)
    public static string Build(IEnumerable<DbcBoard> boards)
    {
        var list = boards.ToList();
        var messages = list.SelectMany(Messages).OrderBy(m => m.Id).ToList();
        var dup = messages.GroupBy(m => m.Id).FirstOrDefault(g => g.Count() > 1);
        if (dup != null)
            throw new InvalidOperationException($"CAN ID 0x{dup.Key:X3} is used by {string.Join(" and ", dup.Select(m => m.Name))}: base IDs overlap");

        var sb = new StringBuilder();
        void Line(string s = "") => sb.Append(s).Append('\n');

        Line("VERSION \"custom-pdm\"");
        Line();
        Line();
        Line("NS_ :");
        foreach (var s in NewSymbols) Line("\t" + s);
        Line();
        Line("BS_:");
        Line();
        Line("BU_: " + string.Join(" ", list.Select(b => b.Node)));
        Line();
        foreach (var m in messages)
        {
            Line();
            Line($"BO_ {m.Id} {m.Name}: 8 {m.Node}");
            foreach (var s in m.Signals)
            {
                var (min, max) = Range(s);
                Line($" SG_ {s.Name} : {s.StartBit}|{s.Length}@1{(s.IsSigned ? '-' : '+')} ({Num(s.Factor)},{Num(s.Offset)}) " +
                     $"[{Num(min)}|{Num(max)}] \"{s.Unit}\" {Receiver}");
            }
        }
        Line();
        Line();
        Line("CM_ \"custom-pdm status messages (firmware NUM_TX_MSGS 38, msg n = base ID + 2 + n, Intel byte order, 8 bytes). " +
             "Generated by ui/tools/DbcGen and the /pdm Export DBC button from the same code (ui/dingoConfig/domain/CustomPdm/DbcExport.cs): do not edit.\";");
        foreach (var b in list)
            Line($"CM_ BU_ {b.Node} \"{(b.Device.DeviceTypeId == 15 ? "custom-pdm board B" : "custom-pdm board A")}, base ID 0x{b.Device.BaseId:X3}\";");
        foreach (var m in messages)
            Line($"CM_ BO_ {m.Id} \"{m.Node} msg {m.MsgNumber}: {MessageComment(m.MsgNumber)}\";");
        foreach (var m in messages)
        foreach (var s in m.Signals.Where(s => s.Comment != null))
            Line($"CM_ SG_ {m.Id} {s.Name} \"{s.Comment}\";");
        foreach (var m in messages)
        foreach (var s in m.Signals.Where(s => s.ValueTable != null))
            Line($"VAL_ {m.Id} {s.Name} {s.ValueTable} ;");
        return sb.ToString();
    }

    private static (double Min, double Max) Range(Signal s)
    {
        var (lo, hi) = s.IsSigned
            ? (-Math.Pow(2, s.Length - 1), Math.Pow(2, s.Length - 1) - 1)
            : (0.0, Math.Pow(2, s.Length) - 1);
        var a = lo * s.Factor + s.Offset;
        var b = hi * s.Factor + s.Offset;
        return (Math.Min(a, b), Math.Max(a, b));
    }

    private static string Num(double v) => Math.Round(v, 6).ToString("0.######", CultureInfo.InvariantCulture);
}
