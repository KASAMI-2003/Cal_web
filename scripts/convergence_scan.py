#!/usr/bin/env python3
"""CLI：ENCUT/k 点收敛扫描（论文 §2.3 / §5.4 辅助）。"""

from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER = os.path.join(ROOT, 'server')
if SERVER not in sys.path:
    sys.path.insert(0, SERVER)

from cal_platform.convergence_scan import scan_convergence  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description='扫描 VASP 算例目录 ENCUT/k 收敛')
    parser.add_argument('root_dir', help='包含多组子目录或 OUTCAR 的根路径')
    parser.add_argument('--threshold', type=float, default=2.0, help='C11 收敛阈值 GPa（默认 2）')
    parser.add_argument('--json', action='store_true', help='仅输出 JSON')
    args = parser.parse_args()

    result = scan_convergence(args.root_dir, threshold_gpa=args.threshold)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get('success') else 1


if __name__ == '__main__':
    raise SystemExit(main())
