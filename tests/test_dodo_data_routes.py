import json
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
    assert "accounting_slice_daily_dynamics" in names
    assert "accounting_sales_channels_summary" in names
    assert "accounting_sales_discounts_summary" in names
    assert "accounting_sales_comparison" in names
    assert "accounting_stock_consumptions_by_period" in names
    assert "accounting_writeoffs_products_summary" in names
    assert "courier_orders" in names
    assert "orders_clients_statistics" in names
    assert "production_orders_handover_time" in names
    assert "production_productivity" in names
    assert "ratings_customer_experience" in names
    assert "ratings_customer_experience_summary" in names
    assert "staff_vacancies_count" in names
    assert "units_month_goals" in names
    assert "ratings_standards_summary" in names


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


def test_dodo_orders_clients_statistics_dry_run_uses_dodo_date_params(tmp_path) -> None:
    settings = make_settings(tmp_path)
    app.dependency_overrides[dodo_data_settings_dep] = lambda: settings
    try:
        client = TestClient(app)
        response = client.get(
            "/dodo/orders/clients-statistics",
            params={
                "units": "unit-1,unit-2",
                "from": "2026-06-01",
                "to": "2026-06-30",
                "dry_run": "true",
                "take": "100",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["function"] == "orders_clients_statistics"
    assert payload["dry_run"] is True
    assert "/orders/clients-statistics" in payload["request"]["url"]
    assert "units=unit-1%2Cunit-2" in payload["request"]["url"]
    assert "fromDate=2026-06-01" in payload["request"]["url"]
    assert "toDate=2026-06-30" in payload["request"]["url"]
    assert "take=100" in payload["request"]["url"]


def test_dodo_production_productivity_dry_run(tmp_path) -> None:
    settings = make_settings(tmp_path)
    app.dependency_overrides[dodo_data_settings_dep] = lambda: settings
    try:
        client = TestClient(app)
        response = client.get(
            "/dodo/production/productivity",
            params={
                "units": "unit-1",
                "from": "2026-06-01",
                "to": "2026-06-07",
                "dry_run": "true",
                "take": "50",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["function"] == "production_productivity"
    assert payload["dry_run"] is True
    assert "/production/productivity" in payload["request"]["url"]
    assert "from=2026-06-01" in payload["request"]["url"]
    assert "to=2026-06-07" in payload["request"]["url"]
    assert "take=50" in payload["request"]["url"]


def test_dodo_production_orders_handover_time_dry_run(tmp_path) -> None:
    settings = make_settings(tmp_path)
    app.dependency_overrides[dodo_data_settings_dep] = lambda: settings
    try:
        client = TestClient(app)
        response = client.get(
            "/dodo/production/orders-handover-time",
            params={
                "units": "unit-1",
                "from": "2026-06-01",
                "to": "2026-06-07",
                "dry_run": "true",
                "take": "50",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["function"] == "production_orders_handover_time"
    assert payload["dry_run"] is True
    assert "/production/orders-handover-time" in payload["request"]["url"]
    assert "from=2026-06-01" in payload["request"]["url"]
    assert "to=2026-06-07" in payload["request"]["url"]
    assert "take=50" in payload["request"]["url"]


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
        "averageCheck": 113.33,
    }
    assert payload["units"] == [
        {
            "orders": 2,
            "products": 3,
            "salesWithDiscount": 160,
            "salesWithoutDiscount": 190,
            "discount": 30,
            "averageCheck": 80,
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
            "averageCheck": 180,
            "unitId": "unit-2",
            "unitName": "Точка 2",
            "source": {"rowsKey": "sales", "pagesFetched": 1, "truncated": False, "nextSkip": None},
        },
    ]
    assert payload["source"]["rawRowsAggregated"] == 3
    assert payload["source"]["pagesFetched"] == 3


def test_dodo_accounting_sales_channels_summary_groups_sources_and_scores(tmp_path, monkeypatch) -> None:
    rows_by_unit = {
        "unit-1": [
            {
                "unitId": "unit-1",
                "unitName": "Точка 1",
                "salesChannel": "Dine-in",
                "orderSource": "Dine-in",
                "products": [{"price": 100, "priceWithDiscount": 100}],
            },
            {
                "unitId": "unit-1",
                "unitName": "Точка 1",
                "salesChannel": "Dine-in",
                "orderSource": "Kiosk",
                "products": [{"price": 200, "priceWithDiscount": 180}],
            },
            {
                "unitId": "unit-1",
                "unitName": "Точка 1",
                "salesChannel": "Delivery",
                "orderSource": "MobileApp",
                "products": [{"price": 150, "priceWithDiscount": 120}],
            },
        ],
        "unit-2": [
            {
                "unitId": "unit-2",
                "unitName": "Точка 2",
                "salesChannel": "Dine-in",
                "orderSource": "Kiosk",
                "products": [{"price": 50, "priceWithDiscount": 40}],
            },
            {
                "unitId": "unit-2",
                "unitName": "Точка 2",
                "salesChannel": "Delivery",
                "orderSource": "MobileApp",
                "products": [{"price": 60, "priceWithDiscount": 60}],
            },
            {
                "unitId": "unit-2",
                "unitName": "Точка 2",
                "salesChannel": "Delivery",
                "orderSource": "CallCenter",
                "products": [{"price": 70, "priceWithDiscount": 70}],
            },
        ],
    }

    async def fake_invoke(self, tool, parameters, dry_run):  # noqa: ANN001
        del self, tool, dry_run
        if parameters["skip"] != 0:
            return {"sales": []}
        return {"sales": rows_by_unit[parameters["units"]]}

    monkeypatch.setattr(DodoConnector, "invoke", fake_invoke)
    settings = make_settings(tmp_path, dodo_access_token="token")
    app.dependency_overrides[dodo_data_settings_dep] = lambda: settings
    try:
        client = TestClient(app)
        response = client.get(
            "/dodo/accounting/sales/channels-summary",
            params={
                "units": "unit-1,unit-2",
                "from": "2026-06-01",
                "to": "2026-06-01",
                "take": "100",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["function"] == "accounting_sales_channels_summary"
    assert payload["total"]["orders"] == 6
    assert payload["total"]["salesWithDiscount"] == 570
    assert payload["total"]["averageOrdersPerDay"] == 6
    unit_1 = next(unit for unit in payload["units"] if unit["unitId"] == "unit-1")
    unit_2 = next(unit for unit in payload["units"] if unit["unitId"] == "unit-2")

    assert "unitId" not in unit_1["total"]
    assert "unitName" not in unit_1["total"]
    dine_in = next(channel for channel in unit_1["salesChannels"] if channel["salesChannel"] == "Dine-in")
    delivery = next(channel for channel in unit_1["salesChannels"] if channel["salesChannel"] == "Delivery")
    kiosk = next(source for source in unit_1["orderSources"] if source["orderSource"] == "Kiosk")
    assert dine_in["orders"] == 2
    assert delivery["orders"] == 1
    assert kiosk["salesWithDiscount"] == 180
    assert unit_1["kioskShare"]["shareOfRestaurantOrdersPercent"] == 50
    assert unit_1["kioskShare"]["shareOfRestaurantSalesPercent"] == 64.3
    assert unit_1["zScores"]["restaurantOrdersPerDayZScore"] == 1
    assert unit_1["zScores"]["deliveryOrdersPerDayZScore"] == -1
    assert unit_2["zScores"]["restaurantOrdersPerDayZScore"] == -1
    assert unit_2["zScores"]["deliveryOrdersPerDayZScore"] == 1
    assert payload["source"]["pagesFetched"] == 2


def test_dodo_accounting_sales_channels_summary_defaults_to_all_pizzerias(tmp_path, monkeypatch) -> None:
    pizzerias_path = tmp_path / "pizzerias.json"
    pizzerias_path.write_text(
        json.dumps(
            [
                {"id": "unit-1", "name": "Точка 1", "unitType": 1},
                {"id": "unit-2", "name": "Точка 2", "unitType": 1},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    calls = []

    async def fake_invoke(self, tool, parameters, dry_run):  # noqa: ANN001
        del self, tool, dry_run
        calls.append((parameters["units"], parameters["skip"]))
        if parameters["skip"] != 0:
            return {"sales": []}
        return {
            "sales": [
                {
                    "unitId": parameters["units"],
                    "unitName": f"Name {parameters['units']}",
                    "salesChannel": "Dine-in",
                    "orderSource": "Kiosk",
                    "products": [{"price": 100, "priceWithDiscount": 90}],
                }
            ]
        }

    monkeypatch.setattr(DodoConnector, "invoke", fake_invoke)
    settings = make_settings(tmp_path, dodo_access_token="token", dodo_pizzerias_path=pizzerias_path)
    app.dependency_overrides[dodo_data_settings_dep] = lambda: settings
    try:
        client = TestClient(app)
        response = client.get(
            "/dodo/accounting/sales/channels-summary",
            params={
                "from": "2026-06-01",
                "to": "2026-06-01",
                "take": "100",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"]["orders"] == 2
    assert {unit["unitId"] for unit in payload["units"]} == {"unit-1", "unit-2"}
    assert calls == [("unit-1", 0), ("unit-2", 0)]


def test_dodo_accounting_sales_discounts_summary_groups_categories_and_masks_promocodes(
    tmp_path,
    monkeypatch,
) -> None:
    rows_by_unit = {
        "unit-1": [
            {
                "unitId": "unit-1",
                "unitName": "Точка 1",
                "products": [
                    {
                        "price": 100,
                        "priceWithDiscount": 80,
                        "discount": {
                            "bonusActionId": "cvm-1",
                            "bonusActionName": "CVM. Personal action",
                        },
                    },
                    {"price": 50, "priceWithDiscount": 50},
                ],
            },
            {
                "unitId": "unit-1",
                "unitName": "Точка 1",
                "products": [
                    {
                        "price": 200,
                        "priceWithDiscount": 150,
                        "discount": {
                            "bonusActionId": "local-1",
                            "bonusActionName": "Local summer offer",
                            "promoCode": "ABCDEF99",
                        },
                    },
                    {
                        "price": 100,
                        "priceWithDiscount": 70,
                        "discount": {
                            "bonusActionId": "cvm-2",
                            "bonusActionName": "СVM. Скидка 15%",
                            "promoCode": "SECRET77",
                        },
                    },
                ],
            },
            {
                "unitId": "unit-1",
                "unitName": "Точка 1",
                "products": [
                    {
                        "price": 80,
                        "priceWithDiscount": 60,
                        "discount": {
                            "bonusActionId": "employee-1",
                            "bonusActionName": "Скидка для сотрудников",
                        },
                    }
                ],
            },
        ],
        "unit-2": [
            {
                "unitId": "unit-2",
                "unitName": "Точка 2",
                "products": [
                    {
                        "price": 100,
                        "priceWithDiscount": 90,
                        "discount": {
                            "bonusActionId": "combo-1",
                            "bonusActionName": "Комбо обед",
                        },
                    },
                    {
                        "price": 50,
                        "priceWithDiscount": 0,
                        "discount": {
                            "bonusActionId": "sauce-1",
                            "bonusActionName": "Сырный соус к картофелю из печи",
                        },
                    },
                ],
            }
        ],
    }

    async def fake_invoke(self, tool, parameters, dry_run):  # noqa: ANN001
        del self, tool, dry_run
        if parameters["skip"] != 0:
            return {"sales": []}
        return {"sales": rows_by_unit[parameters["units"]]}

    monkeypatch.setattr(DodoConnector, "invoke", fake_invoke)
    settings = make_settings(tmp_path, dodo_access_token="token")
    app.dependency_overrides[dodo_data_settings_dep] = lambda: settings
    try:
        client = TestClient(app)
        response = client.get(
            "/dodo/accounting/sales/discounts-summary",
            params={
                "units": "unit-1,unit-2",
                "from": "2026-06-01",
                "to": "2026-06-01",
                "take": "100",
                "includeActions": "true",
                "topActionsLimit": "5",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["function"] == "accounting_sales_discounts_summary"
    assert payload["complete"] is True
    assert payload["total"] == {
        "orders": 4,
        "products": 7,
        "salesWithDiscount": 500,
        "salesWithoutDiscount": 680,
        "discountAmount": 180,
        "discountedOrders": 4,
        "discountedProducts": 6,
        "discountShareOfSalesWithoutDiscountPercent": 26.5,
    }
    categories = {item["category"]: item for item in payload["categories"]}
    assert categories["cvm"]["discountAmount"] == 50
    assert categories["cvm"]["orders"] == 2
    assert categories["cvm"]["shareOfTotalDiscountPercent"] == 27.8
    assert categories["cvm"]["shareOfTotalSalesWithoutDiscountPercent"] == 7.4
    assert categories["cvm"]["discountPercentOfCategorySalesWithoutDiscount"] == 25
    assert categories["local"]["discountAmount"] == 50
    assert categories["employee"]["discountAmount"] == 20
    assert categories["combo"]["discountAmount"] == 10
    assert categories["sauces_addons"]["discountAmount"] == 50

    cvm_action = next(action for action in categories["cvm"]["actions"] if action["bonusActionId"] == "cvm-2")
    assert cvm_action["promocodeProducts"] == 1
    assert cvm_action["promocodeMasked"] == "SE***77"
    assert "SECRET77" not in json.dumps(payload, ensure_ascii=False)

    unit_1 = next(unit for unit in payload["units"] if unit["unitId"] == "unit-1")
    unit_1_categories = {item["category"]: item for item in unit_1["categories"]}
    assert unit_1["total"]["discountAmount"] == 120
    assert unit_1_categories["cvm"]["discountAmount"] == 50


def test_dodo_accounting_sales_discounts_summary_defaults_to_all_pizzerias(tmp_path, monkeypatch) -> None:
    pizzerias_path = tmp_path / "pizzerias.json"
    pizzerias_path.write_text(
        json.dumps(
            [
                {"id": "unit-1", "name": "Точка 1", "unitType": 1},
                {"id": "unit-2", "name": "Точка 2", "unitType": 1},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    calls = []

    async def fake_invoke(self, tool, parameters, dry_run):  # noqa: ANN001
        del self, tool, dry_run
        calls.append((parameters["units"], parameters["skip"]))
        if parameters["skip"] != 0:
            return {"sales": []}
        return {
            "sales": [
                {
                    "unitId": parameters["units"],
                    "unitName": f"Name {parameters['units']}",
                    "products": [
                        {
                            "price": 100,
                            "priceWithDiscount": 90,
                            "discount": {"bonusActionName": "CVM. Personal action"},
                        }
                    ],
                }
            ]
        }

    monkeypatch.setattr(DodoConnector, "invoke", fake_invoke)
    settings = make_settings(tmp_path, dodo_access_token="token", dodo_pizzerias_path=pizzerias_path)
    app.dependency_overrides[dodo_data_settings_dep] = lambda: settings
    try:
        client = TestClient(app)
        response = client.get(
            "/dodo/accounting/sales/discounts-summary",
            params={
                "from": "2026-06-01",
                "to": "2026-06-01",
                "take": "100",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"]["discountAmount"] == 20
    assert {unit["unitId"] for unit in payload["units"]} == {"unit-1", "unit-2"}
    assert calls == [("unit-1", 0), ("unit-2", 0)]


def test_dodo_accounting_sales_summary_uses_cache_on_second_call(tmp_path, monkeypatch) -> None:
    calls = []

    async def fake_invoke(self, tool, parameters, dry_run):  # noqa: ANN001
        del self, tool, dry_run
        calls.append((parameters["units"], parameters["skip"]))
        if parameters["skip"] == 0:
            return {
                "sales": [
                    {
                        "soldAtLocal": "2026-06-01T10:00:00",
                        "unitId": "unit-1",
                        "unitName": "Точка 1",
                        "products": [
                            {"price": 100, "priceWithDiscount": 90},
                            {"price": 50, "priceWithDiscount": 40},
                        ],
                    }
                ]
            }
        return {"sales": []}

    monkeypatch.setattr(DodoConnector, "invoke", fake_invoke)
    settings = make_settings(tmp_path, dodo_access_token="token")
    app.dependency_overrides[dodo_data_settings_dep] = lambda: settings
    try:
        client = TestClient(app)
        first = client.get(
            "/dodo/accounting/sales/summary",
            params={
                "units": "unit-1",
                "from": "2026-06-01",
                "to": "2026-06-01",
                "take": "10",
            },
        )
        second = client.get(
            "/dodo/accounting/sales/summary",
            params={
                "units": "unit-1",
                "from": "2026-06-01",
                "to": "2026-06-01",
                "take": "10",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert first.status_code == 200
    first_payload = first.json()
    assert first_payload["total"]["salesWithDiscount"] == 130
    assert first_payload["source"]["dailyRowsHit"] == 0
    assert first_payload["source"]["cacheWrites"] == 1
    assert first_payload["source"]["unitsFetchedLive"] == ["unit-1"]
    assert calls == [("unit-1", 0)]

    assert second.status_code == 200
    second_payload = second.json()
    assert second_payload["total"]["salesWithDiscount"] == 130
    assert second_payload["source"]["dailyRowsHit"] == 1
    assert second_payload["source"]["cacheWrites"] == 0
    assert second_payload["source"]["pagesFetched"] == 0
    assert second_payload["source"]["unitsFetchedLive"] == []
    assert second_payload["units"][0]["source"]["cache"] == "hit"
    assert calls == [("unit-1", 0)]


def test_dodo_accounting_sales_summary_defaults_to_all_pizzerias(tmp_path, monkeypatch) -> None:
    pizzerias_path = tmp_path / "pizzerias.json"
    pizzerias_path.write_text(
        json.dumps(
            [
                {"id": "unit-1", "name": "Точка 1", "unitType": 1},
                {"id": "unit-2", "name": "Точка 2", "unitType": 1},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    calls = []

    async def fake_invoke(self, tool, parameters, dry_run):  # noqa: ANN001
        del self, tool, dry_run
        calls.append((parameters["units"], parameters["skip"]))
        if parameters["skip"] != 0:
            return {"sales": []}
        return {
            "sales": [
                {
                    "soldAtLocal": "2026-06-01T10:00:00",
                    "unitId": parameters["units"],
                    "unitName": f"Name {parameters['units']}",
                    "products": [{"price": 100, "priceWithDiscount": 90}],
                }
            ]
        }

    monkeypatch.setattr(DodoConnector, "invoke", fake_invoke)
    settings = make_settings(tmp_path, dodo_access_token="token", dodo_pizzerias_path=pizzerias_path)
    app.dependency_overrides[dodo_data_settings_dep] = lambda: settings
    try:
        client = TestClient(app)
        response = client.get(
            "/dodo/accounting/sales/summary",
            params={
                "from": "2026-06-01",
                "to": "2026-06-01",
                "take": "10",
                "cacheMode": "bypass",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"]["salesWithDiscount"] == 180
    assert payload["source"]["dailyRowsRequested"] == 2
    assert payload["source"]["unitsFetchedLive"] == ["unit-1", "unit-2"]
    assert {unit["unitId"] for unit in payload["units"]} == {"unit-1", "unit-2"}
    assert calls == [("unit-1", 0), ("unit-2", 0)]


def test_dodo_accounting_sales_summary_caches_zero_sales_days(tmp_path, monkeypatch) -> None:
    calls = []

    async def fake_invoke(self, tool, parameters, dry_run):  # noqa: ANN001
        del self, tool, dry_run
        calls.append((parameters["units"], parameters["skip"]))
        return {"sales": []}

    monkeypatch.setattr(DodoConnector, "invoke", fake_invoke)
    settings = make_settings(tmp_path, dodo_access_token="token")
    app.dependency_overrides[dodo_data_settings_dep] = lambda: settings
    try:
        client = TestClient(app)
        first = client.get(
            "/dodo/accounting/sales/summary",
            params={
                "units": "unit-1",
                "from": "2026-06-01",
                "to": "2026-06-01",
                "take": "10",
            },
        )
        second = client.get(
            "/dodo/accounting/sales/summary",
            params={
                "units": "unit-1",
                "from": "2026-06-01",
                "to": "2026-06-01",
                "take": "10",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert first.status_code == 200
    assert first.json()["total"]["salesWithDiscount"] == 0
    assert first.json()["source"]["cacheWrites"] == 1

    assert second.status_code == 200
    payload = second.json()
    assert payload["total"]["salesWithDiscount"] == 0
    assert payload["source"]["dailyRowsHit"] == 1
    assert payload["source"]["pagesFetched"] == 0
    assert payload["units"][0]["source"]["cache"] == "hit"
    assert calls == [("unit-1", 0)]


def test_dodo_accounting_sales_comparison_compares_periods(tmp_path, monkeypatch) -> None:
    sales_by_period_unit = {
        ("2026-06-01", "unit-1"): [
            {
                "unitId": "unit-1",
                "unitName": "Точка 1",
                "products": [{"price": 150, "priceWithDiscount": 120}],
            }
        ],
        ("2026-06-01", "unit-2"): [
            {
                "unitId": "unit-2",
                "unitName": "Точка 2",
                "products": [{"price": 220, "priceWithDiscount": 200}],
            }
        ],
        ("2026-05-01", "unit-1"): [
            {
                "unitId": "unit-1",
                "unitName": "Точка 1",
                "products": [{"price": 110, "priceWithDiscount": 100}],
            }
        ],
        ("2026-05-01", "unit-2"): [
            {
                "unitId": "unit-2",
                "unitName": "Точка 2",
                "products": [{"price": 260, "priceWithDiscount": 250}],
            }
        ],
    }

    async def fake_invoke(self, tool, parameters, dry_run):  # noqa: ANN001
        del self, tool, dry_run
        if parameters["skip"] != 0:
            return {"sales": []}
        return {"sales": sales_by_period_unit.get((parameters["from"], parameters["units"]), [])}

    monkeypatch.setattr(DodoConnector, "invoke", fake_invoke)
    settings = make_settings(tmp_path, dodo_access_token="token")
    app.dependency_overrides[dodo_data_settings_dep] = lambda: settings
    try:
        client = TestClient(app)
        response = client.get(
            "/dodo/accounting/sales/comparison",
            params={
                "units": "unit-1,unit-2",
                "from": "2026-06-01",
                "to": "2026-06-01",
                "compareFrom": "2026-05-01",
                "compareTo": "2026-05-01",
                "take": "10",
                "cacheMode": "bypass",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["function"] == "accounting_sales_comparison"
    assert payload["complete"] is True
    assert payload["current"]["total"]["salesWithDiscount"] == 320
    assert payload["current"]["total"]["averageCheck"] == 160
    assert payload["baseline"]["total"]["salesWithDiscount"] == 350
    assert payload["baseline"]["total"]["averageCheck"] == 175
    assert payload["change"]["salesWithDiscount"] == -30
    assert payload["changePercent"]["salesWithDiscount"] == -8.57
    assert payload["change"]["averageCheck"] == -15
    assert payload["units"][0]["unitId"] == "unit-1"
    assert payload["units"][0]["change"]["salesWithDiscount"] == 20
    assert payload["units"][0]["changePercent"]["salesWithDiscount"] == 20
    assert payload["units"][1]["unitId"] == "unit-2"
    assert payload["units"][1]["change"]["salesWithDiscount"] == -50
    assert payload["units"][1]["changePercent"]["salesWithDiscount"] == -20


def test_dodo_accounting_sales_comparison_dry_run_plans_two_periods(tmp_path) -> None:
    settings = make_settings(tmp_path)
    app.dependency_overrides[dodo_data_settings_dep] = lambda: settings
    try:
        client = TestClient(app)
        response = client.get(
            "/dodo/accounting/sales/comparison",
            params={
                "units": "unit-1",
                "from": "2026-06-01",
                "to": "2026-06-01",
                "compareFrom": "2026-05-01",
                "compareTo": "2026-05-01",
                "dry_run": "true",
                "take": "100",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["function"] == "accounting_sales_comparison"
    assert payload["dry_run"] is True
    assert payload["current"]["dry_run"] is True
    assert payload["baseline"]["dry_run"] is True
    assert "from=2026-06-01" in payload["current"]["requests_preview"][0]["request"]["url"]
    assert "to=2026-06-02" in payload["current"]["requests_preview"][0]["request"]["url"]
    assert "from=2026-05-01" in payload["baseline"]["requests_preview"][0]["request"]["url"]
    assert "to=2026-05-02" in payload["baseline"]["requests_preview"][0]["request"]["url"]


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


def test_dodo_accounting_slices_daily_dynamics_dry_run_plans_first_day(tmp_path) -> None:
    settings = make_settings(tmp_path)
    app.dependency_overrides[dodo_data_settings_dep] = lambda: settings
    try:
        client = TestClient(app)
        response = client.get(
            "/dodo/accounting/slices/daily-dynamics",
            params={
                "units": "unit-1",
                "from": "2026-06-16",
                "to": "2026-06-17",
                "dry_run": "true",
                "take": "100",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["function"] == "accounting_slice_daily_dynamics"
    assert payload["dry_run"] is True
    assert payload["request_count"] == 4
    assert payload["requests_preview"]["first_day"] == "2026-06-16"
    assert "/accounting/write-offs/products" in payload["requests_preview"]["writeoffs"]["url"]
    assert "/accounting/sales" in payload["requests_preview"]["sales"]["url"]
    assert "from=2026-06-16" in payload["requests_preview"]["sales"]["url"]
    assert "to=2026-06-17" in payload["requests_preview"]["sales"]["url"]


def test_dodo_accounting_slices_daily_dynamics_groups_by_day(tmp_path, monkeypatch) -> None:
    async def fake_invoke(self, tool, parameters, dry_run):  # noqa: ANN001
        del self, dry_run
        day = parameters["from"]
        if tool.name == "dodo_accounting_writeoffs_products":
            rows_by_day = {
                "2026-06-16": [
                    {
                        "unitId": "unit-1",
                        "unitName": "Чита-2",
                        "writtenOffAtLocal": "2026-06-16T12:00:00",
                        "productName": "Кус Пепперони 1 шт",
                        "quantity": 2,
                        "pricePerPiece": 100,
                    },
                    {
                        "unitId": "unit-1",
                        "unitName": "Чита-2",
                        "writtenOffAtLocal": "2026-06-16T13:00:00",
                        "productName": "Напиток",
                        "quantity": 9,
                        "pricePerPiece": 50,
                    },
                ],
                "2026-06-17": [
                    {
                        "unitId": "unit-1",
                        "unitName": "Чита-2",
                        "writtenOffAtLocal": "2026-06-17T12:00:00",
                        "productName": "Кус Ветчина и сыр 1 шт",
                        "quantity": 1,
                        "pricePerPiece": 90,
                    },
                ],
            }
            return {"writeOffs": rows_by_day.get(day, [])}
        if tool.name == "dodo_accounting_sales":
            rows_by_day = {
                "2026-06-16": [
                    {
                        "unitId": "unit-1",
                        "unitName": "Чита-2",
                        "soldAtLocal": "2026-06-16T10:00:00",
                        "products": [
                            {"defaultProductName": "Кус Пепперони 1 шт", "quantity": 3, "priceWithDiscount": 100},
                            {"defaultProductName": "Напиток", "priceWithDiscount": 70},
                        ],
                    },
                    {
                        "unitId": "unit-1",
                        "unitName": "Чита-2",
                        "soldAtLocal": "2026-06-16T11:00:00",
                        "products": [
                            {"defaultProductName": "Кус Ветчина и сыр 1 шт", "price": 90},
                        ],
                    },
                ],
                "2026-06-17": [
                    {
                        "unitId": "unit-1",
                        "unitName": "Чита-2",
                        "soldAtLocal": "2026-06-17T10:00:00",
                        "products": [
                            {"defaultProductName": "Кус Пепперони 1 шт", "quantity": 2, "priceWithDiscount": 100},
                        ],
                    },
                ],
            }
            return {"sales": rows_by_day.get(day, [])}
        raise AssertionError(tool.name)

    monkeypatch.setattr(DodoConnector, "invoke", fake_invoke)
    settings = make_settings(tmp_path, dodo_access_token="token")
    app.dependency_overrides[dodo_data_settings_dep] = lambda: settings
    try:
        client = TestClient(app)
        response = client.get(
            "/dodo/accounting/slices/daily-dynamics",
            params={
                "units": "unit-1",
                "from": "2026-06-16",
                "to": "2026-06-17",
                "take": "100",
                "max_pages": "1",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["function"] == "accounting_slice_daily_dynamics"
    assert payload["total"]["soldQuantity"] == 6
    assert payload["total"]["writeoffQuantity"] == 3
    assert payload["total"]["laidOutQuantity"] == 9
    assert payload["total"]["writeoffPercent"] == 33.3
    assert payload["days"][0]["day"] == "2026-06-16"
    assert payload["days"][0]["soldQuantity"] == 4
    assert payload["days"][0]["writeoffQuantity"] == 2
    assert payload["days"][0]["writeoffPercent"] == 33.3
    assert payload["days"][1]["day"] == "2026-06-17"
    assert payload["days"][1]["soldQuantity"] == 2
    assert payload["days"][1]["writeoffQuantity"] == 1
    assert payload["units"][0]["unitName"] == "Чита-2"
    assert payload["source"]["sales"]["row_count"] == 3
    assert payload["source"]["writeoffs"]["row_count"] == 3
    assert payload["source"]["sales"]["truncated"] is False


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


def test_dodo_data_external_insufficient_scopes_reports_scope_hint(tmp_path, monkeypatch) -> None:
    async def fake_invoke(self, tool, parameters, dry_run):  # noqa: ANN001
        del self, tool, parameters, dry_run
        request = httpx.Request("GET", "https://api.dodois.io/example")
        response = httpx.Response(
            403,
            json={
                "code": "InsufficientScopes",
                "message": "Insufficient scopes.",
                "details": {"allowedScope": "orders"},
            },
            request=request,
        )
        raise httpx.HTTPStatusError("Forbidden", request=request, response=response)

    monkeypatch.setattr(DodoConnector, "invoke", fake_invoke)
    settings = make_settings(tmp_path, dodo_access_token="token")
    app.dependency_overrides[dodo_data_settings_dep] = lambda: settings
    try:
        client = TestClient(app)
        response = client.get(
            "/dodo/orders/clients-statistics",
            params={
                "units": "unit-1",
                "from": "2026-06-01",
                "to": "2026-06-30",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["function"] == "orders_clients_statistics"
    assert payload["status"] == "blocked_by_scope"
    assert payload["read_only"] is True
    assert payload["blocked"] is True
    assert payload["required_scope_hint"] == "orders"
    detail = payload["detail"]
    assert detail["error"] == "external_insufficient_scopes"
    assert detail["tool_name"] == "dodo_orders_clients_statistics"
    assert detail["external_status"] == 403
    assert detail["external_code"] == "InsufficientScopes"
    assert detail["required_scope_hint"] == "orders"


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


def test_dodo_ratings_standards_summary_aggregates_scores(tmp_path, monkeypatch) -> None:
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
                    {"unitId": "u2", "unitName": "Two", "score": "80%"},
                    {"unitId": "u3", "unitName": "Three", "rate": 60},
                ],
            }
        return {
            **base,
            "unitRates": [
                {"unitId": "u4", "unitName": "Four", "rate": 70},
                {"unitId": "u5", "unitName": "Five", "rate": None, "avgRate": 85},
            ],
        }

    monkeypatch.setattr(DodoConnector, "invoke", fake_invoke)
    settings = make_settings(tmp_path, dodo_access_token="token")
    app.dependency_overrides[dodo_data_settings_dep] = lambda: settings
    try:
        client = TestClient(app)
        response = client.get(
            "/dodo/ratings/standards/summary",
            params={
                "countryCode": "643",
                "lowRateThreshold": "75",
                "topLimit": "2",
                "take": "3",
                "max_pages": "2",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["function"] == "ratings_standards_summary"
    assert payload["meta"] == {
        "periodFrom": "2026-06-08",
        "periodTo": "2026-06-14",
        "publishStatus": "Published",
        "publishedAt": "2026-06-15T16:19:01",
    }
    assert payload["source"] == {
        "rows_key": "unitRates",
        "row_count": 5,
        "pages_fetched": 2,
        "truncated": False,
        "next_skip": None,
    }
    assert payload["threshold"] == {"lowRate": 75}
    assert payload["total"] == {
        "rowCount": 5,
        "ratedUnits": 5,
        "unscoredRows": 0,
        "averageRate": 77,
        "minRate": 60,
        "maxRate": 90,
        "belowThresholdUnits": 2,
    }
    assert payload["lowestUnits"] == [
        {"unitId": "u3", "unitName": "Three", "rate": 60, "rateField": "rate"},
        {"unitId": "u4", "unitName": "Four", "rate": 70, "rateField": "rate"},
    ]
    assert payload["highestUnits"] == [
        {"unitId": "u1", "unitName": "One", "rate": 90, "rateField": "rate"},
        {"unitId": "u5", "unitName": "Five", "rate": 85, "rateField": "avgRate"},
    ]
    assert [unit["unitName"] for unit in payload["belowThreshold"]] == ["Three", "Four"]


def make_settings(
    tmp_path: Path,
    dodo_access_token: str | None = None,
    dodo_data_max_period_days: int = 92,
    dodo_pizzerias_path: Path | None = None,
) -> Settings:
    return Settings(
        api_keys=[],
        tool_registry_path=Path("configs/tools.example.yaml"),
        policy_path=Path("configs/policy.example.yaml"),
        audit_db_path=tmp_path / "audit.sqlite3",
        dodo_access_token=dodo_access_token,
        dodo_data_max_period_days=dodo_data_max_period_days,
        dodo_pizzerias_path=dodo_pizzerias_path,
    )
