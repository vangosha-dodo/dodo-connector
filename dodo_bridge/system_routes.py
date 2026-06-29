from __future__ import annotations

import time
from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, Field, field_validator

from dodo_bridge.audit import AuditStore
from dodo_bridge.capabilities import build_agent_status_payload, build_capabilities_payload
from dodo_bridge.config import Settings, get_settings
from dodo_bridge.dodo_data import DodoDataService
from dodo_bridge.policy import PolicyEngine
from dodo_bridge.registry import ToolRegistry
from dodo_bridge.security import authenticate_actor
from scripts.export_chatgpt_openapi import build_schema

router = APIRouter(prefix="/system", tags=["system"])
HTTP_METHODS = {"get", "put", "post", "delete", "patch", "head", "options", "trace"}


class MissingCapabilityPeriod(BaseModel):
    from_date: date | None = Field(default=None, alias="from")
    to_date: date | None = Field(default=None, alias="to")


class MissingCapabilityRequest(BaseModel):
    user_question: str = Field(min_length=3, max_length=2000)
    requested_capability: str = Field(min_length=3, max_length=200)
    desired_output: str | None = Field(default=None, max_length=1000)
    source_type: Literal[
        "dodo_api",
        "superset",
        "web_interface",
        "google_sheet",
        "unknown",
        "other",
    ] = "unknown"
    known_source: str | None = Field(default=None, max_length=500)
    unit_names: list[str] = Field(default_factory=list, max_length=20)
    period: MissingCapabilityPeriod | None = None
    priority: Literal["low", "normal", "high"] = "normal"
    confidence: float = Field(default=0.5, ge=0, le=1)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("unit_names")
    @classmethod
    def clean_unit_names(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item and item.strip()]


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


def service_dep(
    settings: Settings = Depends(settings_dep),
    registry: ToolRegistry = Depends(registry_dep),
    policy: PolicyEngine = Depends(policy_dep),
) -> DodoDataService:
    return DodoDataService(settings=settings, registry=registry, policy=policy)


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


@router.get("/agent-status")
def agent_status(
    service: DodoDataService = Depends(service_dep),
    actor: str = Depends(actor_dep),
) -> dict[str, Any]:
    del actor
    capabilities = build_capabilities_payload(service)
    return build_agent_status_payload(
        capabilities=capabilities,
        openapi_operation_count=_openapi_operation_count(),
    )


@router.post("/missing-capability")
def report_missing_capability(
    body: MissingCapabilityRequest,
    audit: AuditStore = Depends(audit_dep),
    actor: str = Depends(actor_dep),
) -> dict[str, Any]:
    started = time.perf_counter()
    params = body.model_dump(mode="json", by_alias=True)
    audit_id = audit.record_event(
        actor=actor,
        intent="system:report_missing_capability",
        tool_name="system_missing_capability",
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
        metadata={"schema_version": 1},
    )
    result = {
        "status": "accepted",
        "request_id": request_id,
        "audit_id": audit_id,
        "dodo_is_changed": False,
        "writes": ["bridge_missing_capabilities_backlog"],
        "next_step": (
            "Bridge maintainers should turn this backlog entry into an approved read-only "
            "recipe before the agent uses it for live Dodo IS data."
        ),
    }
    return result


def _openapi_operation_count() -> int:
    schema = build_schema("https://bridge.local")
    paths = schema.get("paths", {})
    if not isinstance(paths, dict):
        return 0
    return sum(
        1
        for path_item in paths.values()
        if isinstance(path_item, dict)
        for method in path_item
        if method.lower() in HTTP_METHODS
    )
