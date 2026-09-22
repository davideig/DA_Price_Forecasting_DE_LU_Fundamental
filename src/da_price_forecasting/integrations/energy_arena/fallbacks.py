from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Sequence

import numpy as np
import pandas as pd

from .formatters import _expected_day_index


DEFAULT_OPERATIONAL_FALLBACK_LAGS_DAYS = [1, 7, 2, 3, 4, 5, 6, 14]


def _localised_forecast(forecast: pd.DataFrame, target_tz: str) -> pd.DataFrame:
    if not isinstance(forecast.index, pd.DatetimeIndex):
        raise TypeError("Operational fallback requires a DatetimeIndex forecast.")

    index = forecast.index
    if index.tz is None:
        index = index.tz_localize(target_tz)
    else:
        index = index.tz_convert(target_tz)

    work = forecast.copy()
    work.index = index
    work = work.sort_index()
    return work.loc[~work.index.duplicated(keep="last")]


def _candidate_days(
    forecast_date: date,
    lags_days: Sequence[int],
    max_lookback_days: int,
) -> list[date]:
    seen: set[date] = set()
    ordered: list[date] = []

    for lag in lags_days:
        if lag <= 0:
            continue
        candidate = forecast_date - timedelta(days=int(lag))
        if candidate not in seen:
            ordered.append(candidate)
            seen.add(candidate)

    for lag in range(1, max(max_lookback_days, 0) + 1):
        candidate = forecast_date - timedelta(days=lag)
        if candidate not in seen:
            ordered.append(candidate)
            seen.add(candidate)

    return ordered


def _remap_values_to_target_length(values: np.ndarray, target_length: int) -> np.ndarray:
    if len(values) == target_length:
        return values
    if len(values) == 0:
        raise ValueError("Cannot remap an empty fallback donor day.")

    source_x = np.linspace(0.0, 1.0, num=len(values))
    target_x = np.linspace(0.0, 1.0, num=target_length)
    columns = [
        np.interp(target_x, source_x, values[:, column_idx].astype(float))
        for column_idx in range(values.shape[1])
    ]
    return np.column_stack(columns)


def _valid_donor_day(
    work: pd.DataFrame,
    donor_day: date,
    target_tz: str,
    columns: Sequence[str],
) -> pd.DataFrame | None:
    donor_index = _expected_day_index(donor_day, target_tz)
    if not donor_index.isin(work.index).all():
        return None

    donor = work.reindex(donor_index)[list(columns)]
    if donor.isna().any().any():
        return None
    return donor


def apply_operational_submission_fallback(
    forecast_df: pd.DataFrame,
    *,
    forecast_date: date,
    target_tz: str,
    columns: Sequence[str],
    lags_days: Sequence[int] | None = None,
    max_lookback_days: int = 30,
    source_name: str | None = None,
) -> tuple[pd.DataFrame, dict[str, Any] | None]:
    """Fill an incomplete submission day from the best available prior forecast.

    This is a last-mile operational fallback for Energy Arena submissions. It
    does not switch models. It only fills the configured submission columns for
    the target day from a previous complete forecast day in the same forecast
    output/cache.
    """
    if not columns:
        return forecast_df, None

    missing_columns = [column for column in columns if column not in forecast_df.columns]
    if missing_columns:
        return forecast_df, None

    work = _localised_forecast(forecast_df, target_tz)
    target_index = _expected_day_index(forecast_date, target_tz)
    target_values = work.reindex(target_index)[list(columns)]
    if not target_values.isna().any().any():
        return forecast_df, None

    lags = list(lags_days or DEFAULT_OPERATIONAL_FALLBACK_LAGS_DAYS)
    donor: pd.DataFrame | None = None
    donor_day: date | None = None
    for candidate_day in _candidate_days(forecast_date, lags, max_lookback_days):
        candidate = _valid_donor_day(work, candidate_day, target_tz, columns)
        if candidate is None:
            continue
        donor = candidate
        donor_day = candidate_day
        break

    if donor is None or donor_day is None:
        return forecast_df, None

    donor_values = _remap_values_to_target_length(donor.to_numpy(dtype=float), len(target_index))
    fallback_values = pd.DataFrame(donor_values, index=target_index, columns=list(columns))
    filled_target = target_values.combine_first(fallback_values)
    if filled_target.isna().any().any():
        return forecast_df, None

    non_target = work.loc[~work.index.isin(target_index)]
    updated = pd.concat([non_target, filled_target], axis=0).sort_index()
    updated.index.name = forecast_df.index.name

    present_units = int(target_index.isin(work.index).sum())
    fallback_info: dict[str, Any] = {
        "type": "operational_submission_day_imputation",
        "source_name": source_name,
        "target_day": forecast_date.isoformat(),
        "donor_day": donor_day.isoformat(),
        "target_units": len(target_index),
        "present_target_units_before_fallback": present_units,
        "filled_target_units": len(target_index) - present_units,
        "columns": list(columns),
        "priority_lags_days": lags,
        "max_lookback_days": max_lookback_days,
    }
    return updated, fallback_info
