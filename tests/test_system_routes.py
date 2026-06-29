from pathlib import Path

from fastapi.testclient import TestClient

from dodo_bridge.audit import AuditStore
from dodo_bridge.config import Settings
from dodo_bridge.main import app
from dodo_bridge.system_routes import settings_dep as system_settings_dep


def test_agent_status_returns_read_only_routing_snapshot(tmp_path) -> None:
    settings = make_settings(tmp_path)
    app.dependency_overrides[system_settings_dep] = lambda: settings
    try:
        client = TestClient(app)
        response = client.get("/system/agent-status")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["read_only"] is True
    assert payload["dodo_is_changed"] is False
    assert payload["openapi"]["operation_limit"] == 30
    assert payload["openapi"]["operation_count"] <= 30
    assert payload["sources"]["dodo_api"]["enabled"] is True
    assert "accounting_sales_summary" in payload["sources"]["dodo_api"]["capabilities"]
    assert "courier_orders" not in payload["sources"]["dodo_api"]["capabilities"]
    assert payload["sources"]["superset"]["capabilities"] == [
        "employee_discount",
        "kiosk_sales_share",
    ]
    assert payload["sources"]["office_manager"]["capabilities"] == [
        "courier_payroll_daily_export"
    ]
    assert payload["agent_next_steps"][0]["action"] == "check_status"


def test_agent_status_requires_api_key_when_configured(tmp_path) -> None:
    settings = make_settings(tmp_path, api_keys=["secret-key"])
    app.dependency_overrides[system_settings_dep] = lambda: settings
    try:
        client = TestClient(app)
        response = client.get("/system/agent-status")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401


def test_report_missing_capability_records_backlog_entry(tmp_path) -> None:
    settings = make_settings(tmp_path)
    app.dependency_overrides[system_settings_dep] = lambda: settings
    try:
        client = TestClient(app)
        response = client.post(
            "/system/missing-capability",
            json={
                "user_question": "Какой дисконт по сотрудникам был в июне?",
                "requested_capability": "employee_discount_by_unit_month",
                "desired_output": "Сумма дисконта и источник",
                "source_type": "superset",
                "known_source": "Дашборд маркетинга",
                "unit_names": [" Тамбов-1 "],
                "period": {"from": "2026-06-01", "to": "2026-06-30"},
                "priority": "high",
                "confidence": 0.8,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "accepted"
    assert payload["dodo_is_changed"] is False
    assert payload["request_id"] > 0
    rows = AuditStore(settings.audit_db_path).fetch_missing_capabilities()
    assert len(rows) == 1
    row = rows[0]
    assert row["requested_capability"] == "employee_discount_by_unit_month"
    assert row["unit_names_json"] == '["Тамбов-1"]'
    assert row["period_from"] == "2026-06-01"
    assert row["period_to"] == "2026-06-30"
    assert row["status"] == "new"


def test_report_missing_capability_requires_api_key_when_configured(tmp_path) -> None:
    settings = make_settings(tmp_path, api_keys=["secret-key"])
    app.dependency_overrides[system_settings_dep] = lambda: settings
    try:
        client = TestClient(app)
        response = client.post(
            "/system/missing-capability",
            json={
                "user_question": "Нужен новый показатель",
                "requested_capability": "new_metric",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401


def make_settings(tmp_path: Path, api_keys: list[str] | None = None) -> Settings:
    return Settings(
        api_keys=api_keys or [],
        tool_registry_path=Path("configs/tools.example.yaml"),
        policy_path=Path("configs/policy.example.yaml"),
        audit_db_path=tmp_path / "audit.sqlite3",
        dodo_access_token=None,
        dodo_pizzerias_path=None,
    )
