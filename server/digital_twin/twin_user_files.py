# -*- coding: utf-8 -*-
"""
用户上传的孪生 .dat：落盘 + 注册表；按 twin_file id 取回路径与探测结果。
disk_path 在 JSON 中存为相对 server/ 的路径（POSIX 斜杠），便于跨平台迁移。
"""
from __future__ import annotations

import json
import os
import re
import secrets
import time
from typing import Any

from twin_dat_probe import load_alloy_rows, probe_dat_bytes

SERVER_ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
REGISTRY_PATH = os.path.join(SERVER_ROOT, "digital_twin_user_registry.json")
UPLOAD_ROOT = os.path.join(SERVER_ROOT, "user_twin_uploads")

_alloy_rows_cache: dict[str, list[dict[str, Any]]] = {}


def _safe_segment(s: str) -> str:
    return re.sub(r"[^\w\-\.]", "_", (s or "user")[:80])


def resolve_disk_path_for_entry(entry: dict[str, Any]) -> str | None:
    """
    将注册表中的 disk_path（相对 server/、绝对路径或旧版 Windows 路径）解析为当前机器上的绝对路径。
    """
    raw = (entry.get("disk_path") or "").strip()
    if not raw:
        return None

    n = os.path.normpath(raw.replace("\\", os.sep))
    if os.path.isabs(n) and os.path.isfile(n):
        return n

    rel = raw.replace("\\", "/").strip("/")
    cand = os.path.normpath(os.path.join(SERVER_ROOT, rel))
    if os.path.isfile(cand):
        return cand

    low = raw.replace("\\", "/").lower()
    marker = "user_twin_uploads/"
    if marker in low:
        idx = low.find(marker)
        tail = raw[idx:].replace("\\", "/")
        cand2 = os.path.normpath(os.path.join(SERVER_ROOT, *tail.split("/")))
        if os.path.isfile(cand2):
            return cand2

    user = _safe_segment((entry.get("username") or "").strip())
    base = os.path.basename(raw.replace("\\", os.sep))
    cand3 = os.path.normpath(os.path.join(UPLOAD_ROOT, user, base))
    if os.path.isfile(cand3):
        return cand3

    return None


def _portable_disk_path(abs_path: str) -> str:
    """写入注册表：相对 server/，统一为正斜杠。"""
    rel = os.path.relpath(abs_path, SERVER_ROOT)
    return rel.replace("\\", "/")


def _save_registry(data: dict[str, Any]) -> None:
    with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _load_registry() -> dict[str, Any]:
    if not os.path.isfile(REGISTRY_PATH):
        return {"files": []}
    try:
        with open(REGISTRY_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {"files": []}

    changed = False
    for e in data.get("files") or []:
        resolved = resolve_disk_path_for_entry(e)
        if not resolved:
            continue
        portable = _portable_disk_path(resolved)
        if e.get("disk_path") != portable:
            e["disk_path"] = portable
            changed = True

    if changed:
        try:
            _save_registry(data)
        except Exception:
            pass

    return data


def register_user_dat(username: str, raw: bytes, original_filename: str) -> dict[str, Any]:
    if not username or not username.strip():
        raise ValueError("需要用户名")
    probe = probe_dat_bytes(raw, original_filename)
    if probe.get("kind") == "unknown":
        raise ValueError(probe.get("error", "无法识别数据文件"))

    file_id = secrets.token_urlsafe(16)
    user_dir = os.path.join(UPLOAD_ROOT, _safe_segment(username.strip()))
    os.makedirs(user_dir, exist_ok=True)
    base = _safe_segment(os.path.basename(original_filename) or "upload.dat")
    if not base.lower().endswith(".dat"):
        base += ".dat"
    disk_name = f"{file_id[:10]}_{int(time.time())}_{base}"
    disk_path = os.path.join(user_dir, disk_name)
    with open(disk_path, "wb") as f:
        f.write(raw)

    entry = {
        "id": file_id,
        "username": username.strip(),
        "original_name": original_filename,
        "disk_path": _portable_disk_path(disk_path),
        "kind": probe["kind"],
        "probe": probe,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
    }
    reg = _load_registry()
    reg.setdefault("files", []).append(entry)
    _save_registry(reg)

    if probe["kind"] == "alloy_table":
        try:
            rows, _ = load_alloy_rows(disk_path)
            _alloy_rows_cache[file_id] = rows
        except Exception:
            _alloy_rows_cache.pop(file_id, None)
    return entry


def list_user_dats(username: str) -> list[dict[str, Any]]:
    reg = _load_registry()
    u = (username or "").strip()
    out = []
    for e in reg.get("files") or []:
        if e.get("username") == u:
            out.append(
                {
                    "id": e.get("id"),
                    "original_name": e.get("original_name"),
                    "kind": e.get("kind"),
                    "created_at": e.get("created_at"),
                }
            )
    return out


def get_entry(file_id: str, username: str | None) -> dict[str, Any] | None:
    reg = _load_registry()
    for e in reg.get("files") or []:
        if e.get("id") == file_id:
            if username and e.get("username") != username.strip():
                return None
            return e
    return None


def ensure_alloy_cache(file_id: str, entry: dict[str, Any]) -> list[dict[str, Any]]:
    if file_id in _alloy_rows_cache:
        return _alloy_rows_cache[file_id]
    path = resolve_disk_path_for_entry(entry)
    if not path:
        return []
    rows, _ = load_alloy_rows(path)
    _alloy_rows_cache[file_id] = rows
    return rows


def capabilities_for_file(entry: dict[str, Any] | None, default_sam_caps: dict[str, Any] | None) -> dict[str, Any]:
    """合并探测结果与前端需要的 T/P/成分 结构。"""
    if not entry:
        return default_sam_caps or {}

    p = entry.get("probe") or {}
    kind = entry.get("kind")
    cap = {
        "twin_file": entry.get("id"),
        "active_kind": kind,
        "original_name": entry.get("original_name"),
        "T": {
            "detected": bool(p.get("has_T")),
            "min": p.get("T", {}).get("min"),
            "max": p.get("T", {}).get("max"),
            "n_unique": p.get("T", {}).get("n_unique"),
            "note": p.get("T", {}).get("note"),
        },
        "P": {
            "detected": bool(p.get("has_P")),
            "min": p.get("P", {}).get("min"),
            "max": p.get("P", {}).get("max"),
            "n_unique": p.get("P", {}).get("n_unique"),
            "note": p.get("P", {}).get("note"),
        },
        "composition": {
            "detected": bool(p.get("has_composition")),
            "n": (p.get("composition") or {}).get("n", 0),
            "labels": (p.get("composition") or {}).get("labels") or [],
        },
    }
    if kind == "alloy_table":
        cap["note"] = (
            "成分为表中离散名义成分；未在表中出现的 T/P 维度显示为未检测到。"
            " 各向异性曲面由 c11、c12、c44（及默认或表内 rho）计算。"
        )
    elif kind == "htem_grid":
        cap["note"] = (
            "已切换 HTEM 温压网格输入（全站进程级生效至下次切换）。"
            " 请用侧栏 T、P 在文件网格范围内扫描。"
        )
    return cap


def default_capabilities_from_sam() -> dict[str, Any]:
    try:
        from htem_sam_bridge import get_sam_cache

        c = get_sam_cache()
        tg, pg = c["T_grid"], c["P_grid"]
        return {
            "twin_file": None,
            "active_kind": "htem_sam",
            "T": {
                "detected": True,
                "min": float(tg[0]),
                "max": float(tg[-1]),
                "n_unique": int(len(tg)),
            },
            "P": {
                "detected": True,
                "min": float(pg[0]),
                "max": float(pg[-1]),
                "n_unique": int(len(pg)),
            },
            "composition": {
                "detected": False,
                "n": 0,
                "labels": [],
                "note": "默认单材料；上传含成分列的表可启用成分轴",
            },
        }
    except Exception as e:
        return {
            "twin_file": None,
            "active_kind": "placeholder",
            "error": str(e),
            "T": {"detected": True, "min": 273.0, "max": 1200.0},
            "P": {"detected": True, "min": 0.0, "max": 20.0},
            "composition": {"detected": False, "n": 0, "labels": []},
        }


def apply_htem_session_for_entry(entry: dict[str, Any] | None) -> None:
    """上传的 htem_grid 激活时指向磁盘路径；alloy 或 None 则清掉覆盖用默认 SAM。"""
    from htem_sam_bridge import set_session_elasticity_dat

    if entry and entry.get("kind") == "htem_grid":
        path = resolve_disk_path_for_entry(entry)
        if path and os.path.isfile(path):
            set_session_elasticity_dat(path)
            return
    set_session_elasticity_dat(None)
