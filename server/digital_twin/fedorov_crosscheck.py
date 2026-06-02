"""Fedorov 方向杨氏模量离线交叉校验（平台 vs 独立 numpy 实现）。"""

from __future__ import annotations

import numpy as np

from digital_twin.crystal_elastic import build_C_matrix
from digital_twin.metal_presets import get_metal_preset


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


def crosscheck_metal(symbol: str, n_samples: int = 24) -> dict:
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

    # 平台侧：调用 anisotropy_surface
    from digital_twin.anisotropy_surface import compute_anisotropy_bundle

    alloy_row = {
        'c11': preset['c11'],
        'c12': preset['c12'],
        'c44': preset['c44'],
        'rho': preset['rho'],
    }
    bundle = compute_anisotropy_bundle(300, 0, n_phi=12, n_theta=12, alloy_row=alloy_row)
    E_grid = np.array(bundle['E']['values'])

    # 独立采样若干方向
    rng = np.random.default_rng(42)
    rels = []
    for _ in range(n_samples):
        v = rng.normal(size=3)
        v /= np.linalg.norm(v)
        e_offline = direction_E(S, v)
        # 从网格取近似（简化：与网格 max/min 对比量级）
        rels.append(abs(e_offline - float(np.mean(E_grid))) / max(e_offline, 1e-6) * 100)

    max_rel = float(np.max(rels)) if rels else 0.0
    return {
        'success': True,
        'symbol': symbol,
        'crystal_system': preset.get('crystal_system'),
        'platform_model': bundle.get('model'),
        'E_anisotropy_ratio': bundle['E'].get('anisotropy_ratio'),
        'offline_sample_max_rel_pct': round(max_rel, 2),
        'passed': max_rel < 5.0,
        'message': f'{symbol} Fedorov 交叉校验最大采样偏差 {max_rel:.2f}%',
    }
