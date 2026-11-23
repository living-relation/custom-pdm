using System.Globalization;
using System.Text;
using System.Text.RegularExpressions;
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
// written as its three flag bits, value tables for device state / board type / output state, and (d2b) the PDM-wide
// name of every output / input signal as the string attribute PdmName plus the signal comment.
public record DbcBoard(string Node, FwDevice Device);

public record DbcRepoBoard(string Node, int DeviceType, int BaseId);

public static class DbcExport
{
    public const int CyclicTxOffset = 2;          // firmware core/device_config.h CYCLIC_TX_OFFSET (msg n = base + 2 + n)
    public const string Receiver = "Vector__XXX";
    public const string PdmFileName = "custompdm_PDM.dbc";

    // Base IDs of the PDM (docs/box-connectors.md): A1 0x500, A2 0x540, B 0x580
    public static readonly DbcRepoBoard[] RepoBoards = [new("A1", 14, 0x500), new("A2", 14, 0x540), new("B", 15, 0x580)];

    public static string FileName(DbcRepoBoard b) => $"custompdm_{b.Node}_0x{b.BaseId:X3}.dbc";

    // The files under firmware/dbc: one per board plus the whole PDM (= what the button gives for a default project)
    public static List<(string FileName, string Text)> RepoFiles(Func<int, FwDeviceDef?> defs, Func<int, CyclicSigsConfig?> sigs)
    {
        var boards = RepoDbcBoards(defs, sigs);
        var files = boards.Select((b, i) => (FileName(RepoBoards[i]), Build([b]))).ToList();
        files.Add((PdmFileName, Build(boards)));
        return files;
    }

    // The three boards of the PDM at their repo base IDs (also the input of ui/tools/CarCanDummy)
    public static List<DbcBoard> RepoDbcBoards(Func<int, FwDeviceDef?> defs, Func<int, CyclicSigsConfig?> sigs) =>
        RepoBoards.Select(b =>
        {
            var def = defs(b.DeviceType) ?? throw new InvalidOperationException($"no device type {b.DeviceType}");
            var cfg = sigs(b.DeviceType) ?? throw new InvalidOperationException($"no cyclic signals for type {b.DeviceType}");
            return new DbcBoard(b.Node, new FwDevice(b.Node, b.BaseId, def, cfg));
        }).ToList();

    // d2b (Dan, 2026-11-16): PdmName = the PDM-wide name ("PDM_Out17_Current"), numbered as PdmView numbers its rows.
    // The signal itself keeps its per-board name: one DBC message cannot hold two signals with one name, and two
    // signals on the same bits are refused by strict DBC tools, so the PDM-wide name is a string attribute (BA_ PdmName)
    // and the start of the signal comment.
    public record Signal(string Name, int StartBit, int Length, bool IsSigned, double Factor, double Offset, string Unit,
        string? Comment = null, string? ValueTable = null, string? PdmName = null);

    public const string PdmNameAttribute = "PdmName";

    private static readonly Regex OutputName = new(@"^Output(\d+)_(\w+)$");
    private static readonly Regex DigitalName = new(@"^DigitalInput(\d+)_(\w+)$");
    private static readonly Regex AnalogName = new(@"^AnalogInput1_(\w+)$");

    // The PDM-wide name of a board signal (name without the board prefix, "Output1_Current"), or null
    public static string? PdmName(string node, string name)
    {
        var m = OutputName.Match(name);
        if (m.Success)
            return PdmView.OutputNumber(node, int.Parse(m.Groups[1].Value) - 1) is { } o ? $"PDM_Out{o}_{m.Groups[2].Value}" : null;
        m = DigitalName.Match(name);
        if (m.Success)
            return PdmView.DigitalInputNumber(node, int.Parse(m.Groups[1].Value) - 1) is { } d ? $"PDM_In{d}_{m.Groups[2].Value}" : null;
        m = AnalogName.Match(name);
        return m.Success && PdmView.AnalogInputNumber(node) is { } a ? $"PDM_In{a}_{m.Groups[1].Value}" : null;
    }

    // uipolish (2026-11-21): the names the user gave outputs and inputs in the project go into the export: the
    // PDM-wide name of output 19 "Fuel pump" is "Fuel_pump_Current", not "PDM_Out19_Current". Key = "PDM_Out19" /
    // "PDM_In15", value = the sanitised name. Stock names (output3, digitalInput5) and empty ones keep the number;
    // a name used by two outputs / inputs of the PDM gets the number added ("Lamp_Out1", "Lamp_Out3").
    public static IReadOnlyDictionary<string, string> ProjectNames(IEnumerable<DbcBoard> boards)
    {
        var named = new List<(string Key, string Name)>();
        void Add(string kind, int? number, string? name)
        {
            if (number != null && Sanitise(name) is { } s) named.Add(($"PDM_{kind}{number}", s));
        }

        foreach (var b in boards)
        {
            for (var i = 0; i < b.Device.Outputs.Count; i++) Add("Out", PdmView.OutputNumber(b.Node, i), b.Device.Outputs[i].Name);
            for (var i = 0; i < b.Device.DigitalInputs.Count; i++) Add("In", PdmView.DigitalInputNumber(b.Node, i), b.Device.DigitalInputs[i].Name);
            if (b.Device.AnalogInputs.Count > 0) Add("In", PdmView.AnalogInputNumber(b.Node), b.Device.AnalogInputs[0].Name);
        }

        var twice = named.GroupBy(n => n.Name, StringComparer.OrdinalIgnoreCase).Where(g => g.Count() > 1)
            .Select(g => g.Key).ToHashSet(StringComparer.OrdinalIgnoreCase);
        return named.ToDictionary(n => n.Key, n => twice.Contains(n.Name) ? $"{n.Name}_{n.Key[4..]}" : n.Name);
    }

    private static readonly Regex StockName = new(@"^(output|digitalInput|analogInput)\d+$", RegexOptions.IgnoreCase);
    public const int NameMax = 40;

    // A name as a DBC-safe word: letters, digits and "_" only, not starting with a digit. null = no own name.
    public static string? Sanitise(string? name)
    {
        var n = name?.Trim() ?? "";
        if (n == "" || StockName.IsMatch(n)) return null;
        n = Regex.Replace(n, "[^A-Za-z0-9]+", "_").Trim('_');
        if (n == "") return null;
        if (char.IsDigit(n[0])) n = "_" + n;
        return n.Length > NameMax ? n[..NameMax].TrimEnd('_') : n;
    }

    // canboard: Dlc / Comment for the frames of a CANBoard (a PDM status message is always 8 bytes)
    public record Message(int Id, int MsgNumber, string Name, string Node, List<Signal> Signals, int Dlc = 8, string? Comment = null);

    private static readonly string OutStateTable = Table(Enum.GetNames<OutState>());
    private static readonly string DeviceStateTable = Table(Enum.GetNames<DeviceState>());
    private const string PdmTypeTable = "14 \"custom-pdm A\" 15 \"custom-pdm B\"";

    private static string Table(string[] names) => string.Join(" ", names.Select((n, i) => $"{i} \"{n}\""));

    // The messages of one board, exactly as the app decodes them (same IDs, bits, sign, factor, unit)
    public static List<Message> Messages(DbcBoard board) => Messages(board, null);

    // names: ProjectNames of the whole export (null = PDM numbers only, as the repo files)
    public static List<Message> Messages(DbcBoard board, IReadOnlyDictionary<string, string>? names)
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
                var pdm = PdmName(board.Node, signals[i].Name);
                if (pdm != null && names != null && pdm.IndexOf('_', 4) is int cut and > 0 && names.TryGetValue(pdm[..cut], out var own))
                    pdm = own + pdm[cut..];   // "PDM_Out19_Current" -> "Fuel_pump_Current"
                if (pdm != null && !used.Add(pdm)) { pdm += $"_M{msgNumber}"; used.Add(pdm); }
                var comment = pdm == null ? signals[i].Comment
                    : $"PDM-wide name {pdm}" + (signals[i].Comment is { } c ? "; " + c : "");
                signals[i] = signals[i] with { Name = name, PdmName = pdm, Comment = comment };
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
        var names = ProjectNames(list);
        var canBoards = CanBoards(list);
        var messages = list.SelectMany(b => Messages(b, names)).Concat(canBoards.SelectMany(c => c.Messages)).OrderBy(m => m.Id).ToList();
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
        Line("BU_: " + string.Join(" ", list.Select(b => b.Node).Concat(canBoards.Select(c => c.Node))));
        Line();
        foreach (var m in messages)
        {
            Line();
            Line($"BO_ {m.Id} {m.Name}: {m.Dlc} {m.Node}");
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
             "Generated by ui/tools/DbcGen and the /pdm Export DBC button from the same code (ui/dingoConfig/domain/CustomPdm/DbcExport.cs): do not edit. " +
             "Output and input signals also carry their PDM-wide name (outputs 1-24, inputs 1-27 as on the /pdm page) in the attribute " + PdmNameAttribute + " and in their comment.\";");
        foreach (var b in list)
            Line($"CM_ BU_ {b.Node} \"{(b.Device.DeviceTypeId == 15 ? "custom-pdm board B" : "custom-pdm board A")}, base ID 0x{b.Device.BaseId:X3}\";");
        foreach (var c in canBoards)
            Line($"CM_ BU_ {c.Node} \"Dingo Electronics CANBoard '{c.Name}' (dingoFW), base ID 0x{c.BaseId:X3}: more inputs / outputs for the PDM over CAN\";");
        foreach (var m in messages)
            Line($"CM_ BO_ {m.Id} \"{m.Comment ?? $"{m.Node} msg {m.MsgNumber}: {MessageComment(m.MsgNumber)}"}\";");
        foreach (var m in messages)
        foreach (var s in m.Signals.Where(s => s.Comment != null))
            Line($"CM_ SG_ {m.Id} {s.Name} \"{s.Comment}\";");
        if (messages.Any(m => m.Signals.Any(s => s.PdmName != null)))
        {
            Line($"BA_DEF_ SG_  \"{PdmNameAttribute}\" STRING ;");
            Line($"BA_DEF_DEF_  \"{PdmNameAttribute}\" \"\";");
            foreach (var m in messages)
            foreach (var s in m.Signals.Where(s => s.PdmName != null))
                Line($"BA_ \"{PdmNameAttribute}\" SG_ {m.Id} {s.Name} \"{s.PdmName}\";");
        }
        foreach (var m in messages)
        foreach (var s in m.Signals.Where(s => s.ValueTable != null))
            Line($"VAL_ {m.Id} {s.Name} {s.ValueTable} ;");
        return sb.ToString();
    }

    // canboard (2026-11-22): the frames of every CANBoard preset of the project (PdmCanBoard: read back from the boards'
    // CAN inputs), with the user's names: its three always-sent status frames (firmware/boards/canboard_v2/msg.cpp
    // TxMsg0-2) and the command frames the PDM sends for its outputs. None in the repo files (fresh boards).
    public record CanBoardDbc(string Node, string Name, int BaseId, List<Message> Messages);

    public static List<CanBoardDbc> CanBoards(IReadOnlyList<DbcBoard> boards)
    {
        var result = new List<CanBoardDbc>();
        var used = new HashSet<string>(boards.Select(b => b.Node), StringComparer.OrdinalIgnoreCase);
        string Unique(string n)
        {
            var name = n;
            for (var i = 2; !used.Add(name); i++) name = $"{n}_{i}";
            return name;
        }

        foreach (var cb in PdmCanBoard.All(PdmView.Build(boards.Select(b => b.Device))))
        {
            var node = Unique(Sanitise(cb.Name) ?? $"CANBoard_{cb.BaseId:X3}");
            string In(PdmCanBoardSignal s) =>
                Unique(Sanitise(PdmCanBoard.Label(cb, s, cb.Inputs.FirstOrDefault(i => i.Signal == s)?.Input)) ?? $"{node}_{s.Key}");
            Signal Sig(PdmCanBoardSignal s) => new(In(s), s.StartBit, s.Length, false, 1, 0,
                s.Kind == PdmCanBoardKind.Analog ? "mV" : "", s.Kind == PdmCanBoardKind.Analog ? "analog input, 0-5 V" : null);
            var an = PdmCanBoard.Signals.Where(s => s.Kind == PdmCanBoardKind.Analog).ToList();
            var msgs = new List<Message>
            {
                new(cb.BaseId + CyclicTxOffset + PdmCanBoard.AnalogMsg, PdmCanBoard.AnalogMsg, $"{node}_Msg0", node, an.Take(4).Select(Sig).ToList(),
                    Comment: $"{node} msg 0: analog inputs 1-4 in mV, always sent every {PdmCanBoard.PeriodMs} ms"),
                new(cb.BaseId + CyclicTxOffset + PdmCanBoard.Analog5Msg, PdmCanBoard.Analog5Msg, $"{node}_Msg1", node,
                    [Sig(an[4]), new Signal(Unique($"{node}_Temperature"), 48, 16, false, 1, 0, "degC", "STM32 temperature")],
                    Comment: $"{node} msg 1: analog input 5 in mV and the STM32 temperature, always sent every {PdmCanBoard.PeriodMs} ms")
            };
            var state = PdmCanBoard.Signals.Where(s => s.Kind == PdmCanBoardKind.Rotary).Select(Sig).ToList();
            state.AddRange(Enumerable.Range(0, 4).Select(i => new Signal(Unique($"{node}_Flasher{i + 1}"), 24 + i, 1, false, 1, 0, "")));
            state.AddRange(PdmCanBoard.Signals.Where(s => s.Kind == PdmCanBoardKind.Switch).Select(Sig));
            state.AddRange(Enumerable.Range(0, PdmCanBoard.Analogs).Select(i => new Signal(Unique($"{node}_AnalogSwitch{i + 1}"), 40 + i, 1, false, 1, 0, "")));
            state.AddRange(Enumerable.Range(0, PdmCanBoard.Outs).Select(i => new Signal(Unique($"{node}_Output{i + 1}_State"), 48 + i, 1, false, 1, 0, "", "1 = the low-side output is on")));
            state.Add(new Signal(Unique($"{node}_Heartbeat"), 56, 8, false, 1, 0, "", "+1 with every frame"));
            msgs.Add(new Message(cb.BaseId + CyclicTxOffset + PdmCanBoard.StateMsg, PdmCanBoard.StateMsg, $"{node}_Msg2", node, state,
                Comment: $"{node} msg 2: rotary positions, digital inputs 1-8, analog inputs as switches, output states, heartbeat; always sent every {PdmCanBoard.PeriodMs} ms"));
            foreach (var g in cb.Outputs.GroupBy(o => o.Id).OrderBy(g => g.Key))
            {
                var role = g.First().Role;
                var sender = boards.FirstOrDefault(b => ReferenceEquals(b.Device, PdmView.Build(boards.Select(x => x.Device)).Boards.First(q => q.Role == role).Device))?.Node ?? role;
                msgs.Add(new Message(g.Key, 0, Unique($"{node}_Cmd_{sender}"), sender,
                    g.OrderBy(o => o.Number).Select(o => new Signal(Unique($"{node}_Output{o.Number}_Cmd"), o.StartBit, 8, false, 1, 0, "",
                        "1 = on; the CANBoard is set to follow this byte (one of its CAN inputs)")).ToList(),
                    g.Max(o => o.StartBit / 8) + 1,
                    $"{sender} sends this every {g.Min(o => o.Out.Interval)} ms: the PDM signals that drive the outputs of {node}"));
            }

            result.Add(new CanBoardDbc(node, cb.Name, cb.BaseId, msgs));
        }

        return result;
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
