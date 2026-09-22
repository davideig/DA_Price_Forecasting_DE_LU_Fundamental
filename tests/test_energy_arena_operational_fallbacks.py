from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from da_price_forecasting.config import EnergyArenaSubmissionConfig, validate_config_payload
from da_price_forecasting.integrations.energy_arena.fallbacks import apply_operational_submission_fallback
from da_price_forecasting.integrations.energy_arena.sources import EnergyArenaForecastResult
from da_price_forecasting.scripts.energy_arena_submit import _build_payload


TZ = "Europe/Berlin"


def test_operational_fallback_fills_missing_target_day_from_previous_forecast_day() -> None:
    donor_index = pd.date_range("2026-09-22T00:00:00+02:00", periods=96, freq="15min")
    forecast = pd.DataFrame({"y_pred": np.arange(96, dtype=float)}, index=donor_index)

    filled, info = apply_operational_submission_fallback(
        forecast,
        forecast_date=date(2026, 9, 23),
        target_tz=TZ,
        columns=["y_pred"],
        source_name="load_model",
    )

    target_index = pd.date_range("2026-09-23T00:00:00+02:00", periods=96, freq="15min")
    assert info is not None
    assert info["donor_day"] == "2026-09-22"
    assert filled.reindex(target_index)["y_pred"].notna().all()
    assert filled.reindex(target_index)["y_pred"].tolist() == forecast["y_pred"].tolist()


def test_energy_arena_payload_uses_operational_fallback_when_enabled(tmp_path: Path) -> None:
    donor_index = pd.date_range("2026-09-22T00:00:00+02:00", periods=96, freq="15min")
    forecast = pd.DataFrame({"y_pred": np.arange(100.0, 196.0)}, index=donor_index)
    submission_config = validate_config_payload(
        {
            "repo_root": tmp_path,
            "source": {
                "kind": "forecast_file",
                "path": str(tmp_path / "forecast.csv"),
                "value_column": "y_pred",
            },
            "forecast_date": "2026-09-23",
            "challenge_id": 20,
            "target_tz": TZ,
            "objective": "point",
            "value_column": "y_pred",
            "enable_operational_fallback": True,
        },
        EnergyArenaSubmissionConfig,
        repo_root=tmp_path,
    )
    result = EnergyArenaForecastResult(
        forecast=forecast,
        source_name="load_model",
        metadata={"source_kind": "forecast_file"},
        default_value_column="y_pred",
    )

    payload, predictions, fallback_info = _build_payload(submission_config, result)

    assert len(predictions) == 96
    assert fallback_info is not None
    assert fallback_info["target_day"] == "2026-09-23"
    assert fallback_info["donor_day"] == "2026-09-22"
    assert payload["values"] == forecast["y_pred"].tolist()
    assert result.metadata is not None
    assert result.metadata["operational_fallback"]["donor_day"] == "2026-09-22"
