from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests
from dotenv import load_dotenv

from ..paths import find_repo_root, resolve_path


DEFAULT_OUTPUT_FILE = Path("data/processed/open_meteo/model_run_availability_log.csv")
DEFAULT_TARGET_TZ = "Europe/Berlin"
DEFAULT_CHECK_TIME = "11:20"
DEFAULT_TARGET_RUN_HOUR_UTC = 6
DEFAULT_SAFETY_BUFFER_MINUTES = 10
DEFAULT_API_KEY_ENV = "OPEN_METEO_API_KEY"


@dataclass(frozen=True)
class ProviderMetadata:
    provider: str
    forecast_model: str
    metadata_model: str
    provider_group: str


DEFAULT_PROVIDERS = (
    ProviderMetadata("DWD", "icon_d2", "dwd_icon_d2", "regional"),
    ProviderMetadata("ECMWF", "ecmwf_ifs025", "ecmwf_ifs025", "global"),
    ProviderMetadata("Meteo-France", "meteofrance_arpege_europe", "meteofrance_arpege_europe", "global"),
    ProviderMetadata("UK Met Office", "ukmo_seamless", "ukmo_global_deterministic_10km", "global"),
    ProviderMetadata("NOAA NCEP", "gfs_seamless", "ncep_gfs013", "global"),
    ProviderMetadata("DMI", "dmi_harmonie_arome_europe", "dmi_harmonie_arome_europe", "regional"),
    ProviderMetadata("DWD", "icon_eu", "dwd_icon_eu", "regional"),
)


def _parse_hhmm(value: str) -> time:
    try:
        hour, minute = value.split(":", 1)
        return time(hour=int(hour), minute=int(minute))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Expected HH:MM, for example 11:20.") from exc


def _metadata_base_url(kind: str) -> str:
    if kind == "customer":
        return "https://customer-api.open-meteo.com/data"
    if kind == "public":
        return "https://api.open-meteo.com/data"
    raise ValueError(f"Unknown metadata endpoint kind: {kind!r}")


def _metadata_url(model: str, kind: str) -> str:
    return f"{_metadata_base_url(kind)}/{model}/static/meta.json"


def _utc_datetime_from_unix(value: object) -> pd.Timestamp | None:
    if value is None:
        return None
    try:
        return pd.to_datetime(float(value), unit="s", utc=True)
    except (TypeError, ValueError):
        return None


def _fetch_metadata(
    provider: ProviderMetadata,
    *,
    endpoint: str,
    api_key_env: str | None,
    timeout_seconds: int,
) -> dict:
    params: dict[str, str | int] = {"cache_buster": int(datetime.now().timestamp())}
    if api_key_env:
        api_key = os.getenv(api_key_env)
        if api_key:
            params["apikey"] = api_key
        elif endpoint == "customer":
            raise RuntimeError(
                f"Open-Meteo customer metadata endpoint configured, but {api_key_env!r} is not set."
            )

    response = requests.get(
        _metadata_url(provider.metadata_model, endpoint),
        params=params,
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError(f"Unexpected Open-Meteo metadata response for {provider.metadata_model!r}: {payload!r}")
    return payload


def _availability_row(
    provider: ProviderMetadata,
    payload: dict,
    *,
    audit_date: date,
    check_deadline: pd.Timestamp,
    expected_run: pd.Timestamp,
    observed_at: pd.Timestamp,
    safety_buffer_minutes: int,
) -> dict:
    initialisation = _utc_datetime_from_unix(payload.get("last_run_initialisation_time"))
    modification = _utc_datetime_from_unix(payload.get("last_run_modification_time"))
    availability = _utc_datetime_from_unix(payload.get("last_run_availability_time"))
    effective_availability = (
        availability + pd.Timedelta(minutes=safety_buffer_minutes)
        if availability is not None
        else None
    )

    target_run_available = (
        initialisation is not None
        and availability is not None
        and initialisation >= expected_run
        and effective_availability <= check_deadline
    )
    latest_available_before_check = (
        availability is not None
        and effective_availability <= check_deadline
    )

    if target_run_available:
        status = "target_run_available"
    elif latest_available_before_check:
        status = "older_run_available"
    else:
        status = "not_available_by_check"

    return {
        "audit_date": audit_date.isoformat(),
        "observed_at_utc": observed_at.isoformat(),
        "check_deadline_utc": check_deadline.isoformat(),
        "provider": provider.provider,
        "provider_group": provider.provider_group,
        "forecast_model": provider.forecast_model,
        "metadata_model": provider.metadata_model,
        "expected_run_utc": expected_run.isoformat(),
        "last_run_initialisation_utc": initialisation.isoformat() if initialisation is not None else "",
        "last_run_availability_utc": availability.isoformat() if availability is not None else "",
        "availability_with_buffer_utc": (
            effective_availability.isoformat() if effective_availability is not None else ""
        ),
        "last_run_modification_utc": modification.isoformat() if modification is not None else "",
        "target_run_available_by_check": target_run_available,
        "latest_run_available_by_check": latest_available_before_check,
        "minutes_available_before_check": (
            (check_deadline - effective_availability).total_seconds() / 60
            if effective_availability is not None
            else pd.NA
        ),
        "run_lag_hours_vs_expected": (
            (expected_run - initialisation).total_seconds() / 3600
            if initialisation is not None
            else pd.NA
        ),
        "temporal_resolution_seconds": payload.get("temporal_resolution_seconds", pd.NA),
        "update_interval_seconds": payload.get("update_interval_seconds", pd.NA),
        "status": status,
    }


def run_open_meteo_availability_audit(
    *,
    output_file: Path,
    audit_date: date,
    target_tz: str,
    check_time: time,
    target_run_hour_utc: int,
    safety_buffer_minutes: int,
    endpoint: str,
    api_key_env: str | None,
    timeout_seconds: int,
) -> pd.DataFrame:
    tz = ZoneInfo(target_tz)
    check_deadline = pd.Timestamp(datetime.combine(audit_date, check_time, tzinfo=tz)).tz_convert("UTC")
    expected_run = pd.Timestamp(
        datetime(audit_date.year, audit_date.month, audit_date.day, target_run_hour_utc, tzinfo=ZoneInfo("UTC"))
    )
    observed_at = pd.Timestamp.now(tz="UTC")

    rows: list[dict] = []
    for provider in DEFAULT_PROVIDERS:
        try:
            payload = _fetch_metadata(
                provider,
                endpoint=endpoint,
                api_key_env=api_key_env,
                timeout_seconds=timeout_seconds,
            )
            row = _availability_row(
                provider,
                payload,
                audit_date=audit_date,
                check_deadline=check_deadline,
                expected_run=expected_run,
                observed_at=observed_at,
                safety_buffer_minutes=safety_buffer_minutes,
            )
        except Exception as exc:  # Keep the daily audit useful even if one provider is down.
            row = {
                "audit_date": audit_date.isoformat(),
                "observed_at_utc": observed_at.isoformat(),
                "check_deadline_utc": check_deadline.isoformat(),
                "provider": provider.provider,
                "provider_group": provider.provider_group,
                "forecast_model": provider.forecast_model,
                "metadata_model": provider.metadata_model,
                "expected_run_utc": expected_run.isoformat(),
                "last_run_initialisation_utc": "",
                "last_run_availability_utc": "",
                "availability_with_buffer_utc": "",
                "last_run_modification_utc": "",
                "target_run_available_by_check": False,
                "latest_run_available_by_check": False,
                "minutes_available_before_check": pd.NA,
                "run_lag_hours_vs_expected": pd.NA,
                "temporal_resolution_seconds": pd.NA,
                "update_interval_seconds": pd.NA,
                "status": "metadata_request_failed",
                "error": f"{type(exc).__name__}: {exc}",
            }
        rows.append(row)

    df = pd.DataFrame(rows)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    if output_file.exists():
        existing = pd.read_csv(output_file)
        df = pd.concat([existing, df], ignore_index=True)
    df.to_csv(output_file, index=False)
    return pd.DataFrame(rows)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Log Open-Meteo model-run availability for the operational wind provider ensemble."
    )
    parser.add_argument("--output-file", type=Path, default=DEFAULT_OUTPUT_FILE)
    parser.add_argument("--date", type=date.fromisoformat, default=None, help="Audit date in YYYY-MM-DD.")
    parser.add_argument("--target-tz", default=DEFAULT_TARGET_TZ)
    parser.add_argument("--check-time", type=_parse_hhmm, default=_parse_hhmm(DEFAULT_CHECK_TIME))
    parser.add_argument("--target-run-hour-utc", type=int, default=DEFAULT_TARGET_RUN_HOUR_UTC)
    parser.add_argument("--safety-buffer-minutes", type=int, default=DEFAULT_SAFETY_BUFFER_MINUTES)
    parser.add_argument("--endpoint", choices=("customer", "public"), default="customer")
    parser.add_argument("--api-key-env", default=DEFAULT_API_KEY_ENV)
    parser.add_argument("--timeout-seconds", type=int, default=30)
    return parser


def main() -> None:
    load_dotenv(find_repo_root() / ".env")
    args = build_parser().parse_args()
    repo_root = find_repo_root()
    audit_date = args.date or datetime.now(ZoneInfo(args.target_tz)).date()
    output_file = resolve_path(args.output_file, repo_root)
    rows = run_open_meteo_availability_audit(
        output_file=output_file,
        audit_date=audit_date,
        target_tz=args.target_tz,
        check_time=args.check_time,
        target_run_hour_utc=args.target_run_hour_utc,
        safety_buffer_minutes=args.safety_buffer_minutes,
        endpoint=args.endpoint,
        api_key_env=args.api_key_env,
        timeout_seconds=args.timeout_seconds,
    )
    print(rows[["forecast_model", "last_run_initialisation_utc", "last_run_availability_utc", "status"]].to_string(index=False))
    print(f"Saved Open-Meteo availability audit -> {output_file}")


if __name__ == "__main__":
    main()
