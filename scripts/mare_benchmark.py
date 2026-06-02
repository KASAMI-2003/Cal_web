#!/usr/bin/env python3
"""MARE 基准脚本：对 element 与实验值（Simmons & Wang 1971）对比。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'server'))

from vasp_import.mare_benchmark import compute_mare  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description='Compute MARE vs experimental elastic data')
    parser.add_argument('--element', required=True, help='Element symbol, e.g. Cu')
    parser.add_argument('--c11', type=float, required=True)
    parser.add_argument('--c12', type=float, required=True)
    parser.add_argument('--c44', type=float, required=True)
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()

    cij = {'C11': args.c11, 'C12': args.c12, 'C44': args.c44}
    report = compute_mare(args.element, cij)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(report.get('message', report))
        if report.get('needs_review'):
            print('NEEDS REVIEW (>15%)')
            return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
