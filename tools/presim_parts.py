"""Data-sheet values for the pre-order simulation campaign (tools/verify_tolerance.py, verify_power.py, ...).

One place for every number the presim checks rest on, each with its source (document, revision, table / parameter
number). Sim plants use these data-sheet values, never copies of firmware constants (.claude/rules/firmware.md);
the firmware constants the checks compare against are read from firmware/boards/custompdm_*/ (see fw_const()).
Design values (resistors, parts) come from the boards (KiCad 9 PCB footprints / docs/parts-audit.md) and the hwfix
stage scripts (ADR-2026-11-20-is-buffer: TLV9004IPWR; IS clamp zeners PDZ5.1B).
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---------------------------------------------------------------- PROFET +2 12V high-side switches (Infineon)
# kilis: list of (IL A, typ, +-tol) from the sense-ratio table; eas / ear in J with their test current;
# ovl0: overload detection IL(OVL0) min/typ/max at 25 C and 150 C; clamp VDS(CLAMP)_25 min/typ/max at 5 mA.
PROFET = {
    "BTS7008-2EPA": dict(  # Data Sheet Rev. 1.20 (2020-12-14); parts-audit cites Rev 1.21 (same kILIS rows)
        src="Infineon BTS7008-2EPA Data Sheet Rev 1.20",
        inom=7.5, rds25=9e-3, rds150=16e-3, rthja=30.9, rthjc=(0.8, 1.4),
        kilis=[(0.02, 5400, .35), (0.1, 5400, .30), (0.25, 5400, .295), (1.0, 5400, .135), (2.8, 5400, .058),
               (5.5, 5450, .040), (10.0, 5450, .039)],                      # Table 22, P_9.7.1.6 .. P_9.7.1.22
        floor=0.2,                                                           # firmware noise floor (profet.cpp)
        eas=(0.075, 15.0), ear=(0.025, 7.5),                                 # P_4.2.1.1 (2*IL(NOM), TJ0 150 C, VS 28 V) / P_4.2.1.2 (1M cycles, TJ0 85 C)
        clamp=(35.0, 38.0, 44.0),                                            # P_7.4.0.2
        ovl0_25=(77, 88, 99), ovl0_150=(65, 75, 85),                         # P_8.7.1.7 / P_8.7.1.8
        ton=(30e-6, 60e-6, 110e-6), toff=(15e-6, 50e-6, 100e-6),            # P_7.4.1.3 / .4 (VS 13.5 V, RL 3.3 Ohm)
        dvdt=(0.3e6, 0.6e6, 0.9e6),                                          # V/s, P_7.4.1.6 / .7
        eon=0.40e-3, eoff=0.51e-3, e_vs=18.0, e_il=7.5 * 18 / 13.5,          # P_7.5.1.14 / .15 at VS 18 V, Figure 16 (RL fixed)
        tj_sd=(150, 175, 200), retry=dict(n_cr=5, n_nt=1, n_cyc=2, t_retry=(0.040, 0.070, 0.100)),  # P_8.6.0.1, P_8.6.1.x
        ivs_off_85=0.6e-6),                                                  # P_6.5.1.1 IVS(SLEEP)_85 max (2 channels)
    "BTS7004-1EPP": dict(  # Data Sheet Rev 1.03 for the tables below; parts-audit: Rev 1.11 gives +-5 % at 15 A
        src="Infineon BTS7004-1EPP Data Sheet Rev 1.03 (kILIS at 15 A: Rev 1.11 Table 21 P_9.7.11.23, +-5 %)",
        inom=15.0, rds25=4.4e-3, rds150=8e-3, rthja=31.8, rthjc=(1.4, 2.4),
        kilis=[(0.05, 20000, .65), (0.2, 20000, .65), (0.45, 20000, .55), (2.0, 20000, .40), (5.5, 20000, .24),
               (10.0, 20000, .08), (15.0, 20000, .05)],                      # Rev 1.03 Table 21 P_9.7.11.8 .. .22; 15 A: Rev 1.11
        floor=0.5,
        eas=(0.150, 30.0), ear=(0.044, 15.0), clamp=(35.0, 38.0, 44.0),     # P_4.2.11.1 / P_4.2.11.4 / P_7.4.0.2
        ovl0_25=(103, 117.5, 132), ovl0_150=(88, 101, 114),                  # P_8.7.11.7 / .8
        ton=(50e-6, 130e-6, 210e-6), toff=(30e-6, 100e-6, 220e-6), dvdt=(0.16e6, 0.27e6, 0.39e6),   # P_7.4.5.x
        eon=1.4e-3, eoff=1.65e-3, e_vs=18.0, e_il=15.0 * 18 / 13.5,          # P_7.5.11.14 / .15
        tj_sd=(150, 175, 200), retry=dict(n_cr=5, n_nt=1, n_cyc=2, t_retry=(0.040, 0.070, 0.100)),
        ivs_off_85=0.5e-6),                                                  # P_6.5.21.1
    "BTS70012-1ESP": dict(
        src="Infineon BTS70012-1ESP Data Sheet Rev 1.21",
        inom=31.3, rds25=1.4e-3, rds150=2.47e-3, rthja=23.0, rthjc=(0.4, 0.7),
        kilis=[(0.2, 33000, .24), (0.7, 33000, .17), (2.0, 33000, .135), (7.0, 33700, .085), (20.0, 33700, .055),
               (30.0, 33700, .048), (40.0, 33700, .047)],                    # Table 21, P_9.7.26.11 .. .31
        floor=1.0,
        eas=(0.525, 62.6), ear=(0.160, 31.3), clamp=(35.0, 38.0, 44.0),     # P_4.2.21.1 / .2 / P_7.4.0.5
        ovl0_25=(180, 209, 238), ovl0_150=(146, 170, 193),                   # P_8.7.24.7 / .8
        ton=(50e-6, 130e-6, 210e-6), toff=(30e-6, 100e-6, 220e-6), dvdt=(0.16e6, 0.27e6, 0.39e6),   # P_7.4.5.x
        eon=1.5e-3, eoff=1.65e-3, e_vs=18.0, e_il=31.3 * 18 / 13.5,          # P_7.5.23.14 / .15
        tj_sd=(150, 175, 200), retry=dict(n_cr=5, n_nt=1, n_cyc=2, t_retry=(0.040, 0.070, 0.100)),
        ivs_off_85=2.2e-6),                                                  # P_6.5.25.1
}
IIS_FAULT = (4.4e-3, 5.5e-3, 10e-3)          # all three, P_9.6.x IIS(FAULT) min / typ / max

# The 24 outputs (README.md / docs/car-loads.dummy.md): board, output, driver, default current limit (w3a)
OUTPUTS = ([("A1", i, "BTS7008-2EPA", 7.5) for i in range(1, 9)] +
           [("A2", i, "BTS7008-2EPA", 1.0 if i == 2 else 7.5) for i in range(1, 9)] +   # A2 OUT2 = box fans, 1 A
           [("B", i, "BTS70012-1ESP", 31.0) for i in range(1, 5)] +
           [("B", i, "BTS7004-1EPP", 15.0) for i in range(5, 9)])

# ---------------------------------------------------------------- STM32F446 (ST DS DocID027107 Rev 3; RM0390)
STM32 = dict(
    src="ST STM32F446xC/E data sheet DocID027107 Rev 3",
    vil_tested=0.3, vil_design=(0.35, -0.04), vih_tested=0.7, vih_design=(0.45, 0.3),   # Table 56 (x VDD [+ V])
    adc_et_lsb=5, adc_et_18mhz_lsb=4,                         # Table 76 (30 MHz) / Table 75 (18 MHz), max
    vrefint=(1.18, 1.21, 1.24), vrefint_spread=5e-3,          # Table 83: VREFINT, spread over temp (VDD 3 V) max
    vrefint_cal_vdda=(3.3, 0.010),                            # VREFINT_CAL taken at VDDA 3.3 V +-10 mV, 30 C (Table 84)
    ts_linearity=2.0, ts_min_sample_s=10e-6, vref_min_sample_s=10e-6,   # Table 80 / 83
    bor=[(2.13, 2.19, 2.24), (2.44, 2.50, 2.56), (2.75, 2.83, 2.88)],   # Table 21 VBOR1..3 falling
    pdr=(1.60, 1.68, 1.76),                                   # Table 21 VPOR/PDR falling
    ws_range_2v7=(2.7, 3.6),                                  # Table 17: 5 WS at 180 MHz only for VDD 2.7-3.6 V
    idd_stop_lp_25=(0.15e-3, 0.95e-3), idd_stop_lp_85=8.5e-3, # Table 31 IDD_STOP_NM, LP regulator, flash in stop: typ 25 / max 25 / max 85 C
    iinj_ft=(-5e-3, 0.0), iinj_sum=25e-3)                     # Table 13 (Abs max): FT pins -5 / +0 mA, total +-25 mA

# ---------------------------------------------------------------- other parts
TLV9004 = dict(src="TI TLV9004 SBOS833R", vos_25=1.6e-3, vos_hot=2.0e-3, iq=75e-6, swing=0.02)   # 7.5: VOS max, IQ max per amp
PDZ = {  # Nexperia PDZ-B series data sheet Table 2: VZ at 5 mA (min, max), IR max at VR
    "PDZ3.3B": dict(vz=(3.32, 3.53), ir=(5e-6, 1.0)),
    "PDZ5.1B": dict(vz=(4.96, 5.20), ir=(2e-6, 1.5)),
}
MCP9808 = dict(src="Microchip MCP9808 DS25095A Table 1-1", acc_m20_100=0.5, acc_m40_125=1.0, idd=400e-6, ishdn=2e-6)
MCP2562FD = dict(src="Microchip MCP2562FD DS20005284A", idd_stby=15e-6, tprop=120e-9, vdd=(4.5, 5.5),
                 can_dc=(-58, 58), can_iso7637=(-150, 100))   # 1.0 DC / AC tables; standby IDDS incl. IIO (max)
TSR = dict(src="Traco TSR 1 series data sheet (2026-10-08)", vin_min=6.5, vin_max=36.0, acc=0.02, line=0.002,
           load=0.004, tc=0.00015, overshoot=0.01, step_dv=0.200, step_t=350e-6, i_noload=1e-3, cap_max=470e-6)
# hw5v (2026-11-21): the 5 V converter on both main boards (A U15 / B U13 TSR 1-2450 -> TI LMZM23601V5, new ref).
# acc: initial accuracy over VIN 4-36 V and TJ -40..125 C (6.5, limits over the full TJ range); dmax: fixed-output max
# duty (6.5); rdrop: HS RDS(on) 0.22 + inductor DCR 0.39 Ohm (6.5); uvlo: VIN rising 3.85 max / hysteresis 0.2 min (6.5);
# i_noload: 32 uA at 12 V in, 5 V out (6.6); pfm_rise: no-load output about 1 % higher in auto PFM (7.3.7.2);
# step_dv: 0.02 -> 0.22 A step, ASSUMED from the averaged model in tools/verify_spice.py (module5v) x 2.
LMZM23601 = dict(src="TI LMZM23601 SNVSAQ4C rev C (2023-03)", vin_min=4.0, vin_max=36.0, vin_abs=40.0, acc=0.015,
                 dmax=0.93, rdrop=0.61, uvlo=(3.85, 0.2), i_noload=32e-6, pfm_rise=0.01, cap_max=220e-6,
                 step_dv=0.05, i_load_max=0.22, tj_max=125.0)
TLV1117LV = dict(src="TI TLV1117LV SBVS160C", vdo_200ma=0.09, vin_max_abs=6.0, acc=0.01, iq=0.1e-3)   # dropout typ, IQ (est.)
MB85RC64TA = dict(src="RAMXEED MB85RC64TA DS501-00044-5v0-E", endurance=1e13, istby=9e-6)          # read/write cycles per byte
# hwtemp (2026-11-23): U5 on both main boards is the Infineon CY15B064J-SXE (Automotive-E, -40..125 C; Infineon 002-10027
# Rev *C): endurance 1e13, ISB 6 uA typ / max at 85 C and 20 uA max at 125 C, VDD 3.0-3.6 V, tPU 1 ms, retention 121 y
# at 85 C / 11 y at 105 C / 11,000 h at 125 C. The MB85RC64TA stays as an approved alternate (105 C).
CY15B064J = dict(src="Infineon CY15B064J 002-10027 Rev *C", endurance=1e13, istby=6e-6, istby_125=20e-6, vdd=(3.0, 3.6),
                 tpu=1e-3)
RESISTOR_TOL = {"0805W8F": 0.01, "0603WAF": 0.01, "RT0805DRD": 0.005}       # Uniroyal 1 %, Yageo RT 0.5 %
RES_TCR = 100e-6                                                            # Uniroyal 0805W8F / 0603WAF: +-100 ppm/K
BAT54S_IS_25 = 2e-7                                                          # as tools/verify_spice.py (Nexperia BAT54S), x2 / 10 K


def fw_const(board, name, cast=float):
    """Read a #define from firmware/boards/custompdm_<board>/port.h (or port.cpp) so checks follow the firmware."""
    for f in ("port.h", "port.cpp", "params.h"):
        p = os.path.join(ROOT, "firmware", "boards", f"custompdm_{board}", f)
        if os.path.exists(p):
            m = re.search(rf"#define\s+{name}\s+\(?([-0-9.eEfxXA-Fa-f]+)", open(p, encoding="utf-8").read())
            if m:
                return cast(m.group(1).rstrip("fF")) if cast is not int else int(m.group(1), 0)
    raise KeyError(f"{name} not in custompdm_{board}")


def kilis_tol(model, il):
    """Data-sheet kILIS (typ, +-tol) at load current il: the nearest tabulated point at or below il (the tolerance
    only narrows with current, so this is the conservative reading of the table)."""
    rows = PROFET[model]["kilis"]
    best = rows[0]
    for r in rows:
        if r[0] <= il:
            best = r
    return best[1], best[2]

# ---------------------------------------------------------------- car loads (docs/car-loads.dummy.md, a DUMMY TEST COPY)
# steady current from the car-loads dummy (st185 fuse = upper bound); inductance / inrush are NOT measured on the car:
# the values are typical published ranges (low, high) and every result built on them is a bench test (BACKLOG).
#   DC PM motors (fans, pumps, wiper, washer): armature L 0.1-1 mH; start / stall current 3-5 x steady for 0.3-1 s
#   (HP Academy motor inrush, ui PdmPresets.cs); A/C clutch coil 3-4 Ohm, 50-200 mH; relay coil 80-120 Ohm, 0.1-0.4 H;
#   horn coil (electromagnetic, self-interrupting) 5-30 mH; solenoid valve 1-2 A, 10-50 mH. All ASSUMED (no data sheet).
CAR_LOADS = [  # name, board, out, driver, steady A, L range (H), inrush x steady, inrush s, kind
    ("Radiator fan", "B", 1, "BTS70012-1ESP", 25.0, (0.2e-3, 1.0e-3), 4.0, 0.5, "motor"),
    ("Condenser fan", "B", 2, "BTS70012-1ESP", 20.0, (0.2e-3, 1.0e-3), 4.0, 0.5, "motor"),
    ("Fuel pump", "B", 3, "BTS70012-1ESP", 19.0, (0.1e-3, 0.5e-3), 4.0, 0.3, "motor"),
    ("CAN-Lambda", "B", 5, "BTS7004-1EPP", 8.1, (0.0, 1e-6), 1.5, 0.1, "electronic"),
    ("A/C clutch", "B", 6, "BTS7004-1EPP", 3.6, (0.05, 0.2), 1.0, 0.0, "coil"),
    ("Wiper motor", "B", 7, "BTS7004-1EPP", 6.0, (0.3e-3, 1.5e-3), 4.0, 0.3, "motor"),
    ("Low beams (LED)", "A1", 1, "BTS7008-2EPA", 2.0, (0.0, 1e-6), 3.0, 0.01, "electronic"),
    ("High beams + dash LED", "A1", 2, "BTS7008-2EPA", 2.5, (0.0, 1e-6), 3.0, 0.01, "electronic"),
    ("Horn pair", "A1", 5, "BTS7008-2EPA", 5.0, (5e-3, 30e-3), 1.0, 0.0, "coil"),
    ("EPS enable (relay coil)", "A1", 6, "BTS7008-2EPA", 0.15, (0.1, 0.4), 1.0, 0.0, "coil"),
    ("Washer pump", "A2", 4, "BTS7008-2EPA", 3.0, (0.2e-3, 1.0e-3), 4.0, 0.2, "motor"),
    ("Generic solenoid (boost / valve)", "A2", 5, "BTS7008-2EPA", 1.5, (10e-3, 50e-3), 1.0, 0.0, "coil"),
    ("Box fans", "A2", 2, "BTS7008-2EPA", 0.13, (1e-3, 5e-3), 3.0, 0.2, "motor"),
]
# board B: BYG23M from GND to every PF_OUT (D13 .. D28), as stock Max. hwprotect (2026-11-20) checked removing them
# (Infineon PROFET+2 data sheets 8.4.1: reverse current must be limited by the load): verify_power / verify_switching
# --no-freewheel-b show what that does to the car loads (A/C clutch and fan turn-off into the switch clamp); kept fitted
# until the design choice is made (BACKLOG / report).
FREEWHEEL = {"A1": None, "A2": None, "B": "BYG23M"}
FREEWHEEL_FOOTPRINTS_B = "D13 D15 D17 D19 D25 D26 D27 D28 (DO-214AC, do not fit)"
BYG23M = dict(src="Vishay BYG23M doc 88962 (2020-02-25)", if_av=1.5, ifsm=30.0, ifsm_t=10e-3, vf_1a=1.7, rth_ja=125.0)
PMEG10010 = dict(src="Nexperia PMEG10010ELR", vf_100ma=0.55, vr=100)      # D19 (A) / D3 (B): +12V -> +12P (est. VF)
PMEG2010 = dict(vf_100ma=(0.265, 0.290), vf_cold=0.38)                      # D18 / D4, docs/parts-audit.md section 9
