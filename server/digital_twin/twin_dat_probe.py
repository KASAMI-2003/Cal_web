# -*- coding: utf-8 -*-
"""
探测 .dat / .xlsx 等输入：HTEM 温压网格表 vs 名义成分 + 弹性常数表（alloy_elastic 类）。
用于数字孪生前端决定 T / P / 成分 三轴是否可用。
"""
from __future__ import annotations

import io
import os
import re
from typing import Any

import numpy as np
import pandas as pd

_EXCEL_EXTS = {".xlsx", ".xlsm", ".xls"}


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


def _is_excel_path(path: str) -> bool:
    return os.path.splitext(path or "")[1].lower() in _EXCEL_EXTS


def _is_excel_filename(filename: str) -> bool:
    return os.path.splitext(filename or "")[1].lower() in _EXCEL_EXTS


def _read_excel(source) -> pd.DataFrame:
    """读取 Excel；若首行不像表头则跳过首行（兼容 HTEM 首行说明）。"""
    df0 = pd.read_excel(source, engine="openpyxl", header=0)
    cols_join = " ".join(str(c) for c in df0.columns)
    if "T(K)" not in cols_join and _norm_name("T(K)") not in _norm_name(cols_join):
        if _find_col(df0, "Alloy", "alloy", "Composition", "composition", "成分") and _find_col(
            df0, "c11", "C11"
        ):
            return df0
        if hasattr(source, "seek"):
            source.seek(0)
        df1 = pd.read_excel(source, engine="openpyxl", header=1)
        return df1
    return df0


def _read_htem_table(path_or_buf) -> pd.DataFrame:
    """HTEM example 格式：首行说明，次行表头，空白分隔。"""
    return pd.read_csv(path_or_buf, sep=r"\s+", engine="python", header=0, skiprows=[0])


def _read_text_table_buf(buf: io.BytesIO) -> pd.DataFrame:
    buf.seek(0)
    try:
        df = pd.read_csv(buf, sep="\t", engine="python")
        if df.shape[1] < 4:
            buf.seek(0)
            df = pd.read_csv(buf, sep=r"\s+", engine="python")
    except Exception:
        buf.seek(0)
        df = pd.read_csv(buf, sep=r"\s+", engine="python")
    return df


def read_table_from_bytes(raw: bytes, filename: str = "") -> pd.DataFrame:
    if _is_excel_filename(filename):
        return _read_excel(io.BytesIO(raw))
    head = raw[:4096].decode("utf-8", errors="ignore")
    if "T(K)" in head and "P(GPa)" in head and ("C11" in head or "c11" in head.lower()):
        return _read_htem_table(io.BytesIO(raw))
    return _read_text_table_buf(io.BytesIO(raw))


def read_table_from_path(path: str) -> pd.DataFrame:
    if _is_excel_path(path):
        return _read_excel(path)
    with open(path, encoding="utf-8", errors="ignore") as f:
        head = f.read(4096)
    if "T(K)" in head and "P(GPa)" in head and ("C11" in head or "c11" in head.lower()):
        return _read_htem_table(path)
    try:
        df = pd.read_csv(path, sep="\t", engine="python")
        if df.shape[1] < 4:
            df = pd.read_csv(path, sep=r"\s+", engine="python")
    except Exception:
        df = pd.read_csv(path, sep=r"\s+", engine="python")
    return df


def _probe_dataframe(df: pd.DataFrame) -> dict[str, Any]:
    """先识别 HTEM 温压网格，再识别成分 + c_ij 表。"""
    tcol = _find_col(df, "T(K)", "t(k)", "T")
    pcol = _find_col(df, "P(GPa)", "p(gpa)", "P")
    c11_htem = _find_col(df, "C11(GPa)", "c11", "C11")
    if tcol and pcol and c11_htem:
        result = probe_htem_style(df)
        if result.get("kind") != "unknown":
            return result

    alloy_col = _find_col(df, "Alloy", "alloy", "Composition", "composition", "成分")
    if alloy_col and _find_col(df, "c11", "C11"):
        return probe_alloy_table(df)

    return {"kind": "unknown", "error": "无法识别：既不是 HTEM 温压网格也不是 Alloy+c11/c12/c44 表"}


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
    alloy_col = _find_col(df, "Alloy", "alloy", "Composition", "composition", "成分")
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
    try:
        df = read_table_from_path(path)
        return _probe_dataframe(df)
    except Exception as e:
        return {"kind": "unknown", "error": f"读取表格失败: {e}"}


def probe_dat_bytes(raw: bytes, filename: str = "") -> dict[str, Any]:
    try:
        df = read_table_from_bytes(raw, filename)
        return _probe_dataframe(df)
    except ImportError as e:
        return {"kind": "unknown", "error": f"缺少 Excel 依赖 openpyxl，请 pip install openpyxl: {e}"}
    except Exception as e:
        return {"kind": "unknown", "error": f"读取表格失败: {e}"}


def load_alloy_rows(path: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """返回每行 {label,c11,c12,c44,rho?, B?, G?, E?, nu?} 与 probe 元数据。"""
    df = read_table_from_path(path)
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


def export_htem_dat(src_path: str, dest_dat: str) -> str:
    """
    将 Excel/文本表格导出为 HTEM 可读的空格分隔 .dat（首行说明 + 表头 + 数据）。
    供上传 xlsx 且 kind=htem_grid 时供 SAM 使用。
    """
    df = read_table_from_path(src_path)
    meta = probe_htem_style(df)
    if meta.get("kind") != "htem_grid":
        raise ValueError(meta.get("error", "不是 HTEM 温压网格"))

    cols = meta["columns"]
    use_cols = [cols[k] for k in ("T", "P", "C11", "C12", "C44", "rho") if cols.get(k)]
    out_df = df[use_cols].dropna(how="all").copy()
    for c in use_cols:
        out_df[c] = pd.to_numeric(out_df[c], errors="coerce")
    out_df = out_df.dropna(subset=[cols["T"], cols["P"], cols["C11"]])

    os.makedirs(os.path.dirname(dest_dat) or ".", exist_ok=True)
    with open(dest_dat, "w", encoding="utf-8", newline="\n") as f:
        f.write("Exported from user upload (xlsx/csv)\n")
        header = "  ".join(str(c) for c in use_cols)
        f.write(header + "\n")
        for _, row in out_df.iterrows():
            f.write("  ".join(f"{float(row[c]):.6g}" for c in use_cols) + "\n")
    return dest_dat


def resolve_htem_dat_path(path: str) -> str:
    """HTEM SAM 仅接受 .dat；Excel 上传时按需导出旁路 .dat。"""
    if not path or not os.path.isfile(path):
        return path
    if not _is_excel_path(path):
        return path
    dest = os.path.splitext(path)[0] + "._htem_export.dat"
    if not os.path.isfile(dest) or os.path.getmtime(dest) < os.path.getmtime(path):
        export_htem_dat(path, dest)
    return dest
