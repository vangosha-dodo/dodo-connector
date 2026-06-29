# Bridge Update Check

Run this after Bridge code, OpenAPI, MCP router, or Caddy allowlist changes.

## From the server

```bash
cd /home/ubuntu/dodo-chatgpt-bridge
PYTHONPATH=. .venv/bin/python -m scripts.check_bridge_health --base-url http://127.0.0.1:8000
```

## From this Windows workspace

```powershell
$line = ssh -o BatchMode=yes ubuntu@92.243.27.224 "cd /home/ubuntu/dodo-chatgpt-bridge && grep '^DODO_BRIDGE_API_KEYS=' .env"
$key = ($line -replace '^DODO_BRIDGE_API_KEYS=', '').Trim().Trim('"').Split(',')[0].Trim()
python -m scripts.check_bridge_health --base-url https://dock-translations-investigated-basketball.trycloudflare.com --api-key $key
Remove-Variable key
```

Expected result:

```text
OK Bridge health-check: https://dock-translations-investigated-basketball.trycloudflare.com
- OK health: status=ok
- OK openapi_operation_limit: 26 <= 30
- OK mcp_diagnostic_not_in_openapi: absent
- OK mcp_read_only: read_only=True
- OK forbidden_capabilities_absent: absent
```

The command does not print the API key. If a check fails, do not update the
ChatGPT Action schema until the failing item is understood.

## What It Guards

- Bridge process responds to `/health`.
- ChatGPT OpenAPI stays under the 30-operation limit.
- Diagnostic `/mcp/capabilities` stays outside ChatGPT Actions.
- MCP router reports `read_only=true`.
- Known unmapped raw capabilities, such as `courier_orders`, are not advertised.
