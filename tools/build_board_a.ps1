# Rebuild board A from the unmodified dingoPDM baseline.
# - Schematics: upstream dingoPDM ships them in KiCad 10 format; our scripts edit them as text.
# - PCB: upstream is KiCad 9 format. It must STAY KiCad 9: Fusion's KiCad importer loses all nets
#   from a KiCad 10 .kicad_pcb. So PCB scripts run in KiCad 9's python.
# - kicad-cli 10 is used read-only (netlist, ERC, DRC); it can read both formats.
# Usage (repo root, on a branch):  powershell -File tools\build_board_a.ps1 [-Out <folder for reports>] [-NoInputs]
# The input expansion (J6, 5 new inputs, test points removed) is part of the design; -NoInputs builds without it.
# Last stage (board fix, 2026-11-11): tools/sch_board_fix.py A + tools/pcb_fix_board_a.py.
# Then (a1a, 2026-11-12): tools/wirepads.py - J3 DT15 header -> wire pads in the same 12 holes.
# Then (r2a / s4a / s6a / t1a, 2026-11-14): tools/sch_board_power.py A + tools/pcb_board_power.py - part fields only.
# Then (2026-11-14): tools/sch_digikey.py A + tools/pcb_digikey.py - Digi-Key fields only.
# Then (2026-11-16): tools/sch_bom_fields.py A + tools/pcb_bom_fields.py - order fields (Manufacturer / MPN / LCSC / ...).
# Then (ADR-2026-11-20-d2-move): tools/d2_tvs.py lib / sch / pcb - DO-218 load-dump TVS D2 in its new spot.
# Last (hwprotect, ADR-2026-11-20-presim-findings): tools/hw_protect.py sch / pcb - NRST / VDDA caps, USB ESD diodes.
param([string]$Out = "$env:LOCALAPPDATA\Workstation\claude-fusion\kicad9", [switch]$NoInputs)
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
    if (-not $NoInputs) {
        & $py9 "$repo\tools\sch_inputs_board_a.py"
        if ($LASTEXITCODE) { throw 'sch_inputs_board_a.py failed' }
    }
    & $py9 "$repo\tools\sch_board_fix.py" A                     # board fix 2026-11-11: parts, CAN terminator (DECISIONS.md)
    if ($LASTEXITCODE) { throw 'sch_board_fix.py failed' }
    & $py9 "$repo\tools\wirepads.py" lib                       # a1a 2026-11-12: DT15 -> wire pads in the same holes
    if ($LASTEXITCODE) { throw 'wirepads.py lib failed' }
    & $py9 "$repo\tools\wirepads.py" sch-a Connectors.kicad_sch
    if ($LASTEXITCODE) { throw 'wirepads.py sch-a failed' }
    & $py9 "$repo\tools\sch_board_power.py" A                   # r2a / s4a / s6a 2026-11-14: RET7, TLV1117LV, power LED DNP; t1a / ADR-2026-11-20-is-buffer TLV9004IPWR op-amps
    if ($LASTEXITCODE) { throw 'sch_board_power.py failed' }
    & $py9 "$repo\tools\sch_digikey.py" A                       # 2026-11-14: Digi-Key numbers for TBD fields
    if ($LASTEXITCODE) { throw 'sch_digikey.py failed' }
    & $py9 "$repo\tools\sch_bom_fields.py" A                    # 2026-11-16: order fields on every fitted part
    if ($LASTEXITCODE) { throw 'sch_bom_fields.py failed' }
    & $py9 "$repo\tools\d2_tvs.py" lib                          # ADR-2026-11-20-d2-move: DO-218 load-dump TVS footprint
    if ($LASTEXITCODE) { throw 'd2_tvs.py lib failed' }
    & $py9 "$repo\tools\d2_tvs.py" sch Power.kicad_sch
    if ($LASTEXITCODE) { throw 'd2_tvs.py sch failed' }
    & $py9 "$repo\tools\hw_protect.py" sch A                  # hwprotect: NRST / VDDA caps, USB ESD diodes; orderprep: 125 C crystal + X7R caps (fields)
    if ($LASTEXITCODE) { throw 'hw_protect.py sch failed' }
    & $py9 "$repo\tools\hw_5v_module.py" lib                  # hw5v: 125 C 5 V module footprint (TI SIL0010A land pattern)
    if ($LASTEXITCODE) { throw 'hw_5v_module.py lib failed' }
    & $py9 "$repo\tools\hw_5v_module.py" sch A                # hw5v: LMZM23601V5 + caps in place of the TSR U15
    if ($LASTEXITCODE) { throw 'hw_5v_module.py sch failed' }
    & $kc10 sch export netlist --format kicadxml -o "$Out\net.xml" DingoPDM.kicad_sch | Out-Null
    & $py9 "$repo\tools\pcb_swap_board_a.py" DingoPDM.kicad_pcb "$Out\net.xml" 2>&1 | Where-Object { $_ -notmatch 'memory leak' }
    if ($LASTEXITCODE) { throw 'pcb_swap_board_a.py failed' }
    & $py9 "$repo\tools\route_board_a.py" DingoPDM.kicad_pcb 2>&1 | Where-Object { $_ -notmatch 'memory leak' }
    if ($LASTEXITCODE) { throw 'route_board_a.py failed' }
    if (-not $NoInputs) {
        Copy-Item -Force DingoPDM.kicad_pcb "$Out\pre_inputs.kicad_pcb"     # snapshot for experiments / debugging
        & $py9 "$repo\tools\pcb_inputs_board_a.py" DingoPDM.kicad_pcb "$Out\net.xml" 2>&1 | Where-Object { $_ -notmatch 'memory leak' }
        if ($LASTEXITCODE) { throw 'pcb_inputs_board_a.py failed' }
    }
    & $kc10 sch export netlist -o "$Out\board-a.net" DingoPDM.kicad_sch | Out-Null
    & $py9 "$repo\tools\pcb_fix_board_a.py" DingoPDM.kicad_pcb "$Out\board-a.net" 2>&1 | Where-Object { $_ -notmatch 'memory leak' }
    if ($LASTEXITCODE) { throw 'pcb_fix_board_a.py failed' }
    & $py9 "$repo\tools\wirepads.py" pcb DingoPDM.kicad_pcb J3 2>&1 | Where-Object { $_ -notmatch 'memory leak' }
    if ($LASTEXITCODE) { throw 'wirepads.py pcb failed' }
    & $py9 "$repo\tools\pcb_board_power.py" DingoPDM.kicad_pcb "$Out\board-a.net" A 2>&1 | Where-Object { $_ -notmatch 'memory leak' }
    if ($LASTEXITCODE) { throw 'pcb_board_power.py failed' }
    & $py9 "$repo\tools\pcb_digikey.py" DingoPDM.kicad_pcb "$Out\board-a.net" 2>&1 | Where-Object { $_ -notmatch 'memory leak' }
    if ($LASTEXITCODE) { throw 'pcb_digikey.py failed' }
    & $py9 "$repo\tools\pcb_bom_fields.py" DingoPDM.kicad_pcb "$Out\board-a.net" 2>&1 | Where-Object { $_ -notmatch 'memory leak' }
    if ($LASTEXITCODE) { throw 'pcb_bom_fields.py failed' }
    & $py9 "$repo\tools\pcb_hole_keepout.py" DingoPDM.kicad_pcb 2>&1 | Where-Object { $_ -notmatch 'memory leak' }   # 2026-11-20 pcbverify: no pour under the sink posts
    if ($LASTEXITCODE) { throw 'pcb_hole_keepout.py failed' }
    & $py9 "$repo\tools\d2_tvs.py" pcb DingoPDM.kicad_pcb A 2>&1 | Where-Object { $_ -notmatch 'memory leak' }   # ADR-2026-11-20-d2-move: D2 to its new spot + clamp copper
    if ($LASTEXITCODE) { throw 'd2_tvs.py pcb failed' }
    & $py9 "$repo\tools\hw_protect.py" pcb DingoPDM.kicad_pcb "$Out\board-a.net" A 2>&1 | Where-Object { $_ -notmatch 'memory leak' }   # hwprotect: new parts placed + connected (last stage)
    if ($LASTEXITCODE) { throw 'hw_protect.py pcb failed' }
    & $py9 "$repo\tools\hw_5v_module.py" pcb DingoPDM.kicad_pcb "$Out\board-a.net" A 2>&1 | Where-Object { $_ -notmatch 'memory leak' }   # hw5v: TSR out, 125 C module in its outline (last stage)
    if ($LASTEXITCODE) { throw 'hw_5v_module.py pcb failed' }
    & $py9 "$repo\tools\pcb_stackup.py" DingoPDM.kicad_pcb A   # orderprep 2026-11-22: stackup copper = the ordered copper (tools/copper_order.py)
    if ($LASTEXITCODE) { throw 'pcb_stackup.py failed' }
    Remove-Item -Force "$b\BTS700n_1EPP.kicad_sch"
    & $kc10 sch erc -o "$Out\erc.rpt" DingoPDM.kicad_sch | Select-Object -Last 2
    & $kc10 pcb drc --schematic-parity -o "$Out\drc.rpt" DingoPDM.kicad_pcb | Select-Object -Last 3
    git -C $repo checkout 542b3b9 -- hardware/board-a/DingoPDM.kicad_pro   # undo kicad-cli 10 project-file upgrade
    python "$repo\tools\drc_erc_waivers.py" A   # drcclean 2026-11-23: DRC / ERC review stage: rules + commented exclusions, parity fields (last)
    if ($LASTEXITCODE) { throw 'drc_erc_waivers.py A failed' }
} finally {
    git -C $repo reset -q -- hardware/board-a                # never leave build output or baseline files staged
    Pop-Location
}
Select-String -Path "$b\DingoPDM.kicad_pcb" -Pattern '^\s*\(version' | Select-Object -First 1 | ForEach-Object { 'pcb format: ' + $_.Line.Trim() }
