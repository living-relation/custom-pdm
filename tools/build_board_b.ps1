# Rebuild board B (dingoPDM-Max based) from the unmodified baseline, then check it.
#   powershell -NoProfile -ExecutionPolicy Bypass -File tools\build_board_b.ps1 [-SchOnly] [-NoRoute]
# Steps: restore baseline files -> tools\sch_board_b.py -> netlist checks (tools\check_board_b.py) -> ERC summary
#        -> tools\pcb_board_b.py (parts, outline, zones) -> tools\route_board_b.py (if present) -> DRC summary + renders.
param([switch]$SchOnly, [switch]$NoRoute)
$ErrorActionPreference = "Stop"
$Repo = Split-Path $PSScriptRoot -Parent
$B = Join-Path $Repo "hardware\board-b-max"
$Baseline = "fe19c28"                       # "Board B: unmodified dingoPDM-Max baseline"
$BaselineA = "542b3b9"                      # board A baseline: source of the BTS700x-1EPP channel layout (dingoPDM v7.5, MIT)
$Cli = "$env:LOCALAPPDATA\Programs\KiCad\10.0\bin\kicad-cli.exe"
$Py9 = "$env:LOCALAPPDATA\Programs\KiCad\9.0\bin\python.exe"
$Out = if ($env:BOARD_B_OUT) { $env:BOARD_B_OUT } else { Join-Path $env:TEMP "board-b-build" }
New-Item -ItemType Directory -Force $Out | Out-Null
$Pcb = Join-Path $B "dingoPDM-Max.kicad_pcb"

function Run-Py9 {
    # KiCad's python prints wx noise on stderr: keep stdout, fail on exit code only
    $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    $log = Join-Path $Out "py9.log"
    cmd /c "`"$Py9`" -u -X faulthandler $($args -join ' ') > `"$log`" 2>&1"
    $code = $LASTEXITCODE; $ErrorActionPreference = $old
    Get-Content $log | Where-Object { $_ -notmatch "image handler" -and $_.Trim() } | ForEach-Object { Write-Host $_ }
    if ($code) { throw "$($args[0]) failed" }
}

Push-Location $Repo
try {
    git checkout $Baseline -- hardware/board-b-max
    git reset -q -- hardware/board-b-max
    foreach ($f in "BTS7004_1EPP.kicad_sch", "HighCurrentDrivers2.kicad_sch", "board-b-refs.json") {
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
    if ($SchOnly) { return }

    cmd /c "git show ${BaselineA}:hardware/board-a/DingoPDM.kicad_pcb > `"$Out\board-a-baseline.kicad_pcb`""
    Run-Py9 (Join-Path $Repo "tools\pcb_board_b.py") $Pcb "$Out\board-b.net" "$Out\board-a-baseline.kicad_pcb" (Join-Path $B "board-b-refs.json")
    $route = Join-Path $Repo "tools\route_board_b.py"
    if ((Test-Path $route) -and -not $NoRoute) { Run-Py9 $route $Pcb "$Out\board-b.net" }

    $tidy = Join-Path $Repo "tools\tidy_board_b.py"
    if ((Test-Path $tidy) -and -not $NoRoute) { Run-Py9 $tidy $Pcb "$Out\board-b.net" (Join-Path $Repo "reference\dingoPDM-Max\dingoPDM-Max\dingoPDM-Max.kicad_pcb") }

    & $Cli pcb drc --schematic-parity --severity-all --format json -o "$Out\drc.json" $Pcb | Out-Null
    python -c "import json,collections;d=json.load(open(r'$Out\drc.json'));c=collections.Counter((v['severity'],v['type']) for v in d.get('violations',[]));print('DRC', sum(c.values()), '| unconnected', len(d.get('unconnected_items',[])), '| parity', len(d.get('schematic_parity',[])));[print(' ',k,n) for k,n in sorted(c.items())]"
    & $Cli pcb render $Pcb -o "$Out\top.png" --side top --width 1400 --height 1300 --quality basic | Out-Null
    & $Cli pcb render $Pcb -o "$Out\bottom.png" --side bottom --width 1400 --height 1300 --quality basic | Out-Null
} finally { Pop-Location }
