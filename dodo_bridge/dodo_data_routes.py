from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Header, Query, Request

from dodo_bridge.audit import AuditStore
from dodo_bridge.config import Settings, get_settings
from dodo_bridge.dodo_data import (
    DodoDataService,
    normalize_units,
    parse_fields,
    validate_period,
)
from dodo_bridge.policy import PolicyEngine
from dodo_bridge.registry import ToolRegistry
from dodo_bridge.security import authenticate_actor

router = APIRouter(prefix="/dodo", tags=["dodo-data"])


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


class RouteContext:
    def __init__(
        self,
        settings: Settings = Depends(settings_dep),
        service: DodoDataService = Depends(service_dep),
        audit: AuditStore = Depends(audit_dep),
        actor: str = Depends(actor_dep),
    ):
        self.settings = settings
        self.service = service
        self.audit = audit
        self.actor = actor


@router.get("/functions")
def list_dodo_functions(
    service: DodoDataService = Depends(service_dep),
    actor: str = Depends(actor_dep),
) -> dict[str, Any]:
    del actor
    return {"functions": service.list_functions()}


@router.get("/delivery/courier-orders")
async def courier_orders(
    units: str = Query(..., description="Comma-separated Dodo unit ids."),
    from_date: date = Query(..., alias="from"),
    to_date: date = Query(..., alias="to"),
    fields: str | None = Query(default=None, description="Optional comma-separated row fields."),
    take: int | None = Query(default=None, ge=1),
    max_pages: int | None = Query(default=None, ge=1),
    dry_run: bool = Query(default=False),
    context: RouteContext = Depends(),
) -> dict[str, Any]:
    params = _period_params(context.settings, units, from_date, to_date)
    return await _fetch(
        context,
        function_name="courier_orders",
        parameters=params,
        dry_run=dry_run,
        fields=fields,
        take=take,
        max_pages=max_pages,
    )


@router.get("/staff/shifts")
async def staff_shifts(
    units: str = Query(..., description="Comma-separated Dodo unit ids."),
    from_date: date = Query(..., alias="from"),
    to_date: date = Query(..., alias="to"),
    staff_type_name: str = Query(default="Courier", alias="staffTypeName"),
    fields: str | None = Query(default=None, description="Optional comma-separated row fields."),
    take: int | None = Query(default=None, ge=1),
    max_pages: int | None = Query(default=None, ge=1),
    dry_run: bool = Query(default=False),
    context: RouteContext = Depends(),
) -> dict[str, Any]:
    validate_period(from_date, to_date, context.settings)
    params = {
        "units": normalize_units(units),
        "clockInFrom": from_date.isoformat(),
        "clockInTo": to_date.isoformat(),
        "staffTypeName": staff_type_name,
    }
    return await _fetch(
        context,
        function_name="staff_shifts",
        parameters=params,
        dry_run=dry_run,
        fields=fields,
        take=take,
        max_pages=max_pages,
    )


@router.get("/delivery/statistics")
async def delivery_statistics(
    units: str = Query(..., description="Comma-separated Dodo unit ids."),
    from_date: date = Query(..., alias="from"),
    to_date: date = Query(..., alias="to"),
    fields: str | None = Query(default=None, description="Optional comma-separated row fields."),
    dry_run: bool = Query(default=False),
    context: RouteContext = Depends(),
) -> dict[str, Any]:
    params = _period_params(context.settings, units, from_date, to_date)
    return await _fetch(
        context,
        function_name="delivery_statistics",
        parameters=params,
        dry_run=dry_run,
        fields=fields,
        take=None,
        max_pages=None,
    )


@router.get("/accounting/sales")
async def accounting_sales(
    units: str = Query(..., description="Comma-separated Dodo unit ids."),
    from_date: date = Query(..., alias="from"),
    to_date: date = Query(..., alias="to"),
    fields: str | None = Query(default=None, description="Optional comma-separated row fields."),
    take: int | None = Query(default=None, ge=1),
    max_pages: int | None = Query(default=None, ge=1),
    dry_run: bool = Query(default=False),
    context: RouteContext = Depends(),
) -> dict[str, Any]:
    params = _period_params(context.settings, units, from_date, to_date)
    return await _fetch(
        context,
        function_name="accounting_sales",
        parameters=params,
        dry_run=dry_run,
        fields=fields,
        take=take,
        max_pages=max_pages,
    )


@router.get("/accounting/writeoffs/products")
async def accounting_writeoffs_products(
    units: str = Query(..., description="Comma-separated Dodo unit ids."),
    from_date: date = Query(..., alias="from"),
    to_date: date = Query(..., alias="to"),
    fields: str | None = Query(default=None, description="Optional comma-separated row fields."),
    take: int | None = Query(default=None, ge=1),
    max_pages: int | None = Query(default=None, ge=1),
    dry_run: bool = Query(default=False),
    context: RouteContext = Depends(),
) -> dict[str, Any]:
    params = _period_params(context.settings, units, from_date, to_date)
    return await _fetch(
        context,
        function_name="accounting_writeoffs_products",
        parameters=params,
        dry_run=dry_run,
        fields=fields,
        take=take,
        max_pages=max_pages,
    )


def _period_params(
    settings: Settings,
    units: str,
    from_date: date,
    to_date: date,
) -> dict[str, Any]:
    validate_period(from_date, to_date, settings)
    return {
        "units": normalize_units(units),
        "from": from_date.isoformat(),
        "to": to_date.isoformat(),
    }


async def _fetch(
    context: RouteContext,
    *,
    function_name: str,
    parameters: dict[str, Any],
    dry_run: bool,
    fields: str | None,
    take: int | None,
    max_pages: int | None,
) -> dict[str, Any]:
    result = await context.service.fetch(
        function_name=function_name,
        parameters=parameters,
        dry_run=dry_run,
        fields=parse_fields(fields),
        take=take,
        max_pages=max_pages,
    )
    context.audit.record_event(
        actor=context.actor,
        intent=f"dodo_data:{function_name}",
        tool_name=result.get("tool_name", function_name),
        connector="dodo",
        decision="allow",
        reason="dodo_data_route",
        outcome="success",
        params={
            **parameters,
            "dry_run": dry_run,
            "fields": fields,
            "take": take,
            "max_pages": max_pages,
        },
        response_chars=len(str(result)),
    )
    return result
