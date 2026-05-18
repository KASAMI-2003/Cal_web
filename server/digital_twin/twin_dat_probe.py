# -*- coding: utf-8 -*-
"""
探测 .dat 输入：HTEM 温压网格表 vs 名义成分 + 弹性常数表（alloy_elastic 类）。
用于数字孪生前端决定 T / P / 成分 三轴是否可用。
"""
from __future__ import annotations

import io
import re
from typing import Any

import numpy as np
import pandas as pd


def _norm_name(s: str) -> str:
    return re.sub(r"\s+", "", str(s).strip().lower())


def _find_col(df: pd.DataFrame, *candidates: str) -> str | None:
    """列名匹配：仅规范化全等，避免 'P' 误匹配到含字母的无关列（如 Alloy、composition）。"""
    cmap = {_norm_name(c): c for c in df.columns}
    for cand in candidates:
        cn = _norm_name(cand)
        if cn in cmap:
            return cmap[cn]
    return None


def _read_htem_table(path_or_buf) -> pd.DataFrame:
    """HTEM example 格式：首行说明，次行表头，空白分隔。"""
    return pd.read_csv(path_or_buf, sep=r"\s+", engine="python", header=0, skiprows=[0])


def probe_htem_style(df: pd.DataFrame) -> dict[str, Any]:
    tcol = _find_col(df, "T(K)", "t(k)", "T")
    pcol = _find_col(df, "P(GPa)", "p(gpa)", "P")
    c11c = _find_col(df, "C11(GPa)", "c11", "C11")
    c12c = _find_col(df, "C12(GPa)", "c12", "C12")
    c44c = _find_col(df, "C44(GPa)", "c44", "C44")
    rhoc = _find_col(df, "rho(g/cm^3)", "rho", "rho(g/cm3)")

    if not tcol or not pcol or not c11c:
        return {"kind": "unknown", "error": "HTEM 样表缺少 T/P/C11 等列"}

    df2 = df.dropna(how="all").copy()
    for c in (tcol, pcol, c11c, c12c, c44c):
        if c and c in df2.columns:
            df2[c] = pd.to_numeric(df2[c], errors="coerce")
    df2 = df2.dropna(subset=[tcol, pcol, c11c])

    tuniq = np.unique(df2[tcol].values)
    puniq = np.unique(df2[pcol].values)
    has_t = len(tuniq) > 1
    has_p = len(puniq) > 1

    comp_col = _find_col(df2, "Alloy", "alloy", "Composition", "composition", "成分")
    has_comp = False
    n_comp = 0
    labels: list[str] = []
    if comp_col:
        lab = df2[comp_col].astype(str).str.strip()
        nu = lab.nunique()
        if nu > 1:
            has_comp = True
            n_comp = int(nu)
            labels = sorted(lab.unique().tolist())

    return {
        "kind": "htem_grid",
        "has_T": bool(has_t),
        "has_P": bool(has_p),
        "has_composition": has_comp,
        "T": {
            "detected": bool(has_t),
            "min": float(np.min(tuniq)),
            "max": float(np.max(tuniq)),
            "n_unique": int(len(tuniq)),
        },
        "P": {
            "detected": bool(has_p),
            "min": float(np.min(puniq)),
            "max": float(np.max(puniq)),
            "n_unique": int(len(puniq)),
        },
        "composition": {
            "detected": has_comp,
            "n": n_comp,
            "labels": labels,
            "field": comp_col,
        },
        "columns": {"T": tcol, "P": pcol, "C11": c11c, "C12": c12c, "C44": c44c, "rho": rhoc},
    }


def probe_alloy_table(df: pd.DataFrame) -> dict[str, Any]:
    alloy_col = _find_col(df, "Alloy", "alloy", "Composition", "composition")
    c11c = _find_col(df, "c11", "C11")
    c12c = _find_col(df, "c12", "C12")
    c44c = _find_col(df, "c44", "C44")
    if not alloy_col or not c11c or not c12c or not c44c:
        return {"kind": "unknown", "error": "成分表需含 Alloy（或成分列）及 c11、c12、c44"}

    tcol = _find_col(df, "T(K)", "t(k)", "T_K", "T")
    pcol = _find_col(df, "P(GPa)", "p(gpa)", "P_GPa", "P")
    rhoc = _find_col(df, "rho", "rho(g/cm^3)", "density")

    df2 = df.dropna(how="all").copy()
    n_rows = len(df2)
    if n_rows < 1:
        return {"kind": "unknown", "error": "无有效数据行"}

    has_t = False
    has_p = False
    t_info: dict[str, Any] = {"detected": False, "note": "未检测到 T（无温压列或仅单点）"}
    p_info: dict[str, Any] = {"detected": False, "note": "未检测到 P（无温压列或仅单点）"}
    if tcol and tcol in df2.columns:
        tv = pd.to_numeric(df2[tcol], errors="coerce").dropna()
        if len(tv) and tv.nunique() > 1:
            has_t = True
            t_info = {
                "detected": True,
                "min": float(tv.min()),
                "max": float(tv.max()),
                "n_unique": int(tv.nunique()),
            }
        elif len(tv):
            t_info = {
                "detected": False,
                "note": "T 列存在但仅单一取值，扫描 T 不可用",
                "min": float(tv.iloc[0]),
                "max": float(tv.iloc[0]),
            }
    if pcol and pcol in df2.columns:
        pv = pd.to_numeric(df2[pcol], errors="coerce").dropna()
        if len(pv) and pv.nunique() > 1:
            has_p = True
            p_info = {
                "detected": True,
                "min": float(pv.min()),
                "max": float(pv.max()),
                "n_unique": int(pv.nunique()),
            }
        elif len(pv):
            p_info = {
                "detected": False,
                "note": "P 列存在但仅单一取值",
                "min": float(pv.iloc[0]),
                "max": float(pv.iloc[0]),
            }

    labels = df2[alloy_col].astype(str).str.strip().tolist()
    return {
        "kind": "alloy_table",
        "has_T": has_t,
        "has_P": has_p,
        "has_composition": n_rows > 0,
        "T": t_info,
        "P": p_info,
        "composition": {
            "detected": True,
            "n": n_rows,
            "labels": labels,
            "field": alloy_col,
        },
        "columns": {
            "alloy": alloy_col,
            "c11": c11c,
            "c12": c12c,
            "c44": c44c,
            "T": tcol,
            "P": pcol,
            "rho": rhoc,
        },
    }


def probe_dat_path(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8", errors="ignore") as f:
        head = f.read(4096)
    if "T(K)" in head and "P(GPa)" in head and ("C11" in head or "c11" in head.lower()):
        try:
            df = _read_htem_table(path)
            return probe_htem_style(df)
        except Exception as e:
            return {"kind": "unknown", "error": f"解析 HTEM 表失败: {e}"}
    try:
        df = pd.read_csv(path, sep="\t", engine="python")
        if df.shape[1] < 4:
            df = pd.read_csv(path, sep=r"\s+", engine="python")
    except Exception as e:
        return {"kind": "unknown", "error": f"读取表格失败: {e}"}
    if _find_col(df, "Alloy", "alloy") and _find_col(df, "c11", "C11"):
        return probe_alloy_table(df)
    return {"kind": "unknown", "error": "无法识别：既不是 HTEM 温压网格也不是 Alloy+c11/c12/c44 表"}


def probe_dat_bytes(raw: bytes, filename: str = "") -> dict[str, Any]:
    buf = io.BytesIO(raw)
    head = raw[:4096].decode("utf-8", errors="ignore")
    if "T(K)" in head and "P(GPa)" in head:
        try:
            df = pd.read_csv(buf, sep=r"\s+", engine="python", header=0, skiprows=[0])
            return probe_htem_style(df)
        except Exception as e:
            return {"kind": "unknown", "error": f"解析 HTEM 表失败: {e}"}
    buf.seek(0)
    try:
        df = pd.read_csv(buf, sep="\t", engine="python")
        if df.shape[1] < 4:
            buf.seek(0)
            df = pd.read_csv(buf, sep=r"\s+", engine="python")
    except Exception as e:
        return {"kind": "unknown", "error": f"读取表格失败: {e}"}
    if _find_col(df, "Alloy", "alloy") and _find_col(df, "c11", "C11"):
        return probe_alloy_table(df)
    return {"kind": "unknown", "error": "无法识别文件格式"}


def load_alloy_rows(path: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """返回每行 {label,c11,c12,c44,rho?, B?, G?, E?, nu?} 与 probe 元数据。"""
    df = pd.read_csv(path, sep="\t", engine="python")
    df = df.dropna(how="all")
    meta = probe_alloy_table(df)
    if meta.get("kind") != "alloy_table":
        raise ValueError(meta.get("error", "不是 alloy_table"))
    c = meta["columns"]
    rows = []
    for _, r in df.iterrows():
        rho = 6.5
        if c.get("rho") and c["rho"] in df.columns and pd.notna(r.get(c["rho"])):
            rho = float(r[c["rho"]])
        rowd: dict[str, Any] = {
            "label": str(r[c["alloy"]]).strip(),
            "c11": float(r[c["c11"]]),
            "c12": float(r[c["c12"]]),
            "c44": float(r[c["c44"]]),
            "rho": rho,
        }
        for key, names in (
            ("B", ("B",)),
            ("G", ("G",)),
            ("E", ("E",)),
            ("nu", ("ν", "nu")),
        ):
            cc = _find_col(df, *names)
            if cc and cc in df.columns and pd.notna(r.get(cc)):
                rowd[key] = float(r[cc])
        rows.append(rowd)
    return rows, meta
