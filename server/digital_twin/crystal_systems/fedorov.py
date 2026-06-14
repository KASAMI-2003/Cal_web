"""Fedorov 张量形式：与 HTEM anisotropy.Anisotropy.dv/nv 及 init_Fedorov_matrix 一致。"""

from __future__ import annotations

import numpy as np


def fedorov_dv(vector: np.ndarray) -> np.ndarray:
    d = np.zeros(6)
    d[0] = vector[0] * vector[0]
    d[1] = vector[1] * vector[1]
    d[2] = vector[2] * vector[2]
    d[3] = np.sqrt(2) * vector[1] * vector[2]
    d[4] = np.sqrt(2) * vector[0] * vector[2]
    d[5] = np.sqrt(2) * vector[0] * vector[1]
    return d


def fedorov_nv(vector: np.ndarray) -> np.ndarray:
    return fedorov_dv(vector)


def fedorov_S_from_C(C: np.ndarray) -> np.ndarray:
    """Voigt 刚度 → Fedorov 柔度（与 HTEM init_Fedorov_matrix 一致）。"""
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
