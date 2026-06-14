"""
调用 HTEM elasticity.format_Cij 构造任意 LC 对称的 6×6 刚度矩阵。

E_input[4:] 为独立弹性常数，顺序与 HTEM write_output.filehead 一致。
HTEM 不可用时，立方(C)/六方(H) 回退到本地 handler。
"""

from __future__ import annotations

import logging
import os
import sys

import numpy as np

_HTEM_ELASTICITY = None


def _load_htem_elasticity():
    global _HTEM_ELASTICITY
    if _HTEM_ELASTICITY is not None:
        return _HTEM_ELASTICITY
    bridge_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    htem_src = os.path.join(bridge_dir, 'HTEM-main', 'source')
    if htem_src not in sys.path and os.path.isdir(htem_src):
        sys.path.insert(0, htem_src)
    try:
        from elasticity import Elasticity  # HTEM package

        _HTEM_ELASTICITY = Elasticity()
    except Exception as exc:
        logging.debug('HTEM Elasticity 不可用，回退本地矩阵构造: %s', exc)
        _HTEM_ELASTICITY = False
    return _HTEM_ELASTICITY


# HTEM format_Cij 中 E_input[4:] 为独立分量顺序（与 write_output filehead 一致）
_HTEM_CIJ_ORDER: dict[str, tuple[str, ...]] = {
    'C': ('c11', 'c12', 'c44'),
    'H': ('c11', 'c12', 'c13', 'c33', 'c44'),
    'TI': ('c11', 'c12', 'c13', 'c33', 'c44', 'c66'),
    'TII': ('c11', 'c12', 'c13', 'c16', 'c33', 'c44', 'c66'),
    'RI': ('c11', 'c12', 'c13', 'c14', 'c33', 'c44'),
    'RII': ('c11', 'c12', 'c13', 'c14', 'c15', 'c33', 'c44'),
    'O': ('c11', 'c12', 'c13', 'c22', 'c23', 'c33', 'c44', 'c55', 'c66'),
    'M': (
        'c11', 'c12', 'c13', 'c16', 'c22', 'c23', 'c26',
        'c33', 'c36', 'c44', 'c45', 'c55', 'c66',
    ),
}


def build_C_matrix_htem(htem_lc: str, cij: dict[str, float]) -> np.ndarray:
    """优先 HTEM format_Cij；失败时由 registry 中具体 handler 构造。"""
    lc = (htem_lc or 'C').upper()
    keys = _HTEM_CIJ_ORDER.get(lc)
    if not keys:
        raise ValueError(f'未知 HTEM LC: {htem_lc}')

    missing = [k for k in keys if k not in cij or cij[k] is None]
    if missing:
        raise ValueError(f'缺少 {lc} 晶系弹性常数: {missing}')

    E_input = np.zeros(25)
    for i, key in enumerate(keys):
        E_input[4 + i] = float(cij[key])

    el = _load_htem_elasticity()
    if el:
        try:
            return np.asarray(el.format_Cij(lc, E_input), dtype=float)
        except Exception as exc:
            logging.warning('HTEM format_Cij(%s) 失败: %s', lc, exc)

    from .cubic import CubicHandler
    from .hexagonal import HexagonalHandler

    _LOCAL = {'C': CubicHandler(), 'H': HexagonalHandler()}
    handler = _LOCAL.get(lc)
    if handler:
        return handler.build_C_matrix(cij)
    raise ValueError(f'HTEM format_Cij 不可用且本地未实现 LC={lc}')
