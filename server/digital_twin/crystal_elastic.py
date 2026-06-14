"""
兼容旧 import 路径（fedorov_crosscheck 等）。

新代码请直接使用 crystal_systems.build_C_matrix / build_elasticity_state_from_row。
"""

from __future__ import annotations

import numpy as np

from .crystal_systems.cubic import CubicHandler
from .crystal_systems.hexagonal import HexagonalHandler
from .crystal_systems.registry import build_C_matrix


def cubic_C_matrix(c11: float, c12: float, c44: float) -> np.ndarray:
    return CubicHandler().build_C_matrix({'c11': c11, 'c12': c12, 'c44': c44})


def hexagonal_C_matrix(c11: float, c12: float, c13: float, c33: float, c44: float) -> np.ndarray:
    return HexagonalHandler().build_C_matrix(
        {'c11': c11, 'c12': c12, 'c13': c13, 'c33': c33, 'c44': c44}
    )
