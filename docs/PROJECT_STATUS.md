# Dodo ChatGPT Bridge - project status

Updated: 2026-06-28

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
- Experimental MCP adapter:
  - `POST /mcp`
  - Supports JSON-RPC `initialize`, `tools/list`, and `tools/call`.
  - Diagnostic `GET /mcp/capabilities` returns executable router capabilities
    without JSON-RPC and is intentionally excluded from ChatGPT OpenAPI.
  - Exposes router tools only: `list_capabilities`, `dodo_api_query`,
    `superset_query`, `office_manager_query`, and `report_missing_capability`.
  - `list_capabilities` reports only capabilities that the MCP router can
    execute, not every internal Dodo function.
  - Executable Dodo router capabilities:
    `accounting_sales_summary`, `accounting_sales_comparison`,
    `accounting_writeoffs_products_summary`, `accounting_slice_writeoff_rate`,
    `accounting_slice_daily_dynamics`, `accounting_sales_channels_summary`, and
    `accounting_sales_discounts_summary`,
    `accounting_inventory_stocks_summary`,
    `accounting_stock_consumptions_by_period_summary`,
    `ratings_customer_experience_summary`, `ratings_standards_summary`, and
    `delivery_courier_productivity_summary`, `staff_vacancies_count`,
    `units_month_goals`, `orders_clients_statistics`,
    `production_productivity`, and `production_orders_handover_time`.
  - First executable Superset router capabilities: `employee_discount` and
    `kiosk_sales_share`.
  - First executable Office Manager router capability:
    `courier_payroll_daily_export` in dry-run/read-only mode only.
  - Unknown or unmapped capabilities return `capability_not_enabled`; no
    arbitrary URL, SQL, JavaScript, browser command, write, or admin execution is
    allowed.
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
- `GET /dodo/orders/clients-statistics`
- `GET /dodo/production/productivity`
- `GET /dodo/production/orders-handover-time`
- `GET /dodo/staff/shifts`
- `GET /dodo/staff/vacancies/count`
- `GET /dodo/accounting/sales`
- `GET /dodo/accounting/sales/summary`
- `GET /dodo/accounting/sales/comparison`
- `GET /dodo/accounting/sales/channels-summary`
- `GET /dodo/accounting/sales/discounts-summary`
- `GET /dodo/accounting/writeoffs/products`
- `GET /dodo/accounting/writeoffs/products/summary`
- `GET /dodo/accounting/slices/writeoff-rate`
- `GET /dodo/accounting/slices/daily-dynamics`
- `GET /dodo/accounting/inventory-stocks`
- `GET /dodo/accounting/inventory-stocks/summary`
- `GET /dodo/accounting/stock-consumptions-by-period`
- `GET /dodo/accounting/stock-consumptions-by-period/summary`
- `GET /dodo/units/month-goals`
- `GET /dodo/ratings/customer-experience`
- `GET /dodo/ratings/customer-experience/summary`
- `GET /dodo/ratings/standards`
- `GET /dodo/ratings/standards/summary`

### Compact aggregations for ChatGPT

These endpoints are preferred for agent questions because they return compact
answers instead of huge raw Dodo rows.

- Product write-off summary:
  - `GET /dodo/accounting/writeoffs/products/summary`
  - For questions like "списания кусочков по всем пиццериям".
  - `units` is optional; when omitted, Bridge uses all configured pizzerias.

### CVM source probes behind scope checks

These routes are exposed as read-only ChatGPT Actions so the agent can request
the CVM metrics and receive a clear scope diagnostic when the current Dodo token
is not allowed to read them.

- Client statistics:
  - `GET /dodo/orders/clients-statistics`
  - Intended for new client share and 30-day churn share.
  - Current Dodo token may return `InsufficientScopes`; required scope hint from
    prior live probe: `orders`.
- Production productivity:
  - `GET /dodo/production/productivity`
  - Intended for kitchen productivity/load metrics.
  - Current Dodo token may return `InsufficientScopes`; required scope hint:
    `productionefficiency`.
- Production order handover time:
  - `GET /dodo/production/orders-handover-time`
  - Intended for handover and heat-shelf load metrics.
  - Current Dodo token may return `InsufficientScopes`; required scope hint:
    `productionefficiency`.
- Slice write-off rate:
  - `GET /dodo/accounting/slices/writeoff-rate`
  - Computes write-offs as a percent of laid-out quantity.
  - `units` is optional; when omitted, Bridge uses all configured pizzerias.
- Sales revenue summary:
  - `GET /dodo/accounting/sales/summary`
  - For questions like "выручка по всем пиццериям за май 2026".
  - `units` is optional; when omitted, Bridge uses all configured pizzerias.
  - `salesWithDiscount` is computed from `products[].priceWithDiscount`.
  - `salesWithoutDiscount` is computed from `products[].price`.
  - `averageCheck` is computed as `salesWithDiscount / orders`.
  - Supports daily SQLite cache modes: `auto`, `refresh`, and `bypass`.
- Sales revenue comparison:
  - `GET /dodo/accounting/sales/comparison`
  - Compares current and baseline periods.
  - `units` is optional; when omitted, Bridge uses all configured pizzerias.
  - Returns current, baseline, absolute change, percent change, and per-pizzeria
    deltas.
  - Uses the same read-only sales source and cache behavior as sales summary.
- Sales channel/source summary:
  - `GET /dodo/accounting/sales/channels-summary`
  - Groups read-only accounting sales by `salesChannel` and `orderSource`.
  - Returns restaurant and delivery checks/day z-scores for CVM analysis.
  - Returns kiosk order/sales share from `orderSource=Kiosk`.
  - `units` is optional; when omitted, Bridge uses all configured pizzerias.
- Sales discount category summary:
  - `GET /dodo/accounting/sales/discounts-summary`
  - Groups read-only product discounts by heuristic categories such as CVM,
    local, combo, dodocoins, certificates, vouchers, employee, and other.
  - Returns discount amount and percent of sales without discount.
  - `includeActions=true` returns top source Dodo actions with masked promocode
    metadata.
  - `units` is optional; when omitted, Bridge uses all configured pizzerias.
- Slice daily dynamics:
  - `GET /dodo/accounting/slices/daily-dynamics`
  - Groups read-only Dodo accounting sales and product write-offs by day.
  - Use for questions like "динамика продажи и списания кусочков по Чите-2 в
    июне".
  - Requires `units`; resolve pizzeria names through `GET /dodo/pizzerias`.
- Rating summaries:
  - `GET /dodo/ratings/customer-experience/summary`
  - `GET /dodo/ratings/standards/summary`
  - Compactly returns average rating, best/worst pizzerias, and units below a
    configurable threshold.
  - When `units` and `countryCode` are omitted, Bridge summarizes the configured
    pizzeria catalog instead of the full country.
- Inventory stock summary:
  - `GET /dodo/accounting/inventory-stocks/summary`
  - Compactly returns total stock money, critical low-stock items, zero/negative
    balances, high-stock items, and top balance-in-money items.
  - `units` is optional; when omitted, Bridge uses all configured pizzerias.
- Stock consumption summary:
  - `GET /dodo/accounting/stock-consumptions-by-period/summary`
  - Compactly returns total cost, pizzeria totals, consumption type totals,
    measurement unit totals, top stock items, and top pizzeria-item pairs.
  - User-facing `to` is inclusive; Bridge sends the Dodo API an exclusive
    next-day `to` because the source rejects same-day ranges otherwise.

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

- Local test suite after CVM source route changes:
  - `105 passed`

### Live checks

- Public Cloudflare route for `GET /dodo/accounting/sales/summary` returns `200`.
- Public Cloudflare route for `GET /dodo/accounting/sales/comparison` returns `200`.
- Public Cloudflare route for `GET /dodo/accounting/sales/channels-summary`
  returns `200`.
- Public Cloudflare route for `GET /dodo/accounting/sales/discounts-summary`
  returns `200`.
- MCP `dodo_api_query` maps the compact inventory, stock consumption, ratings,
  courier productivity summaries, vacancies, month goals, client statistics,
  and production source probes to the existing read-only service layer.
- MCP `office_manager_query` maps `courier_payroll_daily_export` to the internal
  dry-run planner. It can plan Office Manager extraction and planned sheet rows,
  but write flags remain disabled.
- Public Cloudflare route for `GET /dodo/orders/clients-statistics` returns
  `200` with `status=blocked_by_scope` and required scope hint `orders` when
  the current token lacks that scope.
- Public Cloudflare routes for `GET /dodo/production/productivity` and
  `GET /dodo/production/orders-handover-time` return `200` with
  `status=blocked_by_scope` and required scope hint `productionefficiency` when
  the current token lacks that scope.
- Public OpenAPI schema includes `getDodoAccountingSalesComparison`.
- Public OpenAPI schema includes `getDodoAccountingSalesChannelsSummary`.
- Public OpenAPI schema includes `getDodoAccountingSalesDiscountsSummary`.
- Public OpenAPI schema includes `getDodoOrdersClientsStatistics`,
  `getDodoProductionProductivity`, and
  `getDodoProductionOrdersHandoverTime`.
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

### CVM report review

The Google Sheet `Маркетинг - отчётность dodotm`, sheet `CVM влияние`, was
reviewed. Primary metrics are tracked in `docs/CVM_REPORT_METRICS.md`.

First implemented metric block:

- restaurant checks/day z-score;
- delivery checks/day z-score;
- kiosk share from sales source/order source data.
- first-pass discount category shares from Dodo sales product discount metadata.

Blocked or pending metric blocks:

- new clients and 30-day churn routes are ready but require Dodo `orders` scope
  or a Superset/web recipe;
- production/load routes are ready but require `productionefficiency` scope or
  Superset/web recipes;
- exact discount-tab parity still needs a general Superset discount recipe.

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
- Add current-month cache warmup units:
  - `deploy/systemd/dodo-sales-cache-current-month.service`
  - `deploy/systemd/dodo-sales-cache-current-month.timer`
  - Uses `cacheMode=auto` so it backfills cache gaps without forcing a full
    recalculation when the daily cache is already warm.
- Add Dodo API token refresh unit before cache warmup:
  - `deploy/systemd/dodo-token-refresh.service`
  - `deploy/systemd/dodo-token-refresh.timer`
  - Refreshes `DODO_ACCESS_TOKEN` from the saved OpenClaw OAuth files and
    restarts `dodo-bridge` before the cache jobs run.
  - This fixes the failure mode where another token refresh updates `.env` but
    the already-running Bridge process keeps using the old token.

Verified cache coverage:

- May 2026: fully cached for all 16 pizzerias.
- June 1-21, 2026: fully cached for all 16 pizzerias after renewing the Dodo
  API token and rerunning the current-month cache warmup.
- Public check for June 1-21, 2026 with `cacheMode=auto` returned
  `dailyRowsHit=336`, `dailyRowsMissed=0`, and `unitsFetchedLive=0`.
- Public check for `GET /dodo/accounting/slices/daily-dynamics` on
  `Чита-2`, June 1-21, 2026 returned 21 daily rows with no truncation.

Remaining work:

- Decide cache freshness rules for current-day data.

### 2. Update ChatGPT agent configuration

Goal: make the agent reliably choose compact endpoints.

Actions:

- Current prompt draft:
  - `docs/CHATGPT_AGENT_PROMPT.md`
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
