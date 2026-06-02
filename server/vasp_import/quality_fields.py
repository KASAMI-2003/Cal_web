"""VASP 入库质量与收敛元数据（API / CLI / JSON 汇总表共用）。"""

from __future__ import annotations

from typing import Any

# API/CLI 英文字段名
QUALITY_FIELD_KEYS = (
    'strain_fit_residual',
    'k_convergence_tier',
    'calc_exp_deviation_label',
)

# 写入 element_inf 时的中文列名（表中有对应列时审核通过会入库）
QUALITY_DB_COLUMNS = {
    'strain_fit_residual': '应变拟合残差',
    'k_convergence_tier': 'k点收敛档位',
    'calc_exp_deviation_label': '计算—实验偏差标签',
}

# 请求体 / JSON 文件可接受的别名
_QUALITY_ALIASES: dict[str, tuple[str, ...]] = {
    'strain_fit_residual': (
        'strain_fit_residual',
        'strainFitResidual',
        'strain_fit_rmse',
        '应变拟合残差',
        '拟合残差',
    ),
    'k_convergence_tier': (
        'k_convergence_tier',
        'kConvergenceTier',
        'k_convergence_level',
        'k点收敛档位',
        'K点收敛档位',
        'k点收敛',
    ),
    'calc_exp_deviation_label': (
        'calc_exp_deviation_label',
        'calcExpDeviationLabel',
        'calc_exp_label',
        '计算—实验偏差标签',
        '计算-实验偏差标签',
        '计算实验偏差标签',
    ),
}


def _norm_value(raw: Any) -> str | None:
    if raw is None or raw == '':
        return None
    if isinstance(raw, (int, float)):
        return str(raw)
    text = str(raw).strip()
    return text or None


def extract_quality_fields(source: dict[str, Any] | None) -> dict[str, str]:
    """从 API 请求体或 elastic_import.json 根节点提取质量字段（已规范化键名）。"""
    if not source:
        return {}
    out: dict[str, str] = {}
    for canonical, aliases in _QUALITY_ALIASES.items():
        for key in aliases:
            if key not in source:
                continue
            val = _norm_value(source.get(key))
            if val is not None:
                out[canonical] = val
                break
    return out


def quality_fields_to_db(data: dict[str, str]) -> dict[str, str]:
    """转为 db_data 中文字段，供审核通过后写入 MySQL。"""
    db: dict[str, str] = {}
    for key, col in QUALITY_DB_COLUMNS.items():
        val = data.get(key)
        if val not in (None, ''):
            db[col] = str(val)
    return db
