from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any

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
}


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
            payload = await self.connector.invoke(tool, base_params, dry_run=False)
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
            return {
                "function": function.name,
                "tool_name": tool.name,
                "rows_key": rows_key,
                "row_count": len(projected),
                "rows": projected,
            }

        all_rows: list[Any] = []
        rows_key: str | None = None
        pages_fetched = 0
        truncated = False
        for page in range(max_pages_value):
            page_params = dict(base_params)
            page_params["skip"] = page * take_value
            page_params["take"] = take_value
            payload = await self.connector.invoke(tool, page_params, dry_run=False)
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
                    "row_count": None,
                    "rows_key": None,
                    "pages_fetched": pages_fetched,
                    "response": payload,
                }

            rows_key = rows_key or current_key
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
            "rows_key": rows_key,
            "row_count": len(projected),
            "pages_fetched": pages_fetched,
            "truncated": truncated,
            "next_skip": pages_fetched * take_value if truncated else None,
            "rows": projected,
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


def _is_connector_dry_run(payload: Any) -> bool:
    return isinstance(payload, dict) and payload.get("dry_run") is True

