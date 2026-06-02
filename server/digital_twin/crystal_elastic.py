"""立方 / 六方 / 体心（立方对称）弹性刚度矩阵。"""

from __future__ import annotations

import numpy as np


def cubic_C_matrix(c11: float, c12: float, c44: float) -> np.ndarray:
    C = np.zeros((6, 6))
    C[0, 0] = c11
    C[0, 1] = c12
    C[0, 2] = c12
    C[1, 1] = c11
    C[1, 2] = c12
    C[2, 2] = c11
    C[3, 3] = c44
    C[4, 4] = c44
    C[5, 5] = c44
    for i in range(6):
        for j in range(i):
            C[i, j] = C[j, i]
    return C


def hexagonal_C_matrix(c11: float, c12: float, c13: float, c33: float, c44: float) -> np.ndarray:
    C = np.zeros((6, 6))
    C[0, 0] = C[1, 1] = c11
    C[0, 1] = C[1, 0] = c12
    C[0, 2] = C[1, 2] = C[2, 0] = C[2, 1] = c13
    C[2, 2] = c33
    C[3, 3] = C[4, 4] = c44
    C[5, 5] = (c11 - c12) / 2.0
    return C


def build_C_matrix(crystal: str, cij: dict[str, float]) -> np.ndarray:
    crystal = (crystal or 'cubic').lower()
    if crystal in ('hcp', 'hex', 'hexagonal'):
        return hexagonal_C_matrix(
            float(cij['C11']),
            float(cij['C12']),
            float(cij['C13']),
            float(cij['C33']),
            float(cij['C44']),
        )
    # fcc/bcc 均按立方 3 独立分量
    return cubic_C_matrix(float(cij['C11']), float(cij['C12']), float(cij['C44']))
