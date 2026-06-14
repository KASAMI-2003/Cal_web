"""多晶有效介质 / 仅 Hill 模量（各向同性近似，HTEM 仍用 LC='C' 立方对称矩阵）。"""

from __future__ import annotations

import re

import numpy as np

from .base import CrystalSystemHandler, CrystalSystemSpec
from .cubic_moduli import isotropic_cij_from_bg


class IsotropicHandler(CrystalSystemHandler):
    """
    多晶有效 / 各向同性：仅 BH+GH（或 EH+nu）反推 c_ij，不使用 BV/BR/GV/GR 单晶拟合。

    适用于未标明具体晶系的 Hill 多晶有效模量表（非 alpha_pp 等已知单斜相）。
    曲面为球（Zener A=1）；侧栏 B/G/E 仍取自 Hill 列。
    """

    spec = CrystalSystemSpec(
        id='isotropic',
        htem_lc='C',
        display_zh='多晶有效（各向同性）',
        display_en='Polycrystal effective (isotropic)',
        moduli_inverse_supported=True,
    )

    _POLY_RE = re.compile(
        r'\b(amorphous|glass|poly|polycryst|effective|precip|multiphase|mix|'
        r'多晶|非晶|有效|混合|析出)\b',
        re.IGNORECASE,
    )

    def independent_cij_keys(self) -> tuple[str, ...]:
        return ('c11', 'c12', 'c44')

    def build_C_matrix(self, cij: dict[str, float]) -> np.ndarray:
        c11 = float(cij['c11'])
        c12 = float(cij['c12'])
        c44 = float(cij['c44'])
        C = np.zeros((6, 6))
        C[0, 0] = c11
        C[0, 1] = c12
        C[3, 3] = c44
        C[1, 1] = C[0, 0]
        C[2, 2] = C[0, 0]
        C[0, 2] = C[0, 1]
        C[1, 2] = C[0, 1]
        C[4, 4] = C[3, 3]
        C[5, 5] = C[3, 3]
        for i in range(6):
            for j in range(i):
                C[i, j] = C[j, i]
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
            raise ValueError('多晶有效模量表需 BH+GH 或 EH+nu_H')
        out = isotropic_cij_from_bg(B, G)
        out['cij_method'] = 'polycrystal_bh_gh'
        return out

    def phase_match_score(self, phases: str | None) -> float:
        if not phases:
            return 0.55
        if self._POLY_RE.search(phases):
            return 0.95
        p = phases.lower()
        if re.search(r'\b(fcc|bcc|hcp|hex|cubic|立方|六方)\b', p):
            return 0.0
        return 0.7
