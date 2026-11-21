using System.Globalization;
using domain.Devices.Functions;
using domain.Enums;

namespace domain.CustomPdm;

// custom-pdm uipolish (2026-11-21): the /pdm "Simulator" panel. It is shown only when the CAN adapter is the
// simulator bridge (ui/tests/sim_bridge.py --slcan-tcp), and it sends the bridge's own play lines (IN, LOAD, TEMP, AN,
// RESTART, TXP: ui/README.md, sim_bridge.py play_ctl), so the PDM can be played with without editing a ctl file.
// Transport: text lines in band on the SLCAN TCP connection, marked with "!" (a SLCAN reader skips every line that is
// not a frame). The app asks "!HELLO"; only the bridge answers "!SIM custom-pdm". A play line "!LOAD B 4 20" is
// answered "!OK LOAD B 4 20" or "!ERR ...". The ctl file of the bridge works as before.

// an adapter that can pass such lines (infrastructure SlcanAdapter)
public interface IPdmSimLink
{
    event Action<string>? SimLine;     // a line from the other end that starts with "!"
    bool SendSimLine(string line);     // false = not sent
}

// One number the setup reads from a CAN frame that no PDM board sends: an ECU command byte, a CAN value, a keypad button
public record PdmSimField(string Key, string Name, int Id, int StartBit, int Length, ByteOrder Order, bool Signed,
    double Factor, double Offset);

public static class PdmSim
{
    public const char Mark = '!';
    public const string Hello = "HELLO", HelloReply = "SIM custom-pdm";
    public const string BridgeAdapter = "SLCAN TCP";
    public static readonly string[] Wires = ["open", "gnd", "12v"];
    public const double MaxAmps = 200, MaxVolts = 5;

    private static string N(double v) => v.ToString("0.###", CultureInfo.InvariantCulture);

    // null = not a thing of this PDM (nothing is sent)
    public static string? InputLine(PdmView v, int number, string wire) =>
        v.Inputs.FirstOrDefault(r => r.Number == number && r.Digital != null) is { } row && Wires.Contains(wire)
            ? $"IN {row.Board} {row.BoardInput - 1} {wire}" : null;

    public static string? LoadLine(PdmView v, int output, double amps) =>
        v.Outputs.FirstOrDefault(r => r.Number == output) is { } row && amps is >= 0 and <= MaxAmps
            ? $"LOAD {row.Board} {row.BoardOutput - 1} {N(amps)}" : null;

    public static string? TempLine(PdmView v, string role, double c) =>
        v.Boards.Any(b => b.Role == role) && c is >= -40 and <= 150 ? $"TEMP {role} {N(c)}" : null;

    public static string? AnalogLine(PdmView v, string role, double volts) =>
        v.Boards.Any(b => b.Role == role) && volts is >= 0 and <= MaxVolts ? $"AN {role} {N(volts)}" : null;

    public static string? RestartLine(PdmView v) => v.Any ? "RESTART " + string.Join(' ', v.Boards.Select(b => b.Role)) : null;

    public static string FrameLine(int id, byte[] data, int periodMs) => $"TXP {id:X} {Convert.ToHexString(data)} {periodMs}";
    public static string StopLine(int id) => $"TXP {id:X} off";

    // What the setup listens to from outside the PDM: the ECU command bytes of the outputs (PdmEcu) and every CAN
    // input set by hand or as a value (CAN values, keypad buttons). Frames of the PDM's own boards are left out.
    public static IReadOnlyList<PdmSimField> Fields(PdmView v)
    {
        var list = new List<PdmSimField>();
        void Add(PdmSimField f)
        {
            if (list.All(x => x.Key != f.Key)) list.Add(f);
        }

        foreach (var l in PdmEcu.All(v))
            Add(new PdmSimField($"{l.Id:X}:{l.Byte * 8}:8", $"{PdmFaults.OutputLabel(l.Out)}: ECU command (1 = on)", l.Id, l.Byte * 8, 8,
                ByteOrder.LittleEndian, false, 1, 0));
        var m = PdmModel.Build(v);
        foreach (var b in v.Boards)
        foreach (var c in b.Device.CanInputs.Where(c => c.Enabled && !c.Ide && c.Id > 0 && !PdmEcu.IsPdmId(v, c.Id)))
        {
            if (m.ResOf(c) is not { } r || m.ClaimOf(r).Kind is not (PdmClaimKind.Hand or PdmClaimKind.Value)) continue;
            // a byte-aligned 8-bit field is the same bits in both byte orders: one key, so an ECU command is not listed twice
            var aligned = c.BitLength == 8 && (c.ByteOrder == ByteOrder.BigEndian ? c.StartBit % 8 == 7 : c.StartBit % 8 == 0);
            var (start, order) = aligned ? (c.StartBit / 8 * 8, ByteOrder.LittleEndian) : (c.StartBit, c.ByteOrder);
            var key = aligned ? $"{c.Id:X}:{start}:8" : $"{c.Id:X}:{start}:{c.BitLength}:{order}";
            var name = string.IsNullOrWhiteSpace(c.Name) ? $"CAN input {c.Number}" : c.Name.Trim();
            Add(new PdmSimField(key, $"{name} (0x{c.Id:X3})", c.Id, start, c.BitLength, order, c.Signed,
                c.Factor == 0 ? 1 : c.Factor, c.Offset));
        }

        return list.OrderBy(f => f.Id).ThenBy(f => f.StartBit).ToList();
    }

    // the raw bits of a value as the board will read it: value = raw x factor + offset
    public static long Raw(PdmSimField f, double value)
    {
        var raw = (long)Math.Round((value - f.Offset) / f.Factor);
        var (lo, hi) = f.Signed ? (-(1L << (f.Length - 1)), (1L << (f.Length - 1)) - 1) : (0L, (1L << f.Length) - 1);
        return Math.Clamp(raw, lo, hi) & ((1L << f.Length) - 1);
    }

    // DBC bit numbering: Intel = start bit is the LSB, counting up; Motorola = start bit is the MSB, counting down
    // inside a byte and on into the next byte (the firmware's BigEndian start bit, firmware/utils/dbc.cpp)
    public static void Put(byte[] data, int startBit, int length, ByteOrder order, long raw)
    {
        var bit = startBit;
        for (var i = 0; i < length; i++)
        {
            if (bit < 0 || bit >= data.Length * 8) return;
            var one = order == ByteOrder.BigEndian ? (raw >> (length - 1 - i)) & 1 : (raw >> i) & 1;
            if (one != 0) data[bit / 8] |= (byte)(1 << (bit % 8));
            else data[bit / 8] &= (byte)~(1 << (bit % 8));
            bit = order == ByteOrder.BigEndian ? (bit % 8 == 0 ? bit + 15 : bit - 1) : bit + 1;
        }
    }

    // one 8-byte frame per ID with every field's value in it
    public static IReadOnlyDictionary<int, byte[]> Frames(IEnumerable<PdmSimField> fields, Func<PdmSimField, double> value)
    {
        var frames = new SortedDictionary<int, byte[]>();
        foreach (var f in fields)
        {
            if (!frames.TryGetValue(f.Id, out var data)) frames[f.Id] = data = new byte[8];
            Put(data, f.StartBit, f.Length, f.Order, Raw(f, value(f)));
        }

        return frames;
    }
}
