from __future__ import annotations

from datetime import date
from pathlib import Path

from da_price_forecasting.scripts import operational_data_quality as quality


def test_collect_fallback_events_filters_and_records_source(tmp_path: Path) -> None:
    logs = tmp_path / "logs" / "chair_vm_tasks"
    logs.mkdir(parents=True)
    (logs / "price-submit_2026-09-25.log").write_text(
        "normal line\n"
        "[fallback] using yesterday\n"
        "[OPEN-METEO] Using fallback model run 04 instead of 06 for day 2026-09-26.\n",
        encoding="utf-8",
    )
    (logs / "price-submit_2026-09-24.log").write_text("[fallback] old event\n", encoding="utf-8")

    events = quality._collect_fallback_events(tmp_path, date(2026, 9, 25))

    assert [event["line"] for event in events] == [2, 3]
    assert all(event["log"].endswith("_2026-09-25.log") for event in events)


def test_build_quality_report_marks_fallback_as_degraded(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        quality,
        "_collect_dwd_weather",
        lambda repo_root, forecast_date: [{"ready": True}],
    )
    monkeypatch.setattr(quality, "_collect_required_inputs", lambda repo_root: (3, []))
    monkeypatch.setattr(
        quality,
        "_collect_fallback_events",
        lambda repo_root, operation_date: [{"message": "[fallback] donor day"}],
    )
    monkeypatch.setattr(
        quality,
        "_collect_submission_responses",
        lambda repo_root, forecast_date: ["results/submission_response.json"],
    )

    report = quality.build_quality_report(
        repo_root=tmp_path,
        operation_date=date(2026, 9, 25),
        forecast_date=date(2026, 9, 26),
    )

    assert report["status"] == "degraded"
    assert report["required_inputs"] == {"checked": 3, "present": 3, "missing": []}
    assert report["submission_responses"] == ["results/submission_response.json"]
