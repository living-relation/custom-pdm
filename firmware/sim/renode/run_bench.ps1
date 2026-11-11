# One command for the Renode bench from Windows PowerShell:
#   powershell -ExecutionPolicy Bypass -File firmware\sim\renode\run_bench.ps1 [--build]
# Copies run_bench.sh into the WSL sandbox with LF endings and runs it there. Results: ~/renode-pdm/bench/out/results.
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$drive = $here.Substring(0, 1).ToLower()
$src = '/mnt/' + $drive + ($here.Substring(2) -replace '\\', '/')
$extra = ($args -join ' ')
wsl -d Ubuntu -- bash -c "mkdir -p ~/renode-pdm/bench && sed 's/\r`$//' '$src/run_bench.sh' > ~/renode-pdm/bench/run_bench.sh && SRC='$src' bash ~/renode-pdm/bench/run_bench.sh $extra"
