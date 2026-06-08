"""扩展物性：能带 / DOS / 声子输出探测与轻量解析（VASP / phonopy 产物）。"""

from __future__ import annotations

import os
import re
from typing import Any

from vasp_import.metadata_extract import _read_text, extract_from_outcar

MODULES = ('band_structure', 'dos', 'phonon')


def _file_info(path: str) -> dict[str, Any] | None:
    if not os.path.isfile(path):
        return None
    st = os.stat(path)
    return {'path': path, 'size_bytes': st.st_size}


def _parse_band_gap_from_outcar(outcar_path: str) -> float | None:
    if not os.path.isfile(outcar_path):
        return None
    text = _read_text(outcar_path, 400_000)
    m = re.search(r'band\s+gap\s+E_g\s*=\s*([\d.]+)', text, re.I)
    if m:
        return float(m.group(1))
    return None


def _scan_band_structure(work_dir: str) -> dict[str, Any]:
    files = {
        'EIGENVAL': _file_info(os.path.join(work_dir, 'EIGENVAL')),
        'vasprun.xml': _file_info(os.path.join(work_dir, 'vasprun.xml')),
        'PROCAR': _file_info(os.path.join(work_dir, 'PROCAR')),
        'KPOINTS': _file_info(os.path.join(work_dir, 'KPOINTS')),
    }
    present = {k: v for k, v in files.items() if v}
    outcar = os.path.join(work_dir, 'OUTCAR')
    meta = extract_from_outcar(outcar) if os.path.isfile(outcar) else {}
    band_gap = _parse_band_gap_from_outcar(outcar)
    available = bool(present.get('EIGENVAL') or present.get('vasprun.xml'))
    return {
        'available': available,
        'status': 'ready' if available else 'missing',
        'files': present,
        'summary': {
            'band_gap_eV': band_gap,
            'k_points_nkpts': meta.get('k_points_nkpts'),
            'hint': '完整能带图可对接 pymatgen/Plotly；当前返回文件探测与带隙摘要',
        },
    }


def _parse_doscar(work_dir: str, max_points: int = 400) -> dict[str, Any]:
    path = os.path.join(work_dir, 'DOSCAR')
    info = _file_info(path)
    if not info:
        return {'available': False, 'status': 'missing', 'files': {}}
    lines = _read_text(path, 2_000_000).splitlines()
    if len(lines) < 7:
        return {'available': False, 'status': 'invalid', 'files': {'DOSCAR': info}, 'message': 'DOSCAR 行数不足'}
    header = lines[5].split()
    efermi = float(header[0]) if header else None
    nedos = int(float(header[2])) if len(header) > 2 else max(0, len(lines) - 6)
    energies: list[float] = []
    dos_vals: list[float] = []
    for line in lines[6 : 6 + nedos]:
        parts = line.split()
        if len(parts) < 2:
            continue
        try:
            energies.append(float(parts[0]))
            dos_vals.append(float(parts[1]))
        except ValueError:
            continue
    step = max(1, len(energies) // max_points)
    return {
        'available': True,
        'status': 'ready',
        'files': {'DOSCAR': info},
        'summary': {
            'efermi_eV': efermi,
            'nedos': len(energies),
        },
        'curve': {
            'energy_eV': energies[::step],
            'dos': dos_vals[::step],
        },
    }


def _scan_phonon(work_dir: str) -> dict[str, Any]:
    candidates = (
        'band.yaml',
        'band.conf',
        'total_dos.dat',
        'phonon_band.yaml',
        'FORCE_CONSTANTS',
        'FORCE_SETS',
        'mesh.yaml',
    )
    present: dict[str, Any] = {}
    for name in candidates:
        fi = _file_info(os.path.join(work_dir, name))
        if fi:
            present[name] = fi
    for root, _, fnames in os.walk(work_dir):
        if len(present) >= 4:
            break
        depth = root[len(work_dir) :].count(os.sep)
        if depth > 2:
            continue
        for fn in fnames:
            if fn in ('band.yaml', 'total_dos.dat') and fn not in present:
                present[fn] = _file_info(os.path.join(root, fn))
    available = len(present) > 0
    freq_hint = None
    band_yaml = os.path.join(work_dir, 'band.yaml')
    if os.path.isfile(band_yaml):
        text = _read_text(band_yaml, 200_000)
        nums = re.findall(r'[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?', text)
        floats = [float(x) for x in nums[:20] if abs(float(x)) < 5000]
        if floats:
            freq_hint = {'sample_values': floats[:8]}
    return {
        'available': available,
        'status': 'ready' if available else 'missing',
        'files': present,
        'summary': {
            'phonon_engine': 'phonopy' if 'band.yaml' in present or 'FORCE_SETS' in present else 'unknown',
            'freq_hint': freq_hint,
            'hint': '声子色散/full DOS 可接 phonopy CLI；当前为产物探测与摘要',
        },
    }


def scan_extended_properties(work_dir: str | None, module: str | None = None) -> dict[str, Any]:
    if not work_dir or not os.path.isdir(work_dir):
        return {
            'status': 'error',
            'message': 'work_dir 无效或目录不存在（路径相对于 pyserver 所在机器）',
            'modules': {},
        }
    mod = (module or 'all').strip().lower()
    out: dict[str, Any] = {
        'status': 'ok',
        'work_dir': work_dir,
        'modules': {},
        'registered': list(MODULES),
    }
    if mod in ('all', 'band_structure', 'band', 'bands'):
        out['modules']['band_structure'] = _scan_band_structure(work_dir)
    if mod in ('all', 'dos'):
        out['modules']['dos'] = _parse_doscar(work_dir)
    if mod in ('all', 'phonon', 'phonon_dos'):
        out['modules']['phonon'] = _scan_phonon(work_dir)
    if mod not in ('all', 'band_structure', 'band', 'bands', 'dos', 'phonon', 'phonon_dos'):
        out['status'] = 'error'
        out['message'] = f'未知 module: {module}，可选 band_structure / dos / phonon / all'
    return out
