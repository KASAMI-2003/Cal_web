"""应力-应变 vs 能量-应变双路线自动交叉校验。"""

from __future__ import annotations

import os
from typing import Any

from .parser import scan_work_dir


def compare_dual_methods(work_dir: str, element: str | None = None) -> dict[str, Any]:
    """在同一目录尝试两种 method 解析并比较 Cij。"""
    if not work_dir or not os.path.isdir(work_dir):
        return {'available': False, 'message': '无效工作目录'}

    results: dict[str, dict[str, float]] = {}
    errors: dict[str, str] = {}
    for method in ('stress_strain', 'energy_strain'):
        try:
            scan = scan_work_dir(work_dir, method=method)
            results[method] = {k: float(v) for k, v in scan['cij'].items()}
        except Exception as e:
            errors[method] = str(e)

    if len(results) < 2:
        return {
            'available': False,
            'partial': results,
            'errors': errors,
            'message': '目录中未能同时解析两种方法结果',
        }

    keys = sorted(set(results['stress_strain']) & set(results['energy_strain']))
    per: dict[str, float] = {}
    max_rel = 0.0
    for k in keys:
        a, b = results['stress_strain'][k], results['energy_strain'][k]
        denom = max(abs(a), abs(b), 1e-6)
        rel = abs(a - b) / denom * 100
        per[k] = round(rel, 2)
        max_rel = max(max_rel, rel)

    passed = max_rel <= 10.0
    return {
        'available': True,
        'element': element,
        'stress_strain': results['stress_strain'],
        'energy_strain': results['energy_strain'],
        'per_component_pct': per,
        'max_relative_pct': round(max_rel, 2),
        'passed': passed,
        'dual_method_passed': passed,
        'message': f'双方法最大相对偏差 {max_rel:.1f}%' + ('，通过' if passed else '，建议复核'),
    }
