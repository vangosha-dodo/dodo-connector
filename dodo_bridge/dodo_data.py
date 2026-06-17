from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any

import httpx
from fastapi import HTTPException

from dodo_bridge.config import Settings
from dodo_bridge.connectors.dodo import DodoConnector
from dodo_bridge.models import ToolInvocationRequest, ToolSpec
from dodo_bridge.policy import PolicyEngine
from dodo_bridge.registry import ToolRegistry


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
    "accounting_sales": DodoDataFunction(
        name="accounting_sales",
        tool_name="dodo_accounting_sales",
        description="Accounting sales rows.",
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
    "accounting_inventory_stocks": DodoDataFunction(
        name="accounting_inventory_stocks",
        tool_name="dodo_accounting_inventory_stocks",
        description="Inventory stock balance rows.",
        row_keys=("stocks", "inventoryStocks", "items"),
    ),
    "accounting_stock_consumptions_by_period": DodoDataFunction(
        name="accounting_stock_consumptions_by_period",
        tool_name="dodo_accounting_stock_consumptions_by_period",
        description="Stock consumption rows by period.",
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
    "ratings_standards": DodoDataFunction(
        name="ratings_standards",
        tool_name="dodo_controlling_ratings_standards",
        description="Standards ratings by unit or country.",
        row_keys=("unitRates", "ratings", "items"),
        meta_keys=("periodFrom", "periodTo", "publishStatus", "publishedAt"),
    ),
}

WRITEOFF_PRODUCT_SUMMARY_FIELDS = [
    "unitName",
    "productName",
    "quantity",
    "pricePerPiece",
    "reason",
]


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
                    "row_count": None,
                    "rows_key": None,
                    "pages_fetched": pages_fetched,
                    "rows": None,
                    "response": payload,
                }

            rows_key = rows_key or current_key
            pages_fetched += 1
            all_rows.extend(project_rows(rows, fields))
            if len(rows) < take_value:
                break

        if pages_fetched >= max_pages_value:
            truncated = True

        return {
            "function": function.name,
            "tool_name": tool.name,
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
    elif payload:
        detail["external_body_preview"] = str(payload)[:500]

    return detail


def extract_meta(payload: Any, keys: tuple[str, ...]) -> dict[str, Any]:
    if not keys or not isinstance(payload, dict):
        return {}
    return {key: payload.get(key) for key in keys if key in payload}


def _is_connector_dry_run(payload: Any) -> bool:
    return isinstance(payload, dict) and payload.get("dry_run") is True
