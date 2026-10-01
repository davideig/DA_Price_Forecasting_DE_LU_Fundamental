from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from da_price_forecasting.pipelines.common import load_timestamp_csv, save_timestamp_csv
from da_price_forecasting.scripts.operational_gap_repair import (
    ActualDataset,
    discover_actual_datasets,
    impute_persistent_gaps,
    repair_operational_actuals,
)


def test_impute_persistent_gaps_repairs_old_gaps_but_leaves_recent_gap() -> None:
    index = pd.date_range("2026-01-01", "2026-02-05", freq="15min", inclusive="left", tz="Europe/Berlin")
    values = np.arange(len(index), dtype=float)
    frame = pd.DataFrame({"Load_Actual_MW": values}, index=index)
    short_gap = pd.date_range("2026-01-20 10:00", periods=4, freq="15min", tz="Europe/Berlin")
    old_day = pd.date_range("2026-01-21", "2026-01-22", freq="15min", inclusive="left", tz="Europe/Berlin")
    recent_gap = pd.date_range("2026-02-01 10:00", periods=4, freq="15min", tz="Europe/Berlin")
    frame.loc[short_gap.union(old_day).union(recent_gap), "Load_Actual_MW"] = np.nan
    dataset = ActualDataset("load", Path("data/processed/load.csv"), ("Load_Actual_MW",))

    repaired, events, summary = impute_persistent_gaps(
        frame,
        dataset=dataset,
        operation_date=date(2026, 2, 5),
    )

    assert repaired.loc[short_gap.union(old_day), "Load_Actual_MW"].notna().all()
    assert repaired.loc[recent_gap, "Load_Actual_MW"].isna().all()
    methods = {event.method for event in events}
    assert "linear_interpolation" in methods
    assert "seasonal_weekday_quarter_median_8w" in methods
    assert summary["imputed_cells"] == len(short_gap) + len(old_day)
    assert summary["unresolved_cells"] == 0


def test_imputation_uses_only_prior_observed_donors() -> None:
    index = pd.date_range("2026-01-01", "2026-01-04", freq="15min", inclusive="left", tz="Europe/Berlin")
    frame = pd.DataFrame({"Load_Actual_MW": np.nan}, index=index)
    frame.loc[index[-1], "Load_Actual_MW"] = 100.0
    dataset = ActualDataset("load", Path("load.csv"), ("Load_Actual_MW",))

    repaired, events, summary = impute_persistent_gaps(
        frame,
        dataset=dataset,
        operation_date=date(2026, 1, 20),
    )

    assert all(pd.Timestamp(event.timestamp) > index[-1] for event in events)
    assert repaired.loc[repaired.index < index[-1], "Load_Actual_MW"].isna().all()
    assert summary["unresolved_cells"] >= len(index) - 1


def test_previous_imputations_are_not_reused_as_seasonal_donors() -> None:
    index = pd.date_range("2026-01-01", "2026-01-16", freq="15min", inclusive="left", tz="Europe/Berlin")
    frame = pd.DataFrame({"Load_Actual_MW": np.nan}, index=index)
    prior_imputation = pd.Timestamp("2026-01-08 12:00", tz="Europe/Berlin")
    target = pd.Timestamp("2026-01-15 12:00", tz="Europe/Berlin")
    frame.loc[prior_imputation, "Load_Actual_MW"] = 100.0
    dataset = ActualDataset("load", Path("load.csv"), ("Load_Actual_MW",))

    repaired, events, _ = impute_persistent_gaps(
        frame,
        dataset=dataset,
        operation_date=date(2026, 2, 1),
        known_imputed={(prior_imputation, "Load_Actual_MW")},
    )

    assert pd.isna(repaired.loc[target, "Load_Actual_MW"])
    assert all(pd.Timestamp(event.timestamp) != target for event in events)


def test_persistent_gap_repair_handles_dst_delivery_day() -> None:
    index = pd.date_range("2026-10-01", "2026-11-01", freq="15min", inclusive="left", tz="Europe/Berlin")
    frame = pd.DataFrame({"Load_Actual_MW": 100.0}, index=index)
    dst_day = pd.date_range("2026-10-25", "2026-10-26", freq="15min", inclusive="left", tz="Europe/Berlin")
    assert len(dst_day) == 100
    frame.loc[dst_day, "Load_Actual_MW"] = np.nan
    dataset = ActualDataset("load", Path("load.csv"), ("Load_Actual_MW",))

    repaired, events, _ = impute_persistent_gaps(
        frame,
        dataset=dataset,
        operation_date=date(2026, 11, 10),
    )

    assert repaired.loc[dst_day, "Load_Actual_MW"].notna().all()
    assert sum(pd.Timestamp(event.timestamp).date() == date(2026, 10, 25) for event in events) == 100


def test_discover_and_repair_operational_actuals_writes_provenance(tmp_path: Path) -> None:
    config_dir = tmp_path / "configs" / "deployment" / "cutoffs"
    config_dir.mkdir(parents=True)
    config_dir.joinpath("load.yaml").write_text(
        """
kind: load_forecast_model
config:
  actual_load_file: data/processed/load_forecast/actual_load.csv
""".strip(),
        encoding="utf-8",
    )
    path = tmp_path / "data" / "processed" / "load_forecast" / "actual_load.csv"
    index = pd.date_range("2026-01-01", "2026-01-20", freq="15min", inclusive="left", tz="Europe/Berlin")
    frame = pd.DataFrame({"Load_Actual_MW": 100.0}, index=index)
    gap = pd.date_range("2026-01-05 12:00", periods=2, freq="15min", tz="Europe/Berlin")
    frame.loc[gap, "Load_Actual_MW"] = np.nan
    save_timestamp_csv(frame, path)

    datasets = discover_actual_datasets(tmp_path)
    assert [(item.name, item.path) for item in datasets] == [("load", path)]

    report = repair_operational_actuals(repo_root=tmp_path, operation_date=date(2026, 1, 20))

    assert report["imputed_cells"] == 2
    assert load_timestamp_csv(path, "Europe/Berlin").loc[gap, "Load_Actual_MW"].notna().all()
    provenance = pd.read_csv(
        tmp_path / "data" / "processed" / "operational_quality" / "persistent_gap_imputations.csv"
    )
    assert len(provenance) == 2
    assert set(provenance["method"]) == {"linear_interpolation"}
    assert (tmp_path / "data/processed/operational_quality/persistent_gap_repair_2026-01-20.json").exists()
