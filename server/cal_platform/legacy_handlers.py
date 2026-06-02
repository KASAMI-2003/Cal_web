"""遗留 API：mysql_changeData、create_matrix、execute_ssh。"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import mysql.connector


def _mysql_conn(db_name: str = 'element'):
    try:
        return mysql.connector.connect(
            host='localhost',
            user='py_server',
            password='123456',
            database=db_name,
            auth_plugin='mysql_native_password',
            unix_socket=os.path.expanduser('~/mysql/tmp/mysql.sock'),
        )
    except Exception:
        return mysql.connector.connect(
            host='localhost',
            user='py_server',
            password='123456',
            database=db_name,
            auth_plugin='mysql_native_password',
        )


def handle_mysql_change_data(data: dict) -> dict:
    """POST /mysql_changeData — 更新 element_inf 指定元素字段。"""
    element = (data.get('element') or data.get('元素') or '').strip()
    fields = data.get('fields') or data.get('data') or {}
    if not element or not isinstance(fields, dict):
        return {'success': False, 'message': '需要 element 与 fields'}
    try:
        conn = _mysql_conn('element')
        cur = conn.cursor()
        sets = ', '.join(f'`{k}`=%s' for k in fields)
        sql = f'UPDATE element_inf SET {sets} WHERE `元素`=%s'
        params = list(fields.values()) + [element]
        cur.execute(sql, params)
        conn.commit()
        cur.close()
        conn.close()
        return {'success': True, 'message': f'已更新 {element}', 'affected': cur.rowcount}
    except Exception as e:
        logging.warning('mysql_changeData: %s', e)
        return {'success': False, 'message': str(e)}


def handle_create_matrix(data: dict) -> dict:
    """POST /create_matrix — 由 Cij 生成 6×6 Voigt 弹性矩阵。"""
    cij = data.get('cij') or {}
    structure = (data.get('structure') or 'cubic').lower()
    try:
        from digital_twin.crystal_elastic import build_C_matrix

        normalized = {k.upper(): float(v) for k, v in cij.items()}
        if structure in ('hcp', 'hex', 'hexagonal') and 'C13' not in normalized:
            return {'success': False, 'message': 'hcp 需要 C11,C12,C13,C33,C44'}
        if 'C44' not in normalized:
            return {'success': False, 'message': '缺少 C44'}
        C = build_C_matrix(structure, normalized)
        return {'success': True, 'matrix': C.tolist(), 'structure': structure}
    except Exception as e:
        return {'success': False, 'message': str(e)}


def handle_execute_ssh(data: dict) -> dict:
    """POST /execute_ssh — 远程执行单条命令（Paramiko）。"""
    host = (data.get('host') or '127.0.0.1').strip()
    port = int(data.get('port') or 22)
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    command = (data.get('command') or '').strip()
    if not username or not command:
        return {'success': False, 'message': '需要 username 与 command'}
    try:
        import paramiko

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        connect_kw: dict[str, Any] = {'hostname': host, 'port': port, 'username': username, 'timeout': 15}
        if password:
            connect_kw['password'] = password
        else:
            key_path = os.path.expanduser('~/.ssh/id_ed25519')
            if os.path.isfile(key_path):
                connect_kw['key_filename'] = key_path
        client.connect(**connect_kw)
        _, stdout, stderr = client.exec_command(command, timeout=120)
        out = stdout.read().decode('utf-8', errors='replace')
        err = stderr.read().decode('utf-8', errors='replace')
        code = stdout.channel.recv_exit_status()
        client.close()
        return {'success': code == 0, 'exit_code': code, 'stdout': out, 'stderr': err}
    except Exception as e:
        return {'success': False, 'message': str(e)}


VASP_TASK_PRESETS = {
    'relax': 'vasp_std > vasp_relax.log 2>&1',
    'static': 'vasp_std > vasp_static.log 2>&1',
    'elastic': 'vasp_std > vasp_elastic.log 2>&1',
}


def parse_outcar_tail(work_dir: str, tail_lines: int = 80) -> dict:
    path = os.path.join(work_dir or '.', 'OUTCAR')
    if not os.path.isfile(path):
        return {'success': False, 'message': 'OUTCAR 不存在'}
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()
    tail = lines[-tail_lines:]
    energies = []
    for line in tail:
        if 'free  energy   TOTEN' in line or 'energy  without entropy' in line:
            parts = line.split()
            for p in parts:
                try:
                    energies.append(float(p))
                    break
                except ValueError:
                    continue
    return {
        'success': True,
        'tail': ''.join(tail),
        'energy_samples': energies[-20:],
        'line_count': len(lines),
    }
