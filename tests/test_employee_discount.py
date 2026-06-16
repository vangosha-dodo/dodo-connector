from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from dodo_bridge.analytics_routes import settings_dep as analytics_settings_dep
from dodo_bridge.config import Settings
from dodo_bridge.connectors.superset import SupersetConnector
from dodo_bridge.main import app


def test_employee_discount_dry_run_builds_superset_request(tmp_path) -> None:
    settings = make_settings(tmp_path)
    app.dependency_overrides[analytics_settings_dep] = lambda: settings
    try:
        client = TestClient(app)
        response = client.post(
            "/analytics/employee-discount",
            json={
                "period": {"from": "2026-03-01", "to": "2026-03-31"},
                "unit_names": ["Тамбов-3"],
                "dry_run": True,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "dry_run"
    assert payload["capability_id"] == "get_employee_discount"
    assert payload["request"]["method"] == "POST"
    assert payload["request"]["url"].endswith("/api/v1/chart/data?dashboard_id=1410")
    body = payload["request"]["json"]
    assert body["form_data"]["slice_id"] == 26708
    assert body["queries"][0]["filters"][0] == {
        "col": "UnitName",
        "op": "IN",
        "val": ["Тамбов-3"],
    }
    assert body["queries"][0]["time_range"] == "2026-03-01 : 2026-03-31"


def test_employee_discount_normalizes_superset_rows(tmp_path, monkeypatch) -> None:
    async def fake_invoke(self, tool, parameters, dry_run):  # noqa: ANN001
        del self, tool, parameters, dry_run
        return {
            "result": [
                {
                    "rowcount": 2,
                    "is_cached": False,
                    "data": [
                        {
                            "UnitName": "Тамбов-3",
                            "ActionSegmentationAndSource": "Сотрудникам",
                            "BonusActionUUId": "a1",
                            "ActionName": "Сотрудникам",
                            "PromocodeMasked": None,
                            "Discount": 100.5,
                            "SalesWithoutDiscount": 1000,
                        },
                        {
                            "UnitName": "Тамбов-3",
                            "ActionSegmentationAndSource": "Сотрудникам",
                            "BonusActionUUId": "a2",
                            "ActionName": "Сотрудникам 2",
                            "PromocodeMasked": "EMP***",
                            "Discount": 50,
                            "SalesWithoutDiscount": 500,
                        },
                    ],
                }
            ]
        }

    monkeypatch.setattr(SupersetConnector, "invoke", fake_invoke)
    settings = make_settings(tmp_path, superset_base_url="https://analytics.dodois.io")
    app.dependency_overrides[analytics_settings_dep] = lambda: settings
    try:
        client = TestClient(app)
        response = client.post(
            "/analytics/employee-discount",
            json={
                "period": {"from": "2026-03-01", "to": "2026-03-31"},
                "unit_names": ["Тамбов-3"],
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["summary"]["employee_discount_amount"] == 150.5
    assert payload["summary"]["sales_without_discount"] == 1500
    assert payload["summary"]["discount_share_of_sales_without_discount_pct"] == 10.033333333333333
    assert payload["rows"][1]["promocode_masked"] == "EMP***"
    assert payload["superset"]["dashboard_id"] == 1410
    assert payload["superset"]["chart_id"] == 26708


def make_settings(
    tmp_path: Path,
    superset_base_url: str | None = None,
) -> Settings:
    return Settings(
        api_keys=[],
        tool_registry_path=Path("configs/tools.example.yaml"),
        policy_path=Path("configs/policy.example.yaml"),
        audit_db_path=tmp_path / "audit.sqlite3",
        dodo_access_token=None,
        dodo_pizzerias_path=None,
        superset_base_url=superset_base_url,
    )
