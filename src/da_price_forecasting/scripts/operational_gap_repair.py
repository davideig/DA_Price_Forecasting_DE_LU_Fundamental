from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from da_price_forecasting.config.base import load_config_payload
from da_price_forecasting.paths import find_repo_root
from da_price_forecasting.pipelines.common import load_timestamp_csv, save_timestamp_csv


DEFAULT_TARGET_TZ = "Europe/Berlin"
DEFAULT_GRACE_DAYS = 14
DEFAULT_SHORT_GAP_PERIODS = 4
DEFAULT_SEASONAL_WEEKS = 8
DEFAULT_REPORT_DIR = Path("data/processed/operational_quality")
DEFAULT_PROVENANCE_FILE = DEFAULT_REPORT_DIR / "persistent_gap_imputations.csv"


@dataclass(frozen=True)
class ActualDataset:
    name: str
    path: Path
    configured_columns: tuple[str, ...]
    source_id: str | None = None


@dataclass(frozen=True)
class ImputationEvent:
    dataset: str
    source_path: str
    timestamp: str
    column: str
    method: str
    value: float
    operation_date: str
    grace_days: int


def _nested_config(payload: dict) -> dict:
    config = payload.get("config", payload)
    if not isinstance(config, dict):
        raise ValueError("Configuration payload must contain a mapping.")
    return config


def discover_actual_datasets(repo_root: Path) -> list[ActualDataset]:
    """Discover unique realized-value caches used by live cutoff configs."""
    datasets: dict[Path, ActualDataset] = {}
    for config_path in sorted((repo_root / "configs/deployment/cutoffs").glob("*.yaml")):
        payload = load_config_payload(config_path)
        body = _nested_config(payload)
        kind = payload.get("kind")
        if kind == "load_forecast_model" and body.get("actual_load_file"):
            raw_path = Path(body["actual_load_file"])
            path = raw_path if raw_path.is_absolute() else repo_root / raw_path
            datasets[path] = ActualDataset("load", path, ("Load_Actual_MW",), raw_path.as_posix())
        elif kind == "renewable_generation_model" and body.get("actual_generation_file"):
            raw_path = Path(body["actual_generation_file"])
            path = raw_path if raw_path.is_absolute() else repo_root / raw_path
            configured = tuple(str(column) for column in body.get("target_columns", []))
            label = "solar" if any(column.startswith("Solar_") for column in configured) else "wind"
            previous = datasets.get(path)
            columns = configured if previous is None else tuple(dict.fromkeys((*previous.configured_columns, *configured)))
            datasets[path] = ActualDataset(label, path, columns, raw_path.as_posix())
    return sorted(datasets.values(), key=lambda item: (item.name, str(item.path)))


def _actual_columns(frame: pd.DataFrame, configured: tuple[str, ...]) -> list[str]:
    candidates = list(configured)
    candidates.extend(str(column) for column in frame.columns if str(column).endswith("_Actual_MW"))
    return [column for column in dict.fromkeys(candidates) if column in frame.columns]


def _expected_index(frame: pd.DataFrame, eligible_through: date, target_tz: str) -> pd.DatetimeIndex:
    index = pd.DatetimeIndex(frame.index)
    local = index.tz_localize(target_tz) if index.tz is None else index.tz_convert(target_tz)
    start_day = local.min().date()
    if start_day > eligible_through:
        return pd.DatetimeIndex([], tz=target_tz, name=index.name or "timestamp")
    return pd.date_range(
        pd.Timestamp(start_day, tz=target_tz),
        pd.Timestamp(eligible_through + timedelta(days=1), tz=target_tz),
        freq="15min",
        inclusive="left",
        name=index.name or "timestamp",
    )


def _missing_runs(mask: pd.Series) -> list[pd.DatetimeIndex]:
    positions = np.flatnonzero(mask.to_numpy(dtype=bool))
    if not len(positions):
        return []
    boundaries = np.flatnonzero(np.diff(positions) > 1) + 1
    return [mask.index[group] for group in np.split(positions, boundaries)]


def _seasonal_value(
    original: pd.Series,
    timestamp: pd.Timestamp,
    *,
    target_tz: str,
    seasonal_weeks: int,
) -> tuple[float | None, str | None]:
    observed = original.dropna()
    observed = observed.loc[observed.index < timestamp]
    if observed.empty:
        return None, None

    local_index = pd.DatetimeIndex(observed.index).tz_convert(target_tz)
    local_timestamp = timestamp.tz_convert(target_tz)
    quarter = local_index.hour * 4 + local_index.minute // 15
    target_quarter = local_timestamp.hour * 4 + local_timestamp.minute // 15
    recent_start = timestamp - pd.Timedelta(weeks=seasonal_weeks)
    recent_mask = (
        (observed.index >= recent_start)
        & (local_index.weekday == local_timestamp.weekday())
        & (quarter == target_quarter)
    )
    donors = observed.loc[recent_mask]
    if not donors.empty:
        return float(donors.median()), f"seasonal_weekday_quarter_median_{seasonal_weeks}w"

    quarter_donors = observed.loc[quarter == target_quarter]
    if not quarter_donors.empty:
        return float(quarter_donors.median()), "historical_quarter_median"
    return None, None


def impute_persistent_gaps(
    frame: pd.DataFrame,
    *,
    dataset: ActualDataset,
    operation_date: date,
    target_tz: str = DEFAULT_TARGET_TZ,
    grace_days: int = DEFAULT_GRACE_DAYS,
    short_gap_periods: int = DEFAULT_SHORT_GAP_PERIODS,
    seasonal_weeks: int = DEFAULT_SEASONAL_WEEKS,
    known_imputed: set[tuple[pd.Timestamp, str]] | None = None,
) -> tuple[pd.DataFrame, list[ImputationEvent], dict[str, object]]:
    """Fill old realized-value gaps while preserving an auditable source distinction."""
    if frame.empty:
        return frame, [], {"imputed_cells": 0, "unresolved_cells": 0, "columns": []}

    eligible_through = operation_date - timedelta(days=grace_days)
    expected = _expected_index(frame, eligible_through, target_tz)
    original = frame.copy()
    original.index = pd.DatetimeIndex(original.index)
    if original.index.tz is None:
        original.index = original.index.tz_localize(target_tz)
    else:
        original.index = original.index.tz_convert(target_tz)
    original = original.loc[~original.index.duplicated(keep="last")].sort_index()
    repaired = original.reindex(original.index.union(expected).sort_values())
    columns = _actual_columns(repaired, dataset.configured_columns)
    events: list[ImputationEvent] = []
    unresolved = 0

    for column in columns:
        original_values = pd.to_numeric(original[column], errors="coerce").reindex(repaired.index)
        if known_imputed:
            prior_imputed = [timestamp for timestamp, known_column in known_imputed if known_column == column]
            original_values.loc[original_values.index.intersection(prior_imputed)] = np.nan
        values = pd.to_numeric(repaired[column], errors="coerce")
        eligible_mask = repaired.index.isin(expected)
        missing = pd.Series(eligible_mask & values.isna(), index=repaired.index)

        for run in _missing_runs(missing):
            if len(run) <= short_gap_periods:
                first_position = repaired.index.get_loc(run[0])
                last_position = repaired.index.get_loc(run[-1])
                if first_position > 0 and last_position + 1 < len(repaired.index):
                    left_ts = repaired.index[first_position - 1]
                    right_ts = repaired.index[last_position + 1]
                    left = original_values.loc[left_ts]
                    right = original_values.loc[right_ts]
                    if pd.notna(left) and pd.notna(right):
                        span = (right_ts - left_ts).total_seconds()
                        for timestamp in run:
                            weight = (timestamp - left_ts).total_seconds() / span
                            value = max(0.0, float(left + (right - left) * weight))
                            values.loc[timestamp] = value
                            events.append(
                                ImputationEvent(
                                    dataset=dataset.name,
                                    source_path=dataset.source_id or str(dataset.path),
                                    timestamp=timestamp.isoformat(),
                                    column=column,
                                    method="linear_interpolation",
                                    value=value,
                                    operation_date=operation_date.isoformat(),
                                    grace_days=grace_days,
                                )
                            )
                        continue

            for timestamp in run:
                value, method = _seasonal_value(
                    original_values,
                    timestamp,
                    target_tz=target_tz,
                    seasonal_weeks=seasonal_weeks,
                )
                if value is None or method is None:
                    unresolved += 1
                    continue
                value = max(0.0, value)
                values.loc[timestamp] = value
                events.append(
                    ImputationEvent(
                        dataset=dataset.name,
                        source_path=dataset.source_id or str(dataset.path),
                        timestamp=timestamp.isoformat(),
                        column=column,
                        method=method,
                        value=value,
                        operation_date=operation_date.isoformat(),
                        grace_days=grace_days,
                    )
                )
        repaired[column] = values

    summary = {
        "dataset": dataset.name,
        "source_path": dataset.source_id or str(dataset.path),
        "eligible_through": eligible_through.isoformat(),
        "columns": columns,
        "imputed_cells": len(events),
        "unresolved_cells": unresolved,
    }
    return repaired, events, summary


def _write_provenance(path: Path, events: list[ImputationEvent]) -> None:
    columns = list(ImputationEvent.__dataclass_fields__)
    additions = pd.DataFrame([asdict(event) for event in events], columns=columns)
    if path.exists():
        existing = pd.read_csv(path)
        combined = pd.concat([existing, additions], ignore_index=True)
    else:
        combined = additions
    if not combined.empty:
        combined = combined.drop_duplicates(["source_path", "timestamp", "column"], keep="first")
        combined = combined.sort_values(["source_path", "timestamp", "column"])
    path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(path, index=False)


def _known_imputed_cells(path: Path, dataset: ActualDataset, target_tz: str) -> set[tuple[pd.Timestamp, str]]:
    if not path.exists():
        return set()
    try:
        provenance = pd.read_csv(path)
    except (OSError, ValueError):
        return set()
    required = {"source_path", "timestamp", "column"}
    if not required.issubset(provenance.columns):
        return set()
    source_id = dataset.source_id or str(dataset.path)
    selected = provenance.loc[provenance["source_path"] == source_id]
    timestamps = pd.to_datetime(selected["timestamp"], errors="coerce", utc=True)
    cells: set[tuple[pd.Timestamp, str]] = set()
    for timestamp, column in zip(timestamps, selected["column"], strict=False):
        if pd.notna(timestamp):
            cells.add((pd.Timestamp(timestamp).tz_convert(target_tz), str(column)))
    return cells


def repair_operational_actuals(
    *,
    repo_root: Path,
    operation_date: date,
    target_tz: str = DEFAULT_TARGET_TZ,
    grace_days: int = DEFAULT_GRACE_DAYS,
    provenance_path: Path | None = None,
    report_path: Path | None = None,
    dry_run: bool = False,
) -> dict[str, object]:
    datasets = discover_actual_datasets(repo_root)
    summaries: list[dict[str, object]] = []
    all_events: list[ImputationEvent] = []
    missing_files: list[str] = []
    provenance = provenance_path or repo_root / DEFAULT_PROVENANCE_FILE

    for dataset in datasets:
        if not dataset.path.exists():
            missing_files.append(str(dataset.path))
            continue
        frame = load_timestamp_csv(dataset.path, target_tz)
        repaired, events, summary = impute_persistent_gaps(
            frame,
            dataset=dataset,
            operation_date=operation_date,
            target_tz=target_tz,
            grace_days=grace_days,
            known_imputed=_known_imputed_cells(provenance, dataset, target_tz),
        )
        summaries.append(summary)
        all_events.extend(events)
        if events and not dry_run:
            save_timestamp_csv(repaired, dataset.path)

    report = {
        "schema_version": 1,
        "generated_at": datetime.now(ZoneInfo(target_tz)).isoformat(),
        "operation_date": operation_date.isoformat(),
        "grace_days": grace_days,
        "dry_run": dry_run,
        "datasets": summaries,
        "missing_files": missing_files,
        "imputed_cells": sum(int(item["imputed_cells"]) for item in summaries),
        "unresolved_cells": sum(int(item["unresolved_cells"]) for item in summaries),
    }
    if not dry_run:
        _write_provenance(provenance, all_events)
        output = report_path or repo_root / DEFAULT_REPORT_DIR / f"persistent_gap_repair_{operation_date}.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Impute persistent gaps in operational realized-value caches.")
    parser.add_argument("--repo-root", type=Path, default=None)
    parser.add_argument("--operation-date", type=date.fromisoformat, default=None)
    parser.add_argument("--target-tz", default=DEFAULT_TARGET_TZ)
    parser.add_argument("--grace-days", type=int, default=DEFAULT_GRACE_DAYS)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--strict", action="store_true", help="Fail if any old gap remains unresolved.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.grace_days < 1:
        raise SystemExit("--grace-days must be positive.")
    repo_root = args.repo_root.resolve() if args.repo_root else find_repo_root(Path.cwd())
    operation_date = args.operation_date or datetime.now(ZoneInfo(args.target_tz)).date()
    report = repair_operational_actuals(
        repo_root=repo_root,
        operation_date=operation_date,
        target_tz=args.target_tz,
        grace_days=args.grace_days,
        dry_run=args.dry_run,
    )
    for item in report["datasets"]:
        print(
            f"[persistent-gaps] {item['dataset']}: imputed={item['imputed_cells']}; "
            f"unresolved={item['unresolved_cells']}; eligible_through={item['eligible_through']}"
        )
    if report["missing_files"]:
        print(f"[persistent-gaps] Missing cache files: {len(report['missing_files'])}")
    print(
        f"[persistent-gaps] Total imputed={report['imputed_cells']}; "
        f"unresolved={report['unresolved_cells']}"
    )
    has_unresolved = bool(report["unresolved_cells"] or report["missing_files"])
    return 1 if args.strict and has_unresolved else 0


if __name__ == "__main__":
    raise SystemExit(main())
