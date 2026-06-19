# Dodo ChatGPT Bridge - project status

Updated: 2026-06-19

## Goal

Build a read-only Bridge between ChatGPT and Dodo IS so the ChatGPT agent can
answer operational and management questions directly from approved data sources
without routing normal requests through OpenClaw.

The public Bridge endpoint is:

```text
https://dock-translations-investigated-basketball.trycloudflare.com
```

The GitHub repository is:

```text
https://github.com/vangosha-dodo/dodo-connector
```

## Current Rule

Everything exposed to ChatGPT must remain read-only.

ChatGPT Action OpenAPI must not expose write/admin/internal automation routes.
Any write-capable automation remains outside the agent surface and requires a
separate explicit enablement path.

## Implemented And Deployed

### Bridge foundation

- FastAPI Bridge service on the Ubuntu server.
- API-key protection for Bridge endpoints.
- Tool registry and policy layer.
- Audit log for Bridge calls.
- Public Cloudflare URL for ChatGPT Action calls.
- OpenAPI export script for ChatGPT Actions.
- Public ChatGPT Action schema URL:
  - `GET /chatgpt/openapi.yaml`
  - This generates the current read-only Action schema from Bridge code.
  - The public route supports `HEAD`, gzip compression, and keeps the external
    server URL as `https://dock-translations-investigated-basketball.trycloudflare.com`.
- Caddy allowlist for the public tunnel is tracked in `deploy/caddy/Caddyfile`.
- GitHub synchronization for the local project.

### Pizzeria catalog

- `GET /dodo/pizzerias`
- Production catalog currently includes 16 pizzerias:
  - Архангельск-1
  - Архангельск-2
  - Архангельск-3
  - Белогорск-1
  - Благовещенск-1
  - Благовещенск-2
  - Благовещенск-3
  - Северодвинск-1
  - Северодвинск-2
  - Тамбов-1
  - Тамбов-2
  - Тамбов-3
  - Чита-1
  - Чита-2
  - Чита-3
  - Чита-4

### Dodo API read-only endpoints

- `GET /dodo/functions`
- `GET /dodo/delivery/courier-orders`
- `GET /dodo/delivery/statistics`
- `GET /dodo/staff/shifts`
- `GET /dodo/staff/vacancies/count`
- `GET /dodo/accounting/sales`
- `GET /dodo/accounting/sales/summary`
- `GET /dodo/accounting/sales/comparison`
- `GET /dodo/accounting/writeoffs/products`
- `GET /dodo/accounting/writeoffs/products/summary`
- `GET /dodo/accounting/slices/writeoff-rate`
- `GET /dodo/accounting/inventory-stocks`
- `GET /dodo/accounting/stock-consumptions-by-period`
- `GET /dodo/units/month-goals`
- `GET /dodo/ratings/customer-experience`
- `GET /dodo/ratings/standards`

### Compact aggregations for ChatGPT

These endpoints are preferred for agent questions because they return compact
answers instead of huge raw Dodo rows.

- Product write-off summary:
  - `GET /dodo/accounting/writeoffs/products/summary`
  - For questions like "списания кусочков по всем пиццериям".
- Slice write-off rate:
  - `GET /dodo/accounting/slices/writeoff-rate`
  - Computes write-offs as a percent of laid-out quantity.
- Sales revenue summary:
  - `GET /dodo/accounting/sales/summary`
  - For questions like "выручка по всем пиццериям за май 2026".
  - `salesWithDiscount` is computed from `products[].priceWithDiscount`.
  - `salesWithoutDiscount` is computed from `products[].price`.
  - `averageCheck` is computed as `salesWithDiscount / orders`.
  - Supports daily SQLite cache modes: `auto`, `refresh`, and `bypass`.
- Sales revenue comparison:
  - `GET /dodo/accounting/sales/comparison`
  - Compares current and baseline periods.
  - Returns current, baseline, absolute change, percent change, and per-pizzeria
    deltas.
  - Uses the same read-only sales source and cache behavior as sales summary.

### Superset read-only capabilities

- Employee discount:
  - `POST /analytics/employee-discount`
  - Uses approved Superset chart payloads.
- Kiosk sales share:
  - `POST /analytics/kiosk-sales-share`
  - Uses approved Superset chart payloads.

### Authorization support

- Internal Dodo IS web authorization page:
  - `GET /auth/dodo`
  - Supports session refresh and email MFA code entry.
- Internal Dodo Knowledge Base authorization page:
  - `GET /auth/kb`
  - `POST /auth/kb/status`
  - `POST /auth/kb/refresh`
  - Reuses OpenClaw Dodo credentials and mailbox access to refresh
    `dodopizza.info` cookies without printing MFA codes.
- This is admin/internal and is not exported to ChatGPT Action schema.

### Learning / missing capability capture

- `POST /system/missing-capability`
- Allows the agent to record a missing read-only capability in the Bridge
  backlog without changing Dodo IS.

## Verified Recently

### Tests

- Local test suite after sales comparison changes:
  - `92 passed`

### Live checks

- Public Cloudflare route for `GET /dodo/accounting/sales/summary` returns `200`.
- Public Cloudflare route for `GET /dodo/accounting/sales/comparison` returns `200`.
- Public OpenAPI schema includes `getDodoAccountingSalesComparison`.
- Internal `POST /auth/kb/refresh` successfully created
  `dodopizza_info_session.json` from `dodopizza.info`.
- Internal `POST /auth/kb/status` returned `ok: true` for the saved Knowledge
  Base session.
- Public Cloudflare `/auth/kb` remains closed (`404`), so the KB auth workflow
  is internal-only.
- Small live sales summary query through the public URL returned correct compact
  totals.
- Small live sales comparison query for one pizzeria returned current, baseline,
  absolute change, and percent change.
- Dodo OAuth token on the server was refreshed and synced into Bridge `.env`.

### Example result

The May 2026 sales summary across all 16 pizzerias was computed from Dodo API
raw accounting sales:

- Sales with discount: `243093174`
- Sales without discount: `269752883`
- Discount: `26659709`
- Raw sales rows aggregated: `235734`
- Product rows aggregated: `926037`
- Dodo pages fetched: `243`

This full-month live computation took about 4 minutes 25 seconds. A daily
SQLite cache has been added so repeated requests can answer from Bridge cache
after the first calculation or scheduled refresh.

## Known Issues And Constraints

- Raw `GET /dodo/accounting/sales` is too heavy for broad month-long questions.
  The agent should use `GET /dodo/accounting/sales/summary` instead.
- Full-month sales summaries are correct but slow without cache.
- Some Dodo API endpoints are blocked by token scopes or may require additional
  role/access review.
- Superset-only metrics require an explicit extraction recipe:
  dashboard, chart, payload, filters, formula, and expected output.
- Some pizzerias can legitimately return zero rows for a period; the Bridge uses
  the pizzeria catalog to keep their names visible.
- Dodo Knowledge Base authentication is now available, but no KB search/read
  endpoint has been exposed to ChatGPT yet.

## Deferred

Google Sheets automations are intentionally paused for now:

- Courier payroll daily export / weekly registry.
- Cost analysis 2026 sheet filling.
- Measurements tracker filling.

The existing dry-run scaffold and technical notes remain in the repository, but
they are not part of the active next steps.

## Active Next Steps

### 1. Warm and schedule the sales summary cache

Goal: make questions like "выручка за май по всем пиццериям" answer in seconds.

Implemented foundation:

- Store daily pizzeria sales summaries in a local Bridge database table.
- Let `GET /dodo/accounting/sales/summary` read from cache when available.
- Return source metadata showing whether the answer came from cache, live Dodo
  API, or mixed mode.
- Add `scripts/refresh_sales_summary_cache.py` for manual or scheduled cache
  refresh by preset (`yesterday`, `current-month`, `previous-month`) or explicit
  period.
- Add systemd units:
  - `deploy/systemd/dodo-sales-cache-refresh.service`
  - `deploy/systemd/dodo-sales-cache-refresh.timer`

Remaining work:

- Decide cache freshness rules for current-day data.

### 2. Update ChatGPT agent configuration

Goal: make the agent reliably choose compact endpoints.

Actions:

- Import the latest schema from:
  - `https://dock-translations-investigated-basketball.trycloudflare.com/chatgpt/openapi.yaml`
- Update the agent prompt:
  - read-only mode is mandatory;
  - use `getDodoAccountingSalesSummary` for revenue;
  - use compact write-off endpoints for broad write-off questions;
  - do not call raw row endpoints for wide monthly questions unless the user
    explicitly asks for raw rows.
- Run a checklist of typical questions.

### 3. Add management aggregations

Priority candidates:

- Revenue, orders, products, average check.
- Discounts by pizzeria and period.
- Write-offs by product/reason/pizzeria.
- Slice write-off rate by pizzeria.
- Channel split: delivery, dine-in, pickup, kiosk where data source is available.
- Period comparison: day/week/month versus previous period or previous year.

### 4. Continue Superset capabilities

Goal: support metrics that Dodo API does not expose directly.

Process for each metric:

- Confirm source dashboard/chart.
- Capture Superset payload.
- Define filters and allowed dimensions.
- Define output schema.
- Add read-only Bridge endpoint.
- Add tests and OpenAPI operation.

Initial candidates:

- Employee discount details.
- Showcase / laid-out quantity metrics if they exist only in Superset.
- Kiosk and cashier identification metrics.

### 5. Add read-only Knowledge Base retrieval

Goal: let the agent answer policy/process questions from Dodo Knowledge Base
without giving ChatGPT direct login or write/admin access.

Implemented foundation:

- Refresh and check a dedicated `dodopizza.info` session file through
  `/auth/kb`.
- Reuse OpenClaw mailbox access for MFA without printing codes.
- Keep KB auth routes internal and outside the public ChatGPT Action schema.

Remaining work:

- Decide retrieval mode: targeted page fetch by URL, small crawler/index, or
  search endpoint if the site exposes one.
- Define allowed domains and maximum response size.
- Add read-only `/knowledge-base/...` endpoints and tests.
- Add only safe retrieval endpoints to ChatGPT OpenAPI after verification.

## Next Decision

Recommended next implementation step:

```text
Choose the next active track: finish sales cache scheduling, or add read-only
Knowledge Base retrieval on top of the new KB session.
```

Reason: the sales cache fixes management metrics speed; KB retrieval unlocks
policy/process answers from Dodo's closed documentation.
