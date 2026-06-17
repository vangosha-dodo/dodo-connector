from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from dodo_bridge.automation.office_manager import OfficeManagerCommandResult
from dodo_bridge.automation.routes import settings_dep as automation_settings_dep
from dodo_bridge.config import Settings
from dodo_bridge.main import app


def test_automation_jobs_list_is_internal_and_contains_payroll_job(tmp_path) -> None:
    settings = make_settings(tmp_path)
    app.dependency_overrides[automation_settings_dep] = lambda: settings
    try:
        client = TestClient(app)
        response = client.get("/automation/jobs")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["chatgpt_action_exposed"] is False
    assert payload["jobs"][0]["name"] == "courier_payroll_daily_export"
    assert payload["jobs"][0]["status"] == "dry_run_only"
    assert payload["jobs"][0]["writes_enabled"] is False


def test_courier_payroll_daily_export_dry_run_plans_office_manager_extraction(tmp_path) -> None:
    pizzerias_path = write_pizzerias(tmp_path)
    settings = make_settings(tmp_path, dodo_pizzerias_path=pizzerias_path)
    app.dependency_overrides[automation_settings_dep] = lambda: settings
    try:
        client = TestClient(app)
        response = client.post(
            "/automation/jobs/courier_payroll_daily_export/dry-run",
            json={
                "report_date": "2026-06-16",
                "pizzerias": ["Тамбов-1"],
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["audit_id"] > 0
    assert payload["job_name"] == "courier_payroll_daily_export"
    assert payload["dry_run"] is True
    assert payload["dodo_is_changed"] is False
    assert payload["google_sheets_changed"] is False
    assert payload["source"]["path"] == "Отчеты -> Заработная плата"
    assert payload["source"]["filters"] == {"date": "2026-06-16", "staff_type": "Курьер"}
    assert payload["source"]["pizzerias_count"] == 1
    assert payload["source"]["helper_configured"] is False
    assert payload["source"]["helper_called"] is False
    assert payload["target"]["sheet"] == "Ежедневная выгрузка"
    assert payload["target"]["range"] == "A:BF"
    assert payload["target"]["header_count"] == 58
    assert payload["extraction_requests"] == [
        {
            "unit_id": "unit-tambov-1",
            "pizzeria": "Тамбов-1",
            "date": "2026-06-16",
            "staff_type": "Курьер",
            "read_only": True,
        }
    ]
    assert payload["planned_writes"][0]["enabled"] is False
    assert "ЗП, премия" in payload["planned_writes"][0]["preserve_columns"]
    assert "Итого зп" in payload["planned_writes"][0]["formula_columns"]


def test_courier_payroll_daily_export_rejects_unknown_pizzeria(tmp_path) -> None:
    pizzerias_path = write_pizzerias(tmp_path)
    settings = make_settings(tmp_path, dodo_pizzerias_path=pizzerias_path)
    app.dependency_overrides[automation_settings_dep] = lambda: settings
    try:
        client = TestClient(app)
        response = client.post(
            "/automation/jobs/courier_payroll_daily_export/dry-run",
            json={
                "report_date": "2026-06-16",
                "pizzerias": ["Неизвестная-1"],
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json()["detail"] == "No pizzerias matched the requested filter"


def test_courier_payroll_daily_export_normalizes_helper_rows(tmp_path, monkeypatch) -> None:
    async def fake_run(self, action, payload):  # noqa: ANN001
        del self
        assert action == "courier-payroll-daily"
        assert payload["report_date"] == "2026-06-16"
        return OfficeManagerCommandResult(
            configured=True,
            ok=True,
            action=action,
            data={
                "ok": True,
                "rows": [
                    {
                        "shiftStartDate": "2026-06-16",
                        "shiftStartTime": "10:00",
                        "shiftEndTime": "18:00",
                        "lastName": "Иванов",
                        "firstName": "Петр",
                        "employeeId": 123,
                        "employeeUuid": "uuid-123",
                        "employmentType": "Самозанятый",
                        "unitName": "Тамбов-1",
                        "ordersCount": 12,
                        "distanceKm": 42.5,
                    }
                ],
            },
        )

    monkeypatch.setattr("dodo_bridge.automation.jobs.DodoOfficeManagerCommandRunner.run", fake_run)
    pizzerias_path = write_pizzerias(tmp_path)
    settings = make_settings(
        tmp_path,
        dodo_pizzerias_path=pizzerias_path,
        dodo_office_manager_helper_command="node scripts/dodo_office_manager_reports.mjs",
    )
    app.dependency_overrides[automation_settings_dep] = lambda: settings
    try:
        client = TestClient(app)
        response = client.post(
            "/automation/jobs/courier_payroll_daily_export/dry-run",
            json={
                "report_date": "2026-06-16",
                "pizzerias": ["Тамбов-1"],
                "extract_source": True,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"]["helper_configured"] is True
    assert payload["source"]["helper_called"] is True
    assert payload["source"]["helper_ok"] is True
    assert payload["source"]["row_count"] == 1
    assert payload["row_summary"]["ready_rows"] == 1
    assert payload["row_summary"]["invalid_rows"] == 0
    preview = payload["planned_rows_preview"][0]
    assert preview["pizzeria"] == "Тамбов-1"
    assert preview["employee"] == {"id": 123, "uuid": "uuid-123", "name": "Иванов Петр"}
    assert preview["shift"] == {"start": "2026-06-16 10:00", "end": "2026-06-16 18:00"}
    assert len(preview["upsert_match_key"]) == 64
    assert len(preview["source_row_hash"]) == 64
    formulas = payload["planned_writes"][0]["formula_templates"]
    assert formulas["Итого зп"]["column"] == "BC"
    assert formulas["Итого зп"]["formula"].startswith("=V{row}+W{row}")
    assert formulas["Неделя"]["column"] == "BD"


def test_automation_run_is_blocked_while_writes_are_disabled(tmp_path) -> None:
    settings = make_settings(tmp_path)
    app.dependency_overrides[automation_settings_dep] = lambda: settings
    try:
        client = TestClient(app)
        response = client.post("/automation/jobs/courier_payroll_daily_export/run")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["job_name"] == "courier_payroll_daily_export"
    assert detail["dodo_is_changed"] is False
    assert detail["google_sheets_changed"] is False


def write_pizzerias(tmp_path: Path) -> Path:
    path = tmp_path / "pizzerias.json"
    path.write_text(
        json.dumps(
            [
                {
                    "id": "unit-tambov-1",
                    "name": "Тамбов-1",
                    "countryCode": 643,
                    "businessId": "dodopizza",
                    "unitType": 1,
                },
                {
                    "id": "unit-arkh-1",
                    "name": "Архангельск-1",
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


def make_settings(
    tmp_path: Path,
    *,
    dodo_pizzerias_path: Path | None = None,
    dodo_office_manager_helper_command: str | None = None,
) -> Settings:
    return Settings(
        api_keys=[],
        tool_registry_path=Path("configs/tools.example.yaml"),
        policy_path=Path("configs/policy.example.yaml"),
        audit_db_path=tmp_path / "audit.sqlite3",
        dodo_access_token=None,
        dodo_pizzerias_path=dodo_pizzerias_path,
        dodo_office_manager_helper_command=dodo_office_manager_helper_command,
        automation_google_sheets_write_enabled=False,
    )
