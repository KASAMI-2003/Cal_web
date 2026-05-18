# -*- coding: utf-8 -*-
"""
HTEM 各向异性三维曲面数据（与 anisotropy.py 中 E、nu_max、v_l 定义一致），供 WebGL 使用。
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

from htem_sam_bridge import _ensure_htem_path, build_elasticity_at_tp


def _elasticity_from_alloy_cij(
    c11: float,
    c12: float,
    c44: float,
    rho: float,
    T_K: float,
    P_GPa: float,
):
    """由立方 c11/c12/c44 与密度构造 Elasticity（与 HTEM 立方 C 阶一致），用于成分表驱动。"""
    _ensure_htem_path()
    from source.elasticity import Elasticity

    V_nom = 20.0
    row = np.array(
        [float(T_K), V_nom, float(P_GPa), float(rho), float(c11), float(c12), float(c44)],
        dtype=float,
    )
    E = Elasticity()
    E.T = float(T_K)
    E.P = float(P_GPa)
    E.V = V_nom
    E.rho = float(rho)
    E.C_matrix = E.format_Cij("C", row)
    E.S_matrix = np.linalg.inv(E.C_matrix)
    E.init_Fedorov_matrix()
    return E


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
):
    """
    返回 E、nu_max、v_l 三套球面参数化数据（与论文图一致：r(θ,φ)=物理量）。
    alloy_row：含 c11,c12,c44,rho（可选，缺省 rho=6.5 g/cm³）时走成分表，不经 SAM。
    """
    _ensure_htem_path()
    from source.anisotropy import Anisotropy

    if alloy_row is not None:
        rho = float(alloy_row.get("rho") or 6.5)
        Eobj = _elasticity_from_alloy_cij(
            float(alloy_row["c11"]),
            float(alloy_row["c12"]),
            float(alloy_row["c44"]),
            rho,
            T_K,
            P_GPa,
        )
    else:
        Eobj = build_elasticity_at_tp(T_K, P_GPa)
    S_fedorov = Eobj.S_matrix_Fedorov
    ano = Anisotropy()

    n_phi = max(12, min(96, int(n_phi)))
    n_theta = max(24, min(144, int(n_theta)))
    n_chi = max(24, min(120, int(n_chi)))

    phi_e, theta_e, M_e = _youngs_E_surface(S_fedorov, n_phi, n_theta, ano)
    phi_n, theta_n, M_n = _poisson_nu_max_surface(S_fedorov, n_phi, n_theta, n_chi, ano)
    phi_v, theta_v, M_v = _sound_vl_surface(Eobj.C_matrix, Eobj.rho, n_phi, n_theta)

    t = float(Eobj.T)
    p = float(Eobj.P)

    return {
        'T_K': round(t, 2),
        'P_GPa': round(p, 3),
        'n_phi': n_phi,
        'n_theta': n_theta,
        'n_chi': n_chi,
        'E': _pack_surface(phi_e, theta_e, M_e, 'GPa', aniso_squared=False),
        'nu_max': _pack_surface(phi_n, theta_n, M_n, '1', aniso_squared=True),
        'vl': _pack_surface(phi_v, theta_v, M_v, 'km/s', aniso_squared=True),
    }
