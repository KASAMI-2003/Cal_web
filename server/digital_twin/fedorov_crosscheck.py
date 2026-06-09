"""Fedorov 方向杨氏模量离线交叉校验（平台 vs 独立 numpy 实现）。"""

from __future__ import annotations

import numpy as np

from digital_twin.crystal_elastic import build_C_matrix
from digital_twin.metal_presets import alloy_row_from_preset, get_metal_preset


def _fedorov_S(C: np.ndarray) -> np.ndarray:
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


def _dv(v: np.ndarray) -> np.ndarray:
    d = np.zeros(6)
    d[0], d[1], d[2] = v[0] ** 2, v[1] ** 2, v[2] ** 2
    d[3] = np.sqrt(2) * v[1] * v[2]
    d[4] = np.sqrt(2) * v[0] * v[2]
    d[5] = np.sqrt(2) * v[0] * v[1]
    return d


def direction_E(S: np.ndarray, n: np.ndarray) -> float:
    d = _dv(n / np.linalg.norm(n))
    return 1.0 / float(np.dot(d, S @ d))


def _unit(*components: float) -> np.ndarray:
    v = np.array(components, dtype=float)
    return v / np.linalg.norm(v)


def _direction_to_grid_index(phi_arr: np.ndarray, theta_arr: np.ndarray, v: np.ndarray) -> tuple[int, int]:
    v = v / np.linalg.norm(v)
    phi = float(np.arccos(np.clip(v[2], -1.0, 1.0)))
    theta = float(np.arctan2(v[1], v[0]))
    if theta < 0:
        theta += 2.0 * np.pi
    i = int(np.argmin(np.abs(phi_arr - phi)))
    j = int(np.argmin(np.abs(theta_arr - theta)))
    return i, j


def _E_from_bundle_grid(bundle: dict, v: np.ndarray) -> float:
    block = bundle['E']
    phi_arr = np.asarray(block['phi'], dtype=float)
    theta_arr = np.asarray(block['theta'], dtype=float)
    values = np.asarray(block['values'], dtype=float)
    i, j = _direction_to_grid_index(phi_arr, theta_arr, v)
    return float(values[i, j])


def crosscheck_metal(symbol: str, n_random: int = 12) -> dict:
    preset = get_metal_preset(symbol)
    if not preset:
        return {'success': False, 'message': f'无预设金属 {symbol}'}

    cij = {
        'C11': preset['c11'],
        'C12': preset['c12'],
        'C44': preset['c44'],
    }
    if preset.get('crystal_system') == 'hexagonal':
        cij['C13'] = preset['c13']
        cij['C33'] = preset['c33']

    C = build_C_matrix(preset.get('crystal_system', 'cubic'), cij)
    S = _fedorov_S(C)

    from digital_twin.anisotropy_surface import compute_anisotropy_bundle

    alloy_row = alloy_row_from_preset(symbol)
    if alloy_row is None:
        return {'success': False, 'message': f'无法构造金属行 {symbol}'}
    alloy_row = dict(alloy_row)
    alloy_row['_source'] = 'metal_preset'

    bundle = compute_anisotropy_bundle(300, 0, n_phi=48, n_theta=72, alloy_row=alloy_row)

    phi_arr = np.asarray(bundle['E']['phi'], dtype=float)
    theta_arr = np.asarray(bundle['E']['theta'], dtype=float)
    values = np.asarray(bundle['E']['values'], dtype=float)

    rels = []
    samples = []

    # 1) 网格节点：平台值应与离线 Fedorov 公式一致（验证实现，而非网格分辨率）
    step_i = max(1, len(phi_arr) // 12)
    step_j = max(1, len(theta_arr) // 12)
    for i in range(0, len(phi_arr), step_i):
        for j in range(0, len(theta_arr), step_j):
            phi = float(phi_arr[i])
            theta = float(theta_arr[j])
            v = np.array(
                [np.sin(phi) * np.cos(theta), np.sin(phi) * np.sin(theta), np.cos(phi)],
                dtype=float,
            )
            e_offline = direction_E(S, v)
            e_platform = float(values[i, j])
            rel = abs(e_offline - e_platform) / max(abs(e_offline), 1e-6) * 100.0
            rels.append(rel)
            samples.append(
                {
                    'offline_GPa': round(e_offline, 4),
                    'platform_GPa': round(e_platform, 4),
                    'rel_pct': round(rel, 4),
                    'kind': 'grid',
                }
            )

    # 2) 固定高对称方向（允许 ≤2% 网格插值误差）
    fixed_dirs = [
        _unit(1, 0, 0),
        _unit(0, 1, 0),
        _unit(0, 0, 1),
        _unit(1, 1, 0),
        _unit(1, 1, 1),
    ]
    for v in fixed_dirs:
        e_offline = direction_E(S, v)
        e_platform = _E_from_bundle_grid(bundle, v)
        rel = abs(e_offline - e_platform) / max(abs(e_offline), 1e-6) * 100.0
        rels.append(rel)
        samples.append(
            {
                'offline_GPa': round(e_offline, 4),
                'platform_GPa': round(e_platform, 4),
                'rel_pct': round(rel, 3),
                'kind': 'symmetry',
            }
        )

    grid_rels = [s['rel_pct'] for s in samples if s.get('kind') == 'grid']
    sym_rels = [s['rel_pct'] for s in samples if s.get('kind') == 'symmetry']
    max_grid = float(np.max(grid_rels)) if grid_rels else 0.0
    max_sym = float(np.max(sym_rels)) if sym_rels else 0.0
    max_rel = float(np.max(rels)) if rels else 0.0
    mean_rel = float(np.mean(rels)) if rels else 0.0
    passed = max_grid < 0.05 and max_sym < 2.0
    return {
        'success': True,
        'symbol': symbol,
        'crystal_system': preset.get('crystal_system'),
        'platform_model': bundle.get('model'),
        'E_anisotropy_ratio': bundle['E'].get('anisotropy_ratio'),
        'E_range_GPa': [bundle['E'].get('min'), bundle['E'].get('max')],
        'grid_node_max_rel_pct': round(max_grid, 4),
        'symmetry_max_rel_pct': round(max_sym, 3),
        'offline_sample_max_rel_pct': round(max_rel, 3),
        'offline_sample_mean_rel_pct': round(mean_rel, 3),
        'n_directions': len(rels),
        'worst_samples': sorted(samples, key=lambda s: s['rel_pct'], reverse=True)[:3],
        'passed': passed,
        'message': (
            f'{symbol} Fedorov 交叉校验：网格节点最大偏差 {max_grid:.4f}%，'
            f'高对称方向最大偏差 {max_sym:.3f}%，'
            f'{"通过" if passed else "未通过"}'
        ),
    }
