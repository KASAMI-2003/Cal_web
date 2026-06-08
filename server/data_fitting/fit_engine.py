"""曲线拟合与系数协方差 / 标准误差估计。"""

from __future__ import annotations

from typing import Any

import numpy as np
from scipy.optimize import curve_fit

from .fit_funcs import exponential, logarithmic, polynomialFit, sine
from .fit_tools import get_fit_funcs


def _r_squared(y: np.ndarray, y_pred: np.ndarray) -> float:
    ss_res = float(np.sum((y - y_pred) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    return float(1 - ss_res / ss_tot) if ss_tot != 0 else 0.0


def _rmse(y: np.ndarray, y_pred: np.ndarray, dof: int) -> float:
    if len(y) <= 0:
        return 0.0
    ss_res = float(np.sum((y - y_pred) ** 2))
    denom = max(dof, 1)
    return float(np.sqrt(ss_res / denom))


def _ols_covariance(x: np.ndarray, y: np.ndarray, degree: int, coeffs: list[float]) -> dict[str, Any]:
    n = len(x)
    dof = max(n - degree - 1, 1)
    y_pred = np.polyval(coeffs, x)
    rmse = _rmse(y, y_pred, dof)
    design = np.vander(x.astype(float), degree + 1)
    try:
        cov = (rmse**2) * np.linalg.inv(design.T @ design)
        stderr = np.sqrt(np.maximum(np.diag(cov), 0.0))
        return {
            'rmse': rmse,
            'coeff_stderr': [float(v) for v in stderr],
            'covariance_matrix': [[float(v) for v in row] for row in cov],
        }
    except np.linalg.LinAlgError:
        return {
            'rmse': rmse,
            'coeff_stderr': None,
            'covariance_matrix': None,
            'uncertainty_note': '设计矩阵奇异，无法估计协方差',
        }


def _nonlinear_covariance(
    model,
    x: np.ndarray,
    y: np.ndarray,
    p0: list[float] | None = None,
) -> tuple[list[float], dict[str, Any]]:
    kwargs: dict[str, Any] = {}
    if p0 is not None:
        kwargs['p0'] = p0
    popt, pcov = curve_fit(model, x, y, **kwargs)
    y_pred = model(x, *popt)
    n_params = len(popt)
    dof = max(len(x) - n_params, 1)
    rmse = _rmse(y, y_pred, dof)
    try:
        stderr = np.sqrt(np.maximum(np.diag(pcov), 0.0))
        cov_list = [[float(v) for v in row] for row in pcov]
    except Exception:
        stderr = None
        cov_list = None
    return list(popt), {
        'rmse': rmse,
        'coeff_stderr': [float(v) for v in stderr] if stderr is not None else None,
        'covariance_matrix': cov_list,
    }


def run_fit(x_data: list[float], y_data: list[float], fit_type: str, degree: int = 2) -> dict[str, Any]:
    x = np.asarray(x_data, dtype=float)
    y = np.asarray(y_data, dtype=float)
    if len(x) != len(y) or len(x) < 1:
        raise ValueError('数据长度不匹配或数据为空')

    row_count = len(x)
    uncertainty: dict[str, Any] = {}

    if fit_type == 'Polynomial':
        if row_count <= degree:
            raise ValueError(f'数据点不足以支撑拟合{degree}次多项式')
        coeffs = polynomialFit(x.tolist(), y.tolist(), degree)
        coeffs_arr = np.asarray(coeffs, dtype=float)
        y_pred = np.polyval(coeffs_arr, x)
        uncertainty = _ols_covariance(x, y, degree, coeffs)
    elif fit_type == 'Exponential':
        if row_count < 2:
            raise ValueError('数据点不足以支撑拟合指数函数')
        coeffs, uncertainty = _nonlinear_covariance(exponential, x, y)
        y_pred = exponential(x, *coeffs)
    elif fit_type == 'Logarithmic':
        if row_count < 2:
            raise ValueError('数据点不足以支撑拟合对数函数')
        if np.any(x <= 0):
            raise ValueError('对数拟合要求 X 全部为正')
        coeffs, uncertainty = _nonlinear_covariance(logarithmic, x, y)
        y_pred = logarithmic(x, *coeffs)
    elif fit_type == 'Sine':
        if row_count < 3:
            raise ValueError('数据点不足以支撑拟合正弦函数')
        coeffs, uncertainty = _nonlinear_covariance(sine, x, y, p0=[1.0, 1.0, 0.0])
        y_pred = sine(x, *coeffs)
    else:
        raise ValueError('不支持的拟合类型')

    fit_func_str = get_fit_funcs(coeffs, fit_type)
    r_squared = _r_squared(y, y_pred)
    rmse = float(uncertainty.get('rmse', 0.0))

    x_min = float(np.min(x))
    x_max = float(np.max(x))
    x_fit = np.linspace(x_min, x_max, 100)
    if fit_type == 'Polynomial':
        y_fit = np.polyval(np.asarray(coeffs, dtype=float), x_fit)
    elif fit_type == 'Exponential':
        y_fit = exponential(x_fit, *coeffs)
    elif fit_type == 'Logarithmic':
        y_fit = logarithmic(x_fit, *coeffs)
    else:
        y_fit = sine(x_fit, *coeffs)

    return {
        'status': 'success',
        'fit_type': fit_type,
        'degree': degree if fit_type == 'Polynomial' else None,
        'fit_func': fit_func_str,
        'r_squared': round(r_squared, 6),
        'rmse': round(rmse, 8),
        'strain_fit_residual': round(rmse, 8),
        'coeffs': [float(c) for c in coeffs],
        'coeff_stderr': uncertainty.get('coeff_stderr'),
        'covariance_matrix': uncertainty.get('covariance_matrix'),
        'uncertainty_note': uncertainty.get('uncertainty_note'),
        'x_fit': x_fit.tolist(),
        'y_fit': y_fit.tolist(),
    }
