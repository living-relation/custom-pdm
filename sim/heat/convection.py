"""Heat transfer coefficients for the three air-side cases (docs/heat-analysis.md, section 3).

All correlations are textbook ones; every input that is not from a data sheet is ASSUMED.
Units SI. Temperatures in C unless noted.
"""
import math
import geometry as G

g = 9.81
# dry air at 1 atm, Incropera & DeWitt, Fundamentals of Heat and Mass Transfer, Table A.4
_T = [300.0, 350.0, 400.0]
_k = [0.0263, 0.0300, 0.0338]
_nu = [15.89e-6, 20.92e-6, 26.41e-6]
_al = [22.5e-6, 29.9e-6, 38.3e-6]
_pr = [0.707, 0.700, 0.690]
_rho = [1.1614, 0.9950, 0.8711]
_cp = [1007.0, 1009.0, 1014.0]


def air(t_c):
    T = t_c + 273.15
    i = 0 if T < 350 else 1
    w = (T - _T[i]) / 50.0
    lerp = lambda a: a[i] + w * (a[i + 1] - a[i])
    return dict(k=lerp(_k), nu=lerp(_nu), al=lerp(_al), pr=lerp(_pr), rho=lerp(_rho), cp=lerp(_cp), beta=1.0 / T)


def ra(p, dT, L):
    return g * p["beta"] * max(dT, 0.1) * L ** 3 / (p["nu"] * p["al"])


def h_vertical(p, dT, L):
    """Churchill & Chu (1975), laminar form, isothermal vertical plate (Incropera eq. 9.27)."""
    R = ra(p, dT, L)
    nu = 0.68 + 0.670 * R ** 0.25 / (1 + (0.492 / p["pr"]) ** (9 / 16)) ** (4 / 9)
    return nu * p["k"] / L


def h_down(p, dT, L):
    """Lower surface of a hot horizontal plate, Nu = 0.27 Ra^1/4 (Incropera 6th ed. eq. 9.32)."""
    return 0.27 * ra(p, dT, L) ** 0.25 * p["k"] / L


def h_elenbaas(p, dT, S, L):
    """Elenbaas (1942) isothermal symmetric vertical parallel plates, Nu_S = Ra*/24 [1-exp(-35/Ra*)]^0.75
    (Bar-Cohen & Rohsenow 1984). Ra* = Ra_S S/L."""
    Rs = ra(p, dT, S) * S / L
    nu = Rs / 24.0 * (1 - math.exp(-35.0 / Rs)) ** 0.75
    return nu * p["k"] / S


S_CH = (G.FIN_PITCH - G.FIN_T) / 1000.0       # 4 mm channel gap
H_F = G.FIN_H / 1000.0                         # 30 mm fin depth
L_F = (G.fins()[2][1] - G.fins()[2][0]) / 1000.0   # fin length, east-west
N_CH = len(G.fins()) - 1                       # channels between fins
ENV_X, ENV_Y = (G.LX1 - G.LX0) / 1000.0, (G.LY1 - G.LY0) / 1000.0
ENV_H = (G.PLATE_T + G.FIN_H) / 1000.0


def passive_upper(t_sink, t_amb, a_field, a_edge):
    """Case 1a: fins as open vertical channels (Elenbaas) - optimistic for fins pointing DOWN."""
    dT = t_sink - t_amb; p = air((t_sink + t_amb) / 2)
    return dict(h_field=h_elenbaas(p, dT, S_CH, H_F), h_edge=h_vertical(p, dT, ENV_H), t_air=None)


def passive_lower(t_sink, t_amb, a_field, a_edge):
    """Case 1b: envelope method - the finned block counts only as its outer box: bottom = hot plate facing
    down, four sides = vertical plates. Total hA spread evenly over the meshed air-side faces
    (the sink is near isothermal, so where hA sits barely matters)."""
    dT = t_sink - t_amb; p = air((t_sink + t_amb) / 2)
    a_bot = ENV_X * ENV_Y; Lc = a_bot / (2 * (ENV_X + ENV_Y))
    a_side = 2 * (ENV_X + ENV_Y) * ENV_H
    hA = h_down(p, dT, Lc) * a_bot + h_vertical(p, dT, ENV_H) * a_side
    h = hA / (a_field + a_edge)
    return dict(h_field=h, h_edge=h, t_air=None, hA=hA)


# fans: 2 x Sunon MF30101V1-1000U-A99, spec D03033580G-01: 5.5 CFM free air, 0.25 inH2O max static
Q_FREE = 2 * 5.5 * 0.000471947      # m3/s, two fans in parallel
P_MAX = 0.25 * 249.089              # Pa
K_MINOR = 1.5                       # ASSUMED entrance + exit loss coefficient
BYPASS = 0.5                        # ASSUMED share of fan flow that really passes through the fin channels


def fan_point(t_air):
    """Operating point: ASSUMED straight-line fan curve (P = Pmax (1 - Q/Qfree); curve on spec p.5 is a
    picture only) against laminar parallel-plate friction (f Re = 96 on Dh = 2S) + K_MINOR."""
    p = air(t_air); mu = p["nu"] * p["rho"]; A = N_CH * S_CH * H_F; Dh = 2 * S_CH
    lo, hi = 0.0, Q_FREE
    for _ in range(80):
        q = (lo + hi) / 2; V = q / A
        dp = 96 * mu * L_F * V / (2 * Dh ** 2) + K_MINOR * p["rho"] * V ** 2 / 2
        if dp > P_MAX * (1 - q / Q_FREE): hi = q
        else: lo = q
    return q, A


# v2b-F2: one Noctua NF-A6x15 PWM blowing UP into a pocket, air turns and leaves through swept radial channels.
# Fan curve = Noctua spec sheet table (28.09.2018, 3500 rpm): (m3/h, mmH2O).
NOCTUA = [(23.40, 0.00), (16.90, 0.75), (11.60, 1.03), (5.70, 1.80), (0.00, 2.43)]
F2_N = 48                       # 24 long + 24 splitter fins (enclosure/v2b build_v2b.py)
F2_T = 2.5e-3                   # radial fin thickness
F2_RMID = 0.060                 # ASSUMED representative radius for the channel gap
F2_L = 0.060                    # ASSUMED mean radial channel length (pocket edge -> fin-field edge)
F2_K = 2.5                      # ASSUMED losses: turn from the fan into the plenum (1.0) + entry/exit (1.5)


def _noctua_dp(q_m3s):
    qh = q_m3s * 3600.0
    for (q1, p1), (q2, p2) in zip(NOCTUA[:-1], NOCTUA[1:]):
        if q2 <= qh <= q1: return (p1 + (p2 - p1) * (q1 - qh) / (q1 - q2)) * 9.80665
    return 0.0 if qh > NOCTUA[0][0] else NOCTUA[-1][1] * 9.80665


def forced_f2(t_sink, t_amb, a_field, a_edge, p_total):
    """v2b-F2 estimate: fan curve (spec table) against laminar friction in radial channels at r_mid (f Re = 96,
    Dh = 2S) + F2_K; same Stephan correlation as case 2; BYPASS share passes the channels (open fin tips)."""
    p = air(t_amb + 5); mu = p["nu"] * p["rho"]
    S = 2 * math.pi * F2_RMID / F2_N - F2_T; A = F2_N * S * H_F; Dh = 2 * S
    lo, hi = 0.0, NOCTUA[0][0] / 3600.0
    for _ in range(80):
        q = (lo + hi) / 2; V = q / A
        dp = 48 * mu * V * F2_L / Dh ** 2 + F2_K * p["rho"] * V ** 2 / 2   # f Re = 96: dp = (96/Re)(L/Dh) rho V^2/2
        if dp > _noctua_dp(q): hi = q
        else: lo = q
    q0 = lo; q = q0 * BYPASS; V = q / A; Re = V * Dh / p["nu"]
    xs = F2_L / (Dh * Re * p["pr"])
    nu = 7.55 + 0.024 * xs ** -1.14 / (1 + 0.0358 * p["pr"] ** 0.17 * xs ** -0.64)
    h = nu * p["k"] / Dh
    dT_air = p_total / (p["rho"] * q * p["cp"])
    pe = air((t_sink + t_amb) / 2)
    return dict(h_field=h, h_edge=h_vertical(pe, t_sink - t_amb, ENV_H), t_air=(t_amb + dT_air / 2, 0.0),
                q_fan_op_m3s=q0, q_channels_m3s=q, V=V, Re=Re, xstar=xs, Nu=nu, t_exhaust=t_amb + dT_air, S_mm=S * 1000)


def forced(t_sink, t_amb, a_field, a_edge, p_total):
    if G.HEAT_GEOM == "v2b-F2": return forced_f2(t_sink, t_amb, a_field, a_edge, p_total)
    """Case 2: laminar simultaneously developing flow between parallel isothermal plates, mean Nu,
    Stephan correlation (Shah & London 1978): Nu_m = 7.55 + 0.024 x*^-1.14 / (1 + 0.0358 Pr^0.17 x*^-0.64)."""
    q0, A = fan_point(t_amb + 5)
    q = q0 * BYPASS
    p = air(t_amb + 5); Dh = 2 * S_CH; V = q / A; Re = V * Dh / p["nu"]
    xs = L_F / (Dh * Re * p["pr"])
    nu = 7.55 + 0.024 * xs ** -1.14 / (1 + 0.0358 * p["pr"] ** 0.17 * xs ** -0.64)
    h = nu * p["k"] / Dh
    dT_air = p_total / (p["rho"] * q * p["cp"])
    pe = air((t_sink + t_amb) / 2)
    return dict(h_field=h, h_edge=h_vertical(pe, t_sink - t_amb, ENV_H), t_air=(t_amb, dT_air),
                q_fan_op_m3s=q0, q_channels_m3s=q, V=V, Re=Re, xstar=xs, Nu=nu, t_exhaust=t_amb + dT_air)
