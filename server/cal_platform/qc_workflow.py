"""四步 QC：算完 → 自动标注 → 待人工确认 → 正式入库。"""

from __future__ import annotations

import time
from typing import Any, Callable


def enrich_import_with_qc(result: dict[str, Any], work_dir: str | None = None) -> dict[str, Any]:
    """在 build_import_result 之后附加 MARE、双方法、元数据、QC 状态。"""
    from vasp_import.dual_method import compare_dual_methods
    from vasp_import.mare_benchmark import compute_mare
    from vasp_import.metadata_extract import extract_metadata

    element = result.get('element') or result.get('db_data', {}).get('元素', '')
    cij = result.get('cij') or {}
    moduli = result.get('moduli') or {}

    meta = extract_metadata(work_dir, method=str(result.get('method', '')))
    calc_meta = dict(result.get('calc_meta') or {})
    calc_meta.update({k: v for k, v in meta.items() if v not in (None, '')})

    quality = dict(result.get('quality') or {})
    if meta.get('k_convergence_tier') and not quality.get('k_convergence_tier'):
        quality['k_convergence_tier'] = meta['k_convergence_tier']
    if meta.get('strain_fit_residual') and not quality.get('strain_fit_residual'):
        quality['strain_fit_residual'] = meta['strain_fit_residual']

    mare = compute_mare(str(element), cij, moduli)
    if mare.get('calc_exp_deviation_label') and not quality.get('calc_exp_deviation_label'):
        quality['calc_exp_deviation_label'] = mare['calc_exp_deviation_label']

    dual = None
    if work_dir:
        dual = compare_dual_methods(work_dir, str(element))

    qc_status = 'auto_labeled'
    qc_steps = [
        {'step': 1, 'name': 'compute', 'status': 'done', 'at': time.strftime('%Y-%m-%d %H:%M:%S')},
        {'step': 2, 'name': 'auto_label', 'status': 'done'},
        {'step': 3, 'name': 'human_confirm', 'status': 'pending'},
        {'step': 4, 'name': 'formal_import', 'status': 'pending'},
    ]

    auto_reject = result.get('auto_rejected', False)
    if mare.get('auto_reject_mare'):
        auto_reject = True
        result['auto_rejected'] = True
        result['success'] = False
        result['message'] = (
            result.get('message', '')
            + f"；MARE {mare.get('mare_pct')}% 超过 15% 阈值，自动退回"
        ).strip('；')

    result['calc_meta'] = calc_meta
    result['quality'] = quality
    result['mare_report'] = mare
    result['dual_method'] = dual
    result['qc_workflow'] = {
        'status': qc_status,
        'steps': qc_steps,
        'born_passed': (result.get('stability') or {}).get('passed'),
        'mouhat_passed': (result.get('stability') or {}).get('mouhat_passed'),
        'mare_pct': mare.get('mare_pct'),
        'dual_method_passed': (dual or {}).get('passed'),
    }
    result['db_data'] = dict(result.get('db_data') or {})
    if mare.get('label'):
        result['db_data']['calc_exp_deviation_label'] = mare['label']
    if meta.get('encut'):
        result['db_data']['ENCUT'] = str(meta['encut'])
    if meta.get('reference_doi'):
        result['db_data']['reference_doi'] = str(meta['reference_doi'])
    if (result.get('stability') or {}).get('passed') is not None:
        result['db_data']['Born稳定性'] = '通过' if result['stability']['passed'] else '未通过'
    return result


def mark_human_confirmed(entry: dict, admin_user: str, action: str) -> dict:
    wf = dict(entry.get('qc_workflow') or {})
    steps = list(wf.get('steps') or [])
    for s in steps:
        if s.get('step') == 3:
            s['status'] = 'approved' if action == 'approve' else 'rejected'
            s['by'] = admin_user
            s['at'] = time.strftime('%Y-%m-%d %H:%M:%S')
        if s.get('step') == 4 and action == 'approve':
            s['status'] = 'done'
            s['at'] = time.strftime('%Y-%m-%d %H:%M:%S')
    wf['steps'] = steps
    wf['status'] = 'approved' if action == 'approve' else 'rejected'
    entry['qc_workflow'] = wf
    return entry
