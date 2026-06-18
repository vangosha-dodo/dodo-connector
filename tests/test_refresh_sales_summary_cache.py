from __future__ import annotations

from datetime import date

import pytest

from scripts.refresh_sales_summary_cache import resolve_period


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
