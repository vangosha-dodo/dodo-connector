from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest
import requests

from scripts.refresh_sales_summary_cache import refresh_cache, resolve_period, response_error_summary


def test_resolve_yesterday_period() -> None:
    assert resolve_period(
        preset="yesterday",
        from_date=None,
        to_date=None,
        today=date(2026, 6, 18),
    ) == (date(2026, 6, 17), date(2026, 6, 17))


def test_resolve_current_month_period() -> None:
    assert resolve_period(
        preset="current-month",
        from_date=None,
        to_date=None,
        today=date(2026, 6, 18),
    ) == (date(2026, 6, 1), date(2026, 6, 17))


def test_resolve_previous_month_period() -> None:
    assert resolve_period(
        preset="previous-month",
        from_date=None,
        to_date=None,
        today=date(2026, 6, 18),
    ) == (date(2026, 5, 1), date(2026, 5, 31))


def test_resolve_explicit_period() -> None:
    assert resolve_period(
        preset="yesterday",
        from_date=date(2026, 5, 1),
        to_date=date(2026, 5, 31),
    ) == (date(2026, 5, 1), date(2026, 5, 31))


def test_resolve_rejects_partial_explicit_period() -> None:
    with pytest.raises(ValueError):
        resolve_period(preset="yesterday", from_date=date(2026, 5, 1), to_date=None)


def test_refresh_cache_passes_cache_mode(monkeypatch) -> None:
    captured = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"complete": True}

    def fake_get(url, *, headers, params, timeout):  # noqa: ANN001
        captured["url"] = url
        captured["headers"] = headers
        captured["params"] = params
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(
        "scripts.refresh_sales_summary_cache.get_settings",
        lambda: SimpleNamespace(api_keys=["secret"]),
    )
    monkeypatch.setattr("scripts.refresh_sales_summary_cache.requests.get", fake_get)

    result = refresh_cache(
        base_url="http://bridge.local/",
        units="unit-1",
        from_date=date(2026, 6, 1),
        to_date=date(2026, 6, 18),
        cache_mode="auto",
        timeout=1200,
    )

    assert result == {"complete": True}
    assert captured["url"] == "http://bridge.local/dodo/accounting/sales/summary"
    assert captured["headers"] == {"X-Bridge-Key": "secret"}
    assert captured["params"]["cacheMode"] == "auto"
    assert captured["params"]["from"] == "2026-06-01"
    assert captured["params"]["to"] == "2026-06-18"
    assert captured["timeout"] == 1200


def test_response_error_summary_extracts_bridge_external_status() -> None:
    response = requests.Response()
    response.status_code = 502
    response.url = "http://bridge.example/dodo/accounting/sales/summary"
    response._content = (  # noqa: SLF001
        b'{"detail":{"error":"external_http_error","tool_name":"dodo_accounting_sales","external_status":401}}'
    )
    response.headers["Content-Type"] = "application/json"

    assert response_error_summary(response) == {
        "status_code": 502,
        "url": "http://bridge.example/dodo/accounting/sales/summary",
        "body": {
            "detail": {
                "error": "external_http_error",
                "tool_name": "dodo_accounting_sales",
                "external_status": 401,
            }
        },
        "external_status": 401,
        "external_code": None,
        "error": "external_http_error",
    }
