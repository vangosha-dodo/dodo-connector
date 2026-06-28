# MCP Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a minimal read-only MCP-compatible HTTP endpoint on top of the existing Dodo ChatGPT Bridge.

**Architecture:** Keep REST/OpenAPI routes as the stable production interface. Add a thin FastAPI JSON-RPC adapter at `/mcp` that exposes a small set of MCP tools and delegates to existing registry, policy, Dodo data services, Superset recipes, and missing-capability backlog.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic, pytest, existing Bridge registry/policy/audit code.

## Global Constraints

- Bridge remains read-only for Dodo IS, Superset, Office Manager, and ChatGPT-facing tools.
- MCP endpoint must not expose arbitrary URL, SQL, JavaScript, browser automation, or write/admin execution.
- Tool calls must pass through existing authentication, policy, and audit layers.
- First release exposes only router tools, not every internal capability as separate MCP tools.
- No new runtime dependency unless the MCP adapter cannot be implemented with existing FastAPI JSON-RPC handling.

---

### Task 1: MCP Discovery

**Files:**
- Create: `dodo_bridge/mcp_routes.py`
- Modify: `dodo_bridge/main.py`
- Test: `tests/test_mcp_routes.py`

**Interfaces:**
- Consumes: `authenticate_actor`, `Settings`, `ToolRegistry`, `PolicyEngine`, `DodoDataService.list_functions()`.
- Produces: FastAPI router with `POST /mcp` handling JSON-RPC methods `initialize`, `tools/list`, and unknown-method errors.

- [ ] **Step 1: Write failing tests**

```python
def test_mcp_initialize_returns_server_capabilities():
    response = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert response.status_code == 200
    assert response.json()["result"]["serverInfo"]["name"] == "dodo-chatgpt-bridge"
    assert response.json()["result"]["capabilities"]["tools"] == {}


def test_mcp_tools_list_exposes_router_tools_only():
    response = client.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    tool_names = {tool["name"] for tool in response.json()["result"]["tools"]}
    assert {"list_capabilities", "dodo_api_query", "superset_query", "office_manager_query", "report_missing_capability"} <= tool_names
    assert "getDodoAccountingSalesSummary" not in tool_names
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_mcp_routes.py -q`

Expected: FAIL because `/mcp` does not exist yet.

- [ ] **Step 3: Implement discovery**

Create `dodo_bridge/mcp_routes.py` with:
- `router = APIRouter(tags=["mcp"])`
- shared dependencies matching existing routes
- JSON-RPC success and error helpers
- static router tool definitions with input schemas
- `initialize` and `tools/list` handlers

Modify `dodo_bridge/main.py` to include `mcp_router`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_mcp_routes.py -q`

Expected: PASS.

### Task 2: MCP Tool Calls

**Files:**
- Modify: `dodo_bridge/mcp_routes.py`
- Test: `tests/test_mcp_routes.py`

**Interfaces:**
- Consumes: `DodoDataService.fetch`, `DodoDataService.fetch_*_summary` later as needed, `SupersetConnector` through existing analytics route patterns, `AuditStore`.
- Produces: `tools/call` support for the first safe functions.

- [ ] **Step 1: Write failing tests**

```python
def test_mcp_tools_call_list_capabilities_returns_read_only_capabilities():
    response = client.post("/mcp", json={
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {"name": "list_capabilities", "arguments": {}},
    })
    result = response.json()["result"]
    assert result["isError"] is False
    assert "read-only" in result["content"][0]["text"]


def test_mcp_tools_call_rejects_unknown_tool():
    response = client.post("/mcp", json={
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {"name": "delete_orders", "arguments": {}},
    })
    assert response.json()["error"]["code"] == -32602
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_mcp_routes.py -q`

Expected: FAIL because `tools/call` is not implemented yet.

- [ ] **Step 3: Implement safe calls**

Implement:
- `list_capabilities`: returns available read-only capabilities from `DodoDataService.list_functions()` plus the static MCP router list.
- `report_missing_capability`: records backlog through the same audit-backed behavior as `/system/missing-capability`.
- `dodo_api_query`, `superset_query`, `office_manager_query`: first release returns structured `capability_not_enabled` unless capability is explicitly mapped in an internal allowlist.

- [ ] **Step 4: Run focused and route tests**

Run:
- `pytest tests/test_mcp_routes.py -q`
- `pytest tests/test_export_chatgpt_openapi.py tests/test_chatgpt_openapi_route.py -q`

Expected: PASS.

### Task 3: Documentation And Deployment

**Files:**
- Create or modify: `docs/MCP_ADAPTER.md`
- Modify: `docs/PROJECT_STATUS.md`

**Interfaces:**
- Produces: operator-facing documentation for connecting future MCP clients.

- [ ] **Step 1: Document endpoint and safety model**

Document:
- Endpoint: `POST /mcp`
- Auth: same Bridge API key as REST Actions
- Supported methods: `initialize`, `tools/list`, `tools/call`
- First tools: `list_capabilities`, `dodo_api_query`, `superset_query`, `office_manager_query`, `report_missing_capability`
- Read-only guarantee and capability allowlist rule

- [ ] **Step 2: Run full relevant tests**

Run: `pytest tests/test_mcp_routes.py tests/test_export_chatgpt_openapi.py tests/test_chatgpt_openapi_route.py -q`

Expected: PASS.

- [ ] **Step 3: Deploy to server**

Copy changed files to `/home/ubuntu/dodo-chatgpt-bridge`, restart `dodo-bridge`, and verify:
- `systemctl is-active dodo-bridge`
- public `/mcp` `initialize` returns JSON-RPC result

- [ ] **Step 4: Commit and push**

Run:
- `git add docs/superpowers/plans/2026-06-28-mcp-adapter.md dodo_bridge/mcp_routes.py dodo_bridge/main.py tests/test_mcp_routes.py docs/MCP_ADAPTER.md docs/PROJECT_STATUS.md`
- `git commit -m "Add read-only MCP adapter"`
- `git push`
