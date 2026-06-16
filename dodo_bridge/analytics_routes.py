from __future__ import annotations

import json
import time
from typing import Any

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request

from dodo_bridge.analytics_employee_discount import (
    EMPLOYEE_DISCOUNT_CHART_ID,
    EMPLOYEE_DISCOUNT_DASHBOARD_ID,
    EMPLOYEE_DISCOUNT_METRIC,
    EMPLOYEE_DISCOUNT_TOOL,
    EmployeeDiscountRequest,
    build_employee_discount_payload,
    normalize_employee_discount_result,
)
from dodo_bridge.audit import AuditStore
from dodo_bridge.config import Settings, get_settings
from dodo_bridge.connectors.superset import SupersetConnector
from dodo_bridge.models import ToolInvocationRequest
from dodo_bridge.policy import PolicyEngine
from dodo_bridge.registry import ToolRegistry
from dodo_bridge.security import authenticate_actor

router = APIRouter(prefix="/analytics", tags=["analytics"])


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


@router.post("/employee-discount")
async def employee_discount(
    body: EmployeeDiscountRequest,
    settings: Settings = Depends(settings_dep),
    registry: ToolRegistry = Depends(registry_dep),
    policy: PolicyEngine = Depends(policy_dep),
    audit: AuditStore = Depends(audit_dep),
    actor: str = Depends(actor_dep),
) -> dict[str, Any]:
    started = time.perf_counter()
    payload = build_employee_discount_payload(body)
    parameters = {
        "dashboard_id": EMPLOYEE_DISCOUNT_DASHBOARD_ID,
        "chart_id": EMPLOYEE_DISCOUNT_CHART_ID,
        "metric": EMPLOYEE_DISCOUNT_METRIC,
        "body": payload,
    }
    tool = registry.get(EMPLOYEE_DISCOUNT_TOOL)
    decision = policy.evaluate(
        tool,
        ToolInvocationRequest(
            parameters=parameters,
            intent="analytics:get_employee_discount",
            dry_run=body.dry_run,
        ),
        len(json.dumps(parameters, ensure_ascii=False, default=str)),
    )
    if decision.outcome != "allow":
        audit_id = audit.record_event(
            actor=actor,
            intent="analytics:get_employee_discount",
            tool_name=EMPLOYEE_DISCOUNT_TOOL,
            connector="superset",
            decision=decision.outcome,
            reason=decision.reason,
            outcome="blocked",
            params=_audit_params(body),
            latency_ms=int((time.perf_counter() - started) * 1000),
        )
        raise HTTPException(
            status_code=403,
            detail={"audit_id": audit_id, "decision": decision.outcome, "reason": decision.reason},
        )

    try:
        raw = await SupersetConnector(settings).invoke(tool, parameters, body.dry_run)
        if isinstance(raw, dict) and raw.get("dry_run"):
            result = {
                "status": "dry_run",
                "capability_id": "get_employee_discount",
                "source": "Superset",
                "filters": _filters(body),
                "request": raw.get("request"),
                "warnings": [
                    "Superset was not called. Configure SUPERSET_BASE_URL and auth/session for live data."
                ],
            }
        else:
            result = normalize_employee_discount_result(raw, body)
        audit.record_event(
            actor=actor,
            intent="analytics:get_employee_discount",
            tool_name=EMPLOYEE_DISCOUNT_TOOL,
            connector="superset",
            decision=decision.outcome,
            reason=decision.reason,
            outcome="success",
            params=_audit_params(body),
            response_chars=len(json.dumps(result, ensure_ascii=False, default=str)),
            latency_ms=int((time.perf_counter() - started) * 1000),
        )
        return result
    except httpx.HTTPStatusError as exc:
        audit_id = audit.record_event(
            actor=actor,
            intent="analytics:get_employee_discount",
            tool_name=EMPLOYEE_DISCOUNT_TOOL,
            connector="superset",
            decision=decision.outcome,
            reason=decision.reason,
            outcome="error",
            params=_audit_params(body),
            latency_ms=int((time.perf_counter() - started) * 1000),
            error=f"external_http_error:{exc.response.status_code}",
        )
        raise HTTPException(
            status_code=502,
            detail={"audit_id": audit_id, "error": f"external_http_error:{exc.response.status_code}"},
        ) from exc
    except RuntimeError as exc:
        audit_id = audit.record_event(
            actor=actor,
            intent="analytics:get_employee_discount",
            tool_name=EMPLOYEE_DISCOUNT_TOOL,
            connector="superset",
            decision=decision.outcome,
            reason=decision.reason,
            outcome="error",
            params=_audit_params(body),
            latency_ms=int((time.perf_counter() - started) * 1000),
            error=f"superset_connector_error:{type(exc).__name__}",
        )
        raise HTTPException(
            status_code=502,
            detail={
                "audit_id": audit_id,
                "error": "superset_connector_error",
                "message": "Superset request failed. Check bridge audit/logs for details.",
            },
        ) from exc


def _filters(body: EmployeeDiscountRequest) -> dict[str, Any]:
    return {
        "period": {
            "from": body.period.from_date.isoformat(),
            "to": body.period.to_date.isoformat(),
        },
        "unit_names": body.unit_names,
    }


def _audit_params(body: EmployeeDiscountRequest) -> dict[str, Any]:
    return {
        **_filters(body),
        "group_by": body.group_by,
        "row_limit": body.row_limit,
        "dry_run": body.dry_run,
    }
