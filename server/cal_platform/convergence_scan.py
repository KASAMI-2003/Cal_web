"""ENCUT / k 点收敛扫描：扫描工作目录树下多组 VASP 算例并比较弹性常数。"""

from __future__ import annotations

import os
import re
from typing import Any

from vasp_import.metadata_extract import extract_from_incar, extract_from_outcar, extract_k_mesh_tier
from vasp_import.parser import parse_outcar_elastic_tensor

DEFAULT_THRESHOLD_GPA = 2.0


def _parse_encut_from_dirname(name: str) -> float | None:
    m = re.search(r'encut[_-]?(\d+(?:\.\d+)?)', name, re.I)
    if m:
        return float(m.group(1))
    m = re.search(r'^e(\d+(?:\.\d+)?)$', name, re.I)
    return float(m.group(1)) if m else None


def _parse_k_from_dirname(name: str) -> float | None:
    m = re.search(r'k[_-]?(\d+(?:\.\d+)?)', name, re.I)
    if m:
        val = float(m.group(1))
        return val if val < 1 else val / 100.0
    m = re.search(r'kpt[_-]?(\d+(?:\.\d+)?)', name, re.I)
    return float(m.group(1)) if m else None


def _collect_runs(root_dir: str) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []

    def add_run(run_dir: str, label: str):
        outcar = os.path.join(run_dir, 'OUTCAR')
        if not os.path.isfile(outcar):
            return
        incar = os.path.join(run_dir, 'INCAR')
        meta_out = extract_from_outcar(outcar)
        meta_in = extract_from_incar(incar) if os.path.isfile(incar) else {}
        encut = meta_in.get('encut') or meta_out.get('encut')
        if encut is not None:
            encut = float(encut)
        k_tier = extract_k_mesh_tier(run_dir)
        cij: dict[str, float] = {}
        err = None
        try:
            cij = parse_outcar_elastic_tensor(outcar)
        except Exception as exc:
            err = str(exc)
        runs.append(
            {
                'label': label,
                'dir': run_dir,
                'encut_eV': encut,
                'k_convergence_tier': k_tier,
                'encut_from_name': _parse_encut_from_dirname(label),
                'k_from_name': _parse_k_from_dirname(label),
                'cij_GPa': {k: round(v, 4) for k, v in cij.items()},
                'c11_GPa': round(cij['C11'], 4) if 'C11' in cij else None,
                'parse_error': err,
            }
        )

    add_run(root_dir, os.path.basename(root_dir.rstrip(os.sep)) or 'root')
    try:
        for name in sorted(os.listdir(root_dir)):
            sub = os.path.join(root_dir, name)
            if os.path.isdir(sub):
                add_run(sub, name)
    except OSError:
        pass
    return runs


def _series_key(run: dict[str, Any], sweep: str) -> float | None:
    if sweep == 'encut':
        if run.get('encut_eV') is not None:
            return float(run['encut_eV'])
        if run.get('encut_from_name') is not None:
            return float(run['encut_from_name'])
    if sweep == 'kpoints':
        if run.get('k_from_name') is not None:
            return float(run['k_from_name'])
    return None


def _detect_sweep(runs: list[dict[str, Any]]) -> str:
    encut_keys = {_series_key(r, 'encut') for r in runs if _series_key(r, 'encut') is not None}
    k_keys = {_series_key(r, 'kpoints') for r in runs if _series_key(r, 'kpoints') is not None}
    if len(encut_keys) >= 2:
        return 'encut'
    if len(k_keys) >= 2:
        return 'kpoints'
    if len(encut_keys) >= 1 and len(k_keys) >= 1:
        return 'mixed'
    return 'unknown'


def _analyze_series(runs: list[dict[str, Any]], sweep: str, threshold_gpa: float) -> dict[str, Any]:
    usable = [r for r in runs if r.get('c11_GPa') is not None]
    if len(usable) < 2:
        return {
            'converged': False,
            'message': '至少需要 2 组含 C11 的 OUTCAR 才能判断收敛',
            'series': [],
        }

    key_fn = lambda r: _series_key(r, sweep) if sweep in ('encut', 'kpoints') else r.get('encut_eV')
    sorted_runs = sorted(
        [r for r in usable if key_fn(r) is not None],
        key=lambda r: float(key_fn(r)),  # type: ignore[arg-type]
    )
    if len(sorted_runs) < 2:
        sorted_runs = sorted(usable, key=lambda r: r.get('label', ''))

    series: list[dict[str, Any]] = []
    prev_c11 = None
    for r in sorted_runs:
        c11 = float(r['c11_GPa'])
        delta = abs(c11 - prev_c11) if prev_c11 is not None else None
        series.append(
            {
                'label': r['label'],
                'encut_eV': r.get('encut_eV'),
                'k_tier': r.get('k_convergence_tier'),
                'c11_GPa': c11,
                'delta_c11_GPa': round(delta, 4) if delta is not None else None,
                'passed_step': delta is None or delta <= threshold_gpa,
            }
        )
        prev_c11 = c11

    last = series[-1]
    prev = series[-2]
    converged = (
        last.get('delta_c11_GPa') is not None
        and last['delta_c11_GPa'] <= threshold_gpa
    )
    recommended = {
        'encut_eV': last.get('encut_eV') or sorted_runs[-1].get('encut_eV'),
        'k_convergence_tier': last.get('k_tier') or sorted_runs[-1].get('k_convergence_tier'),
        'c11_GPa': last.get('c11_GPa'),
    }
    return {
        'converged': converged,
        'threshold_GPa': threshold_gpa,
        'last_delta_c11_GPa': last.get('delta_c11_GPa'),
        'series': series,
        'recommended': recommended,
        'message': (
            f'末两档 C11 变化 {last.get("delta_c11_GPa")} GPa '
            f'{"≤" if converged else ">"} 阈值 {threshold_gpa} GPa'
        ),
    }


def scan_convergence(
    root_dir: str | None,
    threshold_gpa: float = DEFAULT_THRESHOLD_GPA,
    property_name: str = 'C11',
) -> dict[str, Any]:
    if not root_dir or not os.path.isdir(root_dir):
        return {
            'success': False,
            'message': 'root_dir 无效或目录不存在（路径相对于 pyserver 所在机器）',
        }
    if property_name.upper() != 'C11':
        return {'success': False, 'message': '当前仅支持 property=C11 收敛分析'}

    runs = _collect_runs(root_dir)
    sweep = _detect_sweep(runs)
    analysis = _analyze_series(runs, sweep, float(threshold_gpa))

    qc_tags = {
        'k_convergence_tier': analysis.get('recommended', {}).get('k_convergence_tier'),
        'encut': analysis.get('recommended', {}).get('encut_eV'),
        'convergence_passed': analysis.get('converged'),
        'convergence_delta_c11_GPa': analysis.get('last_delta_c11_GPa'),
    }

    return {
        'success': True,
        'root_dir': root_dir,
        'sweep_type': sweep,
        'threshold_GPa': threshold_gpa,
        'runs': runs,
        'analysis': analysis,
        'qc_suggestions': qc_tags,
        'workflow_note': '独立 HPC 批量算例完成后，将根目录路径传入本接口；推荐值可写入 vasp_import 的 encut / k_convergence_tier',
    }
