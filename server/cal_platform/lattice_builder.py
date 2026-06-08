"""ASE 驱动的晶体结构网格：bulk 原胞或 POSCAR 解析 → Three.js 点/键。"""

from __future__ import annotations

import re
from io import StringIO
from typing import Any

import numpy as np
from ase.build import bulk
from ase.io import read
from ase.neighborlist import NeighborList, natural_cutoffs

DEFAULT_LATTICE_A = {'fcc': 3.615, 'bcc': 2.866, 'hcp': 2.951}
DEFAULT_ELEMENT = {'fcc': 'Cu', 'bcc': 'Fe', 'hcp': 'Ti'}
DEFAULT_HCP_COVERA = 1.588
MAX_VIS_ATOMS = 128


def _normalize_structure(raw: str | None) -> str:
    s = (raw or 'fcc').strip().lower()
    if 'bcc' in s or '体心' in s:
        return 'bcc'
    if 'hcp' in s or 'hex' in s or '六方' in s:
        return 'hcp'
    if 'fcc' in s or '面心' in s:
        return 'fcc'
    return 'fcc'


def _parse_element(raw: str | None, structure: str) -> str:
    fallback = DEFAULT_ELEMENT.get(structure, 'Cu')
    if not raw:
        return fallback
    sym = raw.strip()
    if sym:
        sym = sym[0].upper() + sym[1:] if len(sym) > 1 else sym.upper()
    if re.fullmatch(r'[A-Z][a-z]?', sym):
        return sym
    return fallback


def _float_or(value: Any, default: float) -> float:
    try:
        v = float(value)
        return v if v > 0 else default
    except (TypeError, ValueError):
        return default


def _build_bulk_atoms(
    structure: str,
    element: str,
    lattice_a: float,
    lattice_b: float | None,
    lattice_c: float | None,
) -> Any:
    if structure == 'fcc':
        a = lattice_a
        return bulk(element, 'fcc', a=a, cubic=True)
    if structure == 'bcc':
        a = lattice_a
        return bulk(element, 'bcc', a=a, cubic=True)
    a = lattice_a
    c = lattice_c if lattice_c and lattice_c > 0 else None
    if c:
        return bulk(element, 'hcp', a=a, c=c)
    if lattice_b and lattice_b > 0 and abs(lattice_b - a) > 1e-6:
        covera = lattice_b / a if lattice_b > a else DEFAULT_HCP_COVERA
    else:
        covera = DEFAULT_HCP_COVERA
    return bulk(element, 'hcp', a=a, covera=covera)


def _sanitize_poscar_text(text: str) -> str:
    """去掉教学用注释、分隔线，保留 ASE 可读的 POSCAR 正文。"""
    lines: list[str] = []
    for raw in text.splitlines():
        line = raw.split('#', 1)[0].strip()
        if not line:
            continue
        compact = line.replace(' ', '')
        if compact and set(compact) <= set('-—=_·'):
            continue
        lines.append(line)
    body = '\n'.join(lines).strip()
    if not body:
        raise ValueError('POSCAR 内容为空（去除注释后无有效行）')
    return body


def _atoms_from_poscar(text: str) -> Any:
    body = _sanitize_poscar_text(text)
    try:
        atoms = read(StringIO(body), format='vasp')
    except Exception as exc:
        raise ValueError(f'POSCAR 格式无法解析: {exc}') from exc
    if len(atoms) == 0:
        raise ValueError('POSCAR 未解析到原子')
    return atoms


def _mesh_from_atoms(atoms: Any, source: str, structure: str, element: str | None = None) -> dict[str, Any]:
    n = len(atoms)
    if n > MAX_VIS_ATOMS:
        raise ValueError(
            f'原子数 {n} 超过可视化上限 {MAX_VIS_ATOMS}，请上传更小原胞或使用结构类型生成'
        )

    cutoffs = natural_cutoffs(atoms)
    nl = NeighborList(cutoffs, skin=0.2, bothways=True, self_interaction=False)
    nl.update(atoms)

    positions = atoms.get_positions()
    symbols = atoms.get_chemical_symbols()
    connections: list[list[int]] = []
    seen: set[tuple[int, int]] = set()
    for i in range(n):
        neighbors, _ = nl.get_neighbors(i)
        for j in neighbors:
            ji = int(j)
            key = (min(i, ji), max(i, ji))
            if key not in seen:
                seen.add(key)
                connections.append([key[0], key[1]])

    lengths = atoms.cell.lengths()
    la = float(lengths[0]) if len(lengths) > 0 else float(np.max(positions) - np.min(positions))
    lb = float(lengths[1]) if len(lengths) > 1 else la
    lc = float(lengths[2]) if len(lengths) > 2 else la

    return {
        'points': [[float(v) for v in row] for row in positions.tolist()],
        'connections': connections,
        'elements': [str(s) for s in symbols],
        'lattice_a': round(la, 5),
        'lattice_b': round(lb, 5),
        'lattice_c': round(lc, 5),
        'n_atoms': int(n),
        'source': source,
        'structure': structure,
        'element': element or (symbols[0] if symbols else None),
    }


def create_lattice_picture(
    structure: str = 'fcc',
    lattice_a: float | None = None,
    lattice_b: float | None = None,
    lattice_c: float | None = None,
    element: str | None = None,
    poscar: str | None = None,
    supercell: list[int] | None = None,
) -> dict[str, Any]:
    """
    生成 Three.js 侧栏 3D 晶格数据。
    - 提供 poscar 时优先 ASE 读 POSCAR；
    - 否则按 fcc/bcc/hcp + 晶格常数 + 元素用 ase.build.bulk 构建原胞。
    """
    if poscar and str(poscar).strip():
        atoms = _atoms_from_poscar(str(poscar))
        if supercell and len(supercell) == 3:
            rep = tuple(max(1, int(x)) for x in supercell)
            atoms = atoms.repeat(rep)
        return _mesh_from_atoms(atoms, 'ase_poscar', 'poscar', element)

    st = _normalize_structure(structure)
    el = _parse_element(element, st)
    a = _float_or(lattice_a, DEFAULT_LATTICE_A.get(st, 3.615))
    b = lattice_b if lattice_b is not None else None
    c = lattice_c if lattice_c is not None else None

    atoms = _build_bulk_atoms(st, el, a, b, c)
    if supercell and len(supercell) == 3:
        rep = tuple(max(1, int(x)) for x in supercell)
        atoms = atoms.repeat(rep)

    return _mesh_from_atoms(atoms, 'ase_bulk', st, el)
