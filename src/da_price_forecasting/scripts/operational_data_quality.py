from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from da_price_forecasting.paths import find_repo_root
from da_price_forecasting.preprocessing.dwd_icon_operational import (
    DEFAULT_DWD_ICON_VARIABLES,
    dwd_issue_day_for_forecast,
    processed_weather_folder,
    processed_weather_folder_is_ready,
)
from da_price_forecasting.scripts.check_data_pack import _expand_profile, collect_required_paths
from da_price_forecasting.scripts.dwd_icon_daily_update import load_model_config


DEFAULT_TARGET_TZ = "Europe/Berlin"
DEFAULT_REPORT_DIR = Path("data/processed/operational_quality")
DWD_CONFIG_PATHS = (
    Path("configs/preprocessing/weather_aggregation/dwd_icon_mastr_wind_c100_run00_daily_update.yaml"),
    Path("configs/preprocessing/weather_aggregation/dwd_icon_mastr_solar_tso_c25_run00_daily_update.yaml"),
    Path("configs/preprocessing/weather_aggregation/dwd_icon_c2_run00_daily_update.yaml"),
    Path("configs/preprocessing/weather_aggregation/dwd_icon_mastr_wind_c100_run06_daily_update.yaml"),
    Path("configs/preprocessing/weather_aggregation/dwd_icon_mastr_solar_tso_c25_run06_daily_update.yaml"),
    Path("configs/preprocessing/weather_aggregation/dwd_icon_c2_run06_daily_update.yaml"),
)
FALLBACK_MARKERS = (
    "[fallback]",
    "using fallback model run",
    "skipping unavailable model run",
)


def _collect_dwd_weather(repo_root: Path, forecast_date: date) -> list[dict[str, object]]:
    statuses: list[dict[str, object]] = []
    for relative_config in DWD_CONFIG_PATHS:
        config = load_model_config(relative_config, repo_root)
        issue_day = dwd_issue_day_for_forecast(forecast_date, config.dwd_folder_offset_date)
        folder = processed_weather_folder(config.icon_dir, issue_day, config.required_run)
        expected_csv_files = len(config.dwd_icon_download_variables or DEFAULT_DWD_ICON_VARIABLES)
        csv_files = len(list(folder.glob("*.csv"))) if folder.is_dir() else 0
        statuses.append(
            {
                "config": relative_config.as_posix(),
                "run_hour_utc": config.required_run,
                "issue_day": issue_day.isoformat(),
                "processed_folder": folder.relative_to(repo_root).as_posix(),
                "ready": processed_weather_folder_is_ready(folder, min_csv_files=expected_csv_files),
                "csv_files": csv_files,
                "expected_csv_files": expected_csv_files,
            }
        )
    return statuses


def _collect_required_inputs(repo_root: Path) -> tuple[int, list[dict[str, object]]]:
    required = collect_required_paths(repo_root, _expand_profile(repo_root, "operational"))
    missing = [asdict(item) for item in required if not item.exists]
    return len(required), missing


def _collect_fallback_events(repo_root: Path, operation_date: date) -> list[dict[str, object]]:
    log_dir = repo_root / "logs" / "chair_vm_tasks"
    events: list[dict[str, object]] = []
    for path in sorted(log_dir.glob(f"*_{operation_date.isoformat()}.log")):
        with path.open(encoding="utf-8", errors="replace") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                message = raw_line.strip()
                lowered = message.lower()
                if any(marker in lowered for marker in FALLBACK_MARKERS):
                    events.append(
                        {
                            "log": path.relative_to(repo_root).as_posix(),
                            "line": line_number,
                            "message": message,
                        }
                    )
    return events


def _collect_submission_responses(repo_root: Path, forecast_date: date) -> list[str]:
    root = repo_root / "results" / "energy_arena_submissions"
    if not root.exists():
        return []
    target = forecast_date.isoformat()
    return sorted(
        path.relative_to(repo_root).as_posix()
        for path in root.rglob("submission_response.json")
        if target in path.parts
    )


def build_quality_report(
    *,
    repo_root: Path,
    operation_date: date,
    forecast_date: date,
    target_tz: str = DEFAULT_TARGET_TZ,
) -> dict[str, object]:
    dwd_weather = _collect_dwd_weather(repo_root, forecast_date)
    required_count, missing_inputs = _collect_required_inputs(repo_root)
    fallback_events = _collect_fallback_events(repo_root, operation_date)
    submission_responses = _collect_submission_responses(repo_root, forecast_date)
    degraded = any(not item["ready"] for item in dwd_weather) or bool(missing_inputs) or bool(fallback_events)

    return {
        "schema_version": 1,
        "generated_at": datetime.now(ZoneInfo(target_tz)).isoformat(),
        "operation_date": operation_date.isoformat(),
        "forecast_date": forecast_date.isoformat(),
        "status": "degraded" if degraded else "ok",
        "dwd_weather": dwd_weather,
        "required_inputs": {
            "checked": required_count,
            "present": required_count - len(missing_inputs),
            "missing": missing_inputs,
        },
        "fallback_events": fallback_events,
        "submission_responses": submission_responses,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Write a dated quality report for operational forecast inputs.")
    parser.add_argument("--repo-root", type=Path, default=None)
    parser.add_argument("--operation-date", type=date.fromisoformat, default=None)
    parser.add_argument("--forecast-date", type=date.fromisoformat, default=None)
    parser.add_argument("--target-tz", default=DEFAULT_TARGET_TZ)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--strict", action="store_true", help="Return a non-zero exit status for a degraded report.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = args.repo_root.resolve() if args.repo_root else find_repo_root(Path.cwd())
    today = datetime.now(ZoneInfo(args.target_tz)).date()
    operation_date = args.operation_date or today
    forecast_date = args.forecast_date or operation_date + timedelta(days=1)
    output = args.output or DEFAULT_REPORT_DIR / f"{operation_date.isoformat()}.json"
    output = output if output.is_absolute() else repo_root / output

    report = build_quality_report(
        repo_root=repo_root,
        operation_date=operation_date,
        forecast_date=forecast_date,
        target_tz=args.target_tz,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    dwd_ready = sum(bool(item["ready"]) for item in report["dwd_weather"])
    required = report["required_inputs"]
    print(f"[quality] Status: {report['status']}")
    print(f"[quality] DWD processed inputs ready: {dwd_ready}/{len(report['dwd_weather'])}")
    print(f"[quality] Required inputs present: {required['present']}/{required['checked']}")
    print(f"[quality] Fallback events today: {len(report['fallback_events'])}")
    print(f"[quality] Submission responses for {forecast_date}: {len(report['submission_responses'])}")
    print(f"[quality] Saved report: {output}")
    return 1 if args.strict and report["status"] != "ok" else 0


if __name__ == "__main__":
    raise SystemExit(main())
