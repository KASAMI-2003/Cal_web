# -*- coding: utf-8 -*-
"""
按模块加载 HTEM source/*.py，跳过 source/__init__.py（其会 import anisotropy → imageio）。
Web/SAM 仅需 elasticity、semi_analytic_model、parameter 等，不需要 GIF 绘图栈。
"""
from __future__ import annotations

import importlib.util
import os
import sys
import types


def load_htem_submodule(htem_root: str, name: str):
    """加载 HTEM source/<name>.py 为 source.<name>，不执行 package __init__。"""
    htem_root = os.path.normpath(htem_root)
    src_dir = os.path.join(htem_root, 'source')
    path = os.path.join(src_dir, f'{name}.py')
    if not os.path.isfile(path):
        raise FileNotFoundError(path)

    if htem_root not in sys.path:
        sys.path.insert(0, htem_root)

    pkg_name = 'source'
    if pkg_name not in sys.modules:
        pkg = types.ModuleType(pkg_name)
        pkg.__path__ = [src_dir]  # type: ignore[attr-defined]
        sys.modules[pkg_name] = pkg

    mod_name = f'source.{name}'
    if mod_name in sys.modules:
        return sys.modules[mod_name]

    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(mod_name)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


def preload_sam_modules(htem_root: str):
    """SAM 运行所需的最小 HTEM 模块集合（按依赖顺序）。"""
    for name in ('parameter', 'write_output', 'elasticity', 'semi_analytic_model'):
        load_htem_submodule(htem_root, name)
