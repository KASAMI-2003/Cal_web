"""立方晶系 Voigt/Reuss/Hill 模量 ↔ c_ij（与 HTEM elasticity.cal_properties 一致）。"""

from __future__ import annotations

import numpy as np


def hill_moduli_cubic(c11: float, c12: float, c44: float) -> dict[str, float]:
    """由 c11/c12/c44 计算 HTEM 风格的 BV/BR/GV/GR 及 Zener 比。"""
    c11, c12, c44 = float(c11), float(c12), float(c44)
    bv = (c11 + 2.0 * c12) / 3.0
    gv = (c11 - c12 + 3.0 * c44) / 5.0

    denom = (c11 - c12) * (c11 + 2.0 * c12)
    if abs(denom) < 1e-12:
        raise ValueError('退化立方刚度：无法求 Reuss 模量')
    s11 = (c11 + c12) / denom
    s12 = -c12 / denom
    s44 = 1.0 / max(c44, 1e-12)

    br = 1.0 / (3.0 * s11 + 6.0 * s12)
    gr = 15.0 / (12.0 * (s11 - s12) + 9.0 * s44)

    bh = 0.5 * (bv + br)
    gh = 0.5 * (gv + gr)
    avr = (gv - gr) / max(gv + gr, 1e-12)
    au = 5.0 * gv / max(gr, 1e-12) + bv / max(br, 1e-12) - 6.0
    zener = 2.0 * c44 / max(c11 - c12, 1e-12)
    return {
        'BV': bv,
        'BR': br,
        'BH': bh,
        'GV': gv,
        'GR': gr,
        'GH': gh,
        'AVR': avr,
        'Au': au,
        'zener_A': zener,
    }


def isotropic_cij_from_bg(B: float, G: float) -> dict[str, float]:
    """BH+GH 各向同性极限：Zener A=1 → E/ν/v_l 曲面为球。"""
    c12 = B - 2.0 * G / 3.0
    c11 = c12 + 2.0 * G
    c44 = G
    return {'c11': c11, 'c12': c12, 'c44': c44}


def cij_from_voigt_reuss(
    BV: float,
    BR: float,
    GV: float,
    GR: float,
    *,
    tol: float = 1e-3,
) -> dict[str, float]:
    """
    由表中 BV/BR/GV/GR 反推立方 c_ij（最小二乘，与 HTEM 多晶界一致）。
    当 GV≈GR 且 BV≈BR 时退化为各向同性球面。
    """
    BV, BR, GV, GR = float(BV), float(BR), float(GV), float(GR)
    if abs(GV - GR) < 1e-6 and abs(BV - BR) < 1e-6:
        return isotropic_cij_from_bg(0.5 * (BV + BR), 0.5 * (GV + GR))

    bh, gh = 0.5 * (BV + BR), 0.5 * (GV + GR)
    x0 = np.array(
        [
            isotropic_cij_from_bg(bh, gh)['c11'],
            isotropic_cij_from_bg(bh, gh)['c12'],
            isotropic_cij_from_bg(bh, gh)['c44'],
        ],
        dtype=float,
    )

    try:
        from scipy.optimize import least_squares
    except ImportError:
        return isotropic_cij_from_bg(bh, gh)

    targets = np.array([BV, BR, GV, GR], dtype=float)

    def residuals(x: np.ndarray) -> np.ndarray:
        c11, c12, c44 = x
        if c11 <= c12 + 1e-6 or c44 <= 1e-6:
            return np.full(4, 1e6)
        try:
            m = hill_moduli_cubic(c11, c12, c44)
        except ValueError:
            return np.full(4, 1e6)
        return np.array([m['BV'] - targets[0], m['BR'] - targets[1], m['GV'] - targets[2], m['GR'] - targets[3]])

    res = least_squares(
        residuals,
        x0,
        bounds=([1.0, -1e4, 1e-6], [1e4, 1e4, 1e4]),
        ftol=1e-12,
        xtol=1e-12,
        max_nfev=400,
    )
    c11, c12, c44 = res.x
    if not res.success or float(np.linalg.norm(residuals(res.x))) > tol * max(abs(targets).max(), 1.0):
        return isotropic_cij_from_bg(bh, gh)
    return {'c11': float(c11), 'c12': float(c12), 'c44': float(c44)}
