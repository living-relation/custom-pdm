using System.Text.Json;
using System.Text.RegularExpressions;
using System.Xml.Linq;
using application.Services;
using CarCanDummy;
using domain.CustomPdm;
using domain.Models;
using Xunit;
using Xunit.Abstractions;

namespace CustomPdm.Tests;

using static CustomPdm.Tests.CarCanDummyTests;

// Dan, 2026-11-16 (L1a): Link receive files docs/car-can-dummy/link_pdm_receive.dummy.json / .lcs (DUMMY TEST COPIES).
public class LinkDummyTests
{
    [Fact]
    public void RepoDummyFilesEqualGenerator()
    {
        foreach (var (name, text) in DummyFiles.Generated(Boards(), Table()))
        {
            var path = Path.Combine(DummyDir, name);
            Assert.True(File.Exists(path), $"{name} missing: run dotnet run --project ui/tools/DbcGen");
            Assert.True(Read(path) == text, $"docs/car-can-dummy/{name} differs from the generator: run dotnet run --project ui/tools/DbcGen");
        }
    }

    // ---------------- L1a: Link receive files ----------------

    [Fact]
    public void LinkChannelsChosen()
    {
        var ch = LinkPdmDummy.Channels(Boards());
        Assert.Equal(15, ch.Select(c => c.FrameId).Distinct().Count());       // msgs 0, 1, 2, 3, 37 of 3 boards
        Assert.Equal(28 + 28 + 31, ch.Count);                                // A: 2 + 8 + 8 + 3 + 7, B: ... + 10
        Assert.Equal(ch.Count, ch.Select(c => c.Name).Distinct().Count());
        for (var n = 1; n <= 24; n++)
        {
            Assert.Single(ch, c => c.Name == $"PDM_Out{n}_Current");
            Assert.Single(ch, c => c.Name == $"PDM_Out{n}_State");
            Assert.Single(ch, c => c.Name == $"PDM_In{n}_State" && c.MsgNumber == 37);
        }
        foreach (var b in new[] { "A1", "A2", "B" })
        foreach (var s in new[] { "DeviceState", "BoardTemp", "ThermalOverWarn", "ThermalCritSoon", "ThermalCritical" })
            Assert.Single(ch, c => c.Name == $"{b}_{s}");
        Assert.All(ch, c => Assert.Matches("^[A-Za-z_][A-Za-z0-9_]*$", c.Name));
    }

    // The committed files and the generator output both pass the parity rules
    [Fact]
    public void LinkDummyFilesAgree()
    {
        var dbc = PdmDbc();
        var gen = DummyFiles.Generated(Boards(), Table()).ToDictionary(f => f.FileName, f => f.Text);
        foreach (var (json, lcs) in new[]
                 {
                     (gen[LinkPdmDummy.JsonFile], gen[LinkPdmDummy.LcsFile]),
                     (Read(Path.Combine(DummyDir, LinkPdmDummy.JsonFile)), Read(Path.Combine(DummyDir, LinkPdmDummy.LcsFile)))
                 })
        {
            var errors = LinkParity(json, lcs, dbc);
            Assert.True(errors.Count == 0, string.Join("\n", errors));
        }
    }

    [Fact]
    public void LinkParityCatchesAWrongScaleForm()
    {
        var gen = DummyFiles.Generated(Boards(), Table()).ToDictionary(f => f.FileName, f => f.Text);
        // BoardTemp written in ENCODE form in the .lcs (10 instead of 0.1): the st185 mistake fixed in its .lcs v1.1
        var lcs = Regex.Replace(gen[LinkPdmDummy.LcsFile], @"(Name=""A1_BoardTemp""[^>]*Scale="")0\.1""", "${1}10\"");
        Assert.NotEqual(gen[LinkPdmDummy.LcsFile], lcs);
        Assert.Contains(LinkParity(gen[LinkPdmDummy.JsonFile], lcs, PdmDbc()), e => e.Contains("A1_BoardTemp") && e.Contains("Scale"));
    }

    // Re-implements (read only, nothing copied or run) the rules of st185 bench/check_parity.py @ c2ddf1ab that apply to
    // ECU receive config: load_json_contract (JSON ENCODE form, decode = scale 1 / s, offset -o / s); check_lcs and
    // check_sb_rx (the same fields at the same StartBit / Length in the JSON and the .lcs, names equal, Signed equal,
    // Scale / Offset equal after the conversion, receive Timeout equal to the JSON timeout_ms with timeout value 0;
    // bit N of byte B = StartBit B * 8 + N). Changed for the PDM: ByteOrder must be LittleEndian (st185 checks BigEndian;
    // the PDM sends Intel order). Added: every field equals its signal in firmware/dbc/custompdm_PDM.dbc, fields of one
    // frame do not overlap and stay inside 8 bytes, every receive channel is on CANModule 1.
    internal static List<string> LinkParity(string jsonText, string lcsText, List<DbcSignal> dbc)
    {
        var err = new List<string>();
        var j = JsonDocument.Parse(jsonText).RootElement;
        if (j.GetProperty("byte_order").GetString() != "LittleEndian") err.Add("json byte_order is not LittleEndian");
        if (j.GetProperty("scale_convention").GetString() != "encode: raw = value * scale + offset") err.Add("json scale_convention");
        var rx = j.GetProperty("pdm_to_ecu");
        if (!rx.GetProperty("ecu_receives").GetBoolean()) err.Add("json ecu_receives is not true");
        var timeout = rx.GetProperty("timeout_ms").GetInt32();
        if (rx.GetProperty("timeout_value").GetInt32() != 0) err.Add("json timeout_value is not 0");

        var want = new Dictionary<(int Id, int Start, int Len), (string Name, bool Signed, double Scale, double Offset, string Dbc)>();
        foreach (var f in rx.GetProperty("frames").EnumerateArray())
        {
            var id = Convert.ToInt32(f.GetProperty("id").GetString(), 16);
            if (f.GetProperty("dlc").GetInt32() != 8) err.Add($"json 0x{id:X3} dlc is not 8");
            foreach (var c in f.GetProperty("channels").EnumerateArray())
            {
                var b = c.GetProperty("byte").GetInt32();
                int start, len;
                if (c.TryGetProperty("length", out var l)) (start, len) = (b * 8, l.GetInt32() * 8);
                else
                {
                    (start, len) = (b * 8 + c.GetProperty("bit").GetInt32(), c.GetProperty("bits").GetInt32());
                    if (start % 8 + len > 8) err.Add($"json 0x{id:X3} {c.GetProperty("name")}: bit field crosses a byte");
                }
                var sc = c.GetProperty("scale").GetDouble();
                var of = c.GetProperty("offset").GetDouble();
                var signed = c.TryGetProperty("signed", out var sg) && sg.GetBoolean();
                if (!want.TryAdd((id, start, len), (c.GetProperty("name").GetString()!, signed, 1.0 / sc, -of / sc,
                        c.GetProperty("dbc_signal").GetString()!)))
                    err.Add($"json 0x{id:X3} two fields at bit {start}");
            }
        }

        var have = new Dictionary<(int Id, int Start, int Len), (string Name, bool Signed, double Scale, double Offset)>();
        var x = XDocument.Parse(lcsText);
        foreach (var ch in x.Descendants("Channel"))
        {
            var id = Convert.ToInt32(ch.Attribute("ID")!.Value, 16);
            var where = $".lcs 0x{id:X3}";
            if (ch.Attribute("Direction")?.Value != "Receive") err.Add($"{where} is not Direction=\"Receive\"");
            if (ch.Parent?.Name != "CANModule" || ch.Parent.Attribute("Index")?.Value != "1") err.Add($"{where} is not on CANModule 1");
            if (ch.Attribute("Timeout")?.Value != timeout.ToString()) err.Add($"{where} Timeout {ch.Attribute("Timeout")?.Value}, json {timeout}");
            if (ch.Attribute("DLC")?.Value != "8") err.Add($"{where} DLC is not 8");
            foreach (var p in ch.Elements("Parameter"))
            {
                var key = (id, int.Parse(p.Attribute("StartBit")!.Value), int.Parse(p.Attribute("Length")!.Value));
                if (p.Attribute("ByteOrder")?.Value != "LittleEndian") err.Add($"{where} {p.Attribute("Name")?.Value} ByteOrder");
                if (!have.TryAdd(key, (p.Attribute("Name")!.Value, p.Attribute("Signed")?.Value == "true",
                        double.Parse(p.Attribute("Scale")!.Value, System.Globalization.CultureInfo.InvariantCulture),
                        double.Parse(p.Attribute("Offset")!.Value, System.Globalization.CultureInfo.InvariantCulture))))
                    err.Add($"{where} two parameters at bit {key.Item2}");
            }
        }

        static bool Close(double a, double b) => Math.Abs(a - b) <= 1e-9 * Math.Max(1, Math.Abs(b));
        if (!want.Keys.ToHashSet().SetEquals(have.Keys))
            err.Add("fields differ: json " + string.Join(" ", want.Keys.Except(have.Keys)) + " / .lcs " + string.Join(" ", have.Keys.Except(want.Keys)));
        foreach (var (k, w) in want)
        {
            var where = $"0x{k.Id:X3} bit {k.Start} {w.Name}";
            if (have.TryGetValue(k, out var h))
            {
                if (h.Name != w.Name) err.Add($"{where}: .lcs name {h.Name}");
                if (h.Signed != w.Signed) err.Add($"{where}: .lcs Signed {h.Signed}, json {w.Signed}");
                if (!Close(h.Scale, w.Scale) || !Close(h.Offset, w.Offset))
                    err.Add($"{where}: .lcs Scale/Offset {h.Scale}/{h.Offset}, json decodes to {w.Scale}/{w.Offset}");
            }
            var s = dbc.SingleOrDefault(p => p.Id == k.Id && p.Name == w.Dbc);
            if (s == null) { err.Add($"{where}: DBC signal {w.Dbc} not in message 0x{k.Id:X3}"); continue; }
            if ((s.StartBit, s.Length, s.IsSigned) != (k.Start, k.Len, w.Signed) || !Close(s.Factor, w.Scale) || !Close(s.Offset, w.Offset))
                err.Add($"{where}: DBC {s.Name} is {s.StartBit}|{s.Length} signed {s.IsSigned} ({s.Factor},{s.Offset})");
            if (s.ByteOrder != domain.Enums.ByteOrder.LittleEndian) err.Add($"{where}: DBC signal is not Intel order");
        }
        foreach (var g in want.Keys.GroupBy(k => k.Id))
        {
            var bits = new bool[64];
            foreach (var (_, start, len) in g)
            for (var i = start; i < start + len; i++)
            {
                if (i >= 64 || bits[i]) { err.Add($"0x{g.Key:X3}: fields overlap or pass byte 7 at bit {i}"); break; }
                bits[i] = true;
            }
        }
        return err;
    }
}
