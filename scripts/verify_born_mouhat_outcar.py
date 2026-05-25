#!/usr/bin/env python3
"""用 scripts/examples/outcar_* 样例检验 OUTCAR 解析与 Born/Mouhat 判据。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / 'server'
if str(SERVER) not in sys.path:
    sys.path.insert(0, str(SERVER))

from vasp_import.parser import parse_outcar_elastic_tensor, scan_work_dir  # noqa: E402
from vasp_import.pipeline import build_import_result  # noqa: E402

CASES = [
    {
        'dir': ROOT / 'scripts/examples/outcar_cubic_pass',
        'element': 'Cu',
        'structure': 'fcc',
        'expect_pass': True,
    },
    {
        'dir': ROOT / 'scripts/examples/outcar_cubic_fail',
        'element': 'X',
        'structure': 'cubic',
        'expect_pass': False,
    },
    {
        'dir': ROOT / 'scripts/examples/outcar_hex_pass',
        'element': 'Mg',
        'structure': 'hcp',
        'expect_pass': True,
    },
]


def main() -> int:
    failed = 0
    for case in CASES:
        work_dir = str(case['dir'])
        print(f'\n=== {case["dir"].name} ({case["structure"]}) ===')
        cij = parse_outcar_elastic_tensor(str(case['dir'] / 'OUTCAR'))
        print('parsed Cij (GPa):', json.dumps({k: round(v, 4) for k, v in cij.items()}, ensure_ascii=False))

        result = build_import_result(
            element=case['element'],
            structure=case['structure'],
            method='outcar_elastic_tensor',
            username='test',
            scan_dir=work_dir,
        )
        stability = result['stability']
        passed = bool(stability.get('passed'))
        print('crystal_system:', stability.get('crystal_system'))
        for chk in stability.get('checks', []):
            mark = 'OK' if chk['passed'] else 'FAIL'
            expr = str(chk['expr']).replace('\u2212', '-').replace('\u00b2', '^2')
            print(f"  [{mark}] {expr} = {chk['value']}")
        msgs = [str(m).replace('\u2212', '-') for m in stability.get('messages', [])]
        print('messages:', msgs)

        if passed != case['expect_pass']:
            print(f'ERROR: expected passed={case["expect_pass"]}, got {passed}')
            failed += 1
        else:
            print('RESULT: as expected')

    print(f'\n{"All cases passed." if not failed else f"{failed} case(s) failed."}')
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
