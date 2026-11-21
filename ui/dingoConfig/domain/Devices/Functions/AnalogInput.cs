using System.Text.Json.Serialization;
using domain.Common;
using domain.Interfaces;
using domain.Models;

namespace domain.Devices.Functions;

public class AnalogInput : IDeviceFunction
{
    [JsonIgnore] public const int BaseIndex = 0x2200;
    [JsonPropertyName("number")] public int Number { get; set; }

    [JsonPropertyName("name")]
    public string Name
    {
        get;
        set
        {
            Switch?.Name = value;
            Rotary?.Name = value;
            field = value;
        }
    }

    [JsonPropertyName("enabled")] public bool Enabled { get; set; }
    // custom-pdm: (uiwalk 2026-11-21) Params follow the Switch / Rotary of a loaded project file. Stock built them once
    // in the constructor, so after File > Open they still read the constructor's objects (threshold 0, step 0,
    // max position 0) and a Write All sent step 0, which the firmware refuses (range 1e-6 to 1e9): the write failed.
    [JsonPropertyName("switch")] public AnalogSwitch Switch { get; set { field = value; RefreshParams(); } }
    [JsonPropertyName("rotary")] public RotarySwitch Rotary { get; set { field = value; RefreshParams(); } }

    private void RefreshParams() // custom-pdm: same list object, so a holder of Params sees the new ones
    {
        if (Params == null || Switch == null || Rotary == null) return;
        Params.Clear();
        Params.AddRange(InitParams());
    }
    
    [JsonIgnore][Plotable(displayName:"Millivolts")] public double Millivolts { get; set; }
    
    [JsonIgnore] public List<DeviceParameter> Params { get; }
    
    [JsonConstructor]
    public AnalogInput(int number, string name)
    {
        Number = number;
        Name = name;
        
        Switch = new AnalogSwitch(number, name);
        Rotary = new RotarySwitch(number, name);

        Params = InitParams();
    }
    
    private List<DeviceParameter> InitParams()
    {
        var allParams = new List<DeviceParameter>();
        var subIndex = 0;
        allParams.AddRange(

            new DeviceParameter
            {
                ParentName = Name, Name = $"analogInput[{Number}].enabled", Index = BaseIndex + (Number - 1),
                SubIndex = subIndex++,
                GetValue = () => Enabled, SetValue = val => Enabled = (bool)val,
                ValueType = Enabled.GetType(),
                DefaultValue = false
            }
        );

        allParams.AddRange(Switch.InitParams(ref subIndex));
        allParams.AddRange(Rotary.InitParams(ref subIndex));
        
        return allParams;
    }
    
    public List<DeviceVariable> GetVarMap(ref int index)
    {
        List<DeviceVariable> varMap =
        [
            new()
            {
                GetName = () => Name,
                PropertyName = "Value",
                DataType = "int",
                VariableIndex = index++,
                SingleVariable = false
            },
            new()
            {
                GetName = () => Name,
                PropertyName = "Millivolts",
                DataType = "float",
                VariableIndex = index++,
                SingleVariable = false
            }

        ];

        varMap.AddRange(Rotary.GetVarMap(ref index));
        varMap.AddRange(Switch.GetVarMap(ref index));

        return varMap;
    }
}