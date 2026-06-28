# Dodo Bridge MCP Adapter

The MCP adapter is an experimental read-only interface on top of the existing
Dodo ChatGPT Bridge. It does not replace the REST/OpenAPI ChatGPT Actions
surface; it gives future MCP clients a smaller dynamic tool surface.

## Endpoint

```text
POST /mcp
```

Use the same Bridge API key as REST routes:

```text
Authorization: Bearer <bridge-api-key>
```

If local settings have no API keys configured, the endpoint is open in the same
way as the existing test/dev Bridge routes.

## Supported MCP Methods

- `initialize`
- `notifications/initialized`
- `tools/list`
- `tools/call`

The endpoint uses JSON-RPC 2.0 request and response envelopes.

## MCP Tools

- `list_capabilities`
  - Lists read-only Bridge MCP router tools and Dodo capabilities.
- `dodo_api_query`
  - Runs an approved read-only Dodo API capability by name.
  - Enabled capabilities:
    - `accounting_sales_summary`
    - `accounting_writeoffs_products_summary`
    - `accounting_slice_writeoff_rate`
    - `accounting_slice_daily_dynamics`
    - `accounting_sales_channels_summary`
    - `accounting_sales_discounts_summary`
- `superset_query`
  - Runs approved Superset recipes by capability name.
  - Enabled capabilities:
    - `employee_discount`
    - `kiosk_sales_share`
- `office_manager_query`
  - Reserved for approved Office Manager read-only extractors.
  - Currently returns `capability_not_enabled` unless a capability is mapped in
    Bridge code.
- `report_missing_capability`
  - Records an internal Bridge backlog entry for a missing read-only capability.
  - It does not change Dodo IS, Superset, or Office Manager.

## Safety Model

- The adapter exposes router tools only; it does not publish every internal
  Bridge function as a separate MCP tool.
- Router tools accept only capability names explicitly mapped in Bridge code.
- Arbitrary URLs, SQL, JavaScript, browser commands, write actions, and admin
  actions are not accepted.
- Dodo API execution still goes through the existing registry, policy, and
  read-only service layer.
- Tool definitions are annotated with MCP read-only hints, but Bridge policy is
  the source of truth.

## Example: List Tools

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/list",
  "params": {}
}
```

## Example: Sales Summary

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/call",
  "params": {
    "name": "dodo_api_query",
    "arguments": {
      "capability": "accounting_sales_summary",
      "parameters": {
        "units": "unit-id-1,unit-id-2",
        "from": "2026-05-01",
        "to": "2026-05-31",
        "cacheMode": "auto"
      },
      "dry_run": false
    }
  }
}
```

For all configured pizzerias, omit `parameters.units`; Bridge will use the same
pizzeria catalog as the REST summary endpoints.

## Example: Slice Daily Dynamics

```json
{
  "jsonrpc": "2.0",
  "id": 5,
  "method": "tools/call",
  "params": {
    "name": "dodo_api_query",
    "arguments": {
      "capability": "accounting_slice_daily_dynamics",
      "parameters": {
        "units": "unit-id-1",
        "from": "2026-06-01",
        "to": "2026-06-30",
        "productNamePrefix": "Кус",
        "includeProducts": false
      },
      "dry_run": false
    }
  }
}
```

## Example: Employee Discount

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "superset_query",
    "arguments": {
      "capability": "employee_discount",
      "parameters": {
        "unit_names": ["Тамбов-1"],
        "period": {"from": "2026-06-01", "to": "2026-06-30"}
      },
      "dry_run": false
    }
  }
}
```

## Example: Kiosk Sales Share

```json
{
  "jsonrpc": "2.0",
  "id": 4,
  "method": "tools/call",
  "params": {
    "name": "superset_query",
    "arguments": {
      "capability": "kiosk_sales_share",
      "parameters": {
        "unit_names": ["Чита-2"],
        "month": "2026-06"
      },
      "dry_run": false
    }
  }
}
```
