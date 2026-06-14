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


def _looks_like_data_header(df: pd.DataFrame) -> bool:
    """判断首行是否已是有效表头（避免 Excel 误 skip 一行）。"""
    if _find_col(df, "T(K)", "t(k)"):
        return True
    if _find_col(df, "Alloy", "alloy", "Composition", "composition", "成分") and _find_col(
        df, "c11", "C11"
    ):
        return True
    if _find_col(df, "wt%", "wt", "wt.%") and (
        _find_col(df, "BH", "BV", "BR", "GH", "GV", "GR", "EH", "Ev", "ER")
    ):
        return True
    return False


def _read_excel(source) -> pd.DataFrame:
    """读取 Excel；若首行不像表头则跳过首行（兼容 HTEM 首行说明）。"""
    df0 = pd.read_excel(source, engine="openpyxl", header=0)
    if _looks_like_data_header(df0):
        return df0
    if hasattr(source, "seek"):
        source.seek(0)
    return pd.read_excel(source, engine="openpyxl", header=1)


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


def _cubic_cij_from_bulk_shear(B: float, G: float) -> tuple[float, float, float]:
    """由 Hill/Voigt 体模量 B、剪切模量 G 反推立方 c11/c12/c44（各向同性极限映射，供曲面渲染）。"""
    B, G = float(B), float(G)
    c12 = B - 2.0 * G / 3.0
    c11 = c12 + 2.0 * G
    c44 = G
    return c11, c12, c44


def _cubic_cij_from_E_nu(E: float, nu: float) -> tuple[float, float, float]:
    E, nu = float(E), float(nu)
    G = E / (2.0 * (1.0 + nu))
    B = E / (3.0 * (1.0 - 2.0 * nu))
    return _cubic_cij_from_bulk_shear(B, G)


def _first_numeric(row, col: str | None) -> float | None:
    if not col or col not in row.index:
        return None
    val = pd.to_numeric(row[col], errors="coerce")
    if pd.isna(val):
        return None
    return float(val)


def _composition_label(row, wt_col: str, phases_col: str | None) -> str:
    wt_raw = row[wt_col]
    if pd.isna(wt_raw):
        wt = ""
    else:
        wt = str(wt_raw).strip()
        if wt.endswith(".0") and wt.replace(".0", "").isdigit():
            wt = wt[:-2]
        if wt and not wt.endswith("%") and _norm_name(wt_col) in ("wt%", "wt.%"):
            try:
                float(wt)
                wt = f"{wt}%"
            except ValueError:
                pass
    if phases_col and phases_col in row.index and pd.notna(row.get(phases_col)):
        ph = str(row[phases_col]).strip()
        if ph and ph.lower() != "nan":
            return f"{wt} · {ph}" if wt else ph
    return wt or "row"


def _probe_dataframe(df: pd.DataFrame) -> dict[str, Any]:
    """先识别 HTEM 温压网格，再识别 c_ij 成分表，再识别 wt%+模量表。"""
    tcol = _find_col(df, "T(K)", "t(k)", "T")
    pcol = _find_col(df, "P(GPa)", "p(gpa)", "P")
    c11_htem = _find_col(df, "C11(GPa)", "c11", "C11")
    if tcol and pcol and c11_htem:
        result = probe_htem_style(df)
        if result.get("kind") != "unknown":
            return result

    result = probe_alloy_table(df)
    if result.get("kind") != "unknown":
        return result

    return probe_moduli_table(df)


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
            "format": "cij",
        },
    }


def probe_moduli_table(df: pd.DataFrame) -> dict[str, Any]:
    """
    HTEM / 高通量输出的 wt% + phases + B/G/E/nu（Hill/Voigt/Reuss）成分表。
    无 c11/c12/c44 时由 B、G（或 E、ν）反推立方 c_ij 供各向异性曲面。
    """
    wt_col = _find_col(df, "wt%", "wt", "wt.%", "weight", "wtpercent")
    if not wt_col:
        return {"kind": "unknown", "error": "模量成分表需含 wt%（或 wt）列"}

    b_col = _find_col(df, "BH", "BV", "BR", "B")
    g_col = _find_col(df, "GH", "GV", "GR", "G")
    e_col = _find_col(df, "EH", "Ev", "ER", "E")
    nu_col = _find_col(df, "nu_H", "nu_V", "nu_R", "nu", "ν")
    phases_col = _find_col(df, "phases", "phase", "相")

    if not b_col and not g_col and not (e_col and nu_col):
        return {
            "kind": "unknown",
            "error": "模量成分表需含 BH/GH（或 BV/GV、EH/nu_H 等）模量列",
        }

    df2 = df.dropna(how="all").copy()
    n_rows = len(df2)
    if n_rows < 1:
        return {"kind": "unknown", "error": "无有效数据行"}

    labels = [_composition_label(r, wt_col, phases_col) for _, r in df2.iterrows()]

    return {
        "kind": "alloy_table",
        "has_T": False,
        "has_P": False,
        "has_composition": n_rows > 0,
        "T": {"detected": False, "note": "未检测到 T（wt% 模量表为固定成分点）"},
        "P": {"detected": False, "note": "未检测到 P（wt% 模量表为固定成分点）"},
        "composition": {
            "detected": True,
            "n": n_rows,
            "labels": labels,
            "field": wt_col,
        },
        "columns": {
            "alloy": wt_col,
            "phases": phases_col,
            "B": b_col,
            "G": g_col,
            "E": e_col,
            "nu": nu_col,
            "format": "moduli_hill",
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
    if meta.get("kind") == "unknown":
        meta = probe_moduli_table(df)
    if meta.get("kind") != "alloy_table":
        raise ValueError(meta.get("error", "不是 alloy_table"))

    c = meta["columns"]
    fmt = c.get("format") or "cij"
    rows: list[dict[str, Any]] = []

    for _, r in df.iterrows():
        if fmt == "moduli_hill":
            label = _composition_label(r, c["alloy"], c.get("phases"))
            B = _first_numeric(r, c.get("B"))
            G = _first_numeric(r, c.get("G"))
            E = _first_numeric(r, c.get("E"))
            nu = _first_numeric(r, c.get("nu"))

            if B is not None and G is not None:
                c11, c12, c44 = _cubic_cij_from_bulk_shear(B, G)
            elif E is not None and nu is not None:
                c11, c12, c44 = _cubic_cij_from_E_nu(E, nu)
                if B is None:
                    B = E / (3.0 * (1.0 - 2.0 * nu))
                if G is None:
                    G = E / (2.0 * (1.0 + nu))
            else:
                continue

            rowd: dict[str, Any] = {
                "label": label,
                "c11": c11,
                "c12": c12,
                "c44": c44,
                "rho": 6.5,
            }
            if B is not None:
                rowd["B"] = B
            if G is not None:
                rowd["G"] = G
            if E is not None:
                rowd["E"] = E
            if nu is not None:
                rowd["nu"] = nu
            rows.append(rowd)
            continue

        rho = 6.5
        if c.get("rho") and c["rho"] in df.columns and pd.notna(r.get(c["rho"])):
            rho = float(r[c["rho"]])
        rowd = {
            "label": str(r[c["alloy"]]).strip(),
            "c11": float(r[c["c11"]]),
            "c12": float(r[c["c12"]]),
            "c44": float(r[c["c44"]]),
            "rho": rho,
        }
        for key, names in (
            ("B", ("B", "BH", "BV", "BR")),
            ("G", ("G", "GH", "GV", "GR")),
            ("E", ("E", "EH", "Ev", "ER")),
            ("nu", ("ν", "nu", "nu_H", "nu_V", "nu_R")),
        ):
            cc = _find_col(df, *names)
            if cc and cc in df.columns and pd.notna(r.get(cc)):
                rowd[key] = float(r[cc])
        rows.append(rowd)

    if not rows:
        raise ValueError("模量成分表无有效数据行（需 BH+GH 或 EH+nu_H 等）")
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
