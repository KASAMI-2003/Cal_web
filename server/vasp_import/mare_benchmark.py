"""与 Simmons & Wang (1971) 实验值对比，计算 MARE 并生成偏差标签。"""

from __future__ import annotations

from typing import Any

# 立方/fcc 金属实验弹性常数 (GPa)，来源：Simmons & Wang 1971（论文引用）
EXPERIMENTAL_CIJ_GPA: dict[str, dict[str, float]] = {
    'CU': {'C11': 168.3, 'C12': 122.1, 'C44': 75.7},
    'AL': {'C11': 108.2, 'C12': 60.8, 'C44': 28.5},
    'NI': {'C11': 246.5, 'C12': 147.3, 'C44': 124.7},
    'FE': {'C11': 231.4, 'C12': 134.7, 'C44': 116.4},
    'TI': {'C11': 162.4, 'C12': 92.0, 'C13': 69.0, 'C33': 180.7, 'C44': 46.7},
    'MO': {'C11': 463.0, 'C12': 161.0, 'C44': 109.0},
    'W': {'C11': 501.0, 'C12': 176.0, 'C44': 151.0},
}

EXPERIMENTAL_MODULI_GPA: dict[str, dict[str, float]] = {
    'CU': {'B': 137.8, 'G': 47.1, 'E': 129.8},
    'AL': {'B': 76.6, 'G': 26.2, 'E': 70.3},
}


def _rel_err(calc: float, ref: float) -> float:
    if ref == 0:
        return 0.0 if calc == 0 else 1.0
    return abs(calc - ref) / abs(ref)


def compute_mare(element: str, cij: dict[str, float], moduli: dict[str, float] | None = None) -> dict[str, Any]:
    """返回 mare_pct、per_component、label、needs_review。"""
    key = (element or '').strip().upper()
    ref = EXPERIMENTAL_CIJ_GPA.get(key)
    if not ref:
        return {
            'mare_pct': None,
            'label': 'no_experimental_ref',
            'needs_review': False,
            'messages': [f'无 {element} 实验参考数据，跳过 MARE'],
        }

    keys = [k for k in ref if k in cij and cij[k] is not None]
    if not keys:
        return {
            'mare_pct': None,
            'label': 'missing_cij',
            'needs_review': True,
            'messages': ['缺少与实验对照的 Cij 分量'],
        }

    rels = [_rel_err(float(cij[k]), float(ref[k])) for k in keys]
    mare = sum(rels) / len(rels) * 100.0
    per = {k: round(_rel_err(float(cij[k]), float(ref[k])) * 100, 2) for k in keys}

    if mare <= 5:
        label = 'within_5pct'
    elif mare <= 10:
        label = 'within_10pct'
    elif mare <= 15:
        label = 'within_15pct'
    else:
        label = 'exceeds_15pct'

    moduli_mare = None
    if moduli and key in EXPERIMENTAL_MODULI_GPA:
        mref = EXPERIMENTAL_MODULI_GPA[key]
        mkeys = [k for k in ('B', 'G', 'E') if k in moduli and k in mref]
        if mkeys:
            moduli_mare = round(
                sum(_rel_err(float(moduli[k]), float(mref[k])) for k in mkeys) / len(mkeys) * 100,
                2,
            )

    return {
        'mare_pct': round(mare, 2),
        'moduli_mare_pct': moduli_mare,
        'per_component_pct': per,
        'reference': 'Simmons & Wang 1971',
        'reference_temperature_K': 300,
        'label': label,
        'calc_exp_deviation_label': label,
        'needs_review': mare > 15.0,
        'auto_reject_mare': mare > 15.0,
        'messages': [
            f'MARE={mare:.1f}% ({", ".join(f"{k}:{per[k]:.1f}%" for k in keys)})',
        ],
    }
