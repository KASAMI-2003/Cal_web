# 导入 http.server 模块
import http.server
import socketserver
import json
from flask import request
import re #正则表达式
#导入运算获取模块
import platform
import sys
import logging
from mp_api.client import MPRester
import pandas as pd
import csv
import mysql.connector
from mysql.connector import Error
import numpy as np
from ase import Atoms
from ase.lattice.hexagonal import HexagonalClosedPacked
from ase.visualize import view
from ase.neighborlist import NeighborList
from ase import Atoms
from ase.lattice.cubic import BodyCenteredCubic
import os

# 无图形界面环境（常见 Linux 服务器）下避免 matplotlib 选用需要 Tk/Qt 的后端
os.environ.setdefault('MPLBACKEND', 'Agg')

# tsx-web-app：后端根目录固定为当前本文件所在目录（与「主页面」上级路径解耦）
SERVER_ROOT = os.path.dirname(os.path.abspath(__file__))
if SERVER_ROOT not in sys.path:
    sys.path.insert(0, SERVER_ROOT)

from automation import ssh_command
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
import io
from flask import Flask, send_file, render_template
from urllib.parse import parse_qs, urlparse
import asyncio
import websockets
import subprocess
import threading
import concurrent.futures
import socket
import base64
import time
import shutil
import paramiko

# WebSocket连接集合
CONNECTIONS = set()

# 存储WebSocket端口
websocket_port = None


def check_terminal_host_tcp(host, port, timeout=3.0):
    """对 host:port 做一次 TCP 连接测试（不建立 SSH）。成功表示该端口可连，通常说明 SSH 等服务在线。"""
    try:
        p = int(port)
    except (TypeError, ValueError):
        return False, {'code': 'invalid_port', 'message': '端口无效'}
    if p < 1 or p > 65535:
        return False, {'code': 'invalid_port', 'message': '端口无效'}
    host = (host or '').strip()
    if not host:
        return False, {'code': 'invalid_host', 'message': '主机为空'}
    t0 = time.monotonic()
    try:
        with socket.create_connection((host, p), timeout=timeout):
            pass
        ms = max(1, int((time.monotonic() - t0) * 1000))
        return True, {'latency_ms': ms}
    except socket.gaierror:
        return False, {'code': 'dns', 'message': '无法解析主机名'}
    except TimeoutError:
        return False, {'code': 'timeout', 'message': '连接超时'}
    except OSError as e:
        err = str(e).lower()
        if 'timed out' in err or 'timeout' in err:
            return False, {'code': 'timeout', 'message': '连接超时'}
        if 'refused' in err or '积极拒绝' in str(e) or '拒绝' in str(e):
            return False, {'code': 'refused', 'message': '端口未开放或拒绝连接'}
        return False, {'code': 'error', 'message': (str(e) or '网络错误')[:120]}

# 数据输入申请存储（JSON 文件）
DATA_INPUT_APPLICATIONS_FILE = os.path.join(SERVER_ROOT, 'data_input_applications.json')
_data_input_applications = None

def _load_data_input_applications():
    global _data_input_applications
    if _data_input_applications is not None:
        return _data_input_applications
    try:
        if os.path.isfile(DATA_INPUT_APPLICATIONS_FILE):
            with open(DATA_INPUT_APPLICATIONS_FILE, 'r', encoding='utf-8') as f:
                _data_input_applications = json.load(f)
        else:
            _data_input_applications = []
    except Exception as e:
        logging.warning("load data_input_applications: %s", e)
        _data_input_applications = []
    return _data_input_applications

def _save_data_input_applications():
    try:
        with open(DATA_INPUT_APPLICATIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(_data_input_applications or [], f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.warning("save data_input_applications: %s", e)

def _find_private_key_path():
    """依次查找 id_ed25519、id_rsa。OpenSSH 新版私钥须用 OpenSSH 的 ssh；PuTTY plink 常不兼容。"""
    ssh_dir = os.path.expanduser('~/.ssh')
    for name in ('id_ed25519', 'id_rsa'):
        p = os.path.join(ssh_dir, name)
        if os.path.isfile(p):
            return p
    return None


def _shell_escape_remote_path(p):
    """与 WINDOWS/ssh-bridge 一致的 POSIX shell 单引号转义。"""
    return "'" + str(p).replace("'", "'\"'\"'") + "'"


def _terminal_auth_dims(msg):
    cols = min(500, max(40, int(msg.get('cols') or 80)))
    rows = min(200, max(10, int(msg.get('rows') or 24)))
    try:
        wp = int(msg.get('widthPx') or 640)
    except (TypeError, ValueError):
        wp = 640
    try:
        hp = int(msg.get('heightPx') or 480)
    except (TypeError, ValueError):
        hp = 480
    wp = max(100, min(12000, wp))
    hp = max(100, min(12000, hp))
    return cols, rows, wp, hp


def _load_pkey_from_pem(pem_str, passphrase=None):
    """解析 PEM 私钥（RSA / Ed25519 / ECDSA）。"""
    fp = io.StringIO(str(pem_str))
    pwd = str(passphrase) if passphrase else None
    last_err = None
    for loader in (paramiko.RSAKey, paramiko.Ed25519Key, paramiko.ECDSAKey):
        fp.seek(0)
        try:
            return loader.from_private_key(fp, password=pwd)
        except Exception as e:
            last_err = e
            continue
    raise ValueError(str(last_err) if last_err else '无法解析 privateKey')


def _open_paramiko_shell_channel(msg):
    """
    阻塞：建立 SSH 会话并打开 PTY shell。
    协议对齐 PyCharm WINDOWS 项目 ssh-bridge.mjs（auth JSON → shell → 双向二进制）。
    """
    host = str(msg.get('host') or '').strip()
    if not host:
        raise ValueError('缺少 host')
    try:
        port = int(msg.get('port') or 22)
    except (TypeError, ValueError):
        port = 22
    port = max(1, min(65535, port))
    username = str(msg.get('username') or '').strip()
    if not username:
        raise ValueError('缺少 username')

    cols, rows, wp, hp = _terminal_auth_dims(msg)
    term = msg.get('term') or 'xterm-256color'

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    # Windows 上默认尝试 ssh-agent / 扫描密钥可能长时间阻塞甚至卡死；此处仅使用前端传来的凭据与固定私钥路径。
    connect_kw = {
        'hostname': host,
        'port': port,
        'username': username,
        'timeout': 15,
        'banner_timeout': 18,
        'auth_timeout': 18,
        'allow_agent': False,
        'look_for_keys': False,
    }
    pwd = msg.get('password')
    if pwd is not None and str(pwd) != '':
        connect_kw['password'] = str(pwd)

    pem = msg.get('privateKey')
    if pem:
        pp = msg.get('passphrase')
        connect_kw['pkey'] = _load_pkey_from_pem(pem, pp)

    key_path = _find_private_key_path()
    if key_path and 'pkey' not in connect_kw:
        connect_kw['key_filename'] = key_path

    if 'password' not in connect_kw and 'key_filename' not in connect_kw and 'pkey' not in connect_kw:
        raise ValueError('需要提供密码，或在 ~/.ssh/ 放置 id_ed25519 / id_rsa，或通过 auth 传入 privateKey')

    client.connect(**connect_kw)
    channel = client.invoke_shell(term=term, width=cols, height=rows, width_pixels=wp, height_pixels=hp)
    cwd = msg.get('cwd')
    if cwd and str(cwd).strip():
        channel.send(f"cd {_shell_escape_remote_path(str(cwd).strip())} 2>/dev/null || true\n")
    return client, channel


def ssh_ping_handshake(body):
    """POST /api/ssh/ping：TCP 可达性 + 可选 SSH 握手（对齐 WINDOWS ssh-bridge）。"""
    host = str(body.get('host') or '').strip()
    try:
        port = int(body.get('port') or 22)
    except (TypeError, ValueError):
        port = 22
    port = max(1, min(65535, port))
    if not host:
        return {'ok': False, 'reachable': False, 'error': '缺少 host'}

    reachable, _detail = check_terminal_host_tcp(host, port, timeout=4.0)
    ssh_ok = False
    client = None
    if reachable:
        try:
            username = str(body.get('username') or '').strip()
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            connect_kw = {
                'hostname': host,
                'port': port,
                'username': username,
                'timeout': 12,
                'banner_timeout': 12,
                'auth_timeout': 12,
                'allow_agent': False,
                'look_for_keys': False,
            }
            pwd = body.get('password')
            if pwd is not None and str(pwd) != '':
                connect_kw['password'] = str(pwd)
            pem = body.get('privateKey')
            if pem:
                pp = body.get('passphrase')
                connect_kw['pkey'] = _load_pkey_from_pem(pem, pp)
            kp = _find_private_key_path()
            if kp and 'pkey' not in connect_kw:
                connect_kw['key_filename'] = kp
            if 'password' not in connect_kw and 'key_filename' not in connect_kw and 'pkey' not in connect_kw:
                return {'ok': True, 'reachable': reachable, 'sshHandshake': False}
            client.connect(**connect_kw)
            ssh_ok = True
        except Exception as e:
            logging.info('ssh ping: handshake failed: %s', e)
        finally:
            if client:
                try:
                    client.close()
                except Exception:
                    pass

    return {'ok': True, 'reachable': reachable, 'sshHandshake': ssh_ok}


async def _pump_ssh_to_ws(channel, websocket):
    try:
        while True:
            data = await asyncio.to_thread(channel.recv, 65536)
            if not data:
                break
            await websocket.send(data)
    except websockets.exceptions.ConnectionClosed:
        pass
    except Exception as e:
        logging.info('终端 ssh→ws 结束: %s', e)


async def _pump_ws_to_ssh(websocket, channel):
    try:
        async for message in websocket:
            if isinstance(message, bytes):
                await asyncio.to_thread(channel.send, message)
                continue
            try:
                obj = json.loads(message)
            except json.JSONDecodeError:
                continue
            if obj.get('type') != 'resize':
                continue
            cols = min(500, max(40, int(obj.get('cols') or 80)))
            rows = min(200, max(10, int(obj.get('rows') or 24)))
            try:
                wp = int(obj.get('widthPx') or 0)
            except (TypeError, ValueError):
                wp = 0
            try:
                hp = int(obj.get('heightPx') or 0)
            except (TypeError, ValueError):
                hp = 0
            if wp > 0 and hp > 0:
                wp = max(100, min(12000, wp))
                hp = max(100, min(12000, hp))
            else:
                wp, hp = 640, 480
            try:
                await asyncio.to_thread(channel.resize_pty, cols, rows, wp, hp)
            except Exception:
                pass
    except websockets.exceptions.ConnectionClosed:
        pass
    except Exception as e:
        logging.info('终端 ws→ssh 结束: %s', e)


async def handle_terminal(websocket):
    """
    WebSocket 终端：与 WINDOWS/ssh-bridge.mjs 一致。
    首包 JSON type=auth → auth-ok / auth-error；之后 SSH 输出为二进制帧；键盘输入为二进制；
    窗口变更发送 JSON {type:'resize', cols, rows, widthPx, heightPx}。
    """
    CONNECTIONS.add(websocket)
    client = None
    channel = None
    try:
        raw_first = await websocket.recv()
        if isinstance(raw_first, bytes):
            await websocket.send(json.dumps({'type': 'auth-error', 'message': '首包须为 JSON auth'}, ensure_ascii=False))
            return

        msg = json.loads(raw_first)
        if msg.get('type') != 'auth':
            await websocket.send(json.dumps({'type': 'auth-error', 'message': '需要 auth'}, ensure_ascii=False))
            return

        try:
            client, channel = await asyncio.to_thread(_open_paramiko_shell_channel, msg)
        except Exception as e:
            err_text = str(e) or type(e).__name__
            logging.warning('终端 SSH 连接失败: %s', err_text)
            await websocket.send(json.dumps({'type': 'auth-error', 'message': err_text}, ensure_ascii=False))
            return

        await websocket.send(json.dumps({'type': 'auth-ok'}, ensure_ascii=False))
        await asyncio.gather(
            _pump_ssh_to_ws(channel, websocket),
            _pump_ws_to_ssh(websocket, channel),
        )

    except json.JSONDecodeError:
        logging.error('终端 auth JSON 无效')
        try:
            await websocket.send(json.dumps({'type': 'auth-error', 'message': '无效消息'}, ensure_ascii=False))
        except Exception:
            pass
    except websockets.exceptions.ConnectionClosed:
        logging.info('终端 WebSocket 已关闭')
    except Exception as e:
        logging.error('终端 WebSocket 异常: %s', e)
        try:
            await websocket.send(json.dumps({'type': 'auth-error', 'message': str(e)}, ensure_ascii=False))
        except Exception:
            pass
    finally:
        CONNECTIONS.discard(websocket)
        if channel is not None:
            try:
                channel.close()
            except Exception:
                pass
        if client is not None:
            try:
                client.close()
            except Exception:
                pass

def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(('localhost', port))
            return False
        except socket.error:
            return True

def find_available_port(start_port):
    port = start_port
    while is_port_in_use(port):
        port += 1
    return port

async def start_websocket_server():
    global websocket_port
    try:
        preferred = int(os.environ.get('TERMINAL_WS_PORT', '8765'))
    except (TypeError, ValueError):
        preferred = 8765
    port = preferred if not is_port_in_use(preferred) else find_available_port(preferred)
    websocket_port = port
    if port != preferred:
        logging.warning(
            '终端 WebSocket 端口 %s 不可用，已改用 %s（请同步 Vite 代理 TERMINAL_WS_PORT）',
            preferred,
            port,
        )
    async with websockets.serve(
        handle_terminal,
        '0.0.0.0',
        port,
        ping_interval=20,
        ping_timeout=40,
        max_size=2**22,
    ):
        print(f"终端 WebSocket（/api/ssh/ws 桥接）监听 0.0.0.0:{port}")
        await asyncio.Future()

def run_websocket_server():
    try:
        asyncio.run(start_websocket_server())
    except Exception as e:
        logging.error(f"WebSocket服务器启动错误: {str(e)}")

# 配置日志（写入 server/error.log，与工作目录无关）
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(SERVER_ROOT, 'error.log'), encoding='utf-8'),
        logging.StreamHandler(sys.stderr)
    ]
)

#定义初值
element = 'U-Nb'
num_element = 2

# --- 数字孪生（TSX：`web/` DigitalTwinPage；Python 桥接在 digital_twin/）---
# 物性 API：优先使用 HTEM-main 半解析模型 SAM（htem_sam_bridge）；失败则回退线性占位。
_DIGITAL_TWIN_MAIN_DIR = os.path.normpath(os.path.join(SERVER_ROOT, 'digital_twin'))
if _DIGITAL_TWIN_MAIN_DIR not in sys.path:
    sys.path.insert(0, _DIGITAL_TWIN_MAIN_DIR)
try:
    from htem_sam_bridge import twin_properties_htem as _twin_properties_htem
except Exception as _e:
    _twin_properties_htem = None
    logging.warning('HTEM SAM 桥接未启用（将仅用占位公式）: %s', _e)
try:
    from anisotropy_surface import compute_anisotropy_bundle as _compute_anisotropy_bundle
except Exception as _e:
    _compute_anisotropy_bundle = None
    logging.warning('各向异性曲面 API 未加载: %s', _e)


def twin_properties_placeholder(T_K, P_GPa):
    """
    物性：与前端 DigitalTwinPage /api/digital_twin/properties 约定字段一致。
    优先调用 HTEM SAM（digital_twin/HTEM-main，需 scipy/matplotlib）；失败则使用线性占位。
    替换为你的 Elasticity_T.dat 后，SAM 会重新拟合温压网格（首次请求可能较慢）。
    :param T_K: 温度 (K)
    :param P_GPa: 压强 (GPa)
    """
    if _twin_properties_htem is not None:
        try:
            return _twin_properties_htem(T_K, P_GPa)
        except Exception as e:
            logging.warning('HTEM SAM 物性计算失败，回退占位: %s', e)
    T_K = float(np.clip(T_K, 273.0, 2000.0))
    P_GPa = float(np.clip(P_GPa, 0.0, 50.0))
    T0, P0 = 300.0, 0.0
    dT = T_K - T0
    dP = P_GPa - P0
    B = 110.0 - 0.025 * dT + 1.1 * dP
    G = 50.0 - 0.018 * dT + 0.45 * dP
    B = float(np.clip(B, 10.0, 400.0))
    G = float(np.clip(G, 5.0, 200.0))
    E = 9.0 * B * G / max(3.0 * B + G, 1e-6)
    volume_scale = 1.0 + 3.6e-5 * dT - 2.8e-3 * dP
    volume_scale = float(np.clip(volume_scale, 0.90, 1.12))
    return {
        'T_K': round(T_K, 2),
        'P_GPa': round(P_GPa, 3),
        'bulk_modulus_GPa': round(B, 2),
        'shear_modulus_GPa': round(G, 2),
        'young_modulus_GPa': round(float(E), 2),
        'volume_scale': volume_scale,
        'model': 'placeholder_linear',
    }


def _twin_resolve_alloy_row(qs):
    """查询串含 twin_file 且为 alloy_table 时返回对应成分行 dict。"""
    try:
        from twin_user_files import ensure_alloy_cache, get_entry
    except Exception:
        return None, None
    tf = (qs.get('twin_file') or [None])[0]
    un = (qs.get('username') or [None])[0]
    if not tf:
        return None, None
    entry = get_entry(tf, un)
    if not entry or entry.get('kind') != 'alloy_table':
        return None, entry
    try:
        comp_i = int((qs.get('comp_index') or ['0'])[0])
    except (TypeError, ValueError):
        comp_i = 0
    rows = ensure_alloy_cache(tf, entry)
    if not rows:
        return None, entry
    return rows[comp_i % len(rows)], entry


def twin_properties_for_request(T_K, P_GPa, qs):
    """侧栏标量：上传成分为 alloy_table 时用表中 B/G/E（或由 cij 估算），否则走 SAM/占位。"""
    row, _ent = _twin_resolve_alloy_row(qs)
    if row is not None:
        c11, c12, c44 = float(row['c11']), float(row['c12']), float(row['c44'])
        B = row.get('B')
        if B is None:
            B = (c11 + 2 * c12) / 3
        else:
            B = float(B)
        G = row.get('G')
        if G is None:
            G = (c11 - c12 + 3 * c44) / 5
        else:
            G = float(G)
        E = row.get('E')
        if E is None:
            E = 9 * B * G / max(3 * B + G, 1e-6)
        else:
            E = float(E)
        return {
            'T_K': round(float(T_K), 2),
            'P_GPa': round(float(P_GPa), 3),
            'bulk_modulus_GPa': round(B, 2),
            'shear_modulus_GPa': round(G, 2),
            'young_modulus_GPa': round(E, 2),
            'volume_scale': 1.0,
            'model': f"alloy_table:{row.get('label', '')}",
        }
    return twin_properties_placeholder(T_K, P_GPa)


#api端口行为定义
class MyRequestHandler(http.server.SimpleHTTPRequestHandler):
    """静态文件（如 /img）相对于 server/ 目录解析，不依赖启动时的 cwd。"""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('directory', SERVER_ROOT)
        super().__init__(*args, **kwargs)

    def end_headers(self):
        # 添加CORS头
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()

    def parse_path(self):
        # 解析URL路径
        parsed = urlparse(self.path)
        path = parsed.path
        return path.rstrip('/')

    def do_HEAD(self):
        """支持 HEAD 请求（Nginx、浏览器预检、健康检查等常用）"""
        self.do_GET()

    def do_GET(self):
        if self.path == '/websocket_port':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            response = {'port': websocket_port}
            self.wfile.write(json.dumps(response).encode('utf-8'))
            return
        path = self.parse_path()
        client_address = self.headers.get('X-Forwarded-For', self.client_address[0])
        logging.info(f"Received GET request from {client_address} for path {path}")
        
        if path == '':
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(
                b'<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"/>'
                b'<title>Python API</title></head><body>'
                b'<p>Python API \xe6\x9c\x8d\xe5\x8a\xa1\xe5\xb7\xb2\xe8\xbf\x90\xe8\xa1\x8c\xe3\x80\x82\xe8\xaf\xb7\xe4\xbd\xbf\xe7\x94\xa8 <code>web/</code> \xe7\x9b\xae\xe5\xbd\x95\xe4\xb8\x8b Vite \xe5\x89\x8d\xe7\xab\xaf\xef\xbc\x88npm run dev\xef\xbc\x89\xe3\x80\x82</p>'
                b'</body></html>'
            )
        elif path == '/api/data':
            try:
                # 使用全局变量element和num_element
                global element, num_element
                logging.info(f"Getting data for element: {element}, num_element: {num_element}")

                imf_list = get_data(element, num_element)
                imf_list.append(f'当前查询: {element} (元素数量: {num_element})')

                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                response = {'message': imf_list}
                self.wfile.write(json.dumps(response).encode('utf-8'))
            except Exception as e:
                logging.error(f"Error in /api/data: {str(e)}")
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                error_response = {'message': [f"获取数据时出错: {str(e)}"]}
                self.wfile.write(json.dumps(error_response).encode('utf-8'))
        elif path == '/data_input/my':
            parsed = urlparse(self.path)
            qs = parse_qs(parsed.query)
            username = (qs.get('username') or [None])[0]
            if not username:
                self.send_response(400)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'message': '缺少 username'}).encode('utf-8'))
                return
            apps = [a for a in _load_data_input_applications() if a.get('username') == username]
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'success': True, 'data': apps}).encode('utf-8'))
        elif path == '/data_input/pending':
            parsed = urlparse(self.path)
            qs = parse_qs(parsed.query)
            admin_user = (qs.get('admin_user') or [None])[0]
            if admin_user != 'admin':
                self.send_response(403)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'message': '需要管理员'}).encode('utf-8'))
                return
            apps = [a for a in _load_data_input_applications() if a.get('status') == 'pending']
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'success': True, 'data': apps}).encode('utf-8'))
        elif path == '/api/digital_twin/properties':
            # 查询参数 T、t、P、p 均可；缺省 300K、0GPa。返回 JSON 驱动前端物性与体积标度。
            parsed = urlparse(self.path)
            qs = parse_qs(parsed.query)
            try:
                T_K = float((qs.get('T') or qs.get('t') or ['300'])[0])
                P_GPa = float((qs.get('P') or qs.get('p') or ['0'])[0])
            except (TypeError, ValueError):
                T_K, P_GPa = 300.0, 0.0
            payload = twin_properties_for_request(T_K, P_GPa, qs)
            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps(payload, ensure_ascii=False).encode('utf-8'))
        elif path == '/api/digital_twin/anisotropy_surface':
            # 返回 E、nu_max、v_l 的球面参数化网格（与 HTEM anisotropy 一致），供 Three.js 绘制各向异性曲面
            parsed = urlparse(self.path)
            qs = parse_qs(parsed.query)
            try:
                T_K = float((qs.get('T') or qs.get('t') or ['300'])[0])
                P_GPa = float((qs.get('P') or qs.get('p') or ['0'])[0])
                n_phi = int((qs.get('n_phi') or ['48'])[0])
                n_theta = int((qs.get('n_theta') or ['72'])[0])
                n_chi = int((qs.get('n_chi') or ['48'])[0])
            except (TypeError, ValueError):
                T_K, P_GPa = 300.0, 0.0
                n_phi, n_theta, n_chi = 48, 72, 48
            try:
                if _compute_anisotropy_bundle is None:
                    raise RuntimeError('anisotropy_surface 模块不可用')
                alloy_row, _ent = _twin_resolve_alloy_row(qs)
                payload = _compute_anisotropy_bundle(
                    T_K, P_GPa, n_phi, n_theta, n_chi, alloy_row=alloy_row
                )
                self.send_response(200)
                self.send_header('Content-type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps(payload, ensure_ascii=False).encode('utf-8'))
            except Exception as e:
                logging.exception('anisotropy_surface: %s', e)
                self.send_response(500)
                self.send_header('Content-type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}, ensure_ascii=False).encode('utf-8'))
        elif path == '/api/digital_twin/capabilities':
            parsed = urlparse(self.path)
            qs = parse_qs(parsed.query)
            try:
                from twin_user_files import (
                    capabilities_for_file,
                    default_capabilities_from_sam,
                    get_entry,
                )

                base = default_capabilities_from_sam()
                tf = (qs.get('twin_file') or [None])[0]
                user = (qs.get('username') or [None])[0]
                if tf:
                    entry = get_entry(tf, user)
                    if not entry:
                        self.send_response(404)
                        self.send_header('Content-type', 'application/json; charset=utf-8')
                        self.end_headers()
                        self.wfile.write(
                            json.dumps({'error': '未找到文件或无权限'}, ensure_ascii=False).encode('utf-8')
                        )
                        return
                    cap = capabilities_for_file(entry, base)
                else:
                    cap = base
                self.send_response(200)
                self.send_header('Content-type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps(cap, ensure_ascii=False).encode('utf-8'))
            except Exception as e:
                logging.exception('digital_twin capabilities: %s', e)
                self.send_response(500)
                self.send_header('Content-type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}, ensure_ascii=False).encode('utf-8'))
        elif path == '/api/digital_twin/list_dat':
            parsed = urlparse(self.path)
            qs = parse_qs(parsed.query)
            user = (qs.get('username') or [''])[0]
            try:
                from twin_user_files import list_user_dats

                files = list_user_dats(user)
                self.send_response(200)
                self.send_header('Content-type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({'files': files}, ensure_ascii=False).encode('utf-8'))
            except Exception as e:
                logging.exception('list_dat: %s', e)
                self.send_response(500)
                self.send_header('Content-type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}, ensure_ascii=False).encode('utf-8'))
        else:
            super().do_GET()

    def do_POST(self):
        global element
        global num_element
        path = self.parse_path()

        try:
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length > 0:
                post_data = self.rfile.read(content_length)
                data = json.loads(post_data.decode('utf-8'))
            else:
                data = {}

            if path == '/api/submit':
                try:
                    # 更新全局变量
                    element = data.get('element', '')
                    num_element = data.get('num_element', 2)
                    logging.info(f"Updated element: {element}, num_element: {num_element}")

                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    response = {'status': 'success', 'message': '数据已更新'}
                    self.wfile.write(json.dumps(response).encode('utf-8'))
                except Exception as e:
                    logging.error(f"Error in /api/submit: {str(e)}")
                    self.send_response(500)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    error_response = {'status': 'error', 'message': str(e)} 
                    self.wfile.write(json.dumps(error_response).encode('utf-8'))

            elif path == '/mysql_receive':
                element = data.get('element', '')
                text = data.get('text', '')

                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                imf_list, db_meta = data_in_mysql(element, text)
                db_materials = None
                if imf_list is None or (isinstance(imf_list, list) and all(v is None for v in imf_list)):
                    imf_list, db_meta, db_materials = data_in_u_nb_materials(element, text)
                response = {
                    'message': _to_json_serializable(imf_list) if imf_list is not None else None,
                    'db_meta': _to_json_serializable(db_meta) if db_meta is not None else None,
                    'db_materials': _to_json_serializable(db_materials) if db_materials else None,
                }
                self.wfile.write(json.dumps(response).encode('utf-8'))

            elif path == '/page2_search':
                q = (data.get('q') or data.get('query') or '').strip()
                fuzzy = data.get('fuzzy', True)
                case_sensitive = data.get('case_sensitive', False)
                search_in = data.get('search_in', 'name')
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                try:
                    result = page2_search_db(q, fuzzy=fuzzy, case_sensitive=case_sensitive, search_in=search_in)
                    safe_result = _to_json_serializable(result)
                    self.wfile.write(json.dumps(safe_result).encode('utf-8'))
                except Exception as e:
                    logging.warning("page2_search 异常: %s", e)
                    self.wfile.write(json.dumps({"elements": [], "materials": [], "error": str(e)}).encode('utf-8'))

            elif path == '/data_input/submit':
                username = (data.get('username') or '').strip()
                app_data = data.get('data') or {}
                if not username:
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'success': False, 'message': '请先登录'}).encode('utf-8'))
                    return
                global _data_input_applications
                _load_data_input_applications()
                import time
                app_id = str(int(time.time() * 1000))
                entry = {
                    'id': app_id,
                    'username': username,
                    'data': app_data,
                    'status': 'pending',
                    'created_at': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime()),
                }
                _data_input_applications.append(entry)
                _save_data_input_applications()
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': True, 'message': '提交成功', 'id': app_id}).encode('utf-8'))

            elif path == '/api/digital_twin/upload_dat':
                username = (data.get('username') or '').strip()
                filename = (data.get('filename') or 'upload.dat').strip()
                b64 = data.get('content_base64') or data.get('b64') or ''
                if not username:
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json; charset=utf-8')
                    self.end_headers()
                    self.wfile.write(
                        json.dumps({'success': False, 'message': '需要登录用户名 username'}, ensure_ascii=False).encode(
                            'utf-8'
                        )
                    )
                    return
                try:
                    raw = base64.b64decode(b64)
                    if len(raw) > 15 * 1024 * 1024:
                        raise ValueError('文件过大（>15MB）')
                    from twin_user_files import register_user_dat

                    entry = register_user_dat(username, raw, filename)
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json; charset=utf-8')
                    self.end_headers()
                    self.wfile.write(
                        json.dumps(
                            {
                                'success': True,
                                'id': entry['id'],
                                'kind': entry['kind'],
                                'probe': entry['probe'],
                            },
                            ensure_ascii=False,
                        ).encode('utf-8')
                    )
                except Exception as e:
                    logging.warning('upload_dat: %s', e)
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json; charset=utf-8')
                    self.end_headers()
                    self.wfile.write(
                        json.dumps({'success': False, 'message': str(e)}, ensure_ascii=False).encode('utf-8')
                    )

            elif path == '/api/digital_twin/activate_dat':
                username = (data.get('username') or '').strip()
                tf = data.get('twin_file')
                try:
                    from twin_user_files import apply_htem_session_for_entry, get_entry

                    if not tf:
                        apply_htem_session_for_entry(None)
                        self.send_response(200)
                        self.send_header('Content-type', 'application/json; charset=utf-8')
                        self.end_headers()
                        self.wfile.write(json.dumps({'success': True, 'mode': 'default_sam'}, ensure_ascii=False).encode('utf-8'))
                        return
                    entry = get_entry(str(tf), username)
                    if not entry:
                        self.send_response(200)
                        self.send_header('Content-type', 'application/json; charset=utf-8')
                        self.end_headers()
                        self.wfile.write(
                            json.dumps({'success': False, 'message': '未找到或无权限'}, ensure_ascii=False).encode('utf-8')
                        )
                        return
                    apply_htem_session_for_entry(entry)
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json; charset=utf-8')
                    self.end_headers()
                    self.wfile.write(
                        json.dumps(
                            {'success': True, 'kind': entry.get('kind'), 'twin_file': entry.get('id')},
                            ensure_ascii=False,
                        ).encode('utf-8')
                    )
                except Exception as e:
                    logging.exception('activate_dat: %s', e)
                    self.send_response(500)
                    self.send_header('Content-type', 'application/json; charset=utf-8')
                    self.end_headers()
                    self.wfile.write(json.dumps({'success': False, 'message': str(e)}, ensure_ascii=False).encode('utf-8'))

            elif path == '/create_lattice_picture':
                lattice_const = data.get('lattice_const', 'fcc')
                lattice_data = create_lattice_picture(lattice_const)

                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(lattice_data).encode('utf-8'))

            elif path == '/api/data_fit':
                try:
                    from data_fitting.fit_funcs import polynomialFit, exponential, logarithmic, sine
                    from data_fitting.fit_tools import get_fit_funcs
                    from scipy.optimize import curve_fit

                    x_data = [float(v) for v in data.get('x_data', [])]
                    y_data = [float(v) for v in data.get('y_data', [])]
                    fit_type = data.get('fit_type', 'Polynomial')
                    degree = int(data.get('degree', 2))

                    if len(x_data) != len(y_data) or len(x_data) < 1:
                        raise ValueError('数据长度不匹配或数据为空')

                    row_count = len(x_data)
                    coeffs = None
                    fit_func_str = ''

                    if fit_type == "Polynomial":
                        if row_count <= degree:
                            raise ValueError(f'数据点不足以支撑拟合{degree}次多项式')
                        coeffs = polynomialFit(x_data, y_data, degree)
                    elif fit_type == "Exponential":
                        if row_count < 2:
                            raise ValueError('数据点不足以支撑拟合指数函数')
                        popt, _ = curve_fit(exponential, x_data, y_data)
                        coeffs = list(popt)
                    elif fit_type == "Logarithmic":
                        if row_count < 2:
                            raise ValueError('数据点不足以支撑拟合对数函数')
                        popt, _ = curve_fit(logarithmic, x_data, y_data)
                        coeffs = list(popt)
                    elif fit_type == "Sine":
                        if row_count < 3:
                            raise ValueError('数据点不足以支撑拟合正弦函数')
                        popt, _ = curve_fit(sine, x_data, y_data)
                        coeffs = list(popt)
                    else:
                        raise ValueError('不支持的拟合类型')

                    fit_func_str = get_fit_funcs(coeffs, fit_type)

                    y_pred = []
                    if fit_type == "Polynomial":
                        y_pred = np.polyval(coeffs, x_data).tolist()
                    elif fit_type == "Exponential":
                        y_pred = [float(exponential(x, *coeffs)) for x in x_data]
                    elif fit_type == "Logarithmic":
                        y_pred = [float(logarithmic(x, *coeffs)) for x in x_data]
                    else:
                        y_pred = [float(sine(x, *coeffs)) for x in x_data]

                    y_mean = float(np.mean(y_data))
                    ss_res = sum((yi - ypi) ** 2 for yi, ypi in zip(y_data, y_pred))
                    ss_tot = sum((yi - y_mean) ** 2 for yi in y_data)
                    r_squared = float(1 - ss_res / ss_tot) if ss_tot != 0 else 0.0

                    x_min = min(x_data)
                    x_max = max(x_data)
                    x_fit = np.linspace(x_min, x_max, 100).tolist()
                    if fit_type == "Polynomial":
                        y_fit = np.polyval(coeffs, x_fit).tolist()
                    elif fit_type == "Exponential":
                        y_fit = [float(exponential(x, *coeffs)) for x in x_fit]
                    elif fit_type == "Logarithmic":
                        y_fit = [float(logarithmic(x, *coeffs)) for x in x_fit]
                    else:
                        y_fit = [float(sine(x, *coeffs)) for x in x_fit]

                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    response = {
                        'status': 'success',
                        'fit_func': fit_func_str,
                        'r_squared': round(r_squared, 6),
                        'coeffs': [float(c) for c in coeffs],
                        'x_fit': x_fit,
                        'y_fit': y_fit
                    }
                    self.wfile.write(json.dumps(response).encode('utf-8'))
                except ValueError as e:
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    response = {'status': 'error', 'message': str(e)}
                    self.wfile.write(json.dumps(response).encode('utf-8'))
                except Exception as e:
                    logging.error(f"Error in /api/data_fit: {str(e)}")
                    self.send_response(500)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    response = {'status': 'error', 'message': str(e)}
                    self.wfile.write(json.dumps(response).encode('utf-8'))

            elif path == '/api/ssh/ping':
                ping_body = ssh_ping_handshake(data)
                self.send_response(200)
                self.send_header('Content-type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps(ping_body, ensure_ascii=False).encode('utf-8'))

            elif path == '/api/terminal_reachable':
                host = (data.get('host') or '').strip()
                port = data.get('port', 22)
                try:
                    timeout = float(data.get('timeout', 3))
                except (TypeError, ValueError):
                    timeout = 3.0
                timeout = max(0.5, min(timeout, 15.0))
                reachable, detail = check_terminal_host_tcp(host, port, timeout=timeout)
                self.send_response(200)
                self.send_header('Content-type', 'application/json; charset=utf-8')
                self.end_headers()
                body = {'ok': True, 'reachable': reachable}
                body.update(detail)
                self.wfile.write(json.dumps(body, ensure_ascii=False).encode('utf-8'))
                
            else:
                self.send_response(404)
                self.end_headers()
                
        except Exception as e:
            logging.error(f"Error processing request: {str(e)}")
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            error_response = {'status': 'error', 'message': str(e)}
            self.wfile.write(json.dumps(error_response).encode('utf-8'))

    def do_PUT(self):
        path = self.parse_path()
        if path != '/data_input/review':
            self.send_response(404)
            self.end_headers()
            return
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length > 0:
                body = self.rfile.read(content_length)
                data = json.loads(body.decode('utf-8'))
            else:
                data = {}
            admin_user = (data.get('admin_user') or '').strip()
            if admin_user != 'admin':
                self.send_response(403)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'message': '需要管理员'}).encode('utf-8'))
                return
            app_id = data.get('id')
            action = (data.get('action') or '').strip().lower()
            target_db = (data.get('target_db') or '').strip()
            if not app_id or action not in ('approve', 'reject'):
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'message': '参数错误'}).encode('utf-8'))
                return
            global _data_input_applications
            _load_data_input_applications()
            app = next((a for a in _data_input_applications if a.get('id') == app_id), None)
            if not app or app.get('status') != 'pending':
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'message': '申请不存在或已处理'}).encode('utf-8'))
                return
            import time
            if action == 'reject':
                app['status'] = 'rejected'
                app['reviewed_at'] = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
                _save_data_input_applications()
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': True, 'message': '已拒绝'}).encode('utf-8'))
                return
            if action == 'approve':
                if target_db not in ('element_inf', 'materials'):
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'success': False, 'message': '请选择目标数据库：element_inf 或 materials'}).encode('utf-8'))
                    return
                err = data_input_insert_to_db(app.get('data') or {}, target_db)
                if err:
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'success': False, 'message': '写入数据库失败: ' + str(err)}).encode('utf-8'))
                    return
                app['status'] = 'approved'
                app['target_db'] = target_db
                app['reviewed_at'] = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
                _save_data_input_applications()
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': True, 'message': '已通过并写入 ' + target_db}).encode('utf-8'))
        except Exception as e:
            logging.exception("data_input/review: %s", e)
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'success': False, 'message': str(e)}).encode('utf-8'))

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

#运算行为
class CustomError(Exception):
    def __init__(self, message="This is a custom error."):
        self.message = message
        super().__init__(self.message)

def read_csv_to_list(file_path):
    data_list = []
    with open(file_path, mode='r', encoding='utf-8') as csvfile:
        content = csvfile.read().replace('\n', '\n')  # 将换行符替换为可视化的字符
        csv_reader = csv.reader(content.splitlines())
        for row in csv_reader:
            data_list.append(row)  # 将每一行添加到列表中
    return data_list

# 定义跨平台的错误处理函数
def show_error_message(message, title="错误"):
    if platform.system() == 'Windows':
        try:
            import win32api
            import win32con
            win32api.MessageBox(0, message, title, win32con.MB_OK)
        except ImportError:
            logging.error(f"{title}: {message}")
    else:
        logging.error(f"{title}: {message}")
        print(f"\n错误: {message}", file=sys.stderr)

def get_data(element, num_element):
    try:
        logging.info("==================== 开始获取数据 ====================")
        logging.info(f"请求元素: {element}, 元素数量: {num_element}")
        
        with MPRester("ROFXH1OkrD7GvcFFOasGetGk0asrzOE4") as mpr:
            # 将元素转换为正确的格式
            if '-' in element:
                elements = element.split('-')
                # 处理类似 2U-Nb 的格式
                processed_elements = []
                for elem in elements:
                    # 检查是否有数字前缀
                    match = re.match(r'(\d*)([A-Za-z]+)', elem)
                    if match:
                        count, symbol = match.groups()
                        count = int(count) if count else 1
                        processed_elements.extend([symbol] * count)
                    else:
                        processed_elements.append(elem)
                chemsys = '-'.join(sorted(processed_elements))
            else:
                # 处理单个元素的情况
                match = re.match(r'(\d*)([A-Za-z]+)', element)
                if match:
                    count, symbol = match.groups()
                    count = int(count) if count else 1
                    chemsys = '-'.join([symbol] * count)
                else:
                    chemsys = element
                num_element = 1

            logging.info(f"处理后的化学式: {chemsys}")
            
            try:
                logging.info("正在查询 Materials Project API...")
                # 使用 materials.summary.search 方法
                docs = mpr.materials.summary.search(
                    chemsys=[chemsys],
                    fields=[
                        "material_id",
                        "formula_pretty",
                        "volume",
                        "density",
                        "formation_energy_per_atom",
                        "band_gap",
                        "total_magnetization",
                        "nsites",
                        "symmetry",
                        "energy_above_hull",
                        "is_stable",
                        "is_metal",
                        "elements",
                        "nelements",
                        "composition",
                        "structure",
                        "bulk_modulus",
                        "shear_modulus"
                    ]
                )
                logging.info(f"API查询完成，获取到 {len(docs)} 条记录")
            except Exception as api_error:
                logging.error(f"MP-API请求失败: {str(api_error)}")
                return [f"MP-API请求失败: {str(api_error)}"]
            
            if not docs:
                logging.info("未找到相关数据")
                return ["未找到相关数据"]
            
            result_list = []
            for doc in docs:
                try:
                    logging.info(f"处理材料数据: {doc.material_id}")
                    result_list.append("Material ID: {}".format(doc.material_id))
                    result_list.append("化学式: {}".format(doc.formula_pretty))
                    if getattr(doc, "elements", None):
                        try:
                            elems_sorted = sorted(str(el) for el in doc.elements)
                            result_list.append("元素: {}".format(" ".join(elems_sorted)))
                        except Exception:
                            result_list.append("元素: {}".format(doc.elements))
                    if getattr(doc, "nelements", None) is not None:
                        result_list.append("元素种类数: {}".format(doc.nelements))
                    result_list.append("晶格温度: 0K")
                    
                    # 添加结构信息
                    if hasattr(doc, 'structure'):
                        logging.info(f"处理晶体结构数据...")
                        result_list.append("\n结构信息:")
                        # 获取晶格系统
                        if hasattr(doc, 'symmetry'):
                            crystal_system = doc.symmetry.crystal_system
                            result_list.append("晶体结构: {}".format(crystal_system))
                        else:
                            result_list.append("晶体结构: NONE DATA")
                        
                        # 获取晶格参数
                        try:
                            a = doc.structure.lattice.a
                            b = doc.structure.lattice.b
                            c = doc.structure.lattice.c
                            result_list.append("晶格参数: a={:.3f} b={:.3f} c={:.3f}".format(a, b, c))
                            logging.info(f"晶格参数: a={a:.3f}, b={b:.3f}, c={c:.3f}")
                            # 添加单独的晶格参数，方便前端解析
                            result_list.append("晶格常数a: {:.3f}".format(a))
                            result_list.append("晶格常数b: {:.3f}".format(b))
                            result_list.append("晶格常数c: {:.3f}".format(c))

                            # 添加原子位置信息
                            sites = doc.structure.sites
                            result_list.append("原子位置:")
                            positions = []
                            for i, site in enumerate(sites):
                                pos = site.coords
                                positions.append([float(pos[0]), float(pos[1]), float(pos[2])])
                                result_list.append("原子{}: [{:.3f}, {:.3f}, {:.3f}]".format(i, pos[0], pos[1], pos[2]))
                            
                            # 计算原子间连接
                            connections = []
                            for i in range(len(sites)):
                                for j in range(i + 1, len(sites)):
                                    dist = np.linalg.norm(np.array(positions[i]) - np.array(positions[j]))
                                    # 如果原子间距离小于晶格常数的1.5倍，认为它们之间有连接
                                    if dist < 1.5 * min(a, b, c):
                                        connections.append([i, j])
                            
                            # 添加连接信息
                            result_list.append("原子连接:")
                            for conn in connections:
                                result_list.append("连接: [{}, {}]".format(conn[0], conn[1]))

                        except Exception as e:
                            logging.error(f"获取晶格参数时出错: {str(e)}")
                            result_list.append("晶格参数: NONE DATA")
                            result_list.append("晶格常数a: NONE DATA")
                            result_list.append("晶格常数b: NONE DATA")
                            result_list.append("晶格常数c: NONE DATA")
                    else:
                        logging.info("无晶体结构数据")
                        result_list.append("晶格参数: NONE DATA")
                    
                    # 添加弹性常数和杨氏模量
                    if hasattr(doc, 'bulk_modulus') and hasattr(doc, 'shear_modulus'):
                        logging.info("计算弹性常数和杨氏模量...")
                        try:
                            # 检查并获取体积模量
                            bulk_modulus = doc.bulk_modulus
                            if isinstance(bulk_modulus, dict):
                                logging.info("体积模量是字典类型，使用VRH平均值")
                                if 'vrh' in bulk_modulus and bulk_modulus['vrh'] is not None:
                                    bulk_modulus = bulk_modulus['vrh']
                                    logging.info(f"体积模量VRH值: {bulk_modulus}")
                                elif 'voigt' in bulk_modulus and bulk_modulus['voigt'] is not None:
                                    bulk_modulus = bulk_modulus['voigt']
                                    logging.info(f"使用体积模量Voigt值: {bulk_modulus}")
                                else:
                                    logging.warning("未找到有效的体积模量值")
                                    bulk_modulus = None

                            # 检查并获取剪切模量
                            shear_modulus = doc.shear_modulus
                            if isinstance(shear_modulus, dict):
                                logging.info("剪切模量是字典类型，使用VRH平均值")
                                if 'vrh' in shear_modulus and shear_modulus['vrh'] is not None:
                                    shear_modulus = shear_modulus['vrh']
                                    logging.info(f"剪切模量VRH值: {shear_modulus}")
                                elif 'voigt' in shear_modulus and shear_modulus['voigt'] is not None:
                                    shear_modulus = shear_modulus['voigt']
                                    logging.info(f"使用剪切模量Voigt值: {shear_modulus}")
                                else:
                                    logging.warning("未找到有效的剪切模量值")
                                    shear_modulus = None

                            # 确保值不为None且可以转换为浮点数
                            if bulk_modulus is not None and shear_modulus is not None:
                                try:
                                    bulk_modulus = float(bulk_modulus)
                                    shear_modulus = float(shear_modulus)
                                    
                                    if bulk_modulus > 0 and shear_modulus > 0:
                                        # 计算C11和C12
                                        c11 = bulk_modulus + 4 * shear_modulus / 3
                                        c12 = bulk_modulus - 2 * shear_modulus / 3
                                        result_list.append("弹性刚度常数C11: {:.2f} GPa".format(c11))
                                        result_list.append("弹性刚度常数C12: {:.2f} GPa".format(c12))
                                        
                                        # 计算杨氏模量
                                        youngs_modulus = 9 * bulk_modulus * shear_modulus / (3 * bulk_modulus + shear_modulus)
                                        result_list.append("杨氏模量E-H: {:.2f} GPa".format(youngs_modulus))
                                        logging.info(f"计算完成 - C11: {c11:.2f}, C12: {c12:.2f}, E: {youngs_modulus:.2f}")
                                        
                                        # 添加原始模量值作为参考
                                        result_list.append("体积模量: {:.2f} GPa".format(bulk_modulus))
                                        result_list.append("剪切模量: {:.2f} GPa".format(shear_modulus))
                                    else:
                                        reason = []
                                        if bulk_modulus <= 0:
                                            reason.append(f"体积模量({bulk_modulus:.2f})")
                                        if shear_modulus <= 0:
                                            reason.append(f"剪切模量({shear_modulus:.2f})")
                                        logging.warning(f"以下模量小于等于0: {', '.join(reason)}")
                                        result_list.append("弹性刚度常数C11: NONE DATA (无效模量值)")
                                        result_list.append("弹性刚度常数C12: NONE DATA (无效模量值)")
                                        result_list.append("杨氏模量E-H: NONE DATA (无效模量值)")
                                except ValueError as ve:
                                    logging.error(f"转换为浮点数失败: {ve}")
                                    result_list.append("弹性刚度常数C11: NONE DATA (数值转换错误)")
                                    result_list.append("弹性刚度常数C12: NONE DATA (数值转换错误)")
                                    result_list.append("杨氏模量E-H: NONE DATA (数值转换错误)")
                            else:
                                logging.warning(f"体积模量({bulk_modulus})或剪切模量({shear_modulus})为None")
                                result_list.append("弹性刚度常数C11: NONE DATA (缺少模量数据)")
                                result_list.append("弹性刚度常数C12: NONE DATA (缺少模量数据)")
                                result_list.append("杨氏模量E-H: NONE DATA (缺少模量数据)")
                        except Exception as e:
                            logging.error(f"计算弹性常数时出错: {str(e)}")
                            result_list.append("弹性刚度常数C11: NONE DATA (计算错误)")
                            result_list.append("弹性刚度常数C12: NONE DATA (计算错误)")
                            result_list.append("杨氏模量E-H: NONE DATA (计算错误)")
                    else:
                        logging.info("无弹性数据")
                        result_list.append("弹性刚度常数C11: NONE DATA (无数据)")
                        result_list.append("弹性刚度常数C12: NONE DATA (无数据)")
                        result_list.append("杨氏模量E-H: NONE DATA (无数据)")
                    
                    if hasattr(doc, 'formation_energy_per_atom'):
                        result_list.append("形成能: {:.3f} eV/atom".format(doc.formation_energy_per_atom))
                    else:
                        result_list.append("形成能: NONE DATA")
                    
                    if hasattr(doc, 'energy_above_hull'):
                        result_list.append("相对稳定性能量: {:.3f} eV/atom".format(doc.energy_above_hull))
                    else:
                        result_list.append("相对稳定性能量: NONE DATA")
                    
                    if hasattr(doc, 'is_stable'):
                        result_list.append("是否稳定: {}".format("是" if doc.is_stable else "否"))
                    else:
                        result_list.append("是否稳定: NONE DATA")
                    
                    if hasattr(doc, 'band_gap'):
                        result_list.append("能隙: {:.3f} eV".format(doc.band_gap))
                    else:
                        result_list.append("能隙: NONE DATA")
                    
                    if hasattr(doc, 'is_metal'):
                        result_list.append("是否为金属: {}".format("是" if doc.is_metal else "否"))
                    else:
                        result_list.append("是否为金属: NONE DATA")
                    
                    if hasattr(doc, 'total_magnetization'):
                        result_list.append("总磁矩: {:.2f} μB".format(doc.total_magnetization))
                    else:
                        result_list.append("总磁矩: NONE DATA")
                    
                    if hasattr(doc, 'symmetry'):
                        result_list.append("晶体结构: {}".format(doc.symmetry.crystal_system))
                        result_list.append("空间群: {}".format(doc.symmetry.symbol))
                        result_list.append("点群: {}".format(doc.symmetry.point_group))
                    else:
                        result_list.append("晶体结构: NONE DATA")
                        result_list.append("空间群: NONE DATA")
                        result_list.append("点群: NONE DATA")
                    
                    result_list.append("---")
                    logging.info(f"材料 {doc.material_id} 数据处理完成")
                except Exception as e:
                    logging.error(f"处理材料 {doc.material_id} 时发生错误: {str(e)}")
                    continue
            
            if result_list:
                result_list.append("当前查询: {} (元素数量: {})".format(element, num_element))
            logging.info("==================== 数据处理完成 ====================")
            return result_list if result_list else ["未找到相关数据"]
            
    except Exception as e:
        logging.error(f"获取数据时发生错误: {str(e)}")
        return ["获取数据时出错: {}".format(str(e))]


def _format_lattice_constant_from_db(value):
    """
    将 MySQL 晶格常数字段格式化为 MP-API 兼容格式 "a=X.XXX b=X.XXX c=X.XXX"
    参考 MP-API 的 structure.lattice.a/b/c 输出格式
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    s = str(value).strip()
    if not s:
        return None
    # 已是 a=X b=X c=X 格式
    match = re.match(r'a=([\d.]+)\s+b=([\d.]+)\s+c=([\d.]+)', s, re.I)
    if match:
        a, b, c = match.groups()
        return f"a={float(a):.3f} b={float(b):.3f} c={float(c):.3f}"
    # 尝试提取多个数字（逗号、空格、分号、×等分隔）
    nums = re.findall(r'[\d.]+', s)
    if len(nums) >= 3:
        a, b, c = float(nums[0]), float(nums[1]), float(nums[2])
        return f"a={a:.3f} b={b:.3f} c={c:.3f}"
    if len(nums) == 1:
        v = float(nums[0])
        return f"a={v:.3f} b={v:.3f} c={v:.3f}"
    return None


def data_in_mysql(element, selected):
    mydb = None
    mycursor = None
    specific_value = None
    db_meta = None
    try:
        try:
            mydb = mysql.connector.connect(
                host="localhost",
                user="py_server",
                password="123456",
                database="element",
                auth_plugin='mysql_native_password',
                unix_socket=os.path.expanduser('~/mysql/tmp/mysql.sock')
            )
        except Exception:
            mydb = mysql.connector.connect(
                host="localhost",
                user="py_server",
                password="123456",
                database="element",
                auth_plugin='mysql_native_password',
            )
        # 记录数据库连接成功
        logging.info("数据库连接成功。")
        selected = selected.split(",")  # 确保 selected 是一个列表
        selected = [c.strip() for c in selected if c.strip()]
        logging.info(selected)
        result = []

        mycursor = mydb.cursor()
        for i in range(len(selected)):  # 使用 len(selected) 确保循环次数正确
            col = selected[i]
            logging.info(i)
            query = f"SELECT `{col}` FROM element_inf WHERE 元素=%s"  # 使用 selected[i]
            logging.info(f"要执行的SQL查询语句:{query}，参数:{element}")
            mycursor.execute(query, (element,))  # 记录SQL查询语句执行完成
            result_row = mycursor.fetchone()  # 获取单行结果
            if result_row is not None:
                raw = result_row[0]
                if col == "晶格常数":
                    formatted = _format_lattice_constant_from_db(raw)
                    result.append(formatted if formatted is not None else raw)
                else:
                    result.append(raw)
            else:
                result.append(None)  # 如果没有结果，添加 None

        logging.info("SQL查询语句执行完成。")
        logging.info(result)

        # 记录数据库连接成功
        logging.info("数据库连接成功。")

        if result:
            specific_value = result
            db_meta = {"source": "element_inf", "formula": element, "timestamp": None}
        else:
            logging.warning(f"在数据库中未找到元素 {element} 的数据")
            db_meta = None
    except mysql.connector.Error as e:
        logging.error(f"MySQL连接错误: {e}")
        if e.errno == 2003:
            logging.error("请确保MySQL服务已启动且正在运行在端口3306上")
        db_meta = None
    except Exception as e:
        logging.error(f"数据库查询错误: {e}")
        db_meta = None
    finally:
        if mycursor:
            mycursor.close()
        if mydb and mydb.is_connected():
            mydb.close()
    return (specific_value, db_meta)


def _normalize_element_for_u_nb(element):
    """
    将前端元素字符串规范化为 u_nb_database.materials 可匹配的形式。
    返回 (query_type, u_pct, nb_pct, name_patterns)
    query_type: 'single_u' | 'single_nb' | 'compound'
    """
    s = (element or "").strip().upper()
    if not s:
        # 无元素信息时，不查询 u_nb_database
        return ("none", None, None, [])
    parts = re.split(r"[-–—\s]+", s)
    parts = [p.strip() for p in parts if p.strip()]
    # 解析数字前缀，如 2U -> U,2
    def parse_part(p):
        m = re.match(r"^(\d*)([A-Za-z]+)$", p.strip())
        if m:
            num, sym = m.groups()
            return (sym.upper(), int(num) if num else 1)
        return (p.upper(), 1)

    parsed = [parse_part(p) for p in parts]
    symbols = [x[0] for x in parsed]
    counts = [x[1] for x in parsed]

    # 仅针对 U / Nb 或 U-Nb 体系返回有效查询，其它元素一律不查 u_nb_database
    if len(symbols) == 1:
        if symbols[0] == "U":
            return ("single_u", 100.0, 0.0, ["U"])
        if symbols[0] == "NB":
            return ("single_nb", 0.0, 100.0, ["Nb"])
        # 其它单元素：交给 element_inf / MP 处理
        return ("none", None, None, [])
    if len(symbols) == 2:
        a, b = symbols[0], symbols[1]
        c1, c2 = counts[0], counts[1]
        if (a == "U" and b == "NB") or (a == "NB" and b == "U"):
            total = c1 + c2
            u_pct = round(100.0 * c1 / total, 2) if a == "U" else round(100.0 * c2 / total, 2)
            nb_pct = round(100.0 - u_pct, 2)
            names = []
            if a == "U":
                names.append("U" + (str(c1) if c1 > 1 else "") + "Nb" + (str(c2) if c2 > 1 else ""))
                names.append("Nb" + (str(c2) if c2 > 1 else "") + "U" + (str(c1) if c1 > 1 else ""))
            else:
                names.append("Nb" + (str(c1) if c1 > 1 else "") + "U" + (str(c2) if c2 > 1 else ""))
                names.append("U" + (str(c2) if c2 > 1 else "") + "Nb" + (str(c1) if c1 > 1 else ""))
            return ("compound", u_pct, nb_pct, names)
        # 其它二元体系（如 Li-Ca 等）不在 U-Nb 体系内
        return ("none", None, None, [])
    # 多元体系同样不查 u_nb_database
    return ("none", None, None, [])


def _space_group_no_to_crystal_system(no):
    """常见空间群编号到晶体结构类型的简单映射（与 MP-API 表述接近）"""
    if no is None:
        return None
    n = int(no)
    if n in (195, 198, 200, 201, 205, 206, 207, 208, 212, 213, 214, 215, 218, 219, 221, 222, 223, 224, 225, 226, 227, 228, 229):
        return "cubic"
    if 168 <= n <= 194:
        return "hexagonal"
    if 1 <= n <= 2:
        return "triclinic"
    if 3 <= n <= 15:
        return "monoclinic"
    if 16 <= n <= 74:
        return "orthorhombic"
    if 75 <= n <= 142:
        return "tetragonal"
    if 143 <= n <= 167:
        return "trigonal"
    return None


def _is_mp_data_source(src):
    """判断 data_source 是否来自 Materials Project（此类不展示数据来源）"""
    if not src or not isinstance(src, str):
        return False
    s = src.lower()
    return "materials project" in s or "materialsproject" in s or "mp-optimade" in s or "mp-" in s


def _derive_crystal_from_text(material_name, data_source):
    """从 material_name、data_source 文本中推断晶体结构，与 MP-API 的 symmetry.crystal_system 表述对齐"""
    texts = []
    if material_name:
        texts.append(str(material_name).lower())
    if data_source:
        texts.append(str(data_source).lower())
    combined = " ".join(texts)
    if not combined:
        return None
    if any(x in combined for x in ["monoclinic", "单斜"]):
        return "monoclinic"
    if any(x in combined for x in ["orthorhombic", "斜方", "cmcm", "pnma", "pmma"]):
        return "orthorhombic"
    if any(x in combined for x in ["tetragonal", "四方", "p4", "p42"]):
        return "tetragonal"
    if any(x in combined for x in ["hexagonal", "六方", "p6", "p6_3"]):
        return "hexagonal"
    if any(x in combined for x in ["trigonal", "三角", "r-3", "r3m"]):
        return "trigonal"
    if any(x in combined for x in ["cubic", "立方", "bcc", "fcc", "im-3m", "fm-3m", "体心"]):
        return "cubic"
    return None


def data_in_u_nb_materials(element, selected):
    """
    从 u_nb_database.materials 表查询多重化合物数据，与 MP-API 多材料格式对齐。
    返回 (None, None, db_materials)，db_materials 为列表，每项结构与 MP 材料一致。
    """
    mydb = None
    mycursor = None

    try:
        mydb = mysql.connector.connect(
            host="localhost",
            user="py_server",
            password="123456",
            database="u_nb_database",
            auth_plugin="mysql_native_password",
        )
        if not mydb.is_connected():
            return (None, None, None)
        mycursor = mydb.cursor(dictionary=True)
        query_type, u_pct, nb_pct, name_patterns = _normalize_element_for_u_nb(element)

        # 非 U/Nb 相关体系：直接跳过本地 materials 表查询
        if query_type == "none":
            logging.info("元素组合 %s 不属于 U-Nb 体系，跳过 u_nb_database.materials 查询", element)
            return (None, None, None)

        if query_type == "single_u":
            mycursor.execute(
                "SELECT id, material_name, u_at_pct, nb_at_pct, space_group_no, a, b, c, notes, created_at, data_source "
                "FROM materials WHERE material_name = %s OR (u_at_pct = 100 AND nb_at_pct = 0)",
                ("U",),
            )
        elif query_type == "single_nb":
            mycursor.execute(
                "SELECT id, material_name, u_at_pct, nb_at_pct, space_group_no, a, b, c, notes, created_at, data_source "
                "FROM materials WHERE material_name = %s OR (u_at_pct = 0 AND nb_at_pct = 100)",
                ("Nb",),
            )
        else:
            if u_pct is not None and nb_pct is not None:
                mycursor.execute(
                    "SELECT id, material_name, u_at_pct, nb_at_pct, space_group_no, a, b, c, notes, created_at, data_source "
                    "FROM materials WHERE (u_at_pct = %s AND nb_at_pct = %s) OR (material_name LIKE %s AND material_name LIKE %s)",
                    (float(u_pct), float(nb_pct), "%U%", "%Nb%"),
                )
            else:
                like_u = "%U%" if name_patterns else "%"
                like_nb = "%Nb%" if name_patterns else "%"
                mycursor.execute(
                    "SELECT id, material_name, u_at_pct, nb_at_pct, space_group_no, a, b, c, notes, created_at, data_source "
                    "FROM materials WHERE material_name LIKE %s AND material_name LIKE %s",
                    (like_u, like_nb),
                )
        rows = mycursor.fetchall()
        if not rows:
            logging.info("u_nb_database.materials 未匹配到: %s", element)
            return (None, None, None)

        db_materials = []
        for row in rows:
            result_map = {"晶体结构": None, "晶格常数": None, "弹性刚度常数C11": None, "弹性刚度常数C12": None, "杨氏模量E-H": None}
            space_group_no = row.get("space_group_no")
            result_map["晶体结构"] = _space_group_no_to_crystal_system(space_group_no)
            if result_map["晶体结构"] is None and row.get("notes"):
                notes = (row["notes"] or "").lower()
                if "im-3m" in notes or "fm-3m" in notes or "spacegroup_symbol" in notes and "cubic" in notes:
                    result_map["晶体结构"] = "cubic"
                elif "cmcm" in notes or "orthorhombic" in notes:
                    result_map["晶体结构"] = "orthorhombic"
                elif "p6" in notes or "hexagonal" in notes:
                    result_map["晶体结构"] = "hexagonal"
                elif "tetragonal" in notes or "p4" in notes:
                    result_map["晶体结构"] = "tetragonal"
                elif "monoclinic" in notes:
                    result_map["晶体结构"] = "monoclinic"
            if result_map["晶体结构"] is None:
                result_map["晶体结构"] = _derive_crystal_from_text(
                    row.get("material_name"), row.get("data_source")
                )

            a, b, c = row.get("a"), row.get("b"), row.get("c")
            if a is not None and b is not None and c is not None:
                result_map["晶格常数"] = f"a={float(a):.3f} b={float(b):.3f} c={float(c):.3f}"

            created_at = row.get("created_at")
            ts_str = created_at.strftime("%Y-%m-%d %H:%M") if created_at else None
            data_src = row.get("data_source")
            if isinstance(data_src, str) and len(data_src) > 200:
                data_src = data_src[:200] + "..."

            mat = {
                "id": "db-{}".format(row.get("id", len(db_materials))),
                "化学式": row.get("material_name", element),
                "formula_pretty": row.get("material_name", element),
                "晶体结构": result_map["晶体结构"],
                "晶格常数": result_map["晶格常数"],
                "弹性刚度常数C11": result_map["弹性刚度常数C11"],
                "弹性刚度常数C12": result_map["弹性刚度常数C12"],
                "杨氏模量E-H": result_map["杨氏模量E-H"],
                "source": "数据库",
                "positions": [],
                "connections": [],
                "elements": [],
                "晶格温度": None,
                "db_formula": row.get("material_name", element),
                "db_timestamp": ts_str,
                "data_source": data_src,
            }
            if result_map["晶格常数"]:
                lc = result_map["晶格常数"]
                m = re.match(r"a=([\d.]+)\s+b=([\d.]+)\s+c=([\d.]+)", lc, re.I)
                if m:
                    mat["晶格常数a"], mat["晶格常数b"], mat["晶格常数c"] = m.group(1), m.group(2), m.group(3)
            db_materials.append(mat)

        logging.info("u_nb_database.materials 查询到 %d 条", len(db_materials))
        return (None, None, db_materials)
    except mysql.connector.Error as e:
        logging.warning("u_nb_database 查询异常: %s", e)
        return (None, None, None)
    except Exception as e:
        logging.warning("u_nb_database 查询异常: %s", e)
        return (None, None, None)
    finally:
        if mycursor:
            mycursor.close()
        if mydb and mydb.is_connected():
            mydb.close()


def _to_json_serializable(obj):
    """将 Decimal、datetime、numpy 标量等转为 JSON 可序列化类型"""
    from decimal import Decimal
    from datetime import date, datetime
    if isinstance(obj, Decimal):
        return float(obj)
    try:
        import numpy as np
        if isinstance(obj, (np.integer, np.floating)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
    except (ImportError, TypeError, ValueError):
        pass
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _to_json_serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_json_serializable(x) for x in obj]
    return obj


def _page2_build_where(cols, q, fuzzy, case_sensitive, numeric_cols=None):
    """
    构建 WHERE 子句。数值列用 CAST 转为字符串再比较，避免 'fcc' 被转成 0 误匹配。
    numeric_cols: 数值类型列名集合，这些列用 CAST( col AS CHAR) 比较
    """
    numeric_cols = numeric_cols or set()
    conditions = []
    params = []
    for col in cols:
        safe_col = "`{}`".format(col.replace("`", "``"))
        if col in numeric_cols:
            col_expr = "CAST({} AS CHAR)".format(safe_col)
        else:
            col_expr = "BINARY {}".format(safe_col) if case_sensitive else safe_col
        if fuzzy:
            conditions.append("{} LIKE %s".format(col_expr))
            params.append("%{}%".format(q))
        else:
            conditions.append("{} = %s".format(col_expr))
            params.append(q)
    return " OR ".join(conditions), params


def page2_search_db(query, fuzzy=True, case_sensitive=False, search_in="name"):
    """
    Page2 检索：在 element_inf 和 materials 中搜索。
    query: 检索词
    fuzzy: True=模糊(LIKE %q%), False=精确(=)
    case_sensitive: 是否区分大小写
    search_in: 'name'=仅名称, 'property'=名称+性质/数字
    返回: { "elements": [...], "materials": [...] }
    """
    elements = []
    materials = []
    if not query or len(query) < 1:
        return {"elements": elements, "materials": materials}
    q = str(query).strip()
    # 1. element_inf
    try:
        try:
            mydb = mysql.connector.connect(
                host="localhost",
                user="py_server",
                password="123456",
                database="element",
                auth_plugin="mysql_native_password",
                unix_socket=os.path.expanduser("~/mysql/tmp/mysql.sock"),
            )
        except Exception:
            mydb = mysql.connector.connect(
                host="localhost",
                user="py_server",
                password="123456",
                database="element",
                auth_plugin="mysql_native_password",
            )
        if mydb.is_connected():
            cur = mydb.cursor(dictionary=True)
            if search_in == "name":
                elem_cols = ["元素"]
                elem_numeric = set()
            else:
                cur.execute("SHOW COLUMNS FROM element_inf")
                rows_cols = cur.fetchall()
                def _col_name(r):
                    return r["Field"] if isinstance(r, dict) else r[0]
                def _col_type(r):
                    return r.get("Type", r[1] if len(r) > 1 else "") if isinstance(r, dict) else (r[1] if len(r) > 1 else "")
                all_cols = [_col_name(r) for r in rows_cols if _col_name(r)]
                type_map = {_col_name(r): str(_col_type(r)).lower() for r in rows_cols if _col_name(r)}
                skip_types = ("blob", "geometry")
                elem_cols = [
                    c for c in all_cols
                    if not any(skip in type_map.get(c, "") for skip in skip_types)
                ]
                if not elem_cols:
                    elem_cols = ["元素", "晶体结构"]
                num_types = ("int", "decimal", "float", "double", "real", "numeric")
                elem_numeric = {c for c in elem_cols if any(t in type_map.get(c, "") for t in num_types)}
            where_clause, where_params = _page2_build_where(elem_cols, q, fuzzy, case_sensitive, elem_numeric)
            sql = "SELECT * FROM element_inf WHERE {}".format(where_clause)
            cur.execute(sql, where_params)
            rows = cur.fetchall()
            for r in rows:
                if r:
                    elements.append(_to_json_serializable(dict(r)))
            cur.close()
            mydb.close()
    except Exception as e:
        logging.warning("page2_search element_inf: %s", e)
    # 2. materials (u_nb_database)
    try:
        mydb = mysql.connector.connect(
            host="localhost",
            user="py_server",
            password="123456",
            database="u_nb_database",
            auth_plugin="mysql_native_password",
        )
        if mydb.is_connected():
            cur = mydb.cursor(dictionary=True)
            if search_in == "name":
                mat_cols = ["material_name"]
                mat_numeric = set()
            else:
                mat_cols = ["material_name", "u_at_pct", "nb_at_pct", "space_group_no", "a", "b", "c", "notes", "data_source"]
                mat_numeric = {"u_at_pct", "nb_at_pct", "space_group_no", "a", "b", "c"}
            where_clause, where_params = _page2_build_where(mat_cols, q, fuzzy, case_sensitive, mat_numeric)
            where_params.append(100)
            sql = "SELECT id, material_name, u_at_pct, nb_at_pct, space_group_no, a, b, c, notes, created_at, data_source FROM materials WHERE {} LIMIT %s".format(where_clause)
            cur.execute(sql, where_params)
            rows = cur.fetchall()
            for r in rows:
                if r:
                    materials.append(_to_json_serializable(dict(r)))
            cur.close()
            mydb.close()
    except Exception as e:
        logging.warning("page2_search materials: %s", e)

    # 3. Materials Project
    mp_materials = []
    try:
        mp_materials = page2_search_mp(q, fuzzy, case_sensitive, search_in)
    except Exception as e:
        logging.warning("page2_search mp: %s", e)

    materials.extend(mp_materials)
    return {"elements": elements, "materials": materials}


def page2_search_mp(query, fuzzy=True, case_sensitive=False, search_in="name"):
    """从 Materials Project API 检索，返回与 materials 表格式兼容的 dict 列表"""
    results = []
    if not query or len(query) < 1:
        return results
    q = str(query).strip().lower()
    q_cap = str(query).strip()[0].upper() + str(query).strip()[1:] if len(query) > 1 else str(query).strip().upper()
    limit = 50

    try:
        with MPRester("ROFXH1OkrD7GvcFFOasGetGk0asrzOE4") as mpr:
            crystal_map = {"fcc": "cubic", "bcc": "cubic", "立方": "cubic", "六方": "hexagonal", "四方": "tetragonal", "正交": "orthorhombic", "单斜": "monoclinic"}
            crystal_system = crystal_map.get(q) or (q if q in ("cubic", "hexagonal", "tetragonal", "orthorhombic", "monoclinic", "trigonal", "triclinic") else None)

            kwargs = {"chunk_size": 500, "limit": limit, "fields": ["material_id", "formula_pretty", "symmetry", "structure"]}
            docs = []

            if crystal_system and (search_in == "property" or search_in == "all"):
                try:
                    docs = list(mpr.materials.summary.search(symmetry__crystal_system=crystal_system, **kwargs))
                except (TypeError, AttributeError):
                    try:
                        docs = list(mpr.materials.summary.search(crystal_system=crystal_system, **kwargs))
                    except (TypeError, AttributeError):
                        pass

            if not docs:
                try:
                    docs = list(mpr.materials.summary.search(elements=[q_cap], **kwargs))
                except (TypeError, AttributeError, ValueError):
                    pass

            if not docs and len(q_cap) <= 3:
                try:
                    docs = list(mpr.materials.summary.search(formula=q_cap, **kwargs))
                except (TypeError, AttributeError):
                    pass

            for doc in docs[:limit]:
                try:
                    mid = getattr(doc, "material_id", None) or getattr(doc, "mpid", None)
                    formula = getattr(doc, "formula_pretty", "") or ""
                    sym = getattr(doc, "symmetry", None)
                    crystal = sym.crystal_system if sym and hasattr(sym, "crystal_system") else None
                    a = b = c = None
                    if hasattr(doc, "structure") and doc.structure and hasattr(doc.structure, "lattice"):
                        a = round(doc.structure.lattice.a, 5)
                        b = round(doc.structure.lattice.b, 5)
                        c = round(doc.structure.lattice.c, 5)
                    results.append(_to_json_serializable({
                        "id": "mp-{}".format(mid) if mid and not str(mid).startswith("mp-") else mid,
                        "material_name": formula,
                        "source": "Materials Project",
                        "晶体结构": crystal,
                        "data_source": "Materials Project (id={})".format(mid) if mid else "Materials Project",
                        "a": a, "b": b, "c": c,
                    }))
                except Exception as e:
                    logging.warning("page2_search_mp doc parse: %s", e)
    except Exception as e:
        logging.warning("page2_search_mp: %s", e)
    return results


def data_input_insert_to_db(data_dict, target_db):
    """
    将数据输入申请的数据写入本地 MySQL。
    target_db: 'element_inf' -> database element, table element_inf; 'materials' -> database u_nb_database, table materials.
    返回 None 成功，否则返回错误信息字符串。
    """
    if target_db == 'element_inf':
        database, table = 'element', 'element_inf'
    elif target_db == 'materials':
        database, table = 'u_nb_database', 'materials'
    else:
        return '未知目标库'
    try:
        try:
            mydb = mysql.connector.connect(
                host='localhost',
                user='py_server',
                password='123456',
                database=database,
                auth_plugin='mysql_native_password',
                unix_socket=os.path.expanduser('~/mysql/tmp/mysql.sock'),
            )
        except Exception:
            mydb = mysql.connector.connect(
                host='localhost',
                user='py_server',
                password='123456',
                database=database,
                auth_plugin='mysql_native_password',
            )
        cur = mydb.cursor(dictionary=True)
        cur.execute("SHOW COLUMNS FROM {}".format(table))
        rows = cur.fetchall()
        col_names = [r['Field'] if isinstance(r, dict) else r[0] for r in rows]
        cols = [c for c in col_names if c in data_dict and data_dict[c] not in (None, '')]
        if not cols:
            cur.close()
            mydb.close()
            return '没有可写入的字段'
        placeholders = ', '.join(['%s'] * len(cols))
        columns = ', '.join(['`{}`'.format(c) for c in cols])
        values = [data_dict[c] for c in cols]
        sql = "INSERT INTO {} ({}) VALUES ({})".format(table, columns, placeholders)
        cur.execute(sql, values)
        mydb.commit()
        cur.close()
        mydb.close()
        return None
    except Exception as e:
        logging.warning("data_input_insert_to_db: %s", e)
        return str(e)


def update_cell(database, table, column, condition, new_value):
    """
    更新 MySQL 数据库中指定单元格的数据。

    :param table: 表名称
    :param column: 要更新的列名
    :param condition: 更新条件（例如：元素='Ne'）
    :param new_value: 新的单元格值
    """
    try:
        # 连接到 MySQL 数据库
        connection = mysql.connector.connect(
            host='localhost',  # 数据库主机
            user='py_server',  # 数据库用户名
            password='123456',  # 数据库密码
            database=database,  # 数据库名称
            auth_plugin = 'mysql_native_password'
        )

        if connection.is_connected():
            cursor = connection.cursor()
            # 构建 SQL 更新语句
            sql_update_query = f"UPDATE {table} SET {column} = %s WHERE {condition}"
            cursor.execute(sql_update_query, (new_value,))
            connection.commit()  # 提交更改
            print(f"成功更新 {cursor.rowcount} 行数据。")

    except Error as e:
        print(f"错误: {e}")

    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()
            print("数据库连接已关闭。")
    # 示例调用
    # 确保在调用时，condition 的格式正确
    #update_cell("Element","element_inf","具体分类","元素='Ne'","None")

def create_lattice_picture(structure):
    lattice_points1 = []
    connections1 = []
    if structure == "bcc":
        # 创建BCC晶格结构
        a = 1  # 晶格常数
        bcc = BodyCenteredCubic(directions=[[1, 0, 0], [0, 1, 0], [0, 0, 1]],
                                size=(2, 2, 2),
                                symbol='Fe',
                                pbc=True)
            # 将BCC Lattice转换为Atoms对象
        positions = bcc.get_scaled_positions()  # 使用get_scaled_positions
        cell = bcc.cell
        numbers = bcc.numbers
        symbols = bcc.get_chemical_symbols()

        # 创建Atoms对象
        atoms = Atoms(symbols=symbols,
                      cell=cell,
                      scaled_positions=positions,  # 传递标度位置
                      pbc=True)

        nl = NeighborList([1.5 * a] * len(atoms), skin=0.3, bothways=True, self_interaction=False)
        nl.update(atoms)

        # 转换后的位置
        positions = atoms.get_positions()

        # 转换为numpy数组以方便操作
        lattice_points1 = np.array(positions)

        # 定义连线规则
        connections1 = [
            (2, 6), (0, 2), (4, 6),
            (0, 4), (0, 8), (2, 10),
            (6, 14), (4, 12), (8, 12),
            (12, 14), (10, 14), (8, 10)
        ]
    elif structure =="fcc":
        # 更新晶胞大小（a为新的晶格常数）
        a = 1.77  # 使用传入的晶格常数
        # 创建基础晶格节点
        lattice_points1 = [
            [0, 0, 0],
            [0, a, 0],
            [a, 0, 0],
            [0, 0, a],
            [a, a, 0],
            [0, a, a],
            [a, 0, a],
            [a, a, a],
        ]

        # 添加面心点
        face_centers = [
            [a / 2, a / 2, 0],
            [a / 2, 0, a / 2],
            [0, a / 2, a / 2],
            [a / 2, a / 2, a],
            [a / 2, a, a / 2],
            [a, a / 2, a / 2],
        ]

        lattice_points1.extend(face_centers)

        # 转换为numpy数组以方便操作
        lattice_points1 = np.array(lattice_points1)

        # 定义连线规则
        connections1 = [
            (0, 3), (0, 2), (0, 1),
            (1, 5), (1, 4), (2, 6),
            (2, 4), (6, 7), (3, 6),
            (3, 5), (5, 7), (4, 7)
        ]
    elif structure == "hcp":
        # 创建HCP结构
        a = 1  # 晶格常数
        hcp = HexagonalClosedPacked(symbol='Mg',
                                    latticeconstant={'a': 3.2, 'c/a': 1.633},
                                    size=(3, 3, 3))

        # 将HCP Lattice转换为Atoms对象
        positions = hcp.get_scaled_positions()  # 使用get_scaled_positions
        cell = hcp.cell
        numbers = hcp.numbers
        symbols = hcp.get_chemical_symbols()

        # 创建Atoms对象
        atoms = Atoms(symbols=symbols,
                      cell=cell,
                      scaled_positions=positions,  # 传递标度位置
                      pbc=True)

        # 删除指定索引的原子
        del atoms[35:53]
        del atoms[35]

        nl = NeighborList([1.5 * a] * len(atoms), skin=0.3, bothways=True, self_interaction=False)
        nl.update(atoms)

        # 转换后的位置
        positions = atoms.get_positions()

        # 转换为numpy数组以方便操作
        lattice_points1 = np.array(positions)

        # 定义连线规则
        connections1 = [
            (0, 2), (2, 10), (10, 16), (16, 14), (14, 6), (6, 0),
            (1, 3), (3, 9), (9, 1),
            (20, 28), (28, 34), (34, 32), (32, 24), (24, 18), (18, 20),
            (18, 0), (20, 2), (28, 10), (34, 16), (32, 14), (24, 6)
        ]

    print(lattice_points1,connections1)
    return {
        "points": lattice_points1.tolist(),  # 返回晶格点
        "connections": [list(conn) for conn in connections1]  # 确保返回的是列表
    }
import numpy as np

def create_stiffness_tensor(C11, C12, C44, C13, matrix_type):
    if matrix_type == 'C':
        # 创建C型刚度张量矩阵
        stiffness_tensor = np.array([
            [C11, C12, C12, 0, 0, 0],
            [C12, C11, C12, 0, 0, 0],
            [C12, C12, C11, 0, 0, 0],
            [0, 0, 0, C44, 0, 0],
            [0, 0, 0, 0, C44, 0],
            [0, 0, 0, 0, 0, C44]
        ])
    elif matrix_type == 'H':
        # 创建H型刚度张量矩阵
        stiffness_tensor = np.array([
            [C11, C12, C13, 0, 0, 0],
            [C12, C11, C13, 0, 0, 0],
            [C13, C13, C13, 0, 0, 0],
            [0, 0, 0, C44, 0, 0],
            [0, 0, 0, 0, C44, 0],
            [0, 0, 0, 0, 0, C44]
        ])
    else:
        raise ValueError("无效的矩阵类型。请输入 'C' 或 'H'。")
    
    return stiffness_tensor

def run_http_server():
    try:
        Handler = MyRequestHandler
        port = find_available_port(3569)
        with socketserver.TCPServer(("0.0.0.0", port), Handler) as httpd:
            print(f"HTTP服务器运行在端口 {port},http://localhost:{port}")
            print("Starting HTTP server...")
            httpd.serve_forever()
    except Exception as e:
        logging.error(f"HTTP服务器启动错误: {str(e)}")

if __name__ == "__main__":
    os.chdir(SERVER_ROOT)

    # 启动WebSocket服务器
    websocket_thread = threading.Thread(target=run_websocket_server, daemon=True)
    websocket_thread.start()
    
    # 启动HTTP服务器
    http_thread = threading.Thread(target=run_http_server)
    http_thread.start()

    # 启动 Rust 服务器（database/ 相对于 tsx-web-app/server）；Linux 无 Rust 时可跳过
    _rust_cwd = os.path.join(SERVER_ROOT, 'database')
    rust_proc = None
    _skip_rust = os.environ.get('TSX_SKIP_RUST_SERVER', '').strip().lower() in ('1', 'true', 'yes', 'on')
    if _skip_rust:
        logging.info('已跳过 Rust database 服务（环境变量 TSX_SKIP_RUST_SERVER）')
    else:
        _rust_release = os.path.join(_rust_cwd, 'target', 'release', 'database')
        _rust_debug = os.path.join(_rust_cwd, 'target', 'debug', 'database')
        if os.path.isfile(_rust_release):
            rust_proc = subprocess.Popen([_rust_release], cwd=_rust_cwd)
            logging.info('已启动 Rust database（release 二进制）: %s', _rust_release)
        elif os.path.isfile(_rust_debug):
            rust_proc = subprocess.Popen([_rust_debug], cwd=_rust_cwd)
            logging.info('已启动 Rust database（debug 二进制）: %s', _rust_debug)
        elif shutil.which('cargo'):
            rust_proc = subprocess.Popen(["cargo", "run"], cwd=_rust_cwd)
            logging.info('已通过 cargo run 启动 Rust database（首次编译可能需数分钟）')
        else:
            logging.warning(
                '未找到 Rust database 可执行文件或 cargo，已跳过（'
                '在 database/ 下执行 cargo build --release，或安装 Rust 并加入 PATH）'
            )

    try:
        # 保持主线程运行
        websocket_thread.join()
        http_thread.join()
    except KeyboardInterrupt:
        print("\n正在关闭服务器...")
        sys.exit(0)
    finally:
        if rust_proc is not None:
            rust_proc.terminate()