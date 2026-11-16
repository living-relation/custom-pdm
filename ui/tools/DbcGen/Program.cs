// custom-pdm (route B phase B5): write the DBC files for the ECU into firmware/dbc.
//   dotnet run --project ui/tools/DbcGen              write the files
//   dotnet run --project ui/tools/DbcGen -- --check   exit 1 if a committed file differs from the generator
// Same generator as the /pdm Export DBC button: ui/dingoConfig/domain/CustomPdm/DbcExport.cs.
using System.Text;
using application.Services;
using domain.CustomPdm;

var check = args.Contains("--check");
var dir = new DirectoryInfo(AppContext.BaseDirectory);
while (dir != null && !File.Exists(Path.Combine(dir.FullName, "automation.yml"))) dir = dir.Parent;
if (dir == null) { Console.Error.WriteLine("repo root (automation.yml) not found"); return 2; }
var outDir = Path.Combine(dir.FullName, "firmware", "dbc");

var mgr = new FwDeviceDefManager();
var bad = 0;
foreach (var (name, text) in DbcExport.RepoFiles(mgr.GetByDeviceType, mgr.GetDeviceCyclicSigsConfig))
{
    var path = Path.Combine(outDir, name);
    if (check)
    {
        var same = File.Exists(path) && File.ReadAllText(path).Replace("\r\n", "\n") == text;
        Console.WriteLine($"{(same ? "same" : "DIFFERS")}  firmware/dbc/{name}");
        if (!same) bad++;
    }
    else
    {
        File.WriteAllText(path, text, new UTF8Encoding(false));
        Console.WriteLine($"wrote firmware/dbc/{name}");
    }
}
return bad == 0 ? 0 : 1;
