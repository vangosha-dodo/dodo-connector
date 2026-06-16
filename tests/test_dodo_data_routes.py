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
    assert "accounting_inventory_stocks" in names
    assert "accounting_stock_consumptions_by_period" in names
    assert "courier_orders" in names
    assert "ratings_customer_experience" in names
    assert "staff_vacancies_count" in names
    assert "units_month_goals" in names


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


def test_dodo_accounting_inventory_stocks_dry_run(tmp_path) -> None:
    settings = make_settings(tmp_path)
    app.dependency_overrides[dodo_data_settings_dep] = lambda: settings
    try:
        client = TestClient(app)
        response = client.get(
            "/dodo/accounting/inventory-stocks",
            params={
                "units": "unit-1",
                "from": "2026-06-01",
                "to": "2026-06-02",
                "dry_run": "true",
                "take": "1",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["function"] == "accounting_inventory_stocks"
    assert payload["dry_run"] is True
    assert "/accounting/inventory-stocks" in payload["request"]["url"]
    assert "take=1" in payload["request"]["url"]


def test_dodo_accounting_inventory_stocks_paginates_and_projects(tmp_path, monkeypatch) -> None:
    async def fake_invoke(self, tool, parameters, dry_run):  # noqa: ANN001
        del self, tool, dry_run
        if parameters["skip"] == 0:
            return {
                "stocks": [
                    {"id": "i1", "name": "Cheese", "quantity": 10, "daysUntilBalanceRunsOut": 3},
                    {"id": "i2", "name": "Tomato", "quantity": 20, "daysUntilBalanceRunsOut": 5},
                ]
            }
        return {
            "stocks": [
                {"id": "i3", "name": "Sauce", "quantity": 30, "daysUntilBalanceRunsOut": 7},
            ]
        }

    monkeypatch.setattr(DodoConnector, "invoke", fake_invoke)
    settings = make_settings(tmp_path, dodo_access_token="token")
    app.dependency_overrides[dodo_data_settings_dep] = lambda: settings
    try:
        client = TestClient(app)
        response = client.get(
            "/dodo/accounting/inventory-stocks",
            params={
                "units": "unit-1",
                "from": "2026-06-01",
                "to": "2026-06-02",
                "take": "2",
                "max_pages": "2",
                "fields": "id,quantity,daysUntilBalanceRunsOut",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["row_count"] == 3
    assert payload["pages_fetched"] == 2
    assert payload["rows"] == [
        {"id": "i1", "quantity": 10, "daysUntilBalanceRunsOut": 3},
        {"id": "i2", "quantity": 20, "daysUntilBalanceRunsOut": 5},
        {"id": "i3", "quantity": 30, "daysUntilBalanceRunsOut": 7},
    ]


def test_dodo_accounting_stock_consumptions_by_period_dry_run(tmp_path) -> None:
    settings = make_settings(tmp_path)
    app.dependency_overrides[dodo_data_settings_dep] = lambda: settings
    try:
        client = TestClient(app)
        response = client.get(
            "/dodo/accounting/stock-consumptions-by-period",
            params={
                "units": "unit-1",
                "from": "2026-06-01",
                "to": "2026-06-02",
                "dry_run": "true",
                "take": "1",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["function"] == "accounting_stock_consumptions_by_period"
    assert payload["dry_run"] is True
    assert "/accounting/stock-consumptions-by-period" in payload["request"]["url"]
    assert "take=1" in payload["request"]["url"]


def test_dodo_accounting_stock_consumptions_by_period_paginates_and_projects(tmp_path, monkeypatch) -> None:
    async def fake_invoke(self, tool, parameters, dry_run):  # noqa: ANN001
        del self, tool, dry_run
        if parameters["skip"] == 0:
            return {
                "consumptions": [
                    {
                        "stockItemName": "Cheese",
                        "quantity": 10,
                        "costWithVat": 100,
                        "costWithoutVat": 83,
                        "currency": "RUB",
                    },
                    {
                        "stockItemName": "Tomato",
                        "quantity": 20,
                        "costWithVat": 200,
                        "costWithoutVat": 167,
                        "currency": "RUB",
                    },
                ]
            }
        return {
            "consumptions": [
                {
                    "stockItemName": "Sauce",
                    "quantity": 30,
                    "costWithVat": 300,
                    "costWithoutVat": 250,
                    "currency": "RUB",
                },
            ]
        }

    monkeypatch.setattr(DodoConnector, "invoke", fake_invoke)
    settings = make_settings(tmp_path, dodo_access_token="token")
    app.dependency_overrides[dodo_data_settings_dep] = lambda: settings
    try:
        client = TestClient(app)
        response = client.get(
            "/dodo/accounting/stock-consumptions-by-period",
            params={
                "units": "unit-1",
                "from": "2026-06-01",
                "to": "2026-06-02",
                "take": "2",
                "max_pages": "2",
                "fields": "stockItemName,quantity,costWithVat",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["row_count"] == 3
    assert payload["pages_fetched"] == 2
    assert payload["rows"] == [
        {"stockItemName": "Cheese", "quantity": 10, "costWithVat": 100},
        {"stockItemName": "Tomato", "quantity": 20, "costWithVat": 200},
        {"stockItemName": "Sauce", "quantity": 30, "costWithVat": 300},
    ]


def test_dodo_units_month_goals_dry_run(tmp_path) -> None:
    settings = make_settings(tmp_path)
    app.dependency_overrides[dodo_data_settings_dep] = lambda: settings
    try:
        client = TestClient(app)
        response = client.get(
            "/dodo/units/month-goals",
            params={
                "unit": "unit-1",
                "month": "6",
                "year": "2026",
                "dry_run": "true",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["function"] == "units_month_goals"
    assert payload["dry_run"] is True
    assert "/units/month-goals" in payload["request"]["url"]
    assert "unit=unit-1" in payload["request"]["url"]
    assert "month=6" in payload["request"]["url"]
    assert "year=2026" in payload["request"]["url"]


def test_dodo_units_month_goals_returns_raw_response(tmp_path, monkeypatch) -> None:
    async def fake_invoke(self, tool, parameters, dry_run):  # noqa: ANN001
        del self, tool, dry_run
        assert parameters == {"unit": "unit-1", "month": 6, "year": 2026}
        return {
            "sales": 100000,
            "deliverySales": 25000,
            "leakage": 3,
            "defectiveProduct": 2,
        }

    monkeypatch.setattr(DodoConnector, "invoke", fake_invoke)
    settings = make_settings(tmp_path, dodo_access_token="token")
    app.dependency_overrides[dodo_data_settings_dep] = lambda: settings
    try:
        client = TestClient(app)
        response = client.get(
            "/dodo/units/month-goals",
            params={
                "unit": "unit-1",
                "month": "6",
                "year": "2026",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["function"] == "units_month_goals"
    assert payload["row_count"] is None
    assert payload["rows_key"] is None
    assert payload["response"] == {
        "sales": 100000,
        "deliverySales": 25000,
        "leakage": 3,
        "defectiveProduct": 2,
    }


def test_dodo_staff_vacancies_count_dry_run(tmp_path) -> None:
    settings = make_settings(tmp_path)
    app.dependency_overrides[dodo_data_settings_dep] = lambda: settings
    try:
        client = TestClient(app)
        response = client.get(
            "/dodo/staff/vacancies/count",
            params={
                "countryCode": "643",
                "dry_run": "true",
                "take": "2",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["function"] == "staff_vacancies_count"
    assert payload["dry_run"] is True
    assert "/staff/vacancies/count" in payload["request"]["url"]
    assert "countryCode=643" in payload["request"]["url"]
    assert "take=2" in payload["request"]["url"]


def test_dodo_staff_vacancies_count_paginates_and_projects(tmp_path, monkeypatch) -> None:
    async def fake_invoke(self, tool, parameters, dry_run):  # noqa: ANN001
        del self, tool, dry_run
        if parameters["skip"] == 0:
            return {
                "vacancies": [
                    {"id": "u1", "name": "One", "vacanciesCount": 4, "address": "A"},
                    {"id": "u2", "name": "Two", "vacanciesCount": 2, "address": "B"},
                ]
            }
        return {"vacancies": [{"id": "u3", "name": "Three", "vacanciesCount": 1, "address": "C"}]}

    monkeypatch.setattr(DodoConnector, "invoke", fake_invoke)
    settings = make_settings(tmp_path, dodo_access_token="token")
    app.dependency_overrides[dodo_data_settings_dep] = lambda: settings
    try:
        client = TestClient(app)
        response = client.get(
            "/dodo/staff/vacancies/count",
            params={
                "countryCode": "643",
                "take": "2",
                "max_pages": "2",
                "fields": "id,vacanciesCount",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["row_count"] == 3
    assert payload["pages_fetched"] == 2
    assert payload["rows"] == [
        {"id": "u1", "vacanciesCount": 4},
        {"id": "u2", "vacanciesCount": 2},
        {"id": "u3", "vacanciesCount": 1},
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


def test_dodo_ratings_customer_experience_dry_run(tmp_path) -> None:
    settings = make_settings(tmp_path)
    app.dependency_overrides[dodo_data_settings_dep] = lambda: settings
    try:
        client = TestClient(app)
        response = client.get(
            "/dodo/ratings/customer-experience",
            params={
                "countryCode": "643",
                "dry_run": "true",
                "take": "1",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["function"] == "ratings_customer_experience"
    assert payload["dry_run"] is True
    assert "/controlling/ratings/customer-experience" in payload["request"]["url"]
    assert "countryCode=643" in payload["request"]["url"]
    assert "take=1" in payload["request"]["url"]


def test_dodo_ratings_standards_paginates_and_keeps_meta(tmp_path, monkeypatch) -> None:
    async def fake_invoke(self, tool, parameters, dry_run):  # noqa: ANN001
        del self, tool, dry_run
        base = {
            "periodFrom": "2026-06-08",
            "periodTo": "2026-06-14",
            "publishStatus": "Published",
            "publishedAt": "2026-06-15T16:19:01",
        }
        if parameters["skip"] == 0:
            return {
                **base,
                "unitRates": [
                    {"unitId": "u1", "unitName": "One", "rate": 90},
                    {"unitId": "u2", "unitName": "Two", "rate": 80},
                ],
            }
        return {
            **base,
            "unitRates": [{"unitId": "u3", "unitName": "Three", "rate": 70}],
        }

    monkeypatch.setattr(DodoConnector, "invoke", fake_invoke)
    settings = make_settings(tmp_path, dodo_access_token="token")
    app.dependency_overrides[dodo_data_settings_dep] = lambda: settings
    try:
        client = TestClient(app)
        response = client.get(
            "/dodo/ratings/standards",
            params={
                "countryCode": "643",
                "take": "2",
                "max_pages": "2",
                "fields": "unitId,rate",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["function"] == "ratings_standards"
    assert payload["row_count"] == 3
    assert payload["pages_fetched"] == 2
    assert payload["meta"] == {
        "periodFrom": "2026-06-08",
        "periodTo": "2026-06-14",
        "publishStatus": "Published",
        "publishedAt": "2026-06-15T16:19:01",
    }
    assert payload["rows"] == [
        {"unitId": "u1", "rate": 90},
        {"unitId": "u2", "rate": 80},
        {"unitId": "u3", "rate": 70},
    ]


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
