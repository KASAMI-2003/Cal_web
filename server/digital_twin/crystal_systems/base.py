"""
晶系抽象：与 HTEM elasticity.format_Cij 的 LC 码一一对应。

每个晶系实现为 CrystalSystemHandler 子类，负责：
  - build_C_matrix：独立 c_ij → 6×6 Voigt 刚度矩阵
  - cij_from_moduli（可选）：BH/GH 或 EH/nu → 反推独立 c_ij
  - phase_match_score：从 phases 列文本推断晶系时的匹配分数
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class CrystalSystemSpec:
    """单个晶系的元数据（HTEM 字母码 + 平台 id）。"""

    id: str
    htem_lc: str
    display_zh: str
    display_en: str
    moduli_inverse_supported: bool = False


class CrystalSystemHandler(ABC):
    """各晶系实现：刚度矩阵构造、模量反推 c_ij（若支持）。"""

    spec: CrystalSystemSpec

    @abstractmethod
    def build_C_matrix(self, cij: dict[str, float]) -> np.ndarray:
        """由独立弹性常数构造 6×6 Voigt 刚度矩阵。"""

    def cij_from_moduli(
        self,
        B: float | None,
        G: float | None,
        E: float | None = None,
        nu: float | None = None,
        **kwargs: Any,
    ) -> dict[str, float]:
        """由 Hill/Voigt 体模量、剪切模量（或 E、ν）反推独立 c_ij。"""
        raise NotImplementedError(
            f"{self.spec.id} 暂不支持由 B/G 反推 c_ij，请在表中提供完整弹性常数。"
        )

    def phase_match_score(self, phases: str | None) -> float:
        """phases 文本与该晶系的匹配度 0~1；0 表示不匹配。"""
        return 0.0

    def independent_cij_keys(self) -> tuple[str, ...]:
        return tuple()
