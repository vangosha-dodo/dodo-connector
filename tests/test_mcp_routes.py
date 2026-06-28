from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from dodo_bridge.config import Settings
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
