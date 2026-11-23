# Export the board STEPs the enclosure build reads, from this checkout's KiCad boards. hardware/ is only READ: each board
# (.kicad_pcb + .kicad_pro) is copied to a scratch folder with the 3D models its ${KIPRJMOD}/Models paths need, and exported there.
# Usage (PowerShell 5.1, DansPC):  powershell -ExecutionPolicy Bypass -File enclosure\v2c\src\export_boards.ps1 [-Out <folder>]
# Default output: <repo root>\.claude\cache\enclosure\boards (git-ignored, outside every worktree, so `git worktree remove` keeps it).
# KiCad 10.0.7 kicad-cli (STEP export only). Model sources:
#   ${KICAD6_3DMODEL_DIR} / ${KICAD9_3DMODEL_DIR} -> KiCad 10's own library (STEP; --subst-models swaps the .wrl names for .step)
#   board A ${KIPRJMOD}/Models -> reference\dingoPDM\DingoPDM\Models (stock dingoPDM models, MIT repo) + hardware\board-a\Models
#     (our own models, e.g. D2's DO-218 from tools/d2_model.py)
#   board B ${KIPRJMOD}/Models -> hardware\board-b-max\Models
# BTS70012 (U8-U11, PG-TSDSO-24): since job orderprep (2026-11-22) the footprints point at
# hardware\board-b-max\Models\PG-TSDSO-24_bestguess.step (tools/tsdso24_model.py, a labelled best guess 1.15 mm tall), so
# the next export carries a body for them (the revF release was exported before that, without). See export.log.
param([string]$Out = "")
$ErrorActionPreference = "Continue"
$src = Split-Path -Parent $MyInvocation.MyCommand.Path
$wt = (Resolve-Path (Join-Path $src "..\..\..")).Path
$common = (& git -C $wt rev-parse --path-format=absolute --git-common-dir 2>$null)
$root = Split-Path -Parent $common
if (-not $Out) { $Out = Join-Path $root ".claude\cache\enclosure\boards" }
New-Item -ItemType Directory -Force -Path $Out | Out-Null
$kc = "C:\Users\danie\AppData\Local\Programs\KiCad\10.0"
$cli = Join-Path $kc "bin\kicad-cli.exe"
$lib = Join-Path $kc "share\kicad\3dmodels"
foreach ($v in "KICAD6_3DMODEL_DIR", "KICAD7_3DMODEL_DIR", "KICAD8_3DMODEL_DIR", "KICAD9_3DMODEL_DIR", "KICAD10_3DMODEL_DIR") { Set-Item "env:$v" $lib }
$boards = @(
  @{ dir = "hardware\board-a";     pcb = "DingoPDM.kicad_pcb";     step = "board-A.step";     models = (Join-Path $root "reference\dingoPDM\DingoPDM\Models") },
  @{ dir = "hardware\board-b-max"; pcb = "dingoPDM-Max.kicad_pcb"; step = "board-B.step";     models = (Join-Path $wt "hardware\board-b-max\Models") },
  @{ dir = "hardware\input-board"; pcb = "input-board.kicad_pcb";  step = "input-board.step"; models = "" })
$sha = (& git -C $wt rev-parse --short HEAD 2>$null)
$log = Join-Path $Out "export.log"
"export_boards.ps1 $(Get-Date -Format s) commit $sha kicad-cli $(& $cli --version)" | Set-Content $log
foreach ($b in $boards) {
  $tmp = Join-Path $Out ("_src\" + [IO.Path]::GetFileNameWithoutExtension($b.step))
  Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue; New-Item -ItemType Directory -Force -Path $tmp | Out-Null
  $base = [IO.Path]::GetFileNameWithoutExtension($b.pcb)
  Copy-Item (Join-Path $wt "$($b.dir)\$base.kicad_pcb"), (Join-Path $wt "$($b.dir)\$base.kicad_pro") $tmp
  if ($b.models) { Copy-Item $b.models (Join-Path $tmp "Models") -Recurse }
  # models kept in the repo board folder itself (board A's D2 DO-218 model, tools/d2_model.py) join the stock ones
  $own = Join-Path $wt "$($b.dir)\Models"
  if ((Test-Path $own) -and ($own -ne $b.models)) {
    New-Item -ItemType Directory -Force -Path (Join-Path $tmp "Models") | Out-Null
    Copy-Item (Join-Path $own "*") (Join-Path $tmp "Models") -Force
  }
  # kicad-cli 10 does not expand the old versioned library variables from the environment, and KiCad 10 ships STEP only:
  # rewrite the model paths in the COPY to absolute KiCad 10 library paths with .step (hardware/ itself is untouched)
  $pf = Join-Path $tmp $b.pcb; $libf = $lib -replace '\\', '/'
  $t = [IO.File]::ReadAllText($pf)
  $t = [regex]::Replace($t, '\$\{KICAD(6|7|8|9|10)_3DMODEL_DIR\}', $libf)
  $t = [regex]::Replace($t, '(\(model "' + [regex]::Escape($libf) + '[^"]*)\.wrl"', '$1.step"')
  [IO.File]::WriteAllText($pf, $t)
  $o = Join-Path $Out $b.step
  & $cli pcb export step --force --subst-models -o $o (Join-Path $tmp $b.pcb) 2>&1 | Out-File -Append -Encoding utf8 $log
  "$($b.step) rc=$LASTEXITCODE sha256=$((Get-FileHash $o -Algorithm SHA256).Hash) from $($b.dir)\$($b.pcb) @ $sha" | Add-Content $log
}
Remove-Item (Join-Path $Out "_src") -Recurse -Force -ErrorAction SilentlyContinue
Get-Content $log | Select-String -Pattern 'rc=|export_boards|rror|not found|Cannot' | ForEach-Object { $_.Line }
