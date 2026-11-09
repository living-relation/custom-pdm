# Rebuild board A from the unmodified dingoPDM baseline.
# - Schematics: upstream dingoPDM ships them in KiCad 10 format; our scripts edit them as text.
# - PCB: upstream is KiCad 9 format. It must STAY KiCad 9: Fusion's KiCad importer loses all nets
#   from a KiCad 10 .kicad_pcb. So PCB scripts run in KiCad 9's python.
# - kicad-cli 10 is used read-only (netlist, ERC, DRC); it can read both formats.
# Usage (repo root, on a branch):  powershell -File tools\build_board_a.ps1 [-Out <folder for reports>] [-WithInputs]
# -WithInputs adds the input expansion (J6 + spare MCU pin rework). Work in progress on feat/input-board.
param([string]$Out = "$env:LOCALAPPDATA\Workstation\claude-fusion\kicad9", [switch]$WithInputs)
$repo = Split-Path $PSScriptRoot -Parent
$py9 = "$env:LOCALAPPDATA\Programs\KiCad\9.0\bin\python.exe"
$kc10 = "$env:LOCALAPPDATA\Programs\KiCad\10.0\bin\kicad-cli.exe"
$b = Join-Path $repo 'hardware\board-a'
New-Item -ItemType Directory -Force $Out | Out-Null

git -C $repo checkout 542b3b9 -- hardware/board-a           # baseline: dingoPDM v7.5, unmodified
git -C $repo reset -q -- hardware/board-a                    # keep the index at HEAD: only the working tree changes
& $kc10 pcb drc --schematic-parity -o "$Out\drc-base.rpt" "$b\DingoPDM.kicad_pcb" | Select-Object -Last 3
Push-Location $b
try {
    & $py9 "$repo\tools\sch_swap_board_a.py"
    if ($LASTEXITCODE) { throw 'sch_swap_board_a.py failed' }
    & $py9 "$repo\tools\sch_repin_board_a.py"
    if ($LASTEXITCODE) { throw 'sch_repin_board_a.py failed' }
    if ($WithInputs) {
        & $py9 "$repo\tools\sch_inputs_board_a.py"
        if ($LASTEXITCODE) { throw 'sch_inputs_board_a.py failed' }
    }
    & $kc10 sch export netlist --format kicadxml -o "$Out\net.xml" DingoPDM.kicad_sch | Out-Null
    & $py9 "$repo\tools\pcb_swap_board_a.py" DingoPDM.kicad_pcb "$Out\net.xml" 2>&1 | Where-Object { $_ -notmatch 'memory leak' }
    if ($LASTEXITCODE) { throw 'pcb_swap_board_a.py failed' }
    & $py9 "$repo\tools\route_board_a.py" DingoPDM.kicad_pcb 2>&1 | Where-Object { $_ -notmatch 'memory leak' }
    if ($LASTEXITCODE) { throw 'route_board_a.py failed' }
    if ($WithInputs) {
        & $py9 "$repo\tools\pcb_inputs_board_a.py" DingoPDM.kicad_pcb "$Out\net.xml" 2>&1 | Where-Object { $_ -notmatch 'memory leak' }
        if ($LASTEXITCODE) { throw 'pcb_inputs_board_a.py failed' }
    }
    Remove-Item -Force "$b\BTS700n_1EPP.kicad_sch"
    & $kc10 sch erc -o "$Out\erc.rpt" DingoPDM.kicad_sch | Select-Object -Last 2
    & $kc10 pcb drc --schematic-parity -o "$Out\drc.rpt" DingoPDM.kicad_pcb | Select-Object -Last 3
    git -C $repo checkout 542b3b9 -- hardware/board-a/DingoPDM.kicad_pro   # undo kicad-cli 10 project-file upgrade
} finally {
    git -C $repo reset -q -- hardware/board-a                # never leave build output or baseline files staged
    Pop-Location
}
Select-String -Path "$b\DingoPDM.kicad_pcb" -Pattern '^\s*\(version' | Select-Object -First 1 | ForEach-Object { 'pcb format: ' + $_.Line.Trim() }
