# Rebuild the input daughter board from scratch: schematic (KiCad 10 text) -> netlist -> PCB (KiCad 9 python:
# place, route, pour) -> ERC + DRC with schematic parity. The PCB stays KiCad 9 format (Fusion import).
# Usage (repo root, on a branch):  powershell -File tools\build_input_board.ps1 [-Out <folder for reports>]
param([string]$Out = "$env:LOCALAPPDATA\Workstation\claude-fusion\kicad9")
$repo = Split-Path $PSScriptRoot -Parent
$py9 = "$env:LOCALAPPDATA\Programs\KiCad\9.0\bin\python.exe"
$kc10 = "$env:LOCALAPPDATA\Programs\KiCad\10.0\bin\kicad-cli.exe"
$d = Join-Path $repo 'hardware\input-board'
New-Item -ItemType Directory -Force $Out | Out-Null
Push-Location $d
try {
    $pro = Get-Content input-board.kicad_pro -Raw                  # rules copied from board A; kicad-cli 10 rewrites it
    & $py9 "$repo\tools\gen_input_board_sch.py" .
    if ($LASTEXITCODE) { throw 'gen_input_board_sch.py failed' }
    & $kc10 sch export netlist --format kicadxml -o "$Out\ib-net.xml" input-board.kicad_sch | Out-Null
    if (Test-Path input-board.kicad_pcb) { Remove-Item -Force input-board.kicad_pcb }
    & $py9 "$repo\tools\gen_input_board_pcb.py" input-board.kicad_pcb "$Out\ib-net.xml" 2>&1 | Where-Object { $_ -match 'placed|failed|duplicate|saved|PROBLEM' }
    if ($LASTEXITCODE) { throw 'gen_input_board_pcb.py failed' }
    & $kc10 sch erc -o "$Out\ib-erc.rpt" input-board.kicad_sch | Select-Object -Last 1
    & $kc10 pcb drc --schematic-parity -o "$Out\ib-drc.rpt" input-board.kicad_pcb | Select-Object -Last 2
    Set-Content -Path input-board.kicad_pro -Value $pro -NoNewline -Encoding utf8
} finally { Pop-Location }
Select-String -Path "$d\input-board.kicad_pcb" -Pattern '^\s*\(version' | Select-Object -First 1 | ForEach-Object { 'pcb format: ' + $_.Line.Trim() }
