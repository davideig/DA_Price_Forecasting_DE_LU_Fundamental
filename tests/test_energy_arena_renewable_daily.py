from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from da_price_forecasting.config import RenewableGenerationModelConfig, RunConfig, validate_config_payload
from da_price_forecasting.pipelines.common import load_timestamp_csv, save_timestamp_csv
from da_price_forecasting.scripts import energy_arena_renewable_daily as daily


def test_renewable_daily_defaults_to_onshore_wind_submission_column() -> None:
    assert daily.DEFAULT_WIND_VALUE_COLUMN == "Wind_Onshore_Model_MW"


def test_renewable_daily_rejects_total_wind_for_known_energy_arena_wind_challenge() -> None:
    with pytest.raises(ValueError, match="Wind_Onshore_Model_MW"):
        daily._validate_wind_submission_column(6, "Wind_Total_Model_MW")


def test_renewable_daily_submission_payload_uses_forecast_file_source(tmp_path: Path) -> None:
    forecast_path = tmp_path / "forecast.csv"
    payload = daily.build_renewable_submission_payload(
        forecast_path=forecast_path,
        forecast_date=date(2026, 5, 26),
        challenge_id=44,
        submit=False,
        target_tz="Europe/Berlin",
        value_column="Solar_Model_MW",
        source_name="renewable_generation_solar",
        approach_name="solar_model",
        approach_description=None,
    )

    assert payload["submit"] is False
    assert payload["config"]["forecast_date"] == "2026-05-26"
    assert payload["config"]["challenge_id"] == 44
    assert payload["config"]["source"]["kind"] == "forecast_file"
    assert payload["config"]["source"]["value_column"] == "Solar_Model_MW"
    assert payload["config"]["value_column"] == "Solar_Model_MW"
    validate_config_payload(payload, RunConfig, repo_root=Path.cwd())


def test_renewable_daily_rewrites_feature_and_model_dates(tmp_path: Path) -> None:
    repo_root = Path.cwd()
    forecast_day = date(2026, 5, 26)
    feature_payload = daily.build_renewable_feature_payload(
        feature_config_path=Path(
            "configs/preprocessing/renewable_features/"
            "regional_renewable_features_open_meteo_icon_d2_single_run06_mastr_solar_tso_c25_cloud_cover.yaml"
        ),
        forecast_date=forecast_day,
        repo_root=repo_root,
    )
    feature_config = feature_payload["config"]

    assert feature_config["open_meteo_end_date"] == "2026-05-26"

    proxy_file = tmp_path / "regional_renewable_features.csv"
    model_payload = daily.build_renewable_model_payload(
        model_config_path=Path(
            "configs/final/renewable/"
            "renewable_generation_dwd_icon_mastr_solar_tso_c25_run06_tso_components_cloud_geometry_physics_"
            "residual_own_region_daylight_suspicious_totalbias_hgb_solar_bias45_hour_s075_d90_cutoff1000_"
            "paper_febjul.yaml"
        ),
        forecast_date=forecast_day,
        forecast_dir=tmp_path / "forecast_run",
        renewable_proxy_file=proxy_file,
        repo_root=repo_root,
    )
    model_config = model_payload["config"]

    assert model_config["test_start"] == "2026-05-26"
    assert model_config["test_end"] == "2026-05-26"
    assert model_config["entsoe_end_date"] == "2026-05-25"
    assert model_config["renewable_proxy_file"] == str(proxy_file)
    assert model_config["export_dir"] == str(tmp_path / "forecast_run")
    validate_config_payload(model_payload, RunConfig, repo_root=repo_root)


def test_renewable_daily_leaves_dwd_feature_config_dates_unchanged() -> None:
    payload = daily.build_renewable_feature_payload(
        feature_config_path=Path(
            "configs/preprocessing/renewable_features/"
            "regional_renewable_features_dwd_icon_mastr_solar_tso_c25_run06_solar_spread.yaml"
        ),
        forecast_date=date(2026, 5, 26),
        repo_root=Path.cwd(),
    )

    assert payload["config"]["weather_source"] == "dwd_icon"
    assert "open_meteo_end_date" not in payload["config"]


def test_renewable_daily_features_only_skips_model_and_challenge_ids(
    monkeypatch,
    tmp_path: Path,
) -> None:
    feature_config = tmp_path / "feature.yaml"
    output_file = tmp_path / "features.csv"
    capacity_map_file = tmp_path / "capacity.csv"
    feature_config.write_text(
        "kind: regional_renewable_features\n"
        "config:\n"
        f"  repo_root: {tmp_path}\n"
        "  weather_source: dwd_icon\n"
        f"  icon_dir: {tmp_path / 'icon'}\n"
        f"  cluster_file: {tmp_path / 'clusters.csv'}\n"
        f"  capacity_file: {tmp_path / 'capacity-input.csv'}\n"
        f"  capacity_map_file: {capacity_map_file}\n"
        f"  output_file: {output_file}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(daily, "find_repo_root", lambda: tmp_path)

    def fake_run_from_config(config, **kwargs):
        index = pd.date_range("2026-09-23", "2026-09-25", freq="15min", inclusive="left", tz="Europe/Berlin")
        save_timestamp_csv(pd.DataFrame({"x": np.arange(len(index), dtype=float)}, index=index), output_file)

    monkeypatch.setattr(daily, "run_from_config", fake_run_from_config)

    paths = daily.run_daily_renewable_energy_arena(
        feature_config_path=feature_config,
        model_config_path=tmp_path / "unused-model.yaml",
        forecast_date=date(2026, 9, 24),
        work_root=tmp_path / "work",
        features_only=True,
    )

    metadata = json.loads((paths.work_dir / "daily_run.json").read_text(encoding="utf-8"))
    assert metadata["features_only"] is True
    assert not paths.model_config.exists()


def _open_meteo_feature_payload(tmp_path: Path, output_file: Path) -> dict:
    return {
        "kind": "regional_renewable_features",
        "config": {
            "repo_root": str(tmp_path),
            "weather_source": "open_meteo",
            "target_tz": "Europe/Berlin",
            "cluster_file": str(tmp_path / "clusters.csv"),
            "capacity_file": str(tmp_path / "capacity.csv"),
            "capacity_map_file": str(tmp_path / "capacity-map.csv"),
            "output_file": str(output_file),
            "open_meteo_weather_file": str(tmp_path / "weather.csv"),
            "open_meteo_start_date": "2026-07-01",
            "open_meteo_end_date": "2026-09-24",
        },
    }


def test_incremental_feature_refresh_only_runs_two_days_and_merges_history(monkeypatch, tmp_path: Path) -> None:
    output_file = tmp_path / "features.csv"
    target_day = date(2026, 9, 24)
    historical_index = pd.date_range("2026-09-22", "2026-09-23", freq="15min", inclusive="left", tz="Europe/Berlin")
    save_timestamp_csv(pd.DataFrame({"feature": 1.0}, index=historical_index), output_file)
    payload = _open_meteo_feature_payload(tmp_path, output_file)
    captured: dict[str, str] = {}

    def fake_run_from_config(config, **kwargs):
        captured.update(config.config)
        refreshed_index = pd.date_range(
            "2026-09-23",
            "2026-09-25",
            freq="15min",
            inclusive="left",
            tz="Europe/Berlin",
        )
        save_timestamp_csv(pd.DataFrame({"feature": 2.0}, index=refreshed_index), output_file)

    monkeypatch.setattr(daily, "run_from_config", fake_run_from_config)

    daily._run_feature_payload_incrementally(payload, tmp_path, target_day)

    assert captured["open_meteo_start_date"] == "2026-09-23"
    assert captured["open_meteo_end_date"] == "2026-09-24"
    assert captured["capacity_timeseries_file"] is None
    assert captured["weather_weights_file"] is None
    updated = load_timestamp_csv(output_file, "Europe/Berlin")
    assert daily._feature_cache_has_day(updated, date(2026, 9, 22), "Europe/Berlin")
    assert daily._feature_cache_has_day(updated, target_day, "Europe/Berlin")
    assert (updated.loc[daily._local_day_index(target_day, "Europe/Berlin"), "feature"] == 2.0).all()


def test_incremental_feature_refresh_skips_complete_unchanged_target(monkeypatch, tmp_path: Path) -> None:
    output_file = tmp_path / "features.csv"
    target_day = date(2026, 9, 24)
    target_index = daily._local_day_index(target_day, "Europe/Berlin")
    save_timestamp_csv(pd.DataFrame({"feature": 3.0}, index=target_index), output_file)
    payload = _open_meteo_feature_payload(tmp_path, output_file)

    def unexpected_run(*args, **kwargs):
        raise AssertionError("complete unchanged feature cache should not be rebuilt")

    monkeypatch.setattr(daily, "run_from_config", unexpected_run)

    daily._run_feature_payload_incrementally(payload, tmp_path, target_day)

    unchanged = load_timestamp_csv(output_file, "Europe/Berlin")
    assert unchanged.index.astype(str).tolist() == target_index.astype(str).tolist()


def test_incremental_feature_refresh_uses_cached_donor_day_on_failure(monkeypatch, tmp_path: Path) -> None:
    output_file = tmp_path / "features.csv"
    target_day = date(2026, 9, 24)
    donor_day = target_day - pd.Timedelta(days=1)
    donor_index = daily._local_day_index(donor_day, "Europe/Berlin")
    save_timestamp_csv(pd.DataFrame({"feature": np.arange(len(donor_index), dtype=float)}, index=donor_index), output_file)
    payload = _open_meteo_feature_payload(tmp_path, output_file)

    monkeypatch.setattr(
        daily,
        "run_from_config",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("provider unavailable")),
    )

    daily._run_feature_payload_incrementally(payload, tmp_path, target_day)

    updated = load_timestamp_csv(output_file, "Europe/Berlin")
    target_values = updated.loc[daily._local_day_index(target_day, "Europe/Berlin"), "feature"].to_numpy()
    assert np.array_equal(target_values, np.arange(len(donor_index), dtype=float))


def test_dated_renewable_work_paths_are_per_forecast_day(tmp_path: Path) -> None:
    paths = daily.dated_renewable_work_paths(tmp_path, date(2026, 5, 26), work_root=tmp_path / "work")

    assert paths.work_dir == tmp_path / "work" / "2026-05-26"
    assert paths.forecast_file == paths.work_dir / "forecast_run" / "forecast.csv"
    assert paths.solar_submission_config == paths.work_dir / "generated_configs" / "energy_arena_solar_submission.generated.yaml"
    assert paths.wind_submission_config == paths.work_dir / "generated_configs" / "energy_arena_wind_submission.generated.yaml"
    assert paths.extra_feature_config(2) == paths.work_dir / "generated_configs" / "regional_renewable_features_extra_2.generated.yaml"


def test_update_actual_generation_cache_refreshes_overlap(monkeypatch, tmp_path: Path) -> None:
    cache = tmp_path / "actual_generation.csv"
    existing_index = pd.date_range("2026-05-19T00:00:00+02:00", periods=2, freq="D")
    save_timestamp_csv(
        pd.DataFrame(
            {
                "Solar_Actual_MW": [1.0, 2.0],
                "Wind_Onshore_Actual_MW": [3.0, 4.0],
                "Wind_Offshore_Actual_MW": [5.0, 6.0],
                "Wind_Total_Actual_MW": [8.0, 10.0],
                "Renewable_Total_Actual_MW": [9.0, 12.0],
            },
            index=existing_index,
        ),
        cache,
    )

    captured = {}
    fetched_index = pd.date_range("2026-05-19T00:00:00+02:00", periods=4, freq="D")

    def fake_fetch_actual_renewable_generation(**kwargs):
        captured.update(kwargs)
        return pd.DataFrame(
            {
                "Solar_Actual_MW": np.arange(10.0, 14.0),
                "Wind_Onshore_Actual_MW": np.arange(20.0, 24.0),
                "Wind_Offshore_Actual_MW": np.arange(30.0, 34.0),
                "Wind_Total_Actual_MW": np.arange(50.0, 54.0),
                "Renewable_Total_Actual_MW": np.arange(60.0, 64.0),
            },
            index=fetched_index,
        )

    monkeypatch.setattr(daily, "fetch_actual_renewable_generation", fake_fetch_actual_renewable_generation)

    config = RenewableGenerationModelConfig(
        repo_root=tmp_path,
        entsoe_start_date=date(2026, 5, 1),
        entsoe_end_date=date(2026, 5, 22),
        actual_generation_file=cache,
        renewable_proxy_file=tmp_path / "proxy.csv",
        unavailability_file=tmp_path / "unavailability.csv",
        icon_dir=tmp_path / "icon",
        export_dir=tmp_path / "export",
        target_availability_lag_days=1,
        target_availability_cutoff_hour=10,
        test_start=date(2026, 5, 23),
        test_end=date(2026, 5, 23),
    )

    daily.update_actual_generation_cache(config, forecast_date=date(2026, 5, 23))

    assert captured["start_day"].date().isoformat() == "2026-05-19"
    assert captured["end_day"].date().isoformat() == "2026-05-22"

    updated = load_timestamp_csv(cache, "Europe/Berlin")
    assert updated.index.max().date().isoformat() == "2026-05-22"
    assert updated.loc[pd.Timestamp("2026-05-19T00:00:00+02:00"), "Solar_Actual_MW"] == 10.0
    assert updated.loc[pd.Timestamp("2026-05-22T00:00:00+02:00"), "Renewable_Total_Actual_MW"] == 63.0


def test_update_actual_generation_cache_refreshes_solar_control_area_targets(monkeypatch, tmp_path: Path) -> None:
    cache = tmp_path / "actual_generation.csv"
    fetched_index = pd.date_range("2026-05-21T00:00:00+02:00", periods=2, freq="D")

    def fake_fetch_actual_renewable_generation(**kwargs):
        return pd.DataFrame(
            {
                "Solar_Actual_MW": [1.0, 2.0],
                "Wind_Onshore_Actual_MW": [3.0, 4.0],
                "Wind_Offshore_Actual_MW": [5.0, 6.0],
                "Wind_Total_Actual_MW": [8.0, 10.0],
                "Renewable_Total_Actual_MW": [9.0, 12.0],
            },
            index=fetched_index,
        )

    captured = {}

    def fake_fetch_actual_solar_generation_by_control_area(**kwargs):
        captured.update(kwargs)
        return pd.DataFrame(
            {
                "Solar_50Hertz_Actual_MW": [10.0, 11.0],
                "Solar_Amprion_Actual_MW": [20.0, 21.0],
                "Solar_TenneT_Actual_MW": [30.0, 31.0],
                "Solar_TransnetBW_Actual_MW": [40.0, 41.0],
            },
            index=fetched_index,
        )

    monkeypatch.setattr(daily, "fetch_actual_renewable_generation", fake_fetch_actual_renewable_generation)
    monkeypatch.setattr(
        daily,
        "fetch_actual_solar_generation_by_control_area",
        fake_fetch_actual_solar_generation_by_control_area,
    )

    config = RenewableGenerationModelConfig(
        repo_root=tmp_path,
        entsoe_start_date=date(2026, 5, 21),
        entsoe_end_date=date(2026, 5, 22),
        include_solar_control_area_targets=True,
        target_columns=[
            "Solar_50Hertz_Actual_MW",
            "Solar_Amprion_Actual_MW",
            "Solar_TenneT_Actual_MW",
            "Solar_TransnetBW_Actual_MW",
        ],
        actual_generation_file=cache,
        renewable_proxy_file=tmp_path / "proxy.csv",
        unavailability_file=tmp_path / "unavailability.csv",
        icon_dir=tmp_path / "icon",
        export_dir=tmp_path / "export",
        target_availability_lag_days=1,
        target_availability_cutoff_hour=10,
        test_start=date(2026, 5, 23),
        test_end=date(2026, 5, 23),
    )

    daily.update_actual_generation_cache(config, forecast_date=date(2026, 5, 23))

    assert captured["control_area_targets"] == config.solar_control_area_targets
    updated = load_timestamp_csv(cache, "Europe/Berlin")
    assert updated.loc[pd.Timestamp("2026-05-22T00:00:00+02:00"), "Solar_50Hertz_Actual_MW"] == 11.0
    assert updated.loc[pd.Timestamp("2026-05-22T00:00:00+02:00"), "Solar_TransnetBW_Actual_MW"] == 41.0
