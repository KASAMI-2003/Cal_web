"""
按晶系划分的 HTEM 弹性常数与各向异性构造。

与 HTEM-main/source/elasticity.py 中 format_Cij 的 LC 字母码对齐：
  C=立方, H=六方, TI/TII=四方, O=正交, RI/RII=三方, M=单斜, N=三斜

扩展新晶系步骤：
  1. 在 crystal_systems/ 下新增 XxxHandler(CrystalSystemHandler)
  2. 实现 build_C_matrix、cij_from_moduli（可选）、phase_match_score
  3. 在 registry._HANDLERS 中注册实例

主入口：
  infer_crystal_system(phases) → build_elasticity_state_from_row(alloy_row) → 曲面 API
"""

from .base import CrystalSystemHandler, CrystalSystemSpec
from .fedorov import fedorov_S_from_C, fedorov_dv, fedorov_nv
from .registry import (
    ElasticityState,
    build_C_matrix,
    build_elasticity_state_from_row,
    cij_from_moduli_for_system,
    enrich_alloy_row_from_moduli,
    get_handler,
    get_handler_by_htem_lc,
    infer_crystal_system,
    infer_structure,
    list_crystal_systems,
    normalize_crystal_system,
)

__all__ = [
    'CrystalSystemHandler',
    'CrystalSystemSpec',
    'ElasticityState',
    'build_C_matrix',
    'build_elasticity_state_from_row',
    'cij_from_moduli_for_system',
    'enrich_alloy_row_from_moduli',
    'fedorov_S_from_C',
    'fedorov_dv',
    'fedorov_nv',
    'get_handler',
    'get_handler_by_htem_lc',
    'infer_crystal_system',
    'infer_structure',
    'list_crystal_systems',
    'normalize_crystal_system',
]
