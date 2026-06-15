from __future__ import annotations

from scripts.export_chatgpt_openapi import build_schema


def test_chatgpt_openapi_contains_only_dodo_get_paths() -> None:
    schema = build_schema("https://bridge.example.com/")

    assert schema["servers"] == [{"url": "https://bridge.example.com"}]
    assert set(schema["paths"]) == {
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
