# -*- coding: utf-8 -*-
"""
在独立子进程中运行 HTEM SAM（避免 pyserver 多线程下 os.chdir 干扰）。
用法: python sam_worker_cli.py <HTEM_ROOT> <Elasticity_T.dat> <output.npy>
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import traceback
from types import SimpleNamespace

import numpy as np

_BRIDGE_DIR = os.path.dirname(os.path.abspath(__file__))
if _BRIDGE_DIR not in sys.path:
    sys.path.insert(0, _BRIDGE_DIR)


def _patch_sam_no_plot(SAM):
    SAM.plot_results = lambda *a, **k: None
    SAM.plot_set_range = lambda *a, **k: None


def _parse_elasticity_t_model_dat(path: str) -> np.ndarray:
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


def main() -> int:
    if len(sys.argv) != 4:
        print('usage: sam_worker_cli.py HTEM_ROOT Elasticity_T.dat output.npy', file=sys.stderr)
        return 2

    htem_root = os.path.abspath(sys.argv[1])
    src_dat = os.path.abspath(sys.argv[2])
    out_npy = os.path.abspath(sys.argv[3])

    os.environ.setdefault('MPLBACKEND', 'Agg')
    os.environ.setdefault('MPLCONFIGDIR', '/tmp/matplotlib-calweb')
    os.makedirs(os.environ['MPLCONFIGDIR'], exist_ok=True)

    import matplotlib

    matplotlib.use('Agg')

    if not os.path.isdir(os.path.join(htem_root, 'source')):
        print(f'invalid HTEM_ROOT: {htem_root}', file=sys.stderr)
        return 1
    if not os.path.isfile(src_dat):
        print(f'missing input dat: {src_dat}', file=sys.stderr)
        return 1

    if htem_root not in sys.path:
        sys.path.insert(0, htem_root)

    from htem_loader import preload_sam_modules

    preload_sam_modules(htem_root)
    from source.elasticity import Elasticity
    from source.semi_analytic_model import SAM

    _patch_sam_no_plot(SAM)

    tmp = tempfile.mkdtemp(prefix='htem_sam_')
    try:
        shutil.copy(src_dat, os.path.join(tmp, 'Elasticity_T.dat'))
        os.chdir(tmp)

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

        sam = SAM()
        sam.model_elasticity(C, args, 'isothermal')

        out = os.path.join('figures', 'model', 'Elasticity_T_model.dat')
        if not os.path.isfile(out):
            raise FileNotFoundError('SAM 未生成 figures/model/Elasticity_T_model.dat')
        data = _parse_elasticity_t_model_dat(out)
        np.save(out_npy, data)
        return 0
    except Exception:
        traceback.print_exc(file=sys.stderr)
        return 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    raise SystemExit(main())
