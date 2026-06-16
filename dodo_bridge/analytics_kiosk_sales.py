from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel, Field, field_validator


KIOSK_SALES_SHARE_TOOL = "superset_kiosk_sales_share"
KIOSK_SALES_SHARE_DASHBOARD_ID = 714
KIOSK_SALES_SHARE_CHART_ID = 9533
KIOSK_SALES_SHARE_DATASOURCE_ID = 168
KIOSK_SALES_SHARE_METRIC = "Share sales via Kiosk"
KIOSK_SALES_SHARE_DASHBOARD = "ordres_types_analytics"


class KioskSalesShareRequest(BaseModel):
    month: str = Field(description="Target month in YYYY-MM format.")
    unit_names: list[str] = Field(min_length=1, description="Superset UnitName values.")
    row_limit: int = Field(default=50000, ge=1, le=50000)
    dry_run: bool = False

    @field_validator("month")
    @classmethod
    def clean_month(cls, value: str) -> str:
        parse_month(value)
        return value

    @field_validator("unit_names")
    @classmethod
    def clean_unit_names(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item and item.strip()]
        if not cleaned:
            raise ValueError("at least one unit name is required")
        return cleaned


def build_kiosk_sales_share_payload(body: KioskSalesShareRequest) -> dict[str, Any]:
    start, end = month_range(body.month)
    time_range = f"{start.isoformat()} : {end.isoformat()}"
    filters = [{"col": "UnitName", "op": "IN", "val": body.unit_names}]
    temporal_filter = {
        "clause": "WHERE",
        "comparator": time_range,
        "expressionType": "SIMPLE",
        "operator": "TEMPORAL_RANGE",
        "subject": "Date",
    }
    query = {
        "filters": filters,
        "extras": {"time_grain_sqla": "P1M", "having": "", "where": ""},
        "columns": ["UnitName"],
        "metrics": [KIOSK_SALES_SHARE_METRIC],
        "orderby": [],
        "annotation_layers": [],
        "row_limit": body.row_limit,
        "series_limit": 0,
        "order_desc": True,
        "url_params": {},
        "custom_params": {},
        "custom_form_data": {},
        "time_range": time_range,
        "granularity": "Date",
        "is_timeseries": False,
    }
    form_data = {
        "datasource": f"{KIOSK_SALES_SHARE_DATASOURCE_ID}__table",
        "dashboards": [KIOSK_SALES_SHARE_DASHBOARD_ID],
        "dashboardId": KIOSK_SALES_SHARE_DASHBOARD_ID,
        "slice_id": KIOSK_SALES_SHARE_CHART_ID,
        "viz_type": "table",
        "time_range": time_range,
        "time_grain_sqla": "P1M",
        "granularity_sqla": "Date",
        "adhoc_filters": [temporal_filter],
        "extra_form_data": {
            "filters": filters,
            "time_range": time_range,
            "time_grain_sqla": "P1M",
        },
        "groupby": ["UnitName"],
        "metrics": [KIOSK_SALES_SHARE_METRIC],
        "all_columns": ["UnitName"],
        "query_mode": "aggregate",
        "row_limit": body.row_limit,
        "order_desc": True,
        "show_totals": True,
    }
    return {
        "datasource": {"id": KIOSK_SALES_SHARE_DATASOURCE_ID, "type": "table"},
        "force": False,
        "queries": [query],
        "form_data": form_data,
        "result_format": "json",
        "result_type": "full",
    }


def normalize_kiosk_sales_share_result(
    raw: dict[str, Any],
    body: KioskSalesShareRequest,
) -> dict[str, Any]:
    result = (raw.get("result") or [{}])[0]
    rows = result.get("data") or []
    normalized_rows = [_normalize_row(row) for row in rows if isinstance(row, dict)]
    shares = [
        Decimal(str(row["kiosk_sales_share"]))
        for row in normalized_rows
        if row.get("kiosk_sales_share") is not None
    ]
    average_share_pct = None
    if shares:
        average_share_pct = float((sum(shares, Decimal("0")) / Decimal(len(shares))) * Decimal("100"))

    start, end = month_range(body.month)
    return {
        "status": "ok",
        "capability_id": "get_kiosk_sales_share",
        "source": "Superset",
        "filters": {
            "month": body.month,
            "period": {"from": start.isoformat(), "to": end.isoformat()},
            "unit_names": body.unit_names,
        },
        "summary": {
            "rows_count": len(normalized_rows),
            "average_kiosk_sales_share_pct": average_share_pct,
        },
        "rows": normalized_rows,
        "warnings": [],
        "notes": [
            "Read-only Superset capability.",
            "Metric is SalesDineInKiosk / SalesDineIn; delivery and pickup are not in the denominator.",
        ],
        "superset": {
            "dashboard": KIOSK_SALES_SHARE_DASHBOARD,
            "dashboard_id": KIOSK_SALES_SHARE_DASHBOARD_ID,
            "chart_id": KIOSK_SALES_SHARE_CHART_ID,
            "datasource_id": KIOSK_SALES_SHARE_DATASOURCE_ID,
            "metric": KIOSK_SALES_SHARE_METRIC,
            "rowcount": result.get("rowcount"),
            "is_cached": result.get("is_cached"),
        },
    }


def parse_month(value: str) -> tuple[int, int]:
    parts = value.split("-")
    if len(parts) != 2:
        raise ValueError("month must be YYYY-MM")
    try:
        year = int(parts[0])
        month = int(parts[1])
    except ValueError as exc:
        raise ValueError("month must be YYYY-MM") from exc
    if year < 2000 or year > 2100 or month < 1 or month > 12:
        raise ValueError("month must be YYYY-MM")
    return year, month


def month_range(value: str) -> tuple[date, date]:
    year, month = parse_month(value)
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 1, 1)
    return start, end


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    share = _float(row.get(KIOSK_SALES_SHARE_METRIC))
    return {
        "unit_name": row.get("UnitName"),
        "kiosk_sales_share": share,
        "kiosk_sales_share_pct": share * 100 if share is not None else None,
    }


def _float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (InvalidOperation, TypeError, ValueError):
        return None
