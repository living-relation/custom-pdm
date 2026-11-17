using System.Text.Json.Serialization;
using domain.Models;

namespace domain.CustomPdm;

// custom-pdm (not upstream): the pro-PDM parity settings of our firmware's PRO_FEATURES option (docs/feature-parity.md
// P1 P2 T1), device types 14 / 15 only. Order, types, ranges and defaults = firmware/core/param_defs.h
// OUTPUT_EXT_PARAMS (block 0x7D00 + output) and TABLE_PARAMS (block 0x7E00 + table). P3 (master retry, 0x7F00 sub 6)
// is a plain value in CustomPdmSettings.

// P1 overcurrent trip time + P2 open-load (undercurrent) flag of one output: block 0x7D00 + output, sub 0-2
public class OutputProtection
{
    public const int TripTimeMax = 10000;        // ms, sub 0 (UInt16)
    public const double MinCurrentMax = 100.0;   // A, sub 1 (Float)
    public const int MinCurrentTimeMax = 60000;  // ms, sub 2 (UInt16)
    // firmware DEFAULT_OUT_TRIP_TIME (50 ms: below the ISO 8820-3 blade-fuse minimum opening time at 350 %),
    // min current 0 = off, DEFAULT_OUT_MIN_CURRENT_TIME 500 ms
    public const int DefaultTripTime = 50, DefaultMinCurrentTime = 500;
    public const double DefaultMinCurrent = 0.0;

    [JsonPropertyName("tripTime")] public int TripTime { get; set; } = DefaultTripTime;
    [JsonPropertyName("minCurrent")] public double MinCurrent { get; set; } = DefaultMinCurrent;
    [JsonPropertyName("minCurrentTime")] public int MinCurrentTime { get; set; } = DefaultMinCurrentTime;

    public bool IsValid() => TripTime is >= 0 and <= TripTimeMax && MinCurrent is >= 0 and <= MinCurrentMax &&
                             MinCurrentTime is >= 0 and <= MinCurrentTimeMax;

    public IEnumerable<DeviceParameter> GetParams(string parentName, int output)
    {
        var index = CustomPdmSettings.OutputExtBaseIndex + output;
        var n = $"customPdm.output[{output + 1}]";
        yield return P.Int(parentName, $"{n}.tripTime", index, 0, () => TripTime, v => TripTime = v, DefaultTripTime);
        yield return P.Double(parentName, $"{n}.minCurrent", index, 1, () => MinCurrent, v => MinCurrent = v, DefaultMinCurrent);
        yield return P.Int(parentName, $"{n}.minCurrentTime", index, 2, () => MinCurrentTime, v => MinCurrentTime = v, DefaultMinCurrentTime);
    }
}

// T1 1D lookup table: block 0x7E00 + table, sub 0 enable, 1 input var, 2 points, 3-10 x[0..7], 11-18 y[0..7]
public class LookupTable
{
    public const int MaxPoints = 8;              // firmware TABLE_MAX_POINTS
    public const double ValueLimit = 1e9;        // x / y range, as the firmware's other floats

    [JsonPropertyName("enabled")] public bool Enabled { get; set; }
    [JsonPropertyName("input")] public int Input { get; set; }
    [JsonPropertyName("points")] public int Points { get; set; }      // 0 = empty (factory)
    [JsonPropertyName("x")] public List<double> X { get; set; } = NewPoints();
    [JsonPropertyName("y")] public List<double> Y { get; set; } = NewPoints();

    private static List<double> NewPoints() => Enumerable.Repeat(0.0, MaxPoints).ToList();

    // project files of another size: pad / cut to 8 points
    public void Normalize()
    {
        X = X.Concat(NewPoints()).Take(MaxPoints).ToList();
        Y = Y.Concat(NewPoints()).Take(MaxPoints).ToList();
    }

    // What the firmware uses (functions/lookup_table.h IsValid): 2-8 points, x rising strictly over them.
    // Anything else is accepted by the firmware but gives 0 (the factory "empty" table, an unsorted one).
    public bool IsUsable => Points is >= 2 and <= MaxPoints && Enumerable.Range(1, Points - 1).All(i => X[i] > X[i - 1]);

    // Shown next to an enabled table that the firmware would not use
    public string? Warning => !Enabled || IsUsable ? null
        : Points < 2 ? "Needs 2 to 8 points: this table outputs 0."
        : "X must rise from point to point: this table outputs 0.";

    // Range check only (what the firmware refuses); an unusable but in-range table is allowed (it outputs 0)
    public bool IsValid(int varMapSize) => Input >= 0 && (varMapSize == 0 || Input < varMapSize) &&
                                           Points is >= 0 and <= MaxPoints && X.Count == MaxPoints && Y.Count == MaxPoints &&
                                           X.Concat(Y).All(v => Math.Abs(v) <= ValueLimit);

    // Firmware Update(): linear between points, held at the end values outside the x range, 0 when not used
    public double Evaluate(double x)
    {
        if (!Enabled || !IsUsable) return 0;
        if (x <= X[0]) return Y[0];
        for (var i = 1; i < Points; i++)
            if (x < X[i]) return Y[i - 1] + (x - X[i - 1]) * (Y[i] - Y[i - 1]) / (X[i] - X[i - 1]);
        return Y[Points - 1];
    }

    public IEnumerable<DeviceParameter> GetParams(string parentName, int table)
    {
        var index = CustomPdmSettings.TableBaseIndex + table;
        var n = $"customPdm.table[{table + 1}]";
        yield return new DeviceParameter
        {
            ParentName = parentName, Name = $"{n}.enabled", Index = index, SubIndex = 0,
            GetValue = () => Enabled, SetValue = v => Enabled = Convert.ToBoolean(v), ValueType = typeof(bool), DefaultValue = false
        };
        yield return P.Int(parentName, $"{n}.input", index, 1, () => Input, v => Input = v, 0);
        yield return P.Int(parentName, $"{n}.points", index, 2, () => Points, v => Points = v, 0);
        for (var i = 0; i < MaxPoints; i++)
        {
            var k = i;
            yield return P.Double(parentName, $"{n}.x[{k + 1}]", index, 3 + k, () => X[k], v => X[k] = v, 0.0);
        }
        for (var i = 0; i < MaxPoints; i++)
        {
            var k = i;
            yield return P.Double(parentName, $"{n}.y[{k + 1}]", index, 11 + k, () => Y[k], v => Y[k] = v, 0.0);
        }
    }
}

internal static class P
{
    public static DeviceParameter Int(string parent, string name, int index, int sub, Func<int> get, Action<int> set, int def) => new()
    {
        ParentName = parent, Name = name, Index = index, SubIndex = sub,
        GetValue = () => get(), SetValue = v => set(Convert.ToInt32(v)), ValueType = typeof(int), DefaultValue = def
    };

    public static DeviceParameter Double(string parent, string name, int index, int sub, Func<double> get, Action<double> set, double def) => new()
    {
        ParentName = parent, Name = name, Index = index, SubIndex = sub,
        GetValue = () => get(), SetValue = v => set(Convert.ToDouble(v)), ValueType = typeof(double), DefaultValue = def
    };
}
