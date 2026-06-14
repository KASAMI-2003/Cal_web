# -*- coding: utf-8 -*-
"""
探测用户上传表格（.dat / .xlsx / .csv），识别数据类型并驱动数字孪生三轴。

支持的格式（按 `_probe_dataframe` 识别顺序）：
  1. htem_grid   — T(K)、P(GPa)、C11… 温压网格 → 切换 HTEM SAM 插值
  2. alloy_table (format=cij) — Alloy/wt% + c11/c12/c44 离散成分表
  3. alloy_table (format=moduli_hill) — wt% + phases + BH/GH/EH/nu_H 等 Hill 模量表
     → 经 crystal_systems 按晶系反推 c_ij，供 HTEM Fedorov 各向异性曲面

模量表列优先级（与 HTEM 输出习惯一致）：
  B/G/E/nu 优先 Hill 列（BH、GH、EH、nu_H），其次 Voigt/Reuss（BV/GV、BR/GR…）
  晶系：phases 含 fcc/bcc→立方，hcp→六方；也可显式 crystal_system / LC 列
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


def _import_crystal_systems():
    """延迟导入 crystal_systems，兼容包内相对导入与 pyserver 同目录导入。"""
    try:
        from . import crystal_systems as cs
        return cs
    except ImportError:
        import crystal_systems as cs
        return cs


def _cubic_cij_from_bulk_shear(B: float, G: float) -> tuple[float, float, float]:
    cs = _import_crystal_systems()
    cij = cs.cij_from_moduli_for_system('cubic', B, G)
    return cij['c11'], cij['c12'], cij['c44']


def _cubic_cij_from_E_nu(E: float, nu: float) -> tuple[float, float, float]:
    cs = _import_crystal_systems()
    cij = cs.cij_from_moduli_for_system('cubic', None, None, E=E, nu=nu)
    return cij['c11'], cij['c12'], cij['c44']


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
    """识别顺序：HTEM 温压网格 → c_ij 成分表 → wt% 模量成分表。"""
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
    识别 wt% + phases + Hill/Voigt/Reuss 模量成分表（format=moduli_hill）。

    典型表头：wt%, phases, BV, GV, BR, GR, BH, GH, Ev, nu_V, ER, nu_R, EH, nu_H, …

    可视化链路：
      探测 → load_alloy_rows → crystal_systems.enrich_alloy_row_from_moduli
      → anisotropy_surface.build_elasticity_state_from_row → E / nu_max / v_l 曲面

    注意：含 BV/BR/GV/GR 时做严格四式拟合；不自洽则上传/加载报错，不近似回退。
    仅 BH/GH 且无 VR 四列时，按各向同性立方处理（曲面为球）。
    """
    wt_col = _find_col(df, "wt%", "wt", "wt.%", "weight", "wtpercent")
    if not wt_col:
        return {"kind": "unknown", "error": "模量成分表需含 wt%（或 wt）列"}

    b_col = _find_col(df, "BH", "BV", "BR", "B")
    g_col = _find_col(df, "GH", "GV", "GR", "G")
    e_col = _find_col(df, "EH", "Ev", "ER", "E")
    nu_col = _find_col(df, "nu_H", "nu_V", "nu_R", "nu", "ν")
    phases_col = _find_col(df, "phases", "phase", "相")
    bv_col = _find_col(df, "BV")
    br_col = _find_col(df, "BR")
    gv_col = _find_col(df, "GV")
    gr_col = _find_col(df, "GR")

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
    crystal_col = _find_col(df, "crystal_system", "crystal", "symmetry", "LC", "晶系")
    inferred_systems: list[str] = []
    for _, r in df2.iterrows():
        ph = str(r[phases_col]).strip() if phases_col and pd.notna(r.get(phases_col)) else None
        explicit = str(r[crystal_col]).strip() if crystal_col and pd.notna(r.get(crystal_col)) else None
        cs = _import_crystal_systems()
        sid = cs.infer_crystal_system(ph, explicit)
        if sid not in inferred_systems:
            inferred_systems.append(sid)

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
            "crystal_system": crystal_col,
            "B": b_col,
            "G": g_col,
            "E": e_col,
            "nu": nu_col,
            "BV": bv_col,
            "BR": br_col,
            "GV": gv_col,
            "GR": gr_col,
            "format": "moduli_hill",
        },
        "crystal_systems": {
            "inferred": inferred_systems,
            "from_phases": bool(phases_col),
            "note": "各成分点按 phases/晶系列推断 HTEM 对称性；fcc/bcc→立方，hcp→六方。",
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
    """
    解析成分表每一行为 alloy_row，供 comp_index 选取与各向异性 API 使用。

    返回行字段（moduli_hill 经 enrich 后）：
      label, phases, crystal_system, htem_lc, crystal_display_zh, structure,
      c11…, B, G, E, nu, cij_source ('moduli_hill' | 'table_cij'), rho
    """
    cs = _import_crystal_systems()
    enrich_alloy_row_from_moduli = cs.enrich_alloy_row_from_moduli
    get_handler = cs.get_handler
    infer_crystal_system = cs.infer_crystal_system
    infer_structure = cs.infer_structure

    df = read_table_from_path(path)
    df = df.dropna(how="all")

    meta = probe_alloy_table(df)
    if meta.get("kind") == "unknown":
        meta = probe_moduli_table(df)
    if meta.get("kind") != "alloy_table":
        raise ValueError(meta.get("error", "不是 alloy_table"))

    c = meta["columns"]
    fmt = c.get("format") or "cij"
    crystal_col = _find_col(df, "crystal_system", "crystal", "symmetry", "LC", "晶系")
    phases_col = c.get("phases") or _find_col(df, "phases", "phase", "相")
    rows: list[dict[str, Any]] = []

    for _, r in df.iterrows():
        phases = str(r[phases_col]).strip() if phases_col and pd.notna(r.get(phases_col)) else None
        explicit_cs = str(r[crystal_col]).strip() if crystal_col and pd.notna(r.get(crystal_col)) else None

        if fmt == "moduli_hill":
            # 仅模量、无 c_ij：按 phases/晶系列选 handler，由 BH+GH 反推独立弹性常数
            label = _composition_label(r, c["alloy"], phases_col)
            B = _first_numeric(r, c.get("B"))
            G = _first_numeric(r, c.get("G"))
            E = _first_numeric(r, c.get("E"))
            nu = _first_numeric(r, c.get("nu"))

            base: dict[str, Any] = {"label": label, "phases": phases, "rho": 6.5}
            if B is not None:
                base["B"] = B
            if G is not None:
                base["G"] = G
            if E is not None:
                base["E"] = E
            if nu is not None:
                base["nu"] = nu
            for vr_key in ("BV", "BR", "GV", "GR"):
                vr_col = _find_col(df, vr_key) or c.get(vr_key)
                if vr_col:
                    v = _first_numeric(r, vr_col)
                    if v is not None:
                        base[vr_key] = v
            for extra_key, names in (("AVR", ("AVR",)), ("Au", ("Au", "AU"))):
                ec = _find_col(df, *names)
                if ec:
                    v = _first_numeric(r, ec)
                    if v is not None:
                        base[extra_key] = v
            if not ((B is not None and G is not None) or (E is not None and nu is not None)):
                continue
            try:
                rowd = enrich_alloy_row_from_moduli(
                    base,
                    phases=phases,
                    crystal_system=explicit_cs,
                )
            except Exception as exc:
                try:
                    from .crystal_systems.cubic_moduli import CijFitError
                except ImportError:
                    from crystal_systems.cubic_moduli import CijFitError
                if isinstance(exc, CijFitError):
                    raise ValueError(f'成分「{label}」: {exc}') from exc
                raise
            rows.append(rowd)
            continue

        rho = 6.5
        if c.get("rho") and c["rho"] in df.columns and pd.notna(r.get(c["rho"])):
            rho = float(r[c["rho"]])
        system = infer_crystal_system(phases, explicit_cs)
        rowd = {
            "label": str(r[c["alloy"]]).strip(),
            "c11": float(r[c["c11"]]),
            "c12": float(r[c["c12"]]),
            "c44": float(r[c["c44"]]),
            "rho": rho,
            "phases": phases,
            "crystal_system": system,
            "structure": infer_structure(phases),
            "cij_source": "table_cij",
        }
        if system == "hexagonal":
            for hk in ("c13", "c33"):
                hc = _find_col(df, hk.upper(), hk)
                if hc and pd.notna(r.get(hc)):
                    rowd[hk] = float(r[hc])
        handler = get_handler(system)
        rowd["htem_lc"] = handler.spec.htem_lc
        rowd["crystal_display_zh"] = handler.spec.display_zh
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
