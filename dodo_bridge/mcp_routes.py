from __future__ import annotations

import json
import time
from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import ValidationError

from dodo_bridge.analytics_employee_discount import (
    EMPLOYEE_DISCOUNT_CHART_ID,
    EMPLOYEE_DISCOUNT_DASHBOARD_ID,
    EMPLOYEE_DISCOUNT_METRIC,
    EMPLOYEE_DISCOUNT_TOOL,
    EmployeeDiscountRequest,
    build_employee_discount_payload,
    normalize_employee_discount_result,
)
from dodo_bridge.analytics_kiosk_sales import (
    KIOSK_SALES_SHARE_CHART_ID,
    KIOSK_SALES_SHARE_DASHBOARD_ID,
    KIOSK_SALES_SHARE_METRIC,
    KIOSK_SALES_SHARE_TOOL,
    KioskSalesShareRequest,
    build_kiosk_sales_share_payload,
    normalize_kiosk_sales_share_result,
)
from dodo_bridge.audit import AuditStore
from dodo_bridge.config import Settings, get_settings
from dodo_bridge.connectors.superset import SupersetConnector
from dodo_bridge.dodo_data import DodoDataService, normalize_units, validate_period
from dodo_bridge.models import ToolInvocationRequest
from dodo_bridge.pizzerias import load_pizzerias
from dodo_bridge.policy import PolicyEngine
from dodo_bridge.registry import ToolRegistry
from dodo_bridge.security import authenticate_actor
from dodo_bridge.system_routes import MissingCapabilityRequest

router = APIRouter(tags=["mcp"])

JSON_RPC_VERSION = "2.0"
MCP_PROTOCOL_VERSION = "2025-11-25"
SERVER_INFO = {"name": "dodo-chatgpt-bridge", "version": "0.1.0"}


def settings_dep() -> Settings:
    return get_settings()


def registry_dep(settings: Settings = Depends(settings_dep)) -> ToolRegistry:
    return ToolRegistry(settings.tool_registry_path)


def policy_dep(settings: Settings = Depends(settings_dep)) -> PolicyEngine:
    return PolicyEngine.from_yaml(settings.policy_path)


def audit_dep(settings: Settings = Depends(settings_dep)) -> AuditStore:
    audit = AuditStore(settings.audit_db_path)
    audit.initialize()
    return audit


def actor_dep(
    request: Request,
    settings: Settings = Depends(settings_dep),
    x_bridge_key: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
    x_actor: str | None = Header(default=None),
) -> str:
    return authenticate_actor(
        request,
        settings,
        x_bridge_key=x_bridge_key,
        authorization=authorization,
        x_actor=x_actor,
    )


def service_dep(
    settings: Settings = Depends(settings_dep),
    registry: ToolRegistry = Depends(registry_dep),
    policy: PolicyEngine = Depends(policy_dep),
) -> DodoDataService:
    return DodoDataService(settings=settings, registry=registry, policy=policy)


@router.post("/mcp", response_model=None)
async def mcp_endpoint(
    body: dict[str, Any],
    service: DodoDataService = Depends(service_dep),
    audit: AuditStore = Depends(audit_dep),
    actor: str = Depends(actor_dep),
) -> Any:
    request_id = body.get("id")
    method = body.get("method")
    params = body.get("params") or {}

    if body.get("jsonrpc") != JSON_RPC_VERSION or not isinstance(method, str):
        return _json_rpc_error(request_id, -32600, "Invalid JSON-RPC request")

    if request_id is None and method == "notifications/initialized":
        return Response(status_code=202)

    if method == "initialize":
        return _json_rpc_result(request_id, _initialize_result(params))
    if method == "tools/list":
        return _json_rpc_result(request_id, _tools_list_result())
    if method == "tools/call":
        return await _handle_tools_call(request_id, params, service=service, audit=audit, actor=actor)

    return _json_rpc_error(request_id, -32601, f"Method not found: {method}")


def _initialize_result(params: dict[str, Any]) -> dict[str, Any]:
    requested_version = params.get("protocolVersion")
    protocol_version = requested_version if isinstance(requested_version, str) else MCP_PROTOCOL_VERSION
    return {
        "protocolVersion": protocol_version,
        "serverInfo": SERVER_INFO,
        "capabilities": {"tools": {}},
        "instructions": (
            "Dodo ChatGPT Bridge MCP adapter is read-only. It exposes only approved "
            "capability router tools and never writes to Dodo IS, Superset, or Office Manager."
        ),
    }


def _tools_list_result() -> dict[str, Any]:
    return {
        "resultType": "complete",
        "tools": _mcp_tools(),
        "cacheScope": "public",
        "ttlMs": 300000,
    }


async def _handle_tools_call(
    request_id: Any,
    params: dict[str, Any],
    *,
    service: DodoDataService,
    audit: AuditStore,
    actor: str,
) -> dict[str, Any]:
    if not isinstance(params, dict):
        return _json_rpc_error(request_id, -32602, "tools/call params must be an object")

    name = params.get("name")
    arguments = params.get("arguments") or {}
    if not isinstance(name, str) or not isinstance(arguments, dict):
        return _json_rpc_error(request_id, -32602, "tools/call requires name and arguments")

    if name not in _mcp_tool_names():
        return _json_rpc_error(request_id, -32602, f"Unknown MCP tool: {name}")

    if name == "list_capabilities":
        return _json_rpc_result(request_id, _tool_result(_list_capabilities(service)))

    if name == "report_missing_capability":
        return _json_rpc_result(
            request_id,
            _tool_result(_report_missing_capability(arguments, audit=audit, actor=actor)),
        )

    if name == "dodo_api_query":
        payload, is_error = await _run_dodo_api_query(arguments, service=service, audit=audit, actor=actor)
        return _json_rpc_result(request_id, _tool_result(payload, is_error=is_error))

    if name == "superset_query":
        payload, is_error = await _run_superset_query(arguments, service=service, audit=audit, actor=actor)
        return _json_rpc_result(request_id, _tool_result(payload, is_error=is_error))

    return _json_rpc_result(request_id, _tool_result(_capability_not_enabled(name, arguments), is_error=True))


def _list_capabilities(service: DodoDataService) -> dict[str, Any]:
    dodo_capabilities = _merge_capabilities(
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
    payload = {
        "read_only": True,
        "mcp_tools": [
            {
                "name": tool["name"],
                "description": tool["description"],
            }
            for tool in _mcp_tools()
        ],
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
    }
    payload["message"] = (
        "Bridge MCP adapter is read-only. Use router tools with approved capability names; "
        "unknown capabilities are rejected or reported as missing."
    )
    return payload


def _merge_capabilities(
    existing: list[dict[str, Any]],
    additions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_name = {str(item.get("name")): item for item in existing}
    for item in additions:
        by_name.setdefault(str(item.get("name")), item)
    return [by_name[name] for name in sorted(by_name)]


def _report_missing_capability(
    arguments: dict[str, Any],
    *,
    audit: AuditStore,
    actor: str,
) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        body = MissingCapabilityRequest.model_validate(arguments)
    except ValidationError as exc:
        return {
            "status": "invalid_arguments",
            "read_only": True,
            "errors": exc.errors(),
        }

    params = body.model_dump(mode="json", by_alias=True)
    audit_id = audit.record_event(
        actor=actor,
        intent="mcp:report_missing_capability",
        tool_name="mcp_report_missing_capability",
        connector="internal",
        decision="allow",
        reason="learning_backlog_entry",
        outcome="success",
        params=params,
        response_chars=0,
        latency_ms=int((time.perf_counter() - started) * 1000),
    )
    period = body.period
    request_id = audit.add_missing_capability(
        actor=actor,
        audit_id=audit_id,
        user_question=body.user_question,
        requested_capability=body.requested_capability,
        desired_output=body.desired_output,
        source_type=body.source_type,
        known_source=body.known_source,
        unit_names=body.unit_names,
        period_from=period.from_date.isoformat() if period and period.from_date else None,
        period_to=period.to_date.isoformat() if period and period.to_date else None,
        priority=body.priority,
        confidence=body.confidence,
        notes=body.notes,
        metadata={"schema_version": 1, "source": "mcp"},
    )
    return {
        "status": "accepted",
        "request_id": request_id,
        "audit_id": audit_id,
        "read_only": True,
        "dodo_is_changed": False,
        "writes": ["bridge_missing_capabilities_backlog"],
        "next_step": "Bridge maintainers should turn this into an approved read-only capability.",
    }


async def _run_dodo_api_query(
    arguments: dict[str, Any],
    *,
    service: DodoDataService,
    audit: AuditStore,
    actor: str,
) -> tuple[dict[str, Any], bool]:
    capability = arguments.get("capability")

    try:
        if capability == "accounting_sales_summary":
            result = await service.fetch_sales_summary(**_sales_summary_query(arguments, service.settings))
            tool_name = "dodo_accounting_sales"
        elif capability == "accounting_writeoffs_products_summary":
            result = await service.fetch_writeoff_products_summary(
                **_writeoff_summary_query(arguments, service.settings)
            )
            tool_name = "dodo_accounting_writeoffs_products"
        elif capability == "accounting_slice_writeoff_rate":
            result = await service.fetch_slice_writeoff_rate(
                **_slice_summary_query(arguments, service.settings)
            )
            tool_name = "dodo_accounting_writeoffs_products+dodo_accounting_sales"
        elif capability == "accounting_slice_daily_dynamics":
            result = await service.fetch_slice_daily_dynamics(
                **_slice_summary_query(arguments, service.settings)
            )
            tool_name = "dodo_accounting_writeoffs_products+dodo_accounting_sales"
        elif capability == "accounting_sales_channels_summary":
            result = await service.fetch_sales_channels_summary(
                **_sales_channels_summary_query(arguments, service.settings)
            )
            tool_name = "dodo_accounting_sales"
        elif capability == "accounting_sales_discounts_summary":
            result = await service.fetch_sales_discounts_summary(
                **_sales_discounts_summary_query(arguments, service.settings)
            )
            tool_name = "dodo_accounting_sales"
        elif capability == "accounting_inventory_stocks_summary":
            result = await service.fetch_inventory_stocks_summary(
                **_inventory_stocks_summary_query(arguments, service.settings)
            )
            tool_name = "dodo_accounting_inventory_stocks"
        elif capability == "accounting_stock_consumptions_by_period_summary":
            result = await service.fetch_stock_consumptions_summary(
                **_stock_consumptions_summary_query(arguments, service.settings)
            )
            tool_name = "dodo_accounting_stock_consumptions_by_period"
        elif capability == "ratings_customer_experience_summary":
            result = await service.fetch_ratings_summary(
                **_ratings_summary_query(arguments, service.settings, capability)
            )
            tool_name = "dodo_controlling_ratings_customer_experience"
        elif capability == "ratings_standards_summary":
            result = await service.fetch_ratings_summary(
                **_ratings_summary_query(arguments, service.settings, capability)
            )
            tool_name = "dodo_controlling_ratings_standards"
        elif capability == "delivery_courier_productivity_summary":
            result = await service.fetch_delivery_courier_productivity_summary(
                **_delivery_productivity_summary_query(arguments, service.settings)
            )
            tool_name = "dodo_delivery_statistics"
        else:
            return _capability_not_enabled("dodo_api_query", arguments), True
    except (ValueError, HTTPException) as exc:
        return {
            "status": "invalid_arguments",
            "read_only": True,
            "capability": capability,
            "message": str(getattr(exc, "detail", exc)),
        }, True

    audit.record_event(
        actor=actor,
        intent=f"mcp:dodo_api_query:{capability}",
        tool_name=tool_name,
        connector="dodo",
        decision="allow",
        reason="mcp_capability_router",
        outcome="success",
        params=arguments,
        response_chars=len(json.dumps(result, ensure_ascii=False, default=str)),
    )
    return result, False


async def _run_superset_query(
    arguments: dict[str, Any],
    *,
    service: DodoDataService,
    audit: AuditStore,
    actor: str,
) -> tuple[dict[str, Any], bool]:
    capability = arguments.get("capability")
    raw_parameters = arguments.get("parameters") or {}
    if not isinstance(raw_parameters, dict):
        return {
            "status": "invalid_arguments",
            "read_only": True,
            "capability": capability,
            "message": "parameters must be an object",
        }, True
    dry_run = bool(arguments.get("dry_run", raw_parameters.get("dry_run", False)))

    try:
        if capability == "employee_discount":
            body = EmployeeDiscountRequest.model_validate({**raw_parameters, "dry_run": dry_run})
            superset_payload = build_employee_discount_payload(body)
            tool_name = EMPLOYEE_DISCOUNT_TOOL
            parameters = {
                "dashboard_id": EMPLOYEE_DISCOUNT_DASHBOARD_ID,
                "chart_id": EMPLOYEE_DISCOUNT_CHART_ID,
                "metric": EMPLOYEE_DISCOUNT_METRIC,
                "body": superset_payload,
            }
            normalizer = normalize_employee_discount_result
        elif capability == "kiosk_sales_share":
            body = KioskSalesShareRequest.model_validate({**raw_parameters, "dry_run": dry_run})
            superset_payload = build_kiosk_sales_share_payload(body)
            tool_name = KIOSK_SALES_SHARE_TOOL
            parameters = {
                "dashboard_id": KIOSK_SALES_SHARE_DASHBOARD_ID,
                "chart_id": KIOSK_SALES_SHARE_CHART_ID,
                "metric": KIOSK_SALES_SHARE_METRIC,
                "body": superset_payload,
            }
            normalizer = normalize_kiosk_sales_share_result
        else:
            return _capability_not_enabled("superset_query", arguments), True
    except ValidationError as exc:
        return {
            "status": "invalid_arguments",
            "read_only": True,
            "capability": capability,
            "errors": exc.errors(),
        }, True

    tool = service.registry.get(tool_name)
    decision = service.policy.evaluate(
        tool,
        ToolInvocationRequest(
            parameters=parameters,
            intent=f"mcp:superset_query:{capability}",
            dry_run=dry_run,
        ),
        len(json.dumps(parameters, ensure_ascii=False, default=str)),
    )
    if decision.outcome != "allow":
        audit_id = audit.record_event(
            actor=actor,
            intent=f"mcp:superset_query:{capability}",
            tool_name=tool_name,
            connector="superset",
            decision=decision.outcome,
            reason=decision.reason,
            outcome="blocked",
            params=arguments,
        )
        return {
            "status": "blocked_by_policy",
            "read_only": True,
            "capability": capability,
            "audit_id": audit_id,
            "decision": decision.outcome,
            "reason": decision.reason,
        }, True

    raw = await SupersetConnector(service.settings).invoke(tool, parameters, dry_run)
    if isinstance(raw, dict) and raw.get("dry_run"):
        result = {
            "status": "dry_run",
            "capability_id": capability,
            "source": "Superset",
            "request": raw.get("request"),
            "warnings": ["Superset was not called because dry_run=true."],
            "read_only": True,
        }
    else:
        result = normalizer(raw, body)
    audit.record_event(
        actor=actor,
        intent=f"mcp:superset_query:{capability}",
        tool_name=tool_name,
        connector="superset",
        decision=decision.outcome,
        reason=decision.reason,
        outcome="success",
        params=arguments,
        response_chars=len(json.dumps(result, ensure_ascii=False, default=str)),
    )
    return result, False


def _sales_summary_query(arguments: dict[str, Any], settings: Settings) -> dict[str, Any]:
    raw_parameters, parameters = _period_query(arguments, settings)
    return {
        "parameters": parameters,
        "dry_run": _dry_run(arguments, raw_parameters),
        "take": raw_parameters.get("take"),
        "max_pages_per_unit": raw_parameters.get("maxPagesPerUnit"),
        "concurrency": raw_parameters.get("concurrency"),
        "cache_mode": str(raw_parameters.get("cacheMode", "auto")),
    }


def _writeoff_summary_query(arguments: dict[str, Any], settings: Settings) -> dict[str, Any]:
    raw_parameters, parameters = _period_query(arguments, settings)
    return {
        "parameters": parameters,
        "dry_run": _dry_run(arguments, raw_parameters),
        "product_name_prefix": str(raw_parameters.get("productNamePrefix", "")),
        "include_products": bool(raw_parameters.get("includeProducts", False)),
        "include_reasons": bool(raw_parameters.get("includeReasons", False)),
        "take": raw_parameters.get("take"),
        "max_pages": _max_pages(raw_parameters),
    }


def _slice_summary_query(arguments: dict[str, Any], settings: Settings) -> dict[str, Any]:
    raw_parameters, parameters = _period_query(arguments, settings)
    return {
        "sales_parameters": parameters,
        "writeoff_parameters": dict(parameters),
        "dry_run": _dry_run(arguments, raw_parameters),
        "product_name_prefix": str(raw_parameters.get("productNamePrefix", "Кус")),
        "include_products": bool(raw_parameters.get("includeProducts", False)),
        "take": raw_parameters.get("take"),
        "max_pages": _max_pages(raw_parameters),
    }


def _sales_channels_summary_query(arguments: dict[str, Any], settings: Settings) -> dict[str, Any]:
    raw_parameters, parameters = _period_query(arguments, settings)
    return {
        "parameters": parameters,
        "dry_run": _dry_run(arguments, raw_parameters),
        "take": raw_parameters.get("take"),
        "max_pages_per_unit": raw_parameters.get("maxPagesPerUnit"),
        "concurrency": raw_parameters.get("concurrency"),
    }


def _sales_discounts_summary_query(arguments: dict[str, Any], settings: Settings) -> dict[str, Any]:
    raw_parameters, parameters = _period_query(arguments, settings)
    return {
        "parameters": parameters,
        "dry_run": _dry_run(arguments, raw_parameters),
        "include_actions": bool(raw_parameters.get("includeActions", False)),
        "top_actions_limit": int(raw_parameters.get("topActionsLimit", 10)),
        "take": raw_parameters.get("take"),
        "max_pages_per_unit": raw_parameters.get("maxPagesPerUnit"),
        "concurrency": raw_parameters.get("concurrency"),
    }


def _inventory_stocks_summary_query(arguments: dict[str, Any], settings: Settings) -> dict[str, Any]:
    raw_parameters, parameters = _period_query(arguments, settings, exclusive_to=False)
    return {
        "parameters": parameters,
        "dry_run": _dry_run(arguments, raw_parameters),
        "low_stock_days_threshold": float(raw_parameters.get("lowStockDaysThreshold", 3.0)),
        "high_stock_days_threshold": float(raw_parameters.get("highStockDaysThreshold", 21.0)),
        "top_limit": int(raw_parameters.get("topLimit", 10)),
        "take": raw_parameters.get("take"),
        "max_pages": _max_pages(raw_parameters),
    }


def _stock_consumptions_summary_query(arguments: dict[str, Any], settings: Settings) -> dict[str, Any]:
    raw_parameters, parameters = _period_query(arguments, settings, exclusive_to=True)
    return {
        "parameters": parameters,
        "dry_run": _dry_run(arguments, raw_parameters),
        "top_limit": int(raw_parameters.get("topLimit", 10)),
        "take": raw_parameters.get("take"),
        "max_pages": _max_pages(raw_parameters),
    }


def _ratings_summary_query(
    arguments: dict[str, Any],
    settings: Settings,
    function_name: str,
) -> dict[str, Any]:
    raw_parameters = arguments.get("parameters") or {}
    if not isinstance(raw_parameters, dict):
        raise ValueError("parameters must be an object")

    parameters: dict[str, Any] = {}
    units = raw_parameters.get("units")
    if units:
        parameters["units"] = _units_or_all_pizzerias(settings, units)
    country_code = raw_parameters.get("countryCode", raw_parameters.get("country_code"))
    if country_code is not None:
        parameters["countryCode"] = int(country_code)
    if not parameters:
        parameters["units"] = _units_or_all_pizzerias(settings, None)

    return {
        "function_name": function_name,
        "parameters": parameters,
        "dry_run": _dry_run(arguments, raw_parameters),
        "low_rate_threshold": float(raw_parameters.get("lowRateThreshold", 80.0)),
        "top_limit": int(raw_parameters.get("topLimit", 5)),
        "take": raw_parameters.get("take"),
        "max_pages": _max_pages(raw_parameters),
    }


def _delivery_productivity_summary_query(arguments: dict[str, Any], settings: Settings) -> dict[str, Any]:
    raw_parameters, parameters = _period_query(arguments, settings, exclusive_to=True)
    return {
        "parameters": parameters,
        "dry_run": _dry_run(arguments, raw_parameters),
        "top_limit": int(raw_parameters.get("topLimit", 5)),
    }


def _period_query(
    arguments: dict[str, Any],
    settings: Settings,
    *,
    exclusive_to: bool = True,
) -> tuple[dict[str, Any], dict[str, str]]:
    raw_parameters = arguments.get("parameters") or {}
    if not isinstance(raw_parameters, dict):
        raise ValueError("parameters must be an object")

    from_date = _required_date(raw_parameters, "from")
    to_date = _required_date(raw_parameters, "to")
    validate_period(from_date, to_date, settings)

    parameters = {
        "units": _units_or_all_pizzerias(settings, raw_parameters.get("units")),
        "from": from_date.isoformat(),
        "to": (to_date + timedelta(days=1) if exclusive_to else to_date).isoformat(),
    }
    return raw_parameters, parameters


def _dry_run(arguments: dict[str, Any], raw_parameters: dict[str, Any]) -> bool:
    return bool(arguments.get("dry_run", raw_parameters.get("dry_run", False)))


def _max_pages(raw_parameters: dict[str, Any]) -> Any:
    return raw_parameters.get("max_pages", raw_parameters.get("maxPages"))


def _required_date(parameters: dict[str, Any], key: str) -> date:
    value = parameters.get(key)
    if not isinstance(value, str):
        raise ValueError(f"parameters.{key} is required in YYYY-MM-DD format")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"parameters.{key} must be in YYYY-MM-DD format") from exc


def _units_or_all_pizzerias(settings: Settings, units: Any) -> str:
    if isinstance(units, str) and units.strip():
        return normalize_units(units)
    if isinstance(units, list):
        joined = ",".join(str(item) for item in units if str(item).strip())
        if joined:
            return normalize_units(joined)

    pizzerias = load_pizzerias(settings.dodo_pizzerias_path).get("pizzerias", [])
    unit_ids = [str(item["unit_id"]) for item in pizzerias if item.get("unit_id")]
    if not unit_ids:
        raise ValueError("parameters.units is required when DODO_PIZZERIAS_PATH is not configured")
    return ",".join(unit_ids)


def _capability_not_enabled(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "capability_not_enabled",
        "read_only": True,
        "tool": tool_name,
        "capability": arguments.get("capability"),
        "message": (
            "This MCP router accepts only capabilities explicitly mapped in Bridge code. "
            "No arbitrary Dodo API, Superset, Office Manager, URL, SQL, JavaScript, or write action was executed."
        ),
    }


def _tool_result(payload: dict[str, Any], *, is_error: bool = False) -> dict[str, Any]:
    return {
        "resultType": "complete",
        "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, default=str)}],
        "structuredContent": payload,
        "isError": is_error,
    }


def _json_rpc_result(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": JSON_RPC_VERSION, "id": request_id, "result": result}


def _json_rpc_error(
    request_id: Any,
    code: int,
    message: str,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": JSON_RPC_VERSION, "id": request_id, "error": error}


def _mcp_tool_names() -> set[str]:
    return {tool["name"] for tool in _mcp_tools()}


def _mcp_tools() -> list[dict[str, Any]]:
    return [
        {
            "name": "list_capabilities",
            "title": "List Bridge Capabilities",
            "description": "List read-only Bridge capabilities and router tools.",
            "inputSchema": {"type": "object", "additionalProperties": False},
            "annotations": _read_only_annotations(),
        },
        {
            "name": "dodo_api_query",
            "title": "Dodo API Read-Only Query",
            "description": "Run an approved read-only Dodo API capability by name.",
            "inputSchema": _capability_query_schema(),
            "annotations": _read_only_annotations(),
        },
        {
            "name": "superset_query",
            "title": "Superset Read-Only Query",
            "description": "Run an approved read-only Superset capability by name.",
            "inputSchema": _capability_query_schema(),
            "annotations": _read_only_annotations(),
        },
        {
            "name": "office_manager_query",
            "title": "Office Manager Read-Only Query",
            "description": "Run an approved read-only Office Manager extraction capability by name.",
            "inputSchema": _capability_query_schema(),
            "annotations": _read_only_annotations(),
        },
        {
            "name": "report_missing_capability",
            "title": "Report Missing Bridge Capability",
            "description": "Record a missing read-only capability in the internal Bridge backlog.",
            "inputSchema": _missing_capability_schema(),
            "annotations": _read_only_annotations(),
        },
    ]


def _read_only_annotations() -> dict[str, bool]:
    return {
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }


def _capability_query_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "capability": {
                "type": "string",
                "description": "Approved Bridge capability name from list_capabilities.",
            },
            "parameters": {
                "type": "object",
                "description": "Capability-specific parameters. Arbitrary URLs, SQL, and code are not accepted.",
                "additionalProperties": True,
            },
            "dry_run": {
                "type": "boolean",
                "description": "When true, plan the approved read-only request without calling the source.",
                "default": False,
            },
        },
        "required": ["capability"],
        "additionalProperties": False,
    }


def _missing_capability_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "user_question": {"type": "string", "minLength": 3, "maxLength": 2000},
            "requested_capability": {"type": "string", "minLength": 3, "maxLength": 200},
            "desired_output": {"type": "string", "maxLength": 1000},
            "source_type": {
                "type": "string",
                "enum": ["dodo_api", "superset", "web_interface", "google_sheet", "unknown", "other"],
                "default": "unknown",
            },
            "known_source": {"type": "string", "maxLength": 500},
            "unit_names": {"type": "array", "items": {"type": "string"}, "maxItems": 20},
            "period": {
                "type": "object",
                "properties": {
                    "from": {"type": "string", "format": "date"},
                    "to": {"type": "string", "format": "date"},
                },
                "additionalProperties": False,
            },
            "priority": {"type": "string", "enum": ["low", "normal", "high"], "default": "normal"},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.5},
            "notes": {"type": "string", "maxLength": 2000},
        },
        "required": ["user_question", "requested_capability"],
        "additionalProperties": False,
    }
