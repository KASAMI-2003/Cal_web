"""
晶系注册表：推断、模量→c_ij、构造 HTEM 各向异性所需弹性状态。

数据流（上传 wt% 模量表）：
  twin_dat_probe.load_alloy_rows
    → enrich_alloy_row_from_moduli（按晶系反推 c_ij）
    → build_elasticity_state_from_row（C 矩阵 + Fedorov 柔度）
    → anisotropy_surface.compute_anisotropy_bundle（E / nu_max / v_l）
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import numpy as np

from .base import CrystalSystemHandler
from .cubic import CubicHandler
from .cubic_moduli import hill_moduli_cubic
from .fedorov import fedorov_S_from_C
from .hexagonal import HexagonalHandler
from ._stub import (
    MonoclinicHandler,
    OrthorhombicHandler,
    TetragonalHandler,
    TriclinicHandler,
    TrigonalHandler,
)

_HANDLERS: tuple[CrystalSystemHandler, ...] = (
    CubicHandler(),
    HexagonalHandler(),
    TetragonalHandler(),
    OrthorhombicHandler(),
    TrigonalHandler(),
    MonoclinicHandler(),
    TriclinicHandler(),
)  # 新增晶系：在此追加 Handler 实例

_BY_ID: dict[str, CrystalSystemHandler] = {h.spec.id: h for h in _HANDLERS}
_BY_HTEM: dict[str, CrystalSystemHandler] = {h.spec.htem_lc: h for h in _HANDLERS}

_ALIASES: dict[str, str] = {
    'c': 'cubic',
    'cubic': 'cubic',
    '立方': 'cubic',
    'fcc': 'cubic',
    'bcc': 'cubic',
    'face-centered cubic': 'cubic',
    'body-centered cubic': 'cubic',
    'h': 'hexagonal',
    'hex': 'hexagonal',
    'hcp': 'hexagonal',
    'hexagonal': 'hexagonal',
    '六方': 'hexagonal',
    'ti': 'tetragonal',
    'tetragonal': 'tetragonal',
    '四方': 'tetragonal',
    'o': 'orthorhombic',
    'orthorhombic': 'orthorhombic',
    '正交': 'orthorhombic',
    'ri': 'trigonal',
    'trigonal': 'trigonal',
    'rhombohedral': 'trigonal',
    '三方': 'trigonal',
    'm': 'monoclinic',
    'monoclinic': 'monoclinic',
    '单斜': 'monoclinic',
    'n': 'triclinic',
    'triclinic': 'triclinic',
    '三斜': 'triclinic',
}


@dataclass
class ElasticityState:
    """HTEM Fedorov 各向异性计算所需的完整弹性状态（供 anisotropy_surface 使用）。"""

    T: float
    P: float
    rho: float
    crystal_system: str  # 平台 id：cubic / hexagonal / …
    htem_lc: str  # HTEM LC 字母：C / H / …
    structure: str | None  # 结构标签：fcc / bcc / hcp（展示用，不影响对称性）
    C_matrix: np.ndarray  # 6×6 Voigt 刚度 (GPa)
    S_matrix_Fedorov: np.ndarray  # 6×6 Fedorov 柔度
    cij: dict[str, float]  # 该晶系独立弹性常数
    cij_source: str  # moduli_hill | table_cij | htem_sam | fallback
    crystal_display_zh: str


def normalize_crystal_system(name: str | None) -> str | None:
    if not name:
        return None
    key = re.sub(r'\s+', ' ', str(name).strip().lower())
    if key in _ALIASES:
        return _ALIASES[key]
    if key in _BY_ID:
        return key
    if key.upper() in _BY_HTEM:
        return _BY_HTEM[key.upper()].spec.id
    return None


def infer_structure(phases: str | None) -> str | None:
    if not phases:
        return None
    p = phases.lower()
    if 'fcc' in p or '面心' in p:
        return 'fcc'
    if 'bcc' in p or '体心' in p:
        return 'bcc'
    if 'hcp' in p or 'hex' in p or '六方' in p:
        return 'hcp'
    return None


def infer_crystal_system(
    phases: str | None = None,
    explicit: str | None = None,
) -> str:
    """
    推断晶系 id。优先级：显式列/参数 > phases 关键词匹配 > 默认 cubic。

    phases 规则示例：
      fcc / bcc / 立方 / fcc+bcc → cubic
      hcp / hex / 六方 → hexagonal
    """
    norm = normalize_crystal_system(explicit)
    if norm:
        return norm

    best_id = 'cubic'
    best_score = 0.0
    for handler in _HANDLERS:
        score = handler.phase_match_score(phases)
        if score > best_score:
            best_score = score
            best_id = handler.spec.id

    if best_score <= 0.0 and phases:
        p = phases.lower()
        if 'hcp' in p or 'hex' in p:
            return 'hexagonal'
        if '+' in p or 'mix' in p or '双相' in p:
            return 'cubic'

    return best_id


def get_handler(system_id: str) -> CrystalSystemHandler:
    sid = normalize_crystal_system(system_id) or system_id
    handler = _BY_ID.get(sid)
    if not handler:
        raise KeyError(f'未知晶系: {system_id}')
    return handler


def get_handler_by_htem_lc(htem_lc: str) -> CrystalSystemHandler:
    lc = (htem_lc or 'C').upper()
    handler = _BY_HTEM.get(lc)
    if not handler:
        raise KeyError(f'未知 HTEM LC: {htem_lc}')
    return handler


def list_crystal_systems() -> list[dict[str, Any]]:
    return [
        {
            'id': h.spec.id,
            'htem_lc': h.spec.htem_lc,
            'display_zh': h.spec.display_zh,
            'display_en': h.spec.display_en,
            'moduli_inverse_supported': h.spec.moduli_inverse_supported,
            'cij_keys': list(h.independent_cij_keys()),
        }
        for h in _HANDLERS
    ]


def _normalize_cij_keys(cij: dict[str, float]) -> dict[str, float]:
    return {str(k).lower(): float(v) for k, v in cij.items()}


def build_C_matrix(crystal_system: str, cij: dict[str, float]) -> np.ndarray:
    handler = get_handler(crystal_system)
    return handler.build_C_matrix(_normalize_cij_keys(cij))


def cij_from_moduli_for_system(
    crystal_system: str,
    B: float | None,
    G: float | None,
    E: float | None = None,
    nu: float | None = None,
    **kwargs,
) -> dict[str, float]:
    handler = get_handler(crystal_system)
    return handler.cij_from_moduli(B, G, E=E, nu=nu, **kwargs)


def enrich_alloy_row_from_moduli(
    row: dict[str, Any],
    *,
    phases: str | None = None,
    crystal_system: str | None = None,
) -> dict[str, Any]:
    """
    为 moduli_hill 行补全 c_ij 与晶系元数据。

    输入 row 需含 B+G 或 E+nu（通常来自 BH/GH 或 EH/nu_H 列）。
    输出追加 c11…、crystal_system、htem_lc、cij_source='moduli_hill' 等字段。
    """
    system = infer_crystal_system(phases, crystal_system or row.get('crystal_system'))
    handler = get_handler(system)
    B = row.get('B')
    G = row.get('G')
    E = row.get('E')
    nu = row.get('nu')
    cij = handler.cij_from_moduli(
        float(B) if B is not None else None,
        float(G) if G is not None else None,
        E=float(E) if E is not None else None,
        nu=float(nu) if nu is not None else None,
        bv=row.get('BV'),
        br=row.get('BR'),
        gv=row.get('GV'),
        gr=row.get('GR'),
    )
    out = dict(row)
    out.update(cij)
    out['crystal_system'] = system
    out['htem_lc'] = handler.spec.htem_lc
    out['structure'] = infer_structure(phases) or row.get('structure')
    out['cij_source'] = 'moduli_hill'
    out['crystal_display_zh'] = handler.spec.display_zh
    if system == 'cubic':
        try:
            meta_m = hill_moduli_cubic(out['c11'], out['c12'], out['c44'])
            out['zener_A'] = meta_m['zener_A']
            if row.get('AVR') is None:
                out['AVR'] = meta_m['AVR']
        except ValueError:
            pass
    return out


def build_elasticity_state_from_row(
    row: dict[str, Any],
    T_K: float,
    P_GPa: float,
) -> ElasticityState:
    """
    由 alloy_row 构造 HTEM 各向异性所需状态。

    c_ij 来源（按优先级）：
      1. 行内已有该晶系全部独立常数 → table_cij
      2. 立方且仅有 c11/c12/c44 → table_cij
      3. 否则从 B/G/E/nu 反推 → moduli_hill
    """
    system = infer_crystal_system(row.get('phases'), row.get('crystal_system'))
    handler = get_handler(system)
    keys = handler.independent_cij_keys()
    cij_source = row.get('cij_source') or 'table_cij'

    def _has_full_cij() -> bool:
        return bool(keys) and all(row.get(k) is not None for k in keys)

    if _has_full_cij():
        cij = {k: float(row[k]) for k in keys}
    elif row.get('c11') is not None and system == 'cubic' and row.get('c44') is not None:
        cij = {
            'c11': float(row['c11']),
            'c12': float(row['c12']),
            'c44': float(row['c44']),
        }
    else:
        enriched = enrich_alloy_row_from_moduli(
            row,
            phases=row.get('phases'),
            crystal_system=system,
        )
        system = enriched['crystal_system']
        handler = get_handler(system)
        keys = handler.independent_cij_keys()
        cij = {k: float(enriched[k]) for k in keys}
        cij_source = 'moduli_hill'

    C = handler.build_C_matrix(cij)
    rho = float(row.get('rho') or 6.5)
    return ElasticityState(
        T=float(T_K),
        P=float(P_GPa),
        rho=rho,
        crystal_system=system,
        htem_lc=handler.spec.htem_lc,
        structure=row.get('structure') or infer_structure(row.get('phases')),
        C_matrix=C,
        S_matrix_Fedorov=fedorov_S_from_C(C),
        cij=cij,
        cij_source=cij_source,
        crystal_display_zh=handler.spec.display_zh,
    )
