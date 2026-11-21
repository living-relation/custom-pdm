# Start-PdmUi.ps1 - one-click start of the PDM UI (dingoConfig copy) with the simulated boards.
# Double-click "Start PDM UI.cmd" beside this file, or the Desktop shortcut "PDM UI".
#   (no switch)       start what is missing (sim build, bridge, app), then open http://localhost:<Port>/pdm
#   -Stop             stop only what this launcher started (pid file in %LOCALAPPDATA%\custom-pdm)
#   -NoSim            app only (real hardware later): no sim build, no bridge
#   -Rebuild          build the sim .so files again even if they look current
#   -InstallShortcut  (re)create the Desktop shortcut "PDM UI.lnk" pointing at the main checkout
#   -SelfTest         check the helper functions (starts nothing)
# No admin rights, no installs. Windows PowerShell 5. ASCII only.
[CmdletBinding()]
param(
    [switch]$Stop,
    [switch]$NoSim,
    [switch]$Rebuild,
    [switch]$InstallShortcut,
    [switch]$SelfTest,
    [switch]$NoBrowser,
    [int]$Port = 5000,
    [int]$BridgePort = 3333,
    [string]$SoDir = '/home/daniel/scratch/ui-play/so',
    [string]$FirmwareRef = 'main',
    [int]$WaitSeconds = 180
)
$ErrorActionPreference = 'Continue'   # not Stop: PowerShell 5 turns stderr lines of git / wsl into errors
$UiDir    = $PSScriptRoot
$RepoRoot = Split-Path -Parent $UiDir
$StateDir = Join-Path $env:LOCALAPPDATA 'custom-pdm'
$PidFile  = Join-Path $StateDir ("ui-launcher-{0}.json" -f $Port)
$AppUrl   = "http://localhost:$Port"
$PdmUrl   = "$AppUrl/pdm"

function Say([string]$m)  { Write-Host $m }
function Fail([string]$m) { Write-Host ''; Write-Host "PROBLEM: $m" -ForegroundColor Red; exit 1 }

function ConvertTo-WslPath([string]$p) {
    $p = $p -replace '\\', '/'
    if ($p -match '^([A-Za-z]):/(.*)$') { return '/mnt/' + $Matches[1].ToLower() + '/' + $Matches[2] }
    return $p
}

function Test-SoDirOk([string]$d) {
    # Linux folder inside WSL, never the Windows drive (CRLF checkout, slow) and never a root-level folder.
    return ($d -match '^/[^/\s]+/[^\s]+$') -and ($d -notmatch '^/mnt/') -and ($d -notmatch '\.\.')
}

function Get-MainCheckout {
    # The folder that holds the shared .git (the main checkout), also when this file runs from a worktree.
    $c = (& git -C $RepoRoot rev-parse --path-format=absolute --git-common-dir 2>$null)
    if ($LASTEXITCODE -ne 0 -or -not $c) { return $RepoRoot }
    return (Split-Path -Parent ($c -replace '/', '\'))
}

function Test-AppUp {
    try {
        $r = Invoke-WebRequest -Uri $AppUrl -UseBasicParsing -TimeoutSec 3
        return ($r.StatusCode -ge 200 -and $r.StatusCode -lt 500)
    } catch {
        if ($_.Exception.Response) { return $true }   # it answered, even if with an error page
        return $false
    }
}

function Test-BridgeUp {
    & wsl.exe -e pgrep -f ("slcan-tcp[ ]{0}$" -f $BridgePort) *> $null
    return ($LASTEXITCODE -eq 0)
}

function Read-Pids {
    if (Test-Path $PidFile) { try { return (Get-Content $PidFile -Raw | ConvertFrom-Json) } catch { } }
    return $null
}

function Save-Pids($app, $bridge) {
    if (-not (Test-Path $StateDir)) { New-Item -ItemType Directory -Path $StateDir | Out-Null }
    $o = [ordered]@{ port = $Port; bridgePort = $BridgePort; soDir = $SoDir; app = $app; bridge = $bridge }
    ($o | ConvertTo-Json) | Set-Content -Path $PidFile -Encoding ASCII
}

function New-PidEntry($proc) {
    return [ordered]@{ pid = $proc.Id; started = $proc.StartTime.ToUniversalTime().ToString('o') }
}

function Test-PidEntry($e) {
    # True only if the process is still the one we started (same pid AND same start time).
    if (-not $e -or -not $e.pid) { return $false }
    $p = Get-Process -Id $e.pid -ErrorAction SilentlyContinue
    if (-not $p) { return $false }
    try { return ($p.StartTime.ToUniversalTime().ToString('o') -eq $e.started) } catch { return $false }
}

function Stop-Tree($e) {
    if (Test-PidEntry $e) { & taskkill.exe /PID $e.pid /T /F *> $null; return $true }
    return $false
}

function Invoke-Stop {
    $s = Read-Pids
    if (-not $s) { Say "Nothing to stop: this launcher has started nothing on port $Port."; return }
    if (Stop-Tree $s.app) { Say "Stopped the app (port $($s.port))." } else { Say 'The app this launcher started is already gone.' }
    if ($s.bridge) {
        $hit = Stop-Tree $s.bridge
        # The Linux side of the bridge can outlive wsl.exe: end exactly the one we started (same folder, same port).
        & wsl.exe -e pkill -f ("sim_bridge.py {0} --slcan-tcp {1}$" -f $s.soDir, $s.bridgePort) *> $null
        if ($hit -or $LASTEXITCODE -eq 0) { Say "Stopped the simulator bridge (port $($s.bridgePort))." }
        else { Say 'The simulator bridge this launcher started is already gone.' }
    }
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
}

function Install-Shortcut {
    $target = Join-Path (Get-MainCheckout) 'ui\Start PDM UI.cmd'
    $lnk = Join-Path ([Environment]::GetFolderPath('Desktop')) 'PDM UI.lnk'
    $ws = New-Object -ComObject WScript.Shell
    $sc = $ws.CreateShortcut($lnk)
    $sc.TargetPath = $target
    $sc.WorkingDirectory = Split-Path -Parent $target
    $sc.Description = 'Start the PDM UI (simulated boards) and open it in the browser'
    $sc.IconLocation = "$env:SystemRoot\System32\shell32.dll,12"   # the chip icon
    $sc.WindowStyle = 1
    $sc.Save()
    Say "Desktop shortcut written: $lnk"
    Say "  it starts: $target"
    if (-not (Test-Path $target)) { Say '  (that file is not there yet: it appears when the launcher is merged to main)' }
}

function Get-FirmwareStamp {
    $t = (& git -C $RepoRoot rev-parse "${FirmwareRef}:firmware" 2>$null)
    if ($LASTEXITCODE -ne 0 -or -not $t) { Fail "Cannot find the firmware of branch '$FirmwareRef' in $RepoRoot." }
    return "$t".Trim()
}

function Test-SimCurrent([string]$stamp) {
    foreach ($f in 'custompdm_a_unit1.so', 'custompdm_a_unit2.so', 'custompdm_b_unit1.so') {
        & wsl.exe -e test -f "$SoDir/$f" *> $null
        if ($LASTEXITCODE -ne 0) { return $false }
    }
    $have = (& wsl.exe -e cat "$SoDir/built-from.txt" 2>$null)
    return ("$have".Trim() -eq $stamp)
}

function Build-Sim([string]$stamp) {
    # Rule (.claude/rules/firmware.md): build inside WSL from an LF git archive, started from an LF .sh file.
    if (-not (Test-Path $StateDir)) { New-Item -ItemType Directory -Path $StateDir | Out-Null }
    $sh = Join-Path $StateDir ("build-sim-{0}.sh" -f $Port)
    $lines = @(
        '#!/bin/bash',
        '# written by ui/Start-PdmUi.ps1 - builds the three sim boards from an LF git archive',
        'set -e',
        'GITDIR="$1"; REF="$2"; SO="$3"; STAMP="$4"',
        'S="$(dirname "$SO")"',
        'rm -rf "$S/src"; mkdir -p "$S/src" "$SO"',
        'git -c core.autocrlf=false -c safe.directory="*" --git-dir="$GITDIR" archive "$REF" firmware | tar -x -C "$S/src"',
        'rm -f "$SO/built-from.txt"; rm -rf "$SO"/obj_custompdm_*',
        'cd "$S/src/firmware"',
        'bash sim/build.sh custompdm_a "$SO" 1',
        'bash sim/build.sh custompdm_a "$SO" 2',
        'bash sim/build.sh custompdm_b "$SO" 1',
        'echo "$STAMP" > "$SO/built-from.txt"',
        ''
    )
    [IO.File]::WriteAllText($sh, ($lines -join "`n"), (New-Object Text.ASCIIEncoding))
    $gitDir = (& git -C $RepoRoot rev-parse --path-format=absolute --git-common-dir)
    Say "Building the simulated boards from '$FirmwareRef' (about half a minute) ..."
    & wsl.exe -e bash (ConvertTo-WslPath $sh) (ConvertTo-WslPath $gitDir) $FirmwareRef $SoDir $stamp
    if ($LASTEXITCODE -ne 0) { Fail 'The simulator build failed. The lines above say why.' }
}

function Invoke-SelfTest {
    function Check([string]$name, [bool]$ok) { if ($ok) { Say "  ok    $name" } else { Say "  FAIL  $name"; $script:bad++ } }
    $script:bad = 0
    Check 'wsl path of a C: path'      ((ConvertTo-WslPath 'C:\projects\active\custom-pdm\ui') -eq '/mnt/c/projects/active/custom-pdm/ui')
    Check 'wsl path of a C:/ path'     ((ConvertTo-WslPath 'D:/a b/.git') -eq '/mnt/d/a b/.git')
    Check 'so dir in WSL home is ok'   (Test-SoDirOk '/home/daniel/scratch/ui-play/so')
    Check 'so dir on /mnt/c refused'   (-not (Test-SoDirOk '/mnt/c/projects/so'))
    Check 'so dir with .. refused'     (-not (Test-SoDirOk '/home/daniel/../so'))
    Check 'root-level so dir refused'  (-not (Test-SoDirOk '/so'))
    $me = Get-Process -Id $PID
    Check 'own pid entry is ours'      (Test-PidEntry (New-PidEntry $me))
    Check 'same pid, other start time' (-not (Test-PidEntry ([ordered]@{ pid = $PID; started = '2000-01-01T00:00:00.0000000Z' })))
    Check 'missing pid entry'          (-not (Test-PidEntry $null))
    Check 'main checkout has ui'       (Test-Path (Join-Path (Get-MainCheckout) 'ui'))
    Check 'pid file is per port'       ($PidFile -like "*ui-launcher-$Port.json")
    if ($script:bad) { Fail "$($script:bad) self-test check(s) failed." }
    Say 'Self-test passed.'
}

# ---- main ----
if ($SelfTest)        { Invoke-SelfTest; exit 0 }
if ($InstallShortcut) { Install-Shortcut; exit 0 }
if ($Stop)            { Invoke-Stop; exit 0 }

Say "PDM UI launcher  (checkout: $RepoRoot)"

if (Test-AppUp) {
    Say "The app is already running on $AppUrl."
    if (-not $NoBrowser) { Say "Opening $PdmUrl"; Start-Process $PdmUrl }
    exit 0
}

if (-not (Get-Command dotnet -ErrorAction SilentlyContinue)) { Fail 'dotnet was not found on this PC.' }

$old = Read-Pids
$appEntry = $null
$bridgeEntry = $null
if ($old -and (Test-PidEntry $old.bridge)) { $bridgeEntry = $old.bridge }

if ($NoSim) {
    Say 'No simulator (-NoSim): starting the app only.'
} else {
    if (-not (Test-SoDirOk $SoDir)) { Fail "The simulator folder must be a Linux folder inside WSL (not /mnt/...): $SoDir" }
    $stamp = Get-FirmwareStamp
    if (Test-BridgeUp) {
        Say "The simulator bridge is already running on port $BridgePort."
        if ($Rebuild) { Say '  (not rebuilding under a running bridge: run with -Stop first, then -Rebuild)' }
        elseif (-not (Test-SimCurrent $stamp)) { Say "  (note: its boards are older than '$FirmwareRef'; stop it and start again to update)" }
    } else {
        if ($Rebuild -or -not (Test-SimCurrent $stamp)) { Build-Sim $stamp }
        else { Say "The simulated boards are up to date with '$FirmwareRef'." }
        Say "Starting the simulator bridge on port $BridgePort (minimised window) ..."
        $bridgePy = ConvertTo-WslPath (Join-Path $UiDir 'tests\sim_bridge.py')
        $bp = Start-Process -FilePath 'wsl.exe' -WindowStyle Minimized -PassThru `
            -ArgumentList @('-e', 'python3', "`"$bridgePy`"", $SoDir, '--slcan-tcp', "$BridgePort")
        $bridgeEntry = New-PidEntry $bp
        Save-Pids $null $bridgeEntry
        $up = $false
        foreach ($i in 1..20) { Start-Sleep -Milliseconds 500; if (Test-BridgeUp) { $up = $true; break }; if ($bp.HasExited) { break } }
        if (-not $up) { Fail "The simulator bridge did not start. Try: wsl -e python3 $bridgePy $SoDir --slcan-tcp $BridgePort" }
    }
}

Say 'Building the app ...'
$proj = Join-Path $UiDir 'dingoConfig\web\web.csproj'
$log = & dotnet build $proj --nologo -v q 2>&1
if ($LASTEXITCODE -ne 0) {
    $log | Where-Object { "$_" -match 'error' } | Select-Object -First 15 | ForEach-Object { Write-Host "  $_" }
    Fail 'The app did not build (errors above). Nothing was started; the simulator bridge, if started, is left running.'
}

Say "Starting the app on $AppUrl (minimised window) ..."
$ap = Start-Process -FilePath 'dotnet' -WindowStyle Minimized -PassThru -WorkingDirectory $RepoRoot `
    -ArgumentList @('run', '--no-build', '--project', "`"$proj`"", '--', '--urls', $AppUrl)
$appEntry = New-PidEntry $ap
Save-Pids $appEntry $bridgeEntry

$ok = $false
$until = (Get-Date).AddSeconds($WaitSeconds)
while ((Get-Date) -lt $until) {
    if (Test-AppUp) { $ok = $true; break }
    if ($ap.HasExited) { break }
    Start-Sleep -Milliseconds 700
}
if (-not $ok) {
    if ($ap.HasExited) { Fail "The app stopped right after starting (is port $Port taken by something else?)." }
    Fail "The app did not answer on $AppUrl within $WaitSeconds s. Look at its minimised window."
}

Say "The app is up: $PdmUrl"
if (-not $NoSim) { Say "Simulated boards: in the app pick adapter 'SLCAN TCP', port localhost:$BridgePort, 1000K, then connect." }
if (-not $NoBrowser) { Start-Process $PdmUrl }
Say "To stop it: `"Start PDM UI.cmd`" -Stop"
exit 0
