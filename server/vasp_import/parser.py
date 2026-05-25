"""从汇总表、JSON、OUTCAR 目录解析弹性常数 Cij（GPa）。"""

from __future__ import annotations

import csv
import json
import os
import re
from typing import Any

CIJ_KEYS = ('C11', 'C12', 'C13', 'C33', 'C44')
SCAN_FILENAMES = (
    'elastic_import.json',
    'elastic_summary.json',
    'elastic_results.txt',
    'elastic_constants.txt',
    'summary.csv',
    'elastic.csv',
)

_CIJ_RE = re.compile(
    r'^\s*(C11|C12|C13|C33|C44|c11|c12|c13|c33|c44)\s*[=:]\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)',
    re.MULTILINE,
)
_STRESS_KB_RE = re.compile(
    r'(?:in kB|total\s+FORCES.*?)\s*\n.*?TOTAL-FORCE.*?stress.*?'
    r'|\n\s*direct\s+ion\s+|\n\s*in\s+kB\s*\n',
    re.IGNORECASE | re.DOTALL,
)


def _norm_cij_key(k: str) -> str:
    u = k.strip().upper()
    if u.startswith('C') and len(u) in (3, 4):
        return u[:1] + u[1:]
    return u


def parse_cij_dict(raw: dict[str, Any]) -> dict[str, float]:
    out: dict[str, float] = {}
    for key, val in raw.items():
        nk = _norm_cij_key(str(key))
        if nk in CIJ_KEYS and val not in (None, ''):
            out[nk] = float(val)
    return out


def parse_keyvalue_text(text: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for m in _CIJ_RE.finditer(text):
        out[_norm_cij_key(m.group(1))] = float(m.group(2))
    return out


def parse_json_file(path: str) -> dict[str, Any]:
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f'{path} 根节点须为 JSON 对象')
    cij = data.get('cij') or data.get('Cij') or data
    if isinstance(cij, dict):
        parsed = parse_cij_dict(cij)
    else:
        parsed = parse_cij_dict(data)
    meta = {k: data.get(k) for k in ('element', 'structure', 'method', 'work_dir', 'notes') if k in data}
    return {'cij': parsed, 'meta': meta, 'source_file': os.path.basename(path)}


def parse_csv_file(path: str) -> dict[str, Any]:
    with open(path, 'r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    if not rows:
        raise ValueError(f'{path} 为空')
    row = rows[0]
    cij = parse_cij_dict({k: row.get(k) for k in row})
    meta = {}
    for k in ('element', '元素', 'structure', '晶体结构', 'method'):
        if k in row and row[k]:
            meta[k] = row[k]
    return {'cij': cij, 'meta': meta, 'source_file': os.path.basename(path)}


def parse_text_file(path: str) -> dict[str, Any]:
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        text = f.read()
    cij = parse_keyvalue_text(text)
    if not cij:
        raise ValueError(f'{path} 中未找到 C11/C12/... 键值')
    return {'cij': cij, 'meta': {}, 'source_file': os.path.basename(path)}


def parse_outcar_elastic_tensor(path: str) -> dict[str, float]:
    """从 OUTCAR 的 ELASTIC TENSOR 块读取 6×6 矩阵（Voigt，kBar→GPa）。"""
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        lines = f.readlines()
    start = None
    for i, line in enumerate(lines):
        if 'ELASTIC TENSOR' in line.upper() and 'kBar' in line:
            start = i + 1
            break
    if start is None:
        raise ValueError(f'{path} 中未找到 ELASTIC TENSOR (kBar) 段')
    matrix_rows: list[list[float]] = []
    for line in lines[start : start + 12]:
        nums = re.findall(r'[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?', line)
        if len(nums) >= 6:
            matrix_rows.append([float(x) for x in nums[:6]])
        if len(matrix_rows) >= 6:
            break
    if len(matrix_rows) < 6:
        raise ValueError(f'{path} ELASTIC TENSOR 行数不足')
    # kBar → GPa
    c = [[v / 10.0 for v in row] for row in matrix_rows]
    out = {
        'C11': c[0][0],
        'C12': c[0][1],
        'C44': c[3][3],
    }
    if abs(c[2][2] - c[0][0]) > 1.0 or abs(c[0][2]) > 0.5:
        out['C33'] = c[2][2]
        out['C13'] = c[0][2]
    return out


def scan_work_dir(work_dir: str, method: str | None = None) -> dict[str, Any]:
    """扫描目录内汇总文件；若无则尝试当前目录 OUTCAR。"""
    work_dir = os.path.abspath(work_dir)
    if not os.path.isdir(work_dir):
        raise ValueError(f'目录不存在: {work_dir}')

    for name in SCAN_FILENAMES:
        path = os.path.join(work_dir, name)
        if not os.path.isfile(path):
            continue
        if name.endswith('.json'):
            result = parse_json_file(path)
        elif name.endswith('.csv'):
            result = parse_csv_file(path)
        else:
            result = parse_text_file(path)
        result['work_dir'] = work_dir
        if method:
            result.setdefault('meta', {})['method'] = method
        return result

    outcar = os.path.join(work_dir, 'OUTCAR')
    if os.path.isfile(outcar):
        cij_raw = parse_outcar_elastic_tensor(outcar)
        cij = {k: v for k, v in cij_raw.items() if v is not None}
        return {
            'cij': cij,
            'meta': {'method': method or 'outcar_elastic_tensor'},
            'source_file': 'OUTCAR',
            'work_dir': work_dir,
        }

    raise ValueError(
        f'在 {work_dir} 未找到 {", ".join(SCAN_FILENAMES)} 或含 ELASTIC TENSOR 的 OUTCAR'
    )


def merge_manual_cij(
    base: dict[str, float],
    overrides: dict[str, float | None],
) -> dict[str, float]:
    out = dict(base)
    for k, v in overrides.items():
        nk = _norm_cij_key(k)
        if v is not None and nk in CIJ_KEYS:
            out[nk] = float(v)
    return out
