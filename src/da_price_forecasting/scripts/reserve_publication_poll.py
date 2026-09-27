from __future__ import annotations

import argparse
import csv
import io
import time
import warnings
from dataclasses import dataclass
from datetime import date, datetime, time as datetime_time, timedelta
from pathlib import Path
from typing import Callable, Iterable
from zoneinfo import ZoneInfo

import pandas as pd
import requests


DEFAULT_URL = "https://www.regelleistung.net/apps/crds/api/v2/tenders/results/aggregated"
DEFAULT_PRODUCTS = ("FCR", "aFRR", "mFRR")
DEFAULT_OUTPUT = Path("data/processed/operational_quality/reserve_publication_times.csv")
CSV_FIELDS = (
    "observation_date",
    "delivery_date",
    "product",
    "status",
    "first_available_at_local",
    "first_available_at_utc",
    "polls",
    "last_http_status",
    "last_message",
)


@dataclass(frozen=True)
class PublicationCheck:
    available: bool
    http_status: int | None
    message: str = ""


def parse_clock(value: str) -> datetime_time:
    try:
        return datetime.strptime(value, "%H:%M").time()
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Time values must use HH:MM, for example 11:20.") from exc


def check_publication(
    session: requests.Session,
    *,
    product: str,
    delivery_date: date,
    url: str = DEFAULT_URL,
    timeout_seconds: float = 60.0,
) -> PublicationCheck:
    params = {
        "productType": product,
        "market": "CAPACITY",
        "exportFormat": "xlsx",
        "deliveryDate": delivery_date.isoformat(),
    }
    try:
        response = session.get(url, params=params, timeout=timeout_seconds)
    except requests.RequestException as exc:
        return PublicationCheck(False, None, f"request error: {exc}")

    if response.status_code != 200:
        return PublicationCheck(False, response.status_code, f"HTTP {response.status_code}")
    if not response.content.startswith(b"PK"):
        message = response.text.strip().replace("\n", " ")[:240]
        return PublicationCheck(False, response.status_code, message or "response was not XLSX")

    try:
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="Workbook contains no default style.*",
                module="openpyxl",
            )
            frame = pd.read_excel(io.BytesIO(response.content), engine="openpyxl")
    except Exception as exc:
        return PublicationCheck(False, response.status_code, f"invalid XLSX: {exc}")
    if frame.empty:
        return PublicationCheck(False, response.status_code, "XLSX contained no result rows")
    return PublicationCheck(True, response.status_code)


def _load_existing_observations(output_path: Path, delivery_date: date) -> dict[str, dict[str, str]]:
    if not output_path.exists():
        return {}
    with output_path.open(newline="", encoding="utf-8") as handle:
        rows = csv.DictReader(handle)
        return {
            row["product"]: row
            for row in rows
            if row.get("delivery_date") == delivery_date.isoformat()
            and row.get("status") == "published"
        }


def _append_rows(output_path: Path, rows: Iterable[dict[str, object]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not output_path.exists() or output_path.stat().st_size == 0
    with output_path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        if write_header:
            writer.writeheader()
        for row in rows:
            writer.writerow(row)


def poll_publication_times(
    *,
    delivery_date: date,
    products: Iterable[str] = DEFAULT_PRODUCTS,
    output_path: Path = DEFAULT_OUTPUT,
    target_tz: str = "Europe/Berlin",
    stop_at: datetime_time = datetime_time(11, 20),
    interval_seconds: float = 60.0,
    timeout_seconds: float = 60.0,
    url: str = DEFAULT_URL,
    once: bool = False,
    now: Callable[[], datetime] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    session: requests.Session | None = None,
) -> dict[str, datetime]:
    tz = ZoneInfo(target_tz)
    now = now or (lambda: datetime.now(tz))
    products = tuple(dict.fromkeys(products))
    invalid_products = sorted(set(products).difference(DEFAULT_PRODUCTS))
    if invalid_products:
        raise ValueError(f"Unsupported reserve products: {', '.join(invalid_products)}")
    if interval_seconds <= 0 and not once:
        raise ValueError("interval_seconds must be positive unless once=True.")

    current = now().astimezone(tz)
    stop = datetime.combine(current.date(), stop_at, tzinfo=tz)
    existing = _load_existing_observations(output_path, delivery_date)
    found = {
        product: datetime.fromisoformat(row["first_available_at_local"])
        for product, row in existing.items()
    }
    polls = {product: 0 for product in products}
    last_checks: dict[str, PublicationCheck] = {}
    client = session or requests.Session()

    print(
        f"Polling reserve-capacity results for delivery day {delivery_date} "
        f"until {stop.isoformat()}.",
        flush=True,
    )
    for product, published_at in found.items():
        print(f"[resume] {product} was already observed at {published_at.isoformat()}.", flush=True)

    while len(found) < len(products) and (once or now().astimezone(tz) < stop):
        for product in products:
            if product in found:
                continue
            polls[product] += 1
            check = check_publication(
                client,
                product=product,
                delivery_date=delivery_date,
                url=url,
                timeout_seconds=timeout_seconds,
            )
            last_checks[product] = check
            if not check.available:
                continue

            observed_at = now().astimezone(tz)
            found[product] = observed_at
            _append_rows(
                output_path,
                [
                    {
                        "observation_date": observed_at.date().isoformat(),
                        "delivery_date": delivery_date.isoformat(),
                        "product": product,
                        "status": "published",
                        "first_available_at_local": observed_at.isoformat(),
                        "first_available_at_utc": observed_at.astimezone(ZoneInfo("UTC")).isoformat(),
                        "polls": polls[product],
                        "last_http_status": check.http_status or "",
                        "last_message": "",
                    }
                ],
            )
            print(f"[observed] {product}: {observed_at.isoformat()}", flush=True)

        if once or len(found) == len(products):
            break
        sleep(interval_seconds)

    missing_rows = []
    finished_at = now().astimezone(tz)
    for product in products:
        if product in found:
            continue
        check = last_checks.get(product, PublicationCheck(False, None, "not checked"))
        missing_rows.append(
            {
                "observation_date": finished_at.date().isoformat(),
                "delivery_date": delivery_date.isoformat(),
                "product": product,
                "status": "not_observed",
                "first_available_at_local": "",
                "first_available_at_utc": "",
                "polls": polls[product],
                "last_http_status": check.http_status or "",
                "last_message": check.message,
            }
        )
        print(f"[not observed] {product}: {check.message}", flush=True)
    if missing_rows:
        _append_rows(output_path, missing_rows)
    return found


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Measure when next-day regelleistung.net capacity results become downloadable."
    )
    parser.add_argument(
        "--delivery-date",
        type=date.fromisoformat,
        default=None,
        help="Delivery day; defaults to tomorrow in --target-tz.",
    )
    parser.add_argument("--product", action="append", choices=DEFAULT_PRODUCTS, default=[])
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--target-tz", default="Europe/Berlin")
    parser.add_argument("--stop-at", type=parse_clock, default=datetime_time(11, 20))
    parser.add_argument("--interval-seconds", type=float, default=60.0)
    parser.add_argument("--timeout-seconds", type=float, default=60.0)
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--once", action="store_true", help="Check each product once and exit.")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    tz = ZoneInfo(args.target_tz)
    delivery_date = args.delivery_date or (datetime.now(tz).date() + timedelta(days=1))
    poll_publication_times(
        delivery_date=delivery_date,
        products=args.product or DEFAULT_PRODUCTS,
        output_path=args.output,
        target_tz=args.target_tz,
        stop_at=args.stop_at,
        interval_seconds=args.interval_seconds,
        timeout_seconds=args.timeout_seconds,
        url=args.url,
        once=args.once,
    )


if __name__ == "__main__":
    main()
