from __future__ import annotations

import json
import time
from typing import Any

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request

from dodo_bridge.audit import AuditStore
from dodo_bridge.analytics_routes import router as analytics_router
from dodo_bridge.auth_routes import router as dodo_auth_router
from dodo_bridge.config import Settings, get_settings
from dodo_bridge.connectors.dodo import DodoConnector
from dodo_bridge.connectors.superset import SupersetConnector
from dodo_bridge.dodo_data_routes import router as dodo_data_router
from dodo_bridge.learning import LearningEngine
from dodo_bridge.models import (
    ConnectorName,
    FeedbackRequest,
    ToolInvocationRequest,
    ToolInvocationResult,
)
from dodo_bridge.policy import PolicyEngine
from dodo_bridge.registry import ToolRegistry
from dodo_bridge.security import authenticate_actor

app = FastAPI(title="Dodo ChatGPT Bridge", version="0.1.0")
app.include_router(analytics_router)
app.include_router(dodo_auth_router)
app.include_router(dodo_data_router)


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


@app.get("/health")
def health(settings: Settings = Depends(settings_dep)) -> dict[str, Any]:
    return {
        "status": "ok",
        "tool_registry_path": str(settings.tool_registry_path),
        "policy_path": str(settings.policy_path),
    }


@app.get("/tools")
def list_tools(
    registry: ToolRegistry = Depends(registry_dep),
    policy: PolicyEngine = Depends(policy_dep),
    actor: str = Depends(actor_dep),
) -> dict[str, Any]:
    del actor
    tools = []
    for tool in registry.list_tools():
        tools.append(
            {
                **tool.model_dump(mode="json"),
                "allowed_by_policy": "*" in policy.config.allowed_tools
                or tool.name in policy.config.allowed_tools,
            }
        )
    return {"tools": tools, "policy": policy.config.model_dump(mode="json")}


@app.post("/tools/{tool_name}/invoke", response_model=ToolInvocationResult)
async def invoke_tool(
    tool_name: str,
    body: ToolInvocationRequest,
    settings: Settings = Depends(settings_dep),
    registry: ToolRegistry = Depends(registry_dep),
    policy: PolicyEngine = Depends(policy_dep),
    audit: AuditStore = Depends(audit_dep),
    actor: str = Depends(actor_dep),
) -> ToolInvocationResult:
    started = time.perf_counter()
    actor_name = body.actor or actor
    params_json = json.dumps(body.parameters, ensure_ascii=False, default=str)
    tool = registry.get(tool_name)
    decision = policy.evaluate(tool, body, len(params_json))
    connector_name = tool.connector.value if tool else None

    if decision.outcome != "allow":
        audit_id = audit.record_event(
            actor=actor_name,
            intent=body.intent,
            tool_name=tool_name,
            connector=connector_name,
            decision=decision.outcome,
            reason=decision.reason,
            outcome="blocked",
            params=body.parameters,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )
        status_code = 409 if decision.outcome == "approval_required" else 403
        raise HTTPException(
            status_code=status_code,
            detail={
                "audit_id": audit_id,
                "decision": decision.outcome,
                "reason": decision.reason,
            },
        )

    try:
        result = await _dispatch(settings, tool, body.parameters, body.dry_run)
        result = _truncate_result(result, tool.max_response_chars or policy.config.max_response_chars)
        response_chars = len(json.dumps(result, ensure_ascii=False, default=str))
        audit_id = audit.record_event(
            actor=actor_name,
            intent=body.intent,
            tool_name=tool_name,
            connector=connector_name,
            decision=decision.outcome,
            reason=decision.reason,
            outcome="success",
            params=body.parameters,
            response_chars=response_chars,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )
        return ToolInvocationResult(
            audit_id=audit_id,
            tool_name=tool_name,
            decision=decision.outcome,
            result=result,
        )
    except httpx.HTTPStatusError as exc:
        error = f"external_http_error:{exc.response.status_code}"
        audit_id = audit.record_event(
            actor=actor_name,
            intent=body.intent,
            tool_name=tool_name,
            connector=connector_name,
            decision=decision.outcome,
            reason=decision.reason,
            outcome="error",
            params=body.parameters,
            latency_ms=int((time.perf_counter() - started) * 1000),
            error=error,
        )
        raise HTTPException(status_code=502, detail={"audit_id": audit_id, "error": error}) from exc
    except Exception as exc:
        audit_id = audit.record_event(
            actor=actor_name,
            intent=body.intent,
            tool_name=tool_name,
            connector=connector_name,
            decision=decision.outcome,
            reason=decision.reason,
            outcome="error",
            params=body.parameters,
            latency_ms=int((time.perf_counter() - started) * 1000),
            error=str(exc),
        )
        raise HTTPException(status_code=500, detail={"audit_id": audit_id, "error": str(exc)}) from exc


@app.post("/feedback")
def add_feedback(
    body: FeedbackRequest,
    audit: AuditStore = Depends(audit_dep),
    actor: str = Depends(actor_dep),
) -> dict[str, Any]:
    del actor
    feedback_id = audit.add_feedback(
        audit_id=body.audit_id,
        score=body.score,
        comment=body.comment,
        labels=body.labels,
    )
    return {"feedback_id": feedback_id}


@app.get("/learning/recommendations")
def learning_recommendations(
    audit: AuditStore = Depends(audit_dep),
    policy: PolicyEngine = Depends(policy_dep),
    actor: str = Depends(actor_dep),
) -> dict[str, Any]:
    del actor
    engine = LearningEngine(audit, policy.config)
    return {"recommendations": [item.model_dump() for item in engine.recommendations()]}


async def _dispatch(
    settings: Settings,
    tool: Any,
    parameters: dict[str, Any],
    dry_run: bool,
) -> Any:
    if tool.connector == ConnectorName.DODO:
        return await DodoConnector(settings).invoke(tool, parameters, dry_run)
    if tool.connector == ConnectorName.SUPERSET:
        return await SupersetConnector(settings).invoke(tool, parameters, dry_run)
    return {"dry_run": True, "message": "internal connector has no executable tools yet"}


def _truncate_result(result: Any, limit: int) -> Any:
    encoded = json.dumps(result, ensure_ascii=False, default=str)
    if len(encoded) <= limit:
        return result
    return {
        "truncated": True,
        "max_response_chars": limit,
        "preview": encoded[:limit],
    }
