from __future__ import annotations

import argparse
import copy
import json
import time
from dataclasses import dataclass
from datetime import date, datetime, time as datetime_time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from ..config import LearOperationalConfig, RunConfig, validate_config_payload
from ..paths import find_repo_root, resolve_path
from .energy_arena_daily import run_point_base_forecasts, tomorrow_in_tz
from .energy_arena_price_final_daily import (
    DEFAULT_CHALLENGE_ID_ENV,
    _build_submission_payload,
    _config_body,
    _load_payload,
    _mutate_first_stage_payload,
    _mutate_price_payload,
    _price_train_days,
    _resolve_challenge_id,
    _retry_deadline,
    _run_first_stage_payload,
    _write_yaml,
)
from .run import run_from_config


DEFAULT_WORK_ROOT = Path("results/energy_arena_work/price_cutoff_grid")
DEFAULT_LOAD_CHALLENGE_ID_ENV = "ENERGY_ARENA_LOAD_CHALLENGE_ID"
DEFAULT_SOLAR_CHALLENGE_ID_ENV = "ENERGY_ARENA_SOLAR_CHALLENGE_ID"
DEFAULT_WIND_CHALLENGE_ID_ENV = "ENERGY_ARENA_WIND_CHALLENGE_ID"


@dataclass(frozen=True)
class CutoffSpec:
    label: str
    price_config: Path
    load_config: Path
    solar_config: Path
    wind_config: Path
    approach_name: str
    approach_description: str


CUTOFF_SPECS: dict[str, CutoffSpec] = {
    "0700": CutoffSpec(
        label="0700",
        price_config=Path("configs/rq3_cutoff_grid/price_0700_noexaa_direct_load_renewables_weather_c2_run00_d70.yaml"),
        load_config=Path("configs/rq3_cutoff_grid/load_0700_direct_open_meteo_icon_d2_run00_morning0615_tw224_f180.yaml"),
        solar_config=Path("configs/rq3_cutoff_grid/solar_0700_dwd_mastr_tso_c25_run00_cloud_geometry_physics_morning0615_d90.yaml"),
        wind_config=Path("configs/rq3_cutoff_grid/wind_0700_dwd_mastr_c100_multi_provider7_run00_p80_morning0615_d180.yaml"),
        approach_name="price_cutoff_0700_noexaa_direct_pgen_lightgbm_c2_d70",
        approach_description=(
            "Operational 07:00 cutoff adaptation with own direct load, solar, and wind forecasts "
            "using weather available from the 00 UTC run. This is distinct from the paper's "
            "retrospective 06 UTC early-cutoff backtest."
        ),
    ),
    "0800": CutoffSpec(
        label="0800",
        price_config=Path("configs/rq3_cutoff_grid/price_0800_noexaa_direct_load_renewables_weather_c2_run00_d70.yaml"),
        load_config=Path("configs/rq3_cutoff_grid/load_0800_direct_open_meteo_icon_d2_run00_morning0715_tw224_f180.yaml"),
        solar_config=Path("configs/rq3_cutoff_grid/solar_0800_dwd_mastr_tso_c25_run00_cloud_geometry_physics_morning0715_d90.yaml"),
        wind_config=Path("configs/rq3_cutoff_grid/wind_0800_dwd_mastr_c100_multi_provider7_run00_p80_morning0715_d180.yaml"),
        approach_name="price_cutoff_0800_noexaa_direct_pgen_lightgbm_c2_d70",
        approach_description=(
            "Operational 08:00 cutoff adaptation with own direct load, solar, and wind forecasts "
            "using weather available from the 00 UTC run. This is distinct from the paper's "
            "retrospective 06 UTC early-cutoff backtest."
        ),
    ),
    "0900": CutoffSpec(
        label="0900",
        price_config=Path("configs/rq3_cutoff_grid/price_0900_noexaa_direct_load_renewables_weather_c2_run00_d70.yaml"),
        load_config=Path("configs/rq3_cutoff_grid/load_0900_direct_open_meteo_icon_d2_run00_morning0815_tw224_f180.yaml"),
        solar_config=Path("configs/rq3_cutoff_grid/solar_0900_dwd_mastr_tso_c25_run00_cloud_geometry_physics_morning0815_d90.yaml"),
        wind_config=Path("configs/rq3_cutoff_grid/wind_0900_dwd_mastr_c100_multi_provider7_run00_p80_morning0815_d180.yaml"),
        approach_name="price_cutoff_0900_noexaa_direct_pgen_lightgbm_c2_d70",
        approach_description=(
            "Operational 09:00 cutoff adaptation with own direct load, solar, and wind forecasts "
            "using weather available from the 00 UTC run. This is distinct from the paper's "
            "retrospective 06 UTC early-cutoff backtest."
        ),
    ),
    "1000": CutoffSpec(
        label="1000",
        price_config=Path("configs/rq3_cutoff_grid/price_1000_noexaa_direct_load_renewables_weather_c2_run06_d70.yaml"),
        load_config=Path("configs/rq3_cutoff_grid/load_1000_direct_open_meteo_icon_d2_run06_morning0915_tw224_f180.yaml"),
        solar_config=Path("configs/rq3_cutoff_grid/solar_1000_dwd_mastr_tso_c25_run06_cloud_geometry_physics_morning0915_d90.yaml"),
        wind_config=Path("configs/rq3_cutoff_grid/wind_1000_dwd_mastr_c100_multi_provider7_run06_p80_morning0915_d180.yaml"),
        approach_name="price_cutoff_1000_noexaa_direct_pgen_lightgbm_c2_d70",
        approach_description="RQ3 10:00 cutoff price model with own direct load, solar, and wind forecasts.",
    ),
    "1100": CutoffSpec(
        label="1100",
        price_config=Path("configs/rq3_cutoff_grid/price_1100_noexaa_residual_load_renewables_weather_c2_run06_d70.yaml"),
        load_config=Path("configs/rq3_cutoff_grid/load_1100_residual_open_meteo_icon_d2_run06_morning1015_tw224_f180.yaml"),
        solar_config=Path("configs/rq3_cutoff_grid/solar_1100_dwd_mastr_tso_c25_run06_cloud_geometry_physics_morning1015_d90.yaml"),
        wind_config=Path("configs/rq3_cutoff_grid/wind_1100_dwd_mastr_c100_multi_provider7_run06_p80_morning1015_d180.yaml"),
        approach_name="price_cutoff_1100_noexaa_residual_pgen_lightgbm_c2_d70",
        approach_description="RQ3 11:00 cutoff price model with own residual load, solar, and wind forecasts.",
    ),
    "1200": CutoffSpec(
        label="1200",
        price_config=Path("configs/rq3_cutoff_grid/price_1200_exaa_residual_load_renewables_weather_c2_run06_d70.yaml"),
        load_config=Path("configs/rq3_cutoff_grid/load_1200_residual_open_meteo_icon_d2_run06_morning1115_tw224_f180.yaml"),
        solar_config=Path("configs/rq3_cutoff_grid/solar_1200_dwd_mastr_tso_c25_run06_cloud_geometry_physics_morning1115_d90.yaml"),
        wind_config=Path("configs/rq3_cutoff_grid/wind_1200_dwd_mastr_c100_multi_provider7_run06_p80_morning1115_d180.yaml"),
        approach_name="price_cutoff_1200_exaa_residual_pgen_lightgbm_c2_d70",
        approach_description="RQ3 12:00 cutoff price model with EXAA plus own residual load, solar, and wind forecasts.",
    ),
}


@dataclass(frozen=True)
class CutoffDailyPaths:
    work_dir: Path
    generated_config_dir: Path
    price_export_dir: Path

    @property
    def submission_config(self) -> Path:
        return self.generated_config_dir / "energy_arena_price_cutoff_submission.generated.yaml"

    def first_stage_submission_config(self, label: str) -> Path:
        return self.generated_config_dir / f"energy_arena_{label}_cutoff_submission.generated.yaml"


def cutoff_work_paths(repo_root: Path, forecast_date: date, cutoff: str, work_root: Path | None = None) -> CutoffDailyPaths:
    root = (work_root or DEFAULT_WORK_ROOT)
    if not root.is_absolute():
        root = repo_root / root
    work_dir = root / cutoff / forecast_date.isoformat()
    return CutoffDailyPaths(
        work_dir=work_dir,
        generated_config_dir=work_dir / "generated_configs",
        price_export_dir=work_dir / "price_forecast",
    )


def _price_payload_with_cutoff_export(price_payload: dict, paths: CutoffDailyPaths, cutoff: str) -> dict:
    updated = copy.deepcopy(price_payload)
    config = dict(updated["config"])
    config["export_dir"] = str(paths.price_export_dir)
    config["experiment_name"] = f"{config.get('experiment_name', paths.price_export_dir.name)}_{cutoff}_daily"
    updated["config"] = config
    return updated


def _forecast_file_from_payload(payload: dict, repo_root: Path) -> Path:
    export_dir = _config_body(payload).get("export_dir")
    if not export_dir:
        raise ValueError("First-stage config must define export_dir to submit its forecast.")
    return resolve_path(Path(export_dir), repo_root) / "forecast.csv"


def _build_first_stage_submission_payload(
    *,
    forecast_path: Path,
    forecast_date: date,
    challenge_id: int,
    submit: bool,
    target_tz: str,
    value_column: str,
    source_name: str,
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
                "name": source_name,
                "value_column": value_column,
            },
            "forecast_date": forecast_date.isoformat(),
            "challenge_id": challenge_id,
            "target_tz": target_tz,
            "objective": "point",
            "value_column": value_column,
            "forecast_visibility": "closed",
            "leaderboard_visibility": "public",
            "approach_name": approach_name,
            "approach_description": approach_description,
            "artifacts_dir": "results/energy_arena_submissions",
            "enable_operational_fallback": True,
        },
    }


def _first_stage_submission_specs(
    *,
    cutoff: str,
    load_challenge_id: int,
    solar_challenge_id: int,
    wind_challenge_id: int,
) -> dict[str, dict[str, str | int]]:
    early_operational = cutoff in {"0700", "0800", "0900"}
    scope = "Operational" if early_operational else "RQ3"
    weather_note = " using the admissible 00 UTC weather run" if early_operational else ""
    return {
        "load": {
            "challenge_id": load_challenge_id,
            "value_column": "Load_Model_MW",
            "source_name": f"load_cutoff_{cutoff}",
            "approach_name": f"load_cutoff_{cutoff}_first_stage",
            "approach_description": (
                f"{scope} {cutoff} cutoff own load forecast{weather_note}, used by the final price model."
            ),
        },
        "solar": {
            "challenge_id": solar_challenge_id,
            "value_column": "Solar_Model_MW",
            "source_name": f"solar_cutoff_{cutoff}",
            "approach_name": f"solar_cutoff_{cutoff}_first_stage",
            "approach_description": (
                f"{scope} {cutoff} cutoff own solar generation forecast{weather_note}, used by the final price model."
            ),
        },
        "wind": {
            "challenge_id": wind_challenge_id,
            "value_column": "Wind_Onshore_Model_MW",
            "source_name": f"wind_onshore_cutoff_{cutoff}",
            "approach_name": f"wind_onshore_cutoff_{cutoff}_first_stage",
            "approach_description": (
                f"{scope} {cutoff} cutoff own onshore wind forecast{weather_note}, used by the final price model."
            ),
        },
    }


def run_daily_price_cutoff_energy_arena(
    *,
    cutoff: str,
    challenge_id: int | None = None,
    load_challenge_id: int | None = None,
    solar_challenge_id: int | None = None,
    wind_challenge_id: int | None = None,
    load_challenge_id_env: str = DEFAULT_LOAD_CHALLENGE_ID_ENV,
    solar_challenge_id_env: str = DEFAULT_SOLAR_CHALLENGE_ID_ENV,
    wind_challenge_id_env: str = DEFAULT_WIND_CHALLENGE_ID_ENV,
    forecast_date: date | None = None,
    target_tz: str = "Europe/Berlin",
    work_root: Path | None = None,
    submit: bool = True,
    submit_first_stage: bool = False,
    refresh_first_stage: bool = True,
    fallback_to_cached_first_stage: bool = True,
    first_stage_history_days: int | None = None,
    point_history_days: int = 0,
) -> CutoffDailyPaths:
    repo_root = find_repo_root()
    spec = CUTOFF_SPECS[cutoff]
    day = forecast_date or tomorrow_in_tz(target_tz)
    paths = cutoff_work_paths(repo_root=repo_root, forecast_date=day, cutoff=cutoff, work_root=work_root)
    resolved_challenge_id = _resolve_challenge_id(challenge_id, DEFAULT_CHALLENGE_ID_ENV, repo_root)
    first_stage_submission_specs: dict[str, dict[str, str | int]] = {}
    if submit_first_stage:
        first_stage_submission_specs = _first_stage_submission_specs(
            cutoff=cutoff,
            load_challenge_id=_resolve_challenge_id(load_challenge_id, load_challenge_id_env, repo_root),
            solar_challenge_id=_resolve_challenge_id(solar_challenge_id, solar_challenge_id_env, repo_root),
            wind_challenge_id=_resolve_challenge_id(wind_challenge_id, wind_challenge_id_env, repo_root),
        )

    raw_price_payload = _load_payload(spec.price_config, repo_root)
    price_train_days = _price_train_days(raw_price_payload)
    first_stage_days = first_stage_history_days if first_stage_history_days is not None else price_train_days + point_history_days
    first_stage_start = day - timedelta(days=first_stage_days)

    print(f"Daily RQ3 cutoff Energy Arena price run for cutoff={cutoff} forecast_date={day.isoformat()}")
    print(f"Working directory: {paths.work_dir}")
    print(f"Price model: {spec.price_config}")
    print(f"First-stage cache window: {first_stage_start.isoformat()} -> {day.isoformat()}")

    first_stage_payloads: dict[str, dict] = {}
    if refresh_first_stage:
        for label, config_path in (
            ("load", spec.load_config),
            ("solar", spec.solar_config),
            ("wind", spec.wind_config),
        ):
            print(f"\n--- Refreshing RQ3 {cutoff} first-stage {label} forecast cache ---")
            payload = _mutate_first_stage_payload(
                _load_payload(config_path, repo_root),
                forecast_date=day,
                history_start=first_stage_start,
                target_tz=target_tz,
            )
            first_stage_payloads[label] = payload
            try:
                _run_first_stage_payload(payload, repo_root=repo_root, forecast_date=day)
            except Exception as exc:
                if not fallback_to_cached_first_stage:
                    raise
                print(
                    f"[fallback] RQ3 {cutoff} first-stage {label} refresh failed, using existing cached "
                    f"forecast CSVs from the price config if available: {exc}",
                    flush=True,
                )
    else:
        print(f"[cache] Reusing existing RQ3 {cutoff} first-stage load/solar/wind forecast CSVs.")
        for label, config_path in (
            ("load", spec.load_config),
            ("solar", spec.solar_config),
            ("wind", spec.wind_config),
        ):
            first_stage_payloads[label] = _mutate_first_stage_payload(
                _load_payload(config_path, repo_root),
                forecast_date=day,
                history_start=first_stage_start,
                target_tz=target_tz,
            )

    first_stage_submissions: dict[str, dict[str, int | str | bool]] = {}
    if submit_first_stage:
        print("\n--- Building Energy Arena RQ3 cutoff first-stage submissions ---")
        for label in ("load", "solar", "wind"):
            forecast_path = _forecast_file_from_payload(first_stage_payloads[label], repo_root)
            submission_spec = first_stage_submission_specs[label]
            payload = _build_first_stage_submission_payload(
                forecast_path=forecast_path,
                forecast_date=day,
                challenge_id=int(submission_spec["challenge_id"]),
                submit=submit,
                target_tz=target_tz,
                value_column=str(submission_spec["value_column"]),
                source_name=str(submission_spec["source_name"]),
                approach_name=str(submission_spec["approach_name"]),
                approach_description=str(submission_spec["approach_description"]),
            )
            submission_config = paths.first_stage_submission_config(label)
            _write_yaml(submission_config, payload)
            run_from_config(validate_config_payload(payload, RunConfig, repo_root=repo_root), submit_override=submit)
            first_stage_submissions[label] = {
                "challenge_id": int(submission_spec["challenge_id"]),
                "value_column": str(submission_spec["value_column"]),
                "forecast_path": str(forecast_path),
                "submission_config": str(submission_config),
                "submit": submit,
            }

    price_payload = _mutate_price_payload(
        raw_price_payload,
        forecast_date=day,
        point_history_days=point_history_days,
        export_dir=paths.price_export_dir,
        target_tz=target_tz,
    )
    price_payload = _price_payload_with_cutoff_export(price_payload, paths, cutoff)
    price_config = validate_config_payload(price_payload["config"], LearOperationalConfig, repo_root=repo_root)

    print("\n--- Running RQ3 cutoff price forecast ---")
    try:
        forecast_path = run_point_base_forecasts(
            lear_config=price_config,
            forecast_date=day,
            history_days=point_history_days,
            export_dir=paths.price_export_dir,
        )
    except Exception as exc:
        forecast_path = paths.price_export_dir / "forecast.csv"
        if not forecast_path.exists():
            raise
        print(
            "[fallback] RQ3 cutoff price model refresh failed; using cached forecast CSV "
            f"{forecast_path}: {exc}",
            flush=True,
        )

    payload = _build_submission_payload(
        forecast_path=forecast_path,
        forecast_date=day,
        challenge_id=resolved_challenge_id,
        submit=submit,
        target_tz=target_tz,
        approach_name=spec.approach_name,
        approach_description=spec.approach_description,
    )
    _write_yaml(paths.submission_config, payload)

    print("\n--- Building Energy Arena RQ3 cutoff price submission ---")
    run_config = validate_config_payload(payload, RunConfig, repo_root=repo_root)
    run_from_config(run_config, submit_override=submit)

    paths.work_dir.mkdir(parents=True, exist_ok=True)
    with open(paths.work_dir / "daily_run.json", "w", encoding="utf-8") as handle:
        json.dump(
            {
                "forecast_date": day.isoformat(),
                "cutoff": cutoff,
                "submit": submit,
                "challenge_id": resolved_challenge_id,
                "challenge_id_env": DEFAULT_CHALLENGE_ID_ENV,
                "submit_first_stage": submit_first_stage,
                "first_stage_submissions": first_stage_submissions,
                "price_config_path": str(spec.price_config),
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


def run_daily_price_cutoff_energy_arena_with_retries(
    *,
    cutoff: str,
    challenge_id: int | None,
    load_challenge_id: int | None,
    solar_challenge_id: int | None,
    wind_challenge_id: int | None,
    load_challenge_id_env: str,
    solar_challenge_id_env: str,
    wind_challenge_id_env: str,
    forecast_date: date | None,
    target_tz: str,
    work_root: Path | None,
    submit: bool,
    submit_first_stage: bool,
    refresh_first_stage: bool,
    fallback_to_cached_first_stage: bool,
    first_stage_history_days: int | None,
    point_history_days: int,
    retry_until: datetime_time | None,
    retry_interval_minutes: float,
) -> CutoffDailyPaths:
    deadline = _retry_deadline(datetime.now(ZoneInfo(target_tz)), retry_until, target_tz)
    interval_seconds = max(retry_interval_minutes, 0.1) * 60
    attempt = 1

    while True:
        try:
            return run_daily_price_cutoff_energy_arena(
                cutoff=cutoff,
                challenge_id=challenge_id,
                load_challenge_id=load_challenge_id,
                solar_challenge_id=solar_challenge_id,
                wind_challenge_id=wind_challenge_id,
                load_challenge_id_env=load_challenge_id_env,
                solar_challenge_id_env=solar_challenge_id_env,
                wind_challenge_id_env=wind_challenge_id_env,
                forecast_date=forecast_date,
                target_tz=target_tz,
                work_root=work_root,
                submit=submit,
                submit_first_stage=submit_first_stage,
                refresh_first_stage=refresh_first_stage,
                fallback_to_cached_first_stage=fallback_to_cached_first_stage,
                first_stage_history_days=first_stage_history_days,
                point_history_days=point_history_days,
            )
        except Exception as exc:
            now = datetime.now(ZoneInfo(target_tz))
            if deadline is None or now + timedelta(seconds=interval_seconds) > deadline:
                print(f"Daily RQ3 cutoff {cutoff} attempt {attempt} failed and no retries remain: {exc}", flush=True)
                raise

            next_attempt = now + timedelta(seconds=interval_seconds)
            print(
                f"Daily RQ3 cutoff {cutoff} attempt {attempt} failed: {exc}\n"
                f"Retrying at {next_attempt.isoformat()} until {deadline.isoformat()}.",
                flush=True,
            )
            attempt += 1
            time.sleep(interval_seconds)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one RQ3 cutoff-grid Energy Arena price submission workflow.")
    parser.add_argument("--cutoff", choices=sorted(CUTOFF_SPECS), required=True)
    parser.add_argument("--challenge-id", type=int, default=None)
    parser.add_argument("--load-challenge-id", type=int, default=None)
    parser.add_argument("--solar-challenge-id", type=int, default=None)
    parser.add_argument("--wind-challenge-id", type=int, default=None)
    parser.add_argument("--load-challenge-id-env", default=DEFAULT_LOAD_CHALLENGE_ID_ENV)
    parser.add_argument("--solar-challenge-id-env", default=DEFAULT_SOLAR_CHALLENGE_ID_ENV)
    parser.add_argument("--wind-challenge-id-env", default=DEFAULT_WIND_CHALLENGE_ID_ENV)
    parser.add_argument("--forecast-date", type=date.fromisoformat, default=None, help="Target date; defaults to tomorrow.")
    parser.add_argument("--target-tz", default="Europe/Berlin")
    parser.add_argument("--work-root", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true", help="Generate payloads but do not submit to Energy Arena.")
    parser.add_argument(
        "--submit-first-stage",
        action="store_true",
        help="Also submit the regenerated or cached load, solar, and onshore wind forecasts for this cutoff.",
    )
    parser.add_argument(
        "--skip-first-stage-refresh",
        action="store_true",
        help="Reuse existing generated cutoff load/solar/wind forecast CSVs instead of refreshing them first.",
    )
    parser.add_argument(
        "--no-fallback-to-cached-first-stage",
        action="store_true",
        help=(
            "Fail immediately if a cutoff load/solar/wind first-stage refresh fails. "
            "By default the runner logs a fallback and tries existing cached CSVs."
        ),
    )
    parser.add_argument(
        "--first-stage-history-days",
        type=int,
        default=None,
        help="Generated load/solar/wind forecast cache window. Defaults to price train days plus point history days.",
    )
    parser.add_argument("--point-history-days", type=int, default=0)
    parser.add_argument("--retry-until", type=_parse_retry_until, default=None)
    parser.add_argument("--retry-interval-minutes", type=float, default=10.0)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    run_daily_price_cutoff_energy_arena_with_retries(
        cutoff=args.cutoff,
        challenge_id=args.challenge_id,
        load_challenge_id=args.load_challenge_id,
        solar_challenge_id=args.solar_challenge_id,
        wind_challenge_id=args.wind_challenge_id,
        load_challenge_id_env=args.load_challenge_id_env,
        solar_challenge_id_env=args.solar_challenge_id_env,
        wind_challenge_id_env=args.wind_challenge_id_env,
        forecast_date=args.forecast_date,
        target_tz=args.target_tz,
        work_root=args.work_root,
        submit=not args.dry_run,
        submit_first_stage=args.submit_first_stage,
        refresh_first_stage=not args.skip_first_stage_refresh,
        fallback_to_cached_first_stage=not args.no_fallback_to_cached_first_stage,
        first_stage_history_days=args.first_stage_history_days,
        point_history_days=args.point_history_days,
        retry_until=args.retry_until,
        retry_interval_minutes=args.retry_interval_minutes,
    )


if __name__ == "__main__":
    main()
