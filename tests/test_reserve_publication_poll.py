from __future__ import annotations

import csv
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from da_price_forecasting.scripts import reserve_publication_poll as module


class _Response:
    status_code = 200
    content = b"PK-test-workbook"
    text = ""


class _Session:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def get(self, url: str, *, params: dict[str, str], timeout: float) -> _Response:
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        return _Response()


def test_check_publication_uses_capacity_results_endpoint(monkeypatch) -> None:
    session = _Session()
    monkeypatch.setattr(module.pd, "read_excel", lambda *args, **kwargs: pd.DataFrame({"result": [1]}))

    result = module.check_publication(
        session,
        product="aFRR",
        delivery_date=date(2026, 9, 28),
    )

    assert result.available is True
    assert result.http_status == 200
    assert session.calls == [
        {
            "url": module.DEFAULT_URL,
            "params": {
                "productType": "aFRR",
                "market": "CAPACITY",
                "exportFormat": "xlsx",
                "deliveryDate": "2026-09-28",
            },
            "timeout": 60.0,
        }
    ]


def test_once_records_first_observation_and_resumes_without_overwriting(
    monkeypatch,
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "publication.csv"
    observed_at = datetime(2026, 9, 27, 8, 31, 5, tzinfo=ZoneInfo("Europe/Berlin"))
    checks: list[str] = []

    def fake_check(session, *, product, delivery_date, url, timeout_seconds):
        checks.append(product)
        return module.PublicationCheck(True, 200)

    monkeypatch.setattr(module, "check_publication", fake_check)
    kwargs = {
        "delivery_date": date(2026, 9, 28),
        "products": ["FCR"],
        "output_path": output_path,
        "once": True,
        "now": lambda: observed_at,
    }

    first = module.poll_publication_times(**kwargs)
    second = module.poll_publication_times(**kwargs)

    assert first == {"FCR": observed_at}
    assert second == {"FCR": observed_at}
    assert checks == ["FCR"]
    with output_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1
    assert rows[0]["delivery_date"] == "2026-09-28"
    assert rows[0]["product"] == "FCR"
    assert rows[0]["status"] == "published"
    assert rows[0]["first_available_at_local"] == observed_at.isoformat()


def test_once_records_not_observed_status(monkeypatch, tmp_path: Path) -> None:
    output_path = tmp_path / "publication.csv"
    observed_at = datetime(2026, 9, 27, 8, 0, tzinfo=ZoneInfo("Europe/Berlin"))
    monkeypatch.setattr(
        module,
        "check_publication",
        lambda *args, **kwargs: module.PublicationCheck(False, 404, "HTTP 404"),
    )

    found = module.poll_publication_times(
        delivery_date=date(2026, 9, 28),
        products=["mFRR"],
        output_path=output_path,
        once=True,
        now=lambda: observed_at,
    )

    assert found == {}
    with output_path.open(newline="", encoding="utf-8") as handle:
        row = next(csv.DictReader(handle))
    assert row["status"] == "not_observed"
    assert row["last_http_status"] == "404"
    assert row["last_message"] == "HTTP 404"
