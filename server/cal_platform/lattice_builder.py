"""ASE 驱动的晶体结构网格：bulk 原胞或 POSCAR 解析 → Three.js 点/键。"""

from __future__ import annotations

import re
from io import StringIO
from typing import Any

import numpy as np
from ase.build import bulk
from ase.io import read
from ase.neighborlist import NeighborList, natural_cutoffs

DEFAULT_LATTICE_A = {'fcc': 3.615, 'bcc': 2.866, 'hcp': 2.951, 'orthogonal': 3.5}
DEFAULT_ELEMENT = {'fcc': 'Cu', 'bcc': 'Fe', 'hcp': 'Ti', 'orthogonal': 'Cu'}
DEFAULT_HCP_COVERA = 1.588
MAX_VIS_ATOMS = 128

_BCC_SPACE_GROUPS = frozenset({211, 229})  # Ia-3d, Im-3m
_FCC_SPACE_GROUPS = frozenset({225, 227})  # Fm-3m, Fd-3m
_HEX_SPACE_GROUP_RANGE = range(168, 195)


def _combine_structure_hints(
    raw: str | None,
    *,
    space_group_no: int | None = None,
    notes: str | None = None,
    material_name: str | None = None,
) -> str:
    parts = [raw, notes, material_name]
    if space_group_no is not None:
        parts.append(f'spacegroup={space_group_no}')
    return ' '.join(str(p) for p in parts if p).lower()


def resolve_bulk_structure(
    raw: str | None,
    *,
    space_group_no: int | None = None,
    notes: str | None = None,
    material_name: str | None = None,
) -> str:
    """
    推断 ASE bulk 可构建的晶格类型：fcc / bcc / hcp / orthogonal。
    本地库常见 cubic + Im-3m(229) 须识别为 bcc，避免一律落成 fcc 四面体。
    """
    hints = _combine_structure_hints(
        raw,
        space_group_no=space_group_no,
        notes=notes,
        material_name=material_name,
    )

    # 空间群优先于字面量 fcc/bcc（前端 infer 有误时仍可纠正）
    if space_group_no is not None:
        try:
            sg = int(space_group_no)
            if sg in _BCC_SPACE_GROUPS:
                return 'bcc'
            if sg in _FCC_SPACE_GROUPS:
                return 'fcc'
            if sg in _HEX_SPACE_GROUP_RANGE:
                return 'hcp'
        except (TypeError, ValueError):
            pass

    if re.search(r'\bbcc\b|体心|body[- ]?centered|im[- ]?3m|ia[- ]?3m', hints):
        return 'bcc'
    if re.search(r'\bhcp\b|hexagonal|六方|wurtzite|p6[_/ ]?6|p63', hints):
        return 'hcp'
    if re.search(r'\bfcc\b|面心|face[- ]?centered|fm[- ]?3m|fd[- ]?3m|c1=f', hints):
        return 'fcc'

    if any(token in hints for token in ('hexagonal', '六方', 'trigonal', '三角', 'hcp')):
        return 'hcp'
    if any(
        token in hints
        for token in (
            'orthorhombic',
            'tetragonal',
            'monoclinic',
            'triclinic',
            '斜方',
            '四方',
            '单斜',
            'cmcm',
            'pnma',
        )
    ):
        return 'orthogonal'

    if 'cubic' in hints or '立方' in hints:
        return 'fcc'

    s = (raw or 'fcc').strip().lower()
    if s in ('bcc', 'hcp', 'fcc', 'orthogonal'):
        return s
    return 'fcc'


def _normalize_structure(raw: str | None) -> str:
    return resolve_bulk_structure(raw)


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


def _build_orthogonal_atoms(
    element: str,
    lattice_a: float,
    lattice_b: float | None,
    lattice_c: float | None,
) -> Any:
    from ase import Atoms

    a = lattice_a
    b = lattice_b if lattice_b and lattice_b > 0 else a
    c = lattice_c if lattice_c and lattice_c > 0 else b
    atoms = Atoms(element, positions=[(0.0, 0.0, 0.0)], cell=[a, b, c], pbc=True)
    return atoms.repeat((2, 2, 2))


def _build_bulk_atoms(
    structure: str,
    element: str,
    lattice_a: float,
    lattice_b: float | None,
    lattice_c: float | None,
) -> Any:
    if structure == 'orthogonal':
        return _build_orthogonal_atoms(element, lattice_a, lattice_b, lattice_c)
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
    space_group_no: int | None = None,
    notes: str | None = None,
    material_name: str | None = None,
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

    st = resolve_bulk_structure(
        structure,
        space_group_no=space_group_no,
        notes=notes,
        material_name=material_name,
    )
    el = _parse_element(element, st if st != 'orthogonal' else 'fcc')
    a = _float_or(lattice_a, DEFAULT_LATTICE_A.get(st, 3.615))
    b = lattice_b if lattice_b is not None else None
    c = lattice_c if lattice_c is not None else None

    atoms = _build_bulk_atoms(st, el, a, b, c)
    if supercell and len(supercell) == 3:
        rep = tuple(max(1, int(x)) for x in supercell)
        atoms = atoms.repeat(rep)

    return _mesh_from_atoms(atoms, 'ase_bulk', st, el)
