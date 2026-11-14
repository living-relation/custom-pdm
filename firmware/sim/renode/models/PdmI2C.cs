//
// custom-pdm Renode bench models: STM32F4 I2C (I2Cv1) controller with DMA, FRAM, MCP9808.
//
// Why a new controller model: Renode 1.17.0's STM32F1_I2C leaves DMAEN/LAST unimplemented and clears ADDR on any
// SR2 read. The ChibiOS I2Cv1 driver (os/hal/ports/STM32/LLD/I2Cv1/hal_i2c_lld.c @ 879cf757) moves all data by DMA
// and reads SR2 before SR1 in its event handler, so it cannot work with the stock model.
// This model implements only the master-mode behaviour that driver uses (RM0390 I2C section):
//   START -> SB; address write -> ADDR (+TRA, TxE when transmitting) or AF when nobody answers;
//   ADDR is cleared by an SR1 read (that saw ADDR) followed by an SR2 read;
//   transmit: bytes written to DR are collected, BTF + TxE rise 9 bit times per byte later;
//   receive: one byte per 9 bit times into DR with a DMA request, until the RX DMA stream count reaches zero
//            (stands in for the DMA end-of-transfer signal that goes with LAST);
//   STOP / repeated START hand the collected bytes to the target.
// A target that refuses its address (PDM_MCP9808.Nak) gets AF, as when nobody answers.
// Not modelled: slave mode, 10-bit addressing, SMBus, PEC, clock stretching, bus errors, arbitration, CCR timing.
//
using System;
using System.Collections.Generic;
using System.IO;
using Antmicro.Renode.Core;
using Antmicro.Renode.Core.Structure;
using Antmicro.Renode.Logging;
using Antmicro.Renode.Peripherals.Bus;
using Antmicro.Renode.Peripherals.Timers;
using Antmicro.Renode.Time;

namespace Antmicro.Renode.Peripherals.I2C
{
    public class PDM_I2Cv1 : SimpleContainer<II2CPeripheral>, IDoubleWordPeripheral, IWordPeripheral, IBytePeripheral, IKnownSize
    {
        // the DMA model moves bytes to and from DR with byte accesses
        public byte ReadByte(long offset) { return (byte)ReadDoubleWord(offset); }
        public void WriteByte(long offset, byte value) { WriteDoubleWord(offset, value); }

        // rxDmaStreamCr: bus address of the CR register of the DMA stream used for I2C RX (NDTR is at +4).
        public PDM_I2Cv1(IMachine machine, ulong rxDmaStreamCr, ulong busFrequency = 400000) : base(machine)
        {
            this.rxDmaStreamCr = rxDmaStreamCr;
            timer = new LimitTimer(machine.ClockSource, busFrequency, this, "byteClock", limit: 9, direction: Direction.Ascending,
                enabled: false, workMode: WorkMode.OneShot, eventEnabled: true, autoUpdate: false);
            timer.LimitReached += OnTimer;
            EventInterrupt = new GPIO(); ErrorInterrupt = new GPIO(); RxDMARequest = new GPIO();
            ResetState(true);
        }

        public override void Reset() { lock(sync) { ResetState(true); } }

        public GPIO EventInterrupt { get; private set; }
        public GPIO ErrorInterrupt { get; private set; }
        public GPIO RxDMARequest { get; private set; }
        public long Size { get { return 0x400; } }
        public ulong Transfers { get; private set; }
        public ulong AckFailures { get; private set; }

        public ushort ReadWord(long offset) { return (ushort)ReadDoubleWord(offset); }
        public void WriteWord(long offset, ushort value) { WriteDoubleWord(offset, value); }

        public uint ReadDoubleWord(long offset)
        {
            lock(sync)
            {
                switch(offset)
                {
                case 0x00: return cr1;
                case 0x04: return cr2;
                case 0x08: return oar1;
                case 0x0C: return oar2;
                case 0x10:
                    var v = dr; rxne = false; btf = false;
                    if(state == St.Rx && (cr2 & DMAEN) == 0) Arm(1);
                    Update(); return v;
                case 0x14:
                    if(addr) addrSeen = true;
                    return (sb ? 1u : 0) | (addr ? 2u : 0) | (btf ? 4u : 0) | (rxne ? 0x40u : 0) | (txe ? 0x80u : 0) | (af ? 0x400u : 0);
                case 0x18:
                    var r = (msl ? 1u : 0) | (busy ? 2u : 0) | (tra ? 4u : 0);
                    if(addr && addrSeen)
                    {
                        addr = false; addrSeen = false;
                        if(state == St.AddrTx) state = St.Tx;
                        else if(state == St.AddrRx) { state = St.Rx; Arm(1); }
                        Update();
                    }
                    return r;
                case 0x1C: return ccr;
                case 0x20: return trise;
                default: return 0;
                }
            }
        }

        public void WriteDoubleWord(long offset, uint value)
        {
            lock(sync)
            {
                switch(offset)
                {
                case 0x00:
                    if((value & SWRST) != 0) { ResetState(false); cr1 = SWRST; break; }
                    cr1 = value & ~(START | STOP);
                    if((value & STOP) != 0) DoStop();
                    if((value & START) != 0) DoStart();
                    Update();
                    break;
                case 0x04: cr2 = value & 0x1F3F; Update(); break;
                case 0x08: oar1 = value; break;
                case 0x0C: oar2 = value; break;
                case 0x10: WriteData((byte)value); Update(); break;
                case 0x14: if((value & 0x400) == 0) af = false; Update(); break;
                case 0x1C: ccr = value; break;
                case 0x20: trise = value; break;
                default: break;
                }
            }
        }

        private void ResetState(bool full)
        {
            if(timer != null) timer.Enabled = false;
            if(child != null && state != St.Idle) child.FinishTransmission();
            child = null; state = St.Idle; tx.Clear(); pendingTx = 0;
            sb = addr = btf = rxne = txe = af = msl = busy = tra = addrSeen = false;
            cr1 = cr2 = oar1 = oar2 = ccr = dr = 0; trise = 2;
            if(full) { Transfers = 0; AckFailures = 0; }
            if(EventInterrupt != null) Update();
        }

        private void DoStart()
        {
            if(tx.Count > 0 && child != null) { child.Write(tx.ToArray()); }
            tx.Clear(); pendingTx = 0; timer.Enabled = false;
            sb = true; msl = true; busy = true; tra = false; txe = false; btf = false; addr = false; rxne = false; addrSeen = false;
            state = St.Address;
        }

        private void DoStop()
        {
            if(tx.Count > 0 && child != null) { child.Write(tx.ToArray()); }
            tx.Clear(); pendingTx = 0; timer.Enabled = false;
            if(child != null) { child.FinishTransmission(); Transfers++; }
            child = null; state = St.Idle;
            sb = addr = btf = rxne = txe = msl = busy = tra = addrSeen = false;
        }

        private void WriteData(byte value)
        {
            switch(state)
            {
            case St.Address:
                sb = false;
                if(!TryGetByAddress(value >> 1, out child) || (child is PDM_MCP9808 && ((PDM_MCP9808)child).Nak))
                {
                    child = null; af = true; AckFailures++;
                    this.Log(LogLevel.Warning, "No I2C target at 0x{0:X}: acknowledge failure", value >> 1);
                    break;
                }
                addr = true; addrSeen = false;
                if((value & 1) == 0) { tra = true; txe = true; state = St.AddrTx; }
                else { tra = false; state = St.AddrRx; }
                break;
            case St.AddrTx:
            case St.Tx:
                tx.Add(value); txe = false; btf = false; pendingTx++;
                Arm(pendingTx);
                break;
            default:
                this.Log(LogLevel.Warning, "DR written in state {0}, ignored", state);
                break;
            }
        }

        private void OnTimer()
        {
            lock(sync)
            {
                if(state == St.Tx || state == St.AddrTx) { pendingTx = 0; txe = true; btf = true; Update(); }
                else if(state == St.Rx) RxByte();
            }
        }

        private void RxByte()
        {
            if(rxne || child == null) { Arm(1); return; }
            if((cr2 & DMAEN) == 0)
            {
                dr = First(child.Read(1)); rxne = true; Update(); return;
            }
            var bus = machine.SystemBus;
            var streamOn = (bus.ReadDoubleWord(rxDmaStreamCr) & 1) != 0;
            var left = bus.ReadDoubleWord(rxDmaStreamCr + 4) & 0xFFFF;
            if(!streamOn || left == 0) { Arm(1); return; }      // DMA not ready yet: the bus waits
            dr = First(child.Read(1)); rxne = true;
            RxDMARequest.Set(true); RxDMARequest.Set(false);     // the DMA model reads DR now
            if(left > 1) Arm(1);                                 // after the last byte: NACK, wait for STOP
        }

        private static byte First(byte[] b) { return (b != null && b.Length > 0) ? b[0] : (byte)0xFF; }

        private void Arm(ulong bytes)
        {
            timer.Enabled = false; timer.Limit = 9 * bytes; timer.ResetValue(); timer.Enabled = true;
        }

        private void Update()
        {
            var ev = sb || addr || btf || ((cr2 & ITBUFEN) != 0 && (txe || rxne));
            EventInterrupt.Set((cr2 & ITEVTEN) != 0 && ev);
            ErrorInterrupt.Set((cr2 & ITERREN) != 0 && af);
        }

        private enum St { Idle, Address, AddrTx, AddrRx, Tx, Rx }
        private St state;
        private II2CPeripheral child;
        private readonly List<byte> tx = new List<byte>();
        private ulong pendingTx;
        private bool sb, addr, btf, rxne, txe, af, msl, busy, tra, addrSeen;
        private uint cr1, cr2, oar1, oar2, ccr, trise, dr;
        private readonly LimitTimer timer;
        private readonly ulong rxDmaStreamCr;
        private readonly object sync = new object();
        private const uint START = 1 << 8, STOP = 1 << 9, SWRST = 1 << 15;
        private const uint ITERREN = 1 << 8, ITEVTEN = 1 << 9, ITBUFEN = 1 << 10, DMAEN = 1 << 11;
    }

    // Fujitsu MB85RC256V-style I2C FRAM: a write starts with two address bytes (high, low), data follows;
    // a read continues from the current address; the address wraps at the end of the array.
    // Contents survive machine Reset (non-volatile). Device-ID (0xF8) access is not modelled (the firmware skips it).
    public class PDM_FRAM : II2CPeripheral
    {
        public PDM_FRAM(int size = 32768, byte fill = 0xFF)
        {
            memory = new byte[size];
            Erase(fill);
        }

        public void Reset() { inTransaction = false; }

        public void Write(byte[] data)
        {
            var i = 0;
            if(!inTransaction)
            {
                if(data.Length < 2) { this.Log(LogLevel.Warning, "FRAM write shorter than the 2 address bytes"); return; }
                address = ((data[0] << 8) | data[1]) % memory.Length; i = 2; inTransaction = true;
            }
            for(; i < data.Length; i++) { memory[address] = data[i]; address = (address + 1) % memory.Length; BytesWritten++; }
        }

        public byte[] Read(int count = 1)
        {
            var r = new byte[count];
            for(var i = 0; i < count; i++) { r[i] = memory[address]; address = (address + 1) % memory.Length; BytesRead++; }
            return r;
        }

        public void FinishTransmission() { inTransaction = false; }

        public void Erase(byte fill = 0xFF) { for(var i = 0; i < memory.Length; i++) memory[i] = fill; }
        public void Save(string path) { File.WriteAllBytes(path, memory); }
        public void Load(string path) { var b = File.ReadAllBytes(path); Array.Copy(b, memory, Math.Min(b.Length, memory.Length)); }
        public byte Peek(int addr) { return memory[addr % memory.Length]; }
        public void Poke(int addr, byte value) { memory[addr % memory.Length] = value; }
        public uint Checksum(int length) { uint s = 0; for(var i = 0; i < length && i < memory.Length; i++) s = s * 31 + memory[i]; return s; }
        public ulong BytesWritten { get; private set; }
        public ulong BytesRead { get; private set; }

        private readonly byte[] memory;
        private int address;
        private bool inTransaction;
    }

    // Microchip MCP9808 stand-in (DS25095A): register pointer, 16-bit registers 1..7 (MSB first), 8-bit resolution
    // register 8. Manufacturer ID 0x0054, device ID / revision 0x0400. Limit registers keep bits 12..2. The ambient
    // register carries the three alert flags (bit 15 Ta >= Tcrit, bit 14 Ta > Tupper, bit 13 Ta < Tlower).
    // CONFIG (Register 5-2): lock bits 7 / 6 stay set until PowerOnReset; while either is set THYST, Alert Cnt.,
    // Alert Pol. and Alert Mod. keep their value and SHDN cannot be set (it can be cleared); window lock also keeps
    // Alert Sel.; Tcrit lock blocks writes to Tcrit, window lock to Tupper / Tlower. Bits 4 / 5 are not stored.
    // Shutdown (SHDN): no conversions, the ambient register keeps the last value. After power-on (TA = 0, Table 5-3)
    // and after SHDN is cleared the ambient register keeps its old value for ConversionMs (tCONV 30 ms typ at 0.5 C).
    // Reset() is an MCU reset: the sensor has no reset pin, so registers, locks and shutdown survive it.
    // Nak = true: the sensor does not acknowledge its address (the controller model reports AF).
    // Not modelled: hysteresis, the alert pin itself (AlertEnabled shows Alert Cnt.), resolution-dependent timing.
    public class PDM_MCP9808 : II2CPeripheral
    {
        public PDM_MCP9808(IMachine machine, double temperature = 30.0)
        {
            this.machine = machine; Temperature = temperature; ConversionMs = 30.0; PowerOnReset();
        }

        public void Reset() { pointer = 0; readIndex = 0; }

        public void PowerOnReset()
        {
            Reset(); config = 0; upper = 0; lower = 0; crit = 0; resolution = 3;
            held = 0.0; convStartMs = NowMs(); ShutdownWrites = 0; RejectedShutdowns = 0;
        }

        public double Temperature { get; set; }
        public double ConversionMs { get; set; }
        public bool Nak { get; set; }
        public bool Shutdown { get { return (config & SHDN) != 0; } }
        public bool AlertEnabled { get { return (config & ALERTCNT) != 0; } }
        public bool Locked { get { return (config & (CRITLOCK | WINLOCK)) != 0; } }
        public uint Config { get { return config; } }
        public ulong ShutdownWrites { get; private set; }     // writes that put the sensor into shutdown
        public ulong RejectedShutdowns { get; private set; }  // SHDN = 1 written while a lock bit was set

        public void Write(byte[] data)
        {
            if(data.Length == 0) return;
            pointer = data[0] & 0x0F; readIndex = 0;
            if(data.Length == 2 && pointer == 8) resolution = (byte)(data[1] & 3);
            if(data.Length >= 3)
            {
                var v = (ushort)((data[1] << 8) | data[2]);
                switch(pointer)
                {
                case 1: WriteConfig(v); break;
                case 2: if((config & WINLOCK) == 0) upper = (ushort)(v & 0x1FFC); break;
                case 3: if((config & WINLOCK) == 0) lower = (ushort)(v & 0x1FFC); break;
                case 4: if((config & CRITLOCK) == 0) crit = (ushort)(v & 0x1FFC); break;
                default: break;
                }
            }
        }

        public byte[] Read(int count = 1)
        {
            var r = new byte[count];
            for(var i = 0; i < count; i++)
            {
                if(pointer == 8) r[i] = resolution;
                else { var v = Reg(pointer); r[i] = (readIndex % 2 == 0) ? (byte)(v >> 8) : (byte)v; }
                readIndex++;
            }
            return r;
        }

        public void FinishTransmission() { readIndex = 0; }

        private void WriteConfig(ushort v)
        {
            var n = (ushort)(v & 0x07CF);
            if(Locked)
            {
                const ushort keep = THYST | ALERTCNT | ALERTPOL | ALERTMOD;
                n = (ushort)((n & ~keep) | (config & keep));
                if((n & SHDN) != 0 && (config & SHDN) == 0) { n = (ushort)(n & ~SHDN); RejectedShutdowns++; }
            }
            if((config & WINLOCK) != 0) n = (ushort)((n & ~ALERTSEL) | (config & ALERTSEL));
            n = (ushort)(n | (config & (CRITLOCK | WINLOCK)));
            var was = (config & SHDN) != 0; var now = (n & SHDN) != 0;
            if(!was && now) { held = Ambient(); ShutdownWrites++; }
            if(was && !now) convStartMs = NowMs();
            config = n;
        }

        private double Ambient()
        {
            if(Shutdown || NowMs() - convStartMs < ConversionMs) return held;
            return Temperature;
        }

        private double NowMs() { return machine.LocalTimeSource.ElapsedVirtualTime.TotalMilliseconds; }

        private ushort Reg(int p)
        {
            switch(p)
            {
            case 1: return config;
            case 2: return upper;
            case 3: return lower;
            case 4: return crit;
            case 5:
                var t = Ambient();
                if(!Shutdown) held = t;
                var raw = (int)Math.Round(t * 16.0);
                var v = (ushort)(raw & 0x1FFF);
                if(t >= Limit(crit)) v |= 0x8000;
                if(t > Limit(upper)) v |= 0x4000;
                if(t < Limit(lower)) v |= 0x2000;
                return v;
            case 6: return 0x0054;
            case 7: return 0x0400;
            default: return 0;
            }
        }

        private static double Limit(ushort reg)
        {
            double t = (reg & 0x0FFF) / 16.0;
            if((reg & 0x1000) != 0) t -= 256.0;
            return t;
        }

        private readonly IMachine machine;
        private int pointer, readIndex;
        private ushort config, upper, lower, crit;
        private byte resolution;
        private double held, convStartMs;
        private const ushort THYST = 0x0600, SHDN = 0x0100, CRITLOCK = 0x0080, WINLOCK = 0x0040;
        private const ushort ALERTCNT = 0x0008, ALERTSEL = 0x0004, ALERTPOL = 0x0002, ALERTMOD = 0x0001;
    }
}
