from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from da_price_forecasting.integrations.energy_arena.formatters import (
    _expected_day_index,
    extract_point_predictions,
    extract_quantile_predictions,
)

TZ = "Europe/Berlin"


def _real_clock_forecast(start: str, end: str) -> pd.DataFrame:
    """A forecast on the true Europe/Berlin quarter-hourly grid (DST-correct)."""
    index = pd.date_range(start, end, freq="15min", tz=TZ, inclusive="left")
    values = range(len(index))
    return pd.DataFrame(
        {"y_pred": values, "q10": values, "q90": [v + 1 for v in values]},
        index=index,
    )


@pytest.mark.parametrize(
    "day, expected_units",
    [
        (date(2026, 3, 28), 96),   # regular day
        (date(2026, 3, 29), 92),   # spring transition: 23-hour day
        (date(2026, 10, 25), 100),  # autumn transition: 25-hour day
    ],
)
def test_expected_day_index_dst_lengths(day: date, expected_units: int) -> None:
    assert len(_expected_day_index(day, TZ)) == expected_units


def test_point_extraction_emits_actual_market_units_on_dst_days() -> None:
    forecast = _real_clock_forecast("2026-03-27 00:00", "2026-10-27 00:00")

    regular = extract_point_predictions(forecast, date(2026, 3, 28))
    spring = extract_point_predictions(forecast, date(2026, 3, 29))
    autumn = extract_point_predictions(forecast, date(2026, 10, 25))

    assert len(regular) == 96
    assert len(spring) == 92  # 23-hour day, not padded to 96
    assert len(autumn) == 100  # 25-hour day, not truncated to 96

    # The non-existent 02:00-02:45 hour is absent on the spring day.
    assert not any("T02:" in ts for ts in spring["timestamp"])
    # The repeated 02:00-02:45 hour appears twice on the autumn day.
    assert sum("T02:" in ts for ts in autumn["timestamp"]) == 8


def test_quantile_extraction_matches_dst_grid() -> None:
    forecast = _real_clock_forecast("2026-03-28 00:00", "2026-03-30 00:00")
    spring = extract_quantile_predictions(forecast, date(2026, 3, 29), ["q10", "q90"])
    assert len(spring) == 92
    assert all(len(v) == 2 for v in spring["value"])


def test_incomplete_day_is_rejected() -> None:
    forecast = _real_clock_forecast("2026-05-01 00:00", "2026-05-02 00:00")
    truncated = forecast.iloc[:-4]  # drop the last hour
    with pytest.raises(ValueError, match="missing"):
        extract_point_predictions(truncated, date(2026, 5, 1))
