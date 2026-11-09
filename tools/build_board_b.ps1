# Rebuild board B (dingoPDM-Max based) schematic from the unmodified baseline, then check it.
#   powershell -NoProfile -ExecutionPolicy Bypass -File tools\build_board_b.ps1
# Steps: restore baseline files -> tools\sch_board_b.py -> netlist checks (tools\check_board_b.py) -> ERC summary.
$ErrorActionPreference = "Stop"
$Repo = Split-Path $PSScriptRoot -Parent
$B = Join-Path $Repo "hardware\board-b-max"
$Baseline = "fe19c28"                       # "Board B: unmodified dingoPDM-Max baseline"
$Cli = "$env:LOCALAPPDATA\Programs\KiCad\10.0\bin\kicad-cli.exe"
$Out = Join-Path $env:TEMP "board-b-build"
New-Item -ItemType Directory -Force $Out | Out-Null

Push-Location $Repo
try {
    git checkout $Baseline -- hardware/board-b-max
    git reset -q -- hardware/board-b-max
    foreach ($f in "BTS7004_1EPP.kicad_sch", "HighCurrentDrivers2.kicad_sch") {
        $p = Join-Path $B $f
        if (Test-Path $p) { Remove-Item $p }
    }
    Push-Location $B
    try {
        python (Join-Path $Repo "tools\sch_board_b.py")
        if ($LASTEXITCODE) { throw "sch_board_b.py failed" }
    } finally { Pop-Location }

    & $Cli sch export netlist (Join-Path $B "dingoPDM-Max.kicad_sch") -o "$Out\board-b.net" | Out-Null
    python (Join-Path $Repo "tools\check_board_b.py") "$Out\board-b.net"
    if ($LASTEXITCODE) { throw "netlist check failed" }
    & $Cli sch erc (Join-Path $B "dingoPDM-Max.kicad_sch") --format json -o "$Out\erc.json" | Out-Null
    python -c "import json,collections;d=json.load(open(r'$Out\erc.json'));c=collections.Counter((v['severity'],v['type']) for s in d['sheets'] for v in s['violations']);print('ERC', sum(c.values()));[print(' ',k,n) for k,n in sorted(c.items())]"
} finally { Pop-Location }
