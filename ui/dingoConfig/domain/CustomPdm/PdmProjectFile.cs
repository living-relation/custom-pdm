using System.Security.Cryptography;
using System.Text;
using domain.Devices;
using domain.Enums;
using domain.Interfaces;

namespace domain.CustomPdm;

// custom-pdm uipolish (2026-11-21, supersedes the B3 "File > Open counts as not read"): a project file saved by this
// app loads as WRITABLE, so a saved setup can be put onto a blank or another PDM without a Read All first (that read
// replaced the file's settings with the board's; only the names came back).
// What makes that safe: the file says, per board, whether its values were a complete set when it was saved
// (CustomPdmSettings.CompleteSettings): read from a board, a New PDM, the starter, or loaded from such a file.
// A hand-added board that was never read holds stock dingoPDM PC defaults (500K, A2 on A1's settings): it is saved as
// "not complete" and stays blocked after loading, as before (CustomPdmGuards).
// A file from before this marker (no value in the file): complete when the board is on 1000K (our factory bit rate;
// the stock PC default of a never-read board is 500K) and its 0x7F00 block is valid.
// With a PDM on the bus a loaded board is not read over: /pdm asks ONE question for the PDM (PdmAutoRead: a loaded
// board counts as "the PC holds settings that are not on the board").
public static class PdmProjectFile
{
    // the PC values of this board are a complete, known-good set
    public static bool Complete(FwDevice d) =>
        d.FullReadDone || d.CustomPdm is { FactoryNew: true } or { FromFile: true };

    // just before the project is written to a file
    public static void MarkForSave(IEnumerable<IDevice> devices)
    {
        foreach (var d in devices.OfType<FwDevice>())
            if (d.CustomPdm is { } c)
            {
                c.CompleteSettings = Complete(d);
                c.CriticalSeal = PdmIntegrity.HasUnconfirmed(d) ? null : Seal(d); // uiguide
            }
    }

    // uiguide (PdmIntegrity rule 4): a short hash of the base ID and the critical values, saved with the file
    public static string Seal(FwDevice d) =>
        Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(
            $"{d.BaseId}|{(int)d.BitRate}|{d.CustomPdm!.TempCrit}|{d.CustomPdm.CritExemptMask}")))[..16];

    // just after a project file was read. Returns the boards that are writable.
    public static IReadOnlyList<FwDevice> MarkLoaded(IEnumerable<IDevice> devices)
    {
        var writable = new List<FwDevice>();
        foreach (var d in devices.OfType<FwDevice>())
        {
            if (d.CustomPdm is not { } c) continue;
            c.FromFile = c.CompleteSettings ?? (d.BitRate == CanBitRate.BitRate1000K && c.IsValid());
            if (c.FromFile) writable.Add(d);
        }

        // uiguide: critical values that differ from our factory ones wait for Unlock (PdmIntegrity rule 4)
        PdmIntegrity.MarkFileCritical(PdmView.Build(devices.OfType<FwDevice>()));
        return writable;
    }
}
