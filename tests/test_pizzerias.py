from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from dodo_bridge.config import Settings
from dodo_bridge.dodo_data_routes import settings_dep as dodo_data_settings_dep
from dodo_bridge.main import app
from dodo_bridge.pizzerias import load_pizzerias


def test_load_pizzerias_filters_and_adds_aliases(tmp_path) -> None:
    path = write_units(tmp_path)

    payload = load_pizzerias(path)

    assert payload["count"] == 2
    names = [item["name"] for item in payload["pizzerias"]]
    assert names == ["Архангельск-1", "Архангельск-2"]
    first = payload["pizzerias"][0]
    assert first["unit_id"] == "unit-1"
    assert first["is_pizzeria"] is True
    assert "Архангельск 1" in first["aliases"]


def test_load_pizzerias_searches_by_alias(tmp_path) -> None:
    path = write_units(tmp_path)

    payload = load_pizzerias(path, search="архангельск 2")

    assert payload["count"] == 1
    assert payload["pizzerias"][0]["unit_id"] == "unit-2"


def test_load_pizzerias_can_include_non_pizzerias(tmp_path) -> None:
    path = write_units(tmp_path)

    payload = load_pizzerias(path, include_non_pizzerias=True)

    assert payload["count"] == 3
    assert any(item["name"] == "Офис" for item in payload["pizzerias"])


def test_dodo_pizzerias_route_requires_bridge_key_when_configured(tmp_path) -> None:
    settings = make_settings(tmp_path, api_keys=["secret"])
    app.dependency_overrides[dodo_data_settings_dep] = lambda: settings
    try:
        client = TestClient(app)
        response = client.get("/dodo/pizzerias")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401


def test_dodo_pizzerias_route_returns_catalog(tmp_path) -> None:
    settings = make_settings(tmp_path)
    app.dependency_overrides[dodo_data_settings_dep] = lambda: settings
    try:
        client = TestClient(app)
        response = client.get("/dodo/pizzerias", params={"search": "архангельск-1"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["pizzerias"][0]["unit_id"] == "unit-1"


def write_units(tmp_path: Path) -> Path:
    path = tmp_path / "roles_units.json"
    path.write_text(
        json.dumps(
            [
                {
                    "id": "office",
                    "name": "Офис",
                    "countryCode": 643,
                    "businessId": "dodopizza",
                    "unitType": 0,
                },
                {
                    "id": "unit-1",
                    "name": "Архангельск-1",
                    "countryCode": 643,
                    "businessId": "dodopizza",
                    "unitType": 1,
                },
                {
                    "id": "unit-2",
                    "name": "Архангельск-2",
                    "countryCode": 643,
                    "businessId": "dodopizza",
                    "unitType": 1,
                },
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def make_settings(tmp_path: Path, api_keys: list[str] | None = None) -> Settings:
    return Settings(
        api_keys=api_keys or [],
        tool_registry_path=Path("configs/tools.example.yaml"),
        policy_path=Path("configs/policy.example.yaml"),
        audit_db_path=tmp_path / "audit.sqlite3",
        dodo_access_token=None,
        dodo_pizzerias_path=write_units(tmp_path),
    )
