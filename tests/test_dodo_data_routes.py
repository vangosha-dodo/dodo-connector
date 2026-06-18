from pathlib import Path

import httpx
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
    assert "accounting_slice_writeoff_rate" in names
    assert "accounting_stock_consumptions_by_period" in names
    assert "accounting_writeoffs_products_summary" in names
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
    assert "to=2026-06-03" in payload["request"]["url"]
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


def test_dodo_accounting_sales_summary_aggregates_by_unit(tmp_path, monkeypatch) -> None:
    async def fake_invoke(self, tool, parameters, dry_run):  # noqa: ANN001
        del self, tool, dry_run
        unit = parameters["units"]
        skip = parameters["skip"]
        if unit == "unit-1" and skip == 0:
            return {
                "sales": [
                    {
                        "unitId": "unit-1",
                        "unitName": "Точка 1",
                        "products": [
                            {"price": 100, "priceWithDiscount": 80},
                            {"price": 50, "priceWithDiscount": 50},
                        ],
                    },
                    {
                        "unitId": "unit-1",
                        "unitName": "Точка 1",
                        "products": [{"price": 40, "priceWithDiscount": 30}],
                    },
                ]
            }
        if unit == "unit-2" and skip == 0:
            return {
                "sales": [
                    {
                        "unitId": "unit-2",
                        "unitName": "Точка 2",
                        "products": [{"price": 200, "priceWithDiscount": 180}],
                    }
                ]
            }
        return {"sales": []}

    monkeypatch.setattr(DodoConnector, "invoke", fake_invoke)
    settings = make_settings(tmp_path, dodo_access_token="token")
    app.dependency_overrides[dodo_data_settings_dep] = lambda: settings
    try:
        client = TestClient(app)
        response = client.get(
            "/dodo/accounting/sales/summary",
            params={
                "units": "unit-1,unit-2",
                "from": "2026-06-01",
                "to": "2026-06-01",
                "take": "2",
                "maxPagesPerUnit": "3",
                "concurrency": "2",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["function"] == "accounting_sales_summary"
    assert payload["complete"] is True
    assert payload["total"] == {
        "orders": 3,
        "products": 4,
        "salesWithDiscount": 340,
        "salesWithoutDiscount": 390,
        "discount": 50,
    }
    assert payload["units"] == [
        {
            "orders": 2,
            "products": 3,
            "salesWithDiscount": 160,
            "salesWithoutDiscount": 190,
            "discount": 30,
            "unitId": "unit-1",
            "unitName": "Точка 1",
            "source": {"rowsKey": "sales", "pagesFetched": 2, "truncated": False, "nextSkip": None},
        },
        {
            "orders": 1,
            "products": 1,
            "salesWithDiscount": 180,
            "salesWithoutDiscount": 200,
            "discount": 20,
            "unitId": "unit-2",
            "unitName": "Точка 2",
            "source": {"rowsKey": "sales", "pagesFetched": 1, "truncated": False, "nextSkip": None},
        },
    ]
    assert payload["source"]["rawRowsAggregated"] == 3
    assert payload["source"]["pagesFetched"] == 3


def test_dodo_accounting_writeoffs_products_dry_run_uses_exclusive_to_date(tmp_path) -> None:
    settings = make_settings(tmp_path)
    app.dependency_overrides[dodo_data_settings_dep] = lambda: settings
    try:
        client = TestClient(app)
        response = client.get(
            "/dodo/accounting/writeoffs/products",
            params={
                "units": "unit-1,unit-2",
                "from": "2026-06-16",
                "to": "2026-06-16",
                "dry_run": "true",
                "take": "100",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["function"] == "accounting_writeoffs_products"
    assert payload["dry_run"] is True
    assert "/accounting/write-offs/products" in payload["request"]["url"]
    assert "from=2026-06-16" in payload["request"]["url"]
    assert "to=2026-06-17" in payload["request"]["url"]


def test_dodo_accounting_writeoffs_products_summary_dry_run_uses_exclusive_to_date(tmp_path) -> None:
    settings = make_settings(tmp_path)
    app.dependency_overrides[dodo_data_settings_dep] = lambda: settings
    try:
        client = TestClient(app)
        response = client.get(
            "/dodo/accounting/writeoffs/products/summary",
            params={
                "units": "unit-1,unit-2",
                "from": "2026-06-16",
                "to": "2026-06-16",
                "dry_run": "true",
                "take": "100",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["function"] == "accounting_writeoffs_products_summary"
    assert payload["dry_run"] is True
    assert payload["filter"]["productNamePrefix"] == "Кус"
    assert "/accounting/write-offs/products" in payload["request"]["url"]
    assert "from=2026-06-16" in payload["request"]["url"]
    assert "to=2026-06-17" in payload["request"]["url"]


def test_dodo_accounting_writeoffs_products_summary_aggregates_slice_rows(tmp_path, monkeypatch) -> None:
    async def fake_invoke(self, tool, parameters, dry_run):  # noqa: ANN001
        del self, tool, dry_run
        assert parameters["skip"] == 0
        return {
            "writeOffs": [
                {
                    "unitName": "Тамбов-1",
                    "productName": "Кус Пепперони 1 шт",
                    "quantity": 2,
                    "pricePerPiece": 100,
                    "reason": "ExpiredShowcaseTime",
                    "ignored": "x",
                },
                {
                    "unitName": "Тамбов-1",
                    "productName": "Сырники 1 шт",
                    "quantity": 10,
                    "pricePerPiece": 50,
                    "reason": "Other",
                },
                {
                    "unitName": "Тамбов-1",
                    "productName": "Кус Бекон BBQ 1 шт",
                    "quantity": "3",
                    "pricePerPiece": "80",
                    "reason": "ShowcaseWriteOff",
                },
                {
                    "unitName": "Чита-1",
                    "productName": "кус Песто 1 шт",
                    "quantity": 1.5,
                    "pricePerPiece": 90,
                    "reason": "ExpiredShowcaseTime",
                },
            ]
        }

    monkeypatch.setattr(DodoConnector, "invoke", fake_invoke)
    settings = make_settings(tmp_path, dodo_access_token="token")
    app.dependency_overrides[dodo_data_settings_dep] = lambda: settings
    try:
        client = TestClient(app)
        response = client.get(
            "/dodo/accounting/writeoffs/products/summary",
            params={
                "units": "unit-1,unit-2",
                "from": "2026-06-16",
                "to": "2026-06-16",
                "take": "10",
                "max_pages": "1",
                "includeProducts": "true",
                "includeReasons": "true",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["function"] == "accounting_writeoffs_products_summary"
    assert "rows" not in payload
    assert payload["source"]["row_count"] == 4
    assert payload["matched_row_count"] == 3
    assert payload["total"] == {"quantity": 6.5, "amount": 575, "rows": 3}
    assert payload["units"] == [
        {
            "unitName": "Тамбов-1",
            "quantity": 5,
            "amount": 440,
            "rows": 2,
            "products": [
                {"productName": "Кус Бекон BBQ 1 шт", "quantity": 3, "amount": 240, "rows": 1},
                {"productName": "Кус Пепперони 1 шт", "quantity": 2, "amount": 200, "rows": 1},
            ],
            "reasons": [
                {"reason": "ShowcaseWriteOff", "quantity": 3, "amount": 240, "rows": 1},
                {"reason": "ExpiredShowcaseTime", "quantity": 2, "amount": 200, "rows": 1},
            ],
        },
        {
            "unitName": "Чита-1",
            "quantity": 1.5,
            "amount": 135,
            "rows": 1,
            "products": [{"productName": "кус Песто 1 шт", "quantity": 1.5, "amount": 135, "rows": 1}],
            "reasons": [{"reason": "ExpiredShowcaseTime", "quantity": 1.5, "amount": 135, "rows": 1}],
        },
    ]


def test_dodo_accounting_slices_writeoff_rate_dry_run_plans_sales_and_writeoffs(tmp_path) -> None:
    settings = make_settings(tmp_path)
    app.dependency_overrides[dodo_data_settings_dep] = lambda: settings
    try:
        client = TestClient(app)
        response = client.get(
            "/dodo/accounting/slices/writeoff-rate",
            params={
                "units": "unit-1,unit-2",
                "from": "2026-06-16",
                "to": "2026-06-16",
                "dry_run": "true",
                "take": "100",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["function"] == "accounting_slice_writeoff_rate"
    assert payload["dry_run"] is True
    assert payload["filter"]["productNamePrefix"] == "Кус"
    assert "/accounting/write-offs/products" in payload["requests"]["writeoffs"]["url"]
    assert "/accounting/sales" in payload["requests"]["sales"]["url"]
    assert "from=2026-06-16" in payload["requests"]["sales"]["url"]
    assert "to=2026-06-17" in payload["requests"]["sales"]["url"]
    assert "to=2026-06-17" in payload["requests"]["writeoffs"]["url"]


def test_dodo_accounting_slices_writeoff_rate_aggregates_sales_and_writeoffs(tmp_path, monkeypatch) -> None:
    async def fake_invoke(self, tool, parameters, dry_run):  # noqa: ANN001
        del self, parameters, dry_run
        if tool.name == "dodo_accounting_writeoffs_products":
            return {
                "writeOffs": [
                    {
                        "unitName": "Тамбов-1",
                        "productName": "Кус Пепперони 1 шт",
                        "quantity": 2,
                        "pricePerPiece": 100,
                    },
                    {
                        "unitName": "Тамбов-1",
                        "productName": "Кус Песто 1 шт",
                        "quantity": 1,
                        "pricePerPiece": 90,
                    },
                    {
                        "unitName": "Тамбов-1",
                        "productName": "Сырники 1 шт",
                        "quantity": 9,
                        "pricePerPiece": 50,
                    },
                    {
                        "unitName": "Чита-1",
                        "productName": "Кус Пепперони 1 шт",
                        "quantity": 3,
                        "pricePerPiece": 100,
                    },
                ]
            }
        if tool.name == "dodo_accounting_sales":
            return {
                "sales": [
                    {
                        "unitName": "Тамбов-1",
                        "products": [
                            {"defaultProductName": "Кус Пепперони 1 шт", "priceWithDiscount": 100},
                            {"defaultProductName": "Кус Пепперони 1 шт", "priceWithDiscount": 100},
                            {"defaultProductName": "Кус Песто 1 шт", "priceWithDiscount": 80},
                            {"defaultProductName": "Напиток", "priceWithDiscount": 70},
                        ],
                    },
                    {
                        "unitName": "Тамбов-1",
                        "products": [
                            {"defaultProductName": "Кус Песто 1 шт", "price": 90, "quantity": 2},
                        ],
                    },
                    {
                        "unitName": "Чита-1",
                        "products": [
                            {"defaultProductName": "Кус Пепперони 1 шт", "priceWithDiscount": 100},
                        ],
                    },
                ]
            }
        raise AssertionError(tool.name)

    monkeypatch.setattr(DodoConnector, "invoke", fake_invoke)
    settings = make_settings(tmp_path, dodo_access_token="token")
    app.dependency_overrides[dodo_data_settings_dep] = lambda: settings
    try:
        client = TestClient(app)
        response = client.get(
            "/dodo/accounting/slices/writeoff-rate",
            params={
                "units": "unit-1,unit-2",
                "from": "2026-06-16",
                "to": "2026-06-16",
                "take": "10",
                "max_pages": "1",
                "includeProducts": "true",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["function"] == "accounting_slice_writeoff_rate"
    assert payload["total"]["soldQuantity"] == 6
    assert payload["total"]["writeoffQuantity"] == 6
    assert payload["total"]["laidOutQuantity"] == 12
    assert payload["total"]["writeoffPercent"] == 50
    assert payload["units"][0]["unitName"] == "Тамбов-1"
    assert payload["units"][0]["soldQuantity"] == 5
    assert payload["units"][0]["writeoffQuantity"] == 3
    assert payload["units"][0]["laidOutQuantity"] == 8
    assert payload["units"][0]["writeoffPercent"] == 37.5
    assert payload["units"][0]["salesRowsWithSlices"] == 2
    assert payload["units"][1]["unitName"] == "Чита-1"
    assert payload["units"][1]["writeoffPercent"] == 75
    assert "rows" not in payload
    assert payload["source"]["sales"]["row_count"] == 3
    assert payload["source"]["writeoffs"]["row_count"] == 4


def test_dodo_data_external_http_error_returns_controlled_response(tmp_path, monkeypatch) -> None:
    async def fake_invoke(self, tool, parameters, dry_run):  # noqa: ANN001
        del self, tool, parameters, dry_run
        request = httpx.Request("GET", "https://api.dodois.io/example")
        response = httpx.Response(
            400,
            json={
                "code": "ValidationError",
                "message": "Bad query",
                "details": {"errors": [{"message": "From should be less than To."}]},
            },
            request=request,
        )
        raise httpx.HTTPStatusError("Bad Request", request=request, response=response)

    monkeypatch.setattr(DodoConnector, "invoke", fake_invoke)
    settings = make_settings(tmp_path, dodo_access_token="token")
    app.dependency_overrides[dodo_data_settings_dep] = lambda: settings
    try:
        client = TestClient(app)
        response = client.get(
            "/dodo/accounting/sales",
            params={
                "units": "unit-1",
                "from": "2026-06-16",
                "to": "2026-06-16",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert detail["error"] == "external_http_error"
    assert detail["tool_name"] == "dodo_accounting_sales"
    assert detail["external_status"] == 400
    assert detail["external_code"] == "ValidationError"
    assert detail["external_message"] == "Bad query"
    assert detail["external_details"]["errors"][0]["message"] == "From should be less than To."


def test_dodo_data_external_timeout_returns_gateway_timeout(tmp_path, monkeypatch) -> None:
    async def fake_invoke(self, tool, parameters, dry_run):  # noqa: ANN001
        del self, tool, parameters, dry_run
        raise httpx.ReadTimeout("Dodo API was too slow")

    monkeypatch.setattr(DodoConnector, "invoke", fake_invoke)
    settings = make_settings(tmp_path, dodo_access_token="token")
    app.dependency_overrides[dodo_data_settings_dep] = lambda: settings
    try:
        client = TestClient(app)
        response = client.get(
            "/dodo/accounting/sales",
            params={
                "units": "unit-1",
                "from": "2026-06-16",
                "to": "2026-06-16",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 504
    detail = response.json()["detail"]
    assert detail["error"] == "external_timeout"
    assert detail["tool_name"] == "dodo_accounting_sales"
    assert detail["exception"] == "ReadTimeout"
    assert "Split the request" in detail["hint"]


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
