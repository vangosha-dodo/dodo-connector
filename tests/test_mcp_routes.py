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


def call_mcp_tool(
    tmp_path: Path,
    name: str,
    arguments: dict[str, object],
    *,
    request_id: int,
) -> dict[str, object]:
    with mcp_client(tmp_path) as client:
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
    def __init__(self, tmp_path: Path):
        self.settings = Settings(
            api_keys=[],
            tool_registry_path=Path("configs/tools.example.yaml"),
            policy_path=Path("configs/policy.example.yaml"),
            audit_db_path=tmp_path / "audit.sqlite3",
            dodo_access_token=None,
            dodo_pizzerias_path=None,
        )
        self.client: TestClient | None = None

    def __enter__(self) -> TestClient:
        from dodo_bridge import mcp_routes

        app.dependency_overrides[mcp_routes.settings_dep] = lambda: self.settings
        self.client = TestClient(app)
        return self.client

    def __exit__(self, exc_type, exc, traceback) -> None:  # noqa: ANN001
        app.dependency_overrides.clear()
