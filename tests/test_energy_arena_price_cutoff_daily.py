from __future__ import annotations

from datetime import date
from pathlib import Path

from da_price_forecasting.config import RunConfig, validate_config_payload
from da_price_forecasting.scripts import energy_arena_price_cutoff_daily as cutoff_daily


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
