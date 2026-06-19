from __future__ import annotations

import yaml
from fastapi.testclient import TestClient

from dodo_bridge.main import app


def test_chatgpt_openapi_yaml_route_is_public_and_uses_request_host() -> None:
    client = TestClient(app)

    response = client.get(
        "/chatgpt/openapi.yaml",
        headers={"host": "bridge.example.com"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/yaml")
    schema = yaml.safe_load(response.text)
    assert schema["openapi"] == "3.1.0"
    assert schema["servers"] == [{"url": "http://bridge.example.com"}]
    assert "/dodo/accounting/sales/summary" in schema["paths"]


def test_chatgpt_openapi_yaml_route_uses_forwarded_https_host() -> None:
    client = TestClient(app)

    response = client.get(
        "/chatgpt/openapi.yaml",
        headers={
            "host": "127.0.0.1:8000",
            "x-forwarded-proto": "https",
            "x-forwarded-host": "bridge.example.com",
        },
    )

    assert response.status_code == 200
    schema = yaml.safe_load(response.text)
    assert schema["servers"] == [{"url": "https://bridge.example.com"}]


def test_chatgpt_openapi_yaml_route_prefers_cloudflare_scheme() -> None:
    client = TestClient(app)

    response = client.get(
        "/chatgpt/openapi.yaml",
        headers={
            "host": "bridge.example.com",
            "x-forwarded-proto": "http",
            "cf-visitor": '{"scheme":"https"}',
        },
    )

    assert response.status_code == 200
    schema = yaml.safe_load(response.text)
    assert schema["servers"] == [{"url": "https://bridge.example.com"}]


def test_chatgpt_openapi_yaml_route_allows_head() -> None:
    client = TestClient(app)

    response = client.head(
        "/chatgpt/openapi.yaml",
        headers={
            "host": "bridge.example.com",
            "x-forwarded-proto": "https",
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/yaml")
    assert int(response.headers["content-length"]) > 0
    assert response.content == b""
