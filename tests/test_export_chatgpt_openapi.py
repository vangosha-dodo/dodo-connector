from __future__ import annotations

from scripts.export_chatgpt_openapi import build_schema


def test_chatgpt_openapi_contains_expected_paths() -> None:
    schema = build_schema("https://bridge.example.com/")

    assert schema["openapi"] == "3.1.0"
    assert schema["servers"] == [{"url": "https://bridge.example.com"}]
    assert set(schema["paths"]) == {
        "/analytics/employee-discount",
        "/system/missing-capability",
        "/dodo/pizzerias",
        "/dodo/functions",
        "/dodo/ratings/customer-experience",
        "/dodo/ratings/standards",
        "/dodo/delivery/courier-orders",
        "/dodo/staff/shifts",
        "/dodo/staff/vacancies/count",
        "/dodo/delivery/statistics",
        "/dodo/accounting/sales",
        "/dodo/accounting/writeoffs/products",
        "/dodo/accounting/inventory-stocks",
    }
    for path, path_item in schema["paths"].items():
        if path.startswith("/dodo/"):
            assert set(path_item) == {"get"}
    assert set(schema["paths"]["/analytics/employee-discount"]) == {"post"}
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


def test_chatgpt_openapi_includes_staff_vacancy_counts() -> None:
    schema = build_schema("https://bridge.example.com")

    operation = schema["paths"]["/dodo/staff/vacancies/count"]["get"]
    assert operation["operationId"] == "getDodoStaffVacancyCounts"
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/DodoDataResponse"
    }
