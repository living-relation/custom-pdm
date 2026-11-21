using application.Services;
using domain.Common;
using domain.CustomPdm;
using domain.Devices;
using domain.Enums;
using domain.Models;
using Microsoft.Extensions.Logging.Abstractions;

namespace CustomPdm.Tests;

// A stand-in board for the PdmOps tests that run without WSL: the board side of the dingoFW parameter protocol as far
// as dingoConfig looks at it (firmware/core/param_protocol.cpp, comms/request_msg.cpp). It holds the raw 4 value
// bytes of every param. The same flows run against the real firmware logic in PdmLiveSimTests.
public sealed class FakeBoard
{
    private readonly List<(int Index, int Sub)> _order = [];
    private readonly Dictionary<(int, int), byte[]> _staged = new();

    public int BaseId { get; }
    public Dictionary<(int Index, int Sub), byte[]> Values { get; } = new();
    public bool Silent { get; set; }            // answers nothing
    public bool WrongCheckCrc { get; set; }     // config check never matches
    public bool NoWriteResult { get; set; }     // answers the Write All start, never the WriteAllComplete
    public byte BurnResult { get; set; } = 1;   // byte 4 of the burn reply (WriteConfig())
    public List<MessageCommand> Got { get; } = [];
    public int Burns { get; private set; }
    public List<(int Index, int Sub, int Value)> Writes { get; } = [];

    public FakeBoard(int type, int baseId)
    {
        BaseId = baseId;
        var model = StockTests.MakeDevice(type, baseId);
        model.BitRate = CanBitRate.BitRate1000K;       // not the PC default, as our factory config
        var role = PdmFactoryDefaults.Boards.Single(b => b.BaseId == baseId).Role;
        for (var i = 0; i < model.Outputs.Count; i++)  // our factory limits = ratings (w3a), not the PC's 20 A
            model.Outputs[i].CurrentLimit = PdmFactoryDefaults.CurrentLimit(role, i);
        foreach (var p in model.Params)
        {
            _order.Add((p.Index, p.SubIndex));
            Values[(p.Index, p.SubIndex)] = ParamCodec.ToFrame(MessageCommand.Null, p, 0).Payload[4..8];
        }
    }

    public int Count(MessageCommand cmd) => Got.Count(c => c == cmd);

    private (int, byte[]) Reply(MessageCommand cmd, int b1 = 0, int b2 = 0, int b3 = 0, byte[]? tail = null) =>
        (BaseId, [(byte)cmd, (byte)b1, (byte)b2, (byte)b3, .. tail ?? new byte[4]]);

    private byte[] Crc(IEnumerable<byte[]> values)
    {
        var crc = new CumulativeCrc32();
        foreach (var v in values) crc.Update(v);
        return BitConverter.GetBytes(crc.Final);
    }

    public List<(int Id, byte[] Data)> Rx(CanFrame f)
    {
        var tx = new List<(int, byte[])>();
        if (f.Id != BaseId + 1) return tx;
        var d = f.Payload;
        var cmd = (MessageCommand)d[0];
        Got.Add(cmd);
        if (Silent) return tx;
        var key = (d[2] << 8 | d[1], (int)d[3]);
        switch (cmd)
        {
            case MessageCommand.Version:
                tx.Add(Reply(cmd, tail: [99, 0, 0, 0]));
                break;
            case MessageCommand.ReadAll:
                tx.Add(Reply(cmd));
                foreach (var k in _order) tx.Add(Reply(MessageCommand.ReadAllRsp, k.Index & 255, k.Index >> 8, k.Sub, Values[k]));
                tx.Add(Reply(MessageCommand.ReadAllComplete, _order.Count & 255, _order.Count >> 8, 0, Crc(_order.Select(k => Values[k]))));
                break;
            case MessageCommand.CheckCrc:
                var crc = Crc(_order.Select(k => Values[k]));
                if (WrongCheckCrc) crc[0] ^= 1;
                tx.Add(Reply(MessageCommand.CheckCrcRsp, tail: crc));
                break;
            case MessageCommand.Write:   // uipolish: one param, live (firmware param_protocol.cpp MsgCmd::Write)
                Writes.Add((key.Item1, key.Item2, BitConverter.ToInt32(d, 4)));
                Values[key] = d[4..8];
                tx.Add(Reply(cmd, d[1], d[2], d[3], d[4..8]));
                break;
            case MessageCommand.WriteAll:
                _staged.Clear();
                tx.Add(Reply(cmd));
                break;
            case MessageCommand.WriteAllVal:
                _staged[key] = d[4..8];
                break;
            case MessageCommand.WriteAllComplete:
                if (NoWriteResult) break;
                var ok = _staged.Count == (d[2] << 8 | d[1]) && Crc(_staged.Values).SequenceEqual(d[4..8]);
                if (ok) foreach (var (k, v) in _staged) Values[k] = v;
                tx.Add(Reply(cmd, d[1], d[2], ok ? 1 : 0, d[4..8]));
                break;
            case MessageCommand.BurnParams when d[1] == 1 && d[2] == 3 && d[3] == 8:
                if (BurnResult == 1) Burns++;
                tx.Add(Reply(cmd, 1, 3, 8, [BurnResult, 0, 0, 0]));
                break;
        }

        return tx;
    }
}

// The three PC devices in one real DeviceManager + PdmOpsService, on a bus of FakeBoards, with a hand clock
public sealed class FakePdm
{
    private readonly List<DeviceCanFrame> _pending = [];

    public DeviceManager Mgr { get; }
    // a slow bus / bridge: at most this many PC frames reach the boards per Pump (one Pump per 100 ms round)
    public int? MaxFramesPerPump { get; set; }
    // these boards send a harmless config-channel reply (Version) every Pump, whatever the PC sends
    public HashSet<string> Chatty { get; } = [];
    // clock of every frame the PC sent (same order as Sent)
    public List<(int Id, MessageCommand Cmd, DateTime At)> SentAt { get; } = [];
    public DateTime? FinishedAt { get; private set; }   // clock when the last Run ended
    public PdmOpsService Service { get; }
    public Dictionary<string, FakeBoard> Boards { get; } = new();
    public HashSet<string> Offline { get; } = [];      // by device name
    // every frame the PC sent, with what the PC knew at that moment: the success notes so far and the devices whose
    // config check said "match"
    public List<(int Id, MessageCommand Cmd, string[] Notes, string[] Matching)> Sent { get; } = [];
    public List<string> Notes { get; } = [];
    public bool Adapter { get; set; } = true;
    public DateTime Clock { get; private set; } = new(2026, 1, 1, 0, 0, 0, DateTimeKind.Utc);

    public FakePdm(params string[] roles)
    {
        if (roles.Length == 0) roles = PdmOps.Roles;
        Mgr = new DeviceManager(NullLogger<DeviceManager>.Instance, NullLoggerFactory.Instance,
            new SystemLogger(Path.Combine(Path.GetTempPath(), "cpdm-ui-test-logs")), new FwDeviceDefManager());
        Mgr.SetBatchTransmitCallback(batch => { lock (_pending) _pending.AddRange(batch); });
        foreach (var role in roles)
        {
            var (type, id) = role switch { "A1" => (14, 0x500), "A2" => (14, 0x540), _ => (15, 0x580) };
            Mgr.AddDevice($"fwD:{type}", role, id);
            Boards[role] = new FakeBoard(type, id);
        }

        Service = new PdmOpsService(Mgr, d => !Offline.Contains(d.Name)) { AutoTick = false };
        _devices = Mgr.GetDevicesByType<FwDevice>().ToList();
        foreach (var d in _devices) d.SuccessNotification += Notes.Add;
    }

    private List<FwDevice> _devices;

    // uipolish: File > Open (MainLayout.HandleOpen): the project's devices are replaced by the loaded ones
    public void Open(List<domain.Interfaces.IDevice> loaded)
    {
        Mgr.ClearDevices();
        Mgr.AddDevices(loaded);
        _devices = Mgr.GetDevicesByType<FwDevice>().ToList();
        foreach (var d in _devices) d.SuccessNotification += Notes.Add;
    }

    public FwDevice Dev(string role) => _devices.Single(d => d.Name == role);
    public PdmView View => Service.BuildView();
    public string? Blocked(PdmOpKind op) => Service.BlockedReason(op, View, Adapter);

    // Does the job of CommsDataPipeline: sends what DeviceManager queued (then OnFrameTransmitted, as the pipeline
    // does after the adapter took the frame), and hands every board reply to OnCanDataReceived
    public void Pump()
    {
        foreach (var role in Chatty)
            Mgr.OnCanDataReceived(new CanFrame(Boards[role].BaseId, 8, [(byte)MessageCommand.Version, 0, 0, 0, 99, 0, 0, 0]));
        var left = MaxFramesPerPump ?? int.MaxValue;
        while (left > 0)
        {
            List<DeviceCanFrame> batch;
            lock (_pending)
            {
                batch = _pending.Take(left).ToList();
                _pending.RemoveRange(0, batch.Count);
            }

            if (batch.Count == 0) return;
            left -= batch.Count;
            foreach (var df in batch)
            {
                var f = df.Frame;
                Sent.Add((f.Id, (MessageCommand)f.Payload[0], Notes.ToArray(),
                    _devices.Where(d => !d.ConfigMismatch).Select(d => d.Name).ToArray()));
                SentAt.Add((f.Id, (MessageCommand)f.Payload[0], Clock));
                Mgr.OnFrameTransmitted(df);
                foreach (var board in Boards.Values)
                foreach (var (id, data) in board.Rx(f))
                    Mgr.OnCanDataReceived(new CanFrame(id, 8, data));
            }
        }
    }

    // Start the operation and run it to its end (100 ms of clock per round, 10 min at most). Returns the refusal text, if any.
    public string? Run(PdmOpKind op)
    {
        FinishedAt = null;
        var refused = Service.Start(op, Adapter, Clock);
        for (var i = 0; refused == null && Service.Ops.Busy && i < 6000; i++)
        {
            Pump();
            Clock = Clock.AddMilliseconds(100);
            Service.Tick(Clock);
        }

        if (refused == null) FinishedAt = Clock;
        return refused;
    }

    // p2a: n rounds of 100 ms (bus + Tick), whatever runs or starts by itself
    public void Rounds(int n)
    {
        for (var i = 0; i < n; i++)
        {
            Pump();
            Clock = Clock.AddMilliseconds(100);
            Service.Tick(Clock);
        }
    }

    // rounds until no PDM run is busy (and none started in the last round), 2 min at most
    public void Settle()
    {
        Rounds(1);
        for (var i = 0; Service.Ops.Busy && i < 1200; i++) Rounds(1);
    }

    // time passes, but nothing the PC sent has reached a board yet
    public void TickOnly()
    {
        Clock = Clock.AddMilliseconds(100);
        Service.Tick(Clock);
    }

    public string Line(string role)
    {
        var r = Service.Ops.Results.Single(x => x.Role == role);
        return $"{r.State}: {r.Text}";
    }

    public PdmStepState[] States => Service.Ops.Results.Select(r => r.State).ToArray();
}
