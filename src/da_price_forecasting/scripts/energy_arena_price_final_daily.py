from __future__ import annotations

import argparse
import copy
import json
import os
import time
from dataclasses import dataclass
from datetime import date, datetime, time as datetime_time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from ..config import LearOperationalConfig, RenewableGenerationModelConfig, RunConfig, load_config_payload
from ..config import validate_config_payload
from ..paths import find_repo_root, resolve_path
from .energy_arena_daily import day_bounds, run_point_base_forecasts, tomorrow_in_tz
from .energy_arena_renewable_daily import update_actual_generation_cache
from .run import run_from_config


DEFAULT_PRICE_CONFIG = Path("configs/pricebase_sweep/oos_pgen_c2_d70.yaml")
DEFAULT_LOAD_INPUT_CONFIG = Path(
    "configs/final/load/price_inputs/"
    "load_forecast_hybrid_entsoe_residual_open_meteo_p10_morning1015_daily_weather_lightgbm_"
    "price_warmup_d70_nov23febjul_tw224_f180_pop_weighted_quantiles.yaml"
)
DEFAULT_SOLAR_INPUT_CONFIG = Path(
    "configs/final/renewable/price_inputs/"
    "renewable_generation_dwd_icon_mastr_solar_tso_c25_run06_tso_components_cloud_geometry_physics_"
    "residual_own_region_daylight_suspicious_totalbias_hgb_solar_bias45_hour_s075_d90_cutoff1000_"
    "price_warmup_d70_nov23febjul.yaml"
)
DEFAULT_WIND_INPUT_CONFIG = Path(
    "configs/final/renewable/price_inputs/"
    "renewable_generation_hybrid_dwd_mastr_wind_c100_multi_provider7_run06_summary_meanstd_onoff_split_"
    "wind_hub_p80_common_hgb_wind_struct_minleaf60_maxfeat08_bias30_mtu_s08_d180_cutoff1000_"
    "price_warmup_d70_nov23febjul.yaml"
)
DEFAULT_WORK_ROOT = Path("results/energy_arena_work/price_final_pgen")
DEFAULT_CHALLENGE_ID_ENV = "ENERGY_ARENA_PRICE_CHALLENGE_ID"


@dataclass(frozen=True)
class DailyPricePaths:
    work_dir: Path
    generated_config_dir: Path
    price_export_dir: Path

    @property
    def submission_config(self) -> Path:
        return self.generated_config_dir / "energy_arena_price_final_submission.generated.yaml"


def dated_price_work_paths(
    repo_root: Path,
    forecast_date: date,
    work_root: Path | None = None,
) -> DailyPricePaths:
    root = resolve_path(work_root or DEFAULT_WORK_ROOT, repo_root)
    work_dir = root / forecast_date.isoformat()
    return DailyPricePaths(
        work_dir=work_dir,
        generated_config_dir=work_dir / "generated_configs",
        price_export_dir=work_dir / "price_forecast",
    )


def _write_yaml(path: Path, payload: dict) -> None:
    import yaml

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        yaml.safe_dump(payload, handle, sort_keys=False)


def _load_payload(path: Path, repo_root: Path) -> dict:
    payload = load_config_payload(resolve_path(path, repo_root))
    if not isinstance(payload, dict):
        raise TypeError(f"Expected config mapping in {path}.")
    return payload


def _config_body(payload: dict) -> dict:
    config = payload.get("config")
    if not isinstance(config, dict):
        raise ValueError("Expected a top-level config mapping.")
    return config


def _local_day_start(day: date, target_tz: str) -> str:
    return datetime.combine(day, datetime_time.min, tzinfo=ZoneInfo(target_tz)).isoformat()


def _mutate_first_stage_payload(
    payload: dict,
    *,
    forecast_date: date,
    history_start: date,
    target_tz: str,
) -> dict:
    updated = copy.deepcopy(payload)
    config = dict(_config_body(updated))
    config["test_start"] = history_start.isoformat()
    config["test_end"] = forecast_date.isoformat()
    if "entsoe_end_date" in config:
        config["entsoe_end_date"] = forecast_date.isoformat()
    if "open_meteo_end_date" in config:
        config["open_meteo_end_date"] = forecast_date.isoformat()
    config.setdefault("target_tz", target_tz)
    updated["config"] = config
    return updated


def _mutate_price_payload(
    payload: dict,
    *,
    forecast_date: date,
    point_history_days: int,
    export_dir: Path,
    target_tz: str,
) -> dict:
    updated = copy.deepcopy(payload)
    config = dict(_config_body(updated))
    start, end = day_bounds(forecast_date, target_tz)
    config["entsoe_end_date"] = start
    config["test_start"] = _local_day_start(forecast_date - timedelta(days=point_history_days), target_tz)
    config["test_end"] = end
    config["export_dir"] = str(export_dir)
    config.setdefault("target_tz", target_tz)
    updated["config"] = config
    return updated


def _resolve_challenge_id(challenge_id: int | None, env_var: str, repo_root: Path) -> int:
    if challenge_id is not None:
        return int(challenge_id)

    load_dotenv(repo_root / ".env")
    raw_value = os.getenv(env_var)
    if not raw_value:
        raise ValueError(f"Pass --challenge-id or set {env_var}=<price challenge id> in .env.")
    try:
        return int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{env_var} must be an integer challenge id, got {raw_value!r}.") from exc


def _run_first_stage_payload(payload: dict, repo_root: Path, forecast_date: date) -> None:
    if payload.get("kind") == "renewable_generation_model":
        renewable_config = validate_config_payload(
            _config_body(payload),
            RenewableGenerationModelConfig,
            repo_root=repo_root,
        )
        update_actual_generation_cache(renewable_config, forecast_date=forecast_date)

    run_config = validate_config_payload(payload, RunConfig, repo_root=repo_root)
    run_from_config(run_config)


def _price_train_days(price_payload: dict) -> int:
    return int(_config_body(price_payload).get("train_days_rolling", 70))


def _build_submission_payload(
    *,
    forecast_path: Path,
    forecast_date: date,
    challenge_id: int,
    submit: bool,
    target_tz: str,
    approach_name: str,
    approach_description: str,
) -> dict:
    return {
        "kind": "energy_arena_submit",
        "submit": submit,
        "config": {
            "repo_root": ".",
            "source": {
                "kind": "forecast_file",
                "path": str(forecast_path),
                "name": approach_name,
                "value_column": "y_pred",
            },
            "forecast_date": forecast_date.isoformat(),
            "challenge_id": challenge_id,
            "target_tz": target_tz,
            "objective": "point",
            "value_column": "y_pred",
            "forecast_visibility": "closed",
            "leaderboard_visibility": "public",
            "approach_name": approach_name,
            "approach_description": approach_description,
            "artifacts_dir": "results/energy_arena_submissions",
        },
    }


def run_daily_price_final_energy_arena(
    *,
    price_config_path: Path = DEFAULT_PRICE_CONFIG,
    load_input_config_path: Path = DEFAULT_LOAD_INPUT_CONFIG,
    solar_input_config_path: Path = DEFAULT_SOLAR_INPUT_CONFIG,
    wind_input_config_path: Path = DEFAULT_WIND_INPUT_CONFIG,
    challenge_id: int | None = None,
    challenge_id_env: str = DEFAULT_CHALLENGE_ID_ENV,
    forecast_date: date | None = None,
    target_tz: str = "Europe/Berlin",
    work_root: Path | None = None,
    submit: bool = True,
    refresh_first_stage: bool = True,
    fallback_to_cached_first_stage: bool = True,
    first_stage_history_days: int | None = None,
    point_history_days: int = 0,
    approach_name: str = "price_pgen_lightgbm_c2_run06_d70",
    approach_description: str = "Final paper P_gen LightGBM price model using own load, solar, and wind forecasts.",
) -> DailyPricePaths:
    repo_root = find_repo_root()
    day = forecast_date or tomorrow_in_tz(target_tz)
    paths = dated_price_work_paths(repo_root=repo_root, forecast_date=day, work_root=work_root)
    resolved_challenge_id = _resolve_challenge_id(challenge_id, challenge_id_env, repo_root)

    raw_price_payload = _load_payload(price_config_path, repo_root)
    price_train_days = _price_train_days(raw_price_payload)
    first_stage_days = first_stage_history_days if first_stage_history_days is not None else price_train_days + point_history_days
    first_stage_start = day - timedelta(days=first_stage_days)

    print(f"Daily final Energy Arena price run for forecast_date={day.isoformat()}")
    print(f"Working directory: {paths.work_dir}")
    print(f"Price model: {price_config_path}")
    print(f"First-stage cache window: {first_stage_start.isoformat()} -> {day.isoformat()}")

    if refresh_first_stage:
        for label, config_path in (
            ("load", load_input_config_path),
            ("solar", solar_input_config_path),
            ("wind", wind_input_config_path),
        ):
            print(f"\n--- Refreshing first-stage {label} forecast cache ---")
            payload = _mutate_first_stage_payload(
                _load_payload(config_path, repo_root),
                forecast_date=day,
                history_start=first_stage_start,
                target_tz=target_tz,
            )
            try:
                _run_first_stage_payload(payload, repo_root=repo_root, forecast_date=day)
            except Exception as exc:
                if not fallback_to_cached_first_stage:
                    raise
                print(
                    f"[fallback] First-stage {label} refresh failed, using existing cached forecast CSVs "
                    f"from the price config if available: {exc}",
                    flush=True,
                )
    else:
        print("[cache] Reusing existing first-stage load/solar/wind forecast CSVs.")

    price_payload = _mutate_price_payload(
        raw_price_payload,
        forecast_date=day,
        point_history_days=point_history_days,
        export_dir=paths.price_export_dir,
        target_tz=target_tz,
    )
    price_config = validate_config_payload(_config_body(price_payload), LearOperationalConfig, repo_root=repo_root)

    print("\n--- Running final P_gen price forecast ---")
    forecast_path = run_point_base_forecasts(
        lear_config=price_config,
        forecast_date=day,
        history_days=point_history_days,
        export_dir=paths.price_export_dir,
    )

    payload = _build_submission_payload(
        forecast_path=forecast_path,
        forecast_date=day,
        challenge_id=resolved_challenge_id,
        submit=submit,
        target_tz=target_tz,
        approach_name=approach_name,
        approach_description=approach_description,
    )
    _write_yaml(paths.submission_config, payload)

    print("\n--- Building Energy Arena price submission ---")
    run_config = validate_config_payload(payload, RunConfig, repo_root=repo_root)
    run_from_config(run_config, submit_override=submit)

    paths.work_dir.mkdir(parents=True, exist_ok=True)
    with open(paths.work_dir / "daily_run.json", "w", encoding="utf-8") as handle:
        json.dump(
            {
                "forecast_date": day.isoformat(),
                "submit": submit,
                "challenge_id": resolved_challenge_id,
                "price_config_path": str(price_config_path),
                "forecast_path": str(forecast_path),
                "submission_config": str(paths.submission_config),
                "refresh_first_stage": refresh_first_stage,
                "fallback_to_cached_first_stage": fallback_to_cached_first_stage,
                "first_stage_history_days": first_stage_days,
                "point_history_days": point_history_days,
            },
            handle,
            indent=2,
        )
    return paths


def _parse_retry_until(value: str | None) -> datetime_time | None:
    if value is None:
        return None
    try:
        return datetime.strptime(value, "%H:%M").time()
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--retry-until must use HH:MM, for example 11:55.") from exc


def _retry_deadline(now: datetime, retry_until: datetime_time | None, target_tz: str) -> datetime | None:
    if retry_until is None:
        return None
    tz = ZoneInfo(target_tz)
    current = now.astimezone(tz) if now.tzinfo is not None else now.replace(tzinfo=tz)
    return datetime.combine(current.date(), retry_until, tzinfo=tz)


def run_daily_price_final_energy_arena_with_retries(
    *,
    price_config_path: Path,
    load_input_config_path: Path,
    solar_input_config_path: Path,
    wind_input_config_path: Path,
    challenge_id: int | None,
    challenge_id_env: str,
    forecast_date: date | None,
    target_tz: str,
    work_root: Path | None,
    submit: bool,
    refresh_first_stage: bool,
    fallback_to_cached_first_stage: bool,
    first_stage_history_days: int | None,
    point_history_days: int,
    approach_name: str,
    approach_description: str,
    retry_until: datetime_time | None,
    retry_interval_minutes: float,
) -> DailyPricePaths:
    deadline = _retry_deadline(datetime.now(ZoneInfo(target_tz)), retry_until, target_tz)
    interval_seconds = max(retry_interval_minutes, 0.1) * 60
    attempt = 1

    while True:
        try:
            return run_daily_price_final_energy_arena(
                price_config_path=price_config_path,
                load_input_config_path=load_input_config_path,
                solar_input_config_path=solar_input_config_path,
                wind_input_config_path=wind_input_config_path,
                challenge_id=challenge_id,
                challenge_id_env=challenge_id_env,
                forecast_date=forecast_date,
                target_tz=target_tz,
                work_root=work_root,
                submit=submit,
                refresh_first_stage=refresh_first_stage,
                fallback_to_cached_first_stage=fallback_to_cached_first_stage,
                first_stage_history_days=first_stage_history_days,
                point_history_days=point_history_days,
                approach_name=approach_name,
                approach_description=approach_description,
            )
        except Exception as exc:
            now = datetime.now(ZoneInfo(target_tz))
            if deadline is None or now + timedelta(seconds=interval_seconds) > deadline:
                print(f"Daily final price attempt {attempt} failed and no retries remain: {exc}", flush=True)
                raise

            next_attempt = now + timedelta(seconds=interval_seconds)
            print(
                f"Daily final price attempt {attempt} failed: {exc}\n"
                f"Retrying at {next_attempt.isoformat()} until {deadline.isoformat()}.",
                flush=True,
            )
            attempt += 1
            time.sleep(interval_seconds)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the final paper P_gen Energy Arena price submission workflow.")
    parser.add_argument("--price-config", type=Path, default=DEFAULT_PRICE_CONFIG)
    parser.add_argument("--load-input-config", type=Path, default=DEFAULT_LOAD_INPUT_CONFIG)
    parser.add_argument("--solar-input-config", type=Path, default=DEFAULT_SOLAR_INPUT_CONFIG)
    parser.add_argument("--wind-input-config", type=Path, default=DEFAULT_WIND_INPUT_CONFIG)
    parser.add_argument("--challenge-id", type=int, default=None)
    parser.add_argument("--challenge-id-env", default=DEFAULT_CHALLENGE_ID_ENV)
    parser.add_argument("--forecast-date", type=date.fromisoformat, default=None, help="Target date; defaults to tomorrow.")
    parser.add_argument("--target-tz", default="Europe/Berlin")
    parser.add_argument("--work-root", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true", help="Generate payloads but do not submit to Energy Arena.")
    parser.add_argument(
        "--skip-first-stage-refresh",
        action="store_true",
        help="Reuse existing generated load/solar/wind forecast CSVs instead of refreshing them first.",
    )
    parser.add_argument(
        "--no-fallback-to-cached-first-stage",
        action="store_true",
        help=(
            "Fail immediately if a load/solar/wind first-stage refresh fails. "
            "By default the runner logs a fallback and tries existing cached CSVs."
        ),
    )
    parser.add_argument(
        "--first-stage-history-days",
        type=int,
        default=None,
        help="Generated load/solar/wind forecast cache window. Defaults to price train days plus point history days.",
    )
    parser.add_argument(
        "--point-history-days",
        type=int,
        default=0,
        help="Also produce prior price forecast days before the target day. Use this for later SQRA calibration.",
    )
    parser.add_argument("--approach-name", default="price_pgen_lightgbm_c2_run06_d70")
    parser.add_argument(
        "--approach-description",
        default="Final paper P_gen LightGBM price model using own load, solar, and wind forecasts.",
    )
    parser.add_argument("--retry-until", type=_parse_retry_until, default=None)
    parser.add_argument("--retry-interval-minutes", type=float, default=10.0)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    run_daily_price_final_energy_arena_with_retries(
        price_config_path=args.price_config,
        load_input_config_path=args.load_input_config,
        solar_input_config_path=args.solar_input_config,
        wind_input_config_path=args.wind_input_config,
        challenge_id=args.challenge_id,
        challenge_id_env=args.challenge_id_env,
        forecast_date=args.forecast_date,
        target_tz=args.target_tz,
        work_root=args.work_root,
        submit=not args.dry_run,
        refresh_first_stage=not args.skip_first_stage_refresh,
        fallback_to_cached_first_stage=not args.no_fallback_to_cached_first_stage,
        first_stage_history_days=args.first_stage_history_days,
        point_history_days=args.point_history_days,
        approach_name=args.approach_name,
        approach_description=args.approach_description,
        retry_until=args.retry_until,
        retry_interval_minutes=args.retry_interval_minutes,
    )


if __name__ == "__main__":
    main()
