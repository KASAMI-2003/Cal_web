# -*- coding: utf-8 -*-
"""
HTEM SAM 桥接：在本地调用 digital_twin/HTEM-main 的半解析模型（不运行 VASP）。

默认使用官方示例：
  HTEM-main/example/5_Si_model/Elasticity_cold+NVT_s4.dat（立方 Si，cold+NVT 多温压点）
  参考温度 T_ref=0 K（与 SAM 中 T_ref≤5 分支一致）；平均原子质量取 Si。

可通过环境变量覆盖：
  HTEM_ELASTICITY_T  输入数据路径（Elasticity_T.dat 格式）
  HTEM_T_REF         参考温度 (K)，须与数据文件中某行 T 一致
  HTEM_LATTICE       晶系字母，如 C、H（与数据一致）
  HTEM_M             平均原子质量 (amu)

首次成功运行后会缓存 scipy 正则网格插值器，后续 API 仅做 O(1) 插值。
"""
from __future__ import annotations

import logging
import os
import shutil
import sys
import tempfile
import threading
from types import SimpleNamespace

import numpy as np

def _discover_htem_root() -> str | None:
    """优先 HTEM_ROOT 环境变量，其次与本文件同目录下的 HTEM-main，再次兼容旧布局（仓库根下 digital_twin/HTEM-main）。"""
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = []
    env = (os.environ.get('HTEM_ROOT') or '').strip()
    if env:
        candidates.append(env)
    candidates.append(os.path.join(here, 'HTEM-main'))
    candidates.append(os.path.normpath(os.path.join(here, '..', '..', 'digital_twin', 'HTEM-main')))
    # 与 tsx-web-app 同级的 WEB_FILE/digital_twin/HTEM-main（本地开发常见布局）
    candidates.append(os.path.normpath(os.path.join(here, '..', '..', '..', 'digital_twin', 'HTEM-main')))
    for p in candidates:
        if p and os.path.isdir(p) and os.path.isdir(os.path.join(p, 'source')):
            return os.path.normpath(p)
    return None


_HTEM_ROOT = _discover_htem_root()
_HTEM_SRC = os.path.join(_HTEM_ROOT, 'source') if _HTEM_ROOT else ''
# 默认：HTEM 官方示例（example/README），与手册中的 model 示例一致
_DEFAULT_EXAMPLE_ELASTICITY_T = (
    os.path.join(_HTEM_ROOT, 'example', '5_Si_model', 'Elasticity_cold+NVT_s4.dat') if _HTEM_ROOT else ''
)

_lock = threading.Lock()
_cache: dict | None = None
"""会话内覆盖 HTEM 输入路径（上传的温压网格 .dat）；None 表示用环境变量或默认 Si 示例。"""
_SESSION_ELASTICITY_DAT: str | None = None


def _active_elasticity_path() -> str:
    if _SESSION_ELASTICITY_DAT and os.path.isfile(_SESSION_ELASTICITY_DAT):
        return _SESSION_ELASTICITY_DAT
    return os.environ.get('HTEM_ELASTICITY_T', _DEFAULT_EXAMPLE_ELASTICITY_T)


def set_session_elasticity_dat(path: str | None):
    """
    设置当前 pyserver 进程使用的 Elasticity_T 格式输入；会清空 SAM 插值缓存。
    path 为 None 时恢复为 HTEM_ELASTICITY_T 环境变量或内置 Si 示例。
    注意：多用户共进程时以最后一次设置为准。
    """
    global _SESSION_ELASTICITY_DAT, _cache
    if path is not None and path != '' and not os.path.isfile(path):
        raise FileNotFoundError(path)
    _SESSION_ELASTICITY_DAT = path or None
    _cache = None


def clear_htem_cache():
    """更换 Elasticity_T.dat 或环境变量 HTEM_ELASTICITY_T 后调用，或重启 pyserver。"""
    global _cache
    _cache = None


def htem_available() -> bool:
    """HTEM 源码目录是否已就绪（供各向异性曲面等模块决定是否走 SAM/HTEM 路径）。"""
    return bool(_HTEM_ROOT)


def get_htem_status() -> dict:
    """供 /api/digital_twin/htem_status 与部署自检：HTEM 路径、默认 dat、SAM 缓存是否就绪。"""
    dat = _active_elasticity_path()
    out = {
        'htem_available': htem_available(),
        'htem_root': _HTEM_ROOT or '',
        'elasticity_dat': dat,
        'elasticity_dat_exists': bool(dat and os.path.isfile(dat)),
        'sam_cache_ready': _cache is not None,
    }
    if _cache is not None:
        out['sam_T_range'] = [float(_cache['T_grid'][0]), float(_cache['T_grid'][-1])]
        out['sam_P_range'] = [float(_cache['P_grid'][0]), float(_cache['P_grid'][-1])]
    return out


def warm_sam_cache():
    """首次 SAM 拟合约 10–30s；启动时预热可避免首帧曲面走 numpy 占位回退。"""
    if not htem_available():
        raise RuntimeError('HTEM 未安装')
    get_sam_cache()


def _ensure_htem_path():
    if not _HTEM_ROOT:
        raise RuntimeError(
            '未找到 HTEM-main：请将 HTEM 源码目录放在 digital_twin/HTEM-main，或设置环境变量 HTEM_ROOT'
        )
    if _HTEM_ROOT not in sys.path:
        sys.path.insert(0, _HTEM_ROOT)


def _patch_sam_no_plot(SAM):
    """SAM.model_elasticity 内部会调 matplotlib 出图；Web/API 场景下禁用绘图。"""
    SAM.plot_results = lambda *a, **k: None
    SAM.plot_set_range = lambda *a, **k: None


def _parse_elasticity_t_model_dat(path: str) -> np.ndarray:
    """
    解析 model_elasticity 写出的 figures/model/Elasticity_T_model.dat 中的网格表。
    表头行含 T(K)、P(GPa)、V、Cij、B、G、E。
    """
    with open(path, encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()
    start = None
    for i, line in enumerate(lines):
        if 'The modeled elastic constants and moduli are as follows:' in line:
            start = i + 2
            break
    if start is None:
        raise ValueError('未找到 SAM 网格表头（The modeled elastic constants...）')
    return np.loadtxt(lines[start:])


def _build_interpolators(data: np.ndarray):
    """
    data 列：0=T, 1=P, 2=V, 3-5=C11,C12,C44, 6=B, 7=G, 8=E
    SAM 输出按 T 外层、P 内层循环，可 reshape 为 len(Tu)×len(Pu)。
    """
    from scipy.interpolate import RegularGridInterpolator

    tu = np.unique(data[:, 0])
    pu = np.unique(data[:, 1])
    nt, npt = len(tu), len(pu)
    if data.shape[0] != nt * npt:
        raise ValueError(f'网格行数 {data.shape[0]} 与 {nt}×{npt} 不一致')

    def reshape_col(col_idx: int):
        z = data[:, col_idx].reshape(nt, npt)
        return RegularGridInterpolator(
            (tu, pu),
            z,
            bounds_error=False,
            fill_value=None,
        )

    interp_V = reshape_col(2)
    # 参考体积取 (300K, 0 GPa)，与前端滑块常用温度区间一致，便于解释 V/V₀
    v0 = float(interp_V(np.array([300.0, 0.0])))
    if v0 <= 0:
        v0 = float(data[0, 2])
    return {
        'T_grid': tu,
        'P_grid': pu,
        'interp_C11': reshape_col(3),
        'interp_C12': reshape_col(4),
        'interp_C44': reshape_col(5),
        'interp_B': reshape_col(6),
        'interp_G': reshape_col(7),
        'interp_E': reshape_col(8),
        'interp_V': interp_V,
        'V0_ref': v0,
        'source_dat': _active_elasticity_path(),
    }


def _run_sam_once():
    """在临时目录中运行 SAM.model_elasticity，返回解析后的网格数组。"""
    import matplotlib

    matplotlib.use('Agg')
    _ensure_htem_path()
    from source.elasticity import Elasticity
    from source.semi_analytic_model import SAM

    src_dat = _active_elasticity_path()
    if not os.path.isfile(src_dat):
        raise FileNotFoundError(f'缺少 HTEM 输入: {src_dat}')

    SAM_cls = SAM
    _patch_sam_no_plot(SAM_cls)

    cwd = os.getcwd()
    tmp = tempfile.mkdtemp(prefix='htem_sam_')
    try:
        os.chdir(tmp)
        shutil.copy(src_dat, 'Elasticity_T.dat')

        t_ref = float(os.environ.get('HTEM_T_REF', '0'))
        lattice = os.environ.get('HTEM_LATTICE', 'C').strip() or 'C'
        m_avg = float(os.environ.get('HTEM_M', '28.085'))

        args = SimpleNamespace(
            lattice=lattice,
            T_ref=t_ref,
            T_range=[273.0, 1200.0, 24],
            P_range=[0.0, 20.0, 20],
            weight=2.0,
            plt=None,
            M=m_avg,
        )
        with open('Elasticity_T.dat', encoding='utf-8', errors='ignore') as f:
            n_lines = len(f.readlines()) - 2
        C = {}
        for i in range(n_lines):
            C[i] = Elasticity()
            C[i].read_output('Elasticity_T.dat', args, i)

        sam = SAM_cls()
        sam.model_elasticity(C, args, 'isothermal')

        out = os.path.join('figures', 'model', 'Elasticity_T_model.dat')
        if not os.path.isfile(out):
            raise FileNotFoundError('SAM 未生成 figures/model/Elasticity_T_model.dat')
        return _parse_elasticity_t_model_dat(out)
    finally:
        os.chdir(cwd)
        shutil.rmtree(tmp, ignore_errors=True)


def get_sam_cache():
    """懒加载并缓存插值器；失败时抛出，由上层回退占位公式。"""
    global _cache
    if _cache is not None:
        return _cache
    with _lock:
        if _cache is not None:
            return _cache
        data = _run_sam_once()
        _cache = _build_interpolators(data)
        logging.info(
            'HTEM SAM 已初始化：网格 T=%s..%s (%d点), P=%s..%s (%d点)',
            _cache['T_grid'][0],
            _cache['T_grid'][-1],
            len(_cache['T_grid']),
            _cache['P_grid'][0],
            _cache['P_grid'][-1],
            len(_cache['P_grid']),
        )
        return _cache


def build_elasticity_at_tp(T_K: float, P_GPa: float):
    """
    在当前 (T,P) 用 SAM 插值得到 C11,C12,C44,V,rho，构造 HTEM Elasticity 对象（含 C、S、Fedorov 柔度）。
    供各向异性曲面 / Christoffel 声速计算使用。
    """
    _ensure_htem_path()
    from source.elasticity import Elasticity
    from source.parameter import Basic_para

    c = get_sam_cache()
    t = float(np.clip(T_K, 273.0, 2000.0))
    p = float(np.clip(P_GPa, 0.0, 50.0))
    pt = np.array([t, p])
    V = float(c['interp_V'](pt))
    c11 = float(c['interp_C11'](pt))
    c12 = float(c['interp_C12'](pt))
    c44 = float(c['interp_C44'](pt))
    m_avg = float(os.environ.get('HTEM_M', '28.085'))
    Na = Basic_para().Na
    rho = m_avg / (V * Na / 1e24)
    lattice = os.environ.get('HTEM_LATTICE', 'C').strip() or 'C'
    row = np.array([t, V, p, rho, c11, c12, c44], dtype=float)
    E = Elasticity()
    E.T = t
    E.P = p
    E.V = V
    E.rho = rho
    E.C_matrix = E.format_Cij(lattice, row)
    E.S_matrix = np.linalg.inv(E.C_matrix)
    E.init_Fedorov_matrix()
    return E


def twin_properties_htem(T_K: float, P_GPa: float) -> dict:
    """
    使用 HTEM SAM 在 (T,P) 处插值 B、G、E、V，并给出相对体积 V/V₀（V₀ 为 300K、0GPa 处的插值体积）。
    """
    c = get_sam_cache()
    t = float(np.clip(T_K, 273.0, 2000.0))
    p = float(np.clip(P_GPa, 0.0, 50.0))
    pt = np.array([t, p])

    B = float(c['interp_B'](pt))
    G = float(c['interp_G'](pt))
    E = float(c['interp_E'](pt))
    V = float(c['interp_V'](pt))
    v0 = c['V0_ref'] if c['V0_ref'] > 0 else 1.0
    volume_scale = V / v0

    base = os.path.splitext(os.path.basename(_active_elasticity_path()))[0]
    return {
        'T_K': round(t, 2),
        'P_GPa': round(p, 3),
        'bulk_modulus_GPa': round(B, 2),
        'shear_modulus_GPa': round(G, 2),
        'young_modulus_GPa': round(E, 2),
        'volume_scale': round(volume_scale, 5),
        'model': f'HTEM_SAM:{base}',
    }
