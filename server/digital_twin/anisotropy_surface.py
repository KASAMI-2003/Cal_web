# -*- coding: utf-8 -*-
"""
HTEM 各向异性三维曲面数据，供 WebGL（Three.js）绘制。

物理量定义与 HTEM-main/source/anisotropy.py 一致：
  - E(θ,φ)：Young 模量方向图（Fedorov 柔度 + 方向向量 dv）
  - nu_max(θ,φ)：最大 Poisson 比（对 χ 取 max）
  - v_l(θ,φ)：纵波声速（Christoffel 方程最大特征值）

数据来源分支：
  1. 无上传文件 → HTEM SAM 插值 Si 温压网格（build_elasticity_at_tp）
  2. 上传成分表 → crystal_systems.build_elasticity_state_from_row(alloy_row)
     （按晶系构造 C 矩阵，再走同一套 Fedorov/Christoffel numpy 实现）

API 入口：compute_anisotropy_bundle → pyserver /api/digital_twin/anisotropy_surface
"""
from __future__ import annotations

import logging
import os
import sys

import numpy as np

# 保证可导入 htem_sam_bridge（同目录）
_BRIDGE_DIR = os.path.dirname(os.path.abspath(__file__))
if _BRIDGE_DIR not in sys.path:
    sys.path.insert(0, _BRIDGE_DIR)

from htem_sam_bridge import _ensure_htem_path, build_elasticity_at_tp, htem_available

try:
    from crystal_systems import ElasticityState, build_elasticity_state_from_row
except ImportError:
    from digital_twin.crystal_systems import ElasticityState, build_elasticity_state_from_row


def _elasticity_meta(state: ElasticityState) -> dict:
    """写入 JSON 响应的晶系与 c_ij 来源字段（前端侧栏/状态栏展示）。"""
    meta = {
        'crystal_system': state.crystal_system,
        'htem_lc': state.htem_lc,
        'crystal_display_zh': state.crystal_display_zh,
        'structure': state.structure,
        'cij_source': state.cij_source,
        'rho': round(state.rho, 4),
    }
    if state.cij:
        try:
            if state.crystal_system == 'cubic' and len(state.cij) >= 3:
                from crystal_systems.cubic_moduli import hill_moduli_cubic

                m = hill_moduli_cubic(state.cij['c11'], state.cij['c12'], state.cij['c44'])
                meta['zener_A'] = round(m['zener_A'], 4)
        except Exception:
            pass
    return meta


def _bundle_from_elasticity_state(
    state: ElasticityState,
    n_phi: int,
    n_theta: int,
    n_chi: int,
    model_tag: str,
) -> dict:
    """由 ElasticityState 生成 E / nu_max / v_l 三套球面网格 + 晶系元数据。"""
    S_fedorov = state.S_matrix_Fedorov
    phi_e, theta_e, M_e = _youngs_E_surface_numpy(S_fedorov, n_phi, n_theta)
    phi_n, theta_n, M_n = _poisson_nu_max_surface_numpy(S_fedorov, n_phi, n_theta, n_chi)
    phi_v, theta_v, M_v = _sound_vl_surface(state.C_matrix, state.rho, n_phi, n_theta)
    payload = {
        'T_K': round(state.T, 2),
        'P_GPa': round(state.P, 3),
        'n_phi': n_phi,
        'n_theta': n_theta,
        'n_chi': n_chi,
        'model': model_tag,
        'E': _pack_surface(phi_e, theta_e, M_e, 'GPa', aniso_squared=False),
        'nu_max': _pack_surface(phi_n, theta_n, M_n, '1', aniso_squared=True),
        'vl': _pack_surface(phi_v, theta_v, M_v, 'km/s', aniso_squared=True),
    }
    payload.update(_elasticity_meta(state))
    return payload


def _fedorov_dv(vector: np.ndarray) -> np.ndarray:
    """与 HTEM Anisotropy.dv 一致。"""
    d = np.zeros(6)
    d[0] = vector[0] * vector[0]
    d[1] = vector[1] * vector[1]
    d[2] = vector[2] * vector[2]
    d[3] = np.sqrt(2) * vector[1] * vector[2]
    d[4] = np.sqrt(2) * vector[0] * vector[2]
    d[5] = np.sqrt(2) * vector[0] * vector[1]
    return d


def _fedorov_nv(vector: np.ndarray) -> np.ndarray:
    """与 HTEM Anisotropy.nv 一致。"""
    return _fedorov_dv(vector)


def _cubic_C_matrix(c11: float, c12: float, c44: float) -> np.ndarray:
    """立方 Voigt 刚度矩阵（与 HTEM format_Cij('C') + method.symmetry 对称化一致）。"""
    C = np.zeros((6, 6))
    C[0, 0] = c11
    C[0, 1] = c12
    C[3, 3] = c44
    C[1, 1] = C[0, 0]
    C[2, 2] = C[0, 0]
    C[0, 2] = C[0, 1]
    C[1, 2] = C[0, 1]
    C[4, 4] = C[3, 3]
    C[5, 5] = C[3, 3]
    # HTEM method.py 在 format_Cij 后会镜像下三角，Fedorov/Christoffel 均依赖对称 C
    C[1, 0] = C[0, 1]
    C[2, 0] = C[0, 2]
    C[2, 1] = C[1, 2]
    return C


def _fedorov_S_from_C(C: np.ndarray) -> np.ndarray:
    """由 Voigt 刚度矩阵求 Fedorov 柔度矩阵（与 HTEM init_Fedorov_matrix 一致）。"""
    C_f = np.zeros((6, 6))
    for i in range(6):
        for j in range(6):
            if i <= 2 and j <= 2:
                C_f[i, j] = C[i, j]
            elif i >= 3 and j >= 3:
                C_f[i, j] = 2 * C[i, j]
            else:
                C_f[i, j] = np.sqrt(2) * C[i, j]
    return np.linalg.inv(C_f)


def _default_cij_at_tp(T_K: float, P_GPa: float) -> tuple[float, float, float, float]:
    """
    HTEM/SAM 不可用时的立方 Si 参考弹性常数（300K、0GPa 附近），带简单温压修正。
    数值来自 HTEM 官方 Si 示例 Elasticity_cold+NVT_s4.dat。
    """
    T_K = float(np.clip(T_K, 273.0, 2000.0))
    P_GPa = float(np.clip(P_GPa, 0.0, 50.0))
    dT = T_K - 300.0
    dP = P_GPa - 0.0
    c11 = 154.2 - 0.04 * dT + 2.5 * dP
    c12 = 63.8 - 0.01 * dT + 1.8 * dP
    c44 = 73.8 - 0.015 * dT + 0.05 * dP
    rho = 2.32 - 0.0003 * dT + 0.08 * dP
    return float(c11), float(c12), float(c44), float(max(rho, 0.5))


class _NumpyElasticity:
    """无 HTEM 依赖的轻量弹性对象，供曲面与 Christoffel 声速计算。"""

    def __init__(self, c11, c12, c44, rho, T_K, P_GPa, crystal_system='cubic', c13=None, c33=None):
        self.T = float(T_K)
        self.P = float(P_GPa)
        self.rho = float(rho)
        self.crystal_system = crystal_system
        cij = {'C11': c11, 'C12': c12, 'C44': c44}
        if crystal_system in ('hexagonal', 'hcp', 'hex') and c13 is not None and c33 is not None:
            cij['C13'] = c13
            cij['C33'] = c33
        try:
            from digital_twin.crystal_elastic import build_C_matrix

            self.C_matrix = build_C_matrix(crystal_system, cij)
        except Exception:
            self.C_matrix = _cubic_C_matrix(c11, c12, c44)
        self.S_matrix_Fedorov = _fedorov_S_from_C(self.C_matrix)


def _metal_cij_fallback(symbol: str, T_K: float, P_GPa: float):
    """优先使用论文金属预设，否则 Si 参考。"""
    try:
        from digital_twin.metal_presets import get_metal_preset

        p = get_metal_preset(symbol)
        if p:
            return (
                p['c11'],
                p['c12'],
                p['c44'],
                p['rho'],
                p.get('crystal_system', 'cubic'),
                p.get('c13'),
                p.get('c33'),
                f"metal_preset_{symbol}",
            )
    except Exception:
        pass
    c11, c12, c44, rho = _default_cij_at_tp(T_K, P_GPa)
    return c11, c12, c44, rho, 'cubic', None, None, 'numpy_fallback_si'


def _build_elasticity_numpy(alloy_row: dict | None, T_K: float, P_GPa: float) -> tuple:
    if alloy_row is not None:
        state = build_elasticity_state_from_row(alloy_row, T_K, P_GPa)
        return state, None
    sym = os.environ.get('TWIN_METAL_SYMBOL', 'Cu')
    c11, c12, c44, rho, crystal, c13, c33, _tag = _metal_cij_fallback(sym, T_K, P_GPa)
    preset_row = {
        'c11': c11,
        'c12': c12,
        'c44': c44,
        'rho': rho,
        'crystal_system': crystal,
        'c13': c13,
        'c33': c33,
        'cij_source': 'fallback',
    }
    return build_elasticity_state_from_row(preset_row, T_K, P_GPa), _tag


def _youngs_E_surface_numpy(S_fedorov, n_phi: int, n_theta: int):
    phi = np.linspace(0.0, np.pi, n_phi)
    theta = np.linspace(0.0, 2.0 * np.pi, n_theta)
    dv = []
    for i in range(n_phi):
        for j in range(n_theta):
            v = np.array(
                [
                    np.sin(phi[i]) * np.cos(theta[j]),
                    np.sin(phi[i]) * np.sin(theta[j]),
                    np.cos(phi[i]),
                ]
            )
            v = v / np.linalg.norm(v)
            dv.append(_fedorov_dv(v))
    dv = np.array(dv)
    M_list = [1.0 / np.dot(np.dot(dv[k], S_fedorov), dv[k]) for k in range(len(dv))]
    M = np.array(M_list).reshape((n_phi, n_theta))
    return phi, theta, M


def _poisson_nu_max_surface_numpy(S_fedorov, n_phi: int, n_theta: int, n_chi: int):
    phi = np.linspace(0.0, np.pi, n_phi)
    theta = np.linspace(0.0, 2.0 * np.pi, n_theta)
    chi = np.linspace(0.0, 2.0 * np.pi, n_chi)
    dv_list = []
    for i in range(n_phi):
        for j in range(n_theta):
            v = np.array(
                [
                    np.sin(phi[i]) * np.cos(theta[j]),
                    np.sin(phi[i]) * np.sin(theta[j]),
                    np.cos(phi[i]),
                ]
            )
            v = v / np.linalg.norm(v)
            dv_list.append(_fedorov_dv(v))
    dv = np.array(dv_list)
    nv_list = []
    for i in range(n_phi):
        for j in range(n_theta):
            for k in range(n_chi):
                vec = np.array(
                    [
                        np.sin(theta[j]) * np.sin(chi[k])
                        - np.cos(phi[i]) * np.cos(theta[j]) * np.cos(chi[k]),
                        -np.cos(theta[j]) * np.sin(chi[k])
                        - np.cos(phi[i]) * np.sin(theta[j]) * np.cos(chi[k]),
                        np.sin(phi[i]) * np.cos(chi[k]),
                    ]
                )
                nv_list.append(_fedorov_nv(vec / np.linalg.norm(vec)))
    nv = np.array(nv_list)
    E_list = [1.0 / np.dot(np.dot(dv[i], S_fedorov), dv[i]) for i in range(len(dv))]
    poisson_list = []
    for i in range(len(dv)):
        for j in range(n_chi):
            idx = i * n_chi + j
            poisson_list.append(-E_list[i] * np.dot(np.dot(dv[i], S_fedorov), nv[idx]))
    M_arr = np.array(poisson_list).reshape((n_phi, n_theta, n_chi))
    M_max = np.max(M_arr, axis=2)
    return phi, theta, M_max


def _resolve_fallback_alloy_row(
    alloy_row: dict | None,
    fallback_metal: str | None,
) -> tuple[dict | None, str]:
    """上传成分表优先；否则用金属预设（仅 HTEM 不可用时的回退）。"""
    if alloy_row is not None:
        return alloy_row, 'alloy_table'
    sym = (fallback_metal or os.environ.get('TWIN_METAL_SYMBOL') or 'Cu').strip()
    try:
        from digital_twin.metal_presets import alloy_row_from_preset

        row = alloy_row_from_preset(sym)
        if row:
            return row, f'metal_preset_{sym.capitalize()}'
    except Exception:
        pass
    return None, 'numpy_fallback_si'


def _compute_anisotropy_numpy_fallback(
    T_K: float,
    P_GPa: float,
    n_phi: int,
    n_theta: int,
    n_chi: int,
    alloy_row: dict | None = None,
    fallback_metal: str | None = None,
):
    alloy_row, model_tag = _resolve_fallback_alloy_row(alloy_row, fallback_metal)
    state, _extra = _build_elasticity_numpy(alloy_row, T_K, P_GPa)
    if model_tag == 'alloy_table' and alloy_row:
        model_tag = f"alloy_table:{alloy_row.get('label', '')}"
    elif _extra:
        model_tag = _extra
    payload = _bundle_from_elasticity_state(state, n_phi, n_theta, n_chi, model_tag)
    if alloy_row:
        if alloy_row.get('cij_method'):
            payload['cij_method'] = alloy_row['cij_method']
        if alloy_row.get('zener_A') is not None:
            payload['zener_A'] = alloy_row['zener_A']
    return payload


def _compute_anisotropy_htem(
    T_K: float,
    P_GPa: float,
    n_phi: int,
    n_theta: int,
    n_chi: int,
    alloy_row: dict | None = None,
):
    if alloy_row is not None:
        state = build_elasticity_state_from_row(alloy_row, T_K, P_GPa)
        model_tag = (
            f"metal_preset:{alloy_row.get('label', '')}"
            if alloy_row.get('_source') == 'metal_preset'
            else f"alloy_table:{alloy_row.get('label', '')}"
        )
        payload = _bundle_from_elasticity_state(state, n_phi, n_theta, n_chi, model_tag)
        if alloy_row.get('cij_method'):
            payload['cij_method'] = alloy_row['cij_method']
        if alloy_row.get('zener_A') is not None:
            payload['zener_A'] = alloy_row['zener_A']
        return payload

    Eobj = build_elasticity_at_tp(T_K, P_GPa)
    model_tag = 'HTEM_SAM'
    sam_state = ElasticityState(
        T=float(Eobj.T),
        P=float(Eobj.P),
        rho=float(Eobj.rho),
        crystal_system='cubic',
        htem_lc='C',
        structure=None,
        C_matrix=np.asarray(Eobj.C_matrix, dtype=float),
        S_matrix_Fedorov=np.asarray(Eobj.S_matrix_Fedorov, dtype=float),
        cij={},
        cij_source='htem_sam',
        crystal_display_zh='立方',
    )
    return _bundle_from_elasticity_state(sam_state, n_phi, n_theta, n_chi, model_tag)


def _elasticity_from_alloy_cij(
    c11: float,
    c12: float,
    c44: float,
    rho: float,
    T_K: float,
    P_GPa: float,
):
    """由立方 c11/c12/c44 与密度构造弹性对象（成分表驱动）；不依赖 HTEM anisotropy/imageio。"""
    return _NumpyElasticity(c11, c12, c44, rho, T_K, P_GPa)


def _pack_surface(phi, theta, M, unit: str, aniso_squared: bool = False):
    mmin = float(np.nanmin(M))
    mmax = float(np.nanmax(M))
    eps = 1e-30
    if aniso_squared:
        ratio = float((mmax / max(mmin, eps)) ** 2) if mmin > 0 else 1.0
    else:
        ratio = float(mmax / max(mmin, eps)) if mmin > 0 else 1.0
    return {
        'phi': phi.tolist(),
        'theta': theta.tolist(),
        'values': M.tolist(),
        'min': round(mmin, 6),
        'max': round(mmax, 6),
        'anisotropy_ratio': round(ratio, 4),
        'unit': unit,
    }


def _youngs_E_surface(S_fedorov, n_phi: int, n_theta: int, ano):
    phi = np.linspace(0.0, np.pi, n_phi)
    theta = np.linspace(0.0, 2.0 * np.pi, n_theta)
    dv = []
    for i in range(n_phi):
        for j in range(n_theta):
            v = np.array(
                [
                    np.sin(phi[i]) * np.cos(theta[j]),
                    np.sin(phi[i]) * np.sin(theta[j]),
                    np.cos(phi[i]),
                ]
            )
            v = v / np.linalg.norm(v)
            dv.append(ano.dv(v))
    dv = np.array(dv)
    M_list = [1.0 / np.dot(np.dot(dv[k], S_fedorov), dv[k]) for k in range(len(dv))]
    M = np.array(M_list).reshape((n_phi, n_theta))
    return phi, theta, M


def _poisson_nu_max_surface(S_fedorov, n_phi: int, n_theta: int, n_chi: int, ano):
    phi = np.linspace(0.0, np.pi, n_phi)
    theta = np.linspace(0.0, 2.0 * np.pi, n_theta)
    chi = np.linspace(0.0, 2.0 * np.pi, n_chi)
    dv_list = []
    for i in range(n_phi):
        for j in range(n_theta):
            v = np.array(
                [
                    np.sin(phi[i]) * np.cos(theta[j]),
                    np.sin(phi[i]) * np.sin(theta[j]),
                    np.cos(phi[i]),
                ]
            )
            v = v / np.linalg.norm(v)
            dv_list.append(ano.dv(v))
    dv = np.array(dv_list)
    nv_list = []
    for i in range(n_phi):
        for j in range(n_theta):
            for k in range(n_chi):
                vec = np.array(
                    [
                        np.sin(theta[j]) * np.sin(chi[k])
                        - np.cos(phi[i]) * np.cos(theta[j]) * np.cos(chi[k]),
                        -np.cos(theta[j]) * np.sin(chi[k])
                        - np.cos(phi[i]) * np.sin(theta[j]) * np.cos(chi[k]),
                        np.sin(phi[i]) * np.cos(chi[k]),
                    ]
                )
                nv_list.append(ano.nv(vec / np.linalg.norm(vec)))
    nv = np.array(nv_list)
    E_list = [1.0 / np.dot(np.dot(dv[i], S_fedorov), dv[i]) for i in range(len(dv))]
    poisson_list = []
    for i in range(len(dv)):
        for j in range(n_chi):
            idx = i * n_chi + j
            poisson_list.append(-E_list[i] * np.dot(np.dot(dv[i], S_fedorov), nv[idx]))
    M_arr = np.array(poisson_list).reshape((n_phi, n_theta, n_chi))
    M_max = np.max(M_arr, axis=2)
    return phi, theta, M_max


def _sound_vl_surface(Cm: np.ndarray, rho: float, n_phi: int, n_theta: int):
    """与 anisotropy.calc_sound_3D 中 v_l 一致（km/s）。"""
    phi = np.linspace(0.0, np.pi, n_phi)
    theta = np.linspace(0.0, 2.0 * np.pi, n_theta)
    npt = n_phi * n_theta
    l1 = np.array([np.sin(phi[i]) * np.cos(theta[j]) for i in range(n_phi) for j in range(n_theta)])
    l2 = np.array([np.sin(phi[i]) * np.sin(theta[j]) for i in range(n_phi) for j in range(n_theta)])
    l3 = np.array([np.cos(phi[i]) for i in range(n_phi) for j in range(n_theta)])

    Christoffel_00 = [
        Cm[0, 0] * l1[i] ** 2
        + Cm[5, 5] * l2[i] ** 2
        + Cm[4, 4] * l3[i] ** 2
        + 2 * Cm[4, 5] * l2[i] * l3[i]
        + 2 * Cm[0, 4] * l3[i] * l1[i]
        + 2 * Cm[0, 5] * l1[i] * l2[i]
        for i in range(npt)
    ]
    Christoffel_11 = [
        Cm[5, 5] * l1[i] ** 2
        + Cm[1, 1] * l2[i] ** 2
        + Cm[3, 3] * l3[i] ** 2
        + 2 * Cm[1, 3] * l2[i] * l3[i]
        + 2 * Cm[3, 5] * l3[i] * l1[i]
        + 2 * Cm[1, 5] * l1[i] * l2[i]
        for i in range(npt)
    ]
    Christoffel_22 = [
        Cm[4, 4] * l1[i] ** 2
        + Cm[3, 3] * l2[i] ** 2
        + Cm[2, 2] * l3[i] ** 2
        + 2 * Cm[2, 3] * l2[i] * l3[i]
        + 2 * Cm[2, 4] * l3[i] * l1[i]
        + 2 * Cm[3, 4] * l1[i] * l2[i]
        for i in range(npt)
    ]
    Christoffel_01 = [
        Cm[0, 5] * l1[i] ** 2
        + Cm[1, 5] * l2[i] ** 2
        + Cm[3, 4] * l3[i] ** 2
        + (Cm[3, 5] + Cm[1, 4]) * l2[i] * l3[i]
        + (Cm[0, 3] + Cm[4, 5]) * l3[i] * l1[i]
        + (Cm[0, 1] + Cm[5, 5]) * l1[i] * l2[i]
        for i in range(npt)
    ]
    Christoffel_02 = [
        Cm[0, 4] * l1[i] ** 2
        + Cm[3, 4] * l2[i] ** 2
        + Cm[2, 4] * l3[i] ** 2
        + (Cm[3, 4] + Cm[2, 5]) * l2[i] * l3[i]
        + (Cm[0, 2] + Cm[4, 4]) * l3[i] * l1[i]
        + (Cm[0, 3] + Cm[4, 5]) * l1[i] * l2[i]
        for i in range(npt)
    ]
    Christoffel_12 = [
        Cm[4, 5] * l1[i] ** 2
        + Cm[1, 3] * l2[i] ** 2
        + Cm[2, 3] * l3[i] ** 2
        + (Cm[3, 3] + Cm[1, 2]) * l2[i] * l3[i]
        + (Cm[2, 5] + Cm[3, 4]) * l3[i] * l1[i]
        + (Cm[1, 4] + Cm[3, 5]) * l1[i] * l2[i]
        for i in range(npt)
    ]
    vl = []
    for i in range(npt):
        G = np.array(
            [
                [Christoffel_00[i], Christoffel_01[i], Christoffel_02[i]],
                [Christoffel_01[i], Christoffel_11[i], Christoffel_12[i]],
                [Christoffel_02[i], Christoffel_12[i], Christoffel_22[i]],
            ]
        )
        w = np.linalg.eigh(G * (10**9))[0]
        vl.append(np.sqrt(w[2] / rho / 1000.0) / 1000.0)
    v_l = np.array(vl).reshape((n_phi, n_theta))
    return phi, theta, v_l


def compute_anisotropy_bundle(
    T_K: float,
    P_GPa: float,
    n_phi: int = 48,
    n_theta: int = 72,
    n_chi: int = 48,
    alloy_row: dict | None = None,
    fallback_metal: str | None = None,
):
    """
    返回 E、nu_max、v_l 三套球面参数化数据（r(θ,φ)=物理量，与 HTEM 论文图一致）。

    alloy_row：上传成分表行（c_ij 或 moduli_hill 的 B/G），经 crystal_systems 按晶系
              构造 C 矩阵；响应含 crystal_system / htem_lc / cij_source。
    fallback_metal：HTEM 不可用时的金属预设回退（Cu/Al/Ni/Ti）。
    无 alloy_row 且 HTEM 可用 → Si SAM 温压插值；否则 numpy 回退。
    """
    n_phi = max(12, min(96, int(n_phi)))
    n_theta = max(24, min(144, int(n_theta)))
    n_chi = max(24, min(120, int(n_chi)))

    if htem_available():
        try:
            return _compute_anisotropy_htem(T_K, P_GPa, n_phi, n_theta, n_chi, alloy_row=alloy_row)
        except Exception as e:
            logging.warning('HTEM 各向异性曲面失败，回退 numpy: %s', e)

    return _compute_anisotropy_numpy_fallback(
        T_K,
        P_GPa,
        n_phi,
        n_theta,
        n_chi,
        alloy_row=alloy_row,
        fallback_metal=fallback_metal,
    )
