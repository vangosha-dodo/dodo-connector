from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import httpx
from fastapi import HTTPException

from dodo_bridge.config import Settings
from dodo_bridge.connectors.dodo import DodoConnector
from dodo_bridge.models import ToolInvocationRequest, ToolSpec
from dodo_bridge.pizzerias import load_pizzerias
from dodo_bridge.policy import PolicyEngine
from dodo_bridge.registry import ToolRegistry
from dodo_bridge.sales_cache import SalesSummaryCache


@dataclass(frozen=True)
class DodoDataFunction:
    name: str
    tool_name: str
    description: str
    row_keys: tuple[str, ...]
    paginated: bool = True
    meta_keys: tuple[str, ...] = ()


FUNCTIONS: dict[str, DodoDataFunction] = {
    "courier_orders": DodoDataFunction(
        name="courier_orders",
        tool_name="dodo_delivery_courier_orders",
        description="Courier delivery order rows.",
        row_keys=("couriersOrders", "courierOrders", "orders", "items"),
    ),
    "staff_shifts": DodoDataFunction(
        name="staff_shifts",
        tool_name="dodo_staff_shifts",
        description="Staff shifts, normally courier shifts.",
        row_keys=("shifts", "staffShifts", "items"),
    ),
    "staff_vacancies_count": DodoDataFunction(
        name="staff_vacancies_count",
        tool_name="dodo_staff_vacancies_count",
        description="Open vacancy counts by unit.",
        row_keys=("vacancies", "items"),
    ),
    "delivery_statistics": DodoDataFunction(
        name="delivery_statistics",
        tool_name="dodo_delivery_statistics",
        description="Delivery statistics by unit and period.",
        row_keys=("unitsStatistics", "deliveryStatistics", "statistics", "items"),
        paginated=False,
    ),
    "orders_clients_statistics": DodoDataFunction(
        name="orders_clients_statistics",
        tool_name="dodo_orders_clients_statistics",
        description="Client statistics for new clients and churn metrics.",
        row_keys=("clientsStatistics", "clientStatistics", "statistics", "items"),
    ),
    "production_productivity": DodoDataFunction(
        name="production_productivity",
        tool_name="dodo_production_productivity",
        description="Production productivity metrics by unit and period.",
        row_keys=("unitsProductivity", "productivity", "statistics", "items"),
    ),
    "production_orders_handover_time": DodoDataFunction(
        name="production_orders_handover_time",
        tool_name="dodo_production_orders_handover_time",
        description="Production order handover time metrics by unit and period.",
        row_keys=("ordersHandoverTime", "handoverTimes", "statistics", "items"),
    ),
    "accounting_sales": DodoDataFunction(
        name="accounting_sales",
        tool_name="dodo_accounting_sales",
        description="Accounting sales rows.",
        row_keys=("sales", "items"),
    ),
    "accounting_sales_comparison": DodoDataFunction(
        name="accounting_sales_comparison",
        tool_name="dodo_accounting_sales",
        description="Accounting sales comparison between two periods.",
        row_keys=("sales", "items"),
    ),
    "accounting_sales_channels_summary": DodoDataFunction(
        name="accounting_sales_channels_summary",
        tool_name="dodo_accounting_sales",
        description="Accounting sales aggregation by sales channel and order source.",
        row_keys=("sales", "items"),
    ),
    "accounting_sales_discounts_summary": DodoDataFunction(
        name="accounting_sales_discounts_summary",
        tool_name="dodo_accounting_sales",
        description="Accounting sales discount aggregation by heuristic category and action.",
        row_keys=("sales", "items"),
    ),
    "accounting_writeoffs_products": DodoDataFunction(
        name="accounting_writeoffs_products",
        tool_name="dodo_accounting_writeoffs_products",
        description="Product write-off rows.",
        row_keys=("writeOffs", "writeoffs", "products", "items"),
    ),
    "accounting_writeoffs_products_summary": DodoDataFunction(
        name="accounting_writeoffs_products_summary",
        tool_name="dodo_accounting_writeoffs_products",
        description="Aggregated product write-off summary by unit.",
        row_keys=("writeOffs", "writeoffs", "products", "items"),
    ),
    "accounting_slice_writeoff_rate": DodoDataFunction(
        name="accounting_slice_writeoff_rate",
        tool_name="dodo_accounting_writeoffs_products",
        description="Slice write-off rate from product sales and write-offs.",
        row_keys=("writeOffs", "writeoffs", "products", "items"),
    ),
    "accounting_slice_daily_dynamics": DodoDataFunction(
        name="accounting_slice_daily_dynamics",
        tool_name="dodo_accounting_writeoffs_products",
        description="Daily slice sales and write-off dynamics from product sales and write-offs.",
        row_keys=("writeOffs", "writeoffs", "products", "items"),
    ),
    "accounting_inventory_stocks": DodoDataFunction(
        name="accounting_inventory_stocks",
        tool_name="dodo_accounting_inventory_stocks",
        description="Inventory stock balance rows.",
        row_keys=("stocks", "inventoryStocks", "items"),
    ),
    "accounting_inventory_stocks_summary": DodoDataFunction(
        name="accounting_inventory_stocks_summary",
        tool_name="dodo_accounting_inventory_stocks",
        description="Compact inventory stock balance summary by unit.",
        row_keys=("stocks", "inventoryStocks", "items"),
    ),
    "accounting_stock_consumptions_by_period": DodoDataFunction(
        name="accounting_stock_consumptions_by_period",
        tool_name="dodo_accounting_stock_consumptions_by_period",
        description="Stock consumption rows by period.",
        row_keys=("consumptions", "stockConsumptions", "items"),
    ),
    "accounting_stock_consumptions_by_period_summary": DodoDataFunction(
        name="accounting_stock_consumptions_by_period_summary",
        tool_name="dodo_accounting_stock_consumptions_by_period",
        description="Compact stock consumption cost summary by unit and item.",
        row_keys=("consumptions", "stockConsumptions", "items"),
    ),
    "units_month_goals": DodoDataFunction(
        name="units_month_goals",
        tool_name="dodo_units_month_goals",
        description="Monthly target values for one unit.",
        row_keys=(),
        paginated=False,
    ),
    "ratings_customer_experience": DodoDataFunction(
        name="ratings_customer_experience",
        tool_name="dodo_controlling_ratings_customer_experience",
        description="Customer experience ratings by unit or country.",
        row_keys=("unitRates", "ratings", "items"),
        meta_keys=("periodFrom", "periodTo", "publishStatus", "publishedAt"),
    ),
    "ratings_customer_experience_summary": DodoDataFunction(
        name="ratings_customer_experience_summary",
        tool_name="dodo_controlling_ratings_customer_experience",
        description="Compact customer experience ratings summary by unit.",
        row_keys=("unitRates", "ratings", "items"),
        meta_keys=("periodFrom", "periodTo", "publishStatus", "publishedAt"),
    ),
    "ratings_standards": DodoDataFunction(
        name="ratings_standards",
        tool_name="dodo_controlling_ratings_standards",
        description="Standards ratings by unit or country.",
        row_keys=("unitRates", "ratings", "items"),
        meta_keys=("periodFrom", "periodTo", "publishStatus", "publishedAt"),
    ),
    "ratings_standards_summary": DodoDataFunction(
        name="ratings_standards_summary",
        tool_name="dodo_controlling_ratings_standards",
        description="Compact standards ratings summary by unit.",
        row_keys=("unitRates", "ratings", "items"),
        meta_keys=("periodFrom", "periodTo", "publishStatus", "publishedAt"),
    ),
}

WRITEOFF_PRODUCT_SUMMARY_FIELDS = [
    "unitId",
    "unitName",
    "writtenOffAtLocal",
    "writtenOffAt",
    "productName",
    "quantity",
    "pricePerPiece",
    "reason",
]

SALES_SUMMARY_DEFAULT_MAX_PAGES_PER_UNIT = 100
SALES_SUMMARY_MAX_PAGES_PER_UNIT = 200
SALES_SUMMARY_DEFAULT_CONCURRENCY = 4
SALES_SUMMARY_MAX_CONCURRENCY = 8
SALES_SUMMARY_CACHE_MODES = {"auto", "refresh", "bypass"}
SALES_SUMMARY_METRIC_KEYS = (
    "orders",
    "products",
    "salesWithDiscount",
    "salesWithoutDiscount",
    "discount",
    "averageCheck",
)


class DodoDataService:
    def __init__(
        self,
        *,
        settings: Settings,
        registry: ToolRegistry,
        policy: PolicyEngine,
    ):
        self.settings = settings
        self.registry = registry
        self.policy = policy
        self.connector = DodoConnector(settings)
        self.sales_cache = SalesSummaryCache(settings.audit_db_path)

    def list_functions(self) -> list[dict[str, Any]]:
        result = []
        for function in FUNCTIONS.values():
            tool = self.registry.get(function.tool_name)
            result.append(
                {
                    "name": function.name,
                    "description": function.description,
                    "tool_name": function.tool_name,
                    "enabled": bool(tool and tool.enabled),
                    "allowed_by_policy": bool(
                        tool
                        and ("*" in self.policy.config.allowed_tools or tool.name in self.policy.config.allowed_tools)
                    ),
                    "paginated": function.paginated,
                }
            )
        return result

    async def fetch(
        self,
        *,
        function_name: str,
        parameters: dict[str, Any],
        dry_run: bool,
        fields: list[str] | None = None,
        take: int | None = None,
        max_pages: int | None = None,
    ) -> dict[str, Any]:
        function = FUNCTIONS[function_name]
        tool = self._allowed_tool(function, parameters, dry_run)
        take_value = self._bounded_take(take)
        max_pages_value = self._bounded_max_pages(max_pages)

        base_params = dict(parameters)
        if function.paginated and "take" in tool.allowed_query_params:
            base_params["take"] = take_value
            base_params.setdefault("skip", 0)

        if dry_run:
            request = self.connector.build_request(tool, base_params)
            return {
                "function": function.name,
                "tool_name": tool.name,
                "dry_run": True,
                "request": request,
                "pagination": {
                    "enabled": function.paginated,
                    "take": take_value if function.paginated else None,
                    "max_pages": max_pages_value if function.paginated else None,
                },
            }

        if not function.paginated:
            payload = await self._invoke_tool(tool, base_params)
            if _is_connector_dry_run(payload):
                return {
                    "function": function.name,
                    "tool_name": tool.name,
                    "dry_run": True,
                    "request": payload.get("request"),
                    "external_not_configured": payload.get("external_not_configured"),
                }
            rows_key, rows = extract_rows(payload, function.row_keys)
            if rows is None:
                return {
                    "function": function.name,
                    "tool_name": tool.name,
                    "row_count": None,
                    "rows_key": None,
                    "response": payload,
                }
            projected = project_rows(rows, fields)
            meta = extract_meta(payload, function.meta_keys)
            return {
                "function": function.name,
                "tool_name": tool.name,
                "meta": meta or None,
                "rows_key": rows_key,
                "row_count": len(projected),
                "rows": projected,
            }

        all_rows: list[Any] = []
        rows_key: str | None = None
        pages_fetched = 0
        truncated = False
        meta: dict[str, Any] = {}
        for page in range(max_pages_value):
            page_params = dict(base_params)
            page_params["skip"] = page * take_value
            page_params["take"] = take_value
            payload = await self._invoke_tool(tool, page_params)
            if _is_connector_dry_run(payload):
                return {
                    "function": function.name,
                    "tool_name": tool.name,
                    "dry_run": True,
                    "request": payload.get("request"),
                    "external_not_configured": payload.get("external_not_configured"),
                }

            current_key, rows = extract_rows(payload, function.row_keys)
            if rows is None:
                return {
                    "function": function.name,
                    "tool_name": tool.name,
                    "meta": extract_meta(payload, function.meta_keys) or None,
                    "row_count": None,
                    "rows_key": None,
                    "pages_fetched": pages_fetched,
                    "response": payload,
                }

            rows_key = rows_key or current_key
            if not meta:
                meta = extract_meta(payload, function.meta_keys)
            pages_fetched += 1
            all_rows.extend(rows)
            if len(all_rows) >= self.settings.dodo_data_max_rows:
                all_rows = all_rows[: self.settings.dodo_data_max_rows]
                truncated = True
                break
            if len(rows) < take_value:
                break

        if pages_fetched >= max_pages_value:
            truncated = True

        projected = project_rows(all_rows, fields)
        return {
            "function": function.name,
            "tool_name": tool.name,
            "meta": meta or None,
            "rows_key": rows_key,
            "row_count": len(projected),
            "pages_fetched": pages_fetched,
            "truncated": truncated,
            "next_skip": pages_fetched * take_value if truncated else None,
            "rows": projected,
        }

    async def fetch_writeoff_products_summary(
        self,
        *,
        parameters: dict[str, Any],
        dry_run: bool,
        product_name_prefix: str,
        include_products: bool,
        include_reasons: bool,
        take: int | None = None,
        max_pages: int | None = None,
    ) -> dict[str, Any]:
        result = await self.fetch(
            function_name="accounting_writeoffs_products_summary",
            parameters=parameters,
            dry_run=dry_run,
            fields=WRITEOFF_PRODUCT_SUMMARY_FIELDS,
            take=take,
            max_pages=max_pages,
        )
        result["filter"] = {
            "productNamePrefix": product_name_prefix,
            "includeProducts": include_products,
            "includeReasons": include_reasons,
        }
        if result.get("dry_run"):
            return result

        rows = result.get("rows")
        if not isinstance(rows, list):
            return result

        summary = summarize_writeoff_product_rows(
            rows,
            product_name_prefix=product_name_prefix,
            include_products=include_products,
            include_reasons=include_reasons,
        )
        return {
            "function": "accounting_writeoffs_products_summary",
            "tool_name": result["tool_name"],
            "filter": result["filter"],
            "source": {
                "rows_key": result.get("rows_key"),
                "row_count": result.get("row_count"),
                "pages_fetched": result.get("pages_fetched"),
                "truncated": result.get("truncated"),
                "next_skip": result.get("next_skip"),
            },
            **summary,
        }

    async def fetch_sales_summary(
        self,
        *,
        parameters: dict[str, Any],
        dry_run: bool,
        take: int | None = None,
        max_pages_per_unit: int | None = None,
        concurrency: int | None = None,
        cache_mode: str = "auto",
    ) -> dict[str, Any]:
        if cache_mode not in SALES_SUMMARY_CACHE_MODES:
            raise HTTPException(
                status_code=422,
                detail=f"cacheMode must be one of: {', '.join(sorted(SALES_SUMMARY_CACHE_MODES))}",
            )
        function = FUNCTIONS["accounting_sales"]
        tool = self._allowed_tool(function, parameters, dry_run)
        unit_ids = normalize_units(str(parameters["units"])).split(",")
        take_value = self._bounded_take(take or self.settings.dodo_data_max_take)
        max_pages_value = _bounded_sales_summary_max_pages(max_pages_per_unit)
        concurrency_value = _bounded_sales_summary_concurrency(concurrency, len(unit_ids))
        base_params = dict(parameters)
        days = _sales_summary_days(parameters)

        if dry_run:
            requests_preview = []
            for unit_id in unit_ids[:10]:
                request_params = {
                    **base_params,
                    "units": unit_id,
                    "skip": 0,
                    "take": take_value,
                }
                requests_preview.append(
                    {
                        "unitId": unit_id,
                        "request": self.connector.build_request(tool, request_params),
                    }
                )
            return {
                "function": "accounting_sales_summary",
                "tool_name": tool.name,
                "dry_run": True,
                "request_count": len(unit_ids),
                "requests_preview": requests_preview,
                "pagination": {
                    "take": take_value,
                    "max_pages_per_unit": max_pages_value,
                    "concurrency": concurrency_value,
                    "cache_mode": cache_mode,
                },
                "notes": [
                    "Live mode aggregates raw accounting sales rows by unit.",
                    "salesWithDiscount is sum of products[].priceWithDiscount.",
                ],
            }

        unit_names = self._unit_names_by_id()
        cached = {}
        daily_rows_requested = len(unit_ids) * len(days)
        daily_rows_hit = 0
        if cache_mode == "auto":
            cached = self.sales_cache.fetch_daily(unit_ids=unit_ids, days=days)
            daily_rows_hit = len(cached)

        unit_results: list[dict[str, Any]] = []
        live_unit_ids: list[str] = []
        for unit_id in unit_ids:
            cached_rows = [cached.get((unit_id, day)) for day in days]
            if cache_mode == "auto" and days and all(row is not None for row in cached_rows):
                unit_results.append(
                    _sales_summary_bucket_from_cached_rows(
                        unit_id=unit_id,
                        unit_name=unit_names.get(unit_id),
                        rows=[row for row in cached_rows if row is not None],
                    )
                )
            else:
                live_unit_ids.append(unit_id)

        semaphore = asyncio.Semaphore(concurrency_value)
        live_results = await asyncio.gather(
            *(
                self._fetch_sales_summary_for_unit(
                    tool=tool,
                    base_params=base_params,
                    unit_id=unit_id,
                    unit_name=unit_names.get(unit_id),
                    take=take_value,
                    max_pages=max_pages_value,
                    days=days,
                    semaphore=semaphore,
                )
                for unit_id in live_unit_ids
            )
        )
        unit_results.extend(live_results)

        cache_writes = 0
        if cache_mode in {"auto", "refresh"}:
            daily_rows_to_cache = []
            for unit in live_results:
                if not unit["source"]["truncated"]:
                    daily_rows_to_cache.extend(unit.get("_daily", []))
            cache_writes = self.sales_cache.upsert_daily(daily_rows_to_cache)

        unit_results.sort(key=lambda item: item.get("unitName") or item["unitId"])

        total = _new_sales_summary_bucket()
        pages_fetched = 0
        truncated_units = []
        for unit in unit_results:
            _add_sales_summary_bucket(total, unit)
            pages_fetched += int(unit["source"]["pagesFetched"])
            if unit["source"]["truncated"]:
                truncated_units.append({"unitId": unit["unitId"], "unitName": unit.get("unitName")})
            unit.pop("_daily", None)

        return {
            "function": "accounting_sales_summary",
            "tool_name": tool.name,
            "period": {
                "from": str(parameters.get("from")),
                "to": str(parameters.get("to")),
                "to_is_exclusive": True,
            },
            "complete": not truncated_units,
            "total": _finalize_sales_summary_bucket(total),
            "units": [_finalize_sales_summary_bucket(unit) for unit in unit_results],
            "source": {
                "rawRowsAggregated": int(total["orders"]),
                "pagesFetched": pages_fetched,
                "take": take_value,
                "maxPagesPerUnit": max_pages_value,
                "concurrency": concurrency_value,
                "truncatedUnits": truncated_units,
                "cacheMode": cache_mode,
                "dailyRowsRequested": daily_rows_requested,
                "dailyRowsHit": daily_rows_hit,
                "dailyRowsMissed": daily_rows_requested - daily_rows_hit,
                "cacheWrites": cache_writes,
                "unitsFetchedLive": live_unit_ids,
            },
            "notes": [
                "salesWithDiscount is sum of products[].priceWithDiscount.",
                "salesWithoutDiscount is sum of products[].price.",
                "discount is salesWithoutDiscount - salesWithDiscount.",
                "Cancelled sales are not included; they are exposed by a separate Dodo API endpoint.",
            ],
        }

    async def fetch_sales_comparison(
        self,
        *,
        current_parameters: dict[str, Any],
        baseline_parameters: dict[str, Any],
        dry_run: bool,
        take: int | None = None,
        max_pages_per_unit: int | None = None,
        concurrency: int | None = None,
        cache_mode: str = "auto",
    ) -> dict[str, Any]:
        current = await self.fetch_sales_summary(
            parameters=current_parameters,
            dry_run=dry_run,
            take=take,
            max_pages_per_unit=max_pages_per_unit,
            concurrency=concurrency,
            cache_mode=cache_mode,
        )
        baseline = await self.fetch_sales_summary(
            parameters=baseline_parameters,
            dry_run=dry_run,
            take=take,
            max_pages_per_unit=max_pages_per_unit,
            concurrency=concurrency,
            cache_mode=cache_mode,
        )
        if dry_run:
            return {
                "function": "accounting_sales_comparison",
                "tool_name": current.get("tool_name") or baseline.get("tool_name"),
                "dry_run": True,
                "current": current,
                "baseline": baseline,
                "notes": [
                    "Dry-run only plans read-only Dodo IS accounting sales requests.",
                    "Live mode compares two compact sales summaries inside the Bridge.",
                ],
            }

        current_total = _sales_summary_metrics(current.get("total"))
        baseline_total = _sales_summary_metrics(baseline.get("total"))
        total_comparison = _compare_sales_metrics(current_total, baseline_total)

        return {
            "function": "accounting_sales_comparison",
            "tool_name": current.get("tool_name") or baseline.get("tool_name"),
            "complete": bool(current.get("complete")) and bool(baseline.get("complete")),
            "current": {
                "period": current.get("period"),
                "total": current_total,
            },
            "baseline": {
                "period": baseline.get("period"),
                "total": baseline_total,
            },
            "change": total_comparison["change"],
            "changePercent": total_comparison["changePercent"],
            "units": _compare_sales_units(
                current.get("units") if isinstance(current.get("units"), list) else [],
                baseline.get("units") if isinstance(baseline.get("units"), list) else [],
            ),
            "source": {
                "current": current.get("source"),
                "baseline": baseline.get("source"),
            },
            "notes": [
                "change = current - baseline.",
                "changePercent is null when the baseline metric is zero.",
                "averageCheck is salesWithDiscount / orders.",
            ],
        }

    async def fetch_sales_channels_summary(
        self,
        *,
        parameters: dict[str, Any],
        dry_run: bool,
        take: int | None = None,
        max_pages_per_unit: int | None = None,
        concurrency: int | None = None,
    ) -> dict[str, Any]:
        function = FUNCTIONS["accounting_sales_channels_summary"]
        tool = self._allowed_tool(function, parameters, dry_run)
        unit_ids = normalize_units(str(parameters["units"])).split(",")
        take_value = self._bounded_take(take or self.settings.dodo_data_max_take)
        max_pages_value = _bounded_sales_summary_max_pages(max_pages_per_unit)
        concurrency_value = _bounded_sales_summary_concurrency(concurrency, len(unit_ids))
        base_params = dict(parameters)
        days = _sales_summary_days(parameters)

        if dry_run:
            requests_preview = []
            for unit_id in unit_ids[:10]:
                request_params = {
                    **base_params,
                    "units": unit_id,
                    "skip": 0,
                    "take": take_value,
                }
                requests_preview.append(
                    {
                        "unitId": unit_id,
                        "request": self.connector.build_request(tool, request_params),
                    }
                )
            return {
                "function": "accounting_sales_channels_summary",
                "tool_name": tool.name,
                "dry_run": True,
                "request_count": len(unit_ids),
                "requests_preview": requests_preview,
                "pagination": {
                    "take": take_value,
                    "max_pages_per_unit": max_pages_value,
                    "concurrency": concurrency_value,
                },
            }

        unit_names = self._unit_names_by_id()
        semaphore = asyncio.Semaphore(concurrency_value)
        unit_results = await asyncio.gather(
            *(
                self._fetch_sales_channels_summary_for_unit(
                    tool=tool,
                    base_params=base_params,
                    unit_id=unit_id,
                    unit_name=unit_names.get(unit_id),
                    take=take_value,
                    max_pages=max_pages_value,
                    days_count=len(days),
                    semaphore=semaphore,
                )
                for unit_id in unit_ids
            )
        )

        z_scores = _sales_channel_z_scores(unit_results)
        for unit in unit_results:
            unit["zScores"] = z_scores.get(unit["unitId"], {})

        total = _new_sales_channel_bucket()
        pages_fetched = 0
        truncated_units = []
        for unit in unit_results:
            _add_sales_channel_bucket(total, unit["total"])
            pages_fetched += int(unit["source"]["pagesFetched"])
            if unit["source"]["truncated"]:
                truncated_units.append({"unitId": unit["unitId"], "unitName": unit.get("unitName")})

        unit_results.sort(key=lambda item: item.get("unitName") or item["unitId"])
        return {
            "function": "accounting_sales_channels_summary",
            "tool_name": tool.name,
            "period": {
                "from": str(parameters.get("from")),
                "to": str(parameters.get("to")),
                "to_is_exclusive": True,
                "days": len(days),
            },
            "complete": not truncated_units,
            "total": _finalize_sales_channel_bucket(total, len(days)),
            "units": unit_results,
            "source": {
                "rawRowsAggregated": int(total["orders"]),
                "pagesFetched": pages_fetched,
                "take": take_value,
                "maxPagesPerUnit": max_pages_value,
                "concurrency": concurrency_value,
                "truncatedUnits": truncated_units,
            },
            "notes": [
                "salesChannel comes from Dodo accounting sales rows.",
                "orderSource separates Kiosk, MobileApp, Website, CallCenter, and Dine-in when Dodo provides it.",
                "zScores compare each pizzeria's average orders per day against the configured pizzeria set for the same channel.",
            ],
        }

    async def fetch_sales_discounts_summary(
        self,
        *,
        parameters: dict[str, Any],
        dry_run: bool,
        include_actions: bool,
        top_actions_limit: int,
        take: int | None = None,
        max_pages_per_unit: int | None = None,
        concurrency: int | None = None,
    ) -> dict[str, Any]:
        function = FUNCTIONS["accounting_sales_discounts_summary"]
        tool = self._allowed_tool(function, parameters, dry_run)
        unit_ids = normalize_units(str(parameters["units"])).split(",")
        take_value = self._bounded_take(take or self.settings.dodo_data_max_take)
        max_pages_value = _bounded_sales_summary_max_pages(max_pages_per_unit)
        concurrency_value = _bounded_sales_summary_concurrency(concurrency, len(unit_ids))
        action_limit_value = _bounded_discount_action_limit(top_actions_limit)
        base_params = dict(parameters)
        days = _sales_summary_days(parameters)

        if dry_run:
            requests_preview = []
            for unit_id in unit_ids[:10]:
                request_params = {
                    **base_params,
                    "units": unit_id,
                    "skip": 0,
                    "take": take_value,
                }
                requests_preview.append(
                    {
                        "unitId": unit_id,
                        "request": self.connector.build_request(tool, request_params),
                    }
                )
            return {
                "function": "accounting_sales_discounts_summary",
                "tool_name": tool.name,
                "dry_run": True,
                "request_count": len(unit_ids),
                "requests_preview": requests_preview,
                "pagination": {
                    "take": take_value,
                    "max_pages_per_unit": max_pages_value,
                    "concurrency": concurrency_value,
                },
                "options": {
                    "includeActions": include_actions,
                    "topActionsLimit": action_limit_value,
                },
            }

        unit_names = self._unit_names_by_id()
        semaphore = asyncio.Semaphore(concurrency_value)
        unit_results = await asyncio.gather(
            *(
                self._fetch_sales_discounts_summary_for_unit(
                    tool=tool,
                    base_params=base_params,
                    unit_id=unit_id,
                    unit_name=unit_names.get(unit_id),
                    take=take_value,
                    max_pages=max_pages_value,
                    include_actions=include_actions,
                    top_actions_limit=action_limit_value,
                    semaphore=semaphore,
                )
                for unit_id in unit_ids
            )
        )

        total_bucket = _new_sales_discount_bucket()
        pages_fetched = 0
        truncated_units = []
        for unit in unit_results:
            _add_sales_discount_bucket(total_bucket, unit.pop("_bucket"))
            pages_fetched += int(unit["source"]["pagesFetched"])
            if unit["source"]["truncated"]:
                truncated_units.append({"unitId": unit["unitId"], "unitName": unit.get("unitName")})

        unit_results.sort(key=lambda item: item.get("unitName") or item["unitId"])
        return {
            "function": "accounting_sales_discounts_summary",
            "tool_name": tool.name,
            "period": {
                "from": str(parameters.get("from")),
                "to": str(parameters.get("to")),
                "to_is_exclusive": True,
                "days": len(days),
            },
            "complete": not truncated_units,
            "total": _finalize_sales_discount_total(total_bucket),
            "categories": _finalize_discount_categories(
                total_bucket["categories"],
                total_bucket["discountAmount"],
                total_bucket["salesWithoutDiscount"],
                include_actions=include_actions,
                top_actions_limit=action_limit_value,
            ),
            "units": unit_results,
            "source": {
                "rawRowsAggregated": int(total_bucket["orders"]),
                "pagesFetched": pages_fetched,
                "take": take_value,
                "maxPagesPerUnit": max_pages_value,
                "concurrency": concurrency_value,
                "truncatedUnits": truncated_units,
            },
            "options": {
                "includeActions": include_actions,
                "topActionsLimit": action_limit_value,
            },
            "notes": [
                "Discount categories are heuristic labels computed from Dodo action names and promocodes.",
                "Use includeActions=true to inspect source actions behind a category.",
                "For exact Superset discount-tab parity, add an approved Superset discount recipe.",
            ],
        }

    async def fetch_slice_writeoff_rate(
        self,
        *,
        sales_parameters: dict[str, Any],
        writeoff_parameters: dict[str, Any],
        dry_run: bool,
        product_name_prefix: str,
        include_products: bool,
        take: int | None = None,
        max_pages: int | None = None,
    ) -> dict[str, Any]:
        if dry_run:
            writeoff_plan = await self.fetch(
                function_name="accounting_writeoffs_products_summary",
                parameters=writeoff_parameters,
                dry_run=True,
                fields=WRITEOFF_PRODUCT_SUMMARY_FIELDS,
                take=take,
                max_pages=max_pages,
            )
            sales_plan = await self.fetch(
                function_name="accounting_sales",
                parameters=sales_parameters,
                dry_run=True,
                fields=None,
                take=take,
                max_pages=max_pages,
            )
            return {
                "function": "accounting_slice_writeoff_rate",
                "tool_name": "dodo_accounting_writeoffs_products+dodo_accounting_sales",
                "dry_run": True,
                "requests": {
                    "writeoffs": writeoff_plan.get("request"),
                    "sales": sales_plan.get("request"),
                },
                "filter": {
                    "productNamePrefix": product_name_prefix,
                    "includeProducts": include_products,
                },
                "formula": "laidOutQuantity = soldQuantity + writeoffQuantity; writeoffPercent = writeoffQuantity / laidOutQuantity * 100",
            }

        writeoff_result = await self._fetch_rows_for_summary(
            function_name="accounting_writeoffs_products_summary",
            parameters=writeoff_parameters,
            fields=WRITEOFF_PRODUCT_SUMMARY_FIELDS,
            take=take,
            max_pages=max_pages,
        )
        sales_result = await self._fetch_rows_for_summary(
            function_name="accounting_sales",
            parameters=sales_parameters,
            fields=None,
            take=take,
            max_pages=max_pages,
        )
        writeoff_rows = writeoff_result.get("rows")
        sales_rows = sales_result.get("rows")
        if not isinstance(writeoff_rows, list) or not isinstance(sales_rows, list):
            return {
                "function": "accounting_slice_writeoff_rate",
                "tool_name": "dodo_accounting_writeoffs_products+dodo_accounting_sales",
                "filter": {
                    "productNamePrefix": product_name_prefix,
                    "includeProducts": include_products,
                },
                "source": {
                    "writeoffs": _source_meta(writeoff_result),
                    "sales": _source_meta(sales_result),
                },
                "error": "rows_not_available",
            }

        summary = summarize_slice_writeoff_rate(
            writeoff_rows=writeoff_rows,
            sales_rows=sales_rows,
            product_name_prefix=product_name_prefix,
            include_products=include_products,
        )
        return {
            "function": "accounting_slice_writeoff_rate",
            "tool_name": "dodo_accounting_writeoffs_products+dodo_accounting_sales",
            "filter": {
                "productNamePrefix": product_name_prefix,
                "includeProducts": include_products,
            },
            "formula": "laidOutQuantity = soldQuantity + writeoffQuantity; writeoffPercent = writeoffQuantity / laidOutQuantity * 100",
            "source": {
                "writeoffs": _source_meta(writeoff_result),
                "sales": _source_meta(sales_result),
            },
            **summary,
        }

    async def fetch_slice_daily_dynamics(
        self,
        *,
        sales_parameters: dict[str, Any],
        writeoff_parameters: dict[str, Any],
        dry_run: bool,
        product_name_prefix: str,
        include_products: bool,
        take: int | None = None,
        max_pages: int | None = None,
    ) -> dict[str, Any]:
        unit_ids = normalize_units(str(sales_parameters["units"])).split(",")
        days = _sales_summary_days(sales_parameters)
        if dry_run:
            first_day = days[0] if days else str(sales_parameters.get("from"))
            next_day = (date.fromisoformat(first_day) + timedelta(days=1)).isoformat()
            first_sales_params = {**sales_parameters, "from": first_day, "to": next_day}
            first_writeoff_params = {**writeoff_parameters, "from": first_day, "to": next_day}
            writeoff_plan = await self.fetch(
                function_name="accounting_writeoffs_products_summary",
                parameters=first_writeoff_params,
                dry_run=True,
                fields=WRITEOFF_PRODUCT_SUMMARY_FIELDS,
                take=take,
                max_pages=max_pages,
            )
            sales_plan = await self.fetch(
                function_name="accounting_sales",
                parameters=first_sales_params,
                dry_run=True,
                fields=None,
                take=take,
                max_pages=max_pages,
            )
            return {
                "function": "accounting_slice_daily_dynamics",
                "tool_name": "dodo_accounting_writeoffs_products+dodo_accounting_sales",
                "dry_run": True,
                "request_count": len(unit_ids) * len(days) * 2,
                "requests_preview": {
                    "first_day": first_day,
                    "writeoffs": writeoff_plan.get("request"),
                    "sales": sales_plan.get("request"),
                },
                "filter": {
                    "productNamePrefix": product_name_prefix,
                    "includeProducts": include_products,
                },
                "formula": "laidOutQuantity = soldQuantity + writeoffQuantity; writeoffPercent = writeoffQuantity / laidOutQuantity * 100",
            }

        unit_names = self._unit_names_by_id()
        state = _new_slice_daily_dynamics_state(unit_ids=unit_ids, unit_names=unit_names, days=days)
        source = {
            "writeoffs": _new_slice_dynamics_source(),
            "sales": _new_slice_dynamics_source(),
        }

        for unit_id in unit_ids:
            unit_name = unit_names.get(unit_id)
            for day in days:
                next_day = (date.fromisoformat(day) + timedelta(days=1)).isoformat()
                daily_sales_params = {**sales_parameters, "units": unit_id, "from": day, "to": next_day}
                daily_writeoff_params = {**writeoff_parameters, "units": unit_id, "from": day, "to": next_day}
                writeoff_result = await self._fetch_rows_for_summary(
                    function_name="accounting_writeoffs_products_summary",
                    parameters=daily_writeoff_params,
                    fields=WRITEOFF_PRODUCT_SUMMARY_FIELDS,
                    take=take,
                    max_pages=max_pages,
                )
                sales_result = await self._fetch_rows_for_summary(
                    function_name="accounting_sales",
                    parameters=daily_sales_params,
                    fields=None,
                    take=take,
                    max_pages=max_pages,
                )
                writeoff_rows = writeoff_result.get("rows") if isinstance(writeoff_result.get("rows"), list) else []
                sales_rows = sales_result.get("rows") if isinstance(sales_result.get("rows"), list) else []
                _add_slice_dynamics_source(source["writeoffs"], writeoff_result, unit_id, unit_name, day)
                _add_slice_dynamics_source(source["sales"], sales_result, unit_id, unit_name, day)
                _add_slice_dynamics_writeoff_rows(
                    state,
                    writeoff_rows,
                    unit_id=unit_id,
                    unit_name=unit_name,
                    fallback_day=day,
                    product_name_prefix=product_name_prefix,
                    include_products=include_products,
                )
                _add_slice_dynamics_sales_rows(
                    state,
                    sales_rows,
                    unit_id=unit_id,
                    unit_name=unit_name,
                    fallback_day=day,
                    product_name_prefix=product_name_prefix,
                    include_products=include_products,
                )

        summary = _finalize_slice_daily_dynamics_state(state, include_products=include_products)
        return {
            "function": "accounting_slice_daily_dynamics",
            "tool_name": "dodo_accounting_writeoffs_products+dodo_accounting_sales",
            "filter": {
                "productNamePrefix": product_name_prefix,
                "includeProducts": include_products,
            },
            "formula": "laidOutQuantity = soldQuantity + writeoffQuantity; writeoffPercent = writeoffQuantity / laidOutQuantity * 100",
            "source": source,
            **summary,
        }

    async def fetch_ratings_summary(
        self,
        *,
        function_name: str,
        parameters: dict[str, Any],
        dry_run: bool,
        low_rate_threshold: float,
        top_limit: int,
        take: int | None,
        max_pages: int | None,
    ) -> dict[str, Any]:
        function = FUNCTIONS[function_name]
        tool = self._allowed_tool(function, parameters, dry_run)
        take_value = self._bounded_take(take)
        max_pages_value = self._bounded_max_pages(max_pages)
        base_params = dict(parameters)
        if function.paginated and "take" in tool.allowed_query_params:
            base_params["take"] = take_value
            base_params.setdefault("skip", 0)

        if dry_run:
            request = self.connector.build_request(tool, base_params)
            return {
                "function": function.name,
                "tool_name": tool.name,
                "dry_run": True,
                "request": request,
                "threshold": {"lowRate": low_rate_threshold},
                "topLimit": top_limit,
                "pagination": {
                    "enabled": function.paginated,
                    "take": take_value if function.paginated else None,
                    "max_pages": max_pages_value if function.paginated else None,
                },
            }

        rows_result = await self._fetch_rows_for_summary(
            function_name=function_name,
            parameters=parameters,
            fields=None,
            take=take,
            max_pages=max_pages,
        )
        rows = rows_result.get("rows")
        if rows is None:
            return {
                "function": function.name,
                "tool_name": rows_result.get("tool_name", tool.name),
                "meta": rows_result.get("meta"),
                "source": _source_meta(rows_result),
                "response": rows_result.get("response"),
            }

        summary = summarize_rating_rows(
            rows,
            low_rate_threshold=low_rate_threshold,
            top_limit=top_limit,
        )
        return {
            "function": function.name,
            "tool_name": rows_result.get("tool_name", tool.name),
            "meta": rows_result.get("meta"),
            "threshold": {"lowRate": low_rate_threshold},
            "topLimit": top_limit,
            "source": _source_meta(rows_result),
            **summary,
        }

    async def fetch_inventory_stocks_summary(
        self,
        *,
        parameters: dict[str, Any],
        dry_run: bool,
        low_stock_days_threshold: float,
        high_stock_days_threshold: float,
        top_limit: int,
        take: int | None,
        max_pages: int | None,
    ) -> dict[str, Any]:
        function = FUNCTIONS["accounting_inventory_stocks_summary"]
        tool = self._allowed_tool(function, parameters, dry_run)
        take_value = self._bounded_take(take)
        max_pages_value = self._bounded_max_pages(max_pages)
        base_params = dict(parameters)
        if function.paginated and "take" in tool.allowed_query_params:
            base_params["take"] = take_value
            base_params.setdefault("skip", 0)

        if dry_run:
            request = self.connector.build_request(tool, base_params)
            return {
                "function": function.name,
                "tool_name": tool.name,
                "dry_run": True,
                "request": request,
                "thresholds": {
                    "lowStockDays": low_stock_days_threshold,
                    "highStockDays": high_stock_days_threshold,
                },
                "topLimit": top_limit,
                "pagination": {
                    "enabled": function.paginated,
                    "take": take_value,
                    "max_pages": max_pages_value,
                },
            }

        rows_result = await self._fetch_rows_for_summary(
            function_name=function.name,
            parameters=parameters,
            fields=None,
            take=take,
            max_pages=max_pages,
        )
        rows = rows_result.get("rows")
        if rows is None:
            return {
                "function": function.name,
                "tool_name": rows_result.get("tool_name", tool.name),
                "source": _source_meta(rows_result),
                "response": rows_result.get("response"),
            }

        summary = summarize_inventory_stock_rows(
            rows,
            low_stock_days_threshold=low_stock_days_threshold,
            high_stock_days_threshold=high_stock_days_threshold,
            top_limit=top_limit,
            unit_names_by_id=_configured_unit_names_by_id(self.settings),
        )
        return {
            "function": function.name,
            "tool_name": rows_result.get("tool_name", tool.name),
            "thresholds": {
                "lowStockDays": low_stock_days_threshold,
                "highStockDays": high_stock_days_threshold,
            },
            "topLimit": top_limit,
            "source": _source_meta(rows_result),
            **summary,
        }

    async def fetch_stock_consumptions_summary(
        self,
        *,
        parameters: dict[str, Any],
        dry_run: bool,
        top_limit: int,
        take: int | None,
        max_pages: int | None,
    ) -> dict[str, Any]:
        function = FUNCTIONS["accounting_stock_consumptions_by_period_summary"]
        tool = self._allowed_tool(function, parameters, dry_run)
        take_value = self._bounded_take(take)
        max_pages_value = self._bounded_max_pages(max_pages)
        base_params = dict(parameters)
        if function.paginated and "take" in tool.allowed_query_params:
            base_params["take"] = take_value
            base_params.setdefault("skip", 0)

        if dry_run:
            request = self.connector.build_request(tool, base_params)
            return {
                "function": function.name,
                "tool_name": tool.name,
                "dry_run": True,
                "request": request,
                "topLimit": top_limit,
                "pagination": {
                    "enabled": function.paginated,
                    "take": take_value,
                    "max_pages": max_pages_value,
                },
            }

        rows_result = await self._fetch_rows_for_summary(
            function_name=function.name,
            parameters=parameters,
            fields=None,
            take=take,
            max_pages=max_pages,
        )
        rows = rows_result.get("rows")
        if rows is None:
            return {
                "function": function.name,
                "tool_name": rows_result.get("tool_name", tool.name),
                "source": _source_meta(rows_result),
                "response": rows_result.get("response"),
            }

        summary = summarize_stock_consumption_rows(
            rows,
            top_limit=top_limit,
            unit_names_by_id=_configured_unit_names_by_id(self.settings),
        )
        return {
            "function": function.name,
            "tool_name": rows_result.get("tool_name", tool.name),
            "topLimit": top_limit,
            "source": _source_meta(rows_result),
            **summary,
        }

    async def _fetch_rows_for_summary(
        self,
        *,
        function_name: str,
        parameters: dict[str, Any],
        fields: list[str] | None,
        take: int | None,
        max_pages: int | None,
    ) -> dict[str, Any]:
        function = FUNCTIONS[function_name]
        tool = self._allowed_tool(function, parameters, dry_run=False)
        take_value = self._bounded_take(take)
        max_pages_value = self._bounded_max_pages(max_pages)
        base_params = dict(parameters)
        if function.paginated and "take" in tool.allowed_query_params:
            base_params["take"] = take_value
            base_params.setdefault("skip", 0)

        all_rows: list[Any] = []
        rows_key: str | None = None
        pages_fetched = 0
        truncated = False
        reached_end = False
        meta: dict[str, Any] = {}
        for page in range(max_pages_value):
            page_params = dict(base_params)
            page_params["skip"] = page * take_value
            page_params["take"] = take_value
            payload = await self._invoke_tool(tool, page_params)
            current_key, rows = extract_rows(payload, function.row_keys)
            if rows is None:
                return {
                    "function": function.name,
                    "tool_name": tool.name,
                    "meta": extract_meta(payload, function.meta_keys) or None,
                    "row_count": None,
                    "rows_key": None,
                    "pages_fetched": pages_fetched,
                    "rows": None,
                    "response": payload,
                }

            rows_key = rows_key or current_key
            if not meta:
                meta = extract_meta(payload, function.meta_keys)
            pages_fetched += 1
            all_rows.extend(project_rows(rows, fields))
            if len(rows) < take_value:
                reached_end = True
                break

        if pages_fetched >= max_pages_value and not reached_end:
            truncated = True

        return {
            "function": function.name,
            "tool_name": tool.name,
            "meta": meta or None,
            "rows_key": rows_key,
            "row_count": len(all_rows),
            "pages_fetched": pages_fetched,
            "truncated": truncated,
            "next_skip": pages_fetched * take_value if truncated else None,
            "rows": all_rows,
        }

    def _allowed_tool(
        self,
        function: DodoDataFunction,
        parameters: dict[str, Any],
        dry_run: bool,
    ) -> ToolSpec:
        tool = self.registry.get(function.tool_name)
        request = ToolInvocationRequest(
            parameters=parameters,
            intent=f"dodo_data:{function.name}",
            dry_run=dry_run,
        )
        decision = self.policy.evaluate(
            tool,
            request,
            len(json.dumps(parameters, ensure_ascii=False, default=str)),
        )
        if decision.outcome != "allow":
            raise HTTPException(
                status_code=403,
                detail={
                    "decision": decision.outcome,
                    "reason": decision.reason,
                    "tool_name": function.tool_name,
                },
            )
        if tool is None:
            raise HTTPException(status_code=404, detail=f"Tool not found: {function.tool_name}")
        return tool

    def _bounded_take(self, value: int | None) -> int:
        take = value or self.settings.dodo_data_default_take
        return max(1, min(take, self.settings.dodo_data_max_take))

    def _bounded_max_pages(self, value: int | None) -> int:
        pages = value or self.settings.dodo_data_default_max_pages
        return max(1, min(pages, self.settings.dodo_data_max_pages))

    async def _invoke_tool(self, tool: ToolSpec, parameters: dict[str, Any]) -> Any:
        try:
            return await self.connector.invoke(tool, parameters, dry_run=False)
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=502,
                detail=external_http_error_detail(exc, tool.name),
            ) from exc
        except httpx.TimeoutException as exc:
            raise HTTPException(
                status_code=504,
                detail=external_request_error_detail(
                    exc,
                    tool.name,
                    error="external_timeout",
                    hint=(
                        "Dodo API did not respond before the bridge timeout. "
                        "Split the request by unit or period, or use a compact summary endpoint."
                    ),
                ),
            ) from exc
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=502,
                detail=external_request_error_detail(exc, tool.name, error="external_request_error"),
            ) from exc

    async def _fetch_sales_summary_for_unit(
        self,
        *,
        tool: ToolSpec,
        base_params: dict[str, Any],
        unit_id: str,
        unit_name: str | None,
        take: int,
        max_pages: int,
        days: list[str],
        semaphore: asyncio.Semaphore,
    ) -> dict[str, Any]:
        async with semaphore:
            bucket = _new_sales_summary_bucket(unit_id=unit_id, unit_name=unit_name)
            daily_buckets: dict[str, dict[str, Any]] = {}
            rows_key: str | None = None
            pages_fetched = 0
            truncated = False
            for page in range(max_pages):
                page_params = {
                    **base_params,
                    "units": unit_id,
                    "skip": page * take,
                    "take": take,
                }
                payload = await self._invoke_tool(tool, page_params)
                current_key, rows = extract_rows(payload, FUNCTIONS["accounting_sales"].row_keys)
                if rows is None:
                    raise HTTPException(
                        status_code=502,
                        detail={
                            "error": "unexpected_external_response",
                            "tool_name": tool.name,
                            "unitId": unit_id,
                        },
                    )
                rows_key = rows_key or current_key
                pages_fetched += 1
                _add_sales_rows_to_bucket(bucket, rows, daily_buckets=daily_buckets)
                if len(rows) < take:
                    break
            else:
                truncated = True

            bucket["source"] = {
                "rowsKey": rows_key,
                "pagesFetched": pages_fetched,
                "truncated": truncated,
                "nextSkip": pages_fetched * take if truncated else None,
            }
            for day in days:
                daily_buckets.setdefault(
                    day,
                    _new_sales_summary_bucket(unit_id=unit_id, unit_name=bucket.get("unitName") or unit_name),
                )
            bucket["_daily"] = [
                {"day": day, **_finalize_sales_summary_bucket(daily_bucket)}
                for day, daily_bucket in sorted(daily_buckets.items())
            ]
            return bucket

    async def _fetch_sales_channels_summary_for_unit(
        self,
        *,
        tool: ToolSpec,
        base_params: dict[str, Any],
        unit_id: str,
        unit_name: str | None,
        take: int,
        max_pages: int,
        days_count: int,
        semaphore: asyncio.Semaphore,
    ) -> dict[str, Any]:
        async with semaphore:
            total = _new_sales_channel_bucket()
            sales_channels: dict[str, dict[str, Any]] = {}
            order_sources: dict[str, dict[str, Any]] = {}
            rows_key: str | None = None
            pages_fetched = 0
            truncated = False
            for page in range(max_pages):
                page_params = {
                    **base_params,
                    "units": unit_id,
                    "skip": page * take,
                    "take": take,
                }
                payload = await self._invoke_tool(tool, page_params)
                current_key, rows = extract_rows(payload, FUNCTIONS["accounting_sales"].row_keys)
                if rows is None:
                    raise HTTPException(
                        status_code=502,
                        detail={
                            "error": "unexpected_external_response",
                            "tool_name": tool.name,
                            "unitId": unit_id,
                        },
                    )
                rows_key = rows_key or current_key
                pages_fetched += 1
                _add_sales_channel_rows(total, sales_channels, order_sources, rows)
                if len(rows) < take:
                    break
            else:
                truncated = True

            name = str(total.get("unitName") or unit_name or "")
            return {
                "unitId": unit_id,
                "unitName": name or None,
                "total": _finalize_sales_channel_bucket(total, days_count),
                "salesChannels": _finalize_named_sales_buckets(sales_channels, days_count, "salesChannel"),
                "orderSources": _finalize_named_sales_buckets(order_sources, days_count, "orderSource"),
                "kioskShare": _kiosk_share(order_sources, sales_channels),
                "source": {
                    "rowsKey": rows_key,
                    "pagesFetched": pages_fetched,
                    "truncated": truncated,
                    "nextSkip": pages_fetched * take if truncated else None,
                },
            }

    async def _fetch_sales_discounts_summary_for_unit(
        self,
        *,
        tool: ToolSpec,
        base_params: dict[str, Any],
        unit_id: str,
        unit_name: str | None,
        take: int,
        max_pages: int,
        include_actions: bool,
        top_actions_limit: int,
        semaphore: asyncio.Semaphore,
    ) -> dict[str, Any]:
        async with semaphore:
            bucket = _new_sales_discount_bucket()
            rows_key: str | None = None
            pages_fetched = 0
            truncated = False
            for page in range(max_pages):
                page_params = {
                    **base_params,
                    "units": unit_id,
                    "skip": page * take,
                    "take": take,
                }
                payload = await self._invoke_tool(tool, page_params)
                current_key, rows = extract_rows(payload, FUNCTIONS["accounting_sales"].row_keys)
                if rows is None:
                    raise HTTPException(
                        status_code=502,
                        detail={
                            "error": "unexpected_external_response",
                            "tool_name": tool.name,
                            "unitId": unit_id,
                        },
                    )
                rows_key = rows_key or current_key
                pages_fetched += 1
                _add_sales_discount_rows(bucket, rows)
                if len(rows) < take:
                    break
            else:
                truncated = True

            name = str(bucket.get("unitName") or unit_name or "")
            return {
                "unitId": unit_id,
                "unitName": name or None,
                "total": _finalize_sales_discount_total(bucket),
                "categories": _finalize_discount_categories(
                    bucket["categories"],
                    bucket["discountAmount"],
                    bucket["salesWithoutDiscount"],
                    include_actions=include_actions,
                    top_actions_limit=top_actions_limit,
                ),
                "_bucket": bucket,
                "source": {
                    "rowsKey": rows_key,
                    "pagesFetched": pages_fetched,
                    "truncated": truncated,
                    "nextSkip": pages_fetched * take if truncated else None,
                },
            }

    def _unit_names_by_id(self) -> dict[str, str]:
        pizzerias = load_pizzerias(self.settings.dodo_pizzerias_path).get("pizzerias", [])
        return {
            str(item.get("unit_id")): str(item.get("name"))
            for item in pizzerias
            if item.get("unit_id") and item.get("name")
        }


def normalize_units(units: str) -> str:
    values = [item.strip() for item in units.replace(";", ",").split(",") if item.strip()]
    if not values:
        raise HTTPException(status_code=422, detail="At least one unit id is required")
    return ",".join(values)


def validate_period(from_date: date, to_date: date, settings: Settings) -> None:
    if to_date < from_date:
        raise HTTPException(status_code=422, detail="'to' must be greater than or equal to 'from'")
    days = (to_date - from_date).days + 1
    if days > settings.dodo_data_max_period_days:
        raise HTTPException(
            status_code=422,
            detail=f"Period is too large: {days} days, max {settings.dodo_data_max_period_days}",
        )


def parse_fields(fields: str | None) -> list[str] | None:
    if not fields:
        return None
    parsed = [item.strip() for item in fields.split(",") if item.strip()]
    return parsed or None


def extract_rows(payload: Any, row_keys: tuple[str, ...]) -> tuple[str | None, list[Any] | None]:
    if isinstance(payload, list):
        return "root", payload
    if not isinstance(payload, dict):
        return None, None

    for key in row_keys:
        value = payload.get(key)
        if isinstance(value, list):
            return key, value

    for key, value in payload.items():
        if isinstance(value, list):
            return key, value

    return None, None


def project_rows(rows: list[Any], fields: list[str] | None) -> list[Any]:
    if not fields:
        return rows
    projected = []
    for row in rows:
        if not isinstance(row, dict):
            projected.append(row)
            continue
        projected.append({field: row.get(field) for field in fields if field in row})
    return projected


RATING_VALUE_KEYS = (
    "rate",
    "avgRate",
    "averageRate",
    "rating",
    "score",
    "value",
    "rateValue",
    "ratingValue",
    "totalRate",
    "overallRate",
    "result",
)
RATING_UNIT_ID_KEYS = ("unitId", "unitUUId", "unitUuid", "unitUUID", "id")
RATING_UNIT_NAME_KEYS = ("unitName", "name", "pizzeriaName")


INVENTORY_STOCK_NAME_KEYS = ("name", "stockItemName", "productName", "ingredientName", "id")
INVENTORY_UNIT_ID_KEYS = ("unitId", "unitUUId", "unitUuid", "unitUUID")
INVENTORY_UNIT_NAME_KEYS = ("unitName", "pizzeriaName")
STOCK_CONSUMPTION_ITEM_NAME_KEYS = ("stockItemName", "name", "productName", "ingredientName", "stockItemId")
STOCK_CONSUMPTION_ITEM_ID_KEYS = ("stockItemId", "id")
STOCK_CONSUMPTION_UNIT_ID_KEYS = ("unitId", "unitUUId", "unitUuid", "unitUUID")
STOCK_CONSUMPTION_UNIT_NAME_KEYS = ("unitName", "pizzeriaName")


def summarize_rating_rows(
    rows: list[Any],
    *,
    low_rate_threshold: float,
    top_limit: int,
) -> dict[str, Any]:
    units: list[dict[str, Any]] = []
    unscored_rows = 0
    for row in rows:
        if not isinstance(row, dict):
            unscored_rows += 1
            continue
        rate_key, rate = _extract_rating_value(row)
        if rate is None:
            unscored_rows += 1
            continue
        units.append(
            {
                "unitId": _first_non_empty(row, RATING_UNIT_ID_KEYS),
                "unitName": _first_non_empty(row, RATING_UNIT_NAME_KEYS),
                "rate": _round_metric(rate),
                "rateField": rate_key,
            }
        )

    units.sort(key=lambda item: (float(item["rate"]), str(item.get("unitName") or item.get("unitId") or "")))
    lowest_units = units[:top_limit]
    highest_units = sorted(
        units,
        key=lambda item: (-float(item["rate"]), str(item.get("unitName") or item.get("unitId") or "")),
    )[:top_limit]
    below_threshold = [unit for unit in units if float(unit["rate"]) < low_rate_threshold]
    rate_values = [float(unit["rate"]) for unit in units]

    return {
        "total": {
            "rowCount": len(rows),
            "ratedUnits": len(units),
            "unscoredRows": unscored_rows,
            "averageRate": _round_metric(sum(rate_values) / len(rate_values)) if rate_values else None,
            "minRate": _round_metric(min(rate_values)) if rate_values else None,
            "maxRate": _round_metric(max(rate_values)) if rate_values else None,
            "belowThresholdUnits": len(below_threshold),
        },
        "lowestUnits": lowest_units,
        "highestUnits": highest_units,
        "belowThreshold": below_threshold,
    }


def _extract_rating_value(row: dict[str, Any]) -> tuple[str | None, float | None]:
    for key in RATING_VALUE_KEYS:
        if key not in row:
            continue
        value = _parse_rating_value(row.get(key))
        if value is not None:
            return key, value
    return None, None


def _parse_rating_value(value: Any) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, str):
        normalized = value.strip().removesuffix("%").replace(",", ".")
        if not normalized:
            return None
        try:
            return float(normalized)
        except ValueError:
            return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_non_empty(row: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _configured_unit_names_by_id(settings: Settings) -> dict[str, str]:
    pizzerias = load_pizzerias(settings.dodo_pizzerias_path).get("pizzerias", [])
    result: dict[str, str] = {}
    for item in pizzerias:
        unit_id = str(item.get("unit_id") or "")
        name = str(item.get("name") or "")
        if not unit_id or not name:
            continue
        result[unit_id] = name
        result[unit_id.casefold()] = name
    return result


def summarize_inventory_stock_rows(
    rows: list[Any],
    *,
    low_stock_days_threshold: float,
    high_stock_days_threshold: float,
    top_limit: int,
    unit_names_by_id: dict[str, str] | None = None,
) -> dict[str, Any]:
    units: dict[str, dict[str, Any]] = {}
    items: list[dict[str, Any]] = []
    skipped_rows = 0
    currencies: set[str] = set()
    latest_calculated_at: str | None = None

    for row in rows:
        if not isinstance(row, dict):
            skipped_rows += 1
            continue

        item = _inventory_stock_item(row, unit_names_by_id=unit_names_by_id)
        items.append(item)
        if item.get("currency"):
            currencies.add(str(item["currency"]))
        calculated_at = item.get("calculatedAt")
        if calculated_at and (latest_calculated_at is None or str(calculated_at) > latest_calculated_at):
            latest_calculated_at = str(calculated_at)

        unit_key = item.get("unitId") or item.get("unitName") or "unknown"
        unit = units.setdefault(
            str(unit_key),
            _empty_inventory_unit(str(unit_key), item.get("unitName")),
        )
        _add_inventory_item_to_unit(
            unit,
            item,
            low_stock_days_threshold=low_stock_days_threshold,
            high_stock_days_threshold=high_stock_days_threshold,
        )

    low_stock_items = [
        item
        for item in items
        if _is_low_stock_item(item, low_stock_days_threshold)
    ]
    zero_or_negative_items = [
        item
        for item in items
        if item.get("quantity") is not None and float(item["quantity"]) <= 0
    ]
    high_stock_items = [
        item
        for item in items
        if _is_high_stock_item(item, high_stock_days_threshold)
    ]
    top_balance_items = [
        item
        for item in items
        if item.get("balanceInMoney") is not None and float(item["balanceInMoney"]) > 0
    ]

    unit_rows = [_finalize_inventory_unit(unit) for unit in units.values()]
    unit_rows.sort(key=lambda item: (-float(item["totalBalanceInMoney"]), item.get("unitName") or item["unitId"]))

    total_balance = sum(float(item.get("balanceInMoney") or 0) for item in items)
    return {
        "total": {
            "rowCount": len(rows),
            "itemCount": len(items),
            "skippedRows": skipped_rows,
            "totalBalanceInMoney": _round_metric(total_balance),
            "currencies": sorted(currencies),
            "lowStockItems": len(low_stock_items),
            "zeroOrNegativeItems": len(zero_or_negative_items),
            "highStockItems": len(high_stock_items),
            "unconfirmedItems": sum(1 for item in items if item.get("isConfirmed") is False),
            "latestCalculatedAt": latest_calculated_at,
        },
        "units": unit_rows,
        "criticalItems": _sort_inventory_low_stock(low_stock_items)[:top_limit],
        "zeroOrNegativeItems": _sort_inventory_low_stock(zero_or_negative_items)[:top_limit],
        "highStockItems": _sort_inventory_high_stock(high_stock_items)[:top_limit],
        "topBalanceItems": _sort_inventory_balance(top_balance_items)[:top_limit],
    }


def _inventory_stock_item(
    row: dict[str, Any],
    *,
    unit_names_by_id: dict[str, str] | None = None,
) -> dict[str, Any]:
    unit_id = _first_non_empty(row, INVENTORY_UNIT_ID_KEYS)
    unit_name = _first_non_empty(row, INVENTORY_UNIT_NAME_KEYS)
    if unit_id and not unit_name and unit_names_by_id:
        unit_name = unit_names_by_id.get(unit_id) or unit_names_by_id.get(unit_id.casefold())
    quantity = _optional_float(row.get("quantity"))
    balance = _optional_float(row.get("balanceInMoney"))
    avg_weekday = _optional_float(row.get("avgWeekdayExpense"))
    avg_weekend = _optional_float(row.get("avgWeekendExpense"))
    days_until_runout = _optional_float(row.get("daysUntilBalanceRunsOut"))
    return {
        "unitId": unit_id,
        "unitName": unit_name,
        "itemId": str(row.get("id")) if row.get("id") not in (None, "") else None,
        "name": _first_non_empty(row, INVENTORY_STOCK_NAME_KEYS),
        "categoryName": str(row.get("categoryName")) if row.get("categoryName") not in (None, "") else None,
        "quantity": _round_metric(quantity) if quantity is not None else None,
        "measurementUnit": str(row.get("measurementUnit")) if row.get("measurementUnit") not in (None, "") else None,
        "balanceInMoney": _round_metric(balance) if balance is not None else None,
        "currency": str(row.get("currency")) if row.get("currency") not in (None, "") else None,
        "avgWeekdayExpense": _round_metric(avg_weekday) if avg_weekday is not None else None,
        "avgWeekendExpense": _round_metric(avg_weekend) if avg_weekend is not None else None,
        "daysUntilBalanceRunsOut": _round_metric(days_until_runout) if days_until_runout is not None else None,
        "calculatedAt": str(row.get("calculatedAt")) if row.get("calculatedAt") not in (None, "") else None,
        "isConfirmed": row.get("isConfirmed") if isinstance(row.get("isConfirmed"), bool) else None,
    }


def _empty_inventory_unit(unit_id: str, unit_name: str | None) -> dict[str, Any]:
    return {
        "unitId": unit_id,
        "unitName": unit_name,
        "itemCount": 0,
        "totalBalanceInMoney": 0.0,
        "lowStockItems": 0,
        "zeroOrNegativeItems": 0,
        "highStockItems": 0,
        "unconfirmedItems": 0,
        "nearestRunOutDays": None,
    }


def _add_inventory_item_to_unit(
    unit: dict[str, Any],
    item: dict[str, Any],
    *,
    low_stock_days_threshold: float,
    high_stock_days_threshold: float,
) -> None:
    unit["itemCount"] += 1
    unit["totalBalanceInMoney"] += float(item.get("balanceInMoney") or 0)
    if item.get("unitName") and not unit.get("unitName"):
        unit["unitName"] = item["unitName"]
    if _is_low_stock_item(item, low_stock_days_threshold):
        unit["lowStockItems"] += 1
    if item.get("quantity") is not None and float(item["quantity"]) <= 0:
        unit["zeroOrNegativeItems"] += 1
    if _is_high_stock_item(item, high_stock_days_threshold):
        unit["highStockItems"] += 1
    if item.get("isConfirmed") is False:
        unit["unconfirmedItems"] += 1
    days = item.get("daysUntilBalanceRunsOut")
    if _has_consumption(item) and days is not None:
        current = unit.get("nearestRunOutDays")
        unit["nearestRunOutDays"] = float(days) if current is None else min(float(current), float(days))


def _finalize_inventory_unit(unit: dict[str, Any]) -> dict[str, Any]:
    result = dict(unit)
    result["totalBalanceInMoney"] = _round_metric(float(result["totalBalanceInMoney"]))
    if result["nearestRunOutDays"] is not None:
        result["nearestRunOutDays"] = _round_metric(float(result["nearestRunOutDays"]))
    return result


def _is_low_stock_item(item: dict[str, Any], threshold: float) -> bool:
    days = item.get("daysUntilBalanceRunsOut")
    if days is None:
        return False
    return float(days) <= threshold and (_has_consumption(item) or float(item.get("quantity") or 0) <= 0)


def _is_high_stock_item(item: dict[str, Any], threshold: float) -> bool:
    days = item.get("daysUntilBalanceRunsOut")
    if days is None:
        return False
    return float(days) >= threshold and _has_consumption(item)


def _has_consumption(item: dict[str, Any]) -> bool:
    return float(item.get("avgWeekdayExpense") or 0) > 0 or float(item.get("avgWeekendExpense") or 0) > 0


def _sort_inventory_low_stock(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        items,
        key=lambda item: (
            float(item.get("daysUntilBalanceRunsOut") or 0),
            -float(item.get("balanceInMoney") or 0),
            item.get("unitName") or "",
            item.get("name") or "",
        ),
    )


def _sort_inventory_high_stock(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        items,
        key=lambda item: (
            -float(item.get("daysUntilBalanceRunsOut") or 0),
            -float(item.get("balanceInMoney") or 0),
            item.get("unitName") or "",
            item.get("name") or "",
        ),
    )


def _sort_inventory_balance(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        items,
        key=lambda item: (
            -float(item.get("balanceInMoney") or 0),
            item.get("unitName") or "",
            item.get("name") or "",
        ),
    )


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, str):
        normalized = value.strip().removesuffix("%").replace(",", ".")
        if not normalized:
            return None
        try:
            return float(normalized)
        except ValueError:
            return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def summarize_stock_consumption_rows(
    rows: list[Any],
    *,
    top_limit: int,
    unit_names_by_id: dict[str, str] | None = None,
) -> dict[str, Any]:
    total = _empty_consumption_bucket()
    units: dict[str, dict[str, Any]] = {}
    item_totals: dict[tuple[str, str | None], dict[str, Any]] = {}
    unit_item_totals: dict[tuple[str, str, str | None], dict[str, Any]] = {}
    type_totals: dict[str, dict[str, Any]] = {}
    measurement_totals: dict[str, dict[str, Any]] = {}
    skipped_rows = 0
    currencies: set[str] = set()

    for row in rows:
        if not isinstance(row, dict):
            skipped_rows += 1
            continue

        item = _stock_consumption_item(row, unit_names_by_id=unit_names_by_id)
        _add_consumption_item(total, item)
        if item.get("currency"):
            currencies.add(str(item["currency"]))

        unit_key = item.get("unitId") or item.get("unitName") or "unknown"
        unit = units.setdefault(
            str(unit_key),
            {
                "unitId": str(unit_key),
                "unitName": item.get("unitName"),
                **_empty_consumption_bucket(),
            },
        )
        if item.get("unitName") and not unit.get("unitName"):
            unit["unitName"] = item["unitName"]
        _add_consumption_item(unit, item)

        type_key = str(item.get("consumptionType") or "Unknown")
        type_bucket = type_totals.setdefault(type_key, {"consumptionType": type_key, **_empty_consumption_bucket()})
        _add_consumption_item(type_bucket, item)

        measurement_key = str(item.get("measurementUnit") or "Unknown")
        measurement_bucket = measurement_totals.setdefault(
            measurement_key,
            {"measurementUnit": measurement_key, **_empty_consumption_bucket()},
        )
        _add_consumption_item(measurement_bucket, item)

        item_key = (str(item.get("stockItemName") or item.get("stockItemId") or "Unknown"), item.get("measurementUnit"))
        item_bucket = item_totals.setdefault(
            item_key,
            {
                "stockItemName": item_key[0],
                "measurementUnit": item.get("measurementUnit"),
                "unitCount": 0,
                "_unitIds": set(),
                **_empty_consumption_bucket(),
            },
        )
        _add_consumption_item(item_bucket, item)
        if item.get("unitId") and item["unitId"] not in item_bucket["_unitIds"]:
            item_bucket["_unitIds"].add(item["unitId"])
            item_bucket["unitCount"] += 1

        unit_item_key = (
            str(unit_key),
            str(item.get("stockItemName") or item.get("stockItemId") or "Unknown"),
            item.get("measurementUnit"),
        )
        unit_item_bucket = unit_item_totals.setdefault(
            unit_item_key,
            {
                "unitId": str(unit_key),
                "unitName": item.get("unitName"),
                "stockItemName": unit_item_key[1],
                "measurementUnit": item.get("measurementUnit"),
                **_empty_consumption_bucket(),
            },
        )
        if item.get("unitName") and not unit_item_bucket.get("unitName"):
            unit_item_bucket["unitName"] = item["unitName"]
        _add_consumption_item(unit_item_bucket, item)

    unit_rows = [_finalize_consumption_named_bucket(unit) for unit in units.values()]
    unit_rows.sort(key=lambda item: (-float(item["costWithVat"]), item.get("unitName") or item["unitId"]))

    type_rows = [_finalize_consumption_named_bucket(bucket) for bucket in type_totals.values()]
    type_rows.sort(key=lambda item: (-float(item["costWithVat"]), item["consumptionType"]))

    measurement_rows = [_finalize_consumption_named_bucket(bucket) for bucket in measurement_totals.values()]
    measurement_rows.sort(key=lambda item: (-float(item["costWithVat"]), item["measurementUnit"]))

    item_rows = [_finalize_consumption_named_bucket(_drop_private_sets(bucket)) for bucket in item_totals.values()]
    item_rows.sort(key=lambda item: (-float(item["costWithVat"]), item["stockItemName"]))

    unit_item_rows = [_finalize_consumption_named_bucket(bucket) for bucket in unit_item_totals.values()]
    unit_item_rows.sort(
        key=lambda item: (-float(item["costWithVat"]), item.get("unitName") or item["unitId"], item["stockItemName"])
    )

    return {
        "total": {
            **_finalize_consumption_bucket(total),
            "rowCount": len(rows),
            "skippedRows": skipped_rows,
            "currencies": sorted(currencies),
            "unitCount": len(units),
            "stockItemCount": len(item_totals),
            "consumptionTypeCount": len(type_totals),
        },
        "units": unit_rows,
        "byConsumptionType": type_rows,
        "byMeasurementUnit": measurement_rows,
        "topItems": item_rows[:top_limit],
        "topUnitItems": unit_item_rows[:top_limit],
    }


def _stock_consumption_item(
    row: dict[str, Any],
    *,
    unit_names_by_id: dict[str, str] | None = None,
) -> dict[str, Any]:
    unit_id = _first_non_empty(row, STOCK_CONSUMPTION_UNIT_ID_KEYS)
    unit_name = _first_non_empty(row, STOCK_CONSUMPTION_UNIT_NAME_KEYS)
    if unit_id and not unit_name and unit_names_by_id:
        unit_name = unit_names_by_id.get(unit_id) or unit_names_by_id.get(unit_id.casefold())
    return {
        "unitId": unit_id,
        "unitName": unit_name,
        "consumptionType": str(row.get("consumptionType")) if row.get("consumptionType") not in (None, "") else None,
        "stockItemId": _first_non_empty(row, STOCK_CONSUMPTION_ITEM_ID_KEYS),
        "stockItemName": _first_non_empty(row, STOCK_CONSUMPTION_ITEM_NAME_KEYS),
        "measurementUnit": str(row.get("measurementUnit")) if row.get("measurementUnit") not in (None, "") else None,
        "quantity": _optional_float(row.get("quantity")),
        "costWithVat": _optional_float(row.get("costWithVat")),
        "costWithoutVat": _optional_float(row.get("costWithoutVat")),
        "currency": str(row.get("currency")) if row.get("currency") not in (None, "") else None,
    }


def _empty_consumption_bucket() -> dict[str, Any]:
    return {
        "rows": 0,
        "quantity": 0.0,
        "costWithVat": 0.0,
        "costWithoutVat": 0.0,
    }


def _add_consumption_item(bucket: dict[str, Any], item: dict[str, Any]) -> None:
    bucket["rows"] += 1
    bucket["quantity"] += float(item.get("quantity") or 0)
    bucket["costWithVat"] += float(item.get("costWithVat") or 0)
    bucket["costWithoutVat"] += float(item.get("costWithoutVat") or 0)


def _finalize_consumption_bucket(bucket: dict[str, Any]) -> dict[str, int | float]:
    return {
        "rows": int(bucket["rows"]),
        "quantity": _round_metric(float(bucket["quantity"])),
        "costWithVat": _round_metric(float(bucket["costWithVat"])),
        "costWithoutVat": _round_metric(float(bucket["costWithoutVat"])),
    }


def _finalize_consumption_named_bucket(bucket: dict[str, Any]) -> dict[str, Any]:
    result = {
        key: value
        for key, value in bucket.items()
        if key not in {"rows", "quantity", "costWithVat", "costWithoutVat"} and not key.startswith("_")
    }
    result.update(_finalize_consumption_bucket(bucket))
    return result


def _drop_private_sets(bucket: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in bucket.items() if not key.startswith("_")}


def summarize_writeoff_product_rows(
    rows: list[Any],
    *,
    product_name_prefix: str,
    include_products: bool = False,
    include_reasons: bool = False,
) -> dict[str, Any]:
    prefix = product_name_prefix.casefold()
    units: dict[str, dict[str, Any]] = {}
    total = {"quantity": 0.0, "amount": 0.0, "rows": 0}
    matched_row_count = 0

    for row in rows:
        if not isinstance(row, dict):
            continue
        product_name = str(row.get("productName") or "")
        if prefix and not product_name.casefold().startswith(prefix):
            continue

        matched_row_count += 1
        unit_name = str(row.get("unitName") or "Неизвестная пиццерия")
        quantity = _as_float(row.get("quantity"))
        price_per_piece = _as_float(row.get("pricePerPiece"))
        amount = quantity * price_per_piece
        reason = str(row.get("reason") or "")

        unit = units.setdefault(
            unit_name,
            {
                "unitName": unit_name,
                "quantity": 0.0,
                "amount": 0.0,
                "rows": 0,
                "_products": {},
                "_reasons": {},
            },
        )
        _add_totals(unit, quantity, amount)
        _add_totals(total, quantity, amount)

        if include_products:
            products = unit["_products"]
            product = products.setdefault(
                product_name,
                {"productName": product_name, "quantity": 0.0, "amount": 0.0, "rows": 0},
            )
            _add_totals(product, quantity, amount)
        if include_reasons and reason:
            reasons = unit["_reasons"]
            reason_item = reasons.setdefault(
                reason,
                {"reason": reason, "quantity": 0.0, "amount": 0.0, "rows": 0},
            )
            _add_totals(reason_item, quantity, amount)

    unit_rows = []
    for unit in sorted(units.values(), key=lambda item: item["unitName"]):
        item = {
            "unitName": unit["unitName"],
            "quantity": _round_metric(unit["quantity"]),
            "amount": _round_metric(unit["amount"]),
            "rows": unit["rows"],
        }
        if include_products:
            item["products"] = [
                {
                    "productName": product["productName"],
                    "quantity": _round_metric(product["quantity"]),
                    "amount": _round_metric(product["amount"]),
                    "rows": product["rows"],
                }
                for product in sorted(
                    unit["_products"].values(),
                    key=lambda product: (-product["quantity"], product["productName"]),
                )
            ]
        if include_reasons:
            item["reasons"] = [
                {
                    "reason": reason["reason"],
                    "quantity": _round_metric(reason["quantity"]),
                    "amount": _round_metric(reason["amount"]),
                    "rows": reason["rows"],
                }
                for reason in sorted(
                    unit["_reasons"].values(),
                    key=lambda reason: (-reason["quantity"], reason["reason"]),
                )
            ]
        unit_rows.append(item)

    return {
        "matched_row_count": matched_row_count,
        "total": {
            "quantity": _round_metric(total["quantity"]),
            "amount": _round_metric(total["amount"]),
            "rows": total["rows"],
        },
        "units": unit_rows,
    }


def summarize_slice_writeoff_rate(
    *,
    writeoff_rows: list[Any],
    sales_rows: list[Any],
    product_name_prefix: str,
    include_products: bool = False,
) -> dict[str, Any]:
    prefix = product_name_prefix.casefold()
    units: dict[str, dict[str, Any]] = {}
    total = _empty_slice_rate_bucket("total")
    matched_writeoff_row_count = 0
    matched_sales_product_count = 0

    for row in writeoff_rows:
        if not isinstance(row, dict):
            continue
        product_name = str(row.get("productName") or "")
        if prefix and not product_name.casefold().startswith(prefix):
            continue
        matched_writeoff_row_count += 1
        unit_name = str(row.get("unitName") or "Неизвестная пиццерия")
        quantity = _as_float(row.get("quantity"))
        amount = quantity * _as_float(row.get("pricePerPiece"))
        unit = units.setdefault(unit_name, _empty_slice_rate_bucket(unit_name))
        _add_slice_rate_values(unit, "writeoff", quantity, amount, product_name, include_products)
        _add_slice_rate_values(total, "writeoff", quantity, amount, product_name, include_products)

    for row in sales_rows:
        if not isinstance(row, dict):
            continue
        unit_name = str(row.get("unitName") or "Неизвестная пиццерия")
        unit = units.setdefault(unit_name, _empty_slice_rate_bucket(unit_name))
        order_has_slice = False
        for product in row.get("products") or []:
            if not isinstance(product, dict):
                continue
            product_name = str(
                product.get("defaultProductName")
                or product.get("productName")
                or product.get("name")
                or ""
            )
            if prefix and not product_name.casefold().startswith(prefix):
                continue
            matched_sales_product_count += 1
            order_has_slice = True
            quantity = _product_quantity(product)
            amount = _product_amount(product, quantity)
            _add_slice_rate_values(unit, "sold", quantity, amount, product_name, include_products)
            _add_slice_rate_values(total, "sold", quantity, amount, product_name, include_products)
        if order_has_slice:
            unit["salesRowsWithSlices"] += 1
            total["salesRowsWithSlices"] += 1

    unit_rows = [_finalize_slice_rate_bucket(unit, include_products) for unit in units.values()]
    unit_rows = [unit for unit in unit_rows if unit["laidOutQuantity"] > 0]
    unit_rows.sort(key=lambda item: item["unitName"])

    return {
        "matchedWriteoffRows": matched_writeoff_row_count,
        "matchedSalesProducts": matched_sales_product_count,
        "total": _finalize_slice_rate_bucket(total, include_products, include_name=False),
        "units": unit_rows,
    }


def _new_slice_daily_dynamics_state(
    *,
    unit_ids: list[str],
    unit_names: dict[str, str],
    days: list[str],
) -> dict[str, Any]:
    return {
        "days": days,
        "matchedWriteoffRows": 0,
        "matchedSalesProducts": 0,
        "total": _empty_slice_rate_bucket("total"),
        "dayBuckets": {day: _empty_slice_rate_bucket("total") for day in days},
        "units": {
            unit_id: {
                "unitId": unit_id,
                "unitName": unit_names.get(unit_id),
                "total": _empty_slice_rate_bucket(unit_names.get(unit_id) or unit_id),
                "dayBuckets": {day: _empty_slice_rate_bucket(unit_names.get(unit_id) or unit_id) for day in days},
            }
            for unit_id in unit_ids
        },
    }


def _add_slice_dynamics_writeoff_rows(
    state: dict[str, Any],
    rows: list[Any],
    *,
    unit_id: str,
    unit_name: str | None,
    fallback_day: str,
    product_name_prefix: str,
    include_products: bool,
) -> None:
    prefix = product_name_prefix.casefold()
    unit = state["units"].setdefault(
        unit_id,
        {
            "unitId": unit_id,
            "unitName": unit_name,
            "total": _empty_slice_rate_bucket(unit_name or unit_id),
            "dayBuckets": {day: _empty_slice_rate_bucket(unit_name or unit_id) for day in state["days"]},
        },
    )
    if unit_name and not unit.get("unitName"):
        unit["unitName"] = unit_name
        unit["total"]["unitName"] = unit_name
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_unit_name = str(row.get("unitName") or unit_name or "")
        if row_unit_name and not unit.get("unitName"):
            unit["unitName"] = row_unit_name
            unit["total"]["unitName"] = row_unit_name
            for bucket in unit["dayBuckets"].values():
                bucket["unitName"] = row_unit_name
        product_name = str(row.get("productName") or "")
        if prefix and not product_name.casefold().startswith(prefix):
            continue
        day = _writeoff_row_day(row) or fallback_day
        if day not in state["dayBuckets"]:
            continue
        state["matchedWriteoffRows"] += 1
        quantity = _as_float(row.get("quantity"))
        amount = quantity * _as_float(row.get("pricePerPiece"))
        for bucket in (
            state["total"],
            state["dayBuckets"][day],
            unit["total"],
            unit["dayBuckets"][day],
        ):
            _add_slice_rate_values(bucket, "writeoff", quantity, amount, product_name, include_products)


def _add_slice_dynamics_sales_rows(
    state: dict[str, Any],
    rows: list[Any],
    *,
    unit_id: str,
    unit_name: str | None,
    fallback_day: str,
    product_name_prefix: str,
    include_products: bool,
) -> None:
    prefix = product_name_prefix.casefold()
    unit = state["units"].setdefault(
        unit_id,
        {
            "unitId": unit_id,
            "unitName": unit_name,
            "total": _empty_slice_rate_bucket(unit_name or unit_id),
            "dayBuckets": {day: _empty_slice_rate_bucket(unit_name or unit_id) for day in state["days"]},
        },
    )
    if unit_name and not unit.get("unitName"):
        unit["unitName"] = unit_name
        unit["total"]["unitName"] = unit_name
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_unit_name = str(row.get("unitName") or unit_name or "")
        if row_unit_name and not unit.get("unitName"):
            unit["unitName"] = row_unit_name
            unit["total"]["unitName"] = row_unit_name
            for bucket in unit["dayBuckets"].values():
                bucket["unitName"] = row_unit_name
        day = _sales_row_day(row) or fallback_day
        if day not in state["dayBuckets"]:
            continue
        order_has_slice = False
        for product in row.get("products") or []:
            if not isinstance(product, dict):
                continue
            product_name = str(
                product.get("defaultProductName")
                or product.get("productName")
                or product.get("name")
                or ""
            )
            if prefix and not product_name.casefold().startswith(prefix):
                continue
            state["matchedSalesProducts"] += 1
            order_has_slice = True
            quantity = _product_quantity(product)
            amount = _product_amount(product, quantity)
            for bucket in (
                state["total"],
                state["dayBuckets"][day],
                unit["total"],
                unit["dayBuckets"][day],
            ):
                _add_slice_rate_values(bucket, "sold", quantity, amount, product_name, include_products)
        if order_has_slice:
            for bucket in (
                state["total"],
                state["dayBuckets"][day],
                unit["total"],
                unit["dayBuckets"][day],
            ):
                bucket["salesRowsWithSlices"] += 1


def _finalize_slice_daily_dynamics_state(
    state: dict[str, Any],
    *,
    include_products: bool,
) -> dict[str, Any]:
    units = []
    for unit in state["units"].values():
        unit_name = unit.get("unitName") or unit["unitId"]
        unit["total"]["unitName"] = unit_name
        for bucket in unit["dayBuckets"].values():
            bucket["unitName"] = unit_name
        units.append(
            {
                "unitId": unit["unitId"],
                "unitName": unit_name,
                "total": _finalize_slice_rate_bucket(unit["total"], include_products, include_name=False),
                "days": [
                    {
                        "day": day,
                        **_finalize_slice_rate_bucket(
                            unit["dayBuckets"][day],
                            include_products,
                            include_name=False,
                        ),
                    }
                    for day in state["days"]
                ],
            }
        )
    units.sort(key=lambda item: item["unitName"])
    return {
        "matchedWriteoffRows": state["matchedWriteoffRows"],
        "matchedSalesProducts": state["matchedSalesProducts"],
        "total": _finalize_slice_rate_bucket(state["total"], include_products, include_name=False),
        "days": [
            {
                "day": day,
                **_finalize_slice_rate_bucket(state["dayBuckets"][day], include_products, include_name=False),
            }
            for day in state["days"]
        ],
        "units": units,
    }


def _new_slice_dynamics_source() -> dict[str, Any]:
    return {
        "row_count": 0,
        "pages_fetched": 0,
        "truncated": False,
        "truncatedDays": [],
    }


def _add_slice_dynamics_source(
    source: dict[str, Any],
    result: dict[str, Any],
    unit_id: str,
    unit_name: str | None,
    day: str,
) -> None:
    source["row_count"] += int(result.get("row_count") or 0)
    source["pages_fetched"] += int(result.get("pages_fetched") or 0)
    if result.get("truncated"):
        source["truncated"] = True
        source["truncatedDays"].append(
            {
                "unitId": unit_id,
                "unitName": unit_name,
                "day": day,
                "nextSkip": result.get("next_skip"),
            }
        )


def _empty_slice_rate_bucket(unit_name: str) -> dict[str, Any]:
    return {
        "unitName": unit_name,
        "soldQuantity": 0.0,
        "writeoffQuantity": 0.0,
        "soldAmount": 0.0,
        "writeoffAmount": 0.0,
        "soldRows": 0,
        "writeoffRows": 0,
        "salesRowsWithSlices": 0,
        "_products": {},
    }


def _add_slice_rate_values(
    target: dict[str, Any],
    kind: str,
    quantity: float,
    amount: float,
    product_name: str,
    include_products: bool,
) -> None:
    target[f"{kind}Quantity"] += quantity
    target[f"{kind}Amount"] += amount
    target[f"{kind}Rows"] += 1
    if include_products:
        product = target["_products"].setdefault(product_name, _empty_slice_rate_product(product_name))
        product[f"{kind}Quantity"] += quantity
        product[f"{kind}Amount"] += amount
        product[f"{kind}Rows"] += 1


def _empty_slice_rate_product(product_name: str) -> dict[str, Any]:
    return {
        "productName": product_name,
        "soldQuantity": 0.0,
        "writeoffQuantity": 0.0,
        "soldAmount": 0.0,
        "writeoffAmount": 0.0,
        "soldRows": 0,
        "writeoffRows": 0,
    }


def _finalize_slice_rate_bucket(
    bucket: dict[str, Any],
    include_products: bool,
    *,
    include_name: bool = True,
) -> dict[str, Any]:
    laid_out_quantity = bucket["soldQuantity"] + bucket["writeoffQuantity"]
    laid_out_amount = bucket["soldAmount"] + bucket["writeoffAmount"]
    item = {
        "soldQuantity": _round_metric(bucket["soldQuantity"]),
        "writeoffQuantity": _round_metric(bucket["writeoffQuantity"]),
        "laidOutQuantity": _round_metric(laid_out_quantity),
        "writeoffPercent": _percent(bucket["writeoffQuantity"], laid_out_quantity),
        "soldAmount": _round_metric(bucket["soldAmount"]),
        "writeoffAmount": _round_metric(bucket["writeoffAmount"]),
        "laidOutAmount": _round_metric(laid_out_amount),
        "soldRows": bucket["soldRows"],
        "writeoffRows": bucket["writeoffRows"],
        "salesRowsWithSlices": bucket["salesRowsWithSlices"],
    }
    if include_name:
        item = {"unitName": bucket["unitName"], **item}
    if include_products:
        item["products"] = [
            _finalize_slice_rate_product(product)
            for product in sorted(
                bucket["_products"].values(),
                key=lambda product: (-(product["soldQuantity"] + product["writeoffQuantity"]), product["productName"]),
            )
        ]
    return item


def _finalize_slice_rate_product(product: dict[str, Any]) -> dict[str, Any]:
    laid_out_quantity = product["soldQuantity"] + product["writeoffQuantity"]
    laid_out_amount = product["soldAmount"] + product["writeoffAmount"]
    return {
        "productName": product["productName"],
        "soldQuantity": _round_metric(product["soldQuantity"]),
        "writeoffQuantity": _round_metric(product["writeoffQuantity"]),
        "laidOutQuantity": _round_metric(laid_out_quantity),
        "writeoffPercent": _percent(product["writeoffQuantity"], laid_out_quantity),
        "soldAmount": _round_metric(product["soldAmount"]),
        "writeoffAmount": _round_metric(product["writeoffAmount"]),
        "laidOutAmount": _round_metric(laid_out_amount),
        "soldRows": product["soldRows"],
        "writeoffRows": product["writeoffRows"],
    }


def _product_quantity(product: dict[str, Any]) -> float:
    if "quantity" not in product or product.get("quantity") in (None, ""):
        return 1.0
    quantity = _as_float(product.get("quantity"))
    return quantity if quantity > 0 else 1.0


def _product_amount(product: dict[str, Any], quantity: float) -> float:
    value = product.get("priceWithDiscount")
    if value is None:
        value = product.get("price")
    return _as_float(value) * quantity


def _percent(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator * 100, 1)


def _source_meta(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "rows_key": result.get("rows_key"),
        "row_count": result.get("row_count"),
        "pages_fetched": result.get("pages_fetched"),
        "truncated": result.get("truncated"),
        "next_skip": result.get("next_skip"),
    }


def _add_totals(target: dict[str, Any], quantity: float, amount: float) -> None:
    target["quantity"] += quantity
    target["amount"] += amount
    target["rows"] += 1


def _as_float(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _round_metric(value: float) -> int | float:
    rounded = round(value, 2)
    if rounded.is_integer():
        return int(rounded)
    return rounded


def _bounded_sales_summary_max_pages(value: int | None) -> int:
    pages = value or SALES_SUMMARY_DEFAULT_MAX_PAGES_PER_UNIT
    return max(1, min(pages, SALES_SUMMARY_MAX_PAGES_PER_UNIT))


def _bounded_sales_summary_concurrency(value: int | None, unit_count: int) -> int:
    concurrency = value or SALES_SUMMARY_DEFAULT_CONCURRENCY
    return max(1, min(concurrency, SALES_SUMMARY_MAX_CONCURRENCY, max(unit_count, 1)))


def _bounded_discount_action_limit(value: int | None) -> int:
    limit = value if value is not None else 10
    return max(1, min(limit, 200))


def _sales_summary_days(parameters: dict[str, Any]) -> list[str]:
    from_day = date.fromisoformat(str(parameters["from"]))
    to_exclusive = date.fromisoformat(str(parameters["to"]))
    days = []
    current = from_day
    while current < to_exclusive:
        days.append(current.isoformat())
        current += timedelta(days=1)
    return days


def _sales_summary_bucket_from_cached_rows(
    *,
    unit_id: str,
    unit_name: str | None,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    bucket = _new_sales_summary_bucket(unit_id=unit_id, unit_name=unit_name)
    refreshed_values = []
    for row in rows:
        if row.get("unitName"):
            bucket["unitName"] = row["unitName"]
        _add_sales_summary_bucket(bucket, row)
        if row.get("refreshedAt"):
            refreshed_values.append(str(row["refreshedAt"]))

    bucket["source"] = {
        "rowsKey": "dodo_sales_summary_daily",
        "pagesFetched": 0,
        "truncated": False,
        "nextSkip": None,
        "cache": "hit",
        "days": len(rows),
        "refreshedAtMin": min(refreshed_values) if refreshed_values else None,
        "refreshedAtMax": max(refreshed_values) if refreshed_values else None,
    }
    return bucket


def _new_sales_summary_bucket(
    *,
    unit_id: str | None = None,
    unit_name: str | None = None,
) -> dict[str, Any]:
    bucket: dict[str, Any] = {
        "orders": 0,
        "products": 0,
        "salesWithDiscount": 0.0,
        "salesWithoutDiscount": 0.0,
    }
    if unit_id is not None:
        bucket["unitId"] = unit_id
    if unit_name is not None:
        bucket["unitName"] = unit_name
    return bucket


def _add_sales_rows_to_bucket(
    bucket: dict[str, Any],
    rows: list[Any],
    *,
    daily_buckets: dict[str, dict[str, Any]] | None = None,
) -> None:
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("unitId"):
            bucket["unitId"] = row["unitId"]
        if row.get("unitName"):
            bucket["unitName"] = row["unitName"]

        products_count = 0
        sales_with_discount = 0.0
        sales_without_discount = 0.0
        products = row.get("products")
        if isinstance(products, list):
            for product in products:
                if not isinstance(product, dict):
                    continue
                products_count += 1
                sales_with_discount += _as_float(product.get("priceWithDiscount"))
                sales_without_discount += _as_float(product.get("price"))

        _add_sales_row_metrics(
            bucket,
            orders=1,
            products=products_count,
            sales_with_discount=sales_with_discount,
            sales_without_discount=sales_without_discount,
        )

        if daily_buckets is None:
            continue
        day = _sales_row_day(row)
        if not day:
            continue
        daily_bucket = daily_buckets.setdefault(
            day,
            _new_sales_summary_bucket(
                unit_id=str(row.get("unitId") or bucket.get("unitId") or ""),
                unit_name=str(row.get("unitName") or bucket.get("unitName") or "") or None,
            ),
        )
        if row.get("unitName"):
            daily_bucket["unitName"] = row["unitName"]
        _add_sales_row_metrics(
            daily_bucket,
            orders=1,
            products=products_count,
            sales_with_discount=sales_with_discount,
            sales_without_discount=sales_without_discount,
        )


def _add_sales_row_metrics(
    bucket: dict[str, Any],
    *,
    orders: int,
    products: int,
    sales_with_discount: float,
    sales_without_discount: float,
) -> None:
    bucket["orders"] += orders
    bucket["products"] += products
    bucket["salesWithDiscount"] += sales_with_discount
    bucket["salesWithoutDiscount"] += sales_without_discount


def _add_sales_summary_bucket(total: dict[str, Any], bucket: dict[str, Any]) -> None:
    total["orders"] += int(bucket["orders"])
    total["products"] += int(bucket["products"])
    total["salesWithDiscount"] += float(bucket["salesWithDiscount"])
    total["salesWithoutDiscount"] += float(bucket["salesWithoutDiscount"])


def _sales_row_day(row: dict[str, Any]) -> str | None:
    value = str(row.get("soldAtLocal") or row.get("soldAt") or "")
    return _date_prefix(value)


def _writeoff_row_day(row: dict[str, Any]) -> str | None:
    value = str(row.get("writtenOffAtLocal") or row.get("writtenOffAt") or "")
    return _date_prefix(value)


def _date_prefix(value: str) -> str | None:
    if len(value) < 10:
        return None
    day = value[:10]
    try:
        date.fromisoformat(day)
    except ValueError:
        return None
    return day


def _finalize_sales_summary_bucket(bucket: dict[str, Any]) -> dict[str, Any]:
    orders = int(bucket["orders"])
    sales_with_discount = float(bucket["salesWithDiscount"])
    sales_without_discount = float(bucket["salesWithoutDiscount"])
    result = {
        "orders": orders,
        "products": int(bucket["products"]),
        "salesWithDiscount": _round_metric(sales_with_discount),
        "salesWithoutDiscount": _round_metric(sales_without_discount),
        "discount": _round_metric(sales_without_discount - sales_with_discount),
        "averageCheck": _round_metric(sales_with_discount / orders) if orders else 0,
    }
    if "unitId" in bucket:
        result["unitId"] = bucket["unitId"]
    if "unitName" in bucket:
        result["unitName"] = bucket["unitName"]
    if "source" in bucket:
        result["source"] = bucket["source"]
    return result


def _new_sales_channel_bucket() -> dict[str, Any]:
    return {
        "orders": 0,
        "products": 0,
        "salesWithDiscount": 0.0,
        "salesWithoutDiscount": 0.0,
    }


def _sales_row_product_metrics(row: dict[str, Any]) -> tuple[int, float, float]:
    products_count = 0
    sales_with_discount = 0.0
    sales_without_discount = 0.0
    products = row.get("products")
    if isinstance(products, list):
        for product in products:
            if not isinstance(product, dict):
                continue
            products_count += 1
            sales_with_discount += _as_float(product.get("priceWithDiscount"))
            sales_without_discount += _as_float(product.get("price"))
    return products_count, sales_with_discount, sales_without_discount


def _add_sales_channel_rows(
    total: dict[str, Any],
    sales_channels: dict[str, dict[str, Any]],
    order_sources: dict[str, dict[str, Any]],
    rows: list[Any],
) -> None:
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("unitId"):
            total["unitId"] = row["unitId"]
        if row.get("unitName"):
            total["unitName"] = row["unitName"]

        products_count, sales_with_discount, sales_without_discount = _sales_row_product_metrics(row)
        _add_sales_row_metrics(
            total,
            orders=1,
            products=products_count,
            sales_with_discount=sales_with_discount,
            sales_without_discount=sales_without_discount,
        )

        channel = _sales_dimension_value(row.get("salesChannel"), "Unknown")
        channel_bucket = sales_channels.setdefault(channel, _new_sales_channel_bucket())
        _add_sales_row_metrics(
            channel_bucket,
            orders=1,
            products=products_count,
            sales_with_discount=sales_with_discount,
            sales_without_discount=sales_without_discount,
        )

        source = _sales_dimension_value(row.get("orderSource"), "Unknown")
        source_bucket = order_sources.setdefault(source, _new_sales_channel_bucket())
        _add_sales_row_metrics(
            source_bucket,
            orders=1,
            products=products_count,
            sales_with_discount=sales_with_discount,
            sales_without_discount=sales_without_discount,
        )


def _sales_dimension_value(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    return text or fallback


def _add_sales_channel_bucket(total: dict[str, Any], bucket: dict[str, Any]) -> None:
    total["orders"] += int(bucket.get("orders") or 0)
    total["products"] += int(bucket.get("products") or 0)
    total["salesWithDiscount"] += _as_float(bucket.get("salesWithDiscount"))
    total["salesWithoutDiscount"] += _as_float(bucket.get("salesWithoutDiscount"))


def _finalize_sales_channel_bucket(bucket: dict[str, Any], days_count: int) -> dict[str, Any]:
    result = _finalize_sales_summary_bucket(bucket)
    result.pop("unitId", None)
    result.pop("unitName", None)
    result.pop("source", None)
    result["averageOrdersPerDay"] = _round_metric(result["orders"] / days_count) if days_count else 0
    return result


def _finalize_named_sales_buckets(
    buckets: dict[str, dict[str, Any]],
    days_count: int,
    name_key: str,
) -> list[dict[str, Any]]:
    result = []
    for name in sorted(buckets):
        result.append({name_key: name, **_finalize_sales_channel_bucket(buckets[name], days_count)})
    return result


DISCOUNT_CATEGORY_RULES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("cvm", "CVM", ("cvm",)),
    ("employee", "Сотрудникам", ("сотрудник", "employee", "staff")),
    ("combo", "Комбо", ("combo", "комбо")),
    ("dodo_coins", "Додокоины", ("додокоин", "dodo coin", "dodo coins", "coin")),
    ("certificate", "Сертификаты", ("сертификат", "certificate")),
    ("voucher", "Ваучеры", ("voucher", "ваучер")),
    ("customer_support", "Customer support", ("customer support", "поддержк", "компенсац")),
    ("local", "Локальный", ("local", "локал")),
    ("regional", "Региональный", ("regional", "регион")),
    ("federal", "Федеральный", ("federal", "федерал")),
    ("b2b", "B2B", ("b2b", "корпоратив")),
    ("sauces_addons", "Соусы и добавки", ("соус", "сахар", "прибор", "сгущ", "варенье")),
    ("new_customer", "Новые клиенты", ("новые клиент", "new client", "first25", "первый заказ")),
    ("personal_price", "Персональная цена", ("personalprice", "personal price", "персональн")),
)


def _new_sales_discount_bucket() -> dict[str, Any]:
    return {
        "orders": 0,
        "products": 0,
        "salesWithDiscount": 0.0,
        "salesWithoutDiscount": 0.0,
        "discountAmount": 0.0,
        "discountedOrders": 0,
        "discountedProducts": 0,
        "categories": {},
    }


def _new_discount_category_bucket(category: str, category_name: str) -> dict[str, Any]:
    return {
        "category": category,
        "categoryName": category_name,
        "orders": 0,
        "products": 0,
        "salesWithDiscount": 0.0,
        "salesWithoutDiscount": 0.0,
        "discountAmount": 0.0,
        "actions": {},
    }


def _new_discount_action_bucket(
    *,
    category: str,
    action_name: str | None,
    bonus_action_id: str | None,
) -> dict[str, Any]:
    return {
        "category": category,
        "actionName": action_name,
        "bonusActionId": bonus_action_id,
        "orders": 0,
        "products": 0,
        "salesWithDiscount": 0.0,
        "salesWithoutDiscount": 0.0,
        "discountAmount": 0.0,
        "promocodeProducts": 0,
        "promocodeMasked": None,
    }


def _add_sales_discount_rows(bucket: dict[str, Any], rows: list[Any]) -> None:
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("unitId"):
            bucket["unitId"] = row["unitId"]
        if row.get("unitName"):
            bucket["unitName"] = row["unitName"]
        bucket["orders"] += 1

        row_has_discount = False
        category_hits: set[str] = set()
        action_hits: set[tuple[str, str]] = set()
        products = row.get("products")
        if not isinstance(products, list):
            continue
        for product in products:
            if not isinstance(product, dict):
                continue
            price = _as_float(product.get("price"))
            price_with_discount = _as_float(product.get("priceWithDiscount"))
            discount_amount = max(0.0, price - price_with_discount)
            bucket["products"] += 1
            bucket["salesWithoutDiscount"] += price
            bucket["salesWithDiscount"] += price_with_discount
            bucket["discountAmount"] += discount_amount
            if discount_amount <= 0:
                continue

            row_has_discount = True
            bucket["discountedProducts"] += 1
            discount = product.get("discount") if isinstance(product.get("discount"), dict) else {}
            category, category_name = _classify_discount_category(discount)
            category_bucket = bucket["categories"].setdefault(
                category,
                _new_discount_category_bucket(category, category_name),
            )
            _add_discount_product_metrics(
                category_bucket,
                products=1,
                sales_with_discount=price_with_discount,
                sales_without_discount=price,
                discount_amount=discount_amount,
            )
            category_hits.add(category)

            action_key, action_bucket = _discount_action_identity(discount, category)
            existing_action_bucket = category_bucket["actions"].setdefault(action_key, action_bucket)
            _add_discount_product_metrics(
                existing_action_bucket,
                products=1,
                sales_with_discount=price_with_discount,
                sales_without_discount=price,
                discount_amount=discount_amount,
            )
            promo = str(discount.get("promoCode") or "").strip()
            if promo:
                existing_action_bucket["promocodeProducts"] += 1
                if not existing_action_bucket.get("promocodeMasked"):
                    existing_action_bucket["promocodeMasked"] = _mask_promocode(promo)
            action_hits.add((category, action_key))

        if row_has_discount:
            bucket["discountedOrders"] += 1
        for category in category_hits:
            bucket["categories"][category]["orders"] += 1
        for category, action_key in action_hits:
            bucket["categories"][category]["actions"][action_key]["orders"] += 1


def _add_discount_product_metrics(
    bucket: dict[str, Any],
    *,
    products: int,
    sales_with_discount: float,
    sales_without_discount: float,
    discount_amount: float,
) -> None:
    bucket["products"] += products
    bucket["salesWithDiscount"] += sales_with_discount
    bucket["salesWithoutDiscount"] += sales_without_discount
    bucket["discountAmount"] += discount_amount


def _classify_discount_category(discount: dict[str, Any]) -> tuple[str, str]:
    text = _normalized_discount_text(
        discount.get("bonusActionName"),
        discount.get("promoCode"),
        discount.get("bonusActionId"),
    )
    for category, category_name, needles in DISCOUNT_CATEGORY_RULES:
        if any(needle in text for needle in needles):
            return category, category_name
    if str(discount.get("promoCode") or "").strip():
        return "promocode_other", "Промокод: прочее"
    return "other", "Прочее"


def _normalized_discount_text(*values: Any) -> str:
    text = " ".join(str(value or "") for value in values).casefold()
    return text.replace("сvm", "cvm").replace("сvм", "cvm").replace("cvм", "cvm")


def _discount_action_identity(discount: dict[str, Any], category: str) -> tuple[str, dict[str, Any]]:
    action_name = str(discount.get("bonusActionName") or "").strip() or None
    bonus_action_id = str(discount.get("bonusActionId") or "").strip() or None
    promo = str(discount.get("promoCode") or "").strip()
    identity = bonus_action_id or action_name or (f"promo:{_mask_promocode(promo)}" if promo else "unknown")
    action_key = f"{category}:{identity}"
    return (
        action_key,
        _new_discount_action_bucket(
            category=category,
            action_name=action_name,
            bonus_action_id=bonus_action_id,
        ),
    )


def _mask_promocode(value: str) -> str:
    text = value.strip()
    if not text:
        return ""
    if len(text) <= 4:
        return "*" * len(text)
    return f"{text[:2]}***{text[-2:]}"


def _add_sales_discount_bucket(total: dict[str, Any], bucket: dict[str, Any]) -> None:
    for key in ("orders", "products", "discountedOrders", "discountedProducts"):
        total[key] += int(bucket.get(key) or 0)
    for key in ("salesWithDiscount", "salesWithoutDiscount", "discountAmount"):
        total[key] += _as_float(bucket.get(key))

    for category, category_bucket in bucket.get("categories", {}).items():
        target = total["categories"].setdefault(
            category,
            _new_discount_category_bucket(
                category,
                str(category_bucket.get("categoryName") or category),
            ),
        )
        target["orders"] += int(category_bucket.get("orders") or 0)
        _add_discount_product_metrics(
            target,
            products=int(category_bucket.get("products") or 0),
            sales_with_discount=_as_float(category_bucket.get("salesWithDiscount")),
            sales_without_discount=_as_float(category_bucket.get("salesWithoutDiscount")),
            discount_amount=_as_float(category_bucket.get("discountAmount")),
        )
        for action_key, action_bucket in category_bucket.get("actions", {}).items():
            target_action = target["actions"].setdefault(
                action_key,
                _new_discount_action_bucket(
                    category=category,
                    action_name=action_bucket.get("actionName"),
                    bonus_action_id=action_bucket.get("bonusActionId"),
                ),
            )
            target_action["orders"] += int(action_bucket.get("orders") or 0)
            target_action["promocodeProducts"] += int(action_bucket.get("promocodeProducts") or 0)
            if not target_action.get("promocodeMasked") and action_bucket.get("promocodeMasked"):
                target_action["promocodeMasked"] = action_bucket["promocodeMasked"]
            _add_discount_product_metrics(
                target_action,
                products=int(action_bucket.get("products") or 0),
                sales_with_discount=_as_float(action_bucket.get("salesWithDiscount")),
                sales_without_discount=_as_float(action_bucket.get("salesWithoutDiscount")),
                discount_amount=_as_float(action_bucket.get("discountAmount")),
            )


def _finalize_sales_discount_total(bucket: dict[str, Any]) -> dict[str, Any]:
    result = {
        "orders": int(bucket["orders"]),
        "products": int(bucket["products"]),
        "salesWithDiscount": _round_metric(bucket["salesWithDiscount"]),
        "salesWithoutDiscount": _round_metric(bucket["salesWithoutDiscount"]),
        "discountAmount": _round_metric(bucket["discountAmount"]),
        "discountedOrders": int(bucket["discountedOrders"]),
        "discountedProducts": int(bucket["discountedProducts"]),
        "discountShareOfSalesWithoutDiscountPercent": _percent(
            bucket["discountAmount"],
            bucket["salesWithoutDiscount"],
        ),
    }
    return result


def _finalize_discount_categories(
    categories: dict[str, dict[str, Any]],
    total_discount: float,
    total_sales_without_discount: float,
    *,
    include_actions: bool,
    top_actions_limit: int,
) -> list[dict[str, Any]]:
    result = []
    for category_bucket in sorted(
        categories.values(),
        key=lambda item: (-_as_float(item.get("discountAmount")), str(item.get("category"))),
    ):
        result.append(
            _finalize_discount_category(
                category_bucket,
                total_discount,
                total_sales_without_discount,
                include_actions=include_actions,
                top_actions_limit=top_actions_limit,
            )
        )
    return result


def _finalize_discount_category(
    bucket: dict[str, Any],
    total_discount: float,
    total_sales_without_discount: float,
    *,
    include_actions: bool,
    top_actions_limit: int,
) -> dict[str, Any]:
    discount_amount = _as_float(bucket.get("discountAmount"))
    sales_without_discount = _as_float(bucket.get("salesWithoutDiscount"))
    item: dict[str, Any] = {
        "category": bucket["category"],
        "categoryName": bucket["categoryName"],
        "orders": int(bucket["orders"]),
        "products": int(bucket["products"]),
        "salesWithDiscount": _round_metric(_as_float(bucket.get("salesWithDiscount"))),
        "salesWithoutDiscount": _round_metric(sales_without_discount),
        "discountAmount": _round_metric(discount_amount),
        "shareOfTotalDiscountPercent": _percent(discount_amount, total_discount),
        "shareOfTotalSalesWithoutDiscountPercent": _percent(discount_amount, total_sales_without_discount),
        "discountPercentOfCategorySalesWithoutDiscount": _percent(discount_amount, sales_without_discount),
    }
    if include_actions:
        item["actions"] = _finalize_discount_actions(
            bucket.get("actions", {}),
            category_discount=discount_amount,
            top_actions_limit=top_actions_limit,
        )
    return item


def _finalize_discount_actions(
    actions: dict[str, dict[str, Any]],
    *,
    category_discount: float,
    top_actions_limit: int,
) -> list[dict[str, Any]]:
    result = []
    for action in sorted(
        actions.values(),
        key=lambda item: (-_as_float(item.get("discountAmount")), str(item.get("actionName") or "")),
    )[:top_actions_limit]:
        discount_amount = _as_float(action.get("discountAmount"))
        sales_without_discount = _as_float(action.get("salesWithoutDiscount"))
        result.append(
            {
                "actionName": action.get("actionName"),
                "bonusActionId": action.get("bonusActionId"),
                "orders": int(action["orders"]),
                "products": int(action["products"]),
                "salesWithDiscount": _round_metric(_as_float(action.get("salesWithDiscount"))),
                "salesWithoutDiscount": _round_metric(sales_without_discount),
                "discountAmount": _round_metric(discount_amount),
                "shareOfCategoryDiscountPercent": _percent(discount_amount, category_discount),
                "discountPercentOfActionSalesWithoutDiscount": _percent(discount_amount, sales_without_discount),
                "promocodeProducts": int(action.get("promocodeProducts") or 0),
                "promocodeMasked": action.get("promocodeMasked"),
            }
        )
    return result


def _kiosk_share(
    order_sources: dict[str, dict[str, Any]],
    sales_channels: dict[str, dict[str, Any]],
) -> dict[str, int | float]:
    kiosk = _find_sales_bucket(order_sources, "kiosk", "киоск")
    restaurant = _find_sales_bucket(sales_channels, "dine-in", "dine in", "restaurant", "рест", "зал")
    total = _new_sales_channel_bucket()
    for bucket in order_sources.values():
        _add_sales_channel_bucket(total, bucket)

    return {
        "orders": int(kiosk.get("orders") or 0),
        "salesWithDiscount": _round_metric(_as_float(kiosk.get("salesWithDiscount"))),
        "shareOfRestaurantOrdersPercent": _percent(
            _as_float(kiosk.get("orders")),
            _as_float(restaurant.get("orders")),
        ),
        "shareOfRestaurantSalesPercent": _percent(
            _as_float(kiosk.get("salesWithDiscount")),
            _as_float(restaurant.get("salesWithDiscount")),
        ),
        "shareOfAllOrdersPercent": _percent(
            _as_float(kiosk.get("orders")),
            _as_float(total.get("orders")),
        ),
        "shareOfAllSalesPercent": _percent(
            _as_float(kiosk.get("salesWithDiscount")),
            _as_float(total.get("salesWithDiscount")),
        ),
    }


def _find_sales_bucket(buckets: dict[str, dict[str, Any]], *needles: str) -> dict[str, Any]:
    normalized_needles = tuple(needle.casefold() for needle in needles)
    for name, bucket in buckets.items():
        normalized_name = name.casefold()
        if any(needle in normalized_name for needle in normalized_needles):
            return bucket
    return _new_sales_channel_bucket()


def _sales_channel_z_scores(unit_results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    unit_ids = [str(unit["unitId"]) for unit in unit_results]
    unit_channel_values: dict[str, dict[str, float]] = {}
    channels: set[str] = set()
    for unit in unit_results:
        channel_values = {
            str(channel["salesChannel"]): _as_float(channel.get("averageOrdersPerDay"))
            for channel in unit.get("salesChannels", [])
            if isinstance(channel, dict) and channel.get("salesChannel")
        }
        unit_channel_values[str(unit["unitId"])] = channel_values
        channels.update(channel_values)

    total_values = {
        str(unit["unitId"]): _as_float(unit.get("total", {}).get("averageOrdersPerDay"))
        for unit in unit_results
    }
    total_scores = _z_score_map(total_values, unit_ids)
    channel_scores = {
        channel: _z_score_map(
            {unit_id: unit_channel_values.get(unit_id, {}).get(channel, 0.0) for unit_id in unit_ids},
            unit_ids,
        )
        for channel in sorted(channels)
    }

    result: dict[str, dict[str, Any]] = {}
    for unit_id in unit_ids:
        by_channel = [
            {"salesChannel": channel, **scores[unit_id]}
            for channel, scores in channel_scores.items()
        ]
        restaurant_score = _first_matching_channel_score(by_channel, "dine-in", "dine in", "restaurant", "рест", "зал")
        delivery_score = _first_matching_channel_score(by_channel, "delivery", "достав")
        result[unit_id] = {
            "total": total_scores[unit_id],
            "restaurantOrdersPerDayZScore": restaurant_score.get("zScore") if restaurant_score else None,
            "deliveryOrdersPerDayZScore": delivery_score.get("zScore") if delivery_score else None,
            "bySalesChannel": by_channel,
        }
    return result


def _z_score_map(values_by_unit: dict[str, float], unit_ids: list[str]) -> dict[str, dict[str, int | float]]:
    values = [values_by_unit.get(unit_id, 0.0) for unit_id in unit_ids]
    count = len(values)
    mean = sum(values) / count if count else 0.0
    variance = sum((value - mean) ** 2 for value in values) / count if count else 0.0
    standard_deviation = variance ** 0.5
    result: dict[str, dict[str, int | float]] = {}
    for unit_id in unit_ids:
        value = values_by_unit.get(unit_id, 0.0)
        z_score = 0.0 if standard_deviation == 0 else (value - mean) / standard_deviation
        result[unit_id] = {
            "averageOrdersPerDay": _round_metric(value),
            "mean": _round_metric(mean),
            "standardDeviation": _round_metric(standard_deviation),
            "zScore": _round_metric(z_score),
        }
    return result


def _first_matching_channel_score(
    by_channel: list[dict[str, Any]],
    *needles: str,
) -> dict[str, Any] | None:
    normalized_needles = tuple(needle.casefold() for needle in needles)
    for item in by_channel:
        channel = str(item.get("salesChannel") or "").casefold()
        if any(needle in channel for needle in normalized_needles):
            return item
    return None


def _sales_summary_metrics(value: Any) -> dict[str, int | float]:
    source = value if isinstance(value, dict) else {}
    return {key: _round_metric(_as_float(source.get(key))) for key in SALES_SUMMARY_METRIC_KEYS}


def _compare_sales_metrics(
    current: dict[str, int | float],
    baseline: dict[str, int | float],
) -> dict[str, dict[str, int | float | None]]:
    change: dict[str, int | float] = {}
    change_percent: dict[str, int | float | None] = {}
    for key in SALES_SUMMARY_METRIC_KEYS:
        current_value = _as_float(current.get(key))
        baseline_value = _as_float(baseline.get(key))
        delta = current_value - baseline_value
        change[key] = _round_metric(delta)
        change_percent[key] = None if baseline_value == 0 else _round_metric(delta / baseline_value * 100)
    return {"change": change, "changePercent": change_percent}


def _compare_sales_units(
    current_units: list[Any],
    baseline_units: list[Any],
) -> list[dict[str, Any]]:
    current_by_unit = {
        str(item["unitId"]): item
        for item in current_units
        if isinstance(item, dict) and item.get("unitId")
    }
    baseline_by_unit = {
        str(item["unitId"]): item
        for item in baseline_units
        if isinstance(item, dict) and item.get("unitId")
    }
    unit_ids = set(current_by_unit) | set(baseline_by_unit)
    result = []
    for unit_id in sorted(unit_ids, key=lambda item: _comparison_unit_name(item, current_by_unit, baseline_by_unit)):
        current = _sales_summary_metrics(current_by_unit.get(unit_id))
        baseline = _sales_summary_metrics(baseline_by_unit.get(unit_id))
        comparison = _compare_sales_metrics(current, baseline)
        current_item = current_by_unit.get(unit_id) or {}
        baseline_item = baseline_by_unit.get(unit_id) or {}
        result.append(
            {
                "unitId": unit_id,
                "unitName": current_item.get("unitName") or baseline_item.get("unitName"),
                "current": current,
                "baseline": baseline,
                "change": comparison["change"],
                "changePercent": comparison["changePercent"],
            }
        )
    return result


def _comparison_unit_name(
    unit_id: str,
    current_by_unit: dict[str, dict[str, Any]],
    baseline_by_unit: dict[str, dict[str, Any]],
) -> str:
    current = current_by_unit.get(unit_id) or {}
    baseline = baseline_by_unit.get(unit_id) or {}
    return str(current.get("unitName") or baseline.get("unitName") or unit_id)


def external_http_error_detail(exc: httpx.HTTPStatusError, tool_name: str) -> dict[str, Any]:
    response = exc.response
    detail: dict[str, Any] = {
        "error": "external_http_error",
        "tool_name": tool_name,
        "external_status": response.status_code,
    }
    try:
        payload: Any = response.json()
    except ValueError:
        payload = response.text

    if isinstance(payload, dict):
        code = payload.get("code") or payload.get("Code")
        message = payload.get("message") or payload.get("Message")
        details = payload.get("details") or payload.get("Details")
        if code:
            detail["external_code"] = code
        if message:
            detail["external_message"] = message
        if details:
            detail["external_details"] = details
        if str(code).casefold() == "insufficientscopes":
            detail["error"] = "external_insufficient_scopes"
            scope_hint = _extract_scope_hint(details)
            if scope_hint:
                detail["required_scope_hint"] = scope_hint
    elif payload:
        detail["external_body_preview"] = str(payload)[:500]

    return detail


def _extract_scope_hint(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("allowedScope", "allowedScopes", "requiredScope", "requiredScopes", "scope", "scopes"):
            if value.get(key):
                return str(value[key])
        for item in value.values():
            hint = _extract_scope_hint(item)
            if hint:
                return hint
    if isinstance(value, list):
        for item in value:
            hint = _extract_scope_hint(item)
            if hint:
                return hint
    return None


def external_request_error_detail(
    exc: httpx.RequestError,
    tool_name: str,
    *,
    error: str,
    hint: str | None = None,
) -> dict[str, Any]:
    detail: dict[str, Any] = {
        "error": error,
        "tool_name": tool_name,
        "exception": exc.__class__.__name__,
    }
    if hint:
        detail["hint"] = hint
    return detail


def extract_meta(payload: Any, keys: tuple[str, ...]) -> dict[str, Any]:
    if not keys or not isinstance(payload, dict):
        return {}
    return {key: payload.get(key) for key in keys if key in payload}


def _is_connector_dry_run(payload: Any) -> bool:
    return isinstance(payload, dict) and payload.get("dry_run") is True
