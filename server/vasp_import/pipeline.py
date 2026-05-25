"""VASP 入库：稳定性检验 → 组装 element_inf 字段 → 写入审核队列。"""

from __future__ import annotations

import time
from typing import Any, Callable

from .moduli import compute_moduli, moduli_to_db_fields
from .parser import merge_manual_cij, scan_work_dir
from .stability import check_stability

VALID_METHODS = ('stress_strain', 'energy_strain', 'summary', 'outcar_elastic_tensor', 'manual')


def _structure_to_system(structure: str) -> str:
    s = (structure or '').strip().lower()
    if s in ('fcc', 'bcc', 'cubic'):
        return 'cubic'
    if s in ('hcp', 'hex', 'hexagonal'):
        return 'hexagonal'
    return 'auto'


def build_import_result(
    *,
    element: str,
    structure: str,
    method: str,
    username: str,
    cij: dict[str, float] | None = None,
    work_dir: str | None = None,
    scan_dir: str | None = None,
    notes: str = '',
    extra_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    element = (element or '').strip()
    if not element:
        raise ValueError('缺少 element（元素符号）')
    method = (method or 'summary').strip().lower()
    if method not in VALID_METHODS:
        raise ValueError(f'method 须为 {", ".join(VALID_METHODS)} 之一')

    parsed_meta: dict[str, Any] = {}
    source_file = None
    resolved_work_dir = work_dir or scan_dir

    if cij is None:
        if not scan_dir and not work_dir:
            raise ValueError('请提供 cij 或 scan_dir/work_dir')
        scan = scan_work_dir(scan_dir or work_dir or '.', method=method)
        cij = scan['cij']
        parsed_meta = scan.get('meta') or {}
        source_file = scan.get('source_file')
        resolved_work_dir = scan.get('work_dir', resolved_work_dir)
    elif scan_dir or work_dir:
        try:
            scan = scan_work_dir(scan_dir or work_dir or '.', method=method)
            cij = merge_manual_cij(scan['cij'], cij)
            parsed_meta = scan.get('meta') or {}
            source_file = scan.get('source_file')
        except ValueError:
            pass

    if not cij:
        raise ValueError('未能解析任何 Cij 分量')

    crystal_system = _structure_to_system(structure or str(parsed_meta.get('structure', '')))
    stability = check_stability(crystal_system, cij)
    moduli = compute_moduli(stability['crystal_system'], {k: float(v) for k, v in cij.items()})

    db_data: dict[str, str] = {
        '元素': element,
        '晶体结构': structure or str(parsed_meta.get('structure', '') or stability['crystal_system']),
    }
    if cij.get('C11') is not None:
        db_data['弹性刚度常数C11'] = str(round(cij['C11'], 4))
    for k in ('C12', 'C13', 'C33', 'C44'):
        if cij.get(k) is not None:
            db_data[k] = str(round(cij[k], 4))
    db_data.update(moduli_to_db_fields(moduli))
    db_data['data_source'] = f'VASP {method}'
    if notes:
        db_data['备注'] = notes
    elif parsed_meta.get('notes'):
        db_data['备注'] = str(parsed_meta['notes'])

    calc_meta = {
        'method': method,
        'functional': extra_meta.get('functional') if extra_meta else None,
        'encut': extra_meta.get('encut') if extra_meta else None,
        'k_mesh': extra_meta.get('k_mesh') if extra_meta else None,
        'temperature_K': extra_meta.get('temperature_K', 0) if extra_meta else 0,
        'soc': extra_meta.get('soc', False) if extra_meta else False,
        'work_dir': resolved_work_dir,
        'source_file': source_file,
        'stability_passed': stability['passed'],
        'suggested_target_db': 'element_inf',
    }
    if extra_meta:
        calc_meta.update({k: v for k, v in extra_meta.items() if k not in calc_meta})

    return {
        'success': stability['passed'],
        'auto_rejected': not stability['passed'],
        'element': element,
        'structure': db_data['晶体结构'],
        'method': method,
        'username': username,
        'cij': {k: round(float(v), 4) for k, v in cij.items()},
        'moduli': moduli,
        'stability': stability,
        'db_data': db_data,
        'calc_meta': calc_meta,
        'message': (
            '稳定性检验通过，已提交管理员审核'
            if stability['passed']
            else '稳定性检验未通过，已自动退回：' + '; '.join(stability['messages'])
        ),
    }


def submit_import_application(
    result: dict[str, Any],
    *,
    load_apps: Callable[[], list],
    save_apps: Callable[[], None],
) -> dict[str, Any]:
    """将通过检验的结果写入 data_input_applications（pending）。"""
    if result.get('auto_rejected'):
        return {
            'success': False,
            'auto_rejected': True,
            'stability': result.get('stability'),
            'message': result.get('message'),
        }

    username = (result.get('username') or '').strip()
    if not username:
        return {'success': False, 'message': '缺少 username'}

    apps = load_apps()
    app_id = str(int(time.time() * 1000))
    entry = {
        'id': app_id,
        'username': username,
        'source_type': 'vasp_import',
        'data': result['db_data'],
        'cij': result.get('cij'),
        'moduli': result.get('moduli'),
        'stability': result.get('stability'),
        'calc_meta': result.get('calc_meta'),
        'method': result.get('method'),
        'status': 'pending',
        'suggested_target_db': 'element_inf',
        'created_at': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime()),
    }
    apps.append(entry)
    save_apps()
    return {
        'success': True,
        'auto_rejected': False,
        'id': app_id,
        'stability': result.get('stability'),
        'db_data': result.get('db_data'),
        'message': result.get('message'),
    }
