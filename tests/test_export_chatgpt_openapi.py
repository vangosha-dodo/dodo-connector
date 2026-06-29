from __future__ import annotations

from scripts.export_chatgpt_openapi import build_schema


def test_chatgpt_openapi_contains_expected_paths() -> None:
    schema = build_schema("https://bridge.example.com/")

    assert schema["openapi"] == "3.1.0"
    assert schema["servers"] == [{"url": "https://bridge.example.com"}]
    assert set(schema["paths"]) == {
        "/analytics/employee-discount",
        "/analytics/kiosk-sales-share",
        "/system/agent-status",
        "/system/missing-capability",
        "/dodo/pizzerias",
        "/dodo/functions",
        "/dodo/ratings/customer-experience/summary",
        "/dodo/ratings/standards/summary",
        "/dodo/delivery/courier-orders",
        "/dodo/staff/shifts",
        "/dodo/staff/vacancies/count",
        "/dodo/delivery/statistics",
        "/dodo/delivery/courier-productivity/summary",
        "/dodo/orders/clients-statistics",
        "/dodo/production/productivity",
        "/dodo/production/orders-handover-time",
        "/dodo/accounting/sales/summary",
        "/dodo/accounting/sales/comparison",
        "/dodo/accounting/sales/channels-summary",
        "/dodo/accounting/sales/discounts-summary",
        "/dodo/accounting/writeoffs/products/summary",
        "/dodo/accounting/slices/writeoff-rate",
        "/dodo/accounting/slices/daily-dynamics",
        "/dodo/accounting/inventory-stocks/summary",
        "/dodo/accounting/stock-consumptions-by-period/summary",
        "/dodo/units/month-goals",
    }
    for path, path_item in schema["paths"].items():
        if path.startswith("/dodo/"):
            assert set(path_item) == {"get"}
    assert set(schema["paths"]["/analytics/employee-discount"]) == {"post"}
    assert set(schema["paths"]["/analytics/kiosk-sales-share"]) == {"post"}
    assert set(schema["paths"]["/system/agent-status"]) == {"get"}
    assert set(schema["paths"]["/system/missing-capability"]) == {"post"}


def test_chatgpt_openapi_declares_bearer_auth() -> None:
    schema = build_schema("https://bridge.example.com")

    assert schema["security"] == [{"bearerAuth": []}]
    assert schema["components"]["securitySchemes"]["bearerAuth"] == {
        "type": "http",
        "scheme": "bearer",
        "description": "Bridge API key sent as Authorization: Bearer <key>.",
    }


def test_chatgpt_openapi_object_schemas_have_properties() -> None:
    schema = build_schema("https://bridge.example.com")

    object_schemas = {
        name: component
        for name, component in schema["components"]["schemas"].items()
        if component.get("type") == "object"
    }
    assert object_schemas
    for name, component in object_schemas.items():
        assert "properties" in component, name
    assert "BridgeObjectResponse" not in schema["components"]["schemas"]


def test_chatgpt_openapi_operation_descriptions_fit_actions_limit() -> None:
    schema = build_schema("https://bridge.example.com")

    for path, path_item in schema["paths"].items():
        for method, operation in path_item.items():
            description = operation.get("description", "")
            assert len(description) <= 300, f"{method.upper()} {path}"


def test_chatgpt_openapi_stays_under_actions_operation_limit() -> None:
    schema = build_schema("https://bridge.example.com")

    operations = [
        (path, method)
        for path, path_item in schema["paths"].items()
        for method in path_item
    ]
    assert len(operations) <= 30


def test_chatgpt_openapi_omits_heavy_raw_routes_with_summary_alternatives() -> None:
    schema = build_schema("https://bridge.example.com")

    assert {
        "/dodo/ratings/customer-experience",
        "/dodo/ratings/standards",
        "/dodo/accounting/sales",
        "/dodo/accounting/writeoffs/products",
        "/dodo/accounting/inventory-stocks",
        "/dodo/accounting/stock-consumptions-by-period",
    }.isdisjoint(schema["paths"])


def test_chatgpt_openapi_includes_pizzeria_catalog() -> None:
    schema = build_schema("https://bridge.example.com")

    operation = schema["paths"]["/dodo/pizzerias"]["get"]
    assert operation["operationId"] == "listDodoPizzerias"
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/DodoPizzeriasResponse"
    }
    assert "DodoPizzeria" in schema["components"]["schemas"]


def test_chatgpt_openapi_includes_employee_discount() -> None:
    schema = build_schema("https://bridge.example.com")

    operation = schema["paths"]["/analytics/employee-discount"]["post"]
    assert operation["operationId"] == "getEmployeeDiscount"
    assert operation["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/EmployeeDiscountRequest"
    }
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/EmployeeDiscountResponse"
    }


def test_chatgpt_openapi_includes_kiosk_sales_share() -> None:
    schema = build_schema("https://bridge.example.com")

    operation = schema["paths"]["/analytics/kiosk-sales-share"]["post"]
    assert operation["operationId"] == "getKioskSalesShare"
    assert operation["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/KioskSalesShareRequest"
    }
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/KioskSalesShareResponse"
    }
    assert "KioskSalesShareRow" in schema["components"]["schemas"]


def test_chatgpt_openapi_includes_missing_capability_report() -> None:
    schema = build_schema("https://bridge.example.com")

    operation = schema["paths"]["/system/missing-capability"]["post"]
    assert operation["operationId"] == "reportMissingCapability"
    assert operation["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/MissingCapabilityRequest"
    }
    response = schema["components"]["schemas"]["MissingCapabilityResponse"]
    assert response["properties"]["dodo_is_changed"]["const"] is False


def test_chatgpt_openapi_includes_agent_status() -> None:
    schema = build_schema("https://bridge.example.com")

    operation = schema["paths"]["/system/agent-status"]["get"]
    assert operation["operationId"] == "getBridgeAgentStatus"
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/AgentStatusResponse"
    }
    response = schema["components"]["schemas"]["AgentStatusResponse"]
    assert response["properties"]["read_only"]["const"] is True
    assert response["properties"]["dodo_is_changed"]["const"] is False


def test_chatgpt_openapi_includes_ratings_routes() -> None:
    schema = build_schema("https://bridge.example.com")

    customer_summary = schema["paths"]["/dodo/ratings/customer-experience/summary"]["get"]
    standards_summary = schema["paths"]["/dodo/ratings/standards/summary"]["get"]
    assert customer_summary["operationId"] == "getDodoCustomerExperienceRatingsSummary"
    assert standards_summary["operationId"] == "getDodoStandardsRatingsSummary"
    assert customer_summary["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/DodoRatingsSummaryResponse"
    }
    assert "DodoRatingsSummaryUnit" in schema["components"]["schemas"]


def test_chatgpt_openapi_includes_clients_and_production_routes() -> None:
    schema = build_schema("https://bridge.example.com")

    clients = schema["paths"]["/dodo/orders/clients-statistics"]["get"]
    productivity = schema["paths"]["/dodo/production/productivity"]["get"]
    handover = schema["paths"]["/dodo/production/orders-handover-time"]["get"]
    assert clients["operationId"] == "getDodoOrdersClientsStatistics"
    assert productivity["operationId"] == "getDodoProductionProductivity"
    assert handover["operationId"] == "getDodoProductionOrdersHandoverTime"
    for operation in (clients, productivity, handover):
        parameter_names = {item["name"] for item in operation["parameters"]}
        assert {"units", "from", "to", "fields", "dry_run", "take", "max_pages"} <= parameter_names
        units_param = next(item for item in operation["parameters"] if item["name"] == "units")
        assert units_param["required"] is False
        assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/DodoDataResponse"
    }


def test_chatgpt_openapi_includes_inventory_stocks_summary() -> None:
    schema = build_schema("https://bridge.example.com")

    operation = schema["paths"]["/dodo/accounting/inventory-stocks/summary"]["get"]
    assert operation["operationId"] == "getDodoAccountingInventoryStockSummary"
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/DodoInventoryStocksSummaryResponse"
    }
    assert "DodoInventoryStocksSummaryItem" in schema["components"]["schemas"]


def test_chatgpt_openapi_includes_sales_summary() -> None:
    schema = build_schema("https://bridge.example.com")

    operation = schema["paths"]["/dodo/accounting/sales/summary"]["get"]
    assert operation["operationId"] == "getDodoAccountingSalesSummary"
    parameter_names = {item["name"] for item in operation["parameters"]}
    assert {"units", "from", "to", "maxPagesPerUnit", "concurrency", "cacheMode"} <= parameter_names
    units_param = next(item for item in operation["parameters"] if item["name"] == "units")
    assert units_param["required"] is False
    assert "Omit for all configured pizzerias" in units_param["description"]
    assert "fields" not in parameter_names
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/DodoSalesSummaryResponse"
    }
    assert "DodoSalesSummaryUnit" in schema["components"]["schemas"]


def test_chatgpt_openapi_includes_sales_comparison() -> None:
    schema = build_schema("https://bridge.example.com")

    operation = schema["paths"]["/dodo/accounting/sales/comparison"]["get"]
    assert operation["operationId"] == "getDodoAccountingSalesComparison"
    parameter_names = {item["name"] for item in operation["parameters"]}
    assert {
        "units",
        "from",
        "to",
        "compareFrom",
        "compareTo",
        "maxPagesPerUnit",
        "concurrency",
        "cacheMode",
    } <= parameter_names
    units_param = next(item for item in operation["parameters"] if item["name"] == "units")
    assert units_param["required"] is False
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/DodoSalesComparisonResponse"
    }
    assert "DodoSalesComparisonUnit" in schema["components"]["schemas"]


def test_chatgpt_openapi_includes_sales_channels_summary() -> None:
    schema = build_schema("https://bridge.example.com")

    operation = schema["paths"]["/dodo/accounting/sales/channels-summary"]["get"]
    assert operation["operationId"] == "getDodoAccountingSalesChannelsSummary"
    parameter_names = {item["name"] for item in operation["parameters"]}
    assert {"units", "from", "to", "maxPagesPerUnit", "concurrency"} <= parameter_names
    assert "cacheMode" not in parameter_names
    units_param = next(item for item in operation["parameters"] if item["name"] == "units")
    assert units_param["required"] is False
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/DodoSalesChannelsSummaryResponse"
    }
    assert "DodoSalesChannelsUnit" in schema["components"]["schemas"]
    assert "DodoKioskShare" in schema["components"]["schemas"]


def test_chatgpt_openapi_includes_sales_discounts_summary() -> None:
    schema = build_schema("https://bridge.example.com")

    operation = schema["paths"]["/dodo/accounting/sales/discounts-summary"]["get"]
    assert operation["operationId"] == "getDodoAccountingSalesDiscountsSummary"
    parameter_names = {item["name"] for item in operation["parameters"]}
    assert {
        "units",
        "from",
        "to",
        "maxPagesPerUnit",
        "concurrency",
        "includeActions",
        "topActionsLimit",
    } <= parameter_names
    assert "cacheMode" not in parameter_names
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/DodoSalesDiscountsSummaryResponse"
    }
    assert "DodoSalesDiscountCategory" in schema["components"]["schemas"]
    assert "DodoSalesDiscountAction" in schema["components"]["schemas"]


def test_chatgpt_openapi_includes_product_writeoff_summary() -> None:
    schema = build_schema("https://bridge.example.com")

    operation = schema["paths"]["/dodo/accounting/writeoffs/products/summary"]["get"]
    assert operation["operationId"] == "getDodoAccountingProductWriteoffSummary"
    parameter_names = {item["name"] for item in operation["parameters"]}
    assert {"units", "from", "to", "productNamePrefix", "includeProducts", "includeReasons"} <= parameter_names
    units_param = next(item for item in operation["parameters"] if item["name"] == "units")
    assert units_param["required"] is False
    assert "fields" not in parameter_names
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/DodoWriteoffSummaryResponse"
    }


def test_chatgpt_openapi_includes_slice_writeoff_rate() -> None:
    schema = build_schema("https://bridge.example.com")

    operation = schema["paths"]["/dodo/accounting/slices/writeoff-rate"]["get"]
    assert operation["operationId"] == "getDodoSliceWriteoffRate"
    parameter_names = {item["name"] for item in operation["parameters"]}
    assert {"units", "from", "to", "productNamePrefix", "includeProducts"} <= parameter_names
    units_param = next(item for item in operation["parameters"] if item["name"] == "units")
    assert units_param["required"] is False
    assert "fields" not in parameter_names
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/DodoSliceWriteoffRateResponse"
    }


def test_chatgpt_openapi_includes_slice_daily_dynamics() -> None:
    schema = build_schema("https://bridge.example.com")

    operation = schema["paths"]["/dodo/accounting/slices/daily-dynamics"]["get"]
    assert operation["operationId"] == "getDodoSliceDailyDynamics"
    parameter_names = {item["name"] for item in operation["parameters"]}
    assert {"units", "from", "to", "productNamePrefix", "includeProducts"} <= parameter_names
    units_param = next(item for item in operation["parameters"] if item["name"] == "units")
    assert units_param["required"] is True
    assert "fields" not in parameter_names
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/DodoSliceDailyDynamicsResponse"
    }
    assert "DodoSliceDailyDynamicsDay" in schema["components"]["schemas"]


def test_chatgpt_openapi_includes_stock_consumptions_summary() -> None:
    schema = build_schema("https://bridge.example.com")

    operation = schema["paths"]["/dodo/accounting/stock-consumptions-by-period/summary"]["get"]
    assert operation["operationId"] == "getDodoAccountingStockConsumptionSummary"
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/DodoStockConsumptionSummaryResponse"
    }
    assert "DodoStockConsumptionSummaryUnitItem" in schema["components"]["schemas"]


def test_chatgpt_openapi_includes_unit_month_goals() -> None:
    schema = build_schema("https://bridge.example.com")

    operation = schema["paths"]["/dodo/units/month-goals"]["get"]
    assert operation["operationId"] == "getDodoUnitMonthGoals"
    parameter_names = {item["name"] for item in operation["parameters"]}
    assert {"unit", "month", "year", "dry_run"} <= parameter_names
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/DodoDataResponse"
    }


def test_chatgpt_openapi_includes_staff_vacancy_counts() -> None:
    schema = build_schema("https://bridge.example.com")

    operation = schema["paths"]["/dodo/staff/vacancies/count"]["get"]
    assert operation["operationId"] == "getDodoStaffVacancyCounts"
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/DodoDataResponse"
    }


def test_chatgpt_openapi_includes_courier_productivity_summary() -> None:
    schema = build_schema("https://bridge.example.com")

    operation = schema["paths"]["/dodo/delivery/courier-productivity/summary"]["get"]
    assert operation["operationId"] == "getDodoDeliveryCourierProductivitySummary"
    parameter_names = {item["name"] for item in operation["parameters"]}
    assert {"units", "from", "to", "topLimit", "dry_run"} <= parameter_names
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/DodoDataResponse"
    }
