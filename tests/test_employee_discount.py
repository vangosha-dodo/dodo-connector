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


def test_kiosk_sales_share_dry_run_builds_superset_request(tmp_path) -> None:
    settings = make_settings(tmp_path)
    app.dependency_overrides[analytics_settings_dep] = lambda: settings
    try:
        client = TestClient(app)
        response = client.post(
            "/analytics/kiosk-sales-share",
            json={
                "month": "2026-05",
                "unit_names": ["Тамбов-1"],
                "dry_run": True,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "dry_run"
    assert payload["capability_id"] == "get_kiosk_sales_share"
    assert payload["request"]["method"] == "POST"
    assert payload["request"]["url"].endswith("/api/v1/chart/data?dashboard_id=714")
    body = payload["request"]["json"]
    assert body["form_data"]["slice_id"] == 9533
    assert body["datasource"] == {"id": 168, "type": "table"}
    assert body["queries"][0]["filters"][0] == {
        "col": "UnitName",
        "op": "IN",
        "val": ["Тамбов-1"],
    }
    assert body["queries"][0]["metrics"] == ["Share sales via Kiosk"]
    assert body["queries"][0]["time_range"] == "2026-05-01 : 2026-06-01"


def test_kiosk_sales_share_normalizes_superset_rows(tmp_path, monkeypatch) -> None:
    async def fake_invoke(self, tool, parameters, dry_run):  # noqa: ANN001
        del self, tool, parameters, dry_run
        return {
            "result": [
                {
                    "rowcount": 2,
                    "is_cached": False,
                    "data": [
                        {"UnitName": "Тамбов-1", "Share sales via Kiosk": 0.25},
                        {"UnitName": "Тамбов-2", "Share sales via Kiosk": 0.1},
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
            "/analytics/kiosk-sales-share",
            json={
                "month": "2026-05",
                "unit_names": ["Тамбов-1", "Тамбов-2"],
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["summary"]["rows_count"] == 2
    assert payload["summary"]["average_kiosk_sales_share_pct"] == 17.5
    assert payload["rows"] == [
        {"unit_name": "Тамбов-1", "kiosk_sales_share": 0.25, "kiosk_sales_share_pct": 25.0},
        {"unit_name": "Тамбов-2", "kiosk_sales_share": 0.1, "kiosk_sales_share_pct": 10.0},
    ]
    assert payload["superset"]["dashboard_id"] == 714
    assert payload["superset"]["chart_id"] == 9533
    assert payload["superset"]["metric"] == "Share sales via Kiosk"


def test_clients_phone_share_dry_run_builds_superset_request(tmp_path) -> None:
    settings = make_settings(tmp_path)
    app.dependency_overrides[analytics_settings_dep] = lambda: settings
    try:
        client = TestClient(app)
        response = client.post(
            "/analytics/clients-phone-share",
            json={
                "month": "2026-05",
                "unit_names": ["Тамбов-1"],
                "dry_run": True,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "dry_run"
    assert payload["capability_id"] == "get_clients_phone_share"
    assert payload["request"]["method"] == "POST"
    assert payload["request"]["url"].endswith("/superset/api/v1/chart/data?dashboard_id=868")
    assert payload["request"]["url"].startswith("https://officemanager.dodois.io")
    body = payload["request"]["json"]
    assert body["form_data"]["slice_id"] == 18721
    assert body["datasource"] == {"id": 1615, "type": "table"}
    assert body["queries"][0]["filters"][0] == {
        "col": "UnitName",
        "op": "IN",
        "val": ["Тамбов-1"],
    }
    assert body["queries"][0]["metrics"] == [
        "Share of dine in identified orders via cashier",
        "Count dine in identified orders via cashier",
        "Count dine in orders via cashier",
    ]
    assert body["queries"][0]["time_range"] == "2026-05-01 : 2026-06-01"


def test_clients_phone_share_normalizes_superset_rows(tmp_path, monkeypatch) -> None:
    async def fake_invoke(self, tool, parameters, dry_run):  # noqa: ANN001
        del self, tool, parameters, dry_run
        return {
            "result": [
                {
                    "rowcount": 2,
                    "is_cached": False,
                    "data": [
                        {
                            "UnitName": "Тамбов-1",
                            "Share of dine in identified orders via cashier": 0.08,
                            "Count dine in identified orders via cashier": 16,
                            "Count dine in orders via cashier": 200,
                        },
                        {
                            "UnitName": "Тамбов-2",
                            "Share of dine in identified orders via cashier": 0.1,
                            "Count dine in identified orders via cashier": 25,
                            "Count dine in orders via cashier": 250,
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
            "/analytics/clients-phone-share",
            json={
                "month": "2026-05",
                "unit_names": ["Тамбов-1", "Тамбов-2"],
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["summary"]["rows_count"] == 2
    assert payload["summary"]["average_identified_orders_share_pct"] == 9.0
    assert payload["rows"] == [
        {
            "unit_name": "Тамбов-1",
            "identified_orders_share": 0.08,
            "identified_orders_share_pct": 8.0,
            "identified_orders_count": 16.0,
            "orders_count": 200.0,
        },
        {
            "unit_name": "Тамбов-2",
            "identified_orders_share": 0.1,
            "identified_orders_share_pct": 10.0,
            "identified_orders_count": 25.0,
            "orders_count": 250.0,
        },
    ]
    assert payload["superset"]["dashboard_id"] == 868
    assert payload["superset"]["chart_id"] == 18721
    assert payload["superset"]["metric"] == "Share of dine in identified orders via cashier"


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
