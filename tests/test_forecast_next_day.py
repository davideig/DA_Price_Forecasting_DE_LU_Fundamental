from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from da_price_forecasting.pipelines.common import load_timestamp_csv, save_timestamp_csv
from da_price_forecasting.scripts import forecast_next_day as module


def test_operational_profiles_use_the_expected_weather_runs_and_configs() -> None:
    early = module.get_operational_profile("0700")
    late = module.get_operational_profile("1100")
    final = module.get_operational_profile("final")

    assert early.weather_run == "00"
    assert "run00" in early.wind_config.name
    assert late.weather_run == "06"
    assert "run06" in late.wind_config.name
    assert final.weather_run == "06"
    assert final.load_config == module.FINAL_LOAD_CONFIG
    assert final.solar_config == module.FINAL_SOLAR_CONFIG
    assert final.wind_config == module.FINAL_WIND_CONFIG
    assert final.price_load_config == module.DEFAULT_LOAD_INPUT_CONFIG


def test_cutoff_price_uses_the_same_cutoff_specific_first_stage_configs() -> None:
    profile = module.get_operational_profile("1100")

    assert profile.price_input_configs() == {
        "load": profile.load_config,
        "solar": profile.solar_config,
        "wind": profile.wind_config,
    }


def test_write_target_day_csv_extracts_only_requested_delivery_day(tmp_path: Path) -> None:
    source_path = tmp_path / "source.csv"
    output_path = tmp_path / "published" / "wind.csv"
    index = pd.date_range("2026-09-27", periods=192, freq="15min", tz="Europe/Berlin")
    frame = pd.DataFrame({"Wind_Onshore_Model_MW": range(len(index)), "diagnostic": 1}, index=index)
    save_timestamp_csv(frame, source_path)

    module._write_target_day_csv(
        source_path=source_path,
        output_path=output_path,
        forecast_date=date(2026, 9, 28),
        target_tz="Europe/Berlin",
        value_column="Wind_Onshore_Model_MW",
    )

    published = load_timestamp_csv(output_path, "Europe/Berlin")
    assert len(published) == 96
    assert published.index.min().date() == date(2026, 9, 28)
    assert published.index.max().date() == date(2026, 9, 28)
    assert list(published.columns) == ["Wind_Onshore_Model_MW", "diagnostic"]


def test_wind_command_refreshes_only_wind_inputs_and_uses_selected_cutoff(
    monkeypatch,
    tmp_path: Path,
) -> None:
    calls: dict[str, object] = {}
    day = date(2026, 9, 28)

    monkeypatch.setattr(module, "find_repo_root", lambda: tmp_path)
    monkeypatch.setattr(module, "_ensure_archive_restored", lambda repo_root: None)

    def fake_refresh_data(**kwargs) -> None:
        calls["required_models"] = kwargs["required_models"]
        calls["weather_run"] = kwargs["profile"].weather_run

    def fake_first_stage(**kwargs) -> Path:
        calls["config_path"] = kwargs["config_path"]
        return tmp_path / "source.csv"

    def fake_publish(**kwargs) -> Path:
        output_path = kwargs["output_path"]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.touch()
        return output_path

    monkeypatch.setattr(module, "_refresh_data", fake_refresh_data)
    monkeypatch.setattr(module, "_run_first_stage_config", fake_first_stage)
    monkeypatch.setattr(module, "_write_target_day_csv", fake_publish)

    results = module.run_next_day_forecast(
        model="wind",
        cutoff="1100",
        forecast_date=day,
        output_root=Path("outputs"),
    )

    assert calls["required_models"] == {"wind"}
    assert calls["weather_run"] == "06"
    assert calls["config_path"] == module.CUTOFF_SPECS["1100"].wind_config
    assert results[0].output_path == tmp_path / "outputs/2026-09-28/1100/wind.csv"


def test_price_command_refreshes_all_dependencies(monkeypatch, tmp_path: Path) -> None:
    calls: dict[str, object] = {}
    day = date(2026, 9, 28)

    monkeypatch.setattr(module, "find_repo_root", lambda: tmp_path)
    monkeypatch.setattr(module, "_ensure_archive_restored", lambda repo_root: None)

    def fake_refresh_data(**kwargs) -> None:
        calls["required_models"] = kwargs["required_models"]

    def fake_price(**kwargs) -> Path:
        calls["profile"] = kwargs["profile"]
        return tmp_path / "source.csv"

    def fake_publish(**kwargs) -> Path:
        output_path = kwargs["output_path"]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.touch()
        return output_path

    monkeypatch.setattr(module, "_refresh_data", fake_refresh_data)
    monkeypatch.setattr(module, "_run_price_config", fake_price)
    monkeypatch.setattr(module, "_write_target_day_csv", fake_publish)

    module.run_next_day_forecast(
        model="price",
        cutoff="0800",
        forecast_date=day,
        output_root=Path("outputs"),
    )

    assert calls["required_models"] == {"load", "solar", "wind", "price"}
    assert calls["profile"].name == "0800"
    assert calls["profile"].weather_run == "00"


def test_submission_is_explicit_opt_in(monkeypatch, tmp_path: Path) -> None:
    submissions: list[module.ForecastResult] = []
    day = date(2026, 9, 28)

    monkeypatch.setattr(module, "find_repo_root", lambda: tmp_path)
    monkeypatch.setattr(module, "_ensure_archive_restored", lambda repo_root: None)
    monkeypatch.setattr(module, "_refresh_data", lambda **kwargs: None)
    monkeypatch.setattr(module, "_run_first_stage_config", lambda **kwargs: tmp_path / "source.csv")

    def fake_publish(**kwargs) -> Path:
        output_path = kwargs["output_path"]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.touch()
        return output_path

    monkeypatch.setattr(module, "_write_target_day_csv", fake_publish)
    monkeypatch.setattr(
        module,
        "_submit_result",
        lambda **kwargs: submissions.append(kwargs["result"]),
    )

    module.run_next_day_forecast(
        model="load",
        cutoff="final",
        forecast_date=day,
        output_root=Path("outputs"),
        submit=False,
    )
    assert submissions == []

    module.run_next_day_forecast(
        model="load",
        cutoff="final",
        forecast_date=day,
        output_root=Path("outputs"),
        submit=True,
    )
    assert [result.model for result in submissions] == ["load"]
