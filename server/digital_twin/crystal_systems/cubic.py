"""立方晶系（fcc / bcc / 立方对称，HTEM LC='C'）。"""

from __future__ import annotations

import re

import numpy as np

from .base import CrystalSystemHandler, CrystalSystemSpec


class CubicHandler(CrystalSystemHandler):
    """
    立方晶系：3 个独立常数 c11, c12, c44。

    由 BH+GH 反推时：c44=G, c11=c12+2G, c12=B-2G/3（各向同性映射，E 曲面近球形）。
    fcc 与 bcc 弹性对称性相同，差异仅体现在 structure 标签。
    """
    spec = CrystalSystemSpec(
        id='cubic',
        htem_lc='C',
        display_zh='立方',
        display_en='Cubic',
        moduli_inverse_supported=True,
    )

    _PHASE_RE = re.compile(
        r'\b(fcc|bcc|cubic|面心|体心|立方)\b',
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
            raise ValueError('立方晶系需要 BH+GH 或 EH+nu')

        # Hill 体模量 B 与剪切模量 G → 立方 Voigt 独立分量（HTEM 各向同性极限）
        c12 = B - 2.0 * G / 3.0
        c11 = c12 + 2.0 * G
        c44 = G
        return {'c11': c11, 'c12': c12, 'c44': c44}

    def phase_match_score(self, phases: str | None) -> float:
        if not phases:
            return 0.35
        if self._PHASE_RE.search(phases):
            return 1.0
        p = phases.lower()
        if 'hcp' in p or 'hex' in p or '六方' in p:
            return 0.0
        if '+' in p or 'mix' in p or '双相' in p:
            return 0.85
        return 0.2
