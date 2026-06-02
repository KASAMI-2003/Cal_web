"""论文 VASP 金属参考数据（Cu、Al 等），供数字孪生与 Fedorov 校验。"""

from __future__ import annotations

METAL_PRESETS: dict[str, dict] = {
    'Cu': {
        'structure': 'fcc',
        'crystal_system': 'cubic',
        'c11': 175.96,
        'c12': 124.75,
        'c44': 78.36,
        'rho': 8.96,
        'source': 'thesis_energy_strain',
        'method': 'energy_strain',
    },
    'Al': {
        'structure': 'fcc',
        'crystal_system': 'cubic',
        'c11': 100.9,
        'c12': 66.3,
        'c44': 32.24,
        'rho': 2.70,
        'source': 'thesis_energy_strain',
        'method': 'energy_strain',
    },
    'Ni': {
        'structure': 'fcc',
        'crystal_system': 'cubic',
        'c11': 255.84,
        'c12': 177.22,
        'c44': 113.84,
        'rho': 8.90,
        'source': 'thesis_energy_strain',
    },
    'Ti': {
        'structure': 'hcp',
        'crystal_system': 'hexagonal',
        'c11': 181.86,
        'c12': 86.39,
        'c13': 31.7,
        'c33': 105.3,
        'c44': 29.99,
        'rho': 4.51,
        'source': 'thesis_energy_strain',
    },
}


def get_metal_preset(symbol: str) -> dict | None:
    return METAL_PRESETS.get((symbol or '').strip().capitalize())


def alloy_row_from_preset(symbol: str) -> dict | None:
    p = get_metal_preset(symbol)
    if not p:
        return None
    return {
        'label': symbol,
        'c11': p['c11'],
        'c12': p['c12'],
        'c44': p['c44'],
        'c13': p.get('c13'),
        'c33': p.get('c33'),
        'rho': p['rho'],
        'crystal_system': p.get('crystal_system', 'cubic'),
    }
