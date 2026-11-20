//
// custom-pdm Renode bench models for the MCU safety code (firmware core/safety.h, boards/stm32f446/mcu_safety.cpp):
//   PDM_FlashOpt - STM32F446 flash interface with the user option bytes (RM0390 Rev 6 3.6.2, 3.8): FLASH_ACR, KEYR,
//                  OPTKEYR, SR (BSY), CR (LOCK), OPTCR, and the option bytes at 0x1FFFC000 (RDP + USER, nWRP). The
//                  option bytes are non-volatile: an MCU reset (machine Reset) loads FLASH_OPTCR from them again and
//                  keeps them. OPTSTRT keeps BSY set for ProgramMs of virtual time, then writes FLASH_OPTCR's option
//                  bits into the option bytes (the whole user option sector, as the note in 3.6.2 says). A wrong
//                  OPTKEYR sequence keeps OPTLOCK set until the next reset (3.8.6). Renode 1.17.0's
//                  STM32F4_FlashController has BOR_LEV only as a tag and no BSY, so it cannot test this.
//                  Factory value 0x0FFFAAEC (= the FLASH_OPTCR reset value 0x0FFFAAED without OPTLOCK): BOR off.
//                  Not modelled: main-flash program / erase (the custom boards keep their config in the FRAM).
//   PDM_IWDG     - independent watchdog (RM0390 19): KR keys 0xCCCC start, 0xAAAA reload, 0x5555 PR / RLR access;
//                  counter clock = LSI (Frequency) / (4 << PR), reset of the machine when it reaches 0. PR / RLR
//                  are used from the next reload (the firmware waits for PVU / RVU, SR reads 0 here). Bench counters:
//                  Resets (kept over a machine reset), Refreshes, MaxGapMs (longest time between two reloads while PR
//                  is RunPrescaler), SleepRefreshes (reloads while PR is not RunPrescaler: the RTC wake-ups in STOP).
//                  Renode's STM32_IndependentWatchdog has none of these counters and no settable LSI.
//
using System;
using Antmicro.Renode.Core;
using Antmicro.Renode.Logging;
using Antmicro.Renode.Peripherals.Bus;
using Antmicro.Renode.Peripherals.Timers;
using Antmicro.Renode.Time;

namespace Antmicro.Renode.Peripherals.Miscellaneous
{
    public class PDM_FlashOpt : IDoubleWordPeripheral, IKnownSize
    {
        public PDM_FlashOpt(IMachine machine)
        {
            this.machine = machine; OptionBytes = 0x0FFFAAEC; ProgramMs = 20.0; Reset();
        }

        public long Size { get { return 0x400; } }
        public uint OptionBytes { get; set; }       // bits 31:2 as FLASH_OPTCR shows them (bits 1:0 are control bits)
        public double ProgramMs { get; set; }
        public ulong ProgramCount { get; private set; }
        public ulong FailedUnlocks { get; private set; }
        public uint BorLevelBits { get { return (OptionBytes >> 2) & 3U; } }   // 0 = level 3, 3 = off

        public void Reset()
        {
            acr = 0; cr = 0x80000000U; optcr = OptionBytes & ~3U; optLocked = true; keyStep = 0; optKeyStep = 0;
            optLockedForGood = false; busy = false;
        }

        public uint ReadDoubleWord(long offset)
        {
            switch(offset)
            {
                case 0x00: return acr;
                case 0x0C: return busy ? (1U << 16) : 0U;
                case 0x10: return cr;
                case 0x14: return optcr | (optLocked ? 1U : 0U) | (busy ? 2U : 0U);
                default: return 0;
            }
        }

        public void WriteDoubleWord(long offset, uint value)
        {
            switch(offset)
            {
                case 0x00: acr = value; break;
                case 0x04:                                          // FLASH_KEYR
                    if(keyStep == 0 && value == 0x45670123U) keyStep = 1;
                    else if(keyStep == 1 && value == 0xCDEF89ABU) { cr &= ~0x80000000U; keyStep = 0; }
                    else keyStep = 0;
                    break;
                case 0x08:                                          // FLASH_OPTKEYR
                    if(optLockedForGood) break;
                    if(optKeyStep == 0 && value == 0x08192A3BU) optKeyStep = 1;
                    else if(optKeyStep == 1 && value == 0x4C5D6E7FU) { optLocked = false; optKeyStep = 0; }
                    else { optKeyStep = 0; optLockedForGood = true; FailedUnlocks++; }
                    break;
                case 0x0C: break;                                   // SR: error flags rc_w1, none raised here
                case 0x10: if((cr & 0x80000000U) == 0 || (value & 0x80000000U) != 0) cr = value; break;
                case 0x14:                                          // FLASH_OPTCR
                    if((value & 1U) != 0) { optLocked = true; }
                    if(optLocked || busy) { if(!optLocked) this.Log(LogLevel.Warning, "OPTCR write while busy"); break; }
                    optcr = value & 0x8FFFFFECU;
                    if((value & 2U) != 0) StartProgram();
                    break;
            }
        }

        [ConnectionRegion("optionBytes")]
        public uint ReadDoubleWordFromOptionBytes(long offset)
        {
            // 0x1FFFC000: RDP (15:8) + USER (7:5) + BOR_LEV (3:2); 0x1FFFC008: nWRP (11:0) + SPRMOD (15)
            if(offset == 0x0) return OptionBytes & 0xFFFCU;
            if(offset == 0x8) return ((OptionBytes >> 16) & 0xFFFU) | ((OptionBytes >> 16) & 0x8000U);
            return 0xFFFFFFFFU;
        }

        [ConnectionRegion("optionBytes")]
        public void WriteDoubleWordToOptionBytes(long offset, uint value)
        {
            this.Log(LogLevel.Warning, "Direct write 0x{0:X8} to the option bytes at +0x{1:X} ignored", value, offset);
        }

        private void StartProgram()
        {
            busy = true;
            var bits = optcr;
            machine.ScheduleAction(TimeInterval.FromMilliseconds((ulong)Math.Max(1, ProgramMs)), _ =>
            {
                OptionBytes = bits & ~3U; ProgramCount++; busy = false;
                this.Log(LogLevel.Info, "option bytes programmed: 0x{0:X8} (BOR_LEV {1})", OptionBytes, BorLevelBits);
            });
        }

        private readonly IMachine machine;
        private uint acr, cr, optcr;
        private bool optLocked, optLockedForGood, busy;
        private int keyStep, optKeyStep;
    }

    public class PDM_IWDG : IDoubleWordPeripheral, IKnownSize
    {
        public PDM_IWDG(IMachine machine, long frequency = 32000, uint runPrescaler = 3)
        {
            this.machine = machine; RunPrescaler = runPrescaler;
            timer = new LimitTimer(machine.ClockSource, frequency, this, "iwdg", 0xFFF, Direction.Descending, false,
                WorkMode.OneShot, true, true, 4);
            timer.LimitReached += () =>
            {
                Resets++; Running = false; timer.Enabled = false;
                this.Log(LogLevel.Warning, "watchdog reset (PR {0}, RLR {1})", pr, rlr);
                machine.RequestReset();
            };
            Reset();
        }

        public long Size { get { return 0x400; } }
        public long Frequency { get { return timer.Frequency; } set { timer.Frequency = value; } }   // LSI
        public uint RunPrescaler { get; set; }
        public bool Running { get; private set; }
        public ulong Resets { get; private set; }
        public ulong Refreshes { get; private set; }
        public ulong SleepRefreshes { get; private set; }
        public double MaxGapMs { get; private set; }
        public double LastRefreshMs { get; private set; }
        public uint Prescaler { get { return pr; } }
        public uint ReloadValue { get { return rlr; } }
        public double TimeoutMs { get { return (4U << (int)pr) * (rlr + 1.0) * 1000.0 / timer.Frequency; } }
        public void ClearStats() { MaxGapMs = 0; Refreshes = 0; SleepRefreshes = 0; }

        public void Reset()
        {
            // a system reset stops the IWDG (software watchdog, WDG_SW = 1) and loads the reset values
            timer.Enabled = false; Running = false; access = false; pr = 0; rlr = 0xFFF; pendPr = 0; pendRlr = 0xFFF;
        }

        public uint ReadDoubleWord(long offset)
        {
            switch(offset)
            {
                case 0x4: return pendPr;
                case 0x8: return pendRlr;
                default: return 0;                                  // SR: PVU / RVU done at once
            }
        }

        public void WriteDoubleWord(long offset, uint value)
        {
            switch(offset)
            {
                case 0x0:
                    var key = value & 0xFFFFU;
                    if(key == 0x5555U) { access = true; break; }
                    access = false;
                    if(key == 0xCCCCU)
                    {
                        if(!Running) { Running = true; Load(); timer.Enabled = true; LastRefreshMs = NowMs(); }
                    }
                    else if(key == 0xAAAAU && Running) Refresh();
                    break;
                case 0x4: if(access) pendPr = value & 7U; break;
                case 0x8: if(access) pendRlr = value & 0xFFFU; break;
            }
        }

        private void Load()
        {
            pr = pendPr; rlr = pendRlr;
            timer.Divider = (int)Math.Min(256U, 4U << (int)pr);
            timer.Limit = rlr; timer.Value = rlr;
        }

        private void Refresh()
        {
            var now = NowMs();
            if(pr == RunPrescaler) { var gap = now - LastRefreshMs; if(gap > MaxGapMs) MaxGapMs = gap; Refreshes++; }
            else SleepRefreshes++;
            LastRefreshMs = now;
            Load();
        }

        private double NowMs() { return machine.LocalTimeSource.ElapsedVirtualTime.TotalMilliseconds; }

        private readonly IMachine machine;
        private readonly LimitTimer timer;
        private bool access;
        private uint pr, rlr, pendPr, pendRlr;
    }
}
