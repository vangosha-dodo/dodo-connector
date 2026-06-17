# Step-by-step Plan

## Phase 0 - Repository Baseline

1. Create a local git repository for the bridge.
2. Add a runnable FastAPI service skeleton.
3. Add config-driven tool registry and deny-by-default policy.
4. Add audit logging and a recommendations endpoint.
5. Commit the baseline.

## Phase 1 - Read-only MVP

1. Import Dodo IS Postman collection into disabled tool candidates.
2. Choose 5-10 read-only business tools:
   - sales summary;
   - inventory stock balances;
   - stop sales;
   - production productivity;
   - courier/order delivery stats;
   - units list;
   - selected Superset dashboard/chart data.
3. Add response filters so ChatGPT receives compact JSON instead of raw payloads.
4. Publish a GPT Action OpenAPI schema for the approved tools only.
5. Add API key auth, rate limits, request size limits, and secret redaction.

## Phase 2 - Learning Loop

1. Log unknown/denied tool requests with intent and actor.
2. Add feedback collection after answers: useful, wrong, too broad, unsafe.
3. Generate recommendations:
   - enable frequently requested denied read tools;
   - restrict tools with repeated negative feedback;
   - add response filters for large outputs;
   - require approval for sensitive/write-like tools.
4. Review recommendations in pull requests; do not auto-apply them.

## Phase 3 - Superset Analytics

1. Connect to Superset 4.1.1 via REST API or community MCP adapter.
2. Start with dashboards/charts/saved queries, not arbitrary SQL.
3. Add a curated SQL allowlist only after table-level permissions are clear.
4. Add caching for chart data and aggregate responses.

## Phase 4 - Write Operations

1. Keep writes disabled until read-only usage is stable.
2. Add two-step confirmation for each write.
3. Add idempotency keys and rollback/compensation notes where possible.
4. Require a named human actor and store full audit context.

## Phase 4A - Scheduled Google Sheets Automations

1. Keep Dodo IS read-only, but allow explicitly approved Google Sheets writes.
2. Implement dry-run previews before enabling any scheduled write job.
3. Add idempotency, job locks, audit logs, and per-sheet/range allowlists.
4. Start with the courier payroll daily export and weekly payment register.
5. Track candidates in `docs/AUTOMATION_CANDIDATES.md`.

## Phase 5 - Production Hardening

1. Add OAuth/mTLS if exposing to ChatGPT Apps/MCP.
2. Add structured logs and monitoring.
3. Add backup/retention policy for audit data.
4. Add deployment manifests for the Ubuntu server.
5. Add CI for tests and policy linting.
