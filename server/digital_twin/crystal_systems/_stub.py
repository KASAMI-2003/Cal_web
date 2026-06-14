"""
未实现 B/G 反推的晶系占位（四方/正交/三方/单斜/三斜）。

这些 handler 仅在有完整 c_ij 表时可 build_C_matrix（优先走 HTEM format_Cij）。
后续实现 moduli 反推时：继承 CrystalSystemHandler 并替换 _stub_handler 即可。
"""

from __future__ import annotations

from .base import CrystalSystemHandler, CrystalSystemSpec
from .htem_bridge import build_C_matrix_htem


def _stub_handler(
    system_id: str,
    htem_lc: str,
    display_zh: str,
    display_en: str,
    cij_keys: tuple[str, ...],
) -> CrystalSystemHandler:
    class _Handler(CrystalSystemHandler):
        spec = CrystalSystemSpec(
            id=system_id,
            htem_lc=htem_lc,
            display_zh=display_zh,
            display_en=display_en,
            moduli_inverse_supported=False,
        )

        def independent_cij_keys(self) -> tuple[str, ...]:
            return cij_keys

        def build_C_matrix(self, cij: dict[str, float]) -> __import__('numpy').ndarray:
            return build_C_matrix_htem(htem_lc, cij)

    return _Handler


TetragonalHandler = _stub_handler('tetragonal', 'TI', '四方 I', 'Tetragonal I', ('c11', 'c12', 'c13', 'c33', 'c44', 'c66'))
OrthorhombicHandler = _stub_handler('orthorhombic', 'O', '正交', 'Orthorhombic', ('c11', 'c12', 'c13', 'c22', 'c23', 'c33', 'c44', 'c55', 'c66'))
TrigonalHandler = _stub_handler('trigonal', 'RI', '三方 I', 'Rhombohedral I', ('c11', 'c12', 'c13', 'c14', 'c33', 'c44'))
MonoclinicHandler = _stub_handler('monoclinic', 'M', '单斜', 'Monoclinic', ())
TriclinicHandler = _stub_handler('triclinic', 'N', '三斜', 'Triclinic', ())
