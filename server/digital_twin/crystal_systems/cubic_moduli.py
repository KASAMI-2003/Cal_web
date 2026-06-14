"""立方晶系 Voigt/Reuss/Hill 模量 ↔ c_ij（与 HTEM elasticity.cal_properties 一致）。"""

from __future__ import annotations

import numpy as np


class CijFitError(ValueError):
    """BV/BR/GV/GR 无法用单晶立方 c_ij 在四式约束下自洽拟合。"""


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
    """仅 BH+GH、无 VR 列，或 Voigt/Reuss 四值完全相等时的各向同性立方解。"""
    c12 = B - 2.0 * G / 3.0
    c11 = c12 + 2.0 * G
    c44 = G
    return {'c11': c11, 'c12': c12, 'c44': c44, 'cij_method': 'isotropic_bh_gh'}


def _fit_cubic_cij_voigt_reuss(
    BV: float,
    BR: float,
    GV: float,
    GR: float,
    *,
    rel_tol: float = 0.05,
) -> dict[str, float]:
    """四式等权最小二乘；失败则 CijFitError，不做加权或各向同性回退。"""
    try:
        from scipy.optimize import least_squares
    except ImportError as exc:
        raise CijFitError(
            '拟合 BV/BR/GV/GR 需要 scipy，请 pip install scipy 后重试'
        ) from exc

    targets = np.array([float(BV), float(BR), float(GV), float(GR)], dtype=float)
    bh, gh = 0.5 * (targets[0] + targets[1]), 0.5 * (targets[2] + targets[3])
    iso = isotropic_cij_from_bg(bh, gh)
    x0 = np.array([iso['c11'], iso['c12'], iso['c44']], dtype=float)

    def residuals(x: np.ndarray) -> np.ndarray:
        c11, c12, c44 = x
        if c11 <= c12 + 1e-6 or c44 <= 1e-6:
            return np.full(4, 1e3)
        try:
            m = hill_moduli_cubic(c11, c12, c44)
        except ValueError:
            return np.full(4, 1e3)
        model = np.array([m['BV'], m['BR'], m['GV'], m['GR']], dtype=float)
        return model - targets

    best = None
    best_norm = np.inf
    starts = [x0]
    for a in (1.0, 1.5, 2.5, 3.5, 5.0):
        d = 2.0 * gh / max(a, 0.5)
        starts.append(np.array([iso['c12'] + d + gh, iso['c12'], a * d / 2.0]))

    for start in starts:
        res = least_squares(
            residuals,
            np.asarray(start, dtype=float),
            bounds=([1.0, -1e4, 1e-6], [1e4, 1e4, 1e4]),
            ftol=1e-10,
            xtol=1e-10,
            max_nfev=600,
        )
        if not res.success:
            continue
        norm = float(np.linalg.norm(residuals(res.x)))
        if norm < best_norm:
            best_norm = norm
            best = res.x

    scale = max(float(np.linalg.norm(targets)), 1e-6)
    if best is None:
        raise CijFitError(
            f'无法用单晶立方 c_ij 拟合 BV/BR/GV/GR（优化未收敛）。'
            f' 表值: BV={BV:.4g}, BR={BR:.4g}, GV={GV:.4g}, GR={GR:.4g}。'
            ' 四列可能来自多相混合有效模量且不自洽，请提供 c11/c12/c44。'
        )

    rel = best_norm / scale
    if rel > rel_tol:
        m_try = hill_moduli_cubic(best[0], best[1], best[2])
        raise CijFitError(
            f'BV/BR/GV/GR 与单晶立方 c_ij 自洽性不足（相对残差 {rel:.1%}，阈值 {rel_tol:.0%}）。'
            f' 表值: BV={BV:.4g}, BR={BR:.4g}, GV={GV:.4g}, GR={GR:.4g}；'
            f' 最近拟合: BV={m_try["BV"]:.4g}, BR={m_try["BR"]:.4g}, '
            f'GV={m_try["GV"]:.4g}, GR={m_try["GR"]:.4g}。'
            ' 请核对数据或改提供弹性常数 c11/c12/c44。'
        )

    c11, c12, c44 = best
    return {
        'c11': float(c11),
        'c12': float(c12),
        'c44': float(c44),
        'cij_method': 'voigt_reuss_fit',
    }


def cij_from_voigt_reuss(
    BV: float,
    BR: float,
    GV: float,
    GR: float,
    *,
    bh: float | None = None,
    gh: float | None = None,
) -> dict[str, float]:
    """
    由表中 BV/BR/GV/GR 严格反推立方 c_ij（HTEM 单晶四式约束）。
    拟合失败抛出 CijFitError，不降级为加权或各向同性近似。
    """
    BV, BR, GV, GR = float(BV), float(BR), float(GV), float(GR)

    if abs(GV - GR) < 1e-8 and abs(BV - BR) < 1e-8:
        bh_val = float(bh) if bh is not None else BV
        gh_val = float(gh) if gh is not None else GV
        return isotropic_cij_from_bg(bh_val, gh_val)

    return _fit_cubic_cij_voigt_reuss(BV, BR, GV, GR)
