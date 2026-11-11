//
// custom-pdm Renode bench: remembers the last value the firmware wrote to one register of another peripheral.
// Used for CAN_BTR: Renode's STMCAN (like the real bxCAN) only lets BTR be read in initialization mode,
// so the tests take the bit timing from what the firmware wrote.
//
using Antmicro.Renode.Core;
using Antmicro.Renode.Peripherals.Bus;

namespace Antmicro.Renode.Peripherals.Miscellaneous
{
    public class PDM_WriteSpy : IDoubleWordPeripheral, IKnownSize
    {
        public PDM_WriteSpy(IMachine machine, IBusPeripheral target, long offset)
        {
            this.machine = machine; this.target = target; this.offset = offset;
        }

        // Call once after the platform is loaded.
        public void Install()
        {
            if(installed) return;
            machine.SystemBus.SetHookBeforePeripheralWrite<uint>(target, Spy);
            installed = true;
        }

        public uint LastValue { get; private set; }
        public ulong Writes { get; private set; }

        public long Size { get { return 4; } }
        public uint ReadDoubleWord(long off) { return 0; }
        public void WriteDoubleWord(long off, uint value) { }
        public void Reset() { LastValue = 0; Writes = 0; }

        private uint Spy(uint value, long off)
        {
            if((off & 0x3FF) == offset) { LastValue = value; Writes++; }
            return value;
        }

        private readonly IMachine machine;
        private readonly IBusPeripheral target;
        private readonly long offset;
        private bool installed;
    }
}
