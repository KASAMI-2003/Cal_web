"""六方晶系（hcp / hexagonal，HTEM LC='H'）。"""

from __future__ import annotations

import re

import numpy as np

from .base import CrystalSystemHandler, CrystalSystemSpec

# 无 c33 实测时，c33/c11 默认比（典型 hcp 金属 ~1.0–1.1）
_DEFAULT_C33_OVER_C11 = 1.05


class HexagonalHandler(CrystalSystemHandler):
    """
    六方晶系：5 个独立常数 c11, c12, c13, c33, c44。

    仅 BH/GH 时采用近似：c44=G, c13=c12, c33=eta*c11（eta 默认 1.05）。
    有完整 c_ij 时直接使用表值，各向异性更准确。
    """
    spec = CrystalSystemSpec(
        id='hexagonal',
        htem_lc='H',
        display_zh='六方',
        display_en='Hexagonal',
        moduli_inverse_supported=True,
    )

    _PHASE_RE = re.compile(
        r'\b(hcp|hex|hexagonal|六方|密排)\b',
        re.IGNORECASE,
    )

    def independent_cij_keys(self) -> tuple[str, ...]:
        return ('c11', 'c12', 'c13', 'c33', 'c44')

    def build_C_matrix(self, cij: dict[str, float]) -> np.ndarray:
        c11 = float(cij['c11'])
        c12 = float(cij['c12'])
        c13 = float(cij['c13'])
        c33 = float(cij['c33'])
        c44 = float(cij['c44'])
        C = np.zeros((6, 6))
        C[0, 0] = C[1, 1] = c11
        C[0, 1] = C[1, 0] = c12
        C[0, 2] = C[1, 2] = C[2, 0] = C[2, 1] = c13
        C[2, 2] = c33
        C[3, 3] = C[4, 4] = c44
        C[5, 5] = (c11 - c12) / 2.0
        return C

    def cij_from_moduli(
        self,
        B: float | None,
        G: float | None,
        E: float | None = None,
        nu: float | None = None,
        *,
        c33_over_c11: float = _DEFAULT_C33_OVER_C11,
        **kwargs,
    ) -> dict[str, float]:
        """
        由 B、G 近似反推六方 c_ij（HTEM Hill 模量表常见输出）。
        假设 c13=c12、c44=G，c33/c11=eta（默认 1.05，可通过 kwargs 覆盖）。
        """
        if B is not None and G is not None:
            B, G = float(B), float(G)
        elif E is not None and nu is not None:
            E, nu = float(E), float(nu)
            G = E / (2.0 * (1.0 + nu))
            B = E / (3.0 * (1.0 - 2.0 * nu))
        else:
            raise ValueError('六方晶系需要 BH+GH 或 EH+nu')

        eta = float(c33_over_c11)
        c44 = G
        c12 = (9.0 * B - (4.0 + 2.0 * eta) * G) / (8.0 + eta)
        c11 = c12 + 2.0 * c44
        c13 = c12
        c33 = eta * c11
        return {'c11': c11, 'c12': c12, 'c13': c13, 'c33': c33, 'c44': c44}

    def phase_match_score(self, phases: str | None) -> float:
        if not phases:
            return 0.0
        return 1.0 if self._PHASE_RE.search(phases) else 0.0
