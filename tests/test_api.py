from pathlib import Path

from fastapi.testclient import TestClient

from dodo_bridge.config import Settings
from dodo_bridge.main import app, settings_dep


def test_allowed_tool_invocation_dry_run(tmp_path) -> None:
    settings = make_settings(tmp_path)
    app.dependency_overrides[settings_dep] = lambda: settings
    try:
        client = TestClient(app)
        response = client.post(
            "/tools/dodo_inventory_stocks/invoke",
            json={
                "parameters": {"units": ["unit-1"], "take": 1},
                "intent": "check inventory",
                "dry_run": True,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["decision"] == "allow"
    assert payload["result"]["dry_run"] is True


def test_disabled_tool_is_blocked_and_audited(tmp_path) -> None:
    settings = make_settings(tmp_path)
    app.dependency_overrides[settings_dep] = lambda: settings
    try:
        client = TestClient(app)
        response = client.post(
            "/tools/dodo_sales/invoke",
            json={"parameters": {"take": 1}, "intent": "check sales"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json()["detail"]["reason"] == "tool_disabled"


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        api_keys=[],
        tool_registry_path=Path("configs/tools.example.yaml"),
        policy_path=Path("configs/policy.example.yaml"),
        audit_db_path=tmp_path / "audit.sqlite3",
        dodo_access_token=None,
    )

