from __future__ import annotations

from scripts.export_chatgpt_openapi import build_schema


def test_chatgpt_openapi_contains_expected_paths() -> None:
    schema = build_schema("https://bridge.example.com/")

    assert schema["openapi"] == "3.1.0"
    assert schema["servers"] == [{"url": "https://bridge.example.com"}]
    assert set(schema["paths"]) == {
        "/analytics/employee-discount",
        "/analytics/kiosk-sales-share",
        "/system/missing-capability",
        "/dodo/pizzerias",
        "/dodo/functions",
        "/dodo/ratings/customer-experience",
        "/dodo/ratings/standards",
        "/dodo/delivery/courier-orders",
        "/dodo/staff/shifts",
        "/dodo/staff/vacancies/count",
        "/dodo/delivery/statistics",
        "/dodo/orders/clients-statistics",
        "/dodo/production/productivity",
        "/dodo/production/orders-handover-time",
        "/dodo/accounting/sales",
        "/dodo/accounting/sales/summary",
        "/dodo/accounting/sales/comparison",
        "/dodo/accounting/sales/channels-summary",
        "/dodo/accounting/sales/discounts-summary",
        "/dodo/accounting/writeoffs/products",
        "/dodo/accounting/writeoffs/products/summary",
        "/dodo/accounting/slices/writeoff-rate",
        "/dodo/accounting/slices/daily-dynamics",
        "/dodo/accounting/inventory-stocks",
        "/dodo/accounting/stock-consumptions-by-period",
        "/dodo/units/month-goals",
    }
    for path, path_item in schema["paths"].items():
        if path.startswith("/dodo/"):
            assert set(path_item) == {"get"}
    assert set(schema["paths"]["/analytics/employee-discount"]) == {"post"}
    assert set(schema["paths"]["/analytics/kiosk-sales-share"]) == {"post"}
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


def test_chatgpt_openapi_includes_ratings_routes() -> None:
    schema = build_schema("https://bridge.example.com")

    customer = schema["paths"]["/dodo/ratings/customer-experience"]["get"]
    standards = schema["paths"]["/dodo/ratings/standards"]["get"]
    assert customer["operationId"] == "getDodoCustomerExperienceRatings"
    assert standards["operationId"] == "getDodoStandardsRatings"
    assert customer["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/DodoDataResponse"
    }


def test_chatgpt_openapi_includes_inventory_stocks() -> None:
    schema = build_schema("https://bridge.example.com")

    operation = schema["paths"]["/dodo/accounting/inventory-stocks"]["get"]
    assert operation["operationId"] == "getDodoAccountingInventoryStocks"
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/DodoDataResponse"
    }


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


def test_chatgpt_openapi_includes_stock_consumptions_by_period() -> None:
    schema = build_schema("https://bridge.example.com")

    operation = schema["paths"]["/dodo/accounting/stock-consumptions-by-period"]["get"]
    assert operation["operationId"] == "getDodoAccountingStockConsumptionsByPeriod"
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/DodoDataResponse"
    }


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
