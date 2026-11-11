//
// custom-pdm Renode bench: correction for ICSR.RETTOBASE in Renode 1.17.0's NVIC model.
//
// ARMv7-M (ICSR, bit 11): in Handler mode RETTOBASE is 1 only when no exception other than the current one is active.
// Renode 1.17.0 (Cores/Arm-M/NVIC.cs, renode-infrastructure 066a7f1) computes it from the active *system* exceptions
// only, so it also reads 1 inside an external interrupt that has preempted another external interrupt.
// ChibiOS (os/common/ports/ARMv7-M/chcore.c, __port_irq_epilogue) uses that bit to decide whether an interrupt
// returns to a thread; with the wrong value it builds its context-switch frame while still nested and the kernel
// ready list gets corrupted (seen here as a HardFault, INVSTATE, in __port_switch about 1 s after start).
// This object hooks reads of ICSR and replaces bit 11 with "at most one active exception", taken from the NVIC's
// own list of active exceptions (private field, read by reflection). Nothing else is changed.
//
using System;
using System.Collections.Generic;
using System.Reflection;
using Antmicro.Renode.Core;
using Antmicro.Renode.Exceptions;
using Antmicro.Renode.Peripherals.Bus;
using Antmicro.Renode.Peripherals.IRQControllers;

namespace Antmicro.Renode.Peripherals.Miscellaneous
{
    public class PDM_NvicRettobaseFix : IDoubleWordPeripheral, IKnownSize
    {
        public PDM_NvicRettobaseFix(IMachine machine, NVIC nvic)
        {
            this.machine = machine; this.nvic = nvic; Enabled = true;
            field = typeof(NVIC).GetField("activeIRQs", BindingFlags.NonPublic | BindingFlags.Instance);
        }

        // Call once after the platform is loaded.
        public void Install()
        {
            if(installed) return;
            if(field == null) throw new RecoverableException("NVIC.activeIRQs not found: this fix was written for Renode 1.17.0");
            machine.SystemBus.SetHookAfterPeripheralRead<uint>(nvic, Fix);
            installed = true;
        }

        public bool Enabled { get; set; }
        public ulong Corrections { get; private set; }   // reads where Renode's value was wrong
        public ulong Reads { get; private set; }

        public long Size { get { return 4; } }
        public uint ReadDoubleWord(long offset) { return 0; }
        public void WriteDoubleWord(long offset, uint value) { }
        public void Reset() { }

        private uint Fix(uint value, long offset)
        {
            if((offset & 0xFFF) != 0xD04) return value;
            Reads++;
            var active = ((Stack<int>)field.GetValue(nvic)).Count;
            var correct = active <= 1;
            if(correct == ((value & Rettobase) != 0)) return value;
            Corrections++;
            if(!Enabled) return value;
            return correct ? (value | Rettobase) : (value & ~Rettobase);
        }

        private readonly IMachine machine;
        private readonly NVIC nvic;
        private readonly FieldInfo field;
        private bool installed;
        private const uint Rettobase = 1u << 11;
    }
}
