from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from da_price_forecasting.pipelines.common import load_timestamp_csv, save_timestamp_csv
from da_price_forecasting.scripts import energy_arena_price_final_daily as daily


def _day_frame(day: str, value: float) -> pd.DataFrame:
    start = pd.Timestamp(day, tz="Europe/Berlin")
    end = start + pd.DateOffset(days=1)
    index = pd.date_range(start, end, freq="15min", inclusive="left")
    return pd.DataFrame({"Model_MW": value}, index=index).rename_axis("timestamp")


def test_first_stage_runner_only_runs_missing_days_and_appends(monkeypatch, tmp_path: Path) -> None:
    export_dir = tmp_path / "forecast"
    forecast_path = export_dir / "forecast.csv"
    existing = pd.concat([_day_frame("2026-09-21", 1.0), _day_frame("2026-09-22", 2.0)])
    save_timestamp_csv(existing, forecast_path)
    payload = {
        "kind": "load_forecast_model",
        "config": {
            "repo_root": ".",
            "target_tz": "Europe/Berlin",
            "test_start": "2026-09-21",
            "test_end": "2026-09-23",
            "export_dir": str(export_dir),
        },
    }
    seen_payloads: list[dict] = []
    monkeypatch.setattr(daily, "validate_config_payload", lambda value, *args, **kwargs: value)

    def fake_run(run_config) -> None:
        seen_payloads.append(run_config)
        save_timestamp_csv(_day_frame("2026-09-23", 3.0), forecast_path)

    monkeypatch.setattr(daily, "run_from_config", fake_run)

    daily._run_first_stage_payload(payload, repo_root=tmp_path, forecast_date=date(2026, 9, 23))

    assert seen_payloads[0]["config"]["test_start"] == "2026-09-23"
    combined = load_timestamp_csv(forecast_path, "Europe/Berlin")
    assert len(combined) == 3 * 96
    assert set(combined["Model_MW"].unique()) == {1.0, 2.0, 3.0}


def test_first_stage_runner_skips_complete_cache(monkeypatch, tmp_path: Path) -> None:
    export_dir = tmp_path / "forecast"
    forecast_path = export_dir / "forecast.csv"
    save_timestamp_csv(_day_frame("2026-09-23", 1.0), forecast_path)
    payload = {
        "kind": "load_forecast_model",
        "config": {
            "repo_root": ".",
            "target_tz": "Europe/Berlin",
            "test_start": "2026-09-23",
            "test_end": "2026-09-23",
            "export_dir": str(export_dir),
        },
    }
    monkeypatch.setattr(
        daily,
        "run_from_config",
        lambda run_config: (_ for _ in ()).throw(AssertionError("model should not run")),
    )

    daily._run_first_stage_payload(payload, repo_root=tmp_path, forecast_date=date(2026, 9, 23))


def test_first_stage_runner_restores_cache_after_failure(monkeypatch, tmp_path: Path) -> None:
    export_dir = tmp_path / "forecast"
    forecast_path = export_dir / "forecast.csv"
    existing = _day_frame("2026-09-22", 2.0)
    save_timestamp_csv(existing, forecast_path)
    payload = {
        "kind": "load_forecast_model",
        "config": {
            "repo_root": ".",
            "target_tz": "Europe/Berlin",
            "test_start": "2026-09-22",
            "test_end": "2026-09-23",
            "export_dir": str(export_dir),
        },
    }
    monkeypatch.setattr(daily, "validate_config_payload", lambda value, *args, **kwargs: value)

    def fail_after_truncating(run_config) -> None:
        forecast_path.write_text("", encoding="utf-8")
        raise RuntimeError("model failed")

    monkeypatch.setattr(daily, "run_from_config", fail_after_truncating)

    try:
        daily._run_first_stage_payload(payload, repo_root=tmp_path, forecast_date=date(2026, 9, 23))
    except RuntimeError:
        pass
    else:
        raise AssertionError("Expected the simulated model failure")

    restored = load_timestamp_csv(forecast_path, "Europe/Berlin")
    pd.testing.assert_frame_equal(restored, existing, check_freq=False)


def test_select_cached_price_forecast_prefers_complete_target_day(tmp_path: Path) -> None:
    target_day = date(2026, 9, 25)
    previous_path = tmp_path / "work" / "2026-09-24" / "price_forecast" / "forecast.csv"
    target_path = tmp_path / "work" / "2026-09-25" / "price_forecast" / "forecast.csv"
    save_timestamp_csv(_day_frame("2026-09-24", 1.0).rename(columns={"Model_MW": "y_pred"}), previous_path)
    save_timestamp_csv(_day_frame("2026-09-25", 2.0).rename(columns={"Model_MW": "y_pred"}), target_path)

    selected, selected_day = daily._select_cached_price_forecast(
        repo_root=tmp_path,
        forecast_date=target_day,
        target_tz="Europe/Berlin",
        work_root=Path("work"),
    )

    assert selected == target_path
    assert selected_day == target_day


def test_select_cached_price_forecast_falls_back_to_previous_complete_day(tmp_path: Path) -> None:
    target_day = date(2026, 9, 25)
    target_path = tmp_path / "work" / "2026-09-25" / "price_forecast" / "forecast.csv"
    previous_path = tmp_path / "work" / "2026-09-24" / "price_forecast" / "forecast.csv"
    incomplete = _day_frame("2026-09-25", 2.0).rename(columns={"Model_MW": "y_pred"}).iloc[:-1]
    save_timestamp_csv(incomplete, target_path)
    save_timestamp_csv(_day_frame("2026-09-24", 1.0).rename(columns={"Model_MW": "y_pred"}), previous_path)

    selected, selected_day = daily._select_cached_price_forecast(
        repo_root=tmp_path,
        forecast_date=target_day,
        target_tz="Europe/Berlin",
        work_root=Path("work"),
    )

    assert selected == previous_path
    assert selected_day == date(2026, 9, 24)
