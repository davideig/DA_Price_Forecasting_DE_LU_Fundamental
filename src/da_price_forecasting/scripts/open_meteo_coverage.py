from __future__ import annotations

import argparse
import json
import shutil
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from da_price_forecasting.data.weather import open_meteo_run_provenance_path
from da_price_forecasting.paths import find_repo_root


DEFAULT_CONFIG_DIR = Path("configs/deployment/cutoff_preprocessing")
DEFAULT_REPORT = Path("data/processed/operational_quality/open_meteo_coverage.json")
DEFAULT_QUARANTINE_DIR = Path("data/quarantine/open_meteo_unverified_transition")
MODELS = ("load", "solar", "wind")
RUNS = ("03", "06")


def _date_range(start: date, end: date) -> set[date]:
    if end < start:
        return set()
    return set(pd.date_range(start, end, freq="D").date)


def _date_ranges(days: set[date]) -> list[dict[str, object]]:
    if not days:
        return []
    ordered = sorted(days)
    ranges: list[dict[str, object]] = []
    start = previous = ordered[0]
    for current in ordered[1:]:
        if (current - previous).days != 1:
            ranges.append({"start": start.isoformat(), "end": previous.isoformat()})
            start = current
        previous = current
    ranges.append({"start": start.isoformat(), "end": previous.isoformat()})
    return ranges


def _read_config(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("config"), dict):
        raise ValueError(f"Invalid deployment config: {path}")
    return payload["config"]


def _cached_delivery_days(path: Path, target_tz: str) -> set[date]:
    if not path.exists() or path.stat().st_size == 0:
        return set()
    frame = pd.read_csv(path, index_col=0, usecols=[0])
    # Operational caches span CET and CEST, so their ISO timestamps can carry
    # mixed UTC offsets. Normalize them before converting to the deployment TZ.
    timestamps = pd.to_datetime(frame.index, errors="coerce", utc=True)
    timestamps = timestamps[~pd.isna(timestamps)]
    if len(timestamps) == 0:
        return set()
    timestamps = timestamps.tz_convert(target_tz)
    return set(timestamps.date)


def _read_provenance(path: Path) -> dict[date, dict[str, object]]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid Open-Meteo provenance file: {path}")
    records: dict[date, dict[str, object]] = {}
    for raw_day, record in payload.items():
        if isinstance(record, dict):
            records[date.fromisoformat(raw_day)] = record
    return records


def _validate_provenance_record(
    *,
    day: date,
    record: dict[str, object],
    requested_hour: int,
    target_tz: str,
) -> str | None:
    try:
        requested = pd.Timestamp(str(record["requested_run_utc"]), tz="UTC")
        actual = pd.Timestamp(str(record["actual_run_utc"]), tz="UTC")
    except (KeyError, TypeError, ValueError) as exc:
        return f"{day}: malformed run provenance ({exc})"

    expected_requested = pd.Timestamp(day, tz="UTC") - pd.Timedelta(days=1) + pd.Timedelta(
        hours=requested_hour
    )
    if requested != expected_requested:
        return f"{day}: requested {requested.isoformat()} instead of {expected_requested.isoformat()}"

    if requested_hour in (0, 3) and actual.hour == 6:
        return f"{day}: later 06 UTC data found in run{requested_hour:02d} history"
    lookback_hours = int((requested - actual).total_seconds() // 3600)
    if lookback_hours not in (0, 3):
        return (
            f"{day}: actual run {actual.isoformat()} is not the requested run or its "
            "three-hour predecessor"
        )
    delivery_end = (
        pd.Timestamp(day, tz=target_tz) + pd.DateOffset(days=1)
    ).tz_convert("UTC")
    if actual != requested and actual + pd.Timedelta(hours=48) < delivery_end:
        return (
            f"{day}: fallback run {actual.isoformat()} cannot cover the complete local "
            "delivery day"
        )
    return None


def audit_dataset(
    *,
    model: str,
    run: str,
    config_path: Path,
    repo_root: Path,
    end_date: date | None = None,
) -> dict[str, object]:
    config = _read_config(config_path)
    configured_start = date.fromisoformat(str(config["open_meteo_start_date"]))
    configured_end = date.fromisoformat(str(config["open_meteo_end_date"]))
    audit_end = end_date or configured_end
    target_tz = str(config.get("target_tz", "Europe/Berlin"))
    allowed_missing_days = {
        date.fromisoformat(str(raw_day)) for raw_day in config.get("skip_dates", [])
    }
    cache_path = repo_root / str(config["open_meteo_weather_file"])
    provenance_path = open_meteo_run_provenance_path(cache_path)
    cached_days = _cached_delivery_days(cache_path, target_tz)
    provenance = _read_provenance(provenance_path)
    relevant_days = _date_range(configured_start, audit_end)
    cached_days &= relevant_days
    provenance = {day: record for day, record in provenance.items() if day in relevant_days}

    provenance_days = set(provenance)
    unverified_cached = cached_days - provenance_days
    provenance_without_cache = provenance_days - cached_days
    archive_start = min(provenance_days) if provenance_days else None
    transition_missing = (
        _date_range(configured_start, archive_start - pd.Timedelta(days=1).to_pytimedelta())
        - cached_days
        if archive_start
        else relevant_days - cached_days
    )
    raw_missing_within_archive = (
        _date_range(archive_start, audit_end) - cached_days - provenance_without_cache
        if archive_start
        else set()
    )
    allowed_missing_within_archive = raw_missing_within_archive & allowed_missing_days
    missing_within_archive = raw_missing_within_archive - allowed_missing_days

    requested_hour = int(run)
    invalid_provenance = [
        reason
        for day, record in sorted(provenance.items())
        if (reason := _validate_provenance_record(
            day=day,
            record=record,
            requested_hour=requested_hour,
            target_tz=target_tz,
        ))
    ]
    genuine_days = {
        day
        for day, record in provenance.items()
        if record.get("requested_run_utc") == record.get("actual_run_utc")
    }
    fallback_days = provenance_days - genuine_days
    failures = bool(
        unverified_cached
        or provenance_without_cache
        or missing_within_archive
        or invalid_provenance
        or not provenance_days
    )

    return {
        "model": model,
        "requested_run_utc": f"{run}:00",
        "config": config_path.relative_to(repo_root).as_posix(),
        "cache": cache_path.relative_to(repo_root).as_posix(),
        "provenance": provenance_path.relative_to(repo_root).as_posix(),
        "configured_start": configured_start.isoformat(),
        "audit_end": audit_end.isoformat(),
        "archive_start": archive_start.isoformat() if archive_start else None,
        "first_genuine_date": min(genuine_days).isoformat() if genuine_days else None,
        "last_genuine_date": max(genuine_days).isoformat() if genuine_days else None,
        "genuine_days": len(genuine_days),
        "fallback_days": len(fallback_days),
        "transition_missing_days": len(transition_missing),
        "transition_missing_ranges": _date_ranges(transition_missing),
        "missing_within_archive_days": len(missing_within_archive),
        "missing_within_archive_ranges": _date_ranges(missing_within_archive),
        "allowed_missing_days": len(allowed_missing_within_archive),
        "allowed_missing_ranges": _date_ranges(allowed_missing_within_archive),
        "unverified_cached_days": len(unverified_cached),
        "unverified_cached_ranges": _date_ranges(unverified_cached),
        "provenance_without_cache_days": len(provenance_without_cache),
        "provenance_without_cache_ranges": _date_ranges(provenance_without_cache),
        "invalid_provenance": invalid_provenance,
        "status": "failed" if failures else ("transition" if transition_missing else "ok"),
    }


def _prune_dates_from_csv(
    path: Path,
    *,
    target_tz: str,
    days: set[date],
    backup_path: Path,
) -> int:
    if not days or not path.exists():
        return 0
    frame = pd.read_csv(path, index_col=0)
    timestamps = pd.to_datetime(frame.index, errors="coerce", utc=True)
    local_days = pd.Series(timestamps.tz_convert(target_tz).date, index=frame.index)
    remove = local_days.isin(days).to_numpy()
    if not remove.any():
        return 0

    backup_path.parent.mkdir(parents=True, exist_ok=True)
    if not backup_path.exists():
        shutil.copy2(path, backup_path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.loc[~remove].to_csv(temporary)
    temporary.replace(path)
    return int(remove.sum())


def prune_unverified_transition_rows(
    *,
    repo_root: Path,
    config_dir: Path = DEFAULT_CONFIG_DIR,
    end_date: date | None = None,
    quarantine_dir: Path = DEFAULT_QUARANTINE_DIR,
) -> list[dict[str, object]]:
    """Back up and remove cached rows older than the first proven fixed-run day."""
    resolved_config_dir = config_dir if config_dir.is_absolute() else repo_root / config_dir
    resolved_quarantine = (
        quarantine_dir if quarantine_dir.is_absolute() else repo_root / quarantine_dir
    )
    changes: list[dict[str, object]] = []
    for run in RUNS:
        for model in MODELS:
            config_path = resolved_config_dir / (
                f"load_open_meteo_history_run{run}.yaml"
                if model == "load"
                else f"{model}_open_meteo_features_run{run}.yaml"
            )
            config = _read_config(config_path)
            target_tz = str(config.get("target_tz", "Europe/Berlin"))
            cache_path = repo_root / str(config["open_meteo_weather_file"])
            cached_days = _cached_delivery_days(cache_path, target_tz)
            provenance_days = set(_read_provenance(open_meteo_run_provenance_path(cache_path)))
            if end_date:
                cached_days = {day for day in cached_days if day <= end_date}
                provenance_days = {day for day in provenance_days if day <= end_date}
            if not provenance_days:
                continue
            archive_start = min(provenance_days)
            unverified_days = cached_days - provenance_days
            prune_days = {day for day in unverified_days if day < archive_start}
            blocked_days = unverified_days - prune_days
            paths = [cache_path]
            if config.get("output_file"):
                paths.append(repo_root / str(config["output_file"]))
            removed_rows = 0
            for path in paths:
                relative = path.relative_to(repo_root)
                removed_rows += _prune_dates_from_csv(
                    path,
                    target_tz=target_tz,
                    days=prune_days,
                    backup_path=resolved_quarantine / relative,
                )
            changes.append(
                {
                    "model": model,
                    "run": run,
                    "pruned_days": len(prune_days),
                    "removed_rows": removed_rows,
                    "blocked_days": len(blocked_days),
                }
            )
    return changes


def build_coverage_report(
    *,
    repo_root: Path,
    config_dir: Path = DEFAULT_CONFIG_DIR,
    end_date: date | None = None,
) -> dict[str, object]:
    resolved_config_dir = config_dir if config_dir.is_absolute() else repo_root / config_dir
    datasets = [
        audit_dataset(
            model=model,
            run=run,
            config_path=resolved_config_dir / (
                f"load_open_meteo_history_run{run}.yaml"
                if model == "load"
                else f"{model}_open_meteo_features_run{run}.yaml"
            ),
            repo_root=repo_root,
            end_date=end_date,
        )
        for run in RUNS
        for model in MODELS
    ]
    return {
        "schema_version": 1,
        "status": "failed" if any(item["status"] == "failed" for item in datasets) else "ok",
        "datasets": datasets,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit fixed-run Open-Meteo cache coverage and run provenance."
    )
    parser.add_argument("--repo-root", type=Path, default=None)
    parser.add_argument("--config-dir", type=Path, default=DEFAULT_CONFIG_DIR)
    parser.add_argument("--end-date", type=date.fromisoformat, default=None)
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    parser.add_argument(
        "--prune-unverified-transition",
        action="store_true",
        help=(
            "Back up and remove cache/feature rows before each dataset's first "
            "provenance-backed day. Unverified rows inside the archive remain failures."
        ),
    )
    parser.add_argument("--quarantine-dir", type=Path, default=DEFAULT_QUARANTINE_DIR)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = args.repo_root.resolve() if args.repo_root else find_repo_root(Path.cwd())
    if args.prune_unverified_transition:
        changes = prune_unverified_transition_rows(
            repo_root=repo_root,
            config_dir=args.config_dir,
            end_date=args.end_date,
            quarantine_dir=args.quarantine_dir,
        )
        for change in changes:
            print(
                f"[weather-coverage] {change['model']} run{change['run']}: "
                f"pruned_days={change['pruned_days']}; "
                f"removed_rows={change['removed_rows']}; "
                f"blocked_unverified_days={change['blocked_days']}"
            )
    report = build_coverage_report(
        repo_root=repo_root,
        config_dir=args.config_dir,
        end_date=args.end_date,
    )
    output = args.output if args.output.is_absolute() else repo_root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    for item in report["datasets"]:
        print(
            f"[weather-coverage] {item['model']} run{str(item['requested_run_utc'])[:2]}: "
            f"{item['status']}; archive_start={item['archive_start']}; "
            f"genuine={item['first_genuine_date']}..{item['last_genuine_date']}; "
            f"fallback_days={item['fallback_days']}; "
            f"transition_missing={item['transition_missing_days']}; "
            f"archive_gaps={item['missing_within_archive_days']}; "
            f"allowed_missing={item['allowed_missing_days']}; "
            f"unverified={item['unverified_cached_days']}"
        )
    print(f"[weather-coverage] Saved report: {output}")
    return 1 if report["status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
