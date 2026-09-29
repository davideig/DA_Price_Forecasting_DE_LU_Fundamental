from __future__ import annotations

from datetime import date
from pathlib import Path

from da_price_forecasting.config import RunConfig, validate_config_payload
from da_price_forecasting.config.base import load_config_payload
from da_price_forecasting.scripts import energy_arena_price_cutoff_daily as cutoff_daily


FCR_COLUMNS = [
    "reserve_fcr_germany_demand_mw",
    "reserve_fcr_germany_capacity_price_eur_mw",
    "reserve_fcr_germany_surplus_mw",
]
AFRR_COLUMNS = [
    "reserve_afrr_pos_avg_capacity_price_eur_mw_h",
    "reserve_afrr_pos_marginal_capacity_price_eur_mw_h",
    "reserve_afrr_pos_allocated_mw",
    "reserve_afrr_pos_offered_mw",
    "reserve_afrr_pos_import_export_mw",
    "reserve_afrr_neg_avg_capacity_price_eur_mw_h",
    "reserve_afrr_neg_marginal_capacity_price_eur_mw_h",
    "reserve_afrr_neg_allocated_mw",
    "reserve_afrr_neg_offered_mw",
    "reserve_afrr_neg_import_export_mw",
]
MFRR_COLUMNS = [
    "reserve_mfrr_pos_avg_capacity_price_eur_mw_h",
    "reserve_mfrr_pos_marginal_capacity_price_eur_mw_h",
    "reserve_mfrr_pos_offered_mw",
    "reserve_mfrr_pos_import_export_mw",
    "reserve_mfrr_neg_avg_capacity_price_eur_mw_h",
    "reserve_mfrr_neg_marginal_capacity_price_eur_mw_h",
    "reserve_mfrr_neg_offered_mw",
    "reserve_mfrr_neg_import_export_mw",
]


def test_cutoff_first_stage_submission_specs_use_expected_value_columns() -> None:
    specs = cutoff_daily._first_stage_submission_specs(
        cutoff="0900",
        load_challenge_id=20,
        solar_challenge_id=4,
        wind_challenge_id=6,
    )

    assert specs["load"]["challenge_id"] == 20
    assert specs["load"]["value_column"] == "Load_Model_MW"
    assert specs["solar"]["challenge_id"] == 4
    assert specs["solar"]["value_column"] == "Solar_Model_MW"
    assert specs["wind"]["challenge_id"] == 6
    assert specs["wind"]["value_column"] == "Wind_Onshore_Model_MW"
    assert specs["wind"]["source_name"] == "wind_onshore_cutoff_0900"
    assert "fixed 03 UTC weather run" in specs["wind"]["approach_description"]


def test_live_cutoff_weather_mapping_is_causal() -> None:
    expected_runs = {
        "0700": "03",
        "0800": "03",
        "0900": "03",
        "1000": "06",
        "1100": "06",
        "1200": "06",
    }
    for cutoff, expected_run in expected_runs.items():
        spec = cutoff_daily.CUTOFF_SPECS[cutoff]
        assert spec.weather_run == expected_run
        config_paths = (spec.price_config, spec.load_config, spec.solar_config, spec.wind_config)
        for config_path in config_paths:
            assert f"run{expected_run}" in config_path.name
            assert config_path.parent == Path("configs/deployment/cutoffs")


def test_live_cutoff_configs_validate() -> None:
    for spec in cutoff_daily.CUTOFF_SPECS.values():
        config_paths = (spec.price_config, spec.load_config, spec.solar_config, spec.wind_config)
        for config_path in config_paths:
            payload = load_config_payload(config_path)
            validate_config_payload(payload, RunConfig, repo_root=Path.cwd())


def test_cutoff_first_stage_submission_payload_uses_forecast_file_source(tmp_path: Path) -> None:
    forecast_path = tmp_path / "forecast.csv"
    payload = cutoff_daily._build_first_stage_submission_payload(
        forecast_path=forecast_path,
        forecast_date=date(2026, 9, 23),
        challenge_id=20,
        submit=False,
        target_tz="Europe/Berlin",
        value_column="Load_Model_MW",
        source_name="load_cutoff_0900",
        approach_name="load_cutoff_0900_first_stage",
        approach_description="RQ3 0900 cutoff own load forecast.",
    )

    assert payload["submit"] is False
    assert payload["config"]["forecast_date"] == "2026-09-23"
    assert payload["config"]["challenge_id"] == 20
    assert payload["config"]["source"] == {
        "kind": "forecast_file",
        "path": str(forecast_path),
        "name": "load_cutoff_0900",
        "value_column": "Load_Model_MW",
    }
    assert payload["config"]["value_column"] == "Load_Model_MW"
    validate_config_payload(payload, RunConfig, repo_root=Path.cwd())


def test_cutoff_paths_include_first_stage_submission_configs(tmp_path: Path) -> None:
    paths = cutoff_daily.cutoff_work_paths(
        repo_root=tmp_path,
        forecast_date=date(2026, 9, 23),
        cutoff="0900",
        work_root=tmp_path / "work",
    )

    assert paths.submission_config == (
        tmp_path
        / "work"
        / "0900"
        / "2026-09-23"
        / "generated_configs"
        / "energy_arena_price_cutoff_submission.generated.yaml"
    )
    assert paths.first_stage_submission_config("wind") == (
        tmp_path
        / "work"
        / "0900"
        / "2026-09-23"
        / "generated_configs"
        / "energy_arena_wind_cutoff_submission.generated.yaml"
    )


def test_cutoff_first_stage_forecast_path_comes_from_export_dir(tmp_path: Path) -> None:
    payload = {"kind": "load_forecast", "config": {"export_dir": str(tmp_path / "export")}}

    assert cutoff_daily._forecast_file_from_payload(payload, repo_root=Path.cwd()) == tmp_path / "export" / "forecast.csv"


def test_fixed_run_daily_weather_configs_cover_all_inputs() -> None:
    config_root = Path("configs/deployment/cutoff_preprocessing")
    for run in ("03", "06"):
        expected = {
            f"dwd_icon_c2_run{run}.yaml": (
                f"data/processed/icon_aggregated_c2_run{run}",
                "data/clustering/icon_d2_clustering_c2_run06.parquet",
            ),
            f"dwd_solar_run{run}.yaml": (
                f"data/processed/icon_aggregated_mastr_solar_tso_c25_run{run}",
                "data/clustering/icon_d2_mastr_solar_tso_c25.csv",
            ),
            f"dwd_wind_run{run}.yaml": (
                f"data/processed/icon_aggregated_mastr_wind_c100_run{run}",
                "data/clustering/icon_d2_mastr_wind_c100.csv",
            ),
        }

        for name, (icon_dir, cluster_file) in expected.items():
            payload = load_config_payload(config_root / name)
            validated = validate_config_payload(payload, RunConfig, repo_root=Path.cwd())

            assert validated.config["required_run"] == run
            assert validated.config["icon_dir"] == icon_dir
            assert validated.config["dwd_icon_aggregation_cluster_output_file"] == cluster_file
            assert validated.config["dwd_icon_fallback_previous_runs"] is True
            assert validated.config["dwd_icon_fallback_step_hours"] == 3
            assert validated.config["dwd_icon_fallback_max_lookback_hours"] == 3


def test_cutoff_configs_apply_realized_data_limits_and_fixed_weather() -> None:
    expected = {
        "0700": (5, 30),
        "0800": (6, 30),
        "0900": (7, 30),
        "1000": (8, 30),
        "1100": (9, 30),
        "1200": (10, 30),
    }
    for cutoff, (hour, minute) in expected.items():
        spec = cutoff_daily.CUTOFF_SPECS[cutoff]
        load = load_config_payload(spec.load_config)["config"]
        solar = load_config_payload(spec.solar_config)["config"]
        wind = load_config_payload(spec.wind_config)["config"]
        price = load_config_payload(spec.price_config)["config"]

        assert load["target_availability_cutoff_hour"] == hour
        assert load["target_availability_cutoff_minute"] == minute
        assert load["partial_load_morning_end_hour"] == hour
        assert load["partial_load_morning_end_minute"] == minute
        assert load["require_weather_for_training"] is True
        assert load["actual_load_refresh_lookback_days"] == 14
        assert load["open_meteo_fallback_previous_runs"] is True
        assert load["open_meteo_fallback_step_hours"] == 3
        assert load["open_meteo_fallback_max_lookback_hours"] == 3
        assert solar["actual_generation_refresh_lookback_days"] == 14
        assert wind["actual_generation_refresh_lookback_days"] == 14
        assert "2026-02-07" in wind["skip_dates"]
        assert price["required_run"] == spec.weather_run
        expected_price_skip_dates = ["2026-02-07", "2026-06-19"]
        if cutoff in {"0700", "0800", "0900"}:
            assert price["icon_transition_history_dir"] == "data/processed/icon_aggregated_c2_run06"
            assert price["icon_transition_history_run"] == "06"
            assert price["icon_transition_history_skip_dates"] == expected_price_skip_dates
            assert "2026-06-12" in load["skip_dates"]
            assert "2026-06-12" in solar["skip_dates"]
            assert "2026-06-12" in wind["skip_dates"]
            expected_price_skip_dates.insert(1, "2026-06-12")
        else:
            assert "icon_transition_history_dir" not in price
        assert price["skip_dates"] == expected_price_skip_dates
        expected_reserve_columns = {
            "0700": [],
            "0800": [],
            "0900": FCR_COLUMNS,
            "1000": FCR_COLUMNS + AFRR_COLUMNS,
            "1100": FCR_COLUMNS + AFRR_COLUMNS + MFRR_COLUMNS,
            "1200": FCR_COLUMNS + AFRR_COLUMNS + MFRR_COLUMNS,
        }[cutoff]
        if expected_reserve_columns:
            assert "reserve_market" in price["features"]["covariates"]
            assert price["features"]["reserve_market_columns"] == expected_reserve_columns
        else:
            assert "reserve_market" not in price["features"]["covariates"]
            assert "reserve_market_columns" not in price["features"]

        generation_minute = 0 if cutoff == "1200" else minute
        for generation in (solar, wind):
            assert generation["target_availability_cutoff_hour"] == hour
            assert generation["target_availability_cutoff_minute"] == generation_minute
            assert generation["partial_generation_morning_end_hour"] == hour
            assert generation["partial_generation_morning_end_minute"] == generation_minute
            if cutoff in {"0700", "0800", "0900"}:
                assert generation["renewable_proxy_fallback_history_only"] is True


def test_live_wind_uses_only_open_meteo_icon_d2() -> None:
    for spec in cutoff_daily.CUTOFF_SPECS.values():
        config = load_config_payload(spec.wind_config)["config"]
        assert len(config["extra_renewable_proxy_files"]) == 1
        assert "open_meteo_icon_d2" in config["extra_renewable_proxy_files"][0]
        assert config["extra_renewable_proxy_prefixes"] == ["om_"]
        assert config["min_train_days"] == 20


def test_price_configs_read_immutable_component_histories() -> None:
    for cutoff, spec in cutoff_daily.CUTOFF_SPECS.items():
        features = load_config_payload(spec.price_config)["config"]["features"]
        root = f"data/processed/component_forecast_history/{cutoff}"
        assert features["load_forecast_file"] == f"{root}/load.csv"
        assert features["renewable_proxy_files"] == [f"{root}/solar.csv", f"{root}/wind.csv"]


def test_all_live_open_meteo_configs_request_fixed_runs_with_previous_run_fallback() -> None:
    paths = list(Path("configs/deployment/cutoffs").glob("*.yaml"))
    paths.extend(Path("configs/deployment/cutoff_preprocessing").glob("*open_meteo*.yaml"))
    checked = 0
    for path in paths:
        config = load_config_payload(path)["config"]
        if config.get("weather_source") != "open_meteo" and "open_meteo_api_mode" not in config:
            continue
        assert config["open_meteo_api_mode"] == "single_run"
        assert config["open_meteo_base_url"] == (
            "https://customer-single-runs-api.open-meteo.com/v1/forecast"
        )
        assert config["open_meteo_api_key_env"] == "OPEN_METEO_API_KEY"
        expected_run = next(run for run in ("03", "06") if f"run{run}" in path.name)
        assert config["open_meteo_single_run_hour_utc"] == f"{expected_run}:00"
        assert config["open_meteo_fallback_previous_runs"] is True
        assert config["open_meteo_fallback_step_hours"] == 3
        assert config["open_meteo_fallback_max_lookback_hours"] == 3
        required = config["open_meteo_required_non_null_variables"]
        if "wind_open_meteo" in path.name:
            assert required == [
                "wind_speed_80m",
                "wind_direction_80m",
                "wind_speed_120m",
                "wind_direction_120m",
                "wind_speed_180m",
                "wind_direction_180m",
            ]
            assert "boundary_layer_height" not in required
        checked += 1
    assert checked == 12


def test_live_reserve_products_follow_measured_publication_times() -> None:
    assert cutoff_daily.RESERVE_PRODUCTS_BY_CUTOFF == {
        "0700": (),
        "0800": (),
        "0900": ("FCR",),
        "1000": ("FCR", "aFRR"),
        "1100": ("FCR", "aFRR", "mFRR"),
        "1200": ("FCR", "aFRR", "mFRR"),
    }


def test_reserve_refresh_uses_cutoff_products_and_requested_history(monkeypatch) -> None:
    captured = []
    monkeypatch.setattr(cutoff_daily, "run_from_config", captured.append)

    products = cutoff_daily._refresh_reserve_market_features(
        repo_root=Path.cwd(),
        cutoff="1000",
        forecast_date=date(2026, 9, 29),
        history_days=2,
    )

    assert products == ("FCR", "aFRR")
    assert len(captured) == 1
    assert captured[0].kind.value == "reserve_market"
    assert captured[0].config["start_date"] == "2026-09-27"
    assert captured[0].config["end_date"] == "2026-09-29"
    assert captured[0].config["product_types"] == ["FCR", "aFRR"]
    assert captured[0].config["append_existing"] is True
