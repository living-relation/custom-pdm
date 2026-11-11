//
// custom-pdm Renode bench models: ADC1 with the PROFET current-sense plant, and a CAN test node (ECU + PC tool).
//
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text;
using Antmicro.Renode.Core;
using Antmicro.Renode.Core.CAN;
using Antmicro.Renode.Logging;
using Antmicro.Renode.Peripherals.Bus;
using Antmicro.Renode.Peripherals.CAN;
using Antmicro.Renode.Peripherals.GPIOPort;
using Antmicro.Renode.Peripherals.Timers;
using Antmicro.Renode.Time;

namespace Antmicro.Renode.Peripherals.Analog
{
    // STM32F446 ADC1 as the ChibiOS ADCv2 driver uses it: software start, scan of the regular sequence,
    // continuous mode, one DMA request per conversion (the DMA stream is circular).
    // Why not Renode's STM32_ADC: its conversion time is fixed at 100 us and its samples come from queues,
    // while the firmware needs a whole scan well inside the 60 us it waits after switching DSEL, and the
    // sense voltage depends on pin states at the moment of sampling.
    // Timing: one event per scan, after sum(sampling cycles + 12) ADC clocks (RM0390: Tconv = sampling + 12 cycles
    // at 12 bit); all channels of a scan are sampled at that instant. ADC clock = pclk2 / ADCPRE (ADC_CCR).
    // Voltages: per-pin volts set from the monitor, plus the PROFET sense current into 1.2 k (same rule as
    // firmware/sim/sim_core.cpp chanVolts). Channel to pin: IN0-7 = PA0-7, IN8-9 = PB0-1, IN10-15 = PC0-5 (DS10693).
    // Not modelled: analog watchdog, injected channels, overrun, external triggers, resolution other than 12 bit,
    // noise, settling. Channels 16 and 18 both return the die-temperature voltage; 17 returns VREFINT (1.21 V).
    public class PDM_ADC : IDoubleWordPeripheral, IWordPeripheral, IKnownSize
    {
        // the DMA model reads DR with 16-bit accesses (PSIZE = half word)
        public ushort ReadWord(long offset) { return (ushort)ReadDoubleWord(offset); }
        public void WriteWord(long offset, ushort value) { WriteDoubleWord(offset, value); }

        public PDM_ADC(IMachine machine, STM32_GPIOPort portA, STM32_GPIOPort portB, STM32_GPIOPort portC, STM32_GPIOPort portD = null, ulong pclk2 = 36000000)
        {
            ports = new[] { portA, portB, portC, portD };
            this.pclk2 = pclk2;
            DMARequest = new GPIO(); IRQ = new GPIO();
            timer = new LimitTimer(machine.ClockSource, pclk2 / 2, this, "scanClock", limit: 100, direction: Direction.Ascending,
                enabled: false, workMode: WorkMode.OneShot, eventEnabled: true, autoUpdate: false);
            timer.LimitReached += OnScan;
            Vbat = 13.8; Vdda = 3.3; DieTemperature = 30.0; SenseClamp = 3.3; SenseResistor = 1200.0;
            Reset();
        }

        public void Reset()
        {
            timer.Enabled = false;
            regs.Clear(); sr = cr1 = cr2 = dr = ccr = 0; Scans = 0;
        }

        public GPIO DMARequest { get; private set; }
        public GPIO IRQ { get; private set; }
        public long Size { get { return 0x400; } }
        public double Vbat { get; set; }
        public double Vdda { get; set; }
        public double DieTemperature { get; set; }
        public double SenseClamp { get; set; }
        public double SenseResistor { get; set; }
        public ulong Scans { get; private set; }
        // 1 = real scan period. A larger value makes every scan (and its DMA interrupt) that many times slower.
        public ulong ScanStretch { get; set; }

        // ---- plant, driven from the monitor -------------------------------------------------------------
        // Pins are given as "PB10"; dselPin "" = single-channel part. Returns the output index.
        public int AddOutput(string inPin, string denPin, string dselPin, int dselLevel, string isPin, double kilis)
        {
            var o = new Output { In = Pin(inPin), Den = Pin(denPin), Dsel = string.IsNullOrEmpty(dselPin) ? -1 : Pin(dselPin),
                                 DselLevel = dselLevel != 0, Channel = ChannelOf(isPin), Kilis = kilis };
            outputs.Add(o); return outputs.Count - 1;
        }
        public void SetLoad(int output, double ohms) { outputs[output].Ohms = ohms; }
        public void SetFault(int output, bool fault) { outputs[output].Fault = fault; }
        public void SetPinVolts(string pin, double volts) { pinVolts[ChannelOf(pin)] = volts; }
        public bool OutputLevel(int output) { return Level(outputs[output].In); }
        // bit n = IN pin of output n is driven high
        public uint OutputsOn() { uint m = 0; for(var i = 0; i < outputs.Count; i++) if(Level(outputs[i].In)) m |= 1u << i; return m; }
        public double OutputAmps(int output) { var o = outputs[output]; return (Level(o.In) && o.Ohms > 0) ? Vbat / o.Ohms : 0; }
        public bool PinLevel(string pin) { return Level(Pin(pin)); }
        public uint LastRaw(uint channel) { return Sample((int)channel); }

        // ---- registers ----------------------------------------------------------------------------------
        public uint ReadDoubleWord(long offset)
        {
            lock(sync)
            {
                switch(offset)
                {
                case 0x00: return sr;
                case 0x04: return cr1;
                case 0x08: return cr2;
                case 0x4C: sr &= ~EOC; return dr;
                case 0x304: return ccr;
                default: uint v; return regs.TryGetValue(offset, out v) ? v : 0;
                }
            }
        }

        public void WriteDoubleWord(long offset, uint value)
        {
            lock(sync)
            {
                switch(offset)
                {
                case 0x00: sr &= value; break;
                case 0x04: cr1 = value; break;
                case 0x08:
                    cr2 = value & ~SWSTART;
                    if((cr2 & ADON) == 0) timer.Enabled = false;
                    else if((value & SWSTART) != 0) StartScan();
                    break;
                case 0x304: ccr = value; break;
                default: regs[offset] = value; break;
                }
            }
        }

        private uint Reg(long offset) { uint v; return regs.TryGetValue(offset, out v) ? v : 0; }

        private int SequenceLength { get { return (int)((Reg(0x2C) >> 20) & 0xF) + 1; } }

        private int SequenceChannel(int slot)
        {
            if(slot < 6) return (int)((Reg(0x34) >> (5 * slot)) & 31);
            if(slot < 12) return (int)((Reg(0x30) >> (5 * (slot - 6))) & 31);
            return (int)((Reg(0x2C) >> (5 * (slot - 12))) & 31);
        }

        private static readonly int[] SampleCycles = { 3, 15, 28, 56, 84, 112, 144, 480 };

        private void StartScan()
        {
            ulong cycles = 0;
            for(var i = 0; i < SequenceLength; i++)
            {
                var ch = SequenceChannel(i);
                var smp = ch < 10 ? (Reg(0x10) >> (3 * ch)) & 7 : (Reg(0x0C) >> (3 * (ch - 10))) & 7;
                cycles += (ulong)SampleCycles[smp] + 12;
            }
            var prescaler = 2 * (((ccr >> 16) & 3) + 1);
            timer.Enabled = false; timer.Frequency = pclk2 / prescaler; timer.Limit = cycles * Math.Max(1, ScanStretch); timer.ResetValue(); timer.Enabled = true;
            sr |= STRT;
        }

        private void OnScan()
        {
            lock(sync)
            {
                if((cr2 & ADON) == 0) return;
                var n = SequenceLength;
                for(var i = 0; i < n; i++)
                {
                    dr = Sample(SequenceChannel(i));
                    sr |= EOC;
                    if((cr2 & DMA) != 0) { DMARequest.Set(true); DMARequest.Set(false); }
                }
                Scans++;
                if((cr2 & CONT) != 0) { timer.ResetValue(); timer.Enabled = true; }
            }
        }

        private uint Sample(int ch)
        {
            var raw = (int)(ChannelVolts(ch) / Vdda * 4095.0 + 0.5);
            return (uint)Math.Max(0, Math.Min(4095, raw));
        }

        private double ChannelVolts(int ch)
        {
            if(ch == 17) return 1.21;
            if(ch == 16 || ch == 18) return 0.76 + (DieTemperature - 25.0) * 0.0025;
            if(ch > 15) return 0;
            var v = pinVolts[ch];
            foreach(var o in outputs)
            {
                if(o.Channel != ch || !Level(o.Den)) continue;
                if(o.Dsel >= 0 && Level(o.Dsel) != o.DselLevel) continue;
                var il = (Level(o.In) && o.Ohms > 0) ? Vbat / o.Ohms : 0;
                var vis = o.Fault ? SenseClamp : il / o.Kilis * SenseResistor;
                v += Math.Min(vis, SenseClamp);
            }
            return v;
        }

        private static int Pin(string name)
        {
            name = name.Trim().ToUpperInvariant();
            return ((name[1] - 'A') << 4) | int.Parse(name.Substring(2));
        }

        private static int ChannelOf(string pinName)
        {
            var p = Pin(pinName); int port = p >> 4, pad = p & 15;
            if(port == 0 && pad <= 7) return pad;
            if(port == 1 && pad <= 1) return 8 + pad;
            if(port == 2 && pad <= 5) return 10 + pad;
            throw new ArgumentException(pinName + " is not an ADC1 pin");
        }

        private bool Level(int pin)
        {
            var port = ports[pin >> 4];
            return port != null && port.Connections[pin & 15].IsSet;
        }

        private class Output { public int In, Den, Dsel, Channel; public bool DselLevel, Fault; public double Kilis, Ohms; }

        private readonly List<Output> outputs = new List<Output>();
        private readonly double[] pinVolts = new double[16];
        private readonly Dictionary<long, uint> regs = new Dictionary<long, uint>();
        private readonly STM32_GPIOPort[] ports;
        private readonly LimitTimer timer;
        private readonly ulong pclk2;
        private readonly object sync = new object();
        private uint sr, cr1, cr2, dr, ccr;
        private const uint EOC = 2, STRT = 0x10, ADON = 1, CONT = 2, DMA = 1 << 8, SWSTART = 1u << 30;
    }
}

namespace Antmicro.Renode.Peripherals.CAN
{
    // A CAN node for tests: periodic frames (the ECU), a request queue that waits for the matching reply
    // (the PC tool), and a table of the last frame seen per ID. Lives on its own machine; frames are only
    // sent from its 100 us timer so they enter the hub at a defined virtual time.
    // The Renode CAN hub has no bit timing, arbitration, ACK or error frames: every frame reaches every other node.
    public class PDM_CanNode : ICAN, IDoubleWordPeripheral, IKnownSize
    {
        public PDM_CanNode(IMachine machine)
        {
            timer = new LimitTimer(machine.ClockSource, 1000000, this, "tick", limit: TickUs, direction: Direction.Ascending,
                enabled: true, workMode: WorkMode.Periodic, eventEnabled: true, autoUpdate: false);
            timer.LimitReached += OnTick;
            Powered = true; ReplyTimeoutUs = 100000;
        }

        public event Action<CANMessageFrame> FrameSent;
        public long Size { get { return 0x100; } }
        public uint ReadDoubleWord(long offset) { return 0; }
        public void WriteDoubleWord(long offset, uint value) { }
        public void Reset() { }

        public bool Powered { get; set; }
        public ulong ReplyTimeoutUs { get; set; }
        public ulong NowUs { get { return nowUs; } }
        public int Pending { get { lock(sync) { return queue.Count + (current != null ? 1 : 0) + outbox.Count; } } }
        public int Failed { get; private set; }
        public int Done { get; private set; }
        public string LastReply { get; private set; }
        public string FailedList { get { lock(sync) { return string.Join(";", failedList); } } }
        public ulong FramesSeen { get; private set; }

        public void ClearStats() { lock(sync) { Failed = 0; Done = 0; LastReply = ""; failedList.Clear(); } }
        public void ClearSeen() { lock(sync) { last.Clear(); FramesSeen = 0; } }

        public void Send(uint id, string hex) { lock(sync) { outbox.Enqueue(new CANMessageFrame(id, Bytes(hex))); } }

        public void SetPeriodic(uint id, string hex, uint periodUs)
        {
            lock(sync)
            {
                periodic.RemoveAll(p => p.Id == id);
                periodic.Add(new Periodic { Id = id, Data = Bytes(hex), PeriodUs = periodUs, NextUs = nowUs + periodUs });
            }
        }
        public void SetPeriodicData(uint id, string hex) { lock(sync) { foreach(var p in periodic.Where(x => x.Id == id)) p.Data = Bytes(hex); } }
        public void RemovePeriodic(uint id) { lock(sync) { periodic.RemoveAll(p => p.Id == id); } }

        // Queue a request; the next one goes out when a frame with ID replyId and the same first byte arrives, or on time-out.
        public void QueueRequest(uint id, string hex, uint replyId)
        {
            lock(sync) { queue.Enqueue(new Request { Id = id, Data = Bytes(hex), ReplyId = replyId }); }
        }

        public string Last(uint id) { lock(sync) { Seen s; return last.TryGetValue(id, out s) ? Hex(s.Data) : "none"; } }
        public long AgeUs(uint id) { lock(sync) { Seen s; return last.TryGetValue(id, out s) ? (long)(nowUs - s.TimeUs) : -1; } }
        public ulong Count(uint id) { lock(sync) { Seen s; return last.TryGetValue(id, out s) ? s.Count : 0; } }
        public long TimeUs(uint id) { lock(sync) { Seen s; return last.TryGetValue(id, out s) ? (long)s.TimeUs : -1; } }

        public void OnFrameReceived(CANMessageFrame message)
        {
            lock(sync)
            {
                if(!Powered) return;
                FramesSeen++;
                Seen s;
                if(!last.TryGetValue(message.Id, out s)) { s = new Seen(); last[message.Id] = s; }
                s.Data = message.Data; s.TimeUs = nowUs; s.Count++;
                if(current != null && message.Id == current.ReplyId && message.Data.Length > 0 && message.Data[0] == current.Data[0])
                {
                    Done++; LastReply = Hex(message.Data); current = null;
                }
            }
        }

        private void OnTick()
        {
            var send = new List<CANMessageFrame>();
            lock(sync)
            {
                nowUs += TickUs;
                if(Powered)
                {
                    foreach(var p in periodic)
                    {
                        if(nowUs >= p.NextUs) { send.Add(new CANMessageFrame(p.Id, p.Data)); p.NextUs += p.PeriodUs; }
                    }
                    while(outbox.Count > 0) send.Add(outbox.Dequeue());
                    if(current != null && nowUs >= current.DeadlineUs)
                    {
                        Failed++; failedList.Add(string.Format("{0:X}:{1}", current.Id, Hex(current.Data))); current = null;
                    }
                    if(current == null && queue.Count > 0)
                    {
                        current = queue.Dequeue(); current.DeadlineUs = nowUs + ReplyTimeoutUs;
                        send.Add(new CANMessageFrame(current.Id, current.Data));
                    }
                }
                else
                {
                    foreach(var p in periodic) { while(nowUs >= p.NextUs) p.NextUs += p.PeriodUs; }
                }
            }
            var handler = FrameSent;
            if(handler != null) foreach(var f in send) handler(f);
        }

        private static byte[] Bytes(string hex)
        {
            hex = hex.Replace(" ", "").Replace("0x", "");
            var b = new byte[hex.Length / 2];
            for(var i = 0; i < b.Length; i++) b[i] = byte.Parse(hex.Substring(2 * i, 2), NumberStyles.HexNumber);
            return b;
        }
        private static string Hex(byte[] d) { var sb = new StringBuilder(); foreach(var x in d) sb.Append(x.ToString("X2")); return sb.ToString(); }

        private class Periodic { public uint Id; public byte[] Data; public ulong PeriodUs, NextUs; }
        private class Request { public uint Id, ReplyId; public byte[] Data; public ulong DeadlineUs; }
        private class Seen { public byte[] Data; public ulong TimeUs, Count; }

        private readonly List<Periodic> periodic = new List<Periodic>();
        private readonly Queue<Request> queue = new Queue<Request>();
        private readonly Queue<CANMessageFrame> outbox = new Queue<CANMessageFrame>();
        private readonly Dictionary<uint, Seen> last = new Dictionary<uint, Seen>();
        private readonly List<string> failedList = new List<string>();
        private readonly LimitTimer timer;
        private readonly object sync = new object();
        private Request current;
        private ulong nowUs;
        private const ulong TickUs = 100;
    }
}
