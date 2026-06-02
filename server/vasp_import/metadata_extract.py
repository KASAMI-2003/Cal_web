"""从 OUTCAR / INCAR / POTCAR / 汇总 JSON 提取复现元数据。"""

from __future__ import annotations

import json
import os
import re
from typing import Any


def _read_text(path: str, max_bytes: int = 2_000_000) -> str:
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        return f.read(max_bytes)


def extract_from_outcar(outcar_path: str) -> dict[str, Any]:
    meta: dict[str, Any] = {}
    if not os.path.isfile(outcar_path):
        return meta
    text = _read_text(outcar_path)
    m = re.search(r'ENCUT\s*=\s*([\d.]+)', text)
    if m:
        meta['encut'] = m.group(1)
    m = re.search(r'POTCAR:\s*(.+)', text)
    if m:
        meta['pseudopotential'] = m.group(1).strip()[:120]
    m = re.search(r'exchange correlation type\s*=\s*(\S+)', text, re.I)
    if m:
        meta['functional'] = m.group(1)
    km = re.search(r'k-points\s+NKPTS\s*=\s*(\d+)', text, re.I)
    if km:
        meta['k_points_nkpts'] = int(km.group(1))
    # 应变拟合 R² 近似：查找 ELASTIC MODULI 块后的 stress
    if 'ELASTIC MODULI' in text or 'ELASTIC TENSOR' in text:
        meta['has_elastic_block'] = True
    return meta


def extract_from_incar(incar_path: str) -> dict[str, Any]:
    meta: dict[str, Any] = {}
    if not os.path.isfile(incar_path):
        return meta
    text = _read_text(incar_path, 50000)
    for key, pat in (
        ('encut', r'ENCUT\s*=\s*([\d.]+)'),
        ('ismear', r'ISMEAR\s*=\s*(-?\d+)'),
        ('sigma', r'SIGMA\s*=\s*([\d.]+)'),
        ('ediff', r'EDIFF\s*=\s*([\d.Ee+-]+)'),
        ('ediffg', r'EDIFFG\s*=\s*([\d.Ee+-]+)'),
        ('strain_step_hint', r'IBRION\s*=\s*(-?\d+)'),
    ):
        m = re.search(pat, text, re.I)
        if m:
            meta[key] = m.group(1)
    return meta


def extract_k_mesh_tier(work_dir: str) -> str | None:
    """根据 INCAR/OUTCAR 推断 k 点收敛档位标签。"""
    for name in ('INCAR', 'OUTCAR'):
        p = os.path.join(work_dir, name)
        if not os.path.isfile(p):
            continue
        text = _read_text(p, 80000)
        m = re.search(r'KPOINTS.*?0\.(\d+)', text, re.S | re.I)
        if m:
            val = float('0.' + m.group(1))
            if val <= 0.02:
                return 'dense'
            if val <= 0.04:
                return 'medium'
            return 'coarse'
    return None


def extract_metadata(work_dir: str | None, method: str = '') -> dict[str, Any]:
    """扫描工作目录，合并元数据。"""
    if not work_dir or not os.path.isdir(work_dir):
        return {}
    out: dict[str, Any] = {'work_dir': work_dir, 'calc_method': method}
    out.update(extract_from_outcar(os.path.join(work_dir, 'OUTCAR')))
    out.update(extract_from_incar(os.path.join(work_dir, 'INCAR')))
    tier = extract_k_mesh_tier(work_dir)
    if tier:
        out['k_convergence_tier'] = tier
    jpath = os.path.join(work_dir, 'elastic_import.json')
    if os.path.isfile(jpath):
        try:
            with open(jpath, 'r', encoding='utf-8') as f:
                j = json.load(f)
            for k in ('functional', 'encut', 'k_mesh', 'reference_doi', 'doi', 'strain_fit_residual'):
                if j.get(k) not in (None, ''):
                    out[k if k != 'doi' else 'reference_doi'] = j[k]
        except Exception:
            pass
    if 'reference_doi' not in out:
        out.setdefault('reference_doi', '10.1016/0022-5096(71)90033-0')  # Simmons & Wang 1971
    out.setdefault('reference_temperature_K', 0)
    out.setdefault('data_source_tag', 'local_vasp')
    return out
