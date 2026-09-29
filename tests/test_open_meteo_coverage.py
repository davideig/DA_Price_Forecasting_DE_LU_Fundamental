from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import yaml

from da_price_forecasting.data.weather import open_meteo_run_provenance_path
from da_price_forecasting.scripts.open_meteo_coverage import _cached_delivery_days, audit_dataset


def test_cached_delivery_days_accepts_mixed_cet_and_cest_offsets(tmp_path: Path) -> None:
    cache = tmp_path / "mixed_offsets.csv"
    cache.write_text(
        "timestamp,value\n"
        "2026-01-15T00:00:00+01:00,1\n"
        "2026-07-15T00:00:00+02:00,2\n",
        encoding="utf-8",
    )

    assert _cached_delivery_days(cache, "Europe/Berlin") == {
        date(2026, 1, 15),
        date(2026, 7, 15),
    }


def _write_fixture(
    repo_root: Path,
    *,
    run: str,
    cached_days: list[str],
    provenance_days: list[str],
    actual_run_hour: str | None = None,
) -> Path:
    cache = repo_root / f"data/weather_run{run}.csv"
    cache.parent.mkdir(parents=True, exist_ok=True)
    timestamps = [pd.Timestamp(day, tz="Europe/Berlin") for day in cached_days]
    pd.DataFrame({"temperature": range(len(timestamps))}, index=timestamps).to_csv(cache)

    provenance = {}
    for raw_day in provenance_days:
        day = pd.Timestamp(raw_day)
        requested = day - pd.Timedelta(days=1) + pd.Timedelta(hours=int(run))
        actual_hour = int(actual_run_hour) if actual_run_hour is not None else int(run)
        actual = day - pd.Timedelta(days=1) + pd.Timedelta(hours=actual_hour)
        provenance[raw_day] = {
            "requested_run_utc": requested.strftime("%Y-%m-%dT%H:%M"),
            "actual_run_utc": actual.strftime("%Y-%m-%dT%H:%M"),
            "fallback_used": actual != requested,
            "reason": None,
        }
    open_meteo_run_provenance_path(cache).write_text(
        json.dumps(provenance),
        encoding="utf-8",
    )

    config_path = repo_root / f"configs/run{run}.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        yaml.safe_dump(
            {
                "kind": "load_forecast_model",
                "config": {
                    "target_tz": "Europe/Berlin",
                    "open_meteo_weather_file": cache.relative_to(repo_root).as_posix(),
                    "open_meteo_start_date": "2026-04-01",
                    "open_meteo_end_date": "2026-04-05",
                },
            }
        ),
        encoding="utf-8",
    )
    return config_path


def test_pre_archive_missing_days_are_reported_as_transition(tmp_path: Path) -> None:
    config = _write_fixture(
        tmp_path,
        run="00",
        cached_days=["2026-04-03", "2026-04-04", "2026-04-05"],
        provenance_days=["2026-04-03", "2026-04-04", "2026-04-05"],
    )

    result = audit_dataset(
        model="load",
        run="00",
        config_path=config,
        repo_root=tmp_path,
    )

    assert result["status"] == "transition"
    assert result["archive_start"] == "2026-04-03"
    assert result["transition_missing_days"] == 2
    assert result["missing_within_archive_days"] == 0


def test_gap_within_archive_fails(tmp_path: Path) -> None:
    config = _write_fixture(
        tmp_path,
        run="03",
        cached_days=["2026-04-03", "2026-04-05"],
        provenance_days=["2026-04-03", "2026-04-05"],
    )

    result = audit_dataset(
        model="wind",
        run="03",
        config_path=config,
        repo_root=tmp_path,
    )

    assert result["status"] == "failed"
    assert result["missing_within_archive_ranges"] == [
        {"start": "2026-04-04", "end": "2026-04-04"}
    ]


def test_cached_day_without_provenance_fails(tmp_path: Path) -> None:
    config = _write_fixture(
        tmp_path,
        run="00",
        cached_days=["2026-04-03", "2026-04-04"],
        provenance_days=["2026-04-03"],
    )

    result = audit_dataset(
        model="solar",
        run="00",
        config_path=config,
        repo_root=tmp_path,
        end_date=date(2026, 4, 4),
    )

    assert result["status"] == "failed"
    assert result["unverified_cached_ranges"] == [
        {"start": "2026-04-04", "end": "2026-04-04"}
    ]


def test_later_run_in_early_history_fails(tmp_path: Path) -> None:
    config = _write_fixture(
        tmp_path,
        run="03",
        cached_days=["2026-04-03"],
        provenance_days=["2026-04-03"],
        actual_run_hour="06",
    )

    result = audit_dataset(
        model="load",
        run="03",
        config_path=config,
        repo_root=tmp_path,
        end_date=date(2026, 4, 3),
    )

    assert result["status"] == "failed"
    assert "06 UTC data" in result["invalid_provenance"][0]


def test_run00_previous_evening_fallback_fails_delivery_day_coverage(tmp_path: Path) -> None:
    config = _write_fixture(
        tmp_path,
        run="00",
        cached_days=["2026-04-03"],
        provenance_days=["2026-04-03"],
    )
    provenance_path = open_meteo_run_provenance_path(tmp_path / "data/weather_run00.csv")
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    provenance["2026-04-03"]["actual_run_utc"] = "2026-04-01T21:00"
    provenance["2026-04-03"]["fallback_used"] = True
    provenance_path.write_text(json.dumps(provenance), encoding="utf-8")

    result = audit_dataset(
        model="wind",
        run="00",
        config_path=config,
        repo_root=tmp_path,
        end_date=date(2026, 4, 3),
    )

    assert result["status"] == "failed"
    assert "complete local delivery day" in result["invalid_provenance"][0]
