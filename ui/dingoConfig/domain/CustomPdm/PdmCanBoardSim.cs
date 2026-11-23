namespace domain.CustomPdm;

// custom-pdm canboard: the simulated CANBoard of the /pdm Simulator panel. The bridge (ui/tests/sim_bridge.py, class
// CanBoard) holds a stand-in that sends the CANBoard's three status frames (firmware/boards/canboard_v2/msg.cpp
// TxMsg0-2) every 100 ms and lets its 4 outputs follow the PDM's command frames as a real one would be set to
// (PdmCanBoard.SetupSteps). These are its play lines ("CB <base hex> ...", inputs and outputs count from 0) and the
// decoding of what it reports: the panel shows the frames on the bus, it keeps no state of its own.
public record PdmCanBoardLive(bool Alive, bool[] Switches, int[] Mv, int[] Rotary, bool[] Outputs, int Heartbeat);

public static class PdmCanBoardSim
{
    public const int StaleMs = 350;   // 3 periods + margin without a state frame = not on the bus

    public static string AddLine(int baseId) => $"CB {baseId:X} ADD";
    public static string RemoveLine(int baseId) => $"CB {baseId:X} DEL";
    public static string LinkLine(int baseId, bool on) => $"CB {baseId:X} LINK {(on ? "on" : "off")}";

    public static string? SwitchLine(int baseId, int n, bool on) =>
        n is >= 1 and <= PdmCanBoard.Switches ? $"CB {baseId:X} SW {n - 1} {(on ? 1 : 0)}" : null;

    public static string? AnalogLine(int baseId, int n, int mv) =>
        n is >= 1 and <= PdmCanBoard.Analogs && mv is >= 0 and <= PdmCanBoard.MaxAnalogMv ? $"CB {baseId:X} AN {n - 1} {mv}" : null;

    public static string? RotaryLine(int baseId, int n, int pos) =>
        n is >= 1 and <= PdmCanBoard.Rotaries && pos is >= 0 and <= PdmCanBoard.MaxRotary ? $"CB {baseId:X} ROT {n - 1} {pos}" : null;

    // its 4 outputs as the CANBoard card says to set them: output n follows byte n - 1 of the PDM's command frame
    public static IReadOnlyList<string> OutputLines(PdmCanBoardInfo cb) =>
        Enumerable.Range(1, PdmCanBoard.Outs).Select(n => cb.Outputs.FirstOrDefault(o => o.Number == n) is { } o
            ? $"CB {cb.BaseId:X} OUT {n - 1} {o.Id:X} {o.StartBit} {cb.TimeoutMs}"
            : $"CB {cb.BaseId:X} OUT {n - 1} off").ToList();

    // the status frames of one CANBoard: analog 1-4, analog 5, state
    public static int[] WatchIds(int baseId) =>
        [baseId + 2 + PdmCanBoard.AnalogMsg, baseId + 2 + PdmCanBoard.Analog5Msg, baseId + 2 + PdmCanBoard.StateMsg];

    private static int U16(byte[]? d, int at) => d != null && d.Length >= at + 2 ? d[at] | d[at + 1] << 8 : 0;
    private static int B(byte[]? d, int at) => d != null && d.Length > at ? d[at] : 0;

    public static PdmCanBoardLive Decode(byte[]? msg0, byte[]? msg1, byte[]? msg2, bool alive) => new(
        alive && msg2 != null,
        Enumerable.Range(0, PdmCanBoard.Switches).Select(i => (B(msg2, 4) >> i & 1) != 0).ToArray(),
        [U16(msg0, 0), U16(msg0, 2), U16(msg0, 4), U16(msg0, 6), U16(msg1, 0)],
        [B(msg2, 0) & 15, B(msg2, 0) >> 4, B(msg2, 1) & 15, B(msg2, 1) >> 4, B(msg2, 2) & 15],
        Enumerable.Range(0, PdmCanBoard.Outs).Select(i => (B(msg2, 6) >> i & 1) != 0).ToArray(),
        B(msg2, 7));
}
