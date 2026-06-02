"""page2_search 高级筛选：晶系、计算方法、模量区间、稳定性。"""

from __future__ import annotations

import re
from typing import Any


def _float_val(row: dict, *keys: str) -> float | None:
    for k in keys:
        v = row.get(k)
        if v is None or v == '':
            continue
        try:
            return float(v)
        except (TypeError, ValueError):
            m = re.search(r'[\d.]+', str(v))
            if m:
                return float(m.group(0))
    return None


def _structure_match(row: dict, structure: str) -> bool:
    if not structure or structure == 'all':
        return True
    text = ' '.join(
        str(row.get(k, '') or '')
        for k in ('晶体结构', 'structure', 'crystal_system', 'material_name', 'notes', 'data_source')
    ).lower()
    s = structure.lower()
    mapping = {
        'fcc': ('fcc', '面心', 'fm-3m', 'cubic', '立方'),
        'bcc': ('bcc', '体心', 'im-3m', 'cubic', '立方'),
        'hcp': ('hcp', 'hex', '六方', 'hexagonal', 'p6'),
    }
    for token in mapping.get(s, (s,)):
        if token in text:
            return True
    return False


def _method_match(row: dict, method: str) -> bool:
    if not method or method == 'all':
        return True
    text = ' '.join(
        str(row.get(k, '') or '')
        for k in ('data_source', 'calc_method', 'method', '备注', 'notes', 'calc_meta')
    ).lower()
    if method == 'stress_strain':
        return any(x in text for x in ('stress', 'stress_strain', '应力'))
    if method == 'energy_strain':
        return any(x in text for x in ('energy', 'energy_strain', '能量'))
    return method.lower() in text


def _modulus_in_range(row: dict, young_min: float | None, young_max: float | None) -> bool:
    e = _float_val(row, '杨氏模量E-H', 'E', 'young_modulus', 'E_H')
    if e is None:
        return young_min is None and young_max is None
    if young_min is not None and e < young_min:
        return False
    if young_max is not None and e > young_max:
        return False
    return True


def _stability_match(row: dict, stability: str) -> bool:
    if not stability or stability == 'all':
        return True
    passed = row.get('born_passed')
    if passed is None:
        passed = row.get('stability_passed')
    if passed is None:
        stab = row.get('stability')
        if isinstance(stab, dict):
            passed = stab.get('passed')
    if stability == 'passed':
        return passed is True or str(row.get('calc_exp_deviation_label', '')).startswith('within')
    if stability == 'failed':
        return passed is False or str(row.get('calc_exp_deviation_label', '')) == 'exceeds_15pct'
    if stability == 'review':
        return str(row.get('calc_exp_deviation_label', '')) in ('exceeds_15pct', 'needs_review')
    return True


def apply_search_filters(
    elements: list[dict],
    materials: list[dict],
    filters: dict[str, Any] | None,
) -> dict[str, list]:
    f = filters or {}
    structure = (f.get('structure') or 'all').strip().lower()
    method = (f.get('method') or 'all').strip().lower()
    stability = (f.get('stability') or 'all').strip().lower()
    try:
        y_min = float(f['young_min']) if f.get('young_min') not in (None, '') else None
    except (TypeError, ValueError):
        y_min = None
    try:
        y_max = float(f['young_max']) if f.get('young_max') not in (None, '') else None
    except (TypeError, ValueError):
        y_max = None

    def ok(row: dict) -> bool:
        return (
            _structure_match(row, structure)
            and _method_match(row, method)
            and _modulus_in_range(row, y_min, y_max)
            and _stability_match(row, stability)
        )

    return {
        'elements': [r for r in elements if ok(r)],
        'materials': [r for r in materials if ok(r)],
    }


def compute_source_deviation(local_row: dict, mp_row: dict) -> dict[str, Any] | None:
    """本地 vs MP 杨氏模量相对误差，供前端颜色编码。"""
    e_local = _float_val(local_row, '杨氏模量E-H', 'E')
    e_mp = _float_val(mp_row, '杨氏模量E-H', 'E', 'young_modulus_GPa')
    if e_local is None or e_mp is None or e_mp == 0:
        return None
    rel = abs(e_local - e_mp) / abs(e_mp) * 100
    if rel <= 5:
        level = 'good'
    elif rel <= 15:
        level = 'warn'
    else:
        level = 'bad'
    return {'relative_pct': round(rel, 2), 'level': level, 'local_E': e_local, 'mp_E': e_mp}
