from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


EMPLOYEE_DISCOUNT_TOOL = "superset_employee_discount_chart"
EMPLOYEE_DISCOUNT_DASHBOARD_ID = 1410
EMPLOYEE_DISCOUNT_CHART_ID = 26708
EMPLOYEE_DISCOUNT_METRIC = "employee_segment_discount"
EMPLOYEE_DISCOUNT_SEGMENT = "Сотрудникам"


class Period(BaseModel):
    from_date: date = Field(alias="from")
    to_date: date = Field(alias="to")


class EmployeeDiscountRequest(BaseModel):
    period: Period
    unit_names: list[str] = Field(min_length=1, description="Superset UnitName values.")
    group_by: list[Literal["unit", "action", "promocode"]] = Field(
        default_factory=lambda: ["unit", "action", "promocode"]
    )
    row_limit: int = Field(default=50000, ge=1, le=50000)
    dry_run: bool = False

    @field_validator("unit_names")
    @classmethod
    def clean_unit_names(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item and item.strip()]
        if not cleaned:
            raise ValueError("at least one unit name is required")
        return cleaned


def build_employee_discount_payload(body: EmployeeDiscountRequest) -> dict[str, Any]:
    columns = ["UnitName", "ActionSegmentationAndSource"]
    if "action" in body.group_by:
        columns.extend(["BonusActionUUId", "ActionName"])
    if "promocode" in body.group_by:
        columns.append("PromocodeMasked")

    time_range = f"{body.period.from_date.isoformat()} : {body.period.to_date.isoformat()}"
    filters = [
        {"col": "UnitName", "op": "IN", "val": body.unit_names},
        {"col": "ActionSegmentationAndSource", "op": "IN", "val": [EMPLOYEE_DISCOUNT_SEGMENT]},
    ]
    return {
        "datasource": {"id": 3110, "type": "table"},
        "force": False,
        "queries": [
            {
                "filters": filters,
                "extras": {"time_grain_sqla": "P1M", "having": "", "where": ""},
                "columns": columns,
                "metrics": ["Discount", "SalesWithoutDiscount"],
                "orderby": [],
                "annotation_layers": [],
                "row_limit": body.row_limit,
                "series_limit": 0,
                "order_desc": True,
                "url_params": {},
                "custom_params": {},
                "custom_form_data": {},
                "time_range": time_range,
                "granularity": "SaleDate",
                "is_timeseries": False,
            }
        ],
        "form_data": {
            "adhoc_filters": [
                {
                    "clause": "WHERE",
                    "comparator": ["1"],
                    "datasourceWarning": False,
                    "expressionType": "SIMPLE",
                    "filterOptionName": "filter_is_promocode",
                    "isExtra": False,
                    "isNew": False,
                    "operator": "IN",
                    "operatorId": "IN",
                    "sqlExpression": None,
                    "subject": "isPromocode",
                },
                {
                    "clause": "WHERE",
                    "comparator": "No filter",
                    "datasourceWarning": False,
                    "expressionType": "SIMPLE",
                    "filterOptionName": "filter_sale_date",
                    "isExtra": True,
                    "isNew": False,
                    "operator": "TEMPORAL_RANGE",
                    "sqlExpression": None,
                    "subject": "SaleDate",
                },
            ],
            "all_columns": [
                "UnitUUId",
                "UnitName",
                "CountryId",
                "CountryName",
                "Partner",
                "CityName",
                "RegionName",
                "OrderType",
                "OrderSource",
                "SaleDate",
                "Discount",
                "RevenueWithDiscount",
                "RevenueWithoutDiscount",
                "ApplyCount",
                "UnitCost",
                "BonusActionUUId",
                "ActionCategoryName",
                "ActionArea",
                "ActionResultType",
                "ActionName",
                "DodoIsActionCategoryId",
                "DodoisActionCategoryName",
                "ActionType",
                "Promocode",
                "DiscountType",
                "ApplyType",
                "OrderRevenueWithDiscount",
                "OrderRevenueWithoutDiscount",
                "OrderUnitCost",
            ],
            "allow_rearrange_columns": True,
            "allow_render_html": False,
            "color_pn": False,
            "column_config": {},
            "comparison_color_scheme": "Green",
            "comparison_type": "values",
            "conditional_formatting": [],
            "dashboards": [EMPLOYEE_DISCOUNT_DASHBOARD_ID],
            "datasource": "3110__table",
            "extra_form_data": {
                "filters": filters,
                "time_range": time_range,
                "time_grain_sqla": "P1M",
            },
            "groupby": columns,
            "include_search": True,
            "metrics": ["Discount", "SalesWithoutDiscount"],
            "order_by_cols": [],
            "order_desc": True,
            "percent_metrics": [],
            "query_mode": "aggregate",
            "row_limit": body.row_limit,
            "server_page_length": 10,
            "show_cell_bars": False,
            "show_totals": True,
            "slice_id": EMPLOYEE_DISCOUNT_CHART_ID,
            "table_timestamp_format": "smart_date",
            "temporal_columns_lookup": {"SaleDate": True, "SaleDateAgg": True},
            "viz_type": "table",
            "dashboardId": EMPLOYEE_DISCOUNT_DASHBOARD_ID,
            "time_range": time_range,
            "time_grain_sqla": "P1M",
        },
        "result_format": "json",
        "result_type": "full",
    }


def normalize_employee_discount_result(
    raw: dict[str, Any],
    body: EmployeeDiscountRequest,
) -> dict[str, Any]:
    result = (raw.get("result") or [{}])[0]
    rows = result.get("data") or []
    normalized_rows = [_normalize_row(row) for row in rows if isinstance(row, dict)]
    discount_total = sum((_decimal(row.get("discount_amount")) for row in normalized_rows), Decimal("0"))
    sales_total = sum((_decimal(row.get("sales_without_discount")) for row in normalized_rows), Decimal("0"))
    share = None
    if sales_total:
        share = float((discount_total / sales_total) * Decimal("100"))

    return {
        "status": "ok",
        "capability_id": "get_employee_discount",
        "source": "Superset",
        "filters": {
            "period": {
                "from": body.period.from_date.isoformat(),
                "to": body.period.to_date.isoformat(),
            },
            "unit_names": body.unit_names,
            "discount_type": EMPLOYEE_DISCOUNT_SEGMENT,
        },
        "summary": {
            "employee_discount_amount": float(discount_total),
            "sales_without_discount": float(sales_total),
            "discount_share_of_sales_without_discount_pct": share,
            "rows_count": len(normalized_rows),
        },
        "rows": normalized_rows,
        "warnings": [],
        "notes": [
            "Read-only Superset capability.",
            "PII is not requested by this recipe.",
        ],
        "superset": {
            "dashboard_id": EMPLOYEE_DISCOUNT_DASHBOARD_ID,
            "chart_id": EMPLOYEE_DISCOUNT_CHART_ID,
            "rowcount": result.get("rowcount"),
            "is_cached": result.get("is_cached"),
        },
    }


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "unit_name": row.get("UnitName"),
        "discount_segment": row.get("ActionSegmentationAndSource"),
        "bonus_action_uuid": row.get("BonusActionUUId"),
        "action_name": row.get("ActionName"),
        "promocode_masked": row.get("PromocodeMasked"),
        "discount_amount": _float(row.get("Discount")),
        "sales_without_discount": _float(row.get("SalesWithoutDiscount")),
    }


def _decimal(value: Any) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
