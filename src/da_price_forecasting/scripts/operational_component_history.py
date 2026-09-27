from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from ..integrations.energy_arena.fallbacks import apply_operational_submission_fallback
from ..pipelines.common import load_timestamp_csv, save_timestamp_csv


DEFAULT_HISTORY_ROOT = Path("data/processed/component_forecast_history")
COMPONENT_VALUE_COLUMNS: dict[str, tuple[str, ...]] = {
    "load": ("Load_Model_MW",),
    "solar": ("Solar_Model_MW",),
    "wind": ("Wind_Onshore_Model_MW", "Wind_Offshore_Model_MW", "Wind_Total_Model_MW"),
}


@dataclass(frozen=True)
class StoredComponentHistory:
    path: Path
    fallback_used: bool
    fallback_info: dict[str, object] | None
    rerun_path: Path | None = None


def component_history_path(repo_root: Path, cutoff: str, component: str) -> Path:
    return repo_root / DEFAULT_HISTORY_ROOT / cutoff / f"{component}.csv"


def _feature_provenance_path(output_file: Path) -> Path:
    return output_file.with_suffix(f"{output_file.suffix}.operational_provenance.json")


def model_feature_fallback_used(payload: dict, repo_root: Path, forecast_date: date) -> bool:
    config = payload.get("config", payload)
    paths = [config.get("renewable_proxy_file"), *config.get("extra_renewable_proxy_files", [])]
    for raw_path in paths:
        if not raw_path:
            continue
        output_file = Path(raw_path)
        if not output_file.is_absolute():
            output_file = repo_root / output_file
        provenance = _feature_provenance_path(output_file)
        if not provenance.exists():
            continue
        try:
            records = json.loads(provenance.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if bool(records.get(forecast_date.isoformat(), {}).get("fallback_used")):
            return True
    return False


def _local_day_mask(index: pd.DatetimeIndex, day: date, target_tz: str) -> pd.Series:
    local = index.tz_localize(target_tz) if index.tz is None else index.tz_convert(target_tz)
    return pd.Series(local.date == day, index=index)


def _history_columns(source: pd.DataFrame, component: str) -> list[str]:
    expected = COMPONENT_VALUE_COLUMNS[component]
    available = [column for column in expected if column in source.columns]
    if not available or expected[0] not in available:
        raise ValueError(
            f"{component} forecast is missing required value column {expected[0]!r}; "
            f"available columns: {list(source.columns)}"
        )
    return available


def store_component_forecast_history(
    *,
    repo_root: Path,
    cutoff: str,
    component: str,
    forecast_path: Path,
    forecast_date: date,
    target_tz: str,
    upstream_fallback_used: bool = False,
    recorded_at: datetime | None = None,
) -> StoredComponentHistory:
    """Append an immutable cutoff-specific component forecast history.

    Historical rows are added only when absent. If the delivery day was already
    recorded, the rerun is kept separately and the canonical history is left
    untouched. An incomplete current day is imputed from the best complete prior
    forecast in the same model output and marked as a fallback.
    """
    if component not in COMPONENT_VALUE_COLUMNS:
        raise ValueError(f"Unsupported component {component!r}.")

    source = load_timestamp_csv(forecast_path, target_tz)
    value_columns = _history_columns(source, component)
    completed, fallback_info = apply_operational_submission_fallback(
        source,
        forecast_date=forecast_date,
        target_tz=target_tz,
        columns=value_columns,
        source_name=f"{component}_{cutoff}",
    )
    target_mask = _local_day_mask(pd.DatetimeIndex(completed.index), forecast_date, target_tz)
    target = completed.loc[target_mask.to_numpy(), value_columns]
    expected_units = len(
        pd.date_range(
            pd.Timestamp(forecast_date, tz=target_tz),
            pd.Timestamp(forecast_date, tz=target_tz) + pd.DateOffset(days=1),
            freq="15min",
            inclusive="left",
        )
    )
    if len(target) != expected_units or target.isna().any().any():
        raise ValueError(
            f"No complete {component} forecast is available for cutoff {cutoff} "
            f"and delivery day {forecast_date}."
        )

    now = recorded_at or datetime.now(timezone.utc)
    fallback_used = upstream_fallback_used or fallback_info is not None
    candidate = completed.loc[:, value_columns].copy()
    local_dates = pd.DatetimeIndex(candidate.index).tz_convert(target_tz).date
    candidate["cutoff"] = cutoff
    candidate["component"] = component
    candidate["fallback_used"] = False
    candidate.loc[target_mask.to_numpy(), "fallback_used"] = fallback_used
    candidate["backfilled"] = local_dates < forecast_date
    candidate["recorded_at_utc"] = now.astimezone(timezone.utc).isoformat()
    candidate.index.name = "timestamp"

    history_path = component_history_path(repo_root, cutoff, component)
    existing = load_timestamp_csv(history_path, target_tz) if history_path.exists() else pd.DataFrame()
    rerun_path: Path | None = None
    if not existing.empty and target.index.intersection(existing.index).size:
        stamp = now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        rerun_path = (
            repo_root
            / DEFAULT_HISTORY_ROOT
            / "reruns"
            / cutoff
            / forecast_date.isoformat()
            / stamp
            / f"{component}.csv"
        )
        rerun = candidate.loc[target_mask.to_numpy()].copy()
        save_timestamp_csv(rerun, rerun_path)

    if existing.empty:
        combined = candidate
    else:
        additions = candidate.loc[~candidate.index.isin(existing.index)]
        combined = pd.concat([existing, additions]).sort_index()
    save_timestamp_csv(combined, history_path)
    return StoredComponentHistory(
        path=history_path,
        fallback_used=fallback_used,
        fallback_info=fallback_info,
        rerun_path=rerun_path,
    )
