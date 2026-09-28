from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from ..config import LearOperationalConfig, RunConfig, validate_config_payload
from ..paths import find_repo_root, resolve_path
from ..pipelines.common import load_timestamp_csv, save_timestamp_csv
from .dwd_icon_daily_update import run_dwd_icon_daily_update
from .energy_arena_daily import run_point_base_forecasts, tomorrow_in_tz
from .energy_arena_price_cutoff_daily import CUTOFF_SPECS
from .energy_arena_price_cutoff_daily import _price_payload_with_component_histories
from .energy_arena_price_final_daily import (
    DEFAULT_LOAD_INPUT_CONFIG,
    DEFAULT_PRICE_CONFIG,
    DEFAULT_SOLAR_INPUT_CONFIG,
    DEFAULT_WIND_INPUT_CONFIG,
    _build_submission_payload,
    _config_body,
    _first_stage_forecast_path,
    _load_payload,
    _mutate_first_stage_payload,
    _mutate_price_payload,
    _price_train_days,
    _resolve_challenge_id,
    _run_first_stage_payload,
    _write_yaml,
)
from .energy_arena_price_cutoff_daily import _build_first_stage_submission_payload
from .energy_arena_renewable_daily import (
    _run_feature_payload_incrementally,
    build_renewable_feature_payload,
)
from .operational_archive import DEFAULT_ARCHIVE_ROOT, MANIFEST_NAME, restore_archive
from .operational_component_history import store_component_forecast_history
from .run import run_from_config


DEFAULT_OUTPUT_ROOT = Path("results/operational_forecasts")
DEFAULT_WORK_ROOT = Path("results/operational_forecast_work")
MODEL_NAMES = ("load", "solar", "wind", "price")
VALUE_COLUMNS = {
    "load": "Load_Model_MW",
    "solar": "Solar_Model_MW",
    "wind": "Wind_Onshore_Model_MW",
    "price": "y_pred",
}
CHALLENGE_ID_ENVS = {
    "load": "ENERGY_ARENA_LOAD_CHALLENGE_ID",
    "solar": "ENERGY_ARENA_SOLAR_CHALLENGE_ID",
    "wind": "ENERGY_ARENA_WIND_CHALLENGE_ID",
    "price": "ENERGY_ARENA_PRICE_CHALLENGE_ID",
}

FINAL_LOAD_CONFIG = Path(
    "configs/final/load/"
    "load_forecast_hybrid_entsoe_residual_open_meteo_p10_morning1015_daily_weather_lightgbm_"
    "paper_febjul_tw224_f180_pop_weighted_quantiles.yaml"
)
FINAL_SOLAR_CONFIG = Path(
    "configs/final/renewable/"
    "renewable_generation_dwd_icon_mastr_solar_tso_c25_run06_tso_components_cloud_geometry_physics_"
    "residual_own_region_daylight_suspicious_totalbias_hgb_solar_bias45_hour_s075_d90_cutoff1000_"
    "paper_febjul.yaml"
)
FINAL_WIND_CONFIG = Path(
    "configs/final/renewable/"
    "renewable_generation_hybrid_dwd_mastr_wind_c100_multi_provider7_run06_summary_meanstd_onoff_split_"
    "wind_hub_p80_common_hgb_wind_struct_minleaf60_maxfeat08_bias30_mtu_s08_d180_cutoff1000_"
    "paper_febjul.yaml"
)

DWD_CONFIGS = {
    "00": {
        "price": Path("configs/deployment/cutoff_preprocessing/dwd_icon_c2_run00.yaml"),
        "solar": Path("configs/deployment/cutoff_preprocessing/dwd_solar_run00.yaml"),
        "wind": Path("configs/deployment/cutoff_preprocessing/dwd_wind_run00.yaml"),
    },
    "03": {
        "price": Path("configs/deployment/cutoff_preprocessing/dwd_icon_c2_run03.yaml"),
        "solar": Path("configs/deployment/cutoff_preprocessing/dwd_solar_run03.yaml"),
        "wind": Path("configs/deployment/cutoff_preprocessing/dwd_wind_run03.yaml"),
    },
    "06": {
        "price": Path("configs/deployment/cutoff_preprocessing/dwd_icon_c2_run06.yaml"),
        "solar": Path("configs/deployment/cutoff_preprocessing/dwd_solar_run06.yaml"),
        "wind": Path("configs/deployment/cutoff_preprocessing/dwd_wind_run06.yaml"),
    },
}

DEPLOYMENT_FEATURE_CONFIGS = {
    run: {
        "wind": (
            Path(f"configs/deployment/cutoff_preprocessing/wind_dwd_features_run{run}.yaml"),
            Path(f"configs/deployment/cutoff_preprocessing/wind_open_meteo_features_run{run}.yaml"),
        ),
        "solar": (
            Path(f"configs/deployment/cutoff_preprocessing/solar_dwd_features_run{run}.yaml"),
            Path(f"configs/deployment/cutoff_preprocessing/solar_open_meteo_features_run{run}.yaml"),
        ),
    }
    for run in ("00", "03", "06")
}

FINAL_FEATURE_CONFIGS = {
    "wind": (
        Path(
            "configs/preprocessing/renewable_features/"
            "regional_renewable_features_dwd_icon_mastr_wind_c100_run06_paper_febjul.yaml"
        ),
        *(
            Path(
                "configs/preprocessing/renewable_features/"
                f"regional_renewable_features_open_meteo_{provider}_single_run06_"
                "wind_hub_p80_provider_common_paper_febjul.yaml"
            )
            for provider in (
                "icon_d2",
                "ecmwf_ifs025",
                "arpege_europe",
                "ukmo_seamless",
                "gfs",
                "dmi_harmonie_arome_europe",
                "icon_eu",
            )
        ),
    ),
    "solar": (
        Path(
            "configs/preprocessing/renewable_features/"
            "regional_renewable_features_dwd_icon_mastr_solar_tso_c25_run06_solar_spread.yaml"
        ),
        Path(
            "configs/preprocessing/renewable_features/"
            "regional_renewable_features_open_meteo_icon_d2_single_run06_mastr_solar_tso_c25_"
            "cloud_cover.yaml"
        ),
    ),
}


@dataclass(frozen=True)
class OperationalProfile:
    name: str
    weather_run: str
    price_config: Path
    load_config: Path
    solar_config: Path
    wind_config: Path
    price_load_config: Path
    price_solar_config: Path
    price_wind_config: Path

    def model_config(self, model: str) -> Path:
        return {
            "load": self.load_config,
            "solar": self.solar_config,
            "wind": self.wind_config,
            "price": self.price_config,
        }[model]

    def price_input_configs(self) -> dict[str, Path]:
        return {
            "load": self.price_load_config,
            "solar": self.price_solar_config,
            "wind": self.price_wind_config,
        }


@dataclass(frozen=True)
class ForecastResult:
    model: str
    config_path: Path
    source_path: Path
    output_path: Path


def get_operational_profile(cutoff: str) -> OperationalProfile:
    if cutoff == "final":
        return OperationalProfile(
            name="final",
            weather_run="06",
            price_config=DEFAULT_PRICE_CONFIG,
            load_config=FINAL_LOAD_CONFIG,
            solar_config=FINAL_SOLAR_CONFIG,
            wind_config=FINAL_WIND_CONFIG,
            price_load_config=DEFAULT_LOAD_INPUT_CONFIG,
            price_solar_config=DEFAULT_SOLAR_INPUT_CONFIG,
            price_wind_config=DEFAULT_WIND_INPUT_CONFIG,
        )

    spec = CUTOFF_SPECS[cutoff]
    return OperationalProfile(
        name=cutoff,
        weather_run=spec.weather_run,
        price_config=spec.price_config,
        load_config=spec.load_config,
        solar_config=spec.solar_config,
        wind_config=spec.wind_config,
        price_load_config=spec.load_config,
        price_solar_config=spec.solar_config,
        price_wind_config=spec.wind_config,
    )


def _ensure_archive_restored(repo_root: Path) -> None:
    runtime_markers = (
        repo_root / "data/processed/load_forecast/actual_load.csv",
        repo_root / "data/processed/renewable_generation/actual_generation_2025_20260731.csv",
        repo_root / "data/processed/renewable_proxy",
        repo_root / "data/processed/icon_aggregated_c2_run06",
    )
    if all(marker.exists() for marker in runtime_markers):
        return

    archive_root = repo_root / DEFAULT_ARCHIVE_ROOT
    if not (archive_root / MANIFEST_NAME).exists():
        raise FileNotFoundError(
            "Operational runtime data is missing and no bundled archive was found. "
            "Run `git lfs pull`, then retry."
        )

    print("[bootstrap] Restoring the bundled operational data archive.", flush=True)
    status = restore_archive(
        repo_root=repo_root,
        archive_root=archive_root,
        dry_run=False,
        overwrite=False,
    )
    if status != 0:
        raise RuntimeError(f"Operational archive restore failed with status {status}.")


def _feature_configs(profile: OperationalProfile, model: str) -> tuple[Path, ...]:
    if profile.name == "final":
        return FINAL_FEATURE_CONFIGS[model]
    return DEPLOYMENT_FEATURE_CONFIGS[profile.weather_run][model]


def _refresh_feature_configs(
    config_paths: Iterable[Path],
    *,
    repo_root: Path,
    forecast_date: date,
) -> None:
    for config_path in config_paths:
        print(f"\n--- Refreshing renewable features: {config_path.name} ---")
        payload = build_renewable_feature_payload(
            feature_config_path=config_path,
            forecast_date=forecast_date,
            repo_root=repo_root,
        )
        _run_feature_payload_incrementally(payload, repo_root, forecast_date)


def _refresh_data(
    *,
    profile: OperationalProfile,
    required_models: set[str],
    repo_root: Path,
    forecast_date: date,
    target_tz: str,
) -> None:
    renewable_models = required_models.intersection({"solar", "wind"})
    dwd_models = set(renewable_models)
    if "price" in required_models:
        dwd_models.add("price")

    for model in ("wind", "price", "solar"):
        if model not in dwd_models:
            continue
        config_path = DWD_CONFIGS[profile.weather_run][model]
        print(f"\n--- Updating DWD ICON-D2 run {profile.weather_run} for {model} ---")
        run_dwd_icon_daily_update(
            config_path=config_path,
            forecast_date=forecast_date,
            target_tz=target_tz,
            catch_up_missing_days=False,
        )

    for model in ("wind", "solar"):
        if model in renewable_models:
            _refresh_feature_configs(
                _feature_configs(profile, model),
                repo_root=repo_root,
                forecast_date=forecast_date,
            )


def _run_first_stage_config(
    *,
    config_path: Path,
    repo_root: Path,
    forecast_date: date,
    history_start: date,
    target_tz: str,
) -> Path:
    payload = _mutate_first_stage_payload(
        _load_payload(config_path, repo_root),
        forecast_date=forecast_date,
        history_start=history_start,
        target_tz=target_tz,
    )
    _run_first_stage_payload(payload, repo_root=repo_root, forecast_date=forecast_date)
    forecast_path = _first_stage_forecast_path(payload, repo_root)
    if not forecast_path.exists():
        raise FileNotFoundError(f"Forecast CSV was not created: {forecast_path}")
    return forecast_path


def _run_price_config(
    *,
    profile: OperationalProfile,
    repo_root: Path,
    forecast_date: date,
    target_tz: str,
    work_root: Path,
) -> Path:
    raw_price_payload = _load_payload(profile.price_config, repo_root)
    first_stage_start = forecast_date - timedelta(days=_price_train_days(raw_price_payload))

    first_stage_paths: dict[str, Path] = {}
    for model, config_path in profile.price_input_configs().items():
        print(f"\n--- Refreshing {model} input for the {profile.name} price model ---")
        first_stage_paths[model] = _run_first_stage_config(
            config_path=config_path,
            repo_root=repo_root,
            forecast_date=forecast_date,
            history_start=first_stage_start,
            target_tz=target_tz,
        )

    export_dir = resolve_path(work_root, repo_root) / profile.name / forecast_date.isoformat() / "price"
    if profile.name == "final":
        price_input_payload = raw_price_payload
    else:
        histories = {
            model: store_component_forecast_history(
                repo_root=repo_root,
                cutoff=profile.name,
                component=model,
                forecast_path=source_path,
                forecast_date=forecast_date,
                target_tz=target_tz,
            ).path
            for model, source_path in first_stage_paths.items()
        }
        price_input_payload = _price_payload_with_component_histories(raw_price_payload, histories)

    price_payload = _mutate_price_payload(
        price_input_payload,
        forecast_date=forecast_date,
        point_history_days=0,
        export_dir=export_dir,
        target_tz=target_tz,
    )
    price_config = validate_config_payload(
        _config_body(price_payload),
        LearOperationalConfig,
        repo_root=repo_root,
    )
    print(f"\n--- Running {profile.name} price forecast ---")
    return run_point_base_forecasts(
        lear_config=price_config,
        forecast_date=forecast_date,
        history_days=0,
        export_dir=export_dir,
    )


def _write_target_day_csv(
    *,
    source_path: Path,
    output_path: Path,
    forecast_date: date,
    target_tz: str,
    value_column: str,
) -> Path:
    frame = load_timestamp_csv(source_path, target_tz)
    start = datetime.combine(forecast_date, datetime.min.time(), tzinfo=ZoneInfo(target_tz))
    end = start + timedelta(days=1)
    target = frame.loc[(frame.index >= start) & (frame.index < end)].copy()
    if target.empty:
        raise ValueError(f"{source_path} contains no rows for {forecast_date}.")
    if value_column not in target.columns:
        raise ValueError(f"{source_path} does not contain required column {value_column!r}.")
    if target[value_column].isna().any():
        raise ValueError(f"{source_path} contains missing {value_column!r} values for {forecast_date}.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    save_timestamp_csv(target, output_path)
    return output_path


def _submission_approach_name(profile: OperationalProfile, model: str) -> str:
    if profile.name == "final":
        return {
            "load": "load_open_meteo_p10_morning1015_lightgbm_pop_weighted_quantiles",
            "solar": "renewable_dwd_icon_mastr_solar_tso_c25_run06_cloud_geometry_physics_hgb_solar",
            "wind": "renewable_hybrid_dwd_mastr_wind_c100_multi_provider7_run06_onshore",
            "price": "price_pgen_lightgbm_c2_run06_d70",
        }[model]
    if model == "price":
        return CUTOFF_SPECS[profile.name].approach_name
    return f"{model}_cutoff_{profile.name}_first_stage"


def _submit_result(
    *,
    result: ForecastResult,
    profile: OperationalProfile,
    forecast_date: date,
    target_tz: str,
    repo_root: Path,
) -> None:
    model = result.model
    challenge_id = _resolve_challenge_id(None, CHALLENGE_ID_ENVS[model], repo_root)
    approach_name = _submission_approach_name(profile, model)
    if model == "price":
        payload = _build_submission_payload(
            forecast_path=result.output_path,
            forecast_date=forecast_date,
            challenge_id=challenge_id,
            submit=True,
            target_tz=target_tz,
            approach_name=approach_name,
            approach_description=f"Operational {profile.name} price forecast from the released model registry.",
        )
    else:
        payload = _build_first_stage_submission_payload(
            forecast_path=result.output_path,
            forecast_date=forecast_date,
            challenge_id=challenge_id,
            submit=True,
            target_tz=target_tz,
            value_column=VALUE_COLUMNS[model],
            source_name=f"{model}_{profile.name}",
            approach_name=approach_name,
            approach_description=f"Operational {profile.name} {model} forecast from the released model registry.",
        )

    config_path = result.output_path.parent / f"energy_arena_{model}_submission.generated.yaml"
    _write_yaml(config_path, payload)
    run_from_config(
        validate_config_payload(payload, RunConfig, repo_root=repo_root),
        submit_override=True,
    )


def run_next_day_forecast(
    *,
    model: str,
    cutoff: str = "final",
    forecast_date: date | None = None,
    target_tz: str = "Europe/Berlin",
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    work_root: Path = DEFAULT_WORK_ROOT,
    refresh_data: bool = True,
    restore_archive_if_needed: bool = True,
    submit: bool = False,
) -> list[ForecastResult]:
    repo_root = find_repo_root()
    load_dotenv(repo_root / ".env")
    day = forecast_date or tomorrow_in_tz(target_tz)
    profile = get_operational_profile(cutoff)
    requested_models = list(MODEL_NAMES) if model == "all" else [model]

    if restore_archive_if_needed:
        _ensure_archive_restored(repo_root)

    data_models = set(requested_models)
    if "price" in data_models:
        data_models.update({"load", "solar", "wind"})
    if refresh_data:
        _refresh_data(
            profile=profile,
            required_models=data_models,
            repo_root=repo_root,
            forecast_date=day,
            target_tz=target_tz,
        )

    output_dir = resolve_path(output_root, repo_root) / day.isoformat() / profile.name
    results: list[ForecastResult] = []
    for selected_model in requested_models:
        config_path = profile.model_config(selected_model)
        if selected_model == "price":
            source_path = _run_price_config(
                profile=profile,
                repo_root=repo_root,
                forecast_date=day,
                target_tz=target_tz,
                work_root=work_root,
            )
        else:
            print(f"\n--- Running {profile.name} {selected_model} forecast ---")
            source_path = _run_first_stage_config(
                config_path=config_path,
                repo_root=repo_root,
                forecast_date=day,
                history_start=day,
                target_tz=target_tz,
            )

        output_path = _write_target_day_csv(
            source_path=source_path,
            output_path=output_dir / f"{selected_model}.csv",
            forecast_date=day,
            target_tz=target_tz,
            value_column=VALUE_COLUMNS[selected_model],
        )
        result = ForecastResult(
            model=selected_model,
            config_path=config_path,
            source_path=source_path,
            output_path=output_path,
        )
        results.append(result)
        if submit:
            _submit_result(
                result=result,
                profile=profile,
                forecast_date=day,
                target_tz=target_tz,
                repo_root=repo_root,
            )

    metadata = {
        "created_at": datetime.now(ZoneInfo(target_tz)).isoformat(),
        "forecast_date": day.isoformat(),
        "cutoff": profile.name,
        "weather_run_utc": profile.weather_run,
        "refresh_data": refresh_data,
        "submit": submit,
        "forecasts": [
            {
                "model": result.model,
                "config": str(result.config_path),
                "source": str(result.source_path),
                "output": str(result.output_path),
                "value_column": VALUE_COLUMNS[result.model],
            }
            for result in results
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(output_dir / "metadata.json", "w", encoding="utf-8") as handle:
        json.dump(metadata, handle, indent=2)

    print("\nForecasts ready:")
    for result in results:
        print(f"  {result.model}: {result.output_path}")
    return results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch current inputs and run one released next-day forecast model."
    )
    parser.add_argument("--model", choices=(*MODEL_NAMES, "all"), required=True)
    parser.add_argument("--cutoff", choices=(*sorted(CUTOFF_SPECS), "final"), default="final")
    parser.add_argument(
        "--forecast-date",
        type=date.fromisoformat,
        default=None,
        help="Target delivery date; defaults to tomorrow in --target-tz.",
    )
    parser.add_argument("--target-tz", default="Europe/Berlin")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--work-root", type=Path, default=DEFAULT_WORK_ROOT)
    parser.add_argument(
        "--skip-data-refresh",
        action="store_true",
        help="Use restored/cached inputs without fetching the target day's updates.",
    )
    parser.add_argument(
        "--skip-archive-restore",
        action="store_true",
        help="Do not bootstrap missing runtime data from data/archive/operational.",
    )
    parser.add_argument(
        "--submit",
        action="store_true",
        help="Submit the generated forecast to Energy Arena. Local CSV generation is the default.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    run_next_day_forecast(
        model=args.model,
        cutoff=args.cutoff,
        forecast_date=args.forecast_date,
        target_tz=args.target_tz,
        output_root=args.output_root,
        work_root=args.work_root,
        refresh_data=not args.skip_data_refresh,
        restore_archive_if_needed=not args.skip_archive_restore,
        submit=args.submit,
    )


if __name__ == "__main__":
    main()
