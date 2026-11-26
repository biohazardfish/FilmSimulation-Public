from __future__ import annotations

from typing import Any

import numpy as np


VALID_STATUSES = {"pass", "fail", "not_evaluable"}
VALID_LEVELS = {"V1", "V2", "V3", "V4"}


def metric_record(
    metric_id: str,
    *,
    quantity: str,
    status: str,
    evidence_level: str,
    value: Any = None,
    unit: str | None = None,
    channel: str | None = None,
    reference: Any = None,
    independent: bool = False,
    conditions: dict[str, Any] | None = None,
    normalization: str | None = None,
    uncertainty: Any = None,
    reason: str | None = None,
) -> dict[str, Any]:
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid metric status: {status}")
    if evidence_level not in VALID_LEVELS:
        raise ValueError(f"invalid evidence level: {evidence_level}")
    return {
        "metric_id": metric_id,
        "quantity": quantity,
        "channel": channel,
        "value": value,
        "unit": unit,
        "status": status,
        "evidence_level": evidence_level,
        "reference": reference,
        "independent": bool(independent),
        "conditions": conditions or {},
        "normalization": normalization,
        "uncertainty": uncertainty,
        "reason": reason,
    }


def error_metrics(actual: np.ndarray, reference: np.ndarray) -> dict[str, float]:
    actual = np.asarray(actual, dtype=np.float64)
    reference = np.asarray(reference, dtype=np.float64)
    if actual.shape != reference.shape:
        raise ValueError(f"shape mismatch: {actual.shape} != {reference.shape}")
    finite = np.isfinite(actual) & np.isfinite(reference)
    if not finite.any():
        raise ValueError("no finite comparable samples")
    residual = actual[finite] - reference[finite]
    return {
        "rmse": float(np.sqrt(np.mean(residual**2))),
        "mae": float(np.mean(np.abs(residual))),
        "max_abs": float(np.max(np.abs(residual))),
        "finite_samples": int(finite.sum()),
    }


def monotonicity(values: np.ndarray, direction: str, atol: float = 1e-10) -> dict[str, Any]:
    values = np.asarray(values, dtype=np.float64)
    if values.ndim != 1 or values.size < 2:
        raise ValueError("monotonicity expects a 1-D array with at least two samples")
    delta = np.diff(values)
    if direction == "increasing":
        violations = delta < -atol
    elif direction == "decreasing":
        violations = delta > atol
    else:
        raise ValueError("direction must be increasing or decreasing")
    return {
        "direction": direction,
        "atol": float(atol),
        "violations": int(np.count_nonzero(violations)),
        "max_violation": float(np.max(np.where(violations, np.abs(delta), 0.0))),
        "pass": not bool(np.any(violations)),
    }


def straight_line_regions(x: np.ndarray, y: np.ndarray) -> dict[str, np.ndarray]:
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    if x.shape != y.shape:
        raise ValueError("x and y must have the same shape")
    low = float(np.nanmin(y))
    high = float(np.nanmax(y))
    span = high - low
    if not np.isfinite(span) or span <= 0:
        raise ValueError("curve has no finite density span")
    fraction = (y - low) / span
    return {
        "toe": fraction < 0.2,
        "straight": (fraction >= 0.2) & (fraction <= 0.8),
        "shoulder": fraction > 0.8,
    }


def curve_metrics(x: np.ndarray, y: np.ndarray, reference: np.ndarray | None = None) -> dict[str, Any]:
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    regions = straight_line_regions(x, y)
    straight = regions["straight"] & np.isfinite(x) & np.isfinite(y)
    if np.count_nonzero(straight) < 2:
        raise ValueError("fewer than two straight-line samples")
    slope, intercept = np.polyfit(x[straight], y[straight], 1)
    fitted = slope * x + intercept
    result: dict[str, Any] = {
        "d_min": float(np.nanmin(y)),
        "d_max": float(np.nanmax(y)),
        "density_span": float(np.nanmax(y) - np.nanmin(y)),
        "straight_line_gradient": float(slope),
        "straight_line_intercept": float(intercept),
        "straight_line_samples": int(np.count_nonzero(straight)),
        "toe_deviation_rmse_from_straight_line": float(
            np.sqrt(np.mean((y[regions["toe"]] - fitted[regions["toe"]]) ** 2))
        ),
        "shoulder_deviation_rmse_from_straight_line": float(
            np.sqrt(np.mean((y[regions["shoulder"]] - fitted[regions["shoulder"]]) ** 2))
        ),
    }
    if reference is not None:
        result["reference_error"] = error_metrics(y, reference)
    return result


def exposure_axis_offset(
    x: np.ndarray,
    actual: np.ndarray,
    reference_x: np.ndarray,
    reference_y: np.ndarray,
    search: tuple[float, float] = (-2.0, 2.0),
    steps: int = 4001,
) -> dict[str, float]:
    """Find the horizontal reference shift minimizing finite-sample RMSE."""
    x = np.asarray(x, dtype=np.float64)
    actual = np.asarray(actual, dtype=np.float64)
    reference_x = np.asarray(reference_x, dtype=np.float64)
    reference_y = np.asarray(reference_y, dtype=np.float64)
    shifts = np.linspace(search[0], search[1], steps)
    best_shift = 0.0
    best_rmse = np.inf
    for shift in shifts:
        predicted = np.interp(x + shift, reference_x, reference_y, left=np.nan, right=np.nan)
        finite = np.isfinite(actual) & np.isfinite(predicted)
        if np.count_nonzero(finite) < 3:
            continue
        rmse = float(np.sqrt(np.mean((actual[finite] - predicted[finite]) ** 2)))
        if rmse < best_rmse:
            best_shift, best_rmse = float(shift), rmse
    if not np.isfinite(best_rmse):
        raise ValueError("no overlapping samples for exposure offset")
    return {
        "log10_exposure": best_shift,
        "stops": float(best_shift / np.log10(2.0)),
        "rmse_after_shift": best_rmse,
    }
