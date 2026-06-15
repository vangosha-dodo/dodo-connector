from pathlib import Path

from fastapi.testclient import TestClient

from dodo_bridge.config import Settings
from dodo_bridge.connectors.dodo import DodoConnector
from dodo_bridge.dodo_data_routes import settings_dep as dodo_data_settings_dep
from dodo_bridge.main import app


def test_dodo_functions_list(tmp_path) -> None:
    settings = make_settings(tmp_path)
    app.dependency_overrides[dodo_data_settings_dep] = lambda: settings
    try:
        client = TestClient(app)
        response = client.get("/dodo/functions")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    names = {item["name"] for item in response.json()["functions"]}
    assert "accounting_sales" in names
    assert "courier_orders" in names


def test_dodo_accounting_sales_dry_run(tmp_path) -> None:
    settings = make_settings(tmp_path)
    app.dependency_overrides[dodo_data_settings_dep] = lambda: settings
    try:
        client = TestClient(app)
        response = client.get(
            "/dodo/accounting/sales",
            params={
                "units": "unit-1,unit-2",
                "from": "2026-06-01",
                "to": "2026-06-02",
                "dry_run": "true",
                "take": "100",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["function"] == "accounting_sales"
    assert payload["dry_run"] is True
    assert "/accounting/sales" in payload["request"]["url"]
    assert "take=100" in payload["request"]["url"]


def test_dodo_accounting_sales_paginates_and_projects(tmp_path, monkeypatch) -> None:
    async def fake_invoke(self, tool, parameters, dry_run):  # noqa: ANN001
        del self, tool, dry_run
        if parameters["skip"] == 0:
            return {
                "sales": [
                    {"id": "s1", "amount": 10, "internal": "x"},
                    {"id": "s2", "amount": 20, "internal": "y"},
                ]
            }
        return {"sales": [{"id": "s3", "amount": 30, "internal": "z"}]}

    monkeypatch.setattr(DodoConnector, "invoke", fake_invoke)
    settings = make_settings(tmp_path, dodo_access_token="token")
    app.dependency_overrides[dodo_data_settings_dep] = lambda: settings
    try:
        client = TestClient(app)
        response = client.get(
            "/dodo/accounting/sales",
            params={
                "units": "unit-1",
                "from": "2026-06-01",
                "to": "2026-06-02",
                "take": "2",
                "max_pages": "2",
                "fields": "id,amount",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["row_count"] == 3
    assert payload["pages_fetched"] == 2
    assert payload["rows"] == [
        {"id": "s1", "amount": 10},
        {"id": "s2", "amount": 20},
        {"id": "s3", "amount": 30},
    ]


def test_dodo_data_rejects_too_large_period(tmp_path) -> None:
    settings = make_settings(tmp_path, dodo_data_max_period_days=1)
    app.dependency_overrides[dodo_data_settings_dep] = lambda: settings
    try:
        client = TestClient(app)
        response = client.get(
            "/dodo/accounting/sales",
            params={
                "units": "unit-1",
                "from": "2026-06-01",
                "to": "2026-06-03",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert "Period is too large" in response.json()["detail"]


def make_settings(
    tmp_path: Path,
    dodo_access_token: str | None = None,
    dodo_data_max_period_days: int = 92,
) -> Settings:
    return Settings(
        api_keys=[],
        tool_registry_path=Path("configs/tools.example.yaml"),
        policy_path=Path("configs/policy.example.yaml"),
        audit_db_path=tmp_path / "audit.sqlite3",
        dodo_access_token=dodo_access_token,
        dodo_data_max_period_days=dodo_data_max_period_days,
        dodo_pizzerias_path=None,
    )
