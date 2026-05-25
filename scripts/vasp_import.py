#!/usr/bin/env python3
"""
VASP 弹性常数入库 CLI：在 OUTCAR/汇总表所在目录执行，解析 Cij 并 POST 至 Cal Web API。

示例（当前目录含 elastic_import.json 或 OUTCAR）：
  python scripts/vasp_import.py --username admin --element Cu --structure fcc --method stress_strain --scan-dir .

示例（命令行指定 Cij，GPa）：
  python scripts/vasp_import.py --username admin --element Cu --structure fcc --method energy_strain \\
    --c11 175.96 --c12 124.75 --c44 78.36

环境变量：
  CALWEB_API_URL  默认 http://127.0.0.1:3569
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / 'server'
if str(SERVER) not in sys.path:
    sys.path.insert(0, str(SERVER))

import requests  # noqa: E402

from vasp_import.parser import merge_manual_cij, scan_work_dir  # noqa: E402


def _float_or_none(v):
    if v is None or v == '':
        return None
    return float(v)


def build_payload(args: argparse.Namespace) -> dict:
    cij = {}
    for name in ('c11', 'c12', 'c13', 'c33', 'c44'):
        val = _float_or_none(getattr(args, name, None))
        if val is not None:
            cij[f'C{name[1:].upper()}'] = val

    work_dir = os.path.abspath(args.scan_dir or os.getcwd())
    parsed_from = None

    if args.json:
        path = os.path.abspath(args.json)
        from vasp_import.parser import parse_json_file

        scan = parse_json_file(path)
        cij = merge_manual_cij(scan['cij'], cij)
        parsed_from = path
    elif args.scan_dir is not None or not cij:
        scan = scan_work_dir(args.scan_dir or '.', method=args.method)
        cij = merge_manual_cij(scan['cij'], cij)
        work_dir = scan.get('work_dir', work_dir)
        parsed_from = scan.get('source_file')

    if not cij:
        raise SystemExit('未解析到 Cij：请提供 --scan-dir / --json 或 --c11 等参数')

    payload = {
        'username': args.username,
        'element': args.element,
        'structure': args.structure,
        'method': args.method,
        'cij': cij,
        'work_dir': work_dir,
        'notes': args.notes or '',
    }
    if args.functional:
        payload['functional'] = args.functional
    if args.encut:
        payload['encut'] = args.encut
    if args.k_mesh:
        payload['k_mesh'] = args.k_mesh
    if parsed_from:
        payload['notes'] = (payload['notes'] + f' | 源: {parsed_from}').strip(' |')
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description='VASP 弹性常数 → Cal Web 入库审核')
    parser.add_argument('--api-url', default=os.environ.get('CALWEB_API_URL', 'http://127.0.0.1:3569'))
    parser.add_argument('--username', required=True, help='登录用户名')
    parser.add_argument('--element', required=True, help='元素符号，如 Cu')
    parser.add_argument('--structure', required=True, choices=['fcc', 'bcc', 'hcp', 'cubic', 'hexagonal'])
    parser.add_argument(
        '--method',
        required=True,
        choices=['stress_strain', 'energy_strain', 'summary', 'outcar_elastic_tensor', 'manual'],
    )
    parser.add_argument('--scan-dir', default='.', help='扫描 elastic_import.json / OUTCAR 等（默认当前目录）')
    parser.add_argument('--json', help='直接指定 elastic_import.json 路径')
    parser.add_argument('--c11', type=float)
    parser.add_argument('--c12', type=float)
    parser.add_argument('--c13', type=float)
    parser.add_argument('--c33', type=float)
    parser.add_argument('--c44', type=float)
    parser.add_argument('--notes', default='')
    parser.add_argument('--functional', default='GGA-PBE')
    parser.add_argument('--encut', help='截断能 eV')
    parser.add_argument('--k-mesh', dest='k_mesh', help='k 点密度描述')
    parser.add_argument('--dry-run', action='store_true', help='仅本地解析与检验，不提交 API')
    args = parser.parse_args()

    payload = build_payload(args)

    if args.dry_run:
        from vasp_import.pipeline import build_import_result

        result = build_import_result(
            element=payload['element'],
            structure=payload['structure'],
            method=payload['method'],
            username=payload['username'],
            cij=payload['cij'],
            work_dir=payload.get('work_dir'),
            notes=payload.get('notes', ''),
            extra_meta={k: payload[k] for k in ('functional', 'encut', 'k_mesh') if k in payload},
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get('success') else 1

    url = args.api_url.rstrip('/') + '/api/vasp/import'
    try:
        resp = requests.post(url, json=payload, timeout=60)
        resp.raise_for_status()
        body = resp.json()
    except requests.RequestException as e:
        print(f'API 请求失败: {e}', file=sys.stderr)
        return 2

    print(json.dumps(body, ensure_ascii=False, indent=2))
    if body.get('auto_rejected'):
        return 1
    return 0 if body.get('success') else 1


if __name__ == '__main__':
    raise SystemExit(main())
