from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from da_price_forecasting.pipelines.common import load_timestamp_csv, save_timestamp_csv
from da_price_forecasting.scripts.operational_component_history import (
    model_feature_fallback_used,
    store_component_forecast_history,
)


def _day(day: str) -> pd.DatetimeIndex:
    start = pd.Timestamp(day, tz="Europe/Berlin")
    return pd.date_range(start, start + pd.DateOffset(days=1), freq="15min", inclusive="left")


def test_component_history_is_immutable_and_keeps_rerun(tmp_path: Path) -> None:
    forecast_path = tmp_path / "forecast.csv"
    index = _day("2026-09-28")
    save_timestamp_csv(pd.DataFrame({"Load_Model_MW": 1.0}, index=index), forecast_path)

    first = store_component_forecast_history(
        repo_root=tmp_path,
        cutoff="0700",
        component="load",
        forecast_path=forecast_path,
        forecast_date=date(2026, 9, 28),
        target_tz="Europe/Berlin",
        recorded_at=datetime(2026, 9, 27, 4, 40, tzinfo=timezone.utc),
    )
    save_timestamp_csv(pd.DataFrame({"Load_Model_MW": 2.0}, index=index), forecast_path)
    second = store_component_forecast_history(
        repo_root=tmp_path,
        cutoff="0700",
        component="load",
        forecast_path=forecast_path,
        forecast_date=date(2026, 9, 28),
        target_tz="Europe/Berlin",
        recorded_at=datetime(2026, 9, 27, 5, 0, tzinfo=timezone.utc),
    )

    canonical = load_timestamp_csv(first.path, "Europe/Berlin")
    rerun = load_timestamp_csv(second.rerun_path, "Europe/Berlin")
    assert canonical["Load_Model_MW"].eq(1.0).all()
    assert rerun["Load_Model_MW"].eq(2.0).all()
    assert second.rerun_path is not None


def test_component_history_marks_imputed_target_day_as_fallback(tmp_path: Path) -> None:
    forecast_path = tmp_path / "forecast.csv"
    donor_index = _day("2026-09-27")
    target_index = _day("2026-09-28")
    source = pd.DataFrame(
        {"Solar_Model_MW": np.concatenate([np.arange(len(donor_index), dtype=float), [np.nan] * len(target_index)])},
        index=donor_index.append(target_index),
    )
    save_timestamp_csv(source, forecast_path)

    stored = store_component_forecast_history(
        repo_root=tmp_path,
        cutoff="0700",
        component="solar",
        forecast_path=forecast_path,
        forecast_date=date(2026, 9, 28),
        target_tz="Europe/Berlin",
    )

    history = load_timestamp_csv(stored.path, "Europe/Berlin")
    target = history.loc[target_index]
    assert stored.fallback_used is True
    assert stored.fallback_info["donor_day"] == "2026-09-27"
    assert target["fallback_used"].astype(bool).all()
    assert target["Solar_Model_MW"].tolist() == list(np.arange(len(target_index), dtype=float))


def test_component_history_marks_backfilled_training_days(tmp_path: Path) -> None:
    forecast_path = tmp_path / "forecast.csv"
    old_index = _day("2026-09-27")
    target_index = _day("2026-09-28")
    source = pd.DataFrame(
        {"Wind_Onshore_Model_MW": 3.0},
        index=old_index.append(target_index),
    )
    save_timestamp_csv(source, forecast_path)

    stored = store_component_forecast_history(
        repo_root=tmp_path,
        cutoff="0800",
        component="wind",
        forecast_path=forecast_path,
        forecast_date=date(2026, 9, 28),
        target_tz="Europe/Berlin",
    )

    history = load_timestamp_csv(stored.path, "Europe/Berlin")
    assert history.loc[old_index, "backfilled"].astype(bool).all()
    assert not history.loc[target_index, "backfilled"].astype(bool).any()


def test_component_history_detects_feature_level_fallback(tmp_path: Path) -> None:
    output = tmp_path / "renewable_features.csv"
    provenance = output.with_suffix(".csv.operational_provenance.json")
    provenance.write_text(
        '{"2026-09-28": {"fallback_used": true, "donor_day": "2026-09-27"}}',
        encoding="utf-8",
    )
    payload = {"config": {"renewable_proxy_file": str(output), "extra_renewable_proxy_files": []}}

    assert model_feature_fallback_used(payload, tmp_path, date(2026, 9, 28)) is True
    assert model_feature_fallback_used(payload, tmp_path, date(2026, 9, 29)) is False
