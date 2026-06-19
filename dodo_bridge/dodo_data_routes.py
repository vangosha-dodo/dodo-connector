from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

from dodo_bridge.audit import AuditStore
from dodo_bridge.config import Settings, get_settings
from dodo_bridge.dodo_data import (
    DodoDataService,
    normalize_units,
    parse_fields,
    validate_period,
)
from dodo_bridge.pizzerias import load_pizzerias
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


@router.get("/pizzerias")
def list_pizzerias(
    search: str | None = Query(default=None, description="Optional name, alias, or unit id search."),
    query: str | None = Query(default=None, description="Alias for search."),
    include_non_pizzerias: bool = Query(
        default=False,
        description="When true, include office/production units from the same Dodo roles-units catalog.",
    ),
    settings: Settings = Depends(settings_dep),
    actor: str = Depends(actor_dep),
) -> dict[str, Any]:
    del actor
    return load_pizzerias(
        settings.dodo_pizzerias_path,
        search=search or query,
        include_non_pizzerias=include_non_pizzerias,
    )


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


@router.get("/staff/vacancies/count")
async def staff_vacancies_count(
    units: str | None = Query(default=None, description="Optional comma-separated Dodo unit ids."),
    country_code: int | None = Query(
        default=None,
        alias="countryCode",
        description="Optional Dodo country code for country-level vacancy counts.",
    ),
    fields: str | None = Query(default=None, description="Optional comma-separated row fields."),
    take: int | None = Query(default=None, ge=1),
    max_pages: int | None = Query(default=None, ge=1),
    dry_run: bool = Query(default=False),
    context: RouteContext = Depends(),
) -> dict[str, Any]:
    params = _optional_unit_country_params(units=units, country_code=country_code)
    return await _fetch(
        context,
        function_name="staff_vacancies_count",
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


@router.get("/orders/clients-statistics")
async def orders_clients_statistics(
    units: str | None = Query(
        default=None,
        description="Optional comma-separated Dodo unit ids. Omit for all configured pizzerias.",
    ),
    from_date: date = Query(..., alias="from"),
    to_date: date = Query(..., alias="to"),
    fields: str | None = Query(default=None, description="Optional comma-separated row fields."),
    take: int | None = Query(default=None, ge=1),
    max_pages: int | None = Query(default=None, ge=1),
    dry_run: bool = Query(default=False),
    context: RouteContext = Depends(),
) -> dict[str, Any]:
    params = _date_params(
        context.settings,
        _units_or_all_pizzerias(context.settings, units),
        from_date,
        to_date,
        from_key="fromDate",
        to_key="toDate",
    )
    return await _fetch_scope_aware(
        context,
        function_name="orders_clients_statistics",
        parameters=params,
        dry_run=dry_run,
        fields=fields,
        take=take,
        max_pages=max_pages,
    )


@router.get("/production/productivity")
async def production_productivity(
    units: str | None = Query(
        default=None,
        description="Optional comma-separated Dodo unit ids. Omit for all configured pizzerias.",
    ),
    from_date: date = Query(..., alias="from"),
    to_date: date = Query(..., alias="to"),
    fields: str | None = Query(default=None, description="Optional comma-separated row fields."),
    take: int | None = Query(default=None, ge=1),
    max_pages: int | None = Query(default=None, ge=1),
    dry_run: bool = Query(default=False),
    context: RouteContext = Depends(),
) -> dict[str, Any]:
    params = _period_params(
        context.settings,
        _units_or_all_pizzerias(context.settings, units),
        from_date,
        to_date,
    )
    return await _fetch_scope_aware(
        context,
        function_name="production_productivity",
        parameters=params,
        dry_run=dry_run,
        fields=fields,
        take=take,
        max_pages=max_pages,
    )


@router.get("/production/orders-handover-time")
async def production_orders_handover_time(
    units: str | None = Query(
        default=None,
        description="Optional comma-separated Dodo unit ids. Omit for all configured pizzerias.",
    ),
    from_date: date = Query(..., alias="from"),
    to_date: date = Query(..., alias="to"),
    fields: str | None = Query(default=None, description="Optional comma-separated row fields."),
    take: int | None = Query(default=None, ge=1),
    max_pages: int | None = Query(default=None, ge=1),
    dry_run: bool = Query(default=False),
    context: RouteContext = Depends(),
) -> dict[str, Any]:
    params = _period_params(
        context.settings,
        _units_or_all_pizzerias(context.settings, units),
        from_date,
        to_date,
    )
    return await _fetch_scope_aware(
        context,
        function_name="production_orders_handover_time",
        parameters=params,
        dry_run=dry_run,
        fields=fields,
        take=take,
        max_pages=max_pages,
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
    params = _period_params(context.settings, units, from_date, to_date, exclusive_to=True)
    return await _fetch(
        context,
        function_name="accounting_sales",
        parameters=params,
        dry_run=dry_run,
        fields=fields,
        take=take,
        max_pages=max_pages,
    )


@router.get("/accounting/sales/summary")
async def accounting_sales_summary(
    units: str | None = Query(
        default=None,
        description="Optional comma-separated Dodo unit ids. Omit for all configured pizzerias.",
    ),
    from_date: date = Query(..., alias="from"),
    to_date: date = Query(..., alias="to"),
    take: int | None = Query(default=None, ge=1),
    max_pages_per_unit: int | None = Query(default=None, alias="maxPagesPerUnit", ge=1),
    concurrency: int | None = Query(default=None, ge=1, le=8),
    cache_mode: str = Query(
        default="auto",
        alias="cacheMode",
        pattern="^(auto|refresh|bypass)$",
        description="auto uses cached daily summaries and fills misses; refresh recalculates and stores; bypass ignores cache.",
    ),
    dry_run: bool = Query(default=False),
    context: RouteContext = Depends(),
) -> dict[str, Any]:
    params = _period_params(
        context.settings,
        _units_or_all_pizzerias(context.settings, units),
        from_date,
        to_date,
        exclusive_to=True,
    )
    result = await context.service.fetch_sales_summary(
        parameters=params,
        dry_run=dry_run,
        take=take,
        max_pages_per_unit=max_pages_per_unit,
        concurrency=concurrency,
        cache_mode=cache_mode,
    )
    _record_dodo_audit(
        context,
        function_name="accounting_sales_summary",
        parameters={**params, "cacheMode": cache_mode},
        dry_run=dry_run,
        fields=None,
        take=take,
        max_pages=max_pages_per_unit,
        result=result,
    )
    return result


@router.get("/accounting/sales/comparison")
async def accounting_sales_comparison(
    units: str | None = Query(
        default=None,
        description="Optional comma-separated Dodo unit ids. Omit for all configured pizzerias.",
    ),
    from_date: date = Query(..., alias="from"),
    to_date: date = Query(..., alias="to"),
    compare_from_date: date = Query(..., alias="compareFrom"),
    compare_to_date: date = Query(..., alias="compareTo"),
    take: int | None = Query(default=None, ge=1),
    max_pages_per_unit: int | None = Query(default=None, alias="maxPagesPerUnit", ge=1),
    concurrency: int | None = Query(default=None, ge=1, le=8),
    cache_mode: str = Query(
        default="auto",
        alias="cacheMode",
        pattern="^(auto|refresh|bypass)$",
        description="auto uses cached daily summaries and fills misses; refresh recalculates and stores; bypass ignores cache.",
    ),
    dry_run: bool = Query(default=False),
    context: RouteContext = Depends(),
) -> dict[str, Any]:
    resolved_units = _units_or_all_pizzerias(context.settings, units)
    current_params = _period_params(context.settings, resolved_units, from_date, to_date, exclusive_to=True)
    baseline_params = _period_params(
        context.settings,
        resolved_units,
        compare_from_date,
        compare_to_date,
        exclusive_to=True,
    )
    result = await context.service.fetch_sales_comparison(
        current_parameters=current_params,
        baseline_parameters=baseline_params,
        dry_run=dry_run,
        take=take,
        max_pages_per_unit=max_pages_per_unit,
        concurrency=concurrency,
        cache_mode=cache_mode,
    )
    _record_dodo_audit(
        context,
        function_name="accounting_sales_comparison",
        parameters={
            **current_params,
            "compareFrom": compare_from_date.isoformat(),
            "compareTo": compare_to_date.isoformat(),
            "cacheMode": cache_mode,
        },
        dry_run=dry_run,
        fields=None,
        take=take,
        max_pages=max_pages_per_unit,
        result=result,
    )
    return result


@router.get("/accounting/sales/channels-summary")
async def accounting_sales_channels_summary(
    units: str | None = Query(
        default=None,
        description="Optional comma-separated Dodo unit ids. Omit for all configured pizzerias.",
    ),
    from_date: date = Query(..., alias="from"),
    to_date: date = Query(..., alias="to"),
    take: int | None = Query(default=None, ge=1),
    max_pages_per_unit: int | None = Query(default=None, alias="maxPagesPerUnit", ge=1),
    concurrency: int | None = Query(default=None, ge=1, le=8),
    dry_run: bool = Query(default=False),
    context: RouteContext = Depends(),
) -> dict[str, Any]:
    params = _period_params(
        context.settings,
        _units_or_all_pizzerias(context.settings, units),
        from_date,
        to_date,
        exclusive_to=True,
    )
    result = await context.service.fetch_sales_channels_summary(
        parameters=params,
        dry_run=dry_run,
        take=take,
        max_pages_per_unit=max_pages_per_unit,
        concurrency=concurrency,
    )
    _record_dodo_audit(
        context,
        function_name="accounting_sales_channels_summary",
        parameters=params,
        dry_run=dry_run,
        fields=None,
        take=take,
        max_pages=max_pages_per_unit,
        result=result,
    )
    return result


@router.get("/accounting/sales/discounts-summary")
async def accounting_sales_discounts_summary(
    units: str | None = Query(
        default=None,
        description="Optional comma-separated Dodo unit ids. Omit for all configured pizzerias.",
    ),
    from_date: date = Query(..., alias="from"),
    to_date: date = Query(..., alias="to"),
    include_actions: bool = Query(
        default=False,
        alias="includeActions",
        description="When true, include top discount actions inside each category.",
    ),
    top_actions_limit: int = Query(
        default=10,
        alias="topActionsLimit",
        ge=1,
        le=200,
        description="Maximum action rows per category when includeActions=true.",
    ),
    take: int | None = Query(default=None, ge=1),
    max_pages_per_unit: int | None = Query(default=None, alias="maxPagesPerUnit", ge=1),
    concurrency: int | None = Query(default=None, ge=1, le=8),
    dry_run: bool = Query(default=False),
    context: RouteContext = Depends(),
) -> dict[str, Any]:
    params = _period_params(
        context.settings,
        _units_or_all_pizzerias(context.settings, units),
        from_date,
        to_date,
        exclusive_to=True,
    )
    result = await context.service.fetch_sales_discounts_summary(
        parameters=params,
        dry_run=dry_run,
        include_actions=include_actions,
        top_actions_limit=top_actions_limit,
        take=take,
        max_pages_per_unit=max_pages_per_unit,
        concurrency=concurrency,
    )
    _record_dodo_audit(
        context,
        function_name="accounting_sales_discounts_summary",
        parameters={
            **params,
            "includeActions": include_actions,
            "topActionsLimit": top_actions_limit,
        },
        dry_run=dry_run,
        fields=None,
        take=take,
        max_pages=max_pages_per_unit,
        result=result,
    )
    return result


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
    params = _period_params(context.settings, units, from_date, to_date, exclusive_to=True)
    return await _fetch(
        context,
        function_name="accounting_writeoffs_products",
        parameters=params,
        dry_run=dry_run,
        fields=fields,
        take=take,
        max_pages=max_pages,
    )


@router.get("/accounting/writeoffs/products/summary")
async def accounting_writeoffs_products_summary(
    units: str | None = Query(
        default=None,
        description="Optional comma-separated Dodo unit ids. Omit for all configured pizzerias.",
    ),
    from_date: date = Query(..., alias="from"),
    to_date: date = Query(..., alias="to"),
    product_name_prefix: str = Query(
        default="Кус",
        alias="productNamePrefix",
        description="Only write-off rows whose productName starts with this prefix are included.",
    ),
    include_products: bool = Query(
        default=False,
        alias="includeProducts",
        description="When true, include per-product breakdown inside each pizzeria.",
    ),
    include_reasons: bool = Query(
        default=False,
        alias="includeReasons",
        description="When true, include per-reason breakdown inside each pizzeria.",
    ),
    take: int | None = Query(default=None, ge=1),
    max_pages: int | None = Query(default=None, ge=1),
    dry_run: bool = Query(default=False),
    context: RouteContext = Depends(),
) -> dict[str, Any]:
    params = _period_params(
        context.settings,
        _units_or_all_pizzerias(context.settings, units),
        from_date,
        to_date,
        exclusive_to=True,
    )
    result = await context.service.fetch_writeoff_products_summary(
        parameters=params,
        dry_run=dry_run,
        product_name_prefix=product_name_prefix,
        include_products=include_products,
        include_reasons=include_reasons,
        take=take,
        max_pages=max_pages,
    )
    _record_dodo_audit(
        context,
        function_name="accounting_writeoffs_products_summary",
        parameters={
            **params,
            "productNamePrefix": product_name_prefix,
            "includeProducts": include_products,
            "includeReasons": include_reasons,
        },
        dry_run=dry_run,
        fields=None,
        take=take,
        max_pages=max_pages,
        result=result,
    )
    return result


@router.get("/accounting/slices/writeoff-rate")
async def accounting_slices_writeoff_rate(
    units: str | None = Query(
        default=None,
        description="Optional comma-separated Dodo unit ids. Omit for all configured pizzerias.",
    ),
    from_date: date = Query(..., alias="from"),
    to_date: date = Query(..., alias="to"),
    product_name_prefix: str = Query(
        default="Кус",
        alias="productNamePrefix",
        description="Only products whose name starts with this prefix are counted as slices.",
    ),
    include_products: bool = Query(
        default=False,
        alias="includeProducts",
        description="When true, include per-product write-off rate inside each pizzeria.",
    ),
    take: int | None = Query(default=None, ge=1),
    max_pages: int | None = Query(default=None, ge=1),
    dry_run: bool = Query(default=False),
    context: RouteContext = Depends(),
) -> dict[str, Any]:
    resolved_units = _units_or_all_pizzerias(context.settings, units)
    sales_params = _period_params(context.settings, resolved_units, from_date, to_date, exclusive_to=True)
    writeoff_params = _period_params(context.settings, resolved_units, from_date, to_date, exclusive_to=True)
    take_value = take or context.settings.dodo_data_max_take
    max_pages_value = max_pages or context.settings.dodo_data_max_pages
    result = await context.service.fetch_slice_writeoff_rate(
        sales_parameters=sales_params,
        writeoff_parameters=writeoff_params,
        dry_run=dry_run,
        product_name_prefix=product_name_prefix,
        include_products=include_products,
        take=take_value,
        max_pages=max_pages_value,
    )
    _record_dodo_audit(
        context,
        function_name="accounting_slice_writeoff_rate",
        parameters={
            **sales_params,
            "productNamePrefix": product_name_prefix,
            "includeProducts": include_products,
        },
        dry_run=dry_run,
        fields=None,
        take=take_value,
        max_pages=max_pages_value,
        result=result,
    )
    return result


@router.get("/accounting/inventory-stocks")
async def accounting_inventory_stocks(
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
        function_name="accounting_inventory_stocks",
        parameters=params,
        dry_run=dry_run,
        fields=fields,
        take=take,
        max_pages=max_pages,
    )


@router.get("/accounting/stock-consumptions-by-period")
async def accounting_stock_consumptions_by_period(
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
        function_name="accounting_stock_consumptions_by_period",
        parameters=params,
        dry_run=dry_run,
        fields=fields,
        take=take,
        max_pages=max_pages,
    )


@router.get("/units/month-goals")
async def units_month_goals(
    unit: str = Query(..., description="Dodo unit id."),
    month: int = Query(..., ge=1, le=12, description="Month number, 1-12."),
    year: int = Query(..., ge=2000, le=2100, description="Calendar year."),
    dry_run: bool = Query(default=False),
    context: RouteContext = Depends(),
) -> dict[str, Any]:
    params = {
        "unit": normalize_units(unit),
        "month": month,
        "year": year,
    }
    return await _fetch(
        context,
        function_name="units_month_goals",
        parameters=params,
        dry_run=dry_run,
        fields=None,
        take=None,
        max_pages=None,
    )


@router.get("/ratings/customer-experience")
async def ratings_customer_experience(
    units: str | None = Query(default=None, description="Comma-separated Dodo unit ids."),
    country_code: int | None = Query(
        default=None,
        alias="countryCode",
        description="Optional Dodo country code. Use when requesting country-level ratings.",
    ),
    fields: str | None = Query(default=None, description="Optional comma-separated row fields."),
    take: int | None = Query(default=None, ge=1),
    max_pages: int | None = Query(default=None, ge=1),
    dry_run: bool = Query(default=False),
    context: RouteContext = Depends(),
) -> dict[str, Any]:
    params = _ratings_params(units=units, country_code=country_code)
    return await _fetch(
        context,
        function_name="ratings_customer_experience",
        parameters=params,
        dry_run=dry_run,
        fields=fields,
        take=take,
        max_pages=max_pages,
    )


@router.get("/ratings/standards")
async def ratings_standards(
    units: str | None = Query(default=None, description="Comma-separated Dodo unit ids."),
    country_code: int | None = Query(
        default=None,
        alias="countryCode",
        description="Optional Dodo country code. Use when requesting country-level ratings.",
    ),
    fields: str | None = Query(default=None, description="Optional comma-separated row fields."),
    take: int | None = Query(default=None, ge=1),
    max_pages: int | None = Query(default=None, ge=1),
    dry_run: bool = Query(default=False),
    context: RouteContext = Depends(),
) -> dict[str, Any]:
    params = _ratings_params(units=units, country_code=country_code)
    return await _fetch(
        context,
        function_name="ratings_standards",
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
    *,
    exclusive_to: bool = False,
) -> dict[str, Any]:
    validate_period(from_date, to_date, settings)
    api_to_date = to_date + timedelta(days=1) if exclusive_to else to_date
    return {
        "units": normalize_units(units),
        "from": from_date.isoformat(),
        "to": api_to_date.isoformat(),
    }


def _date_params(
    settings: Settings,
    units: str,
    from_date: date,
    to_date: date,
    *,
    from_key: str,
    to_key: str,
    exclusive_to: bool = False,
) -> dict[str, Any]:
    validate_period(from_date, to_date, settings)
    api_to_date = to_date + timedelta(days=1) if exclusive_to else to_date
    return {
        "units": normalize_units(units),
        from_key: from_date.isoformat(),
        to_key: api_to_date.isoformat(),
    }


def _units_or_all_pizzerias(settings: Settings, units: str | None) -> str:
    if units:
        return normalize_units(units)

    pizzerias = load_pizzerias(settings.dodo_pizzerias_path).get("pizzerias", [])
    unit_ids = [str(item["unit_id"]) for item in pizzerias if item.get("unit_id")]
    if not unit_ids:
        raise HTTPException(status_code=422, detail="Provide 'units' or configure DODO_PIZZERIAS_PATH")
    return ",".join(unit_ids)


def _ratings_params(*, units: str | None, country_code: int | None) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if units:
        params["units"] = normalize_units(units)
    if country_code is not None:
        params["countryCode"] = country_code
    if not params:
        raise HTTPException(status_code=422, detail="Provide either 'units' or 'countryCode'")
    return params


def _optional_unit_country_params(*, units: str | None, country_code: int | None) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if units:
        params["units"] = normalize_units(units)
    if country_code is not None:
        params["countryCode"] = country_code
    return params


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
    _record_dodo_audit(
        context,
        function_name=function_name,
        parameters=parameters,
        dry_run=dry_run,
        fields=fields,
        take=take,
        max_pages=max_pages,
        result=result,
    )
    return result


async def _fetch_scope_aware(
    context: RouteContext,
    *,
    function_name: str,
    parameters: dict[str, Any],
    dry_run: bool,
    fields: str | None,
    take: int | None,
    max_pages: int | None,
) -> dict[str, Any]:
    try:
        return await _fetch(
            context,
            function_name=function_name,
            parameters=parameters,
            dry_run=dry_run,
            fields=fields,
            take=take,
            max_pages=max_pages,
        )
    except HTTPException as exc:
        detail = exc.detail
        if not (
            exc.status_code == 502
            and isinstance(detail, dict)
            and detail.get("error") == "external_insufficient_scopes"
        ):
            raise
        result = {
            "function": function_name,
            "tool_name": detail.get("tool_name"),
            "status": "blocked_by_scope",
            "read_only": True,
            "blocked": True,
            "required_scope_hint": detail.get("required_scope_hint"),
            "external_status": detail.get("external_status"),
            "external_code": detail.get("external_code"),
            "message": "Dodo API token does not have the required read scope for this source.",
            "detail": detail,
        }
        _record_dodo_audit(
            context,
            function_name=function_name,
            parameters=parameters,
            dry_run=dry_run,
            fields=fields,
            take=take,
            max_pages=max_pages,
            result=result,
        )
        return result


def _record_dodo_audit(
    context: RouteContext,
    *,
    function_name: str,
    parameters: dict[str, Any],
    dry_run: bool,
    fields: str | None,
    take: int | None,
    max_pages: int | None,
    result: dict[str, Any],
) -> None:
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
