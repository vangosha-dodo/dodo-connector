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
            "/tools/dodo_delivery_courier_orders/invoke",
            json={
                "parameters": {
                    "units": ["unit-1"],
                    "from": "2026-06-01",
                    "to": "2026-06-02",
                    "take": 1,
                },
                "intent": "check courier delivery orders",
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
            "/tools/superset_kiosk_sales_share/invoke",
            json={
                "parameters": {
                    "dashboard_id": 123,
                    "chart_id": 456,
                    "metric": "Share sales via Kiosk",
                },
                "intent": "check kiosk share",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json()["detail"]["reason"] == "tool_disabled"


def test_superset_chart_constraints_block_wrong_dashboard(tmp_path) -> None:
    settings = make_settings(tmp_path)
    app.dependency_overrides[settings_dep] = lambda: settings
    try:
        client = TestClient(app)
        response = client.post(
            "/tools/superset_employee_discount_chart/invoke",
            json={
                "parameters": {
                    "dashboard_id": 9999,
                    "chart_id": 26708,
                    "metric": "employee_segment_discount",
                },
                "intent": "check employee discount",
                "dry_run": True,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json()["detail"]["reason"] == "dashboard_not_allowed"


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        api_keys=[],
        tool_registry_path=Path("configs/tools.example.yaml"),
        policy_path=Path("configs/policy.example.yaml"),
        audit_db_path=tmp_path / "audit.sqlite3",
        dodo_access_token=None,
        dodo_pizzerias_path=None,
    )
