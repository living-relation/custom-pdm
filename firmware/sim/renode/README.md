# Renode bench

The three real firmware binaries (board A unit 1, board A unit 2, board B) run in Renode 1.17.0 on one emulated
CAN bus. Robot Framework tests repeat the checks of the host simulation `../s1_system.py`.
Latest results and limits: `RESULTS-renode.md`.

## Run it

Windows PowerShell, from the repo root:

    powershell -ExecutionPolicy Bypass -File firmware\sim\renode\run_bench.ps1

Inside WSL: `bash run_bench.sh` (add `--build` to rebuild the firmware from `main`; `BRANCH=<name>` for another branch).
Needs the sandbox from `install_wsl.sh` and one earlier run of `build_wsl.sh` (ChibiOS clone).
Output: `~/renode-pdm/bench/out/` (`report.html`, `log.html`, `robot_output.xml`). About 3 minutes.

## Files

| File | What it is |
|---|---|
| `stm32f446re.repl` | Platform: STM32F446RE as far as the firmware uses it |
| `models/PdmI2C.cs` | I2C controller with DMA, FRAM (MB85RC256V style), MCP9808 stand-in |
| `models/PdmAdcCan.cs` | ADC1 with the PROFET current-sense plant; CAN test node (ECU + PC tool) |
| `models/STM32DMA_Circ.cs` | Renode's STM32DMA (MIT, Antmicro) plus circular mode |
| `models/PdmNvicFix.cs` | Correction for `ICSR.RETTOBASE` in Renode 1.17.0 |
| `gen_bench.py` | Writes `bench.resc` (4 machines on one CAN hub) from the pin tables in `../pdmsim.py` |
| `tests/pdm_bench.robot`, `tests/pdm_bench.py` | The tests and their keywords |
| `build_bench.sh` | Builds the three binaries into `~/renode-pdm/bench/fw` (own folders, apart from `build_wsl.sh`) |
| `run_bench.sh`, `run_bench.ps1` | One-command run |

## How it is put together

- Each board is one Renode machine with its own firmware ELF; a fourth machine holds the CAN test node.
- Pin tables (IN, DEN, DSEL, IS pins, kILIS, input pins) come from `../pdmsim.py`, which was written from
  `docs/firmware-pin-map.md`, not from the firmware. A wrong pin in the firmware fails a test.
- "Output is on" in the tests means the IN pin of that output is driven high (read from the GPIO model);
  "status says on" comes from the board's CAN status frames, decoded with `pdmsim.Status`.
- A power cycle is `machine Reset` plus a reload of the ELF; the FRAM keeps its contents.

## Why the extra models

Checked against Renode 1.17.0 sources (renode-infrastructure 066a7f1) and ChibiOS 879cf757:

- `STM32F1_I2C` (stock) has no DMA and clears ADDR on any SR2 read. The ChibiOS I2Cv1 driver moves all data by
  DMA and reads SR2 before SR1.
- `STM32DMA` (stock) does not implement circular mode. The ChibiOS ADC driver needs it.
- `STM32_ADC` (stock) takes a fixed 100 us per conversion and plays back queued samples. The firmware waits 60 us
  after switching DSEL, and the sense voltage depends on the pin states when the sample is taken.
- `NVIC` (stock) reports `RETTOBASE = 1` inside an interrupt that preempted another interrupt. ChibiOS then
  switches threads while still nested and crashes about 1 s after start (HardFault in `__port_switch`).
- The stock `stm32f4.repl` is an F40x: 2 MB flash, 256 KB RAM, timers at 10 MHz, no ADC, no DWT cycle counter
  (ChibiOS polled delays hang without it).
- Nothing exists for the MCP9808; `MB85RC1MT` is the 1 Mbit part with a different addressing scheme.

## Limits

See the "Not covered" list in `RESULTS-renode.md`.
