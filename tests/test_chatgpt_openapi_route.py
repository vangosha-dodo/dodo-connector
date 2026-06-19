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
    assert response.headers["content-type"].startswith("application/yaml")
    schema = yaml.safe_load(response.text)
    assert schema["openapi"] == "3.1.0"
    assert schema["servers"] == [{"url": "http://bridge.example.com"}]
    assert "/dodo/accounting/sales/summary" in schema["paths"]
