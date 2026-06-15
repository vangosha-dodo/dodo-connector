from __future__ import annotations

from scripts.export_chatgpt_openapi import build_schema


def test_chatgpt_openapi_contains_only_dodo_get_paths() -> None:
    schema = build_schema("https://bridge.example.com/")

    assert schema["openapi"] == "3.1.0"
    assert schema["servers"] == [{"url": "https://bridge.example.com"}]
    assert set(schema["paths"]) == {
        "/dodo/pizzerias",
        "/dodo/functions",
        "/dodo/delivery/courier-orders",
        "/dodo/staff/shifts",
        "/dodo/delivery/statistics",
        "/dodo/accounting/sales",
        "/dodo/accounting/writeoffs/products",
    }
    for path_item in schema["paths"].values():
        assert set(path_item) == {"get"}


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
