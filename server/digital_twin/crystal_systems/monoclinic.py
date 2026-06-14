"""单斜晶系（HTEM LC='M'，Space group 3–15）。"""

from __future__ import annotations

import re

import numpy as np

from .base import CrystalSystemHandler, CrystalSystemSpec

# HTEM write_output filehead 顺序
_MONOCLINIC_CIJ_KEYS: tuple[str, ...] = (
    'c11', 'c12', 'c13', 'c16', 'c22', 'c23', 'c26',
    'c33', 'c36', 'c44', 'c45', 'c55', 'c66',
)


def _shear_avr_index(**kwargs) -> float:
    """优先表列 AVR，否则由 GV/GR 或 GV/GR 列估算。"""
    for key in ('avr', 'AVR'):
        v = kwargs.get(key)
        if v is not None:
            return min(max(abs(float(v)), 0.005), 0.45)
    gv = kwargs.get('gv') if kwargs.get('gv') is not None else kwargs.get('GV')
    gr = kwargs.get('gr') if kwargs.get('gr') is not None else kwargs.get('GR')
    if gv is not None and gr is not None:
        gv, gr = float(gv), float(gr)
        denom = max(gv + gr, 1e-12)
        return min(max(abs(gv - gr) / denom, 0.005), 0.45)
    bv = kwargs.get('bv') if kwargs.get('bv') is not None else kwargs.get('BV')
    br = kwargs.get('br') if kwargs.get('br') is not None else kwargs.get('BR')
    if bv is not None and br is not None:
        bv, br = float(bv), float(br)
        denom = max(bv + br, 1e-12)
        return min(max(abs(bv - br) / denom, 0.005), 0.45)
    return 0.06


class MonoclinicHandler(CrystalSystemHandler):
    """
    单斜晶系：13 个独立常数（HTEM M 对称）。

    仅 BH/GH 时：以 Hill 模量为基准，用 AVR（或 GV/GR、BV/BR）注入单斜耦合项；
    完整 c_ij 列存在时直接使用表值。
    """

    spec = CrystalSystemSpec(
        id='monoclinic',
        htem_lc='M',
        display_zh='单斜',
        display_en='Monoclinic',
        moduli_inverse_supported=True,
    )

    _PHASE_RE = re.compile(
        r'\b(monoclinic|mono|单斜)\b',
        re.IGNORECASE,
    )
    _KNOWN_PHASES = frozenset({'alpha_pp', 'alpha-pp', 'alphapp'})

    def independent_cij_keys(self) -> tuple[str, ...]:
        return _MONOCLINIC_CIJ_KEYS

    def build_C_matrix(self, cij: dict[str, float]) -> np.ndarray:
        c11 = float(cij['c11'])
        c12 = float(cij['c12'])
        c13 = float(cij['c13'])
        c16 = float(cij['c16'])
        c22 = float(cij['c22'])
        c23 = float(cij['c23'])
        c26 = float(cij['c26'])
        c33 = float(cij['c33'])
        c36 = float(cij['c36'])
        c44 = float(cij['c44'])
        c45 = float(cij['c45'])
        c55 = float(cij['c55'])
        c66 = float(cij['c66'])
        C = np.zeros((6, 6))
        C[0, 0] = c11
        C[0, 1] = c12
        C[0, 2] = c13
        C[0, 5] = c16
        C[1, 1] = c22
        C[1, 2] = c23
        C[1, 5] = c26
        C[2, 2] = c33
        C[2, 5] = c36
        C[3, 3] = c44
        C[3, 4] = c45
        C[4, 4] = c55
        C[5, 5] = c66
        for i in range(5):
            for j in range(i + 1, 6):
                C[j, i] = C[i, j]
        return C

    def cij_from_moduli(
        self,
        B: float | None,
        G: float | None,
        E: float | None = None,
        nu: float | None = None,
        **kwargs,
    ) -> dict[str, float]:
        if B is not None and G is not None:
            B, G = float(B), float(G)
        elif E is not None and nu is not None:
            E, nu = float(E), float(nu)
            G = E / (2.0 * (1.0 + nu))
            B = E / (3.0 * (1.0 - 2.0 * nu))
        else:
            raise ValueError('单斜晶系 moduli 表需 BH+GH 或 EH+nu_H')

        avr = _shear_avr_index(**kwargs)
        c12 = B - 2.0 * G / 3.0
        c11_0 = c12 + 2.0 * G

        c11 = c11_0 * (1.0 + avr)
        c22 = c11_0
        c33 = c11_0 * max(1.0 - 0.55 * avr, 0.55)
        c13 = c12
        c23 = c12
        c44 = G
        c55 = G * (1.0 + 0.45 * avr)
        c66 = G * max(1.0 - 0.45 * avr, 0.35)
        delta = max(c11 - c12, G * 0.1)
        c16 = delta * avr * 0.4
        c26 = delta * avr * 0.25
        c36 = delta * avr * 0.18
        c45 = G * avr * 0.3

        out = {
            'c11': c11,
            'c12': c12,
            'c13': c13,
            'c16': c16,
            'c22': c22,
            'c23': c23,
            'c26': c26,
            'c33': c33,
            'c36': c36,
            'c44': c44,
            'c45': c45,
            'c55': c55,
            'c66': c66,
            'cij_method': 'monoclinic_bg_avr_approx',
        }
        return out

    def phase_match_score(self, phases: str | None) -> float:
        if not phases:
            return 0.0
        p = phases.strip().lower().replace(' ', '_').replace('-', '_')
        if p in self._KNOWN_PHASES or 'alpha_pp' in p:
            return 1.0
        if self._PHASE_RE.search(phases):
            return 0.98
        return 0.0
