from __future__ import annotations

from typing import Any

from dodo_bridge.analytics_employee_discount import EMPLOYEE_DISCOUNT_TOOL
from dodo_bridge.analytics_kiosk_sales import KIOSK_SALES_SHARE_TOOL
from dodo_bridge.automation.jobs import AutomationJobRegistry
from dodo_bridge.config import Settings
from dodo_bridge.dodo_data import DodoDataService


DODO_API_QUERY_CAPABILITIES = {
    "accounting_sales_summary",
    "accounting_sales_comparison",
    "accounting_writeoffs_products_summary",
    "accounting_slice_writeoff_rate",
    "accounting_slice_daily_dynamics",
    "accounting_sales_channels_summary",
    "accounting_sales_discounts_summary",
    "accounting_inventory_stocks_summary",
    "accounting_stock_consumptions_by_period_summary",
    "ratings_customer_experience_summary",
    "ratings_standards_summary",
    "delivery_courier_productivity_summary",
    "staff_vacancies_count",
    "units_month_goals",
    "orders_clients_statistics",
    "production_productivity",
    "production_orders_handover_time",
}


def build_capabilities_payload(
    service: DodoDataService,
    *,
    mcp_tools: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    dodo_capabilities = _filter_dodo_api_query_capabilities(
        _merge_capabilities(
            service.list_functions(),
            [
                {
                    "name": "accounting_sales_summary",
                    "description": "Compact accounting sales revenue summary by pizzeria.",
                    "tool_name": "dodo_accounting_sales",
                    "enabled": True,
                    "allowed_by_policy": True,
                    "paginated": True,
                }
            ],
        )
    )
    payload: dict[str, Any] = {
        "read_only": True,
        "dodo_capabilities": dodo_capabilities,
        "superset_capabilities": [
            {
                "name": "employee_discount",
                "description": "Employee discount from the approved Superset recipe.",
                "tool_name": EMPLOYEE_DISCOUNT_TOOL,
                "enabled": True,
                "allowed_by_policy": True,
            },
            {
                "name": "kiosk_sales_share",
                "description": "Kiosk sales share from the approved Superset recipe.",
                "tool_name": KIOSK_SALES_SHARE_TOOL,
                "enabled": True,
                "allowed_by_policy": True,
            },
        ],
        "office_manager_capabilities": _office_manager_capabilities(service.settings),
    }
    if mcp_tools is not None:
        payload["mcp_tools"] = [
            {
                "name": tool["name"],
                "description": tool["description"],
            }
            for tool in mcp_tools
        ]
    return payload


def build_agent_status_payload(
    *,
    capabilities: dict[str, Any],
    openapi_operation_count: int,
    openapi_operation_limit: int = 30,
) -> dict[str, Any]:
    dodo_capabilities = _capability_names(capabilities, "dodo_capabilities")
    superset_capabilities = _capability_names(capabilities, "superset_capabilities")
    office_manager_capabilities = _capability_names(capabilities, "office_manager_capabilities")
    openapi_ok = openapi_operation_count <= openapi_operation_limit
    return {
        "status": "ok" if openapi_ok and capabilities.get("read_only") is True else "attention",
        "read_only": True,
        "dodo_is_changed": False,
        "writes": [],
        "openapi": {
            "operation_count": openapi_operation_count,
            "operation_limit": openapi_operation_limit,
            "within_limit": openapi_ok,
        },
        "sources": {
            "dodo_api": {
                "enabled": bool(dodo_capabilities),
                "capability_count": len(dodo_capabilities),
                "capabilities": dodo_capabilities,
            },
            "superset": {
                "enabled": bool(superset_capabilities),
                "capability_count": len(superset_capabilities),
                "capabilities": superset_capabilities,
            },
            "office_manager": {
                "enabled": bool(office_manager_capabilities),
                "capability_count": len(office_manager_capabilities),
                "capabilities": office_manager_capabilities,
                "mode": "read_only_or_dry_run",
            },
        },
        "agent_next_steps": [
            {
                "action": "check_status",
                "tool": "getBridgeAgentStatus",
                "when": "Use first when tool access or routing is uncertain.",
            },
            {
                "action": "select_source",
                "tool": "listDodoPizzerias or source-specific read-only action",
                "when": "Resolve pizzeria, period, metric, and source before querying.",
            },
            {
                "action": "query_read_only_capability",
                "tool": "approved Bridge capability",
                "when": "Run only listed read-only capabilities with user parameters.",
            },
            {
                "action": "report_gap",
                "tool": "reportMissingCapability",
                "when": "Use when no listed read-only capability covers the request.",
            },
        ],
        "message": (
            "Bridge is read-only. Use only listed capabilities; do not call write/admin tools "
            "or invent unavailable data."
        ),
    }


def _office_manager_capabilities(settings: Settings) -> list[dict[str, Any]]:
    return [
        {
            "name": job.name,
            "description": job.description,
            "status": job.status,
            "source": job.source,
            "enabled": True,
            "read_only": True,
            "writes_enabled": job.writes_enabled,
        }
        for job in AutomationJobRegistry().list(settings)
    ]


def _merge_capabilities(
    existing: list[dict[str, Any]],
    additions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_name = {str(item.get("name")): item for item in existing}
    for item in additions:
        by_name.setdefault(str(item.get("name")), item)
    return [by_name[name] for name in sorted(by_name)]


def _filter_dodo_api_query_capabilities(capabilities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        item
        for item in capabilities
        if item.get("name") in DODO_API_QUERY_CAPABILITIES
    ]


def _capability_names(payload: dict[str, Any], key: str) -> list[str]:
    items = payload.get(key, [])
    if not isinstance(items, list):
        return []
    return [
        str(item["name"])
        for item in items
        if isinstance(item, dict) and item.get("name")
    ]
