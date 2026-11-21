using domain.Enums;

namespace domain.CustomPdm;

// custom-pdm (fwsafety, ADR-2026-11-20-fwsafety): words for the warnings our firmware sends once after boot (type
// Warning, src Init, firmware/core/safety.h SAFETY_MSG_*), added to the stock log line of a custom-pdm board.
public static class CustomPdmBootMessages
{
    public const int WdgReset = 1, BorReset = 2, BorLowVbat = 3, BorFailed = 4;
    public const int BorMinVbatX10 = 100; // SAFETY_BOR_MIN_VBAT 10.0 V

    // RM0390 option bytes BOR_LEV: 00 = level 3, 01 = level 2, 10 = level 1, 11 = off
    private static string BorLevel(int lev) => lev switch { 0 => "level 3", 1 => "level 2", 2 => "level 1", 3 => "off", _ => $"{lev}" };

    // null = not one of ours (the stock line stays as it is)
    public static string? Words(MessageType type, MessageSrc src, int code, int data1, int data2)
    {
        if (type != MessageType.Warning || src != MessageSrc.Init) return null;
        return code switch
        {
            WdgReset => "watchdog reset: the board restarted itself (outputs were off for the restart)",
            BorReset => "brown-out reset: the board's supply dipped below about 2.8 V and it restarted",
            BorLowVbat => FormattableString.Invariant($"BOR not set (low battery): {data1 / 10.0:0.0} V, needs {BorMinVbatX10 / 10} V; tried again at the next start"),
            BorFailed => $"BOR write failed: brown-out level reads {BorLevel(data1)} after the write; tried again at the next start",
            _ => null
        };
    }
}
