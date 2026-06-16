from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel, Field, field_validator

from dodo_bridge.analytics_kiosk_sales import month_range, parse_month


CLIENTS_PHONE_SHARE_TOOL = "superset_clients_phone_share"
CLIENTS_PHONE_SHARE_DASHBOARD_ID = 868
CLIENTS_PHONE_SHARE_CHART_ID = 18721
CLIENTS_PHONE_SHARE_DATASOURCE_ID = 1615
CLIENTS_PHONE_SHARE_BASE_URL = "https://officemanager.dodois.io"
CLIENTS_PHONE_SHARE_DASHBOARD_URL = (
    "https://officemanager.dodois.io/OfficeManager/Analytics/Client_analytics"
)
CLIENTS_PHONE_SHARE_METRIC = "Share of dine in identified orders via cashier"
CLIENTS_PHONE_IDENTIFIED_METRIC = "Count dine in identified orders via cashier"
CLIENTS_PHONE_ORDERS_METRIC = "Count dine in orders via cashier"
CLIENTS_PHONE_DASHBOARD = "Client_analytics"


class ClientsPhoneShareRequest(BaseModel):
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


def build_clients_phone_share_payload(body: ClientsPhoneShareRequest) -> dict[str, Any]:
    start, end = month_range(body.month)
    time_range = f"{start.isoformat()} : {end.isoformat()}"
    filters = [{"col": "UnitName", "op": "IN", "val": body.unit_names}]
    temporal_filter = {
        "clause": "WHERE",
        "comparator": time_range,
        "expressionType": "SIMPLE",
        "operator": "TEMPORAL_RANGE",
        "subject": "date",
    }
    metrics = [
        CLIENTS_PHONE_SHARE_METRIC,
        CLIENTS_PHONE_IDENTIFIED_METRIC,
        CLIENTS_PHONE_ORDERS_METRIC,
    ]
    query = {
        "filters": filters,
        "extras": {"time_grain_sqla": "P1M", "having": "", "where": ""},
        "columns": ["UnitName"],
        "metrics": metrics,
        "orderby": [],
        "annotation_layers": [],
        "row_limit": body.row_limit,
        "series_limit": 0,
        "order_desc": True,
        "url_params": {},
        "custom_params": {},
        "custom_form_data": {},
        "time_range": time_range,
        "granularity": "date",
        "is_timeseries": False,
    }
    form_data = {
        "datasource": f"{CLIENTS_PHONE_SHARE_DATASOURCE_ID}__table",
        "dashboards": [CLIENTS_PHONE_SHARE_DASHBOARD_ID],
        "dashboardId": CLIENTS_PHONE_SHARE_DASHBOARD_ID,
        "slice_id": CLIENTS_PHONE_SHARE_CHART_ID,
        "viz_type": "table",
        "time_range": time_range,
        "time_grain_sqla": "P1M",
        "granularity_sqla": "date",
        "adhoc_filters": [temporal_filter],
        "extra_form_data": {
            "filters": filters,
            "time_range": time_range,
            "time_grain_sqla": "P1M",
        },
        "groupby": ["UnitName"],
        "metrics": metrics,
        "all_columns": ["UnitName"],
        "query_mode": "aggregate",
        "row_limit": body.row_limit,
        "order_desc": True,
        "show_totals": True,
    }
    return {
        "datasource": {"id": CLIENTS_PHONE_SHARE_DATASOURCE_ID, "type": "table"},
        "force": False,
        "queries": [query],
        "form_data": form_data,
        "result_format": "json",
        "result_type": "full",
    }


def normalize_clients_phone_share_result(
    raw: dict[str, Any],
    body: ClientsPhoneShareRequest,
) -> dict[str, Any]:
    result = (raw.get("result") or [{}])[0]
    rows = result.get("data") or []
    normalized_rows = [_normalize_row(row) for row in rows if isinstance(row, dict)]
    shares = [
        Decimal(str(row["identified_orders_share"]))
        for row in normalized_rows
        if row.get("identified_orders_share") is not None
    ]
    average_share_pct = None
    if shares:
        average_share_pct = float((sum(shares, Decimal("0")) / Decimal(len(shares))) * Decimal("100"))

    start, end = month_range(body.month)
    return {
        "status": "ok",
        "capability_id": "get_clients_phone_share",
        "source": "Superset",
        "filters": {
            "month": body.month,
            "period": {"from": start.isoformat(), "to": end.isoformat()},
            "unit_names": body.unit_names,
        },
        "summary": {
            "rows_count": len(normalized_rows),
            "average_identified_orders_share_pct": average_share_pct,
        },
        "rows": normalized_rows,
        "warnings": [],
        "notes": [
            "Read-only Superset capability.",
            "Metric is dine-in cashier orders with identified client divided by all dine-in cashier orders.",
        ],
        "superset": {
            "dashboard": CLIENTS_PHONE_DASHBOARD,
            "dashboard_id": CLIENTS_PHONE_SHARE_DASHBOARD_ID,
            "chart_id": CLIENTS_PHONE_SHARE_CHART_ID,
            "datasource_id": CLIENTS_PHONE_SHARE_DATASOURCE_ID,
            "metric": CLIENTS_PHONE_SHARE_METRIC,
            "rowcount": result.get("rowcount"),
            "is_cached": result.get("is_cached"),
        },
    }


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    share = _float(row.get(CLIENTS_PHONE_SHARE_METRIC))
    return {
        "unit_name": row.get("UnitName"),
        "identified_orders_share": share,
        "identified_orders_share_pct": share * 100 if share is not None else None,
        "identified_orders_count": _float(row.get(CLIENTS_PHONE_IDENTIFIED_METRIC)),
        "orders_count": _float(row.get(CLIENTS_PHONE_ORDERS_METRIC)),
    }


def _float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (InvalidOperation, TypeError, ValueError):
        return None
