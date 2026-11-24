# Firmware flashing: boards A1, A2 and B

Written 2026-11-24 (job pkgfix). Facts come from this repo (file named in each line) and from the upstream dingo
update guide, <https://corygrant.github.io/dingoElec/dingofw/updating/> (read 2026-11-24; our boards use the same
STM32F446, USB-C socket and BOOT switch as dingoPDM v7). No board exists yet: nothing here has been tried on
hardware (`.claude/rules/firmware.md`: do not flash anything until the boards are made).

## 1. Which file goes on which board

| Board | File (`.hex`, or `.bin` at 0x08000000) | CAN base ID (default) | Notes |
|---|---|---|---|
| Board A, first unit (A1, input board #1 on J6) | `custompdm_a_unit1` | 0x500 | |
| Board A, second unit (A2, input board #2 on J6) | `custompdm_a_unit2` | 0x540 | runs the box fans on its output 2 (`firmware/boards/custompdm_a/port.h` `FAN_OUTPUT`) |
| Board B | `custompdm_b_unit1` | 0x580 | |

- **Never mix them.** The two board A files differ only in the default base ID and the fan output; the A file
  does not match board B's pins at all. Mark each board (A1 / A2 / B) before you start.
- A base ID changed later in dingoConfig is kept in the board's memory (FRAM) across updates, unless the config
  layout changes (section 3).

## 2. Where to get the files

1. **Build package** (easiest): `common/firmware/` in the latest `custom-pdm-board-build-package-<date>-<sha>.zip`.
   It has `.hex`, `.bin`, `.elf`, `SHA256SUMS.txt` (check the file before you flash) and `build-info.txt` (main
   commit, compiler, CONFIG_VERSION, and the md5 of the stock `dingopdm_v7` build, which must stay
   `fbe414ba90f541c714e8fd7e99589691`).
2. **Build it yourself from `main`** (WSL, as `.claude/rules/firmware.md` says: from an LF `git archive`, never
   from the Windows checkout): `bash firmware/sim/renode/build_wsl.sh` builds all four (A unit 1, A unit 2, B, stock
   v7) into `~/renode-pdm/fw` (`custompdm_a_unit1.bin` ...). Make the `.hex` with
   `arm-none-eabi-objcopy -O ihex custompdm_a_unit1.elf custompdm_a_unit1.hex`. Expect 4 builds OK, the only
   warning the linker "RWX segment" one.
3. **Proposed, not set up:** a GitHub release on this private repo for every firmware merge (tag `fw-<version>-<sha>`,
   the three `.hex` / `.bin` files and `SHA256SUMS.txt`). The coordinator decides; nothing is published.

## 3. When to update

- After a firmware change merges to `main` (anything under `firmware/` except `firmware/sim/` and docs): flash all
  three boards from the same commit, the same day. **Never run boards on different firmware commits** (they share
  CAN messages and settings formats).
- When `CONFIG_VERSION` changes (`firmware/core/config.h`). It is the version of the settings layout stored in
  FRAM: the high byte counts our layout (now 0x04), the low byte is upstream's (0x0A), so builds from `main` today
  are **0x040A** on all three boards. When a board starts with firmware whose CONFIG_VERSION differs from the one
  in its FRAM, it throws the stored settings away and starts on defaults. So: save the settings to a file first,
  and after flashing do **Write All** and **Burn** (section 6).
- Not needed for a settings change only: settings go over USB / CAN with dingoConfig, no flashing.

## 4. Before you start (safety)

- Car side off: disconnect the battery feed and the box connectors (X1 / X2) from the PDM, or work on the bench
  with the board on its own. Entering the bootloader **turns every output off** (upstream guide), so nothing in
  the car may depend on the PDM while you flash.
- USB-C powers the logic for flashing (VBUS through D15 on A, D6 on B into +5 V): **no 12 V is needed**. Leave the
  battery input off while flashing.
- In dingoConfig: connect, **Read All**, then save the settings of each board to a file.
- Use a USB-C data cable. Both boards have the 5.1 kOhm CC resistors (A: R54, R55; B: R6, R7), so USB-C to USB-C
  should work; if the PC does not see the board, try a USB-C to USB-A cable (the upstream guide asks for one on
  v7.2 boards, which lack those resistors).

## 5. Flash over USB-C (DFU, the STM32's built-in bootloader)

**Step 1: put the board in bootloader mode (pick one).**
- **dingoConfig Bootloader button** (firmware already running): connect, open the board's page, press
  "Bootloader". It works over USB or CAN, but the update itself must go over USB. The board drops off dingoConfig:
  close dingoConfig before the next step. (Firmware: CAN or USB message to base ID + 1 with byte 0 = 33 and
  `BOOTL` in bytes 1-5, `firmware/comms/request_msg.cpp`.)
- **BOOT switch SW1** (first flash, or if the firmware does not run): power off (unplug USB). SW1 is the 3-pin
  slide switch next to the USB-C socket (A: J5, B: J2) at the south edge of the top surface, same spot on A and B.
  Its middle pin goes through a 10 kOhm resistor (A: R4, B: R10) to the MCU BOOT0 pin; the outer pin nearer the
  south edge is GND (normal run), the other outer pin is +3V3 (bootloader). Slide it to the bootloader side: the
  upstream guide says to line the switch up with the lines marked on its body. Check with a meter, power off: SW1
  middle pin to GND reads 0 Ohm in the run position and not 0 in the bootloader position. A power cycle is needed
  every time SW1 is moved (upstream guide).

**Step 2: connect USB-C.** Windows Device Manager shows "STM32 BOOTLOADER" under "Universal Serial Bus devices";
Linux `lsusb` shows "STMicroelectronics STM Device in DFU Mode" (USB ID 0483:df11).

**Step 3: flash (pick one tool).**
- **STM32CubeProgrammer** (the upstream way): connection type USB, refresh, Connect. "Erasing & Programming",
  Browse to the `.hex` for this board, leave "Skip flash erase" unchecked, tick "Verify programming" and "Run after
  programming", Start Programming. The board disconnects when it is done.
- **STM32CubeProgrammer command line:** `STM32_Programmer_CLI -c port=USB1 -w custompdm_a_unit1.hex -v -s`
- **dfu-util:** `dfu-util -a 0 -d 0483:df11 -s 0x08000000:leave -D custompdm_a_unit1.bin` (the `.bin` goes at the
  start of flash, 0x08000000).

**Step 4:** if you used SW1, unplug, slide SW1 back to the run side (meter: 0 Ohm middle pin to GND), plug in again.

## 6. After flashing

1. dingoConfig: connect, open the board's page and read the **firmware version** (section 7). Check it is the
   version you flashed and the base ID is right (0x500 / 0x540 / 0x580, or yours).
2. If CONFIG_VERSION changed (or the board shows default settings): open the saved file, **Write All**, then
   **Burn**. Write All took about 40 s per board through the simulator bridge (measured 2026-11-16).
3. First start with **10 V or more** on the battery input: the firmware sets the MCU brown-out level once and
   resets itself (normal; `firmware/core/safety.cpp`, `SAFETY_BOR_MIN_VBAT` 10 V). On USB power alone it waits for
   a later start.
4. Do the next board. When all three are done, check that all three show on CAN with their own base IDs.

## 7. How to check the flashed version

- **dingoConfig:** the board's page shows the firmware version (upstream guide).
- **Over CAN (any tool):** send to base ID + 1 (A1 0x501, A2 0x541, B 0x581) 8 bytes with byte 0 = 31 (`Version`).
  The board answers on its base ID (0x500 / 0x540 / 0x580): byte 0 = 31, byte 4 = major, byte 5 = minor,
  bytes 6-7 = build (high byte first) (`firmware/comms/request_msg.cpp`). Builds from `main` today answer
  **0.6.2** (`firmware/core/device_config.h` `MAJOR_VERSION` / `MINOR_VERSION` / `BUILD`).
- The version number alone does not show the commit: the build package's `build-info.txt` and `SHA256SUMS.txt`
  tie a file to its `main` commit. CONFIG_VERSION is not sent over CAN: read it in `build-info.txt` or in
  `firmware/core/config.h` of that commit.

## 8. Fallback: ST-Link over SWD

If USB / DFU does not work (dead USB-C, no bootloader): the 6-pin Tag-Connect pads, **A: J4, B: J5**, top surface
(`Tag-Connect_TC2030-IDC-NL`; pad 1 +3V3, 2 SWDIO, 3 NRST, 4 SWCLK, 5 GND, 6 SWO). Use a TC2030-IDC-NL (no-legs)
cable with the Tag-Connect adapter for your ST-Link, power the board from USB-C or the bench supply (12 V, current
limit about 0.2 A), STM32CubeProgrammer connection type ST-LINK (SWD), Connect, then the same "Erasing &
Programming" steps; command line `STM32_Programmer_CLI -c port=SWD -w custompdm_a_unit1.hex -v -rst`.
The upstream guide uses the same ST-Link + TC2030 way for its CANBoard (which has no USB).

## 9. If something goes wrong

- PC does not see "STM32 BOOTLOADER": SW1 not in the bootloader position, no power cycle after moving it, or a
  charge-only cable. Try another cable (USB-C to USB-A).
- Board runs but shows default settings: CONFIG_VERSION changed (expected) or the FRAM was blank: Write All + Burn.
- Two boards answer on the same base ID: one has the wrong unit file or a copied setting; fix the base ID in
  dingoConfig (a critical setting: unlock, type the value, confirm) or re-flash the right file and Write All.
