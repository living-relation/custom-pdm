// custom-pdm (route B phase B5): write the DBC files for the ECU into firmware/dbc, and (Dan, 2026-11-16: L1a, L2, L3a)
// the DUMMY TEST COPY car-CAN files into docs/car-can-dummy (Link receive JSON / .lcs, bus-load estimate; the ID table
// there is hand made, only read and clash-checked).
//   dotnet run --project ui/tools/DbcGen              write the files
//   dotnet run --project ui/tools/DbcGen -- --check   exit 1 if a committed file differs from the generator or IDs clash
// Same generator as the /pdm Export DBC button: ui/dingoConfig/domain/CustomPdm/DbcExport.cs.
using System.Text;
using application.Services;
using CarCanDummy;
using domain.CustomPdm;

var check = args.Contains("--check");
var dir = new DirectoryInfo(AppContext.BaseDirectory);
while (dir != null && !File.Exists(Path.Combine(dir.FullName, "automation.yml"))) dir = dir.Parent;
if (dir == null) { Console.Error.WriteLine("repo root (automation.yml) not found"); return 2; }

var mgr = new FwDeviceDefManager();
var bad = 0;

void Emit(string folder, string name, string text)
{
    var path = Path.Combine(dir.FullName, folder, name);
    if (check)
    {
        var same = File.Exists(path) && File.ReadAllText(path).Replace("\r\n", "\n") == text;
        Console.WriteLine($"{(same ? "same" : "DIFFERS")}  {folder}/{name}");
        if (!same) bad++;
    }
    else
    {
        File.WriteAllText(path, text, new UTF8Encoding(false));
        Console.WriteLine($"wrote {folder}/{name}");
    }
}

foreach (var (name, text) in DbcExport.RepoFiles(mgr.GetByDeviceType, mgr.GetDeviceCyclicSigsConfig))
    Emit("firmware/dbc", name, text);

var tablePath = Path.Combine(dir.FullName, DummySources.Folder, CanIdTableDummy.FileName);
var table = File.ReadAllText(tablePath).Replace("\r\n", "\n");
foreach (var problem in CanIdTableDummy.Check(CanIdTableDummy.Parse(table)))
{
    Console.WriteLine($"ID TABLE  {problem}");
    bad++;
}
var boards = DbcExport.RepoDbcBoards(mgr.GetByDeviceType, mgr.GetDeviceCyclicSigsConfig);
foreach (var (name, text) in DummyFiles.Generated(boards, table))
    Emit(DummySources.Folder, name, text);
return bad == 0 ? 0 : 1;
