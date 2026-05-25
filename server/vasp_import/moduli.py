"""由单晶 Cij 计算 Voigt–Reuss–Hill 多晶模量（GPa）。"""

from __future__ import annotations

from typing import Any


def compute_moduli(crystal_system: str, cij: dict[str, float]) -> dict[str, float | None]:
    system = (crystal_system or 'cubic').lower()
    if system in ('fcc', 'bcc'):
        system = 'cubic'
    if system in ('hcp', 'hex'):
        system = 'hexagonal'

    c11 = float(cij['C11'])
    c12 = float(cij['C12'])
    c44 = float(cij.get('C44') or 0)

    if system == 'cubic':
        bv = (c11 + 2 * c12) / 3.0
        gv = (c11 - c12 + 3 * c44) / 5.0
        denom_gr = 4 * c44 + 3 * (c11 - c12)
        gr = (5 * (c11 - c12) * c44 / denom_gr) if denom_gr else None
    else:
        c13 = float(cij['C13'])
        c33 = float(cij['C33'])
        bv = (2 * (c11 + c12) + c33 + 2 * c13) / 9.0
        # 六方 Voigt/Reuss 剪切近似（与平台论文公式一致时可再细化）
        gv = (c11 - c12 + 3 * c44) / 5.0
        gr = gv

    if gr is None:
        return {'B': bv, 'G_voigt': gv, 'G_reuss': None, 'G_hill': None, 'E': None, 'nu': None}

    gh = (gv + gr) / 2.0
    denom_e = 3 * bv + gh
    e = 9 * bv * gh / denom_e if denom_e else None
    denom_nu = 2 * (3 * bv + gh)
    nu = (3 * bv - 2 * gh) / denom_nu if denom_nu else None
    return {
        'B': round(bv, 4),
        'G_voigt': round(gv, 4),
        'G_reuss': round(gr, 4),
        'G_hill': round(gh, 4),
        'E': round(e, 4) if e is not None else None,
        'nu': round(nu, 4) if nu is not None else None,
    }


def moduli_to_db_fields(moduli: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    if moduli.get('B') is not None:
        out['体模量B'] = str(moduli['B'])
    if moduli.get('G_hill') is not None:
        out['剪切模量G-H'] = str(moduli['G_hill'])
    if moduli.get('E') is not None:
        out['杨氏模量E-H'] = str(moduli['E'])
    if moduli.get('nu') is not None:
        out['泊松比v-H'] = str(moduli['nu'])
    return out
