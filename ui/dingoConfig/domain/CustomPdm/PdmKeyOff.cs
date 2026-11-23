using domain.Devices;
using domain.Devices.Functions;
using domain.Enums;

namespace domain.CustomPdm;

// configfix (drive cycle s5, 2026-11-23): auto sleep after the key off, with stock functions only, so the PDM does not
// drain the battery.
//
// Stock dingoFW core/sleep.cpp CheckEnterSleep: a board sleeps by itself when device.sleepEnabled is on, every output
// has been off for SLEEP_TIMEOUT (30 s, firmware/boards/custompdm_*/port.h), USB is not connected and no CAN frame has
// been received for SLEEP_TIMEOUT (comms/can.cpp stamps every received frame). The three boards send cyclic frames all
// the time, so each one always hears the other two and that alone never fires. The stock "mute CAN TX" input
// (device.muteCanTxInput, comms/can.cpp TX thread) closes the gap: on every board a timer goes on once the ignition
// has been off for MuteDelayMs and mutes that board's cyclic frames; when all three (and the car) are quiet, each
// sleeps 30 s later. A frame at key on (the ECU, the car) wakes them: CAN wake stays on (stock default, core/sleep.cpp
// EnterSleep arms CAN RX).
// Recipe per board: timer "OnDelay MuteDelayMs, input always on, reset = ignition" -> muteCanTxInput; sleepEnabled on.
// The ignition on a board without the wire: a dedicated CAN input on the wire board's msg 37 bit, the 'off' link
// recipe with its 1 s time-out (PdmLinks.MakeTermSlot), so a lost or muted board reads as key off. The conflict engine
// owns the timer and that CAN input as one system function, "auto sleep" (PdmValues.All); "Remove unused" keeps the
// CAN input (a timer reads it: PdmEngine.IsRead).
public static class PdmKeyOff
{
    public const int MuteDelayMs = 10000;   // > the ECU's own hold after key off and the starter's 5 s cluster off-delay
    public const string IgnitionTag = "ignition (key off / auto sleep)";

    private static int FreeTimer(FwDevice d) => d.Timers.FindIndex(t => !t.Enabled && t.Input == 0 && t.ResetInput == 0);

    // the ignition (digital input `input` of the PDM) as a variable on board q: the input itself on its own board,
    // else this recipe's CAN input on the wire board's msg 37 (made when missing). -1 + why when q is full.
    public static int IgnitionVar(PdmView v, PdmBoard q, int input, out string? why)
    {
        why = null;
        var row = v.Inputs.FirstOrDefault(r => r.Number == input && r.Digital != null);
        if (row == null) { why = $"IN{input} is not a digital input of this PDM."; return -1; }
        var d = q.Device;
        if (row.Board == q.Role) return PdmFactoryDefaults.VarOf(d, row.Digital!);
        var p = v.Boards.Single(b => b.Role == row.Board);
        var id = p.Device.BaseId + PdmLinks.StatusOffset;
        for (var s = 0; s < d.CanInputs.Count; s++)
            if (d.CanInputs[s] is { Enabled: true, TimeoutEnabled: true, BitLength: 1, Operator: Operator.Equal, Operand: 1.0 } c
                && c.Id == id && c.StartBit == row.BoardInput - 1 && c.Name.StartsWith(IgnitionTag))
                return PdmFactoryDefaults.CanInState(d, s);
        var free = Enumerable.Range(0, d.CanInputs.Count).FirstOrDefault(s => PdmLinks.IsFreeSlot(q, s), -1);
        if (free < 0) { why = $"{q.Role} has no free CAN input for the ignition from {row.Board} IN{row.BoardInput}."; return -1; }
        PdmLinks.MakeTermSlot(v, q, free, row, IgnitionTag);
        return PdmFactoryDefaults.CanInState(d, free);
    }

    // Auto sleep on every board (recipe above). Null = set on the PC (Write All sends it); else why not (nothing changed).
    public static string? SetAutoSleep(PdmView v, int ignitionInput, int muteDelayMs = MuteDelayMs)
    {
        if (muteDelayMs is < 1000 or > 600000) return "The key-off delay must be 1 to 600 s.";
        var restore = PdmSnapshot.Take(v.Boards.Select(b => b.Device).ToList());
        foreach (var q in v.Boards)
        {
            var d = q.Device;
            var ign = IgnitionVar(v, q, ignitionInput, out var why);
            var t = FreeTimer(d);
            if (ign < 0 || t < 0)
            {
                restore.Restore();
                return why ?? $"{q.Role} has no free timer for the key-off delay.";
            }
            var tm = d.Timers[t];
            (tm.Name, tm.Enabled, tm.Input, tm.ResetInput, tm.Mode, tm.Time) =
                ($"Key off {muteDelayMs / 1000.0:0.#} s: mute CAN TX (auto sleep)", true, PdmTriggers.AlwaysOnVar, ign, TimerMode.OnDelay, muteDelayMs);
            d.MuteCanTxInput = PdmFactoryDefaults.VarOf(d, tm);
            d.SleepEnabled = true;
        }
        return null;
    }

    // the auto-sleep timer of a board (the one muteCanTxInput reads), or null
    public static DeviceTimer? SleepTimer(FwDevice d) =>
        d.MuteCanTxInput == 0 ? null : d.Timers.FirstOrDefault(t => PdmFactoryDefaults.VarOf(d, t) == d.MuteCanTxInput);
}
