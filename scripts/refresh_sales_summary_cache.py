#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import requests

from dodo_bridge.config import get_settings
from dodo_bridge.pizzerias import load_pizzerias


MOSCOW_TZ = ZoneInfo("Europe/Moscow")


def response_error_summary(response: requests.Response) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "status_code": response.status_code,
        "url": response.url,
    }
    try:
        payload = response.json()
    except ValueError:
        text = response.text.strip()
        if text:
            summary["body_preview"] = text[:1000]
        return summary

    if isinstance(payload, dict):
        detail = payload.get("detail")
        summary["body"] = payload
        if isinstance(detail, dict):
            summary["external_status"] = detail.get("external_status")
            summary["external_code"] = detail.get("external_code")
            summary["error"] = detail.get("error")
    else:
        summary["body"] = payload
    return summary


def resolve_period(
    *,
    preset: str,
    from_date: date | None,
    to_date: date | None,
    today: date | None = None,
) -> tuple[date, date]:
    if from_date or to_date:
        if not from_date or not to_date:
            raise ValueError("Provide both --from and --to, or neither")
        if to_date < from_date:
            raise ValueError("--to must be greater than or equal to --from")
        return from_date, to_date

    today = today or datetime.now(MOSCOW_TZ).date()
    if preset == "yesterday":
        day = today - timedelta(days=1)
        return day, day
    if preset == "current-month":
        from_day = today.replace(day=1)
        to_day = today - timedelta(days=1)
        if to_day < from_day:
            to_day = from_day
        return from_day, to_day
    if preset == "previous-month":
        first_this_month = today.replace(day=1)
        last_previous_month = first_this_month - timedelta(days=1)
        return last_previous_month.replace(day=1), last_previous_month
    raise ValueError(f"Unknown preset: {preset}")


def unit_ids_from_settings(units: str) -> str:
    if units != "all":
        return units

    settings = get_settings()
    pizzerias = load_pizzerias(settings.dodo_pizzerias_path).get("pizzerias", [])
    unit_ids = [str(item["unit_id"]) for item in pizzerias if item.get("unit_id")]
    if not unit_ids:
        raise RuntimeError("No pizzerias found in DODO_PIZZERIAS_PATH")
    return ",".join(unit_ids)


def refresh_cache(
    *,
    base_url: str,
    units: str,
    from_date: date,
    to_date: date,
    cache_mode: str,
    timeout: int,
) -> dict[str, Any]:
    settings = get_settings()
    if not settings.api_keys:
        raise RuntimeError("DODO_BRIDGE_API_KEYS is empty")

    response = requests.get(
        f"{base_url.rstrip('/')}/dodo/accounting/sales/summary",
        headers={"X-Bridge-Key": settings.api_keys[0]},
        params={
            "units": units,
            "from": from_date.isoformat(),
            "to": to_date.isoformat(),
            "cacheMode": cache_mode,
        },
        timeout=timeout,
    )
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise RuntimeError(json.dumps(response_error_summary(response), ensure_ascii=False)) from exc
    return response.json()


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh Bridge daily sales summary cache.")
    parser.add_argument("--preset", choices=["yesterday", "current-month", "previous-month"], default="yesterday")
    parser.add_argument("--from", dest="from_date", type=date.fromisoformat)
    parser.add_argument("--to", dest="to_date", type=date.fromisoformat)
    parser.add_argument("--units", default="all", help="Comma-separated unit ids, or 'all'.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--cache-mode",
        choices=["auto", "refresh"],
        default="refresh",
        help="Use refresh for authoritative recalculation, or auto to fill only cache misses.",
    )
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args()

    try:
        from_day, to_day = resolve_period(
            preset=args.preset,
            from_date=args.from_date,
            to_date=args.to_date,
        )
        units = unit_ids_from_settings(args.units)
        result = refresh_cache(
            base_url=args.base_url,
            units=units,
            from_date=from_day,
            to_date=to_day,
            cache_mode=args.cache_mode,
            timeout=args.timeout,
        )
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "ok": True,
                "period": {"from": from_day.isoformat(), "to": to_day.isoformat()},
                "complete": result.get("complete"),
                "total": result.get("total"),
                "source": result.get("source"),
                "cache_mode": args.cache_mode,
            },
            ensure_ascii=False,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
