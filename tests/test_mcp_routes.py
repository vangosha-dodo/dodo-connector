from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from dodo_bridge.config import Settings
from dodo_bridge.connectors.superset import SupersetConnector
from dodo_bridge.dodo_data import DodoDataService
from dodo_bridge.main import app


def test_mcp_initialize_returns_server_capabilities(tmp_path) -> None:
    with mcp_client(tmp_path) as client:
        response = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["jsonrpc"] == "2.0"
    assert payload["id"] == 1
    assert payload["result"]["serverInfo"] == {
        "name": "dodo-chatgpt-bridge",
        "version": "0.1.0",
    }
    assert payload["result"]["capabilities"]["tools"] == {}


def test_mcp_tools_list_exposes_router_tools_only(tmp_path) -> None:
    with mcp_client(tmp_path) as client:
        response = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        )

    assert response.status_code == 200
    payload = response.json()
    tools = payload["result"]["tools"]
    tool_names = {tool["name"] for tool in tools}
    assert {
        "list_capabilities",
        "dodo_api_query",
        "superset_query",
        "office_manager_query",
        "report_missing_capability",
    } <= tool_names
    assert "getDodoAccountingSalesSummary" not in tool_names
    assert payload["result"]["resultType"] == "complete"
    assert all(tool["inputSchema"]["type"] == "object" for tool in tools)


def test_mcp_tools_call_list_capabilities_returns_read_only_capabilities(tmp_path) -> None:
    with mcp_client(tmp_path) as client:
        response = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "list_capabilities", "arguments": {}},
            },
        )

    assert response.status_code == 200
    payload = response.json()
    result = payload["result"]
    assert result["resultType"] == "complete"
    assert result["isError"] is False
    assert "read-only" in result["content"][0]["text"]
    assert result["structuredContent"]["read_only"] is True
    capability_names = {
        item["name"] for item in result["structuredContent"]["dodo_capabilities"]
    }
    assert "accounting_sales_summary" in capability_names
    assert "accounting_sales_comparison" in capability_names
    assert "accounting_inventory_stocks_summary" in capability_names
    assert "delivery_courier_productivity_summary" in capability_names
    assert "staff_vacancies_count" in capability_names
    assert "units_month_goals" in capability_names
    assert "orders_clients_statistics" in capability_names
    assert "production_productivity" in capability_names
    assert "production_orders_handover_time" in capability_names
    assert "courier_orders" not in capability_names
    office_manager_names = {
        item["name"] for item in result["structuredContent"]["office_manager_capabilities"]
    }
    assert "courier_payroll_daily_export" in office_manager_names


def test_mcp_capabilities_get_returns_router_capabilities(tmp_path) -> None:
    with mcp_client(tmp_path) as client:
        response = client.get("/mcp/capabilities")

    assert response.status_code == 200
    payload = response.json()
    assert payload["read_only"] is True
    assert payload["diagnostic"] == {
        "endpoint": "/mcp",
        "jsonrpc_method": "tools/call",
        "tool_name": "list_capabilities",
        "chatgpt_openapi_exposed": False,
    }
    capability_names = {item["name"] for item in payload["dodo_capabilities"]}
    assert "accounting_sales_summary" in capability_names
    assert "production_productivity" in capability_names
    assert "courier_orders" not in capability_names
    assert payload["office_manager_capabilities"][0]["name"] == "courier_payroll_daily_export"


def test_mcp_tools_call_rejects_unknown_tool(tmp_path) -> None:
    with mcp_client(tmp_path) as client:
        response = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": "delete_orders", "arguments": {}},
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["jsonrpc"] == "2.0"
    assert payload["id"] == 4
    assert payload["error"]["code"] == -32602
    assert "Unknown MCP tool" in payload["error"]["message"]


def test_mcp_tools_call_dodo_api_query_requires_allowed_capability(tmp_path) -> None:
    with mcp_client(tmp_path) as client:
        response = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {
                    "name": "dodo_api_query",
                    "arguments": {"capability": "delete_orders", "parameters": {}},
                },
            },
        )

    assert response.status_code == 200
    result = response.json()["result"]
    assert result["isError"] is True
    assert result["structuredContent"]["status"] == "capability_not_enabled"
    assert result["structuredContent"]["read_only"] is True


def test_mcp_dodo_api_query_runs_allowed_sales_summary(tmp_path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_fetch_sales_summary(
        self,  # noqa: ANN001
        *,
        parameters,
        dry_run,
        take,
        max_pages_per_unit,
        concurrency,
        cache_mode,
    ):
        captured["parameters"] = parameters
        captured["dry_run"] = dry_run
        captured["take"] = take
        captured["max_pages_per_unit"] = max_pages_per_unit
        captured["concurrency"] = concurrency
        captured["cache_mode"] = cache_mode
        return {
            "function": "accounting_sales_summary",
            "read_only": True,
            "total": {"salesWithDiscount": 12345},
        }

    monkeypatch.setattr(DodoDataService, "fetch_sales_summary", fake_fetch_sales_summary)

    with mcp_client(tmp_path) as client:
        response = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 6,
                "method": "tools/call",
                "params": {
                    "name": "dodo_api_query",
                    "arguments": {
                        "capability": "accounting_sales_summary",
                        "parameters": {
                            "units": "unit-1",
                            "from": "2026-05-01",
                            "to": "2026-05-31",
                            "take": 500,
                            "maxPagesPerUnit": 7,
                            "concurrency": 2,
                            "cacheMode": "bypass",
                        },
                        "dry_run": True,
                    },
                },
            },
        )

    assert response.status_code == 200
    result = response.json()["result"]
    assert result["isError"] is False
    assert result["structuredContent"]["function"] == "accounting_sales_summary"
    assert result["structuredContent"]["total"]["salesWithDiscount"] == 12345
    assert captured == {
        "parameters": {"units": "unit-1", "from": "2026-05-01", "to": "2026-06-01"},
        "dry_run": True,
        "take": 500,
        "max_pages_per_unit": 7,
        "concurrency": 2,
        "cache_mode": "bypass",
    }


def test_mcp_dodo_api_query_runs_sales_comparison(tmp_path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_fetch_sales_comparison(
        self,  # noqa: ANN001
        *,
        current_parameters,
        baseline_parameters,
        dry_run,
        take,
        max_pages_per_unit,
        concurrency,
        cache_mode,
    ):
        captured["current_parameters"] = current_parameters
        captured["baseline_parameters"] = baseline_parameters
        captured["dry_run"] = dry_run
        captured["take"] = take
        captured["max_pages_per_unit"] = max_pages_per_unit
        captured["concurrency"] = concurrency
        captured["cache_mode"] = cache_mode
        return {"function": "accounting_sales_comparison", "read_only": True}

    monkeypatch.setattr(DodoDataService, "fetch_sales_comparison", fake_fetch_sales_comparison)

    result = call_mcp_tool(
        tmp_path,
        "dodo_api_query",
        {
            "capability": "accounting_sales_comparison",
            "parameters": {
                "units": "unit-1",
                "from": "2026-06-01",
                "to": "2026-06-30",
                "compareFrom": "2026-05-01",
                "compareTo": "2026-05-31",
                "take": 500,
                "maxPagesPerUnit": 6,
                "concurrency": 3,
                "cacheMode": "auto",
            },
            "dry_run": True,
        },
        request_id=20,
    )

    assert result["isError"] is False
    assert result["structuredContent"]["function"] == "accounting_sales_comparison"
    assert captured == {
        "current_parameters": {"units": "unit-1", "from": "2026-06-01", "to": "2026-07-01"},
        "baseline_parameters": {"units": "unit-1", "from": "2026-05-01", "to": "2026-06-01"},
        "dry_run": True,
        "take": 500,
        "max_pages_per_unit": 6,
        "concurrency": 3,
        "cache_mode": "auto",
    }


def test_mcp_dodo_api_query_runs_writeoff_summary(tmp_path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_fetch_writeoff_products_summary(
        self,  # noqa: ANN001
        *,
        parameters,
        dry_run,
        product_name_prefix,
        include_products,
        include_reasons,
        take,
        max_pages,
    ):
        captured["parameters"] = parameters
        captured["dry_run"] = dry_run
        captured["product_name_prefix"] = product_name_prefix
        captured["include_products"] = include_products
        captured["include_reasons"] = include_reasons
        captured["take"] = take
        captured["max_pages"] = max_pages
        return {"function": "accounting_writeoffs_products_summary", "read_only": True}

    monkeypatch.setattr(
        DodoDataService,
        "fetch_writeoff_products_summary",
        fake_fetch_writeoff_products_summary,
    )

    result = call_mcp_tool(
        tmp_path,
        "dodo_api_query",
        {
            "capability": "accounting_writeoffs_products_summary",
            "parameters": {
                "units": "unit-1",
                "from": "2026-06-01",
                "to": "2026-06-01",
                "productNamePrefix": "Кус",
                "includeProducts": True,
                "includeReasons": True,
                "take": 100,
                "max_pages": 3,
            },
            "dry_run": True,
        },
        request_id=9,
    )

    assert result["isError"] is False
    assert result["structuredContent"]["function"] == "accounting_writeoffs_products_summary"
    assert captured == {
        "parameters": {"units": "unit-1", "from": "2026-06-01", "to": "2026-06-02"},
        "dry_run": True,
        "product_name_prefix": "Кус",
        "include_products": True,
        "include_reasons": True,
        "take": 100,
        "max_pages": 3,
    }


def test_mcp_dodo_api_query_runs_slice_writeoff_rate(tmp_path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_fetch_slice_writeoff_rate(
        self,  # noqa: ANN001
        *,
        sales_parameters,
        writeoff_parameters,
        dry_run,
        product_name_prefix,
        include_products,
        take,
        max_pages,
    ):
        captured["sales_parameters"] = sales_parameters
        captured["writeoff_parameters"] = writeoff_parameters
        captured["dry_run"] = dry_run
        captured["product_name_prefix"] = product_name_prefix
        captured["include_products"] = include_products
        captured["take"] = take
        captured["max_pages"] = max_pages
        return {"function": "accounting_slice_writeoff_rate", "read_only": True}

    monkeypatch.setattr(DodoDataService, "fetch_slice_writeoff_rate", fake_fetch_slice_writeoff_rate)

    result = call_mcp_tool(
        tmp_path,
        "dodo_api_query",
        {
            "capability": "accounting_slice_writeoff_rate",
            "parameters": {
                "units": "unit-1",
                "from": "2026-06-01",
                "to": "2026-06-30",
                "productNamePrefix": "Кус",
                "includeProducts": False,
                "take": 250,
                "max_pages": 5,
            },
            "dry_run": False,
        },
        request_id=10,
    )

    expected_params = {"units": "unit-1", "from": "2026-06-01", "to": "2026-07-01"}
    assert result["isError"] is False
    assert result["structuredContent"]["function"] == "accounting_slice_writeoff_rate"
    assert captured == {
        "sales_parameters": expected_params,
        "writeoff_parameters": expected_params,
        "dry_run": False,
        "product_name_prefix": "Кус",
        "include_products": False,
        "take": 250,
        "max_pages": 5,
    }


def test_mcp_dodo_api_query_runs_slice_daily_dynamics(tmp_path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_fetch_slice_daily_dynamics(
        self,  # noqa: ANN001
        *,
        sales_parameters,
        writeoff_parameters,
        dry_run,
        product_name_prefix,
        include_products,
        take,
        max_pages,
    ):
        captured["sales_parameters"] = sales_parameters
        captured["writeoff_parameters"] = writeoff_parameters
        captured["dry_run"] = dry_run
        captured["product_name_prefix"] = product_name_prefix
        captured["include_products"] = include_products
        captured["take"] = take
        captured["max_pages"] = max_pages
        return {"function": "accounting_slice_daily_dynamics", "read_only": True}

    monkeypatch.setattr(DodoDataService, "fetch_slice_daily_dynamics", fake_fetch_slice_daily_dynamics)

    result = call_mcp_tool(
        tmp_path,
        "dodo_api_query",
        {
            "capability": "accounting_slice_daily_dynamics",
            "parameters": {
                "units": "unit-1",
                "from": "2026-06-01",
                "to": "2026-06-03",
                "productNamePrefix": "Кус",
                "includeProducts": True,
                "take": 300,
                "max_pages": 4,
            },
            "dry_run": True,
        },
        request_id=11,
    )

    expected_params = {"units": "unit-1", "from": "2026-06-01", "to": "2026-06-04"}
    assert result["isError"] is False
    assert result["structuredContent"]["function"] == "accounting_slice_daily_dynamics"
    assert captured == {
        "sales_parameters": expected_params,
        "writeoff_parameters": expected_params,
        "dry_run": True,
        "product_name_prefix": "Кус",
        "include_products": True,
        "take": 300,
        "max_pages": 4,
    }


def test_mcp_dodo_api_query_runs_sales_channels_summary(tmp_path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_fetch_sales_channels_summary(
        self,  # noqa: ANN001
        *,
        parameters,
        dry_run,
        take,
        max_pages_per_unit,
        concurrency,
    ):
        captured["parameters"] = parameters
        captured["dry_run"] = dry_run
        captured["take"] = take
        captured["max_pages_per_unit"] = max_pages_per_unit
        captured["concurrency"] = concurrency
        return {"function": "accounting_sales_channels_summary", "read_only": True}

    monkeypatch.setattr(DodoDataService, "fetch_sales_channels_summary", fake_fetch_sales_channels_summary)

    result = call_mcp_tool(
        tmp_path,
        "dodo_api_query",
        {
            "capability": "accounting_sales_channels_summary",
            "parameters": {
                "units": "unit-1",
                "from": "2026-05-01",
                "to": "2026-05-31",
                "take": 1000,
                "maxPagesPerUnit": 12,
                "concurrency": 8,
            },
            "dry_run": True,
        },
        request_id=12,
    )

    assert result["isError"] is False
    assert result["structuredContent"]["function"] == "accounting_sales_channels_summary"
    assert captured == {
        "parameters": {"units": "unit-1", "from": "2026-05-01", "to": "2026-06-01"},
        "dry_run": True,
        "take": 1000,
        "max_pages_per_unit": 12,
        "concurrency": 8,
    }


def test_mcp_dodo_api_query_runs_sales_discounts_summary(tmp_path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_fetch_sales_discounts_summary(
        self,  # noqa: ANN001
        *,
        parameters,
        dry_run,
        include_actions,
        top_actions_limit,
        take,
        max_pages_per_unit,
        concurrency,
    ):
        captured["parameters"] = parameters
        captured["dry_run"] = dry_run
        captured["include_actions"] = include_actions
        captured["top_actions_limit"] = top_actions_limit
        captured["take"] = take
        captured["max_pages_per_unit"] = max_pages_per_unit
        captured["concurrency"] = concurrency
        return {"function": "accounting_sales_discounts_summary", "read_only": True}

    monkeypatch.setattr(DodoDataService, "fetch_sales_discounts_summary", fake_fetch_sales_discounts_summary)

    result = call_mcp_tool(
        tmp_path,
        "dodo_api_query",
        {
            "capability": "accounting_sales_discounts_summary",
            "parameters": {
                "units": "unit-1",
                "from": "2026-05-01",
                "to": "2026-05-31",
                "includeActions": True,
                "topActionsLimit": 20,
                "take": 1000,
                "maxPagesPerUnit": 12,
                "concurrency": 8,
            },
            "dry_run": False,
        },
        request_id=13,
    )

    assert result["isError"] is False
    assert result["structuredContent"]["function"] == "accounting_sales_discounts_summary"
    assert captured == {
        "parameters": {"units": "unit-1", "from": "2026-05-01", "to": "2026-06-01"},
        "dry_run": False,
        "include_actions": True,
        "top_actions_limit": 20,
        "take": 1000,
        "max_pages_per_unit": 12,
        "concurrency": 8,
    }


def test_mcp_dodo_api_query_runs_inventory_stocks_summary(tmp_path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_fetch_inventory_stocks_summary(
        self,  # noqa: ANN001
        *,
        parameters,
        dry_run,
        low_stock_days_threshold,
        high_stock_days_threshold,
        top_limit,
        take,
        max_pages,
    ):
        captured["parameters"] = parameters
        captured["dry_run"] = dry_run
        captured["low_stock_days_threshold"] = low_stock_days_threshold
        captured["high_stock_days_threshold"] = high_stock_days_threshold
        captured["top_limit"] = top_limit
        captured["take"] = take
        captured["max_pages"] = max_pages
        return {"function": "accounting_inventory_stocks_summary", "read_only": True}

    monkeypatch.setattr(DodoDataService, "fetch_inventory_stocks_summary", fake_fetch_inventory_stocks_summary)

    result = call_mcp_tool(
        tmp_path,
        "dodo_api_query",
        {
            "capability": "accounting_inventory_stocks_summary",
            "parameters": {
                "units": "unit-1",
                "from": "2026-06-21",
                "to": "2026-06-21",
                "lowStockDaysThreshold": 2.5,
                "highStockDaysThreshold": 30,
                "topLimit": 15,
                "take": 250,
                "maxPages": 3,
            },
            "dry_run": True,
        },
        request_id=14,
    )

    assert result["isError"] is False
    assert result["structuredContent"]["function"] == "accounting_inventory_stocks_summary"
    assert captured == {
        "parameters": {"units": "unit-1", "from": "2026-06-21", "to": "2026-06-21"},
        "dry_run": True,
        "low_stock_days_threshold": 2.5,
        "high_stock_days_threshold": 30.0,
        "top_limit": 15,
        "take": 250,
        "max_pages": 3,
    }


def test_mcp_dodo_api_query_runs_stock_consumptions_summary(tmp_path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_fetch_stock_consumptions_summary(
        self,  # noqa: ANN001
        *,
        parameters,
        dry_run,
        top_limit,
        take,
        max_pages,
    ):
        captured["parameters"] = parameters
        captured["dry_run"] = dry_run
        captured["top_limit"] = top_limit
        captured["take"] = take
        captured["max_pages"] = max_pages
        return {"function": "accounting_stock_consumptions_by_period_summary", "read_only": True}

    monkeypatch.setattr(DodoDataService, "fetch_stock_consumptions_summary", fake_fetch_stock_consumptions_summary)

    result = call_mcp_tool(
        tmp_path,
        "dodo_api_query",
        {
            "capability": "accounting_stock_consumptions_by_period_summary",
            "parameters": {
                "units": "unit-1",
                "from": "2026-06-01",
                "to": "2026-06-30",
                "topLimit": 12,
                "take": 100,
                "max_pages": 4,
            },
            "dry_run": False,
        },
        request_id=15,
    )

    assert result["isError"] is False
    assert result["structuredContent"]["function"] == "accounting_stock_consumptions_by_period_summary"
    assert captured == {
        "parameters": {"units": "unit-1", "from": "2026-06-01", "to": "2026-07-01"},
        "dry_run": False,
        "top_limit": 12,
        "take": 100,
        "max_pages": 4,
    }


def test_mcp_dodo_api_query_runs_customer_experience_ratings_summary(tmp_path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_fetch_ratings_summary(
        self,  # noqa: ANN001
        *,
        function_name,
        parameters,
        dry_run,
        low_rate_threshold,
        top_limit,
        take,
        max_pages,
    ):
        captured["function_name"] = function_name
        captured["parameters"] = parameters
        captured["dry_run"] = dry_run
        captured["low_rate_threshold"] = low_rate_threshold
        captured["top_limit"] = top_limit
        captured["take"] = take
        captured["max_pages"] = max_pages
        return {"function": function_name, "read_only": True}

    monkeypatch.setattr(DodoDataService, "fetch_ratings_summary", fake_fetch_ratings_summary)

    result = call_mcp_tool(
        tmp_path,
        "dodo_api_query",
        {
            "capability": "ratings_customer_experience_summary",
            "parameters": {
                "units": ["unit-1", "unit-2"],
                "lowRateThreshold": 85.5,
                "topLimit": 7,
                "take": 200,
                "maxPages": 2,
            },
            "dry_run": True,
        },
        request_id=16,
    )

    assert result["isError"] is False
    assert result["structuredContent"]["function"] == "ratings_customer_experience_summary"
    assert captured == {
        "function_name": "ratings_customer_experience_summary",
        "parameters": {"units": "unit-1,unit-2"},
        "dry_run": True,
        "low_rate_threshold": 85.5,
        "top_limit": 7,
        "take": 200,
        "max_pages": 2,
    }


def test_mcp_dodo_api_query_runs_standards_ratings_summary(tmp_path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_fetch_ratings_summary(
        self,  # noqa: ANN001
        *,
        function_name,
        parameters,
        dry_run,
        low_rate_threshold,
        top_limit,
        take,
        max_pages,
    ):
        captured["function_name"] = function_name
        captured["parameters"] = parameters
        captured["dry_run"] = dry_run
        captured["low_rate_threshold"] = low_rate_threshold
        captured["top_limit"] = top_limit
        captured["take"] = take
        captured["max_pages"] = max_pages
        return {"function": function_name, "read_only": True}

    monkeypatch.setattr(DodoDataService, "fetch_ratings_summary", fake_fetch_ratings_summary)

    result = call_mcp_tool(
        tmp_path,
        "dodo_api_query",
        {
            "capability": "ratings_standards_summary",
            "parameters": {
                "countryCode": 643,
                "lowRateThreshold": 82,
                "topLimit": 10,
            },
            "dry_run": False,
        },
        request_id=17,
    )

    assert result["isError"] is False
    assert result["structuredContent"]["function"] == "ratings_standards_summary"
    assert captured == {
        "function_name": "ratings_standards_summary",
        "parameters": {"countryCode": 643},
        "dry_run": False,
        "low_rate_threshold": 82.0,
        "top_limit": 10,
        "take": None,
        "max_pages": None,
    }


def test_mcp_dodo_api_query_runs_delivery_courier_productivity_summary(tmp_path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_fetch_delivery_courier_productivity_summary(
        self,  # noqa: ANN001
        *,
        parameters,
        dry_run,
        top_limit,
    ):
        captured["parameters"] = parameters
        captured["dry_run"] = dry_run
        captured["top_limit"] = top_limit
        return {"function": "delivery_courier_productivity_summary", "read_only": True}

    monkeypatch.setattr(
        DodoDataService,
        "fetch_delivery_courier_productivity_summary",
        fake_fetch_delivery_courier_productivity_summary,
    )

    result = call_mcp_tool(
        tmp_path,
        "dodo_api_query",
        {
            "capability": "delivery_courier_productivity_summary",
            "parameters": {
                "units": "unit-1",
                "from": "2026-06-01",
                "to": "2026-06-30",
                "topLimit": 8,
            },
            "dry_run": True,
        },
        request_id=18,
    )

    assert result["isError"] is False
    assert result["structuredContent"]["function"] == "delivery_courier_productivity_summary"
    assert captured == {
        "parameters": {"units": "unit-1", "from": "2026-06-01", "to": "2026-07-01"},
        "dry_run": True,
        "top_limit": 8,
    }


def test_mcp_dodo_api_query_runs_staff_vacancies_count(tmp_path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_fetch(
        self,  # noqa: ANN001
        *,
        function_name,
        parameters,
        dry_run,
        fields,
        take,
        max_pages,
    ):
        captured["function_name"] = function_name
        captured["parameters"] = parameters
        captured["dry_run"] = dry_run
        captured["fields"] = fields
        captured["take"] = take
        captured["max_pages"] = max_pages
        return {"function": function_name, "read_only": True}

    monkeypatch.setattr(DodoDataService, "fetch", fake_fetch)

    result = call_mcp_tool(
        tmp_path,
        "dodo_api_query",
        {
            "capability": "staff_vacancies_count",
            "parameters": {
                "units": ["unit-1", "unit-2"],
                "fields": ["id", "name", "vacanciesCount"],
                "take": 100,
                "maxPages": 2,
            },
            "dry_run": True,
        },
        request_id=21,
    )

    assert result["isError"] is False
    assert result["structuredContent"]["function"] == "staff_vacancies_count"
    assert captured == {
        "function_name": "staff_vacancies_count",
        "parameters": {"units": "unit-1,unit-2"},
        "dry_run": True,
        "fields": ["id", "name", "vacanciesCount"],
        "take": 100,
        "max_pages": 2,
    }


def test_mcp_dodo_api_query_runs_units_month_goals(tmp_path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_fetch(
        self,  # noqa: ANN001
        *,
        function_name,
        parameters,
        dry_run,
        fields,
        take,
        max_pages,
    ):
        captured["function_name"] = function_name
        captured["parameters"] = parameters
        captured["dry_run"] = dry_run
        captured["fields"] = fields
        captured["take"] = take
        captured["max_pages"] = max_pages
        return {"function": function_name, "read_only": True}

    monkeypatch.setattr(DodoDataService, "fetch", fake_fetch)

    result = call_mcp_tool(
        tmp_path,
        "dodo_api_query",
        {
            "capability": "units_month_goals",
            "parameters": {"unit": "unit-1", "month": 6, "year": 2026},
            "dry_run": True,
        },
        request_id=22,
    )

    assert result["isError"] is False
    assert result["structuredContent"]["function"] == "units_month_goals"
    assert captured == {
        "function_name": "units_month_goals",
        "parameters": {"unit": "unit-1", "month": 6, "year": 2026},
        "dry_run": True,
        "fields": None,
        "take": None,
        "max_pages": None,
    }


def test_mcp_dodo_api_query_runs_orders_clients_statistics(tmp_path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_fetch(
        self,  # noqa: ANN001
        *,
        function_name,
        parameters,
        dry_run,
        fields,
        take,
        max_pages,
    ):
        captured["function_name"] = function_name
        captured["parameters"] = parameters
        captured["dry_run"] = dry_run
        captured["fields"] = fields
        captured["take"] = take
        captured["max_pages"] = max_pages
        return {"function": function_name, "read_only": True}

    monkeypatch.setattr(DodoDataService, "fetch", fake_fetch)

    result = call_mcp_tool(
        tmp_path,
        "dodo_api_query",
        {
            "capability": "orders_clients_statistics",
            "parameters": {
                "units": "unit-1",
                "from": "2026-06-01",
                "to": "2026-06-30",
                "fields": "unitId,newClientsCount",
                "take": 200,
                "max_pages": 3,
            },
            "dry_run": True,
        },
        request_id=23,
    )

    assert result["isError"] is False
    assert result["structuredContent"]["function"] == "orders_clients_statistics"
    assert captured == {
        "function_name": "orders_clients_statistics",
        "parameters": {"units": "unit-1", "fromDate": "2026-06-01", "toDate": "2026-06-30"},
        "dry_run": True,
        "fields": ["unitId", "newClientsCount"],
        "take": 200,
        "max_pages": 3,
    }


def test_mcp_dodo_api_query_runs_production_productivity(tmp_path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_fetch(
        self,  # noqa: ANN001
        *,
        function_name,
        parameters,
        dry_run,
        fields,
        take,
        max_pages,
    ):
        captured["function_name"] = function_name
        captured["parameters"] = parameters
        captured["dry_run"] = dry_run
        captured["fields"] = fields
        captured["take"] = take
        captured["max_pages"] = max_pages
        return {"function": function_name, "read_only": True}

    monkeypatch.setattr(DodoDataService, "fetch", fake_fetch)

    result = call_mcp_tool(
        tmp_path,
        "dodo_api_query",
        {
            "capability": "production_productivity",
            "parameters": {
                "units": "unit-1",
                "from": "2026-06-01",
                "to": "2026-06-07",
                "fields": ["unitId", "productivity"],
                "take": 50,
            },
            "dry_run": True,
        },
        request_id=24,
    )

    assert result["isError"] is False
    assert result["structuredContent"]["function"] == "production_productivity"
    assert captured == {
        "function_name": "production_productivity",
        "parameters": {"units": "unit-1", "from": "2026-06-01", "to": "2026-06-07"},
        "dry_run": True,
        "fields": ["unitId", "productivity"],
        "take": 50,
        "max_pages": None,
    }


def test_mcp_dodo_api_query_runs_production_orders_handover_time(tmp_path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_fetch(
        self,  # noqa: ANN001
        *,
        function_name,
        parameters,
        dry_run,
        fields,
        take,
        max_pages,
    ):
        captured["function_name"] = function_name
        captured["parameters"] = parameters
        captured["dry_run"] = dry_run
        captured["fields"] = fields
        captured["take"] = take
        captured["max_pages"] = max_pages
        return {"function": function_name, "read_only": True}

    monkeypatch.setattr(DodoDataService, "fetch", fake_fetch)

    result = call_mcp_tool(
        tmp_path,
        "dodo_api_query",
        {
            "capability": "production_orders_handover_time",
            "parameters": {
                "units": "unit-1",
                "from": "2026-06-01",
                "to": "2026-06-07",
                "take": 50,
                "maxPages": 2,
            },
            "dry_run": True,
        },
        request_id=25,
    )

    assert result["isError"] is False
    assert result["structuredContent"]["function"] == "production_orders_handover_time"
    assert captured == {
        "function_name": "production_orders_handover_time",
        "parameters": {"units": "unit-1", "from": "2026-06-01", "to": "2026-06-07"},
        "dry_run": True,
        "fields": None,
        "take": 50,
        "max_pages": 2,
    }


def test_mcp_superset_query_runs_employee_discount(tmp_path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_invoke(self, tool, parameters, dry_run):  # noqa: ANN001
        captured["tool_name"] = tool.name
        captured["parameters"] = parameters
        captured["dry_run"] = dry_run
        return {
            "result": [
                {
                    "rowcount": 1,
                    "data": [
                        {
                            "UnitName": "Тамбов-1",
                            "ActionSegmentationAndSource": "Сотрудникам",
                            "Discount": 1000,
                            "SalesWithoutDiscount": 10000,
                        }
                    ],
                }
            ]
        }

    monkeypatch.setattr(SupersetConnector, "invoke", fake_invoke)

    with mcp_client(tmp_path) as client:
        response = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 7,
                "method": "tools/call",
                "params": {
                    "name": "superset_query",
                    "arguments": {
                        "capability": "employee_discount",
                        "parameters": {
                            "unit_names": [" Тамбов-1 "],
                            "period": {"from": "2026-06-01", "to": "2026-06-30"},
                        },
                        "dry_run": False,
                    },
                },
            },
        )

    assert response.status_code == 200
    result = response.json()["result"]
    assert result["isError"] is False
    payload = result["structuredContent"]
    assert payload["capability_id"] == "get_employee_discount"
    assert payload["summary"]["employee_discount_amount"] == 1000
    assert captured["tool_name"] == "superset_employee_discount_chart"
    assert captured["dry_run"] is False
    assert captured["parameters"]["dashboard_id"] == 1410
    assert captured["parameters"]["chart_id"] == 26708


def test_mcp_superset_query_runs_kiosk_sales_share(tmp_path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_invoke(self, tool, parameters, dry_run):  # noqa: ANN001
        captured["tool_name"] = tool.name
        captured["parameters"] = parameters
        captured["dry_run"] = dry_run
        return {
            "result": [
                {
                    "rowcount": 1,
                    "data": [{"UnitName": "Чита-2", "Share sales via Kiosk": 0.42}],
                }
            ]
        }

    monkeypatch.setattr(SupersetConnector, "invoke", fake_invoke)

    with mcp_client(tmp_path) as client:
        response = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 8,
                "method": "tools/call",
                "params": {
                    "name": "superset_query",
                    "arguments": {
                        "capability": "kiosk_sales_share",
                        "parameters": {
                            "unit_names": ["Чита-2"],
                            "month": "2026-06",
                        },
                        "dry_run": True,
                    },
                },
            },
        )

    assert response.status_code == 200
    result = response.json()["result"]
    assert result["isError"] is False
    payload = result["structuredContent"]
    assert payload["capability_id"] == "get_kiosk_sales_share"
    assert payload["summary"]["average_kiosk_sales_share_pct"] == 42
    assert captured["tool_name"] == "superset_kiosk_sales_share"
    assert captured["dry_run"] is True
    assert captured["parameters"]["dashboard_id"] == 714
    assert captured["parameters"]["chart_id"] == 9533


def test_mcp_office_manager_query_runs_courier_payroll_daily_export(tmp_path) -> None:
    pizzerias_path = write_pizzerias(tmp_path)
    result = call_mcp_tool(
        tmp_path,
        "office_manager_query",
        {
            "capability": "courier_payroll_daily_export",
            "parameters": {
                "report_date": "2026-06-16",
                "pizzerias": ["Тамбов-1"],
                "extract_source": False,
                "include_source_rows": False,
            },
        },
        request_id=19,
        dodo_pizzerias_path=pizzerias_path,
    )

    assert result["isError"] is False
    payload = result["structuredContent"]
    assert payload["job_name"] == "courier_payroll_daily_export"
    assert payload["dry_run"] is True
    assert payload["dodo_is_changed"] is False
    assert payload["google_sheets_changed"] is False
    assert payload["source"]["path"] == "Отчеты -> Заработная плата"
    assert payload["source"]["filters"] == {"date": "2026-06-16", "staff_type": "Курьер"}
    assert payload["source"]["helper_called"] is False
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
    assert payload["safety"] == {
        "chatgpt_action_exposed": False,
        "dodo_is_write_allowed": False,
        "google_sheets_write_allowed": False,
    }


def call_mcp_tool(
    tmp_path: Path,
    name: str,
    arguments: dict[str, object],
    *,
    request_id: int,
    dodo_pizzerias_path: Path | None = None,
) -> dict[str, object]:
    with mcp_client(tmp_path, dodo_pizzerias_path=dodo_pizzerias_path) as client:
        response = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            },
        )

    assert response.status_code == 200
    return response.json()["result"]


class mcp_client:
    def __init__(self, tmp_path: Path, *, dodo_pizzerias_path: Path | None = None):
        self.settings = Settings(
            api_keys=[],
            tool_registry_path=Path("configs/tools.example.yaml"),
            policy_path=Path("configs/policy.example.yaml"),
            audit_db_path=tmp_path / "audit.sqlite3",
            dodo_access_token=None,
            dodo_pizzerias_path=dodo_pizzerias_path,
        )
        self.client: TestClient | None = None

    def __enter__(self) -> TestClient:
        from dodo_bridge import mcp_routes

        app.dependency_overrides[mcp_routes.settings_dep] = lambda: self.settings
        self.client = TestClient(app)
        return self.client

    def __exit__(self, exc_type, exc, traceback) -> None:  # noqa: ANN001
        app.dependency_overrides.clear()


def write_pizzerias(tmp_path: Path) -> Path:
    path = tmp_path / "pizzerias.json"
    path.write_text(
        """[
  {
    "id": "unit-tambov-1",
    "name": "Тамбов-1",
    "countryCode": 643,
    "businessId": "dodopizza",
    "unitType": 1
  },
  {
    "id": "unit-arkh-1",
    "name": "Архангельск-1",
    "countryCode": 643,
    "businessId": "dodopizza",
    "unitType": 1
  }
]""",
        encoding="utf-8",
    )
    return path
